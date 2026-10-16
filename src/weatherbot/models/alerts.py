# src/weatherbot/models/alerts.py
"""NWS alerts and zones, and Nominatim's reverse-geocoding result."""

from typing import Literal, Self

from pydantic import Field, model_validator

from weatherbot.models.base import DomainModel
from weatherbot.models.codes import (
    AlertCategory,
    AlertCertainty,
    AlertMessageType,
    AlertSeverity,
    AlertStatus,
    AlertUrgency,
)
from weatherbot.models.geometry import Geometry, require_geometry
from weatherbot.models.provenance import Provenance
from weatherbot.models.times import UtcDatetime


class AlertQuery(DomainModel):
    """One query that returned an alert: at the location's point, or for one zone."""

    kind: Literal["point", "zone"]
    zone_id: str | None = Field(default=None, pattern=r"^[A-Z]{2}[CZ]\d{3}$")
    provenance: Provenance

    @model_validator(mode="after")
    def _zone_names_its_id(self) -> Self:
        if (self.kind == "zone") != (self.zone_id is not None):
            message = "a zone query names its zone id, and a point query names none"
            raise ValueError(message)
        return self


class NwsAlert(DomainModel):
    """An active NWS alert, merged across the queries that returned it.

    ``found_by``, ``affected_zone_ids``, ``geocode_same``, and ``geocode_ugc`` are the
    inputs issue #10's rule needs: whether a county alert outside the location's own
    forecast zone applies is Phase 3's decision, not this record's. ``found_by`` holds the
    provenance of each response that carried the alert.
    """

    id: str = Field(min_length=1)
    event: str
    headline: str | None
    severity: AlertSeverity
    certainty: AlertCertainty
    urgency: AlertUrgency
    status: AlertStatus
    message_type: AlertMessageType
    category: AlertCategory
    sent: UtcDatetime
    effective: UtcDatetime
    onset: UtcDatetime | None
    expires: UtcDatetime
    ends: UtcDatetime | None
    area_desc: str
    sender_name: str
    references: tuple[str, ...] = Field(description="The ids of the alerts this one updates.")
    vtec: tuple[str, ...] = Field(description="parameters.VTEC.")
    nws_headline: tuple[str, ...] = Field(description="parameters.NWSheadline.")
    description: str | None
    instruction: str | None
    affected_zone_ids: tuple[str, ...] = Field(
        description="The last path segment of each affectedZones URL."
    )
    geocode_same: tuple[str, ...]
    geocode_ugc: tuple[str, ...]
    geometry: Geometry | None
    found_by: tuple[AlertQuery, ...] = Field(min_length=1)


class NwsZone(DomainModel):
    """An NWS zone's metadata and shape (the register's fields for ``nws-zones``)."""

    id: str = Field(pattern=r"^[A-Z]{2}[CZ]\d{3}$")
    type: str = Field(description="public, county, or fire, as the API names it.")
    name: str
    state: str
    cwa: tuple[str, ...]
    time_zone: tuple[str, ...]
    effective_date: UtcDatetime
    geometry: Geometry
    provenance: Provenance

    @model_validator(mode="after")
    def _areal(self) -> Self:
        require_geometry(self.geometry, ("Polygon", "MultiPolygon"), "a zone")
        return self


class GeocodeResult(DomainModel):
    """Nominatim's reverse-geocoding answer (the register's fields), as received.

    Its provenance URL carries the location's coordinates, and stays out of ``repr``.
    """

    display_name: str
    name: str | None
    country_code: str | None = Field(pattern=r"^[A-Za-z]{2}$")
    country: str | None
    licence: str
    osm_type: str
    osm_id: int
    provenance: Provenance
