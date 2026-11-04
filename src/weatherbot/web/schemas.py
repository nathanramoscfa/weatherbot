# src/weatherbot/web/schemas.py
"""Typed Pydantic response models for the local web API.

Every response model is frozen and forbids unknown fields. No model carries coordinates
except ``LocationsResponse`` and ``MapResponse`` (and ``/api/replay/{atcf_id}/{advisory}``),
and validation error responses strip ``input`` so rejected payloads are never echoed back.
No AI model carries a key, a prompt, a context, or a question; the ledger's rows carry no
text at all, and a source's ``url`` is only ever a public NOAA page that names no point.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
from weatherbot.services.ai.chat import QUESTION_LIMIT
from weatherbot.services.ai.errors import AiUnavailableReason
from weatherbot.services.ai.ledger import CallKind
from weatherbot.services.ai.narration import Horizon
from weatherbot.services.ai.schemas import SectionName
from weatherbot.services.ai.service import AiStateName, CredentialSource
from weatherbot.services.ai.tools import Basin, ToolName
from weatherbot.services.events import EventKind, QueryKey

type GeometryKind = Literal[
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
]


class _ApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# Health ------------------------------------------------------------------------------------


class DatabaseHealth(_ApiModel):
    """Database revision status reported by ``GET /api/health``."""

    revision: str | None = Field(description="Current Alembic revision of the database, or null.")
    head: str = Field(description="Expected Alembic head revision.")
    current: bool = Field(description="Whether the database revision matches the head revision.")


class SchedulerHealth(_ApiModel):
    """The ``serve`` runner heartbeat summary reported by ``GET /api/health``."""

    last_success_at: datetime | None = Field(
        description="UTC instant of the runner's last successful heartbeat, or null."
    )
    expected_every_s: int | None = Field(
        description="Expected heartbeat cadence in seconds, or null when unscheduled."
    )
    stale: bool = Field(description="Whether the runner heartbeat is past twice its cadence.")


class HeartbeatHealth(_ApiModel):
    """One source, watch, or runner heartbeat row reported by ``GET /api/health``."""

    kind: str = Field(description="Heartbeat category: source, watch, or runner.")
    name: str = Field(description="Source identifier, watch name, or runner process name.")
    last_success_at: datetime | None = Field(
        description="UTC instant of the last successful attempt, or null."
    )
    age_s: float | None = Field(
        description="Seconds elapsed since the last success, or null if never succeeded."
    )
    consecutive_failures: int = Field(
        ge=0, description="Number of consecutive failed attempts since the last success."
    )
    expected_every_s: int | None = Field(
        description="Expected cadence in seconds, or null when no cadence is promised."
    )
    stale: bool = Field(description="Whether the heartbeat is stale under the twice-cadence rule.")


class UiHealth(_ApiModel):
    """Whether the built frontend bundle is present on disk at startup."""

    present: bool = Field(description="Whether web/dist/index.html is loaded and ready to serve.")
    index_sha256: str | None = Field(
        description="SHA-256 digest of the built index.html template, or null when absent."
    )


class AiHealth(_ApiModel):
    """The AI's state and today's spend: never a credential, a prompt, or an answer."""

    state: AiStateName = Field(
        description="off, ready, paused, capped, or unavailable; computed without a request."
    )
    reason: AiUnavailableReason | None = Field(
        description="Why AI is not ready (for example no_credential or capped); null when ready."
    )
    spent_micro_usd: int = Field(
        description="Today's settled AI cost and open reservations, in micro-dollars."
    )
    cap_micro_usd: int = Field(
        description="Today's limit: the daily cap plus any allowances, in micro-dollars."
    )


class HealthResponse(_ApiModel):
    """Response document for ``GET /api/health``."""

    version: str = Field(description="Installed Weatherbot package version.")
    started_at: datetime = Field(description="UTC instant when the web server started.")
    now: datetime = Field(description="Current UTC instant on the server clock.")
    database: DatabaseHealth = Field(description="SQLite database migration status.")
    scheduler: SchedulerHealth = Field(description="Scheduled runner heartbeat status.")
    heartbeats: list[HeartbeatHealth] = Field(
        description="All recorded source, watch, and runner heartbeats."
    )
    stale: bool = Field(description="Whether any heartbeat is currently stale.")
    next_product_at: datetime = Field(
        description="Next scheduled NHC synoptic advisory release instant in UTC."
    )
    ui: UiHealth = Field(description="Built frontend bundle availability.")
    corpus: bool = Field(
        description=(
            "Whether a replay corpus is configured and available for historical map replay."
        )
    )
    ai: AiHealth = Field(description="The AI's state and today's spend against its cap.")
    notice: str = Field(description="One-line informational-only disclaimer notice.")


# GeoJSON -----------------------------------------------------------------------------------


class GeoJsonCrsResponse(_ApiModel):
    """Explicit geographic coordinate reference system metadata without WKT."""

    name: Literal["EPSG:4326", "native"] = Field(
        description="Geographic coordinate reference system identifier, such as EPSG:4326."
    )
    datum: str | None = Field(
        default=None,
        description="Geodetic datum or sphere identifier carried by a native source product.",
    )


class GeoJsonGeometryResponse(_ApiModel):
    """A GeoJSON geometry object with explicit CRS metadata."""

    type: GeometryKind = Field(description="GeoJSON geometry type.")
    coordinates: object = Field(
        description="GeoJSON coordinate array in the geometry's native CRS."
    )
    crs: GeoJsonCrsResponse = Field(description="Coordinate reference system of the coordinates.")


class GeoJsonFeatureResponse(_ApiModel):
    """A GeoJSON Feature with typed properties and explicit CRS metadata."""

    type: Literal["Feature"] = Field(
        default="Feature", description="GeoJSON Feature discriminator."
    )
    geometry: GeoJsonGeometryResponse = Field(description="Feature geometry with CRS metadata.")
    properties: dict[str, object] = Field(description="Feature attributes for map display.")
    crs: GeoJsonCrsResponse = Field(description="Coordinate reference system of this feature.")


class GeoJsonFeatureCollectionResponse(_ApiModel):
    """A GeoJSON FeatureCollection with explicit CRS metadata."""

    type: Literal["FeatureCollection"] = Field(
        default="FeatureCollection", description="GeoJSON FeatureCollection discriminator."
    )
    features: tuple[GeoJsonFeatureResponse, ...] = Field(
        description="Features belonging to this map layer."
    )
    crs: GeoJsonCrsResponse = Field(
        description="Coordinate reference system of the feature collection."
    )


# Shared snapshot metadata ------------------------------------------------------------------


class DriftWarningResponse(_ApiModel):
    """A source-drift warning logged while fetching a snapshot."""

    source_id: SourceId = Field(description="Official source that logged the drift warning.")
    message: str = Field(description="Redacted description of the schema or metadata drift.")


class SnapshotSummaryResponse(_ApiModel):
    """Metadata and source outcomes for the snapshot backing a read response."""

    snapshot_id: UUID = Field(description="Unique identifier of the snapshot.")
    started_at: datetime = Field(description="UTC instant when the snapshot fetch started.")
    completed_at: datetime = Field(description="UTC instant when the snapshot fetch completed.")
    status: Literal["complete", "partial", "failed"] = Field(
        description="Overall snapshot completeness across official sources."
    )
    age_seconds: float = Field(
        ge=0,
        description="Seconds elapsed between snapshot completion and response generation.",
    )
    source_outcomes: tuple[SourceOutcome, ...] = Field(
        description="Per-source fetch outcome recorded for the snapshot."
    )
    drift_warnings: tuple[DriftWarningResponse, ...] = Field(
        default=(), description="Source-drift warnings recorded with the snapshot."
    )


# Locations (GET /api/locations) ------------------------------------------------------------


class LocationPreferencesResponse(_ApiModel):
    """Per-location notification preferences returned by ``GET /api/locations``."""

    toast: bool = Field(
        default=True,
        description="Whether Windows desktop toasts are enabled for this location.",
    )
    browser: bool = Field(
        default=True,
        description="Whether browser alert banners are enabled for this location.",
    )
    phone: bool = Field(
        default=True,
        description="Whether phone push notifications (ntfy) are enabled for this location.",
    )
    phone_min_level: int = Field(
        default=2,
        ge=2,
        le=5,
        description="Minimum threat level (2..5) that triggers a phone push notification.",
    )


class LocationResponse(_ApiModel):
    """A watched location with its coordinates, NWS coverage, toggle state, and zone polygon."""

    name: str = Field(description="Unique operator-chosen name of the location.")
    latitude: float = Field(ge=-90, le=90, description="Latitude in degrees north.")
    longitude: float = Field(ge=-180, le=180, description="Longitude in degrees east.")
    country_code: str | None = Field(
        description="ISO 3166-1 alpha-2 country code from reverse geocoding, or null."
    )
    display_name: str | None = Field(
        description="Reverse-geocoded place label from Nominatim, or null."
    )
    nws: NwsCoverage | None = Field(
        description=(
            "NWS office, forecast/county zones, and time zone, or null outside NWS coverage."
        )
    )
    has_polygon: bool = Field(
        description="Whether a county or forecast zone polygon is stored for this location."
    )
    polygon: GeoJsonGeometryResponse | None = Field(
        default=None,
        description="Stored county or forecast zone polygon geometry with CRS metadata, or null.",
    )
    evacuation_order_in_effect: bool = Field(
        description="Whether the operator's evacuation-order toggle is currently on."
    )
    evacuation_order_set_at: datetime | None = Field(
        description="UTC instant when the evacuation-order toggle was last changed, or null."
    )
    breakpoint_span: BreakpointSpan | None = Field(
        description="Nearest NHC coastal breakpoint span, or null before the first assessment."
    )
    preferences: LocationPreferencesResponse = Field(
        default=LocationPreferencesResponse(),
        description="Per-location notification channel preferences.",
    )


class LocationsResponse(_ApiModel):
    """Response document for ``GET /api/locations``."""

    locations: tuple[LocationResponse, ...] = Field(
        description="Stored watched locations ordered by name."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


# Assessments (GET /api/assessments) --------------------------------------------------------


class ThreatLevelResponse(_ApiModel):
    """Five-level hurricane threat ladder reading."""

    number: int = Field(
        ge=1,
        le=5,
        description="Alert ladder level from 1 (All Clear) to 5 (Extreme Threat).",
    )
    label: str = Field(description="Short human-readable name for the threat level.")
    actions: str = Field(description="Recommended preparedness actions for this threat level.")


class EvacuationOrderResponse(_ApiModel):
    """State of the operator's manual evacuation-order toggle for a location."""

    on: bool = Field(
        description="Whether the toggle is on (holding the location at Level 4 or above)."
    )
    set_at: datetime | None = Field(
        description="UTC instant when the toggle was last changed, or null."
    )


class AssessmentEvidenceResponse(_ApiModel):
    """One piece of product evidence that matched the deciding ladder rule."""

    product: Literal[
        "nws_alert",
        "watch_warning_segment",
        "cone",
        "wind_probability",
        "development_region",
        "evacuation_toggle",
    ] = Field(description="Kind of official product or toggle that matched the rule.")
    source_id: SourceId | None = Field(
        description="Register source identifier, or null for the operator's evacuation toggle."
    )
    code: str | None = Field(
        description="NWS event name, NHC watch/warning code, or probability band label."
    )
    atcf_id: str | None = Field(
        description="Storm ATCF identifier when the evidence is for a storm."
    )
    storm_name: str | None = Field(description="Storm name when the evidence is for a storm.")
    advisory: str | None = Field(
        description="Advisory number when the evidence is from an advisory."
    )
    issued_at: datetime | None = Field(
        description="UTC issuance instant of the product or toggle change."
    )
    test: Literal[
        "point_query",
        "zone_list",
        "segment_distance",
        "point_in_polygon",
        "band",
        "toggle",
    ] = Field(description="Geometric or zone test that matched the evidence.")
    distance_km: float | None = Field(
        description="Geodesic distance in kilometres rounded to 0.1 km, when applicable."
    )
    at_end: bool | None = Field(
        description="Whether the nearest point on a coastal segment was one of its ends."
    )
    crs: str | None = Field(description="CRS identifier used for the geometric test, or null.")
    closest_approach_at: datetime | None = Field(
        description="UTC instant of closest forecast track approach, when applicable."
    )
    lead_h: float | None = Field(
        description="Hours from the snapshot to closest approach, rounded to 0.1 h."
    )
    detail: str = Field(description="Plain-language explanation of the evidence match.")


class AssessmentOfficialProductResponse(_ApiModel):
    """An official NWS alert or NHC watch-warning segment evaluated at a location."""

    kind: Literal["nws_alert", "watch_warning_segment"] = Field(
        description="Official product kind."
    )
    code: str = Field(description="NWS event name or NHC watch-warning code.")
    alert_id: str | None = Field(description="NWS alert identifier, or null for an NHC segment.")
    issuer: str | None = Field(description="Issuing NWS office name, or null.")
    atcf_id: str | None = Field(description="Storm ATCF identifier for an NHC segment, or null.")
    storm_name: str | None = Field(description="Storm name for an NHC segment, or null.")
    advisory: str | None = Field(description="Advisory number for an NHC segment, or null.")
    issued_at: datetime | None = Field(description="UTC issuance or effective instant.")
    expires_at: datetime | None = Field(description="UTC expiration instant for an NWS alert.")
    zones: tuple[str, ...] = Field(description="UGC zone identifiers named by an NWS alert.")
    distance_km: float | None = Field(
        description="Distance in kilometres to a covering NHC segment, rounded to 0.1 km."
    )
    breakpoints: tuple[str, ...] = Field(
        description="Coastal breakpoint names at the ends of a covering NHC segment."
    )
    covers: bool = Field(
        description=(
            "Whether this official product covers the location and can set its threat level."
        )
    )
    is_county_context: bool = Field(
        description=(
            "True when the product is a county-zone NWS alert outside the location's zones "
            "(issue #10)."
        )
    )
    rule: str | None = Field(
        description=(
            "Ladder rule code triggered by a covering product, or null when it sets no level."
        )
    )
    reason: str = Field(description="Why the product covers or does not cover the location.")


class WindReadingResponse(_ApiModel):
    """Wind-speed-probability reading at a location for one wind threshold."""

    threshold_kt: Literal[34, 50, 64] = Field(description="Wind speed threshold in knots.")
    synoptic_at: datetime = Field(description="UTC synoptic time of the wind-probability product.")
    reading: Literal["band", "below_every_band", "outside_coverage"] = Field(
        description="Whether the location falls in a band, below all bands, or outside coverage."
    )
    label: str | None = Field(description="Percentage band label such as '20-30%', or null.")
    lower_pct: int | None = Field(description="Lower bound of the percentage band, or null.")
    upper_pct: int | None = Field(description="Upper bound of the percentage band, or null.")


class ArrivalReadingResponse(_ApiModel):
    """Tropical-storm-force wind arrival-time reading at a location."""

    kind: Literal["earliest_reasonable", "most_likely"] = Field(description="Arrival-time variant.")
    origin: Literal["kmz", "map_layer", "track"] = Field(
        description="Product source used to derive the arrival reading."
    )
    reading: Literal["before", "between", "after", "outside", "unresolved", "track"] = Field(
        description="How the location sits relative to the arrival-time contours."
    )
    advisory: str | None = Field(
        description="Advisory number of the arrival-time product, or null."
    )
    start: datetime | None = Field(description="UTC start of the arrival window, when applicable.")
    end: datetime | None = Field(description="UTC end of the arrival window, when applicable.")
    approach_at: datetime | None = Field(
        description="UTC closest-approach fallback instant when derived from the forecast track."
    )
    label: str | None = Field(description="Contour label from the product, or null.")
    reason: str | None = Field(
        description="Explanation when the arrival reading is unresolved, or null."
    )


class StormThreatResponse(_ApiModel):
    """Per-storm threat summary for a watched location."""

    atcf_id: str = Field(description="Storm ATCF identifier.")
    storm_name: str = Field(description="Storm name.")
    advisory: str | None = Field(description="Advisory number of the storm products, or null.")
    issued_at: datetime | None = Field(description="UTC issuance instant of the advisory, or null.")
    category: int | None = Field(
        description=(
            "Saffir-Simpson category 1..5 at peak or current intensity, or null below hurricane."
        )
    )
    development: str | None = Field(description="Storm development classification, or null.")
    in_cone: bool | None = Field(
        description=(
            "Whether the location is inside the forecast cone, or null when no cone is usable."
        )
    )
    distance_km: float | None = Field(
        description="Distance in kilometres from the storm's initial center, rounded to 0.1 km."
    )
    bearing_deg: int | None = Field(
        description="Initial geodesic bearing in whole degrees (0..359) from the storm's center."
    )
    closest_approach_at: datetime | None = Field(
        description="UTC instant of closest forecast track approach, or null."
    )
    closest_approach_km: float | None = Field(
        description="Closest approach distance in kilometres, rounded to 0.1 km, or null."
    )
    lead_h: float | None = Field(
        description="Hours from the snapshot to closest approach, rounded to 0.1 h, or null."
    )
    hurricane_by_approach: bool | None = Field(
        description=(
            "Whether forecast points at or before closest approach reach hurricane strength."
        )
    )
    earliest_arrival: ArrivalReadingResponse = Field(
        description="Earliest-reasonable arrival reading of 34-kt winds."
    )
    most_likely_arrival: ArrivalReadingResponse = Field(
        description="Most-likely arrival reading of 34-kt winds."
    )


class AssessmentChangeResponse(_ApiModel):
    """One typed change event between a location's previous and current stored assessments."""

    kind: Literal[
        "level_changed",
        "advisory_issued",
        "official_added",
        "official_changed",
        "official_removed",
        "cone_entered",
        "cone_left",
    ] = Field(description="Change event category.")
    detail: str = Field(description="Plain-language description of what changed.")


class AssessmentUnavailableResponse(_ApiModel):
    """An input the engine lacked when assessing a snapshot, making the level a floor."""

    kind: str = Field(description="Category of unavailable input.")
    source_id: SourceId | None = Field(description="Official source that was unavailable, or null.")
    storm_name: str | None = Field(
        description="Storm name when a storm product was missing, or null."
    )
    threshold_kt: Literal[34, 50, 64] | None = Field(
        description="Wind threshold in knots when a wind-probability product was missing, or null."
    )
    reason: str = Field(description="Human-readable explanation of the missing input.")


class StalenessItemResponse(_ApiModel):
    """Staleness evaluation of one recorded heartbeat."""

    kind: Literal["source", "watch", "runner"] = Field(description="Heartbeat category.")
    name: str = Field(description="Source identifier, watch name, or runner name.")
    last_success_at: datetime | None = Field(
        description="UTC instant of last success, or null if never succeeded."
    )
    expected_every_s: int | None = Field(
        ge=1,
        description="Expected cadence in seconds, or null when no cadence is promised.",
    )
    age_s: int | None = Field(
        ge=0, description="Whole seconds elapsed since last success, or null."
    )
    stale: bool = Field(description="Whether the heartbeat exceeds twice its expected cadence.")


class StoredAssessmentResponse(_ApiModel):
    """The latest stored assessment for one watched location."""

    id: int = Field(ge=1, description="Database primary key of the stored assessment.")
    stored_at: datetime = Field(description="UTC instant when the assessment was stored.")
    snapshot_id: UUID = Field(description="Identifier of the snapshot that was assessed.")
    as_of: datetime = Field(description="UTC completion instant of the assessed snapshot.")
    level: ThreatLevelResponse = Field(
        description="Decided threat level, label, and recommended actions."
    )
    rule: str = Field(description="Identifier of the first ladder rule that matched.")
    rule_trigger: str = Field(description="Human-readable summary of what triggers that rule.")
    complete: bool = Field(
        description=("False when one or more inputs were unavailable, making the level a floor.")
    )
    unavailable: tuple[AssessmentUnavailableResponse, ...] = Field(
        description="Inputs that were unavailable when the assessment was computed."
    )
    evidence: tuple[AssessmentEvidenceResponse, ...] = Field(
        description="Evidence items supporting the deciding rule."
    )
    official: tuple[AssessmentOfficialProductResponse, ...] = Field(
        description="Covering official products and county-zone context alerts (issue #10)."
    )
    wind_probabilities: tuple[WindReadingResponse, ...] = Field(
        description="34, 50, and 64 kt wind-speed-probability readings at the location."
    )
    threats: tuple[StormThreatResponse, ...] = Field(
        description="Per-storm threat readings for each active storm in the snapshot."
    )
    changes: tuple[AssessmentChangeResponse, ...] = Field(
        description="Change events compared with the location's previous stored assessment."
    )
    breakpoint_span: BreakpointSpan | None = Field(
        description="Nearest coastal breakpoint span from the assessed snapshot, or null."
    )
    evacuation_order: EvacuationOrderResponse = Field(
        description="Current evacuation-order toggle state for the location."
    )
    ruleset: str = Field(description="Fingerprint of the ladder ruleset and thresholds.")
    toggle_changed: bool = Field(
        description=(
            "True when the evacuation-order toggle was flipped after this assessment was stored."
        )
    )
    toggle_note: str | None = Field(
        default=None,
        description=(
            "Note explaining that the toggle changed after this assessment was stored, or null."
        ),
    )


class LocationAssessmentResponse(_ApiModel):
    """A watched location paired with its latest stored assessment."""

    name: str = Field(description="Location name.")
    inside_nws_coverage: bool = Field(description="Whether the location is inside NWS coverage.")
    time_zone: str | None = Field(description="IANA time zone of the location, or null.")
    evacuation_order: EvacuationOrderResponse = Field(
        description="Current evacuation-order toggle state."
    )
    breakpoint_span: BreakpointSpan | None = Field(
        description="Nearest coastal breakpoint span stored for the location, or null."
    )
    assessment: StoredAssessmentResponse | None = Field(
        description=(
            "Latest stored assessment for this location, or null before the first assessment."
        )
    )


class AssessmentsResponse(_ApiModel):
    """Response document for ``GET /api/assessments``."""

    snapshot: SnapshotSummaryResponse | None = Field(
        description="Latest stored snapshot summary, or null when no snapshot is stored."
    )
    locations: tuple[LocationAssessmentResponse, ...] = Field(
        description="Each stored location and its latest stored assessment."
    )
    staleness: tuple[StalenessItemResponse, ...] = Field(
        description="All recorded heartbeats evaluated against the staleness rule."
    )
    stale_banner: tuple[str, ...] = Field(
        description="Human-readable staleness warning lines for the dashboard banner."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


# Storms (GET /api/storms) ------------------------------------------------------------------


class ArrivalProductSummaryResponse(_ApiModel):
    """Metadata for one arrival-time product carried by a storm in the snapshot."""

    kind: Literal["earliest_reasonable", "most_likely"] = Field(
        description="Arrival-time product variant."
    )
    origin: Literal["kmz", "map_layer"] = Field(description="Source feed of the arrival product.")
    advisory: str = Field(description="Advisory number of the arrival product.")
    published_at: datetime | None = Field(
        description="UTC publication instant stated by the product, or null."
    )
    time_zone: str | None = Field(description="Time zone code stated by the product, or null.")
    lines: int = Field(ge=0, description="Number of arrival-time contour lines in the product.")
    withheld_reason: str | None = Field(
        description="Reason the product's labels were withheld from parsing, or null."
    )


class StormProductsSummaryResponse(_ApiModel):
    """Counts and flags of advisory products carried for an active storm."""

    cone: bool = Field(description="Whether the snapshot holds a forecast cone for the storm.")
    track: bool = Field(description="Whether the snapshot holds a forecast track line.")
    track_points: int = Field(ge=0, description="Number of forecast track points carried.")
    watch_warning_segments: int = Field(
        ge=0, description="Number of coastal watch-warning segments carried."
    )
    wind_radii: int = Field(ge=0, description="Number of forecast wind-radii polygons carried.")
    arrival_times: tuple[ArrivalProductSummaryResponse, ...] = Field(
        description="Arrival-time products carried for the storm."
    )


class StormSummaryResponse(_ApiModel):
    """Summary of one active tropical cyclone in the latest snapshot (without geometry)."""

    atcf_id: str = Field(description="ATCF cyclone identifier, such as AL112017.")
    slot: StormSlot = Field(
        description="NHC map-service wallet slot (AT1..AT5, EP1..EP5, CP1..CP5)."
    )
    name: str = Field(description="Official cyclone name or number.")
    classification: StormClassification = Field(
        description="Tropical cyclone classification code and label."
    )
    intensity_kt: int | None = Field(description="Maximum sustained wind speed in knots, or null.")
    pressure_mb: int | None = Field(description="Minimum central pressure in millibars, or null.")
    movement_dir_deg: float | None = Field(
        description="Present movement direction in degrees, or null."
    )
    movement_speed_mph: float | None = Field(
        description="Present movement speed in miles per hour, or null."
    )
    advisory: str = Field(description="Public advisory number, such as 22 or 22A.")
    advisory_issued_at: datetime = Field(description="UTC issuance instant of the public advisory.")
    last_update: datetime = Field(description="UTC last-update instant reported by the NHC roster.")
    products: StormProductsSummaryResponse = Field(
        description="Summary of advisory products carried for this storm."
    )


class OutlookAreaSummaryResponse(_ApiModel):
    """Summary of one Tropical Weather Outlook area in the latest snapshot (without geometry)."""

    basin: str = Field(description="Ocean basin name.")
    kind: Literal[
        "two_day_location",
        "seven_day_location",
        "development_region",
        "development_motion",
    ] = Field(description="Outlook feature kind.")
    chance_2day_pct: int | None = Field(
        description="48-hour formation probability in percent, or null."
    )
    chance_7day_pct: int | None = Field(
        description="7-day formation probability in percent, or null."
    )
    risk_2day: OutlookRisk | None = Field(description="48-hour formation risk category, or null.")
    risk_7day: OutlookRisk | None = Field(description="7-day formation risk category, or null.")
    issued_at: datetime = Field(description="UTC issuance instant of the outlook.")


class WindProbabilitySummaryResponse(_ApiModel):
    """Summary of one wind-speed-probability product in the latest snapshot."""

    threshold_kt: Literal[34, 50, 64] = Field(description="Wind speed threshold in knots.")
    synoptic_at: datetime = Field(description="UTC synoptic time of the probability product.")
    bands: int = Field(ge=0, description="Number of probability contour bands in the product.")


class StormsResponse(_ApiModel):
    """Response document for ``GET /api/storms``."""

    snapshot: SnapshotSummaryResponse | None = Field(
        description="Latest stored snapshot summary, or null when no snapshot is stored."
    )
    storms: tuple[StormSummaryResponse, ...] = Field(
        description="Active tropical cyclones from the latest snapshot."
    )
    outlook: tuple[OutlookAreaSummaryResponse, ...] = Field(
        description="Tropical Weather Outlook areas from the latest snapshot."
    )
    wind_probabilities: tuple[WindProbabilitySummaryResponse, ...] = Field(
        description="Wind-speed-probability product summaries from the latest snapshot."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


# Alerts (GET /api/alerts) ------------------------------------------------------------------


class AlertFoundByResponse(_ApiModel):
    """One NWS alert query (coordinate lookup or zone lookup) that returned an alert."""

    kind: Literal["point", "zone"] = Field(description="Whether found by coordinate or zone query.")
    zone_id: str | None = Field(description="UGC zone identifier for a zone query, or null.")


class LocationAlertResponse(_ApiModel):
    """An active NWS alert associated with a watched location."""

    id: str = Field(description="Official NWS alert identifier.")
    event: str = Field(description="NWS alert event name, such as Hurricane Warning.")
    severity: AlertSeverity = Field(description="CAP severity classification.")
    urgency: AlertUrgency = Field(description="CAP urgency classification.")
    certainty: AlertCertainty = Field(description="CAP certainty classification.")
    headline: str | None = Field(description="NWS alert headline, or null.")
    effective: datetime = Field(description="UTC effective instant of the alert.")
    expires: datetime = Field(description="UTC expiration instant of the alert.")
    effective_local: str | None = Field(
        description="ISO 8601 effective time in the location's local time zone, or null."
    )
    expires_local: str | None = Field(
        description="ISO 8601 expiration time in the location's local time zone, or null."
    )
    sender_name: str | None = Field(description="Issuing NWS office name, or null.")
    vtec: tuple[str, ...] = Field(description="Valid Time Event Code strings carried by the alert.")
    found_by: tuple[AlertFoundByResponse, ...] = Field(
        description="Queries that returned this alert during the snapshot fetch."
    )
    affected_zone_ids: tuple[str, ...] = Field(
        description="UGC zone identifiers listed in the alert's affectedZones."
    )
    covers: bool = Field(
        description=(
            "Whether the alert covers the location (returned by coordinate query or naming "
            "its zones)."
        )
    )
    is_county_context: bool = Field(
        description=(
            "True when the alert came only from the county zone and names other zones (issue #10)."
        )
    )
    coverage: str = Field(
        description=(
            "Plain-language explanation of why the alert covers or does not cover the location."
        )
    )
    rule: str | None = Field(
        description=("Ladder rule code triggered when the alert covers the location, or null.")
    )


class WatchWarningSegmentResponse(_ApiModel):
    """An NHC coastal watch-warning segment evaluated for a watched location."""

    atcf_id: str = Field(description="Storm ATCF identifier.")
    storm_name: str = Field(description="Storm name.")
    tcww: WatchWarningType = Field(description="NHC tropical cyclone watch/warning type.")
    advisory: str = Field(description="Advisory number of the segment.")
    issued_at: datetime | None = Field(
        default=None, description="UTC issuance instant of the advisory, or null."
    )
    covers: bool = Field(description="Whether the segment covers the location within thresholds.")
    distance_km: float | None = Field(
        description=(
            "Nearest geodesic distance in kilometres for a covering segment, rounded to 0.1 km."
        )
    )
    at_end: bool | None = Field(
        description="Whether the nearest point on a covering segment is at its end."
    )
    breakpoints: tuple[str, ...] = Field(
        description="Coastal breakpoint names at the ends of a covering segment."
    )
    coverage: str | None = Field(
        description="Explanation of why a covering segment covers the location, or null."
    )
    rule: str | None = Field(
        default=None,
        description="Ladder rule code triggered by a covering segment, or null.",
    )


class AlertLocationMetadataResponse(_ApiModel):
    """Metadata of the watched location for an alert group (without coordinates)."""

    name: str = Field(description="Location name.")
    inside_nws_coverage: bool = Field(description="Whether the location is inside NWS coverage.")
    time_zone: str | None = Field(description="IANA time zone of the location, or null.")
    forecast_zone: str | None = Field(description="NWS forecast zone identifier, or null.")
    county_zone: str | None = Field(description="NWS county zone identifier, or null.")


class LocationAlertsGroupResponse(_ApiModel):
    """Active NWS alerts and NHC watch-warning segments for one watched location."""

    location: AlertLocationMetadataResponse = Field(
        description="Watched location metadata without coordinates."
    )
    alerts: tuple[LocationAlertResponse, ...] | None = Field(
        description=(
            "Active NWS alerts for the location, or null when outside NWS coverage or unavailable."
        )
    )
    watch_warnings: tuple[WatchWarningSegmentResponse, ...] = Field(
        description=(
            "NHC coastal watch-warning segments (covering segments inside NWS coverage; "
            "all segments outside)."
        )
    )
    note: str | None = Field(
        description=(
            "Explanatory note when outside NWS coverage or when alert sources failed, or null."
        )
    )


class AlertsResponse(_ApiModel):
    """Response document for ``GET /api/alerts``."""

    snapshot: SnapshotSummaryResponse | None = Field(
        description="Latest stored snapshot summary, or null when no snapshot is stored."
    )
    locations: tuple[LocationAlertsGroupResponse, ...] = Field(
        description="Per-location NWS alerts and NHC watch-warning segments."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


# Notifications (GET /api/notifications) ----------------------------------------------------


class NotificationDeliveryResponse(_ApiModel):
    """One channel delivery outcome for a stored notification."""

    id: int = Field(ge=1, description="Database primary key of the delivery record.")
    channel: str = Field(description="Delivery channel name, such as log, toast, or browser.")
    attempted_at: datetime = Field(description="UTC instant of the delivery attempt.")
    result: Literal["delivered", "failed", "disabled", "unavailable", "muted"] = Field(
        description="Outcome of the channel delivery attempt."
    )
    detail: str | None = Field(description="Error class or reason when not delivered, or null.")


class NotificationChannelStatusResponse(_ApiModel):
    """Configured status and latest non-muted delivery outcome of one notification channel."""

    name: Literal["log", "toast", "browser", "ntfy"] = Field(description="Delivery channel name.")
    state: Literal["on", "off", "unconfigured"] = Field(
        description="Current channel state: on, off, or unconfigured."
    )
    detail: str = Field(
        description="Human-readable configuration summary (never a secret or topic)."
    )
    last_result: Literal["delivered", "failed", "disabled", "unavailable"] | None = Field(
        default=None,
        description="Most recent non-muted delivery result for this channel, or null.",
    )
    last_attempted_at: datetime | None = Field(
        default=None,
        description="UTC instant of the most recent non-muted delivery attempt, or null.",
    )


class NotificationChannelsResponse(_ApiModel):
    """Response document for ``GET /api/notifications/channels``."""

    channels: tuple[NotificationChannelStatusResponse, ...] = Field(
        description="Status of the four delivery channels in order: log, toast, browser, ntfy."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


class NotificationDecisionResponse(_ApiModel):
    """One notification policy decision recorded during a monitor cycle."""

    id: int = Field(ge=1, description="Database primary key of the decision record.")
    location: str = Field(description="Name of the assessed location.")
    assessment_id: int = Field(ge=1, description="Identifier of the stored assessment.")
    change_position: int = Field(
        description=("Position of the change event within the assessment, or -1 for level/held.")
    )
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
    ] = Field(description="Trigger that the notification policy evaluated.")
    event_key: str | None = Field(description="Deduplication key for cooldown tracking, or null.")
    decision: Literal[
        "escalation",
        "sent",
        "repeat",
        "quiet_hours",
        "held",
        "withdrawn",
        "informational",
    ] = Field(description="Policy decision outcome for this trigger.")
    level_after: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Announced threat level after the decision, or null.",
    )
    notification_id: int | None = Field(
        default=None,
        ge=1,
        description="Identifier of the notification sent by this decision, or null.",
    )
    decided_at: datetime = Field(description="UTC instant when the decision was recorded.")


class NotificationItemResponse(_ApiModel):
    """A stored notification with its channel deliveries and policy decisions."""

    id: int = Field(ge=1, description="Database primary key of the notification.")
    location: str | None = Field(
        description="Watched location name, or null for system/test notifications."
    )
    time_zone: str | None = Field(description="IANA time zone of the location, or null.")
    assessment_id: int | None = Field(
        default=None,
        ge=1,
        description="Associated stored assessment identifier, or null.",
    )
    cycle_id: int | None = Field(
        default=None, ge=1, description="Associated monitor cycle identifier, or null."
    )
    kind: Literal["location", "degraded", "recovered", "stale_monitor", "test"] = Field(
        description="Notification category."
    )
    level: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Threat level announced by the notification, or null.",
    )
    escalation: bool = Field(
        description="Whether this notification is an upward threat-level escalation."
    )
    title: str = Field(description="Notification headline.")
    body: tuple[str, ...] = Field(description="Notification body lines.")
    created_at: datetime = Field(description="UTC instant when the notification was created.")
    created_at_local: str | None = Field(
        default=None,
        description="ISO 8601 creation time in the location's local time zone, or null.",
    )
    deliveries: tuple[NotificationDeliveryResponse, ...] = Field(
        description="Per-channel delivery attempts and outcomes."
    )
    decisions: tuple[NotificationDecisionResponse, ...] = Field(
        description="Policy decisions from the cycle that produced this notification."
    )


class NotificationsResponse(_ApiModel):
    """Response document for ``GET /api/notifications``."""

    limit: int = Field(ge=1, le=500, description="Maximum number of notifications requested.")
    notifications: tuple[NotificationItemResponse, ...] = Field(
        description="Stored notifications ordered newest first."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


# Timeline (GET /api/timeline) --------------------------------------------------------------


class TimelineEntryResponse(_ApiModel):
    """One chronological entry (assessment or notification) in ``GET /api/timeline``."""

    kind: Literal["assessment", "notification"] = Field(
        description="Timeline entry discriminator: assessment or notification."
    )
    id: int = Field(ge=1, description="Database primary key of the assessment or notification.")
    occurred_at: datetime = Field(
        description=(
            "UTC instant of the entry (as_of for assessments, created_at for notifications)."
        )
    )
    occurred_at_local: str | None = Field(
        default=None,
        description="ISO 8601 instant in the location's local time zone, or null.",
    )
    location: str | None = Field(
        description="Location name, or null for system/test notifications."
    )
    time_zone: str | None = Field(description="IANA time zone of the location, or null.")
    level: ThreatLevelResponse | None = Field(
        default=None,
        description="Threat level details when the entry carries a level, or null.",
    )
    rule: str | None = Field(
        default=None,
        description="Deciding ladder rule code for an assessment entry, or null.",
    )
    rule_trigger: str | None = Field(
        default=None,
        description="Deciding rule trigger summary for an assessment entry, or null.",
    )
    complete: bool | None = Field(
        default=None, description="Completeness flag for an assessment entry, or null."
    )
    snapshot_id: UUID | None = Field(
        default=None,
        description="Assessed snapshot identifier for an assessment entry, or null.",
    )
    stored_at: datetime | None = Field(
        default=None,
        description="UTC instant when an assessment was stored, or null.",
    )
    changes: tuple[AssessmentChangeResponse, ...] = Field(
        default=(), description="Change events recorded on an assessment entry."
    )
    notification_kind: (
        Literal["location", "degraded", "recovered", "stale_monitor", "test"] | None
    ) = Field(
        default=None,
        description="Notification category for a notification entry, or null.",
    )
    escalation: bool | None = Field(
        default=None, description="Escalation flag for a notification entry, or null."
    )
    title: str | None = Field(
        default=None, description="Notification title for a notification entry, or null."
    )
    body: tuple[str, ...] = Field(
        default=(), description="Notification body lines for a notification entry."
    )
    decisions: tuple[NotificationDecisionResponse, ...] = Field(
        default=(), description="Policy decisions associated with a notification entry."
    )
    deliveries: tuple[NotificationDeliveryResponse, ...] = Field(
        default=(),
        description="Channel delivery results associated with a notification entry.",
    )


class TimelineResponse(_ApiModel):
    """Response document for ``GET /api/timeline``."""

    location: str | None = Field(
        description=("Location name filter applied to the timeline, or null for all locations.")
    )
    limit: int = Field(ge=1, le=500, description="Maximum number of entries returned.")
    entries: tuple[TimelineEntryResponse, ...] = Field(
        description="Merged assessment and notification entries ordered newest first."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


# Settings (GET /api/settings) --------------------------------------------------------------


class SettingOriginResponse(_ApiModel):
    """Effective value and origin of one configuration setting."""

    table: str = Field(description="TOML table name, such as logging, engine, monitor, or web.")
    key: str = Field(description="Setting key within the TOML table.")
    value: str | int | float | bool = Field(description="Effective setting value.")
    origin: Literal["default", "file", "environment"] = Field(
        description=(
            "Where the effective value came from: default, weatherbot.toml, or environment."
        )
    )
    variable: str = Field(description="Environment variable name that overrides this setting.")


class SettingsResponse(_ApiModel):
    """Response document for ``GET /api/settings``."""

    settings_file: str = Field(description="Filesystem path to weatherbot.toml as a string.")
    settings_file_exists: bool = Field(description="Whether weatherbot.toml exists on disk.")
    file_modified_since_start: bool = Field(
        description=(
            "Whether weatherbot.toml has been modified on disk since the web server started."
        )
    )
    settings: tuple[SettingOriginResponse, ...] = Field(
        description="All effective settings in table and key order."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


# Disclaimer (GET /api/disclaimer) ----------------------------------------------------------


class DisclaimerResponse(_ApiModel):
    """Response document for ``GET /api/disclaimer``."""

    notice: str = Field(
        description="One-line informational-only disclaimer shown on every assessment surface."
    )
    essentials: tuple[str, ...] = Field(description="Essential disclaimer summary points.")
    full_text: str = Field(description="Complete text of DISCLAIMER.md.")
    url: str = Field(description="Canonical public URL for DISCLAIMER.md.")


# Map & Replay (GET /api/map, GET /api/replay, GET /api/replay/{atcf_id}/{advisory}) --------


class StormMapLayersResponse(_ApiModel):
    """GeoJSON map layers for one storm in a live or replayed snapshot."""

    atcf_id: str = Field(description="Storm ATCF identifier.")
    name: str = Field(description="Storm name.")
    classification: str | None = Field(
        description="Storm classification code or archive storm type, or null."
    )
    intensity_kt: int | None = Field(description="Maximum sustained wind speed in knots, or null.")
    pressure_mb: int | None = Field(description="Minimum central pressure in millibars, or null.")
    advisory: str | None = Field(description="Advisory number for the storm layers, or null.")
    issued_at: datetime | None = Field(
        description="UTC issuance instant of the storm advisory, or null."
    )
    cone: GeoJsonFeatureResponse | None = Field(
        description=(
            "Forecast cone Polygon/MultiPolygon feature (antimeridian-unwrapped), or null."
        )
    )
    track: GeoJsonFeatureResponse | None = Field(
        description=(
            "Forecast track LineString/MultiLineString feature (antimeridian-unwrapped), or null."
        )
    )
    forecast_points: GeoJsonFeatureCollectionResponse = Field(
        description="Forecast track Point features (antimeridian-unwrapped)."
    )
    watch_warnings: GeoJsonFeatureCollectionResponse = Field(
        description="Coastal watch-warning segment features (antimeridian-unwrapped)."
    )


class MapResponse(_ApiModel):
    """Response document for ``GET /api/map`` and ``GET /api/replay/{atcf_id}/{advisory}``."""

    snapshot_id: UUID | None = Field(
        description="Identifier of the rendered snapshot, or null when no snapshot is stored."
    )
    as_of: datetime | None = Field(
        description="UTC completion or issuance instant of the snapshot, or null."
    )
    status: Literal["complete", "partial", "failed"] | None = Field(
        description="Completeness status of the snapshot, or null."
    )
    origin: Literal["live", "replay"] | None = Field(
        description="Whether the map payload comes from a live snapshot or a replay advisory."
    )
    storms: tuple[StormMapLayersResponse, ...] = Field(
        description=(
            "Per-storm GeoJSON layers (cones, tracks, forecast points, and watches/warnings)."
        )
    )
    outlook_areas: GeoJsonFeatureCollectionResponse = Field(
        description=(
            "Tropical Weather Outlook development regions, disturbances, and motion arrows."
        )
    )
    locations: GeoJsonFeatureCollectionResponse = Field(
        description=(
            "Watched location Point features (and stored zone polygons) with current threat levels."
        )
    )
    location_polygons: GeoJsonFeatureCollectionResponse = Field(
        description=(
            "Stored county or forecast zone Polygon/MultiPolygon features for watched locations."
        )
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


class ReplayStormSummaryResponse(_ApiModel):
    """One historical storm available in the configured replay corpus."""

    atcf_id: str = Field(description="Storm ATCF identifier, such as AL112017.")
    name: str = Field(description="Historical storm name from the archive.")
    advisory_count: int = Field(
        ge=1,
        description="Number of advisories available for this storm in the corpus.",
    )
    advisories: tuple[str, ...] = Field(description="Advisory numbers in manifest issuance order.")
    first_issued_at: datetime = Field(
        description="UTC issuance instant of the storm's first advisory in the corpus."
    )
    last_issued_at: datetime = Field(
        description="UTC issuance instant of the storm's last advisory in the corpus."
    )


class ReplayStormsResponse(_ApiModel):
    """Response document for ``GET /api/replay``."""

    storms: tuple[ReplayStormSummaryResponse, ...] = Field(
        description="Historical storms available in the configured replay corpus."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


# Events (GET /api/events) ------------------------------------------------------------------


class StreamEvent(_ApiModel):
    """Server-sent event payload emitted by ``GET /api/events``.

    Carries only identifiers, location names, threat levels, kinds, and query keys to
    invalidate — never coordinates, distances, or bearings.
    """

    id: int = Field(ge=1, description="Process-wide monotonically increasing event identifier.")
    kind: EventKind = Field(description="Event category.")
    at: datetime = Field(description="UTC instant when the event was published.")
    invalidate: tuple[QueryKey, ...] = Field(
        default=(),
        description="Query keys that open dashboard pages must refetch.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="UTC instant when the server started (set on hello events), or null.",
    )
    cycle_id: int | None = Field(
        default=None,
        ge=1,
        description="Monitor cycle identifier, or null.",
    )
    runner: str | None = Field(
        default=None,
        description="Runner that executed the cycle, or null.",
    )
    trigger: str | None = Field(
        default=None,
        description="Trigger that initiated the cycle, or null.",
    )
    status: str | None = Field(
        default=None,
        description="Cycle or snapshot completion status, or null.",
    )
    snapshot_id: UUID | None = Field(
        default=None,
        description="Stored snapshot identifier (set on snapshot events), or null.",
    )
    location: str | None = Field(
        default=None,
        description=(
            "Watched location name (set on assessment, alert, notification, and location events), "
            "or null."
        ),
    )
    assessment_id: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Stored assessment identifier (set on assessment, alert, and notification events), "
            "or null."
        ),
    )
    level: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description=(
            "Threat level integer from 1 to 5 (set on assessment and notification events), or null."
        ),
    )
    complete: bool | None = Field(
        default=None,
        description=(
            "Whether the stored assessment had every required input (set on assessment events), "
            "or null."
        ),
    )
    notification_id: int | None = Field(
        default=None,
        ge=1,
        description="Stored notification identifier (set on notification events), or null.",
    )
    notification_kind: (
        Literal["location", "degraded", "recovered", "stale_monitor", "test"] | None
    ) = Field(
        default=None,
        description="Notification category (set on notification events), or null.",
    )
    escalation: bool | None = Field(
        default=None,
        description=(
            "Whether the notification announces an upward escalation (set on notification events), "
            "or null."
        ),
    )
    title: str | None = Field(
        default=None,
        description="Notification headline when delivered for display, or null.",
    )
    body: tuple[str, ...] | None = Field(
        default=None,
        description="Notification body lines when delivered for display, or null.",
    )
    display: bool = Field(
        default=False,
        description=(
            "Whether open dashboard pages should display this notification as an active alert."
        ),
    )
    call_id: int | None = Field(
        default=None,
        ge=1,
        description="AI ledger row identifier (set on ai events about a request or a control).",
    )
    output_id: int | None = Field(
        default=None,
        ge=1,
        description="Stored AI product identifier (set on ai events about a stored product).",
    )
    ai_kind: str | None = Field(
        default=None,
        description=(
            "AI row kind (briefing, summary, chat, narration, allowance, pause, or resume) "
            "on ai events, or null."
        ),
    )


# AI (GET /api/ai, /api/ai/calls, /api/ai/briefings, /api/ai/summaries, /api/ai/narrations) -


class AiModelsResponse(_ApiModel):
    """The models AI requests run on, by id and by display name."""

    model: str = Field(description="Model of briefings, chat, and narrations, by id.")
    model_name: str = Field(description="Its display name, such as Claude Sonnet 5.5.")
    summary_model: str = Field(description="Model of the change summaries, by id.")
    summary_model_name: str = Field(description="Its display name.")


class AiFeaturesResponse(_ApiModel):
    """Which AI products the ``[ai]`` settings switch on."""

    enabled: bool = Field(description="Whether [ai] enabled lets AI run at all.")
    change_summaries: bool = Field(description="Whether serve summarizes each change.")
    outlook_narration: bool = Field(description="Whether outlook graphics may be narrated.")


class AiKindTotalsResponse(_ApiModel):
    """One kind of request's count, tokens, and cost today."""

    kind: CallKind = Field(description="Request kind: briefing, summary, chat, or narration.")
    requests: int = Field(ge=0, description="Requests of this kind today.")
    input_tokens: int = Field(ge=0, description="Uncached input tokens.")
    cache_write_tokens: int = Field(ge=0, description="Tokens written to the prompt cache.")
    cache_read_tokens: int = Field(ge=0, description="Tokens read from the prompt cache.")
    output_tokens: int = Field(ge=0, description="Output tokens, thinking included.")
    cost_micro_usd: int = Field(ge=0, description="Cost at list price, in micro-dollars.")


class AiTodayResponse(_ApiModel):
    """Today's AI spend against the cap, in the operator's local calendar day."""

    day: str = Field(description="The operator's local calendar day, YYYY-MM-DD.")
    spent_micro_usd: int = Field(ge=0, description="Settled requests' cost, in micro-dollars.")
    reserved_micro_usd: int = Field(
        ge=0, description="Open reservations at their ceilings, in micro-dollars."
    )
    cap_micro_usd: int = Field(ge=0, description="The daily cap, before allowances.")
    allowance_micro_usd: int = Field(ge=0, description="Today's allowances, in micro-dollars.")
    allowances_left: int = Field(ge=0, description="How many more allowances today accepts.")
    calls: int = Field(ge=0, description="Requests today, of every kind.")
    input_tokens: int = Field(ge=0, description="Uncached input tokens today.")
    cache_write_tokens: int = Field(ge=0, description="Prompt-cache write tokens today.")
    cache_read_tokens: int = Field(ge=0, description="Prompt-cache read tokens today.")
    output_tokens: int = Field(ge=0, description="Output tokens today.")
    by_kind: tuple[AiKindTotalsResponse, ...] = Field(
        description="Today's totals per kind of request that ran."
    )


class AiStatusResponse(_ApiModel):
    """Response document for ``GET /api/ai`` and the AI controls: never a credential."""

    state: AiStateName = Field(
        description="off, ready, paused, capped, or unavailable; computed without a request."
    )
    reason: AiUnavailableReason | None = Field(
        description="Why AI is not ready (for example no_credential or capped); null when ready."
    )
    credential_source: CredentialSource | None = Field(
        description=(
            "Where the credential comes from (environment, auth_token, profile, or none), "
            "never its value; null while [ai] enabled is false."
        )
    )
    models: AiModelsResponse = Field(description="The models AI requests run on.")
    features: AiFeaturesResponse = Field(description="Which AI products are switched on.")
    today: AiTodayResponse = Field(description="Today's spend, reservations, and tokens.")
    paused: bool = Field(description="Whether the manual pause holds.")
    notice: str = Field(description="One-line informational-only disclaimer notice.")


class AiCallResponse(_ApiModel):
    """One AI ledger row: what it was, how it ended, and what it cost, never any text."""

    id: int = Field(ge=1, description="Ledger row identifier.")
    kind: str = Field(
        description="briefing, summary, chat, narration, or a control: allowance, pause, resume."
    )
    model: str | None = Field(description="Model id of a request; null for a control.")
    location: str | None = Field(description="Location name the request was about, or null.")
    status: str = Field(
        description=(
            "reserved, ok, failed, incomplete, declined, abandoned, or control (a control row)."
        )
    )
    started_at: datetime = Field(description="UTC instant the request was reserved.")
    finished_at: datetime | None = Field(description="UTC instant it settled, or null.")
    input_tokens: int = Field(ge=0, description="Uncached input tokens.")
    cache_write_tokens: int = Field(ge=0, description="Prompt-cache write tokens.")
    cache_read_tokens: int = Field(ge=0, description="Prompt-cache read tokens.")
    output_tokens: int = Field(ge=0, description="Output tokens.")
    cost_micro_usd: int | None = Field(
        description="Cost at list price in micro-dollars; null while reserved."
    )
    allowance_micro_usd: int = Field(
        ge=0, description="An allowance row's amount in micro-dollars; 0 otherwise."
    )
    stop_reason: str | None = Field(description="The final message's stop reason, or null.")
    refusal_category: str | None = Field(description="A refusal's category, or null.")
    error_kind: str | None = Field(description="Why the request failed, as a reason, or null.")


class AiCallsResponse(_ApiModel):
    """Response document for ``GET /api/ai/calls``: the ledger, newest first."""

    limit: int = Field(ge=1, le=100, description="Maximum number of rows requested.")
    calls: tuple[AiCallResponse, ...] = Field(description="Ledger rows, newest first.")
    notice: str = Field(description="One-line informational-only disclaimer notice.")


class AiSourceResponse(_ApiModel):
    """A source an AI product cites, resolved from its stored record, never from the model."""

    key: str = Field(description="The key the product cites, such as S2.")
    source_id: SourceId = Field(description="Data-source register identifier.")
    title: str = Field(description="The product's title, as a page shows it.")
    code: str | None = Field(description="Product code (TCP, TWO, an NWS event), or null.")
    issuer: str | None = Field(description="Issuing office, such as NHC, or null.")
    advisory: str | None = Field(description="Advisory number, or null.")
    issued_at: datetime | None = Field(description="UTC issuance, to the hour, or null.")
    why: str | None = Field(
        default=None, description="What the product took from the source, or null."
    )
    url: str | None = Field(
        description="A public NOAA product page that names no point, or null (never the model's)."
    )


class AiTimelineItemResponse(_ApiModel):
    """One expected development in a briefing's timeline."""

    when: str = Field(description="When, as the products state it.")
    what: str = Field(description="What happens then, in plain language.")
    sources: tuple[str, ...] = Field(description="The source keys that state it.")


class StoredBriefingResponse(_ApiModel):
    """A location's newest stored briefing: its sections, or why it was withheld."""

    id: int = Field(ge=1, description="Stored AI product identifier.")
    status: Literal["ok", "withheld"] = Field(description="ok, or withheld (no text is kept).")
    withheld_reason: str | None = Field(description="Why it was withheld, or null.")
    model: str = Field(description="Model id that wrote it.")
    model_name: str = Field(description="Its display name.")
    prompt_version: str = Field(description="SHA-256 of the frozen prompt it was written with.")
    assessment_id: int | None = Field(description="The assessment it was written for.")
    created_at: datetime = Field(description="UTC instant it was stored.")
    stale: bool = Field(description="Whether a newer assessment has been stored since.")
    situation: str | None = Field(description="The situation section, or null when withheld.")
    what_it_means_here: str | None = Field(
        description="What the engine's level means here, or null when withheld."
    )
    timeline: tuple[AiTimelineItemResponse, ...] = Field(
        description="Expected developments, earliest first."
    )
    actions: tuple[str, ...] = Field(description="The ladder's actions, as the briefing says.")
    sources: tuple[AiSourceResponse, ...] = Field(description="Every source the briefing cites.")


class LocationBriefingResponse(_ApiModel):
    """One watched location's latest assessment and its newest stored briefing."""

    location: str = Field(description="Watched location name.")
    assessment_id: int | None = Field(description="The location's latest assessment, or null.")
    briefing: StoredBriefingResponse | None = Field(
        description="The newest stored briefing, or null when none is stored."
    )


class BriefingsResponse(_ApiModel):
    """Response document for ``GET /api/ai/briefings``."""

    location: str | None = Field(description="Location name filter, or null for every one.")
    locations: tuple[LocationBriefingResponse, ...] = Field(
        description="Each watched location's newest briefing, in name order."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


class StoredSummaryResponse(_ApiModel):
    """One stored change summary, or why it was withheld."""

    id: int = Field(ge=1, description="Stored AI product identifier.")
    location: str | None = Field(description="Location name.")
    assessment_id: int | None = Field(description="The assessment whose changes it summarizes.")
    status: Literal["ok", "withheld"] = Field(description="ok, or withheld (no text is kept).")
    withheld_reason: str | None = Field(description="Why it was withheld, or null.")
    model: str = Field(description="Model id that wrote it.")
    model_name: str = Field(description="Its display name.")
    prompt_version: str = Field(description="SHA-256 of the frozen prompt it was written with.")
    created_at: datetime = Field(description="UTC instant it was stored.")
    summary: str | None = Field(description="What changed, or null when withheld.")
    sources: tuple[AiSourceResponse, ...] = Field(description="Every source the summary cites.")


class SummariesResponse(_ApiModel):
    """Response document for ``GET /api/ai/summaries``: newest first."""

    location: str | None = Field(description="Location name filter, or null for every one.")
    limit: int = Field(ge=1, le=200, description="Maximum number of summaries requested.")
    summaries: tuple[StoredSummaryResponse, ...] = Field(
        description="Stored change summaries, newest first."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


class AiAreaResponse(_ApiModel):
    """One area an outlook graphic marks, in plain words, with its chance as the TWO states it."""

    description: str = Field(description="Where the area lies and what it is.")
    chance_text: str = Field(description='Its chance as the TWO states it, or "not stated".')


class StoredNarrationResponse(_ApiModel):
    """The newest stored narration of one of the latest snapshot's outlook graphics."""

    id: int = Field(ge=1, description="Stored AI product identifier.")
    basin: Basin = Field(description="Outlook basin: atl, pac, or cpac.")
    horizon: Horizon = Field(description="Outlook horizon: 2d0 or 7d0.")
    graphic_sha256: str = Field(description="SHA-256 of the narrated graphic's PNG body.")
    status: Literal["ok", "withheld"] = Field(description="ok, or withheld (no text is kept).")
    withheld_reason: str | None = Field(description="Why it was withheld, or null.")
    model: str = Field(description="Model id that wrote it.")
    model_name: str = Field(description="Its display name.")
    prompt_version: str = Field(description="SHA-256 of the narration prompt.")
    created_at: datetime = Field(description="UTC instant it was stored.")
    summary: str | None = Field(description="What the graphic shows, or null when withheld.")
    areas: tuple[AiAreaResponse, ...] = Field(description="Each area the graphic marks.")
    caveat: str | None = Field(description="That the official graphic governs, or null.")
    two: AiSourceResponse | None = Field(
        description="The TWO the narration was checked against, or null when withheld."
    )


class NarrationsResponse(_ApiModel):
    """Response document for ``GET /api/ai/narrations``."""

    enabled: bool = Field(description="Whether [ai] outlook_narration is on.")
    label: str = Field(description="How every surface labels a narration.")
    narrations: tuple[StoredNarrationResponse, ...] = Field(
        description="The latest snapshot's graphics' newest stored narrations."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


class AiRefusalDetail(_ApiModel):
    """Why an AI stream was refused before it began: a reason and its fixed text."""

    reason: AiUnavailableReason = Field(description="The reason, such as capped or busy.")
    message: str = Field(description="Fixed text for the reason; never an SDK message.")


class AiRefusalResponse(_ApiModel):
    """Response document of a 503 or 429 answer to an AI stream."""

    detail: AiRefusalDetail = Field(description="Why the stream was refused.")


class BriefingRequest(_ApiModel):
    """Request body for ``POST /api/ai/briefings``."""

    location: str = Field(min_length=1, description="Name of the watched location to brief.")
    new: bool = Field(default=False, description="Ask for a new briefing even when one is stored.")


class ChatRequest(_ApiModel):
    """Request body for ``POST /api/ai/chat``."""

    question: str = Field(
        min_length=1, max_length=QUESTION_LIMIT, description="The question, 1 to 2,000 characters."
    )
    conversation_id: str | None = Field(
        default=None, max_length=64, description="The conversation to continue, or null."
    )
    location: str | None = Field(
        default=None, description="The location the question is about, or null for every one."
    )

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            message = "a question is not blank"
            raise ValueError(message)
        return value


class NarrationRequest(_ApiModel):
    """Request body for ``POST /api/ai/narrations``."""

    basin: Basin = Field(description="Outlook basin: atl, pac, or cpac.")
    horizon: Horizon = Field(description="Outlook horizon: 2d0 or 7d0.")


class PauseRequest(_ApiModel):
    """Request body for ``PUT /api/ai/pause``."""

    paused: bool = Field(description="Whether every AI request is refused until resumed.")


class AllowanceRequest(_ApiModel):
    """Request body for ``POST /api/ai/allowance``."""

    usd: float = Field(gt=0, description="Dollars to add to today's limit, at most one day's cap.")


class BriefingStreamEvent(_ApiModel):
    """One server-sent event of ``POST /api/ai/briefings``: never a coordinate or a distance."""

    kind: Literal["started", "section", "done", "withheld", "unavailable"] = Field(
        description="started, then a section per validated section, then done; or withheld "
        "(remove every section shown) or unavailable."
    )
    model: str | None = Field(default=None, description="Model id (started), or null.")
    model_name: str | None = Field(default=None, description="Its display name, or null.")
    assessment_id: int | None = Field(
        default=None, description="The assessment briefed (started), or null."
    )
    as_of: datetime | None = Field(
        default=None, description="UTC instant of that assessment (started), or null."
    )
    prompt_version: str | None = Field(
        default=None, description="SHA-256 of the frozen prompt (started), or null."
    )
    section: SectionName | None = Field(default=None, description="The section's name, or null.")
    text: str | None = Field(default=None, description="The section's plain text, or null.")
    output_id: int | None = Field(
        default=None, description="Stored product identifier (done, withheld), or null."
    )
    created_at: datetime | None = Field(
        default=None, description="UTC instant the briefing was stored (done), or null."
    )
    reused: bool | None = Field(
        default=None, description="Whether a stored briefing was replayed (done), or null."
    )
    reason: str | None = Field(
        default=None, description="Why it was withheld or unavailable, or null."
    )
    detail: str | None = Field(
        default=None, description="Fixed text for the reason, never the model's, or null."
    )


class ChatStreamEvent(_ApiModel):
    """One server-sent event of ``POST /api/ai/chat``: never a coordinate or a distance."""

    kind: Literal["started", "tool", "text", "done", "withheld", "unavailable"] = Field(
        description="started, then tool and text events, then done; or withheld (the rest of "
        "the answer and the conversation end) or unavailable."
    )
    conversation_id: str | None = Field(
        default=None, description="The conversation (started), or null."
    )
    model: str | None = Field(default=None, description="Model id (started), or null.")
    model_name: str | None = Field(default=None, description="Its display name, or null.")
    tool: ToolName | Literal["unknown_tool"] | None = Field(
        default=None, description="The tool's name only (tool), or null."
    )
    text: str | None = Field(default=None, description="One checked sentence (text), or null.")
    call_ids: tuple[int, ...] = Field(
        default=(), description="The turn's ledger rows (done, withheld, unavailable)."
    )
    reason: str | None = Field(
        default=None, description="Why it was withheld or unavailable, or null."
    )
    detail: str | None = Field(
        default=None, description="Fixed text for the reason, never the model's, or null."
    )


class NarrationStreamEvent(_ApiModel):
    """One server-sent event of ``POST /api/ai/narrations``: never a coordinate or a distance."""

    kind: Literal["started", "done", "withheld", "unavailable"] = Field(
        description="started, then done with the narration; or withheld or unavailable."
    )
    model: str | None = Field(default=None, description="Model id (started), or null.")
    model_name: str | None = Field(default=None, description="Its display name, or null.")
    basin: Basin | None = Field(default=None, description="Outlook basin (started), or null.")
    horizon: Horizon | None = Field(default=None, description="Outlook horizon (started), or null.")
    graphic_sha256: str | None = Field(
        default=None, description="SHA-256 of the graphic's PNG body (started), or null."
    )
    two_issued_at: datetime | None = Field(
        default=None, description="UTC issuance of the TWO it is checked against, or null."
    )
    prompt_version: str | None = Field(
        default=None, description="SHA-256 of the narration prompt (started), or null."
    )
    output_id: int | None = Field(
        default=None, description="Stored product identifier (done, withheld), or null."
    )
    created_at: datetime | None = Field(
        default=None, description="UTC instant the narration was stored (done), or null."
    )
    reused: bool | None = Field(
        default=None, description="Whether a stored narration was replayed (done), or null."
    )
    summary: str | None = Field(default=None, description="What the graphic shows (done), or null.")
    areas: tuple[AiAreaResponse, ...] = Field(
        default=(), description="Each area the graphic marks (done)."
    )
    caveat: str | None = Field(
        default=None, description="That the official graphic governs (done), or null."
    )
    reason: str | None = Field(
        default=None, description="Why it was withheld or unavailable, or null."
    )
    detail: str | None = Field(
        default=None, description="Fixed text for the reason, never the model's, or null."
    )


# Outlook (GET /api/outlook, GET /api/outlook/{basin}/{horizon}) -----------------------------


class OutlookGraphicResponse(_ApiModel):
    """One official outlook graphic stored with the latest snapshot."""

    basin: Basin = Field(description="Outlook basin: atl, pac, or cpac.")
    horizon: Horizon = Field(description="Outlook horizon: 2d0 or 7d0.")
    width_px: int = Field(gt=0, description="Image width in pixels.")
    height_px: int = Field(gt=0, description="Image height in pixels.")
    sha256: str = Field(description="SHA-256 of the PNG body served by the image route.")
    fetched_at: datetime = Field(description="UTC instant the graphic was fetched.")
    issued_at: datetime | None = Field(description="UTC issuance when NHC states one, or null.")


class OutlookGraphicsResponse(_ApiModel):
    """Response document for ``GET /api/outlook``."""

    snapshot_id: UUID | None = Field(
        description="The latest snapshot, or null when no snapshot is stored."
    )
    graphics: tuple[OutlookGraphicResponse, ...] = Field(
        description="The official outlook graphics the latest snapshot stored."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


# Actions (POST /api/locations, PUT /api/locations/evacuation, POST /api/cycles,
# POST /api/notifications/test) -------------------------------------------------------------


class CreateLocationRequest(_ApiModel):
    """Request body for ``POST /api/locations``."""

    name: str = Field(description="Display name for the watched location.")
    latitude: float = Field(description="Location latitude in decimal degrees [-90, 90].")
    longitude: float = Field(description="Location longitude in decimal degrees [-180, 180].")
    polygon: Literal["county", "forecast"] | None = Field(
        default=None,
        description="Optional NWS zone polygon to store: county, forecast, or null.",
    )


class SearchLocationsRequest(_ApiModel):
    """Request body for ``POST /api/locations/search``."""

    query: str = Field(description="Place query to forward-geocode through Nominatim.")


class LocationSearchCandidateResponse(_ApiModel):
    """One forward-geocoding candidate returned by ``POST /api/locations/search``."""

    display_name: str = Field(description="Full Nominatim display label for the candidate.")
    name: str = Field(description="Short place name from Nominatim.")
    latitude: float = Field(ge=-90, le=90, description="Latitude in degrees north.")
    longitude: float = Field(ge=-180, le=180, description="Longitude in degrees east.")
    country_code: str | None = Field(
        description="ISO 3166-1 alpha-2 country code in uppercase, or null."
    )
    category: str = Field(description="Nominatim feature category, such as boundary or place.")
    kind: str = Field(description="Nominatim feature type, such as administrative or city.")


class SearchLocationsResponse(_ApiModel):
    """Response document for ``POST /api/locations/search``."""

    candidates: tuple[LocationSearchCandidateResponse, ...] = Field(
        description="Up to five Nominatim candidates matching the search query."
    )
    attribution: str = Field(description="Required OpenStreetMap Nominatim attribution text.")
    notice: str = Field(description="One-line informational-only disclaimer notice.")


class RemoveLocationRequest(_ApiModel):
    """Request body for ``POST /api/locations/remove``."""

    location: str = Field(description="Name of the watched location to remove.")


class RemoveLocationResponse(_ApiModel):
    """Response document for ``POST /api/locations/remove``."""

    removed: str = Field(description="Name of the removed watched location.")
    notice: str = Field(description="One-line informational-only disclaimer notice.")


class UpdateEvacuationRequest(_ApiModel):
    """Request body for ``PUT /api/locations/evacuation``."""

    location: str = Field(description="Name of the watched location to update.")
    on: bool = Field(description="Whether an official evacuation order is in effect.")


class EvacuationUpdateResponse(_ApiModel):
    """Response document for ``PUT /api/locations/evacuation``."""

    location: LocationResponse = Field(
        description="Updated watched location in /api/locations' shape."
    )
    changed: bool = Field(
        description="Whether the evacuation-order toggle changed from its previous state."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


class UpdateLocationPreferencesRequest(_ApiModel):
    """Request body for ``PUT /api/locations/preferences``."""

    location: str = Field(min_length=1, description="Name of the watched location to update.")
    preferences: LocationPreferencesResponse = Field(
        description="Per-location notification channel preferences."
    )


class TriggerCycleRequest(_ApiModel):
    """Empty JSON request body for ``POST /api/cycles``."""


class TriggerCycleResponse(_ApiModel):
    """Response document for ``POST /api/cycles`` (HTTP 202 Accepted)."""

    status: Literal["accepted"] = Field(
        default="accepted",
        description="Confirmation that the manual cycle was scheduled on the server loop.",
    )
    trigger: Literal["manual"] = Field(
        default="manual",
        description="Cycle trigger passed to the running schedule.",
    )
    started_at: datetime = Field(
        description="UTC instant when the manual cycle request was accepted."
    )
    notice: str = Field(description="One-line informational-only disclaimer notice.")


class TestNotificationRequest(_ApiModel):
    """Empty JSON request body for ``POST /api/notifications/test``."""
