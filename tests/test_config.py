# tests/test_config.py
"""Configuration tests for weatherbot."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from weatherbot.config import WeatherbotConfig, load_config


class TestWeatherbotConfig:
    """Test WeatherbotConfig class."""

    def test_valid_config(self) -> None:
        """Test valid configuration creation."""
        config = WeatherbotConfig(
            home_lat=25.7617,
            home_lon=-80.1918
        )
        assert config.home_lat == 25.7617
        assert config.home_lon == -80.1918
        assert config.toast_enabled is True
        assert config.use_county_intersect is False
        # alert_cooldown_minutes might be overridden by environment
        assert config.alert_cooldown_minutes >= 0
        assert config.log_level == "INFO"

    def test_latitude_validation(self) -> None:
        """Test latitude validation."""
        # Valid latitudes
        config = WeatherbotConfig(home_lat=0, home_lon=0)
        assert config.home_lat == 0

        config = WeatherbotConfig(home_lat=90, home_lon=0)
        assert config.home_lat == 90

        config = WeatherbotConfig(home_lat=-90, home_lon=0)
        assert config.home_lat == -90

        # Invalid latitudes
        with pytest.raises(ValidationError, match="Latitude must be between"):
            WeatherbotConfig(home_lat=91, home_lon=0)

        with pytest.raises(ValidationError, match="Latitude must be between"):
            WeatherbotConfig(home_lat=-91, home_lon=0)

    def test_longitude_validation(self) -> None:
        """Test longitude validation."""
        # Valid longitudes
        config = WeatherbotConfig(home_lat=0, home_lon=0)
        assert config.home_lon == 0

        config = WeatherbotConfig(home_lat=0, home_lon=180)
        assert config.home_lon == 180

        config = WeatherbotConfig(home_lat=0, home_lon=-180)
        assert config.home_lon == -180

        # Invalid longitudes
        with pytest.raises(ValidationError, match="Longitude must be between"):
            WeatherbotConfig(home_lat=0, home_lon=181)

        with pytest.raises(ValidationError, match="Longitude must be between"):
            WeatherbotConfig(home_lat=0, home_lon=-181)

    def test_log_level_validation(self) -> None:
        """Test log level validation."""
        # Valid log levels
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            config = WeatherbotConfig(home_lat=0, home_lon=0, log_level=level)
            assert config.log_level == level.upper()

        # Case insensitive
        config = WeatherbotConfig(home_lat=0, home_lon=0, log_level="debug")
        assert config.log_level == "DEBUG"

        # Invalid log level
        with pytest.raises(ValidationError, match="Log level must be one of"):
            WeatherbotConfig(home_lat=0, home_lon=0, log_level="INVALID")


    def test_optional_paths_validation(self) -> None:
        """Test optional path validation."""
        # Valid paths
        config = WeatherbotConfig(
            home_lat=0,
            home_lon=0,
            county_geojson_path="/path/to/file.geojson"
        )
        assert config.county_geojson_path == "/path/to/file.geojson"

        # Empty strings become None
        config = WeatherbotConfig(
            home_lat=0,
            home_lon=0,
            county_geojson_path=""
        )
        assert config.county_geojson_path is None

    def test_get_county_geojson_path(self) -> None:
        """Test county GeoJSON path resolution."""
        # Custom path
        config = WeatherbotConfig(
            home_lat=0,
            home_lon=0,
            county_geojson_path="/custom/path.geojson"
        )
        assert config.get_county_geojson_path() == Path("/custom/path.geojson")

        # Default path
        config = WeatherbotConfig(home_lat=0, home_lon=0)
        expected_path = Path(__file__).parent.parent / "src" / "weatherbot" / "data" / "default_area.geojson"
        assert config.get_county_geojson_path() == expected_path


    def test_get_alert_icon_path(self) -> None:
        """Test alert icon path resolution."""
        config = WeatherbotConfig(home_lat=0, home_lon=0)
        expected_path = Path(__file__).parent.parent / "src" / "weatherbot" / "icons" / "alert.ico"
        assert config.get_alert_icon_path() == expected_path

    @patch('weatherbot.config.validate_coordinate_coverage')
    def test_validate_coverage(self, mock_validate) -> None:
        """Test coverage validation."""
        mock_validate.return_value = {"status": "covered"}

        config = WeatherbotConfig(home_lat=25.7617, home_lon=-80.1918)
        result = config.validate_coverage()

        assert result == {"status": "covered"}
        mock_validate.assert_called_once_with(25.7617, -80.1918)


class TestLoadConfig:
    """Test load_config function."""

    def test_load_config_with_env_vars(self) -> None:
        """Test loading config with environment variables."""
        os.environ["HOME_LAT"] = "25.7617"
        os.environ["HOME_LON"] = "-80.1918"
        os.environ["TOAST_ENABLED"] = "false"

        try:
            config = load_config()
            assert config.home_lat == 25.7617
            assert config.home_lon == -80.1918
            assert config.toast_enabled is False
        finally:
            # Clean up
            os.environ.pop("HOME_LAT", None)
            os.environ.pop("HOME_LON", None)
            os.environ.pop("TOAST_ENABLED", None)

    def test_load_config_with_required_fields(self) -> None:
        """Test loading config when required fields are provided."""
        # Set required environment variables
        os.environ["HOME_LAT"] = "25.0"
        os.environ["HOME_LON"] = "-80.0"

        try:
            # Config should load successfully
            config = load_config()
            assert config is not None
            assert hasattr(config, 'home_lat')
            assert hasattr(config, 'home_lon')
            assert config.home_lat == 25.0
            assert config.home_lon == -80.0
        finally:
            # Clean up environment variables
            os.environ.pop("HOME_LAT", None)
            os.environ.pop("HOME_LON", None)
