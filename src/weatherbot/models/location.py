# src/weatherbot/models/location.py
"""Locations: the places an operator watches, and what the NWS says covers them.

A location's point and polygon are the operator's own coordinates. They stay out of every
``repr``, so a log line, a traceback, or a test failure never prints them. No model here
holds an operator's value by default.
"""

from typing import Self

from pydantic import Field, field_validator, model_validator

from weatherbot.models.base import DomainModel
from weatherbot.models.geometry import Geometry
from weatherbot.models.provenance import Provenance


class LatLon(DomainModel):
    """A latitude and longitude in WGS 84 degrees. Neither appears in ``repr``."""

    latitude: float = Field(ge=-90.0, le=90.0, repr=False)
    longitude: float = Field(ge=-180.0, le=180.0, repr=False)


class NwsCoverage(DomainModel):
    """What the NWS ``/points`` answer says covers a location (the register's fields)."""

    forecast_zone: str = Field(pattern=r"^[A-Z]{2}Z\d{3}$")
    county_zone: str = Field(pattern=r"^[A-Z]{2}C\d{3}$")
    cwa: str = Field(pattern=r"^[A-Z]{3}$", description="The forecast office.")
    time_zone: str = Field(
        pattern=r"^[A-Za-z_]+(?:/[A-Za-z0-9_+-]+)+$", description="An IANA time-zone name."
    )
    city: str = Field(description="relativeLocation's city.")
    state: str = Field(description="relativeLocation's state.")


class Location(DomainModel):
    """A named place to assess: a point, and optionally an NWS zone's shape.

    ``nws`` is ``None`` when ``/points`` answers ``InvalidPoint``: the location is outside
    NWS coverage, and its official watches and warnings come from NHC's breakpoint segments.
    """

    name: str = Field(min_length=1, max_length=64)
    point: LatLon = Field(repr=False)
    polygon: Geometry | None = Field(default=None, repr=False)
    country_code: str | None = Field(
        default=None, pattern=r"^[A-Z]{2}$", description="ISO 3166-1 alpha-2, from geocoding."
    )
    display_name: str | None = None
    nws: NwsCoverage | None = None
    breakpoint_span: None = Field(default=None, description="Phase 3 defines and fills it.")
    evacuation_order_in_effect: bool = Field(
        default=False, description="The operator's toggle (brief §4), read by level 4."
    )
    geocoding: Provenance | None = Field(
        default=None, description="The reverse-geocoding response, when one was made."
    )

    @field_validator("name")
    @classmethod
    def _printable(cls, value: str) -> str:
        if not value.isprintable() or not value.strip():
            message = "a location name is 1-64 printable characters"
            raise ValueError(message)
        return value

    @model_validator(mode="after")
    def _polygon_is_areal(self) -> Self:
        if self.polygon is not None and self.polygon.type not in ("Polygon", "MultiPolygon"):
            message = "a location's polygon must be a Polygon or a MultiPolygon"
            raise ValueError(message)
        return self
