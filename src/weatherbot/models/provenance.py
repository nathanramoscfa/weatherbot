# src/weatherbot/models/provenance.py
"""Provenance: where a record came from, when, and as which bytes."""

from typing import Literal

from pydantic import Field

from weatherbot.models.advisory_number import AdvisoryNumber
from weatherbot.models.base import DomainModel
from weatherbot.models.times import UtcDatetime

# The register's source ids (docs/DATA_SOURCES.md, "Register"); a test keeps them equal.
type SourceId = Literal[
    "nhc-current-storms",
    "nhc-arrival-times",
    "nhc-map-tropical-weather",
    "nhc-map-tropical-summary",
    "nhc-map-breakpoints",
    "nhc-map-peak-surge",
    "nhc-map-surge-risk",
    "nhc-gis-rss",
    "nhc-gis-archive",
    "nhc-text-products",
    "nhc-outlook-graphics",
    "nws-points",
    "nws-alerts-point",
    "nws-alerts-zone",
    "nws-zones",
    "basemap-osm-tiles",
    "overlay-radar",
    "overlay-satellite",
    "geocode-nominatim",
]


class Provenance(DomainModel):
    """The response a record was parsed from. Records parsed from one response share it.

    ``url`` stays out of ``repr``: an NWS ``/points`` or alerts URL and a Nominatim URL
    carry a location's coordinates.
    """

    source_id: SourceId
    url: str = Field(repr=False, pattern=r"^https?://\S+$")
    status: int = Field(ge=100, le=599)
    fetched_at: UtcDatetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Of the bytes as received.")
    issued_at: UtcDatetime | None = Field(
        default=None, description="The product's own issuance, when it states one."
    )
    advisory: AdvisoryNumber | None = None
    etag: str | None = None
    last_modified: str | None = Field(
        default=None, description="The Last-Modified header as received."
    )
    not_modified: bool = Field(
        default=False, description="A 304 answer: the stored body was reused."
    )
