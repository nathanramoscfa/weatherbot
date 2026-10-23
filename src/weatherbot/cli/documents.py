# src/weatherbot/cli/documents.py
"""The ``--json`` documents: one Pydantic model per command, and its JSON Schema.

Every document carries ``schema_version``, ``command``, ``generated_at``, and the
``disclaimer`` notice; a document read from a snapshot carries its id, times, status, and
source outcomes; ``data`` holds the command's records, built from the domain models
without geometry (Phase 5's API serves geometry). ``locations list --json`` is the only
document that holds a location's coordinates. A distance or a bearing from a storm or a
product locates a location too, so ``status`` and ``alerts`` round them for reading (a
tenth of a kilometre, a whole degree); the exact values stay in the local database.
``scripts/export_schemas.py`` writes each model's schema to
``docs/schema/<command>.schema.json`` (JSON Schema 2020-12), and a test keeps the committed
files equal to a fresh export.
"""

from datetime import datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from weatherbot.models import (
    AlertCertainty,
    AlertSeverity,
    AlertUrgency,
    BreakpointSpan,
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
    evacuation_order_set_at: datetime | None = Field(
        description="When the toggle was last turned on or off; null: never."
    )
    breakpoint_span: BreakpointSpan | None = Field(
        description="The coast it sits on, from NHC's catalogue; null until a status run finds one."
    )


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
    covers: bool = Field(
        description="Whether it is in effect for this location (issue #10): returned by the "
        "point query, or naming one of its zones."
    )
    coverage: str = Field(
        description="Why it covers the location or not, such as a county-zone alert outside "
        "this location's zones."
    )
    rule: str | None = Field(description="The ladder rule a covering alert triggers.")


class SegmentEntry(_Document):
    """An active storm's watch-warning segment, and whether it covers the location."""

    atcf_id: str
    storm_name: str
    tcww: WatchWarningType
    advisory: str
    covers: bool
    distance_km: float | None = Field(
        description="A covering segment's nearest point, to a tenth of a kilometre."
    )
    at_end: bool | None = Field(description="Whether that nearest point is the segment's end.")
    breakpoints: tuple[str, ...] = Field(description="Its ends, named from the catalogue.")
    coverage: str | None = Field(description="Why a covering segment covers the location.")


class AlertLocationEntry(_Document):
    """The location the alerts are for, without its coordinates."""

    name: str
    inside_nws_coverage: bool
    time_zone: str | None
    forecast_zone: str | None
    county_zone: str | None


class AlertsData(_Document):
    """A location's alerts and the watch-warning segments, each saying whether it covers it."""

    location: AlertLocationEntry
    alerts: tuple[AlertEntry, ...] | None = Field(
        description="null: the snapshot holds no alert list for this location."
    )
    watch_warnings: tuple[SegmentEntry, ...] = Field(
        description="Inside NWS coverage, the segments that cover the location; outside it, "
        "every active segment, those that cover it first."
    )
    note: str | None


class AlertsDocument(_Envelope):
    """``weatherbot alerts --json``."""

    command: Literal["alerts"] = "alerts"
    snapshot: SnapshotInfo
    data: AlertsData


# status ------------------------------------------------------------------------------------


class EvidenceEntry(_Document):
    """One match of the deciding rule: the product, its issuance, the test, the distance."""

    product: Literal[
        "nws_alert",
        "watch_warning_segment",
        "cone",
        "wind_probability",
        "development_region",
        "evacuation_toggle",
    ]
    source_id: SourceId | None = Field(description="null: the operator's toggle.")
    code: str | None = Field(description="The NWS event, the NHC tcww code, or the band.")
    atcf_id: str | None
    storm_name: str | None
    advisory: str | None
    issued_at: datetime | None = Field(
        description="The product's issuance, or when the toggle was turned on."
    )
    test: Literal[
        "point_query", "zone_list", "segment_distance", "point_in_polygon", "band", "toggle"
    ]
    distance_km: float | None
    at_end: bool | None
    crs: str | None
    closest_approach_at: datetime | None
    lead_h: float | None = Field(description="Hours from the snapshot to the closest approach.")
    detail: str


class OfficialEntry(_Document):
    """An NWS alert or NHC segment that covers the location, or a county alert beside it."""

    kind: Literal["nws_alert", "watch_warning_segment"]
    code: str = Field(description="The NWS event, or the NHC tcww code as received.")
    alert_id: str | None
    issuer: str | None
    atcf_id: str | None
    storm_name: str | None
    advisory: str | None
    issued_at: datetime | None
    expires_at: datetime | None
    zones: tuple[str, ...] = Field(description="The UGC zones an alert names.")
    distance_km: float | None
    breakpoints: tuple[str, ...]
    covers: bool = Field(description="false: a county-zone alert outside this location's zones.")
    rule: str | None = Field(description="The ladder rule it triggers; null: it sets no level.")
    reason: str


class WindReadingEntry(_Document):
    """A wind-speed-probability product read at the location."""

    threshold_kt: Literal[34, 50, 64]
    synoptic_at: datetime
    reading: Literal["band", "below_every_band", "outside_coverage"]
    label: str | None
    lower_pct: int | None
    upper_pct: int | None


class ArrivalEntry(_Document):
    """When tropical-storm-force winds arrive, as one arrival-time product says."""

    kind: Literal["earliest_reasonable", "most_likely"]
    origin: Literal["kmz", "map_layer", "track"]
    reading: Literal["before", "between", "after", "outside", "unresolved", "track"]
    advisory: str | None
    start: datetime | None
    end: datetime | None
    approach_at: datetime | None = Field(description="The track fallback's closest approach.")
    label: str | None
    reason: str | None


class ThreatEntry(_Document):
    """What one storm means for the location, read from its own advisory products."""

    atcf_id: str
    storm_name: str
    advisory: str | None
    issued_at: datetime | None
    category: int | None = Field(description="Saffir-Simpson 1 to 5; null below hurricane.")
    development: str | None
    in_cone: bool | None = Field(description="null: no usable cone.")
    distance_km: float | None = Field(description="From the storm's center.")
    bearing_deg: int | None = Field(description="From the storm's center, to a whole degree.")
    closest_approach_at: datetime | None
    closest_approach_km: float | None
    lead_h: float | None
    hurricane_by_approach: bool | None
    earliest_arrival: ArrivalEntry
    most_likely_arrival: ArrivalEntry


class ChangeEntry(_Document):
    """One change since the previous stored assessment."""

    kind: Literal[
        "level_changed",
        "advisory_issued",
        "official_added",
        "official_changed",
        "official_removed",
        "cone_entered",
        "cone_left",
    ]
    detail: str


class UnavailableEntry(_Document):
    """An input the rules lacked; the level then reads as "at least"."""

    kind: str
    source_id: SourceId | None
    storm_name: str | None
    threshold_kt: Literal[34, 50, 64] | None
    reason: str


class EvacuationOrderEntry(_Document):
    """The operator's evacuation-order toggle: on holds the location at level 4 or above."""

    on: bool
    set_at: datetime | None = Field(description="When it was last turned on or off.")


class StatusLocationEntry(_Document):
    """One location's assessment: its level, why, each storm's threat, and what changed."""

    name: str
    inside_nws_coverage: bool
    time_zone: str | None
    as_of: datetime = Field(description="The snapshot's instant the assessment reads.")
    level: int = Field(ge=1, le=5)
    level_name: str
    actions: str
    rule: str
    rule_trigger: str
    complete: bool = Field(
        description="false: an input was unavailable, and the level reads as at least."
    )
    unavailable: tuple[UnavailableEntry, ...]
    evidence: tuple[EvidenceEntry, ...]
    official: tuple[OfficialEntry, ...] = Field(
        description="The products that cover the location, and the county-zone alerts "
        "outside its zones."
    )
    wind_probabilities: tuple[WindReadingEntry, ...]
    threats: tuple[ThreatEntry, ...]
    changes: tuple[ChangeEntry, ...] = Field(
        description="The changes since the previous stored assessment."
    )
    breakpoint_span: BreakpointSpan | None
    evacuation_order: EvacuationOrderEntry
    ruleset: str
    stored_before: bool = Field(
        description="true: an earlier run stored this snapshot's assessment already."
    )
    toggle_changed: bool = Field(
        description="true: the toggle was set after that stored assessment, which did not "
        "read it; the next fetched snapshot's assessment will."
    )


class StalenessEntry(_Document):
    """One heartbeat, judged when the document was made: stale past twice its cadence."""

    kind: Literal["source", "watch", "runner"]
    name: str = Field(description="A source id, a watch's name, or a monitor process's name.")
    last_success_at: datetime | None = Field(description="null: it never succeeded.")
    expected_every_s: int | None = Field(
        ge=1, description="The cadence its writer expects; null: none is promised, never stale."
    )
    age_s: int | None = Field(ge=0, description="Whole seconds since its last success.")
    stale: bool


class StatusData(_Document):
    """Each location's assessment against the snapshot, or the one named, and the pulse."""

    locations: tuple[StatusLocationEntry, ...]
    staleness: tuple[StalenessEntry, ...] = Field(
        description="Every heartbeat; a stale one is shown in a banner above the locations."
    )


class StatusDocument(_Envelope):
    """``weatherbot status --json``."""

    command: Literal["status"] = "status"
    snapshot: SnapshotInfo
    data: StatusData


# replay ------------------------------------------------------------------------------------


class ReplayStormEntry(_Document):
    """The replayed storm, named as the corpus names it."""

    atcf_id: str
    name: str
    advisories: int = Field(ge=1)
    first_issued_at: datetime
    last_issued_at: datetime


class ReplayLocationEntry(_Document):
    """The stored location the storm is replayed at, without its coordinates."""

    name: str
    inside_nws_coverage: bool
    evacuation_order_stored_on: bool = Field(
        description="The stored toggle; a replay always assesses with it off."
    )


class ReplayStepEntry(_Document):
    """One replayed advisory's assessment and its changes from the advisory before."""

    advisory: str
    issued_at: datetime
    level: int = Field(ge=1, le=5)
    level_name: str
    rule: str
    complete: bool
    official_codes: tuple[str, ...] = Field(
        description="The codes of the covering watches and warnings, sorted."
    )
    changes: tuple[ChangeEntry, ...]


class ReplayData(_Document):
    """A storm's ladder timeline at a location: its transitions, or every advisory."""

    storm: ReplayStormEntry
    location: ReplayLocationEntry
    every: bool = Field(description="false: only the advisories where the level or rule changes.")
    ruleset: str
    steps: tuple[ReplayStepEntry, ...]
    notes: tuple[str, ...] = Field(
        description="What the replay could not read, and that the toggle stayed off."
    )


class ReplayDocument(_Envelope):
    """``weatherbot replay --json``."""

    command: Literal["replay"] = "replay"
    data: ReplayData


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
    heartbeats: tuple[StalenessEntry, ...] = Field(
        description="Every heartbeat, judged by the staleness rule; empty when none is stored."
    )
    failed: bool


class DoctorDocument(_Envelope):
    """``weatherbot doctor --json``."""

    command: Literal["doctor"] = "doctor"
    data: DoctorData


# notifications -----------------------------------------------------------------------------


class NotificationDeliveryEntry(_Document):
    """One delivery attempt of a notification through a channel."""

    id: int = Field(ge=1)
    channel: str
    attempted_at: datetime
    result: Literal["delivered", "failed", "disabled", "unavailable"]
    detail: str | None


class NotificationDecisionEntry(_Document):
    """One trigger's policy decision on an assessment."""

    id: int = Field(ge=1)
    location: str
    assessment_id: int = Field(ge=1)
    change_position: int
    trigger: Literal[
        "level",
        "held",
        "level_changed",
        "advisory_issued",
        "official_added",
        "official_changed",
        "official_removed",
        "cone_entered",
        "cone_left",
    ]
    event_key: str | None
    decision: Literal[
        "escalation",
        "sent",
        "repeat",
        "quiet_hours",
        "held",
        "withdrawn",
        "informational",
    ]
    level_after: int | None = Field(default=None, ge=1, le=5)
    notification_id: int | None = Field(default=None, ge=1)
    decided_at: datetime


class NotificationEntry(_Document):
    """A stored notification, with its deliveries and the decisions that sent it."""

    id: int = Field(ge=1)
    location: str | None
    time_zone: str | None
    assessment_id: int | None = Field(default=None, ge=1)
    cycle_id: int | None = Field(default=None, ge=1)
    kind: Literal["location", "degraded", "recovered", "stale_monitor", "test"]
    level: int | None = Field(default=None, ge=1, le=5)
    escalation: bool
    title: str
    body: tuple[str, ...]
    created_at: datetime
    created_at_local: str | None = Field(
        default=None, description="ISO 8601 in the location's time zone."
    )
    deliveries: tuple[NotificationDeliveryEntry, ...]
    decisions: tuple[NotificationDecisionEntry, ...]


class NotificationsData(_Document):
    """The newest stored notifications first."""

    limit: int = Field(ge=1)
    notifications: tuple[NotificationEntry, ...]


class NotificationsDocument(_Envelope):
    """``weatherbot notify log --json``."""

    command: Literal["notify log"] = "notify log"
    data: NotificationsData


class NotifySetupData(_Document):
    """What ``notify setup`` did with the toast's application identity."""

    action: Literal["register", "remove"]
    outcome: Literal["registered", "unchanged", "removed", "absent", "not_needed"] = Field(
        description="not_needed: not Windows, where toasts need no identity; nothing changed."
    )
    app_id: str
    display_name: str
    registry_key: str | None = Field(
        description="The identity's key under HKEY_CURRENT_USER; null off Windows."
    )


class NotifySetupDocument(_Envelope):
    """``weatherbot notify setup --json``."""

    command: Literal["notify setup"] = "notify setup"
    data: NotifySetupData


class NotifyTestData(_Document):
    """The stored test notification, with each channel's delivery."""

    notification: NotificationEntry
    failed: bool = Field(
        description="true: a channel failed or was disabled, or the toast was unavailable on "
        "Windows with the toast on; the command exits 1."
    )


class NotifyTestDocument(_Envelope):
    """``weatherbot notify test --json``."""

    command: Literal["notify test"] = "notify test"
    data: NotifyTestData


# check -------------------------------------------------------------------------------------


class CycleEntry(_Document):
    """The monitor cycle a command ran."""

    cycle_id: int = Field(ge=1)
    runner: Literal[
        "serve", "check", "check-once", "fallback", "status", "fetch", "storms", "alerts"
    ]
    trigger: Literal[
        "manual", "window", "roster", "alerts", "confirm", "retry", "startup", "resume", "fallback"
    ]
    status: Literal["complete", "partial", "failed", "skipped", "error"]
    started_at: datetime
    completed_at: datetime


class CheckLocationEntry(_Document):
    """One location's level after the cycle, and what changed."""

    name: str
    level: int = Field(ge=1, le=5)
    level_name: str
    rule: str
    complete: bool = Field(
        description="false: an input was unavailable, and the level reads as at least."
    )
    changes: tuple[ChangeEntry, ...]
    stored_before: bool


class CheckData(_Document):
    """One monitor cycle: every location's level, changes, and sent notifications."""

    cycle: CycleEntry
    locations: tuple[CheckLocationEntry, ...]
    notifications: tuple[NotificationEntry, ...] = ()
    confirm_at: datetime | None = None
    drift_warnings: tuple[DriftWarningEntry, ...]


class CheckDocument(_Envelope):
    """``weatherbot check --once --json``."""

    command: Literal["check"] = "check"
    snapshot: SnapshotInfo
    data: CheckData


# config ------------------------------------------------------------------------------------


class SettingEntry(_Document):
    """One setting's effective value and where it came from."""

    table: str
    key: str
    value: str | int | float | bool
    origin: Literal["default", "file", "environment"]
    variable: str = Field(description="The environment variable that overrides it.")


class ConfigData(_Document):
    """Every setting, table by table."""

    settings_file: str
    settings_file_exists: bool
    settings: tuple[SettingEntry, ...]


class ConfigDocument(_Envelope):
    """``weatherbot config show --json``."""

    command: Literal["config show"] = "config show"
    data: ConfigData


class ConfigPathData(_Document):
    """Where Weatherbot keeps its files."""

    config_dir: str
    settings_file: str
    data_dir: str
    database_file: str
    backup_dir: str
    cycle_lock_file: str
    migrate_lock_file: str


class ConfigPathDocument(_Envelope):
    """``weatherbot config path --json``."""

    command: Literal["config path"] = "config path"
    data: ConfigPathData


DOCUMENTS: Final[dict[str, type[_Envelope]]] = {
    "locations": LocationsDocument,
    "fetch": FetchDocument,
    "storms": StormsDocument,
    "alerts": AlertsDocument,
    "doctor": DoctorDocument,
    "status": StatusDocument,
    "replay": ReplayDocument,
    "check": CheckDocument,
    "config": ConfigDocument,
    "config-path": ConfigPathDocument,
    "notifications": NotificationsDocument,
    "notify-setup": NotifySetupDocument,
    "notify-test": NotifyTestDocument,
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
