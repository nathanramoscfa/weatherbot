# src/weatherbot/services/persistence/tables.py
"""The tables Weatherbot writes, in SQLAlchemy 2's typed declarative mapping.

Tables arrive with their writers: Phase 2's snapshots and locations (revisions 0001 and
0002), and the assessments, their evidence, and their changes (revision 0003, Phase 3);
notifications and the heartbeat (Phase 4), and briefings and the Claude ledger (Phase 6)
are later revisions. Every instant goes in and comes out as an aware UTC value. A naming
convention names every constraint, so a SQLite batch migration can find and alter it.

Records that a snapshot holds by reference (a storm, a text product, a feed item, an
alert) are stored once and observed per snapshot, and every observation keeps what the
snapshot saw: its position in the snapshot's tuple and its own provenance.
"""

from datetime import UTC, datetime
from typing import Any, ClassVar, Final, override
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Dialect,
    ForeignKey,
    Index,
    LargeBinary,
    MetaData,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from weatherbot.models import CHANGE_KINDS, AlertLevel

NAMING_CONVENTION: Final = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

PRODUCT_KINDS: Final = (
    "cone",
    "track_point",
    "track",
    "watch_warning",
    "wind_radii",
    "arrival_time",
    "outlook_area",
    "wind_probability",
    "breakpoint",
    "display_layer",
    "outlook_graphic",
)
OUTCOME_STATUSES: Final = ("ok", "not_modified", "failed", "skipped")
SNAPSHOT_STATUSES: Final = ("complete", "partial", "failed")
EVIDENCE_ROLES: Final = ("evidence", "official")
"""An evidence row is one match of the deciding rule, or one official product considered."""


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class UtcDateTime(TypeDecorator[datetime]):
    """An aware instant, stored as naive UTC text and read back as aware UTC."""

    impl = DateTime(timezone=False)
    cache_ok = True

    @override
    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            message = "an instant must be timezone-aware"
            raise ValueError(message)
        return value.astimezone(UTC).replace(tzinfo=None)

    @override
    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


# Python None is SQL NULL, never the JSON text "null".
Json: Final = JSON(none_as_null=True)


class Base(DeclarativeBase):
    """The declarative base: every table shares one metadata and its naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: UtcDateTime(), dict[str, Any]: Json}


class LocationRow(Base):
    """A watched location. Its coordinates never leave the local database."""

    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint(
            "(nws_forecast_zone IS NULL) = (nws_county_zone IS NULL)"
            " AND (nws_forecast_zone IS NULL) = (nws_cwa IS NULL)"
            " AND (nws_forecast_zone IS NULL) = (nws_time_zone IS NULL)"
            " AND (nws_forecast_zone IS NULL) = (nws_city IS NULL)"
            " AND (nws_forecast_zone IS NULL) = (nws_state IS NULL)",
            name="nws_coverage_whole",
        ),
        CheckConstraint("(polygon IS NULL) = (polygon_crs IS NULL)", name="polygon_has_crs"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    latitude: Mapped[float]
    longitude: Mapped[float]
    polygon: Mapped[dict[str, Any] | None] = mapped_column(comment="GeoJSON geometry")
    polygon_crs: Mapped[str | None] = mapped_column(Text, comment="EPSG:4326 or the WKT")
    polygon_crs_datum: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(String(2))
    display_name: Mapped[str | None] = mapped_column(Text)
    nws_forecast_zone: Mapped[str | None] = mapped_column(String(6))
    nws_county_zone: Mapped[str | None] = mapped_column(String(6))
    nws_cwa: Mapped[str | None] = mapped_column(String(3))
    nws_time_zone: Mapped[str | None] = mapped_column(Text)
    nws_city: Mapped[str | None] = mapped_column(Text)
    nws_state: Mapped[str | None] = mapped_column(Text)
    breakpoint_span: Mapped[dict[str, Any] | None]
    evacuation_order_in_effect: Mapped[bool] = mapped_column(server_default=false())
    evacuation_order_set_at: Mapped[datetime | None] = mapped_column(
        comment="When the toggle was last turned on or off (revision 0003)"
    )
    geocoding: Mapped[dict[str, Any] | None] = mapped_column(comment="Provenance JSON")
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class SnapshotRow(Base):
    """One run's snapshot."""

    __tablename__ = "snapshots"
    __table_args__ = (CheckConstraint(_one_of("status", SNAPSHOT_STATUSES), name="status"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(8))


class SourceOutcomeRow(Base):
    """What one source answered in one snapshot."""

    __tablename__ = "source_outcomes"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "source_id"),
        CheckConstraint(_one_of("status", OUTCOME_STATUSES), name="status"),
        CheckConstraint("(status = 'failed') = (error_kind IS NOT NULL)", name="error_kind"),
        CheckConstraint("(status = 'skipped') = (reason IS NOT NULL)", name="reason"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"))
    position: Mapped[int]
    source_id: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(12))
    error_kind: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(comment="Its latest answer's")


class ResponseBodyRow(Base):
    """A response body, stored once per SHA-256 and zlib-compressed."""

    __tablename__ = "response_bodies"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    size: Mapped[int] = mapped_column(comment="Bytes before compression")
    body: Mapped[bytes] = mapped_column(LargeBinary, comment="zlib-compressed")


class RawResponseRow(Base):
    """One answer as received: allowlisted response headers only, never a request header.

    ``url`` can carry a location's coordinates; it stays in this local database.
    """

    __tablename__ = "raw_responses"
    __table_args__ = (
        UniqueConstraint("source_id", "product_key", "issued_at", "sha256"),
        Index(None, "url", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(32))
    product_key: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime | None]
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[int]
    fetched_at: Mapped[datetime]
    sha256: Mapped[str] = mapped_column(ForeignKey("response_bodies.sha256"))
    headers: Mapped[dict[str, Any]]
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)


class OutcomeResponseRow(Base):
    """The answers behind one source outcome, in the order they arrived."""

    __tablename__ = "outcome_responses"

    outcome_id: Mapped[int] = mapped_column(
        ForeignKey("source_outcomes.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    raw_response_id: Mapped[int] = mapped_column(ForeignKey("raw_responses.id"), index=True)


class StormRow(Base):
    """A storm, by ATCF id, and when a snapshot first and last saw it."""

    __tablename__ = "storms"

    id: Mapped[int] = mapped_column(primary_key=True)
    atcf_id: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(Text)
    basin: Mapped[str] = mapped_column(String(2))
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]


class StormObservationRow(Base):
    """A storm as one snapshot's roster summarized it."""

    __tablename__ = "storm_observations"
    __table_args__ = (UniqueConstraint("snapshot_id", "storm_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"))
    storm_id: Mapped[int] = mapped_column(ForeignKey("storms.id"), index=True)
    position: Mapped[int]
    summary: Mapped[dict[str, Any]] = mapped_column(comment="StormSummary JSON")


class AdvisoryRow(Base):
    """An advisory of a storm, as the first product that named it stated it."""

    __tablename__ = "advisories"
    __table_args__ = (UniqueConstraint("storm_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    storm_id: Mapped[int] = mapped_column(ForeignKey("storms.id"))
    number: Mapped[str] = mapped_column(String(4), comment="Such as 22A")
    issued_at: Mapped[datetime | None]
    local_text: Mapped[str | None] = mapped_column(Text)


class ProductGeometryRow(Base):
    """A snapshot's product: its geometry as GeoJSON in its own CRS, and everything else.

    ``geojson`` is a GeoJSON geometry, or a FeatureCollection for a product of several
    shapes (an arrival-time product's lines, a wind-probability product's bands, a display
    layer as received). An outlook graphic has no geometry.
    """

    __tablename__ = "product_geometries"
    __table_args__ = (
        CheckConstraint(_one_of("product_kind", PRODUCT_KINDS), name="product_kind"),
        Index(None, "snapshot_id", "product_kind", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"))
    advisory_id: Mapped[int | None] = mapped_column(ForeignKey("advisories.id"), index=True)
    product_kind: Mapped[str] = mapped_column(String(20))
    position: Mapped[int]
    crs: Mapped[str | None] = mapped_column(Text, comment="EPSG:4326 or the verbatim WKT")
    crs_datum: Mapped[str | None] = mapped_column(Text)
    geojson: Mapped[dict[str, Any] | None]
    properties: Mapped[dict[str, Any]]
    provenance: Mapped[dict[str, Any]]


class TextProductRow(Base):
    """A TCP or a TWO, stored once per product id."""

    __tablename__ = "text_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(Text, unique=True)
    code: Mapped[str] = mapped_column(String(3))
    location: Mapped[str] = mapped_column(String(3))
    wmo_collective_id: Mapped[str] = mapped_column(Text)
    issuing_office: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime]
    atcf_id: Mapped[str | None] = mapped_column(String(8))
    advisory: Mapped[str | None] = mapped_column(String(4))
    text: Mapped[str] = mapped_column(Text)


class TextProductObservationRow(Base):
    """A text product as one snapshot fetched it."""

    __tablename__ = "text_product_observations"
    __table_args__ = (UniqueConstraint("snapshot_id", "text_product_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"))
    text_product_id: Mapped[int] = mapped_column(ForeignKey("text_products.id"), index=True)
    position: Mapped[int]
    provenance: Mapped[dict[str, Any]]


class FeedItemRow(Base):
    """A GIS RSS item, stored once per feed and guid, with its latest values."""

    __tablename__ = "feed_items"
    __table_args__ = (UniqueConstraint("feed", "guid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guid: Mapped[str] = mapped_column(Text)
    feed: Mapped[str] = mapped_column(String(2))
    title: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None]
    is_placeholder: Mapped[bool]
    atcf_id: Mapped[str | None] = mapped_column(String(8))
    slot: Mapped[str | None] = mapped_column(String(3))
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]


class FeedItemObservationRow(Base):
    """A feed item exactly as one snapshot read it."""

    __tablename__ = "feed_item_observations"
    __table_args__ = (UniqueConstraint("snapshot_id", "feed_item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"))
    feed_item_id: Mapped[int] = mapped_column(ForeignKey("feed_items.id"), index=True)
    position: Mapped[int]
    item: Mapped[dict[str, Any]] = mapped_column(comment="GisFeedItem JSON")


class AlertRow(Base):
    """An NWS alert, stored once per alert id."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[str] = mapped_column(Text, unique=True)
    sent: Mapped[datetime]
    effective: Mapped[datetime]
    expires: Mapped[datetime]
    ends: Mapped[datetime | None]
    event: Mapped[str] = mapped_column(Text)
    alert: Mapped[dict[str, Any]] = mapped_column(comment="NwsAlert JSON, as first seen")
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]


class AlertObservationRow(Base):
    """An alert one snapshot found for one location, and the queries that found it.

    A row without an alert records that the location's queries found none, so a snapshot
    keeps an empty list apart from a location it did not ask about.
    """

    __tablename__ = "alert_observations"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "location_id", "alert_id"),
        CheckConstraint("(alert_id IS NULL) = (found_by IS NULL)", name="found_by"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"))
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), index=True
    )
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), index=True)
    position: Mapped[int]
    found_by: Mapped[list[Any] | None] = mapped_column(Json, comment="AlertQuery JSON list")


class SettingRow(Base):
    """Application state, such as when the disclaimer was first shown; not weatherbot.toml."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, comment="Any JSON value")
    updated_at: Mapped[datetime]


class DriftWarningRow(Base):
    """A Source-drift warning logged while one snapshot was fetched (revision 0002).

    The message names products and fields, never a coordinate (``weatherbot.sources.drift``).
    """

    __tablename__ = "drift_warnings"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("snapshots.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    source_id: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)


class AssessmentRow(Base):
    """The level one live snapshot set for one location, under one ruleset (revision 0003).

    ``assessment`` is the whole ``Assessment`` as validated JSON, so it loads back equal;
    the level, rule, completeness, and thresholds are copied beside it for queries. Its
    evidence holds distances that locate the location, so it stays in this database.
    Removing the location removes its assessments, their evidence, and their changes.
    """

    __tablename__ = "assessments"
    __table_args__ = (
        UniqueConstraint("location_id", "snapshot_id", "ruleset"),
        Index(None, "location_id", "as_of"),
        CheckConstraint(f"level BETWEEN {min(AlertLevel):d} AND {max(AlertLevel):d}", name="level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"))
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("snapshots.id", ondelete="CASCADE"), index=True
    )
    ruleset: Mapped[str] = mapped_column(String(64), comment="Thresholds and rule order")
    as_of: Mapped[datetime] = mapped_column(comment="The snapshot's instant")
    level: Mapped[int]
    rule: Mapped[str] = mapped_column(String(40))
    complete: Mapped[bool]
    thresholds: Mapped[dict[str, Any]] = mapped_column(comment="Thresholds JSON")
    assessment: Mapped[dict[str, Any]] = mapped_column(comment="Assessment JSON")
    stored_at: Mapped[datetime]


class AssessmentEvidenceRow(Base):
    """One evidence record or one official product of an assessment, for queries."""

    __tablename__ = "assessment_evidence"
    __table_args__ = (
        UniqueConstraint("assessment_id", "role", "position"),
        CheckConstraint(_one_of("role", EVIDENCE_ROLES), name="role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(8))
    position: Mapped[int]
    kind: Mapped[str] = mapped_column(String(24), comment="The product's kind")
    rule: Mapped[str | None] = mapped_column(String(40))
    source_id: Mapped[str | None] = mapped_column(String(32))
    code: Mapped[str | None] = mapped_column(Text, comment="The NWS event or the NHC code")
    distance_km: Mapped[float | None]
    covers: Mapped[bool | None] = mapped_column(comment="An official product's coverage")


class AssessmentChangeRow(Base):
    """One change event from the previous stored assessment of the location, in order."""

    __tablename__ = "assessment_changes"
    __table_args__ = (
        UniqueConstraint("assessment_id", "position"),
        CheckConstraint(_one_of("kind", CHANGE_KINDS), name="kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    position: Mapped[int]
    kind: Mapped[str] = mapped_column(String(20))
    event: Mapped[dict[str, Any]] = mapped_column(comment="ChangeEvent JSON")
