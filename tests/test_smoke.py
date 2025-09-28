# tests/test_smoke.py
"""Smoke tests for weatherbot."""

import pytest


def test_package_imports() -> None:
    """Test that all main modules can be imported."""
    import weatherbot
    import weatherbot.alerting
    import weatherbot.cli
    import weatherbot.config
    import weatherbot.geometry
    import weatherbot.logging_setup
    import weatherbot.nhc
    import weatherbot.notifiers.toast
    import weatherbot.nws
    import weatherbot.state

    assert weatherbot.__version__


def test_config_loading() -> None:
    """Test configuration loading with environment variables."""
    import os

    from weatherbot.config import WeatherbotConfig

    # Set test environment variables
    os.environ["HOME_LAT"] = "25.7617"
    os.environ["HOME_LON"] = "-80.1918"

    try:
        config = WeatherbotConfig()
        assert config.home_lat == 25.7617
        assert config.home_lon == -80.1918
        assert config.toast_enabled is True
    finally:
        # Clean up
        os.environ.pop("HOME_LAT", None)
        os.environ.pop("HOME_LON", None)


def test_cli_entry_point() -> None:
    """Test that CLI entry point exists and loads."""
    from weatherbot.cli import app

    assert app is not None
    assert hasattr(app, "registered_commands")


def test_state_management() -> None:
    """Test basic state operations."""
    from weatherbot.state import WeatherbotState

    state = WeatherbotState()
    assert state.last_cone_advisories == {}
    assert state.last_alert_ids == []
    assert state.was_in_cone is False

    # Test advisory tracking
    assert state.is_new_cone_advisory("AL012023", "001")
    state.update_cone_advisory("AL012023", "001")
    assert not state.is_new_cone_advisory("AL012023", "001")
    assert state.is_new_cone_advisory("AL012023", "002")

    # Test alert tracking
    assert state.is_new_alert("test-alert-id")
    state.add_alert_id("test-alert-id")
    assert not state.is_new_alert("test-alert-id")


def test_geometry_helpers() -> None:
    """Test basic geometry operations."""
    from weatherbot.geometry import create_point, validate_coordinates

    # Test coordinate validation
    validate_coordinates(-80.1918, 25.7617)  # Should not raise

    with pytest.raises(ValueError):
        validate_coordinates(200, 25)  # Invalid longitude

    with pytest.raises(ValueError):
        validate_coordinates(-80, 100)  # Invalid latitude

    # Test point creation
    point = create_point(-80.1918, 25.7617)
    assert point.x == -80.1918
    assert point.y == 25.7617
