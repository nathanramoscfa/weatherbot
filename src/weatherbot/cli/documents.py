# src/weatherbot/cli/documents.py
"""The ``--json`` documents: one Pydantic model per command, and its JSON Schema.

Every document carries ``schema_version``, ``command``, ``generated_at``, and the
``disclaimer`` notice; a document read from a snapshot carries its id, times, status, and
source outcomes; ``data`` holds the command's records, built from the domain models
without geometry (Phase 5's API serves geometry). ``locations list --json`` is the only
document that holds a location's coordinates. ``scripts/export_schemas.py`` writes each
model's schema to ``docs/schema/<command>.schema.json`` (JSON Schema 2020-12), and a test
keeps the committed files equal to a fresh export.
"""

from datetime import datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from weatherbot.models import (
    AlertCertainty,
    AlertSeverity,
    AlertUrgency,
    NwsCoverage,
    OutlookRisk,
    SourceId,
    SourceOutcome,
    StormClassification,
    StormSlot,
    WatchWarningType,
)

SCHEMA_VERSION: Final = 1
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_BASE_URL: Final = (
    "https://raw.githubusercontent.com/nathanramoscfa/weatherbot/main/docs/schema"
)


class _Document(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class SnapshotInfo(_Document):
    """The snapshot a document was read from."""

    snapshot_id: UUID
    started_at: datetime
    completed_at: datetime
    status: Literal["complete", "partial", "failed"]
    age_seconds: float = Field(ge=0, description="generated_at minus completed_at.")
    source_outcomes: tuple[SourceOutcome, ...]


class DriftWarningEntry(_Document):
    """A Source-drift warning: an official product disagreed with another or the register."""

    source_id: SourceId
    message: str


class _Envelope(_Document):
    schema_version: Literal[1] = SCHEMA_VERSION
    generated_at: datetime
    disclaimer: str = Field(description="Weatherbot's one-line disclaimer notice.")


# locations ---------------------------------------------------------------------------------


class LocationEntry(_Document):
    """A stored location. Its coordinates appear in this document and in no other."""

    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    country_code: str | None
    display_name: str | None
    nws: NwsCoverage | None = Field(description="null: outside NWS coverage.")
    has_polygon: bool = Field(description="Whether a zone's shape is stored (not shown).")
    evacuation_order_in_effect: bool


class LocationsData(_Document):
    """The stored locations, by name."""

    locations: tuple[LocationEntry, ...]


class LocationsDocument(_Envelope):
    """``weatherbot locations list --json``."""

    command: Literal["locations list"] = "locations list"
    data: LocationsData


# fetch -------------------------------------------------------------------------------------


class FetchCounts(_Document):
    """How many records of each kind the snapshot holds."""

    storms: int = Field(ge=0)
    outlook_areas: int = Field(ge=0)
    wind_probability_products: int = Field(ge=0)
    text_products: int = Field(ge=0)
    gis_feed_items: int = Field(ge=0)
    outlook_graphics: int = Field(ge=0)
    breakpoints: int = Field(ge=0)
    display_layers: int = Field(ge=0)


class FetchData(_Document):
    """What one fetch stored."""

    counts: FetchCounts
    alerts: dict[str, int] = Field(
        description="Alerts per location inside NWS coverage, when both alert sources answered."
    )
    drift_warnings: tuple[DriftWarningEntry, ...]


class FetchDocument(_Envelope):
    """``weatherbot fetch --json``."""

    command: Literal["fetch"] = "fetch"
    snapshot: SnapshotInfo
    data: FetchData


# storms ------------------------------------------------------------------------------------


class ArrivalProductEntry(_Document):
    """An arrival-time product the snapshot holds, and where its times come from."""

    kind: Literal["earliest_reasonable", "most_likely"]
    origin: Literal["kmz", "map_layer"]
    advisory: str
    published_at: datetime | None
    time_zone: str | None
    lines: int = Field(ge=0)
    withheld_reason: str | None


class StormProductsEntry(_Document):
    """Which advisory products the snapshot holds for a storm."""

    cone: bool
    track: bool
    track_points: int = Field(ge=0)
    watch_warning_segments: int = Field(ge=0)
    wind_radii: int = Field(ge=0)
    arrival_times: tuple[ArrivalProductEntry, ...]


class StormEntry(_Document):
    """An active storm from the roster, with the latest advisory and its products."""

    atcf_id: str
    slot: StormSlot
    name: str
    classification: StormClassification
    intensity_kt: int | None
    pressure_mb: int | None
    movement_dir_deg: float | None
    movement_speed_mph: float | None
    advisory: str = Field(description="The public advisory's number, such as 22A.")
    advisory_issued_at: datetime
    last_update: datetime
    products: StormProductsEntry


class OutlookEntry(_Document):
    """An outlook area: a disturbance, a development region, or a motion arrow."""

    basin: str
    kind: Literal[
        "two_day_location", "seven_day_location", "development_region", "development_motion"
    ]
    chance_2day_pct: int | None
    chance_7day_pct: int | None
    risk_2day: OutlookRisk | None
    risk_7day: OutlookRisk | None
    issued_at: datetime


class WindProbabilityEntry(_Document):
    """A wind-speed-probability product: one per threshold and synoptic time."""

    threshold_kt: Literal[34, 50, 64]
    synoptic_at: datetime
    bands: int = Field(ge=0)


class StormsData(_Document):
    """The active storms, the outlook, and the wind-probability products."""

    storms: tuple[StormEntry, ...]
    outlook: tuple[OutlookEntry, ...]
    wind_probabilities: tuple[WindProbabilityEntry, ...]


class StormsDocument(_Envelope):
    """``weatherbot storms --json``."""

    command: Literal["storms"] = "storms"
    snapshot: SnapshotInfo
    data: StormsData


# alerts ------------------------------------------------------------------------------------


class FoundByEntry(_Document):
    """One query that returned an alert."""

    kind: Literal["point", "zone"]
    zone_id: str | None


class AlertEntry(_Document):
    """An active NWS alert, with its times in UTC and in the location's time zone."""

    id: str
    event: str
    severity: AlertSeverity
    urgency: AlertUrgency
    certainty: AlertCertainty
    headline: str | None
    effective: datetime
    expires: datetime
    effective_local: str | None = Field(description="ISO 8601 in the location's time zone.")
    expires_local: str | None = Field(description="ISO 8601 in the location's time zone.")
    found_by: tuple[FoundByEntry, ...]
    affected_zone_ids: tuple[str, ...]


class SegmentEntry(_Document):
    """An active storm's official watch-warning segment, verbatim, not matched to a place."""

    atcf_id: str
    storm_name: str
    tcww: WatchWarningType
    advisory: str


class AlertLocationEntry(_Document):
    """The location the alerts are for, without its coordinates."""

    name: str
    inside_nws_coverage: bool
    time_zone: str | None
    forecast_zone: str | None
    county_zone: str | None


class AlertsData(_Document):
    """A location's alerts, or, outside NWS coverage, the active watch-warning segments."""

    location: AlertLocationEntry
    alerts: tuple[AlertEntry, ...] | None = Field(
        description="null: the snapshot holds no alert list for this location."
    )
    watch_warnings: tuple[SegmentEntry, ...]
    note: str | None


class AlertsDocument(_Envelope):
    """``weatherbot alerts --json``."""

    command: Literal["alerts"] = "alerts"
    snapshot: SnapshotInfo
    data: AlertsData


# doctor ------------------------------------------------------------------------------------

type CheckStatus = Literal["pass", "fail", "skip"]


class DoctorPaths(_Document):
    """Where Weatherbot keeps its state."""

    config_dir: str
    data_dir: str
    settings_file: str
    database_file: str


class DoctorDatabase(_Document):
    """The database's Alembic revision against the head."""

    revision: str | None
    head: str
    at_head: bool
    created: bool
    backup_file: str | None


class DoctorCheck(_Document):
    """One local check."""

    name: str
    status: CheckStatus
    detail: str


class SourceProbeEntry(_Document):
    """One register source's probe, or why it was not probed."""

    source_id: SourceId
    status: CheckStatus
    detail: str


class LayerDiscoveryEntry(_Document):
    """A map service's register layers resolved in this run's catalog."""

    source_id: SourceId
    status: CheckStatus
    expected: int = Field(ge=0)
    resolved: int = Field(ge=0)
    missing: tuple[str, ...]


class DoctorData(_Document):
    """Everything ``doctor`` checked."""

    paths: DoctorPaths
    database: DoctorDatabase | None
    locations: int | None = Field(description="How many are stored; never their coordinates.")
    checks: tuple[DoctorCheck, ...]
    offline: bool
    probes: tuple[SourceProbeEntry, ...]
    layers: tuple[LayerDiscoveryEntry, ...]
    drift_snapshot_id: UUID | None
    drift_warnings: tuple[DriftWarningEntry, ...]
    failed: bool


class DoctorDocument(_Envelope):
    """``weatherbot doctor --json``."""

    command: Literal["doctor"] = "doctor"
    data: DoctorData


DOCUMENTS: Final[dict[str, type[_Envelope]]] = {
    "locations": LocationsDocument,
    "fetch": FetchDocument,
    "storms": StormsDocument,
    "alerts": AlertsDocument,
    "doctor": DoctorDocument,
}
"""Each schema's file stem and its document model."""


def json_schema(name: str) -> dict[str, object]:
    """Return a document's JSON Schema (2020-12), with ``$schema`` and ``$id``.

    Args:
        name: A key of ``DOCUMENTS``.

    Returns:
        The schema.
    """
    schema = DOCUMENTS[name].model_json_schema(mode="serialization")
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": f"{SCHEMA_BASE_URL}/{name}.schema.json",
        **schema,
    }
