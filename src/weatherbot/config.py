# src/weatherbot/config.py
"""Configuration management for Weatherbot."""

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .coverage_validator import validate_coordinate_coverage


class WeatherbotConfig(BaseSettings):
    """Configuration settings for Weatherbot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Location settings (required)
    home_lat: float = Field(..., description="Home latitude in decimal degrees")
    home_lon: float = Field(..., description="Home longitude in decimal degrees")

    # County intersection settings
    use_county_intersect: bool = Field(
        default=False,
        description="Use county-level intersection instead of point-only",
    )
    county_geojson_path: str | None = Field(
        default=None,
        description="Path to county GeoJSON file",
    )

    # Notification settings
    toast_enabled: bool = Field(
        default=True,
        description="Enable Windows toast notifications",
    )

    # Alert behavior
    alert_cooldown_minutes: int = Field(
        default=0,
        description="Cooldown period between duplicate alerts (0 = no cooldown)",
    )

    # AI enhancement
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key for enhanced storm analysis",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    @field_validator("home_lat")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        """Validate latitude is in valid range."""
        if not -90 <= v <= 90:
            raise ValueError("Latitude must be between -90 and 90 degrees")
        return v

    @field_validator("home_lon")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        """Validate longitude is in valid range."""
        if not -180 <= v <= 180:
            raise ValueError("Longitude must be between -180 and 180 degrees")
        return v

    def validate_coverage(self) -> dict:
        """Validate coordinate coverage for NOAA data sources.

        Returns:
            Coverage validation results
        """
        return validate_coordinate_coverage(self.home_lat, self.home_lon)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()


    @field_validator("county_geojson_path", mode="before")
    @classmethod
    def validate_optional_paths(cls, v: Any) -> Any:
        """Convert empty strings to None for optional path fields."""
        if v == "":
            return None
        return v

    def get_county_geojson_path(self) -> Path:
        """Get the area coverage GeoJSON file path."""
        if self.county_geojson_path:
            return Path(self.county_geojson_path)

        # Default to bundled area data
        package_dir = Path(__file__).parent
        return package_dir / "data" / "default_area.geojson"


    def get_alert_icon_path(self) -> Path:
        """Get the alert icon file path."""
        package_dir = Path(__file__).parent
        return package_dir / "icons" / "alert.ico"


def load_config() -> WeatherbotConfig:
    """Load and validate configuration."""
    return WeatherbotConfig()
