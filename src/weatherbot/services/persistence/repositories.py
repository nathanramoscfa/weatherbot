# src/weatherbot/services/persistence/repositories.py
"""Repositories: the domain models in, the same models out.

``LocationRepository`` keeps the watched locations, ``SnapshotRepository`` stores a whole
live ``Snapshot`` with its raw responses in one transaction and loads it back equal (a
replay snapshot is never stored: history is live only; an unchanged product's content is
stored once, whichever snapshots hold it), ``AssessmentRepository`` stores
each live assessment with its evidence and changes and loads it back equal, and
``SettingsRepository`` keeps application state such as when the disclaimer was shown.

A write that takes a ``session`` joins the caller's transaction, so a service can store
several records in one; without one, it commits on its own.
"""

import hashlib
import json
import zlib
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, cast
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import Engine, Select, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from weatherbot.models import (
    Advisory,
    AdvisoryNumber,
    ArrivalTimeProduct,
    Assessment,
    Breakpoint,
    BreakpointSpan,
    ChangeEvent,
    ConeGeometry,
    DisplayLayer,
    DomainModel,
    ForecastTrack,
    GisFeedItem,
    LatLon,
    Location,
    NwsAlert,
    NwsCoverage,
    OutlookArea,
    OutlookGraphic,
    Snapshot,
    SourceId,
    SourceOutcome,
    StormProducts,
    StormSummary,
    TextProduct,
    TrackPoint,
    WatchWarningSegment,
    WindProbabilityProduct,
    WindRadii,
)
from weatherbot.services.persistence.codec import (
    EncodedProduct,
    Json,
    canonical_content,
    crs_columns,
    crs_from_columns,
    decode_product,
    dump,
    encode_product,
    from_content,
    geojson,
    validated,
    with_crs,
)
from weatherbot.services.persistence.raw_cache import CachedFetch, CorruptBodyError, record_fetch
from weatherbot.services.persistence.tables import (
    AdvisoryRow,
    AlertObservationRow,
    AlertRow,
    AssessmentChangeRow,
    AssessmentEvidenceRow,
    AssessmentRow,
    DriftWarningRow,
    FeedItemObservationRow,
    FeedItemRow,
    GeometryContentRow,
    LocationRow,
    OutcomeResponseRow,
    ProductGeometryRow,
    SettingRow,
    SnapshotGeometryRow,
    SnapshotProvenanceRow,
    SnapshotRow,
    SourceOutcomeRow,
    StormObservationRow,
    StormRow,
    TextProductObservationRow,
    TextProductRow,
)

type Clock = Callable[[], datetime]

# Storm products, in the order StormProducts holds them.
_STORM_KINDS: Final = (
    "cone",
    "track",
    "track_point",
    "watch_warning",
    "wind_radii",
    "arrival_time",
)
_SNAPSHOT_KINDS: Final = (
    "outlook_area",
    "wind_probability",
    "breakpoint",
    "display_layer",
    "outlook_graphic",
)


def _now() -> datetime:
    return datetime.now(UTC)


class LocationExistsError(Exception):
    """A location of that name is already stored."""


class SnapshotStoreError(Exception):
    """A snapshot cannot be stored as given."""


class AssessmentStoreError(Exception):
    """An assessment cannot be stored as given."""


@dataclass(frozen=True)
class DriftWarning:
    """A Source-drift warning a fetch logged: its source and a coordinate-free message."""

    source_id: SourceId
    message: str


@contextmanager
def _writing(engine: Engine, session: Session | None) -> Generator[Session]:
    """Join the caller's transaction, or open one that commits when the block ends."""
    if session is not None:
        yield session
        return
    with Session(engine) as own, own.begin():
        yield own


# Locations ---------------------------------------------------------------------------------


def _location_row(location: Location, now: datetime) -> LocationRow:
    polygon = location.polygon
    polygon_crs, polygon_datum = crs_columns(polygon.crs) if polygon else (None, None)
    nws = location.nws
    return LocationRow(
        name=location.name,
        latitude=location.point.latitude,
        longitude=location.point.longitude,
        polygon=geojson(dump(polygon)) if polygon else None,
        polygon_crs=polygon_crs,
        polygon_crs_datum=polygon_datum,
        country_code=location.country_code,
        display_name=location.display_name,
        nws_forecast_zone=nws.forecast_zone if nws else None,
        nws_county_zone=nws.county_zone if nws else None,
        nws_cwa=nws.cwa if nws else None,
        nws_time_zone=nws.time_zone if nws else None,
        nws_city=nws.city if nws else None,
        nws_state=nws.state if nws else None,
        breakpoint_span=dump(location.breakpoint_span) if location.breakpoint_span else None,
        evacuation_order_in_effect=location.evacuation_order_in_effect,
        evacuation_order_set_at=location.evacuation_order_set_at,
        geocoding=dump(location.geocoding) if location.geocoding else None,
        created_at=now,
        updated_at=now,
    )


def _location(row: LocationRow) -> Location:
    polygon = (
        with_crs(row.polygon, crs_from_columns(row.polygon_crs, row.polygon_crs_datum))
        if row.polygon is not None and row.polygon_crs is not None
        else None
    )
    nws = (
        NwsCoverage(
            forecast_zone=row.nws_forecast_zone,
            county_zone=cast("str", row.nws_county_zone),
            cwa=cast("str", row.nws_cwa),
            time_zone=cast("str", row.nws_time_zone),
            city=cast("str", row.nws_city),
            state=cast("str", row.nws_state),
        )
        if row.nws_forecast_zone is not None
        else None
    )
    return validated(
        Location,
        {
            "name": row.name,
            "point": LatLon(latitude=row.latitude, longitude=row.longitude),
            "polygon": polygon,
            "country_code": row.country_code,
            "display_name": row.display_name,
            "nws": nws,
            "breakpoint_span": row.breakpoint_span,
            "evacuation_order_in_effect": row.evacuation_order_in_effect,
            "evacuation_order_set_at": row.evacuation_order_set_at,
            "geocoding": row.geocoding,
        },
    )


class LocationRepository:
    """The watched locations, by name."""

    def __init__(self, engine: Engine, *, now: Clock = _now) -> None:
        """Create the repository.

        Args:
            engine: The open database.
            now: The clock, for created and updated times.
        """
        self._engine = engine
        self._now = now

    def add(self, location: Location) -> None:
        """Store a new location.

        Args:
            location: The location.

        Raises:
            LocationExistsError: A location of that name is stored.
        """
        with Session(self._engine) as session, session.begin():
            if session.scalar(select(LocationRow.id).where(LocationRow.name == location.name)):
                message = "a location of that name already exists"
                raise LocationExistsError(message)
            session.add(_location_row(location, self._now()))

    def list(self) -> tuple[Location, ...]:
        """Return every location, by name.

        Returns:
            The locations.
        """
        with Session(self._engine) as session:
            rows = session.scalars(select(LocationRow).order_by(LocationRow.name))
            return tuple(_location(row) for row in rows)

    def get(self, name: str) -> Location | None:
        """Return the location of a name.

        Args:
            name: The location's name.

        Returns:
            The location, or ``None``.
        """
        with Session(self._engine) as session:
            row = session.scalar(select(LocationRow).where(LocationRow.name == name))
            return _location(row) if row is not None else None

    def remove(self, name: str) -> bool:
        """Remove a location, its alert observations, and its assessments, in one transaction.

        Args:
            name: The location's name.

        Returns:
            Whether a location was removed.
        """
        with Session(self._engine) as session, session.begin():
            row = session.scalar(select(LocationRow).where(LocationRow.name == name))
            if row is None:
                return False
            # The database cascades to its alert observations and its assessments, and from
            # each assessment to its evidence and changes.
            session.delete(row)
            return True

    def set_evacuation_order(
        self, name: str, *, on: bool, at: datetime, session: Session | None = None
    ) -> Location | None:
        """Turn a location's evacuation-order toggle on or off, and record when.

        Args:
            name: The location's name.
            on: Whether the toggle is on.
            at: When it was set.
            session: A transaction to join; the write commits on its own without one.

        Returns:
            The updated location, or ``None`` when no location has that name.
        """
        with _writing(self._engine, session) as active:
            row = active.scalar(select(LocationRow).where(LocationRow.name == name))
            if row is None:
                return None
            row.evacuation_order_in_effect = on
            row.evacuation_order_set_at = at
            row.updated_at = self._now()
            active.flush()
            return _location(row)

    def set_breakpoint_span(
        self, name: str, span: BreakpointSpan | None, *, session: Session | None = None
    ) -> bool:
        """Replace a location's breakpoint span.

        Args:
            name: The location's name.
            span: The span, or ``None`` to clear it.
            session: A transaction to join; the write commits on its own without one.

        Returns:
            Whether a location of that name was updated.
        """
        with _writing(self._engine, session) as active:
            row = active.scalar(select(LocationRow).where(LocationRow.name == name))
            if row is None:
                return False
            row.breakpoint_span = dump(span) if span is not None else None
            row.updated_at = self._now()
            return True


# Snapshots ---------------------------------------------------------------------------------


def _storm_id(session: Session, summary: StormSummary, seen: datetime) -> int:
    row = session.scalar(select(StormRow).where(StormRow.atcf_id == summary.atcf_id))
    if row is None:
        row = StormRow(
            atcf_id=summary.atcf_id,
            name=summary.name,
            basin=summary.atcf_id[:2],
            first_seen=seen,
            last_seen=seen,
        )
        session.add(row)
    else:
        row.first_seen = min(row.first_seen, seen)
        if seen >= row.last_seen:
            row.name, row.last_seen = summary.name, seen
    session.flush()
    return row.id


def _advisory_id(
    session: Session, storm_ids: dict[str, int], atcf_id: str, advisory: Advisory | AdvisoryNumber
) -> int:
    number = advisory.number if isinstance(advisory, Advisory) else advisory
    stated = advisory if isinstance(advisory, Advisory) else None
    storm_id = storm_ids[atcf_id]
    row = session.scalar(
        select(AdvisoryRow).where(
            AdvisoryRow.storm_id == storm_id, AdvisoryRow.number == str(number)
        )
    )
    if row is None:
        row = AdvisoryRow(
            storm_id=storm_id,
            number=str(number),
            issued_at=stated.issued_at if stated else None,
            local_text=stated.local_text if stated else None,
        )
        session.add(row)
    elif stated is not None:
        row.issued_at = row.issued_at or stated.issued_at
        row.local_text = row.local_text or stated.local_text
    session.flush()
    return row.id


def _storm_records(products: StormProducts) -> Iterable[tuple[str, int, DomainModel]]:
    if products.cone is not None:
        yield "cone", 0, products.cone
    if products.track is not None:
        yield "track", 0, products.track
    groups: list[tuple[str, Sequence[DomainModel]]] = [
        ("track_point", products.track_points),
        ("watch_warning", products.watch_warnings),
        ("wind_radii", products.wind_radii),
        ("arrival_time", products.arrival_times),
    ]
    for kind, records in groups:
        for position, record in enumerate(records):
            yield kind, position, record


def _snapshot_records(snapshot: Snapshot) -> Iterable[tuple[str, int, DomainModel]]:
    groups: list[tuple[str, Sequence[DomainModel]]] = [
        ("outlook_area", snapshot.outlook_areas),
        ("wind_probability", snapshot.wind_probabilities),
        ("breakpoint", snapshot.breakpoints),
        ("display_layer", snapshot.display_layers),
        ("outlook_graphic", snapshot.outlook_graphics),
    ]
    for kind, records in groups:
        for position, record in enumerate(records):
            yield kind, position, record


type _Product = tuple[str, int, DomainModel, int | None]
"""A product to store: its kind, its position, the record, and its storm's advisory row."""


def _content_ids(session: Session, hashes: Iterable[str]) -> dict[str, int]:
    """The stored contents' ids, by SHA-256."""
    found = session.execute(
        select(GeometryContentRow.sha256, GeometryContentRow.id).where(
            GeometryContentRow.sha256.in_(list(hashes))
        )
    )
    return dict(found.all())


def _store_contents(session: Session, contents: Mapping[str, tuple[str, bytes]]) -> dict[str, int]:
    """Insert each content by its SHA-256, compressed, unless it is stored; return the ids."""
    ids = _content_ids(session, contents)
    missing = [sha256 for sha256 in contents if sha256 not in ids]
    if missing:
        inserting = insert(GeometryContentRow).on_conflict_do_nothing(index_elements=["sha256"])
        session.execute(
            inserting,
            [
                {
                    "sha256": sha256,
                    "product_kind": contents[sha256][0],
                    "size": len(contents[sha256][1]),
                    "body": zlib.compress(contents[sha256][1]),
                }
                for sha256 in missing
            ],
        )
        ids.update(_content_ids(session, missing))
    return ids


def _save_products(session: Session, snapshot_id: UUID, products: Sequence[_Product]) -> None:
    """Link each product to its content, stored once, and its provenance, once per snapshot."""
    contents: dict[str, tuple[str, bytes]] = {}
    provenances: dict[str, SnapshotProvenanceRow] = {}
    links: list[tuple[str, int, int | None, str, SnapshotProvenanceRow]] = []
    for kind, position, record, advisory_id in products:
        encoded = encode_product(kind, record)
        content = canonical_content(kind, encoded)
        sha256 = hashlib.sha256(content).hexdigest()
        contents.setdefault(sha256, (kind, content))
        key = json.dumps(encoded.provenance, sort_keys=True)
        if key not in provenances:
            provenances[key] = SnapshotProvenanceRow(
                snapshot_id=snapshot_id, position=len(provenances), provenance=encoded.provenance
            )
        links.append((kind, position, advisory_id, sha256, provenances[key]))
    content_ids = _store_contents(session, contents)
    session.add_all(provenances.values())
    session.flush()
    session.add_all(
        SnapshotGeometryRow(
            provenance_id=provenance.id,
            advisory_id=advisory_id,
            product_kind=kind,
            position=position,
            content_id=content_ids[sha256],
        )
        for kind, position, advisory_id, sha256, provenance in links
    )
    session.flush()


def _record_advisory(record: DomainModel) -> tuple[str, Advisory | AdvisoryNumber]:
    if isinstance(record, WindRadii):
        return record.atcf_id, record.advisory
    advised = cast("ConeGeometry", record)  # every other storm product is an AdvisoryRecord
    return advised.atcf_id, advised.advisory


class SnapshotRepository:
    """Every snapshot, stored whole and loaded back equal.

    A product's content (its kind, CRS, geometry, and fields) is stored once by its
    SHA-256 and shared by every snapshot that holds it, each distinct provenance once per
    snapshot, and one link per product (revision 0004); a snapshot stored before keeps its
    products in ``product_geometries`` and loads back as it was. A content row is never
    updated or deleted: removing a snapshot removes its provenances and their links, and a
    content that no snapshot links any more stays until Phase 7's retention.
    """

    def __init__(self, engine: Engine) -> None:
        """Create the repository.

        Args:
            engine: The open database.
        """
        self._engine = engine

    def save(
        self,
        snapshot: Snapshot,
        responses: Sequence[CachedFetch] = (),
        drift_warnings: Sequence[DriftWarning] = (),
    ) -> None:
        """Store a snapshot, its outcomes, and the answers behind them in one transaction.

        Args:
            snapshot: The snapshot.
            responses: Its sources' answers, each recorded once per body and linked to its
                source's outcome.
            drift_warnings: The Source-drift warnings its fetch logged, in order.

        Raises:
            SnapshotStoreError: The snapshot is a replay (history is live only), it is
                stored already, an answer's source has no outcome, or an alert names a
                location that is not stored.
        """
        if snapshot.origin != "live":
            message = "a replay snapshot is never stored: history is live only"
            raise SnapshotStoreError(message)
        with Session(self._engine) as session, session.begin():
            if session.get(SnapshotRow, snapshot.snapshot_id) is not None:
                message = "that snapshot is stored already"
                raise SnapshotStoreError(message)
            session.add(
                SnapshotRow(
                    id=snapshot.snapshot_id,
                    started_at=snapshot.started_at,
                    completed_at=snapshot.completed_at,
                    status=snapshot.status,
                )
            )
            session.flush()
            self._save_outcomes(session, snapshot, responses)
            products = [
                *self._save_storms(session, snapshot),
                *(
                    (kind, position, record, None)
                    for kind, position, record in _snapshot_records(snapshot)
                ),
            ]
            _save_products(session, snapshot.snapshot_id, products)
            self._save_text_products(session, snapshot)
            self._save_feed_items(session, snapshot)
            self._save_alerts(session, snapshot)
            session.add_all(
                DriftWarningRow(
                    snapshot_id=snapshot.snapshot_id,
                    position=position,
                    source_id=warning.source_id,
                    message=warning.message,
                )
                for position, warning in enumerate(drift_warnings)
            )

    @staticmethod
    def _save_outcomes(
        session: Session, snapshot: Snapshot, responses: Sequence[CachedFetch]
    ) -> None:
        outcomes: dict[str, SourceOutcomeRow] = {}
        for position, outcome in enumerate(snapshot.source_outcomes):
            row = SourceOutcomeRow(
                snapshot_id=snapshot.snapshot_id,
                position=position,
                source_id=outcome.source_id,
                status=outcome.status,
                error_kind=outcome.error_kind,
                reason=outcome.reason,
                fetched_at=None,
            )
            session.add(row)
            outcomes[outcome.source_id] = row
        session.flush()
        counts: dict[str, int] = defaultdict(int)
        for cached in responses:
            source = cached.result.source_id
            outcome_row = outcomes.get(source)
            if outcome_row is None:
                message = f"an answer from {source} has no outcome in the snapshot"
                raise SnapshotStoreError(message)
            raw = record_fetch(session, cached.result, cached.product_key, cached.issued_at)
            session.add(
                OutcomeResponseRow(
                    outcome_id=outcome_row.id, position=counts[source], raw_response_id=raw.id
                )
            )
            counts[source] += 1
            fetched = cached.result.fetched_at
            if outcome_row.fetched_at is None or fetched > outcome_row.fetched_at:
                outcome_row.fetched_at = fetched
        session.flush()

    @staticmethod
    def _save_storms(session: Session, snapshot: Snapshot) -> list[_Product]:
        """Store each storm and its advisories, and return its products to store."""
        storm_ids: dict[str, int] = {}
        stored: list[_Product] = []
        for position, products in enumerate(snapshot.storms):
            summary = cast("StormSummary", products.summary)  # a live storm's roster record
            storm_id = _storm_id(session, summary, snapshot.completed_at)
            storm_ids[summary.atcf_id] = storm_id
            session.add(
                StormObservationRow(
                    snapshot_id=snapshot.snapshot_id,
                    storm_id=storm_id,
                    position=position,
                    summary=dump(summary),
                )
            )
            for kind, index, record in _storm_records(products):
                atcf_id, advisory = _record_advisory(record)
                advisory_id = _advisory_id(session, storm_ids, atcf_id, advisory)
                stored.append((kind, index, record, advisory_id))
        session.flush()
        return stored

    @staticmethod
    def _save_text_products(session: Session, snapshot: Snapshot) -> None:
        for position, product in enumerate(snapshot.text_products):
            row = session.scalar(
                select(TextProductRow).where(TextProductRow.product_id == product.product_id)
            )
            if row is None:
                row = TextProductRow(
                    product_id=product.product_id,
                    code=product.code,
                    location=product.location,
                    wmo_collective_id=product.wmo_collective_id,
                    issuing_office=product.issuing_office,
                    issued_at=product.issued_at,
                    atcf_id=product.atcf_id,
                    advisory=str(product.advisory) if product.advisory else None,
                    text=product.text,
                )
                session.add(row)
                session.flush()
            session.add(
                TextProductObservationRow(
                    snapshot_id=snapshot.snapshot_id,
                    text_product_id=row.id,
                    position=position,
                    provenance=dump(product.provenance),
                )
            )
        session.flush()

    @staticmethod
    def _save_feed_items(session: Session, snapshot: Snapshot) -> None:
        seen = snapshot.completed_at
        for position, item in enumerate(snapshot.gis_feed_items):
            row = session.scalar(
                select(FeedItemRow).where(
                    FeedItemRow.feed == item.feed, FeedItemRow.guid == item.guid
                )
            )
            if row is None:
                row = FeedItemRow(guid=item.guid, feed=item.feed, first_seen=seen, last_seen=seen)
                session.add(row)
            else:
                row.first_seen = min(row.first_seen, seen)
            if seen >= row.last_seen:
                row.last_seen = seen
                row.title, row.link, row.published_at = item.title, item.link, item.published_at
                row.is_placeholder, row.atcf_id, row.slot = (
                    item.is_placeholder,
                    item.atcf_id,
                    item.slot,
                )
            session.flush()
            session.add(
                FeedItemObservationRow(
                    snapshot_id=snapshot.snapshot_id,
                    feed_item_id=row.id,
                    position=position,
                    item=dump(item),
                )
            )
        session.flush()

    @staticmethod
    def _save_alerts(session: Session, snapshot: Snapshot) -> None:
        seen = snapshot.completed_at
        for name, alerts in snapshot.alerts.items():
            location_id = session.scalar(select(LocationRow.id).where(LocationRow.name == name))
            if location_id is None:
                message = "a snapshot's alerts name a location that is not stored"
                raise SnapshotStoreError(message)
            if not alerts:
                session.add(
                    AlertObservationRow(
                        snapshot_id=snapshot.snapshot_id,
                        location_id=location_id,
                        alert_id=None,
                        position=0,
                        found_by=None,
                    )
                )
            for position, alert in enumerate(alerts):
                row = session.scalar(select(AlertRow).where(AlertRow.alert_id == alert.id))
                if row is None:
                    row = AlertRow(
                        alert_id=alert.id,
                        sent=alert.sent,
                        effective=alert.effective,
                        expires=alert.expires,
                        ends=alert.ends,
                        event=alert.event,
                        alert=dump(alert),
                        first_seen=seen,
                        last_seen=seen,
                    )
                    session.add(row)
                else:
                    row.first_seen = min(row.first_seen, seen)
                    row.last_seen = max(row.last_seen, seen)
                session.flush()
                session.add(
                    AlertObservationRow(
                        snapshot_id=snapshot.snapshot_id,
                        location_id=location_id,
                        alert_id=row.id,
                        position=position,
                        found_by=[dump(query) for query in alert.found_by],
                    )
                )
        session.flush()

    def latest_id(self) -> UUID | None:
        """Return the id of the snapshot that completed last, without loading it.

        Returns:
            The id, or ``None`` when none is stored.
        """
        with Session(self._engine) as session:
            return session.scalar(
                select(SnapshotRow.id)
                .order_by(SnapshotRow.completed_at.desc(), SnapshotRow.started_at.desc())
                .limit(1)
            )

    def latest(self) -> Snapshot | None:
        """Return the snapshot that completed last.

        Returns:
            The snapshot, or ``None`` when none is stored.
        """
        snapshot_id = self.latest_id()
        return self.load(snapshot_id) if snapshot_id is not None else None

    def drift_warnings(self, snapshot_id: UUID) -> tuple[DriftWarning, ...]:
        """Return the Source-drift warnings stored with a snapshot, in the order logged.

        Args:
            snapshot_id: The snapshot's id.

        Returns:
            The warnings; none for a snapshot that is not stored.
        """
        with Session(self._engine) as session:
            rows = session.scalars(
                select(DriftWarningRow)
                .where(DriftWarningRow.snapshot_id == snapshot_id)
                .order_by(DriftWarningRow.position)
            )
            return tuple(
                DriftWarning(source_id=cast("SourceId", row.source_id), message=row.message)
                for row in rows
            )

    def load(self, snapshot_id: UUID) -> Snapshot | None:
        """Load a stored snapshot back into an equal ``Snapshot``.

        Args:
            snapshot_id: The snapshot's id.

        Returns:
            The snapshot, or ``None`` when it is not stored.
        """
        with Session(self._engine) as session:
            return _load(session, snapshot_id)


def _decoded(row: ProductGeometryRow) -> DomainModel:
    return decode_product(
        row.product_kind,
        EncodedProduct(
            crs=row.crs,
            crs_datum=row.crs_datum,
            geojson=row.geojson,
            properties=row.properties,
            provenance=row.provenance,
        ),
    )


def _content(sha256: str, size: int, body: bytes) -> bytes:
    """Decompress a stored content, refusing one that is not what was stored."""
    inflater = zlib.decompressobj()
    content = inflater.decompress(body, size + 1)
    if len(content) != size or not inflater.eof:
        message = f"the stored content {sha256[:12]} is corrupt"
        raise CorruptBodyError(message)
    return content


def _links_products(session: Session, snapshot_id: UUID) -> bool:
    """Whether a snapshot's products are linked through ``snapshot_geometries``.

    A provenance row is written only for a linked product, so a snapshot has one exactly
    when it links its products.
    """
    linked = select(SnapshotProvenanceRow.id).where(
        SnapshotProvenanceRow.snapshot_id == snapshot_id
    )
    return session.scalar(linked.limit(1)) is not None


def _products(
    session: Session, snapshot_id: UUID, kinds: tuple[str, ...]
) -> list[tuple[str, str | None, DomainModel]]:
    """A snapshot's products of some kinds, in position order, each with its storm's id.

    A snapshot stored at revision 0004 or later links its products through
    ``snapshot_geometries``; one stored before keeps them in ``product_geometries``,
    decoded as revision 0003 decoded them. A snapshot never has both.
    """
    if not _links_products(session, snapshot_id):
        rows = session.execute(
            select(ProductGeometryRow, StormRow.atcf_id)
            .outerjoin(AdvisoryRow, AdvisoryRow.id == ProductGeometryRow.advisory_id)
            .outerjoin(StormRow, StormRow.id == AdvisoryRow.storm_id)
            .where(
                ProductGeometryRow.snapshot_id == snapshot_id,
                ProductGeometryRow.product_kind.in_(kinds),
            )
            .order_by(ProductGeometryRow.position)
        ).all()
        return [(row.product_kind, atcf_id, _decoded(row)) for row, atcf_id in rows]
    linked = session.execute(
        select(
            SnapshotGeometryRow.product_kind,
            StormRow.atcf_id,
            GeometryContentRow.sha256,
            GeometryContentRow.size,
            GeometryContentRow.body,
            SnapshotProvenanceRow.provenance,
        )
        .join(SnapshotProvenanceRow, SnapshotProvenanceRow.id == SnapshotGeometryRow.provenance_id)
        .join(GeometryContentRow, GeometryContentRow.id == SnapshotGeometryRow.content_id)
        .outerjoin(AdvisoryRow, AdvisoryRow.id == SnapshotGeometryRow.advisory_id)
        .outerjoin(StormRow, StormRow.id == AdvisoryRow.storm_id)
        .where(
            SnapshotProvenanceRow.snapshot_id == snapshot_id,
            SnapshotGeometryRow.product_kind.in_(kinds),
        )
        .order_by(SnapshotGeometryRow.position)
    ).all()
    return [
        (
            kind,
            atcf_id,
            decode_product(kind, from_content(_content(sha256, size, body), provenance)),
        )
        for kind, atcf_id, sha256, size, body, provenance in linked
    ]


def _storms(session: Session, snapshot_id: UUID) -> tuple[StormProducts, ...]:
    observed = session.execute(
        select(StormObservationRow.summary, StormRow.atcf_id)
        .join(StormRow, StormRow.id == StormObservationRow.storm_id)
        .where(StormObservationRow.snapshot_id == snapshot_id)
        .order_by(StormObservationRow.position)
    ).all()
    grouped: dict[tuple[str | None, str], list[DomainModel]] = defaultdict(list)
    for kind, atcf_id, record in _products(session, snapshot_id, _STORM_KINDS):
        grouped[atcf_id, kind].append(record)
    storms: list[StormProducts] = []
    for summary, atcf_id in observed:
        cones = grouped[atcf_id, "cone"]
        tracks = grouped[atcf_id, "track"]
        storms.append(
            StormProducts(
                summary=validated(StormSummary, summary),
                cone=cast("ConeGeometry", cones[0]) if cones else None,
                track=cast("ForecastTrack", tracks[0]) if tracks else None,
                track_points=cast("tuple[TrackPoint, ...]", tuple(grouped[atcf_id, "track_point"])),
                watch_warnings=cast(
                    "tuple[WatchWarningSegment, ...]", tuple(grouped[atcf_id, "watch_warning"])
                ),
                wind_radii=cast("tuple[WindRadii, ...]", tuple(grouped[atcf_id, "wind_radii"])),
                arrival_times=cast(
                    "tuple[ArrivalTimeProduct, ...]", tuple(grouped[atcf_id, "arrival_time"])
                ),
            )
        )
    return tuple(storms)


def _snapshot_products(session: Session, snapshot_id: UUID) -> dict[str, list[DomainModel]]:
    grouped: dict[str, list[DomainModel]] = defaultdict(list)
    for kind, _, record in _products(session, snapshot_id, _SNAPSHOT_KINDS):
        grouped[kind].append(record)
    return grouped


def _text_products(session: Session, snapshot_id: UUID) -> tuple[TextProduct, ...]:
    rows = session.execute(
        select(TextProductRow, TextProductObservationRow.provenance)
        .join(TextProductRow, TextProductRow.id == TextProductObservationRow.text_product_id)
        .where(TextProductObservationRow.snapshot_id == snapshot_id)
        .order_by(TextProductObservationRow.position)
    ).all()
    return tuple(
        validated(
            TextProduct,
            {
                "product_id": row.product_id,
                "code": row.code,
                "location": row.location,
                "wmo_collective_id": row.wmo_collective_id,
                "issuing_office": row.issuing_office,
                "issued_at": row.issued_at,
                "text": row.text,
                "atcf_id": row.atcf_id,
                "advisory": AdvisoryNumber.parse(row.advisory) if row.advisory else None,
                "provenance": provenance,
            },
        )
        for row, provenance in rows
    )


def _feed_items(session: Session, snapshot_id: UUID) -> tuple[GisFeedItem, ...]:
    items = session.scalars(
        select(FeedItemObservationRow.item)
        .where(FeedItemObservationRow.snapshot_id == snapshot_id)
        .order_by(FeedItemObservationRow.position)
    )
    return tuple(validated(GisFeedItem, item) for item in items)


def _alerts(session: Session, snapshot_id: UUID) -> dict[str, tuple[NwsAlert, ...]]:
    rows = session.execute(
        select(LocationRow.name, AlertRow.alert, AlertObservationRow.found_by)
        .join(LocationRow, LocationRow.id == AlertObservationRow.location_id)
        .outerjoin(AlertRow, AlertRow.id == AlertObservationRow.alert_id)
        .where(AlertObservationRow.snapshot_id == snapshot_id)
        .order_by(LocationRow.name, AlertObservationRow.position)
    ).all()
    alerts: dict[str, list[NwsAlert]] = {}
    for name, stored, found_by in rows:
        found = alerts.setdefault(name, [])
        alert = cast("Json | None", stored)  # None where the outer join found no alert
        if alert is not None:
            found.append(validated(NwsAlert, {**alert, "found_by": found_by}))
    return {name: tuple(found) for name, found in alerts.items()}


def _load(session: Session, snapshot_id: UUID) -> Snapshot | None:
    row = session.get(SnapshotRow, snapshot_id)
    if row is None:
        return None
    outcomes = session.scalars(
        select(SourceOutcomeRow)
        .where(SourceOutcomeRow.snapshot_id == snapshot_id)
        .order_by(SourceOutcomeRow.position)
    )
    products = _snapshot_products(session, snapshot_id)
    return Snapshot(
        snapshot_id=row.id,
        started_at=row.started_at,
        completed_at=row.completed_at,
        storms=_storms(session, snapshot_id),
        outlook_areas=cast("tuple[OutlookArea, ...]", tuple(products["outlook_area"])),
        wind_probabilities=cast(
            "tuple[WindProbabilityProduct, ...]", tuple(products["wind_probability"])
        ),
        text_products=_text_products(session, snapshot_id),
        gis_feed_items=_feed_items(session, snapshot_id),
        outlook_graphics=cast("tuple[OutlookGraphic, ...]", tuple(products["outlook_graphic"])),
        breakpoints=cast("tuple[Breakpoint, ...]", tuple(products["breakpoint"])),
        display_layers=cast("tuple[DisplayLayer, ...]", tuple(products["display_layer"])),
        alerts=_alerts(session, snapshot_id),
        source_outcomes=tuple(
            SourceOutcome.model_validate(
                {
                    "source_id": outcome.source_id,
                    "status": outcome.status,
                    "error_kind": outcome.error_kind,
                    "reason": outcome.reason,
                },
                strict=False,  # the source id and status come back from text columns
            )
            for outcome in outcomes
        ),
    )


# Assessments -------------------------------------------------------------------------------


@dataclass(frozen=True)
class StoredAssessment:
    """A stored assessment: its id, the assessment, its changes, and when it was stored.

    ``changes`` are the change events from the location's previous stored assessment.
    """

    id: int
    assessment: Assessment
    changes: tuple[ChangeEvent, ...]
    stored_at: datetime


def _evidence_rows(assessment_id: int, assessment: Assessment) -> list[AssessmentEvidenceRow]:
    rows = [
        AssessmentEvidenceRow(
            assessment_id=assessment_id,
            role="evidence",
            position=position,
            kind=item.product,
            rule=str(item.rule),
            source_id=item.source_id,
            code=item.code,
            distance_km=item.distance_km,
            covers=None,
        )
        for position, item in enumerate(assessment.evidence)
    ]
    rows.extend(
        AssessmentEvidenceRow(
            assessment_id=assessment_id,
            role="official",
            position=position,
            kind=product.kind,
            rule=str(product.rule) if product.rule is not None else None,
            source_id=product.citation.source_id,
            code=product.code,
            distance_km=product.distance_km,
            covers=product.covers,
        )
        for position, product in enumerate(assessment.official)
    )
    return rows


def _stored(session: Session, row: AssessmentRow) -> StoredAssessment:
    events = session.scalars(
        select(AssessmentChangeRow.event)
        .where(AssessmentChangeRow.assessment_id == row.id)
        .order_by(AssessmentChangeRow.position)
    )
    return StoredAssessment(
        id=row.id,
        assessment=validated(Assessment, row.assessment),
        changes=tuple(validated(ChangeEvent, event) for event in events),
        stored_at=row.stored_at,
    )


def _of_location(name: str) -> "Select[AssessmentRow]":
    """A location's assessments, newest first: by its snapshot's instant, then as stored."""
    return (
        select(AssessmentRow)
        .join(LocationRow, LocationRow.id == AssessmentRow.location_id)
        .where(LocationRow.name == name)
        .order_by(AssessmentRow.as_of.desc(), AssessmentRow.id.desc())
    )


class AssessmentRepository:
    """Every live assessment, with its evidence and its changes, stored whole by location."""

    def __init__(self, engine: Engine, *, now: Clock = _now) -> None:
        """Create the repository.

        Args:
            engine: The open database.
            now: The clock, for when an assessment is stored.
        """
        self._engine = engine
        self._now = now

    def save(
        self,
        assessment: Assessment,
        changes: Sequence[ChangeEvent],
        *,
        session: Session | None = None,
    ) -> StoredAssessment:
        """Store an assessment, a row per evidence record and official product, and its changes.

        Args:
            assessment: The assessment, of a live snapshot that is stored.
            changes: Its change events from the location's previous stored assessment.
            session: A transaction to join; the write commits on its own without one.

        Returns:
            The stored assessment.

        Raises:
            AssessmentStoreError: The assessment is a replay's (history is live only), its
                location or its snapshot is not stored, or it is stored already for that
                snapshot, location, and ruleset.
        """
        if assessment.origin != "live":
            message = "a replay assessment is never stored: history is live only"
            raise AssessmentStoreError(message)
        stored_at = self._now()
        with _writing(self._engine, session) as active:
            location_id = active.scalar(
                select(LocationRow.id).where(LocationRow.name == assessment.location_name)
            )
            if location_id is None:
                message = "the assessment names a location that is not stored"
                raise AssessmentStoreError(message)
            if active.get(SnapshotRow, assessment.snapshot_id) is None:
                message = "the assessment's snapshot is not stored"
                raise AssessmentStoreError(message)
            taken = active.scalar(
                select(AssessmentRow.id).where(
                    AssessmentRow.location_id == location_id,
                    AssessmentRow.snapshot_id == assessment.snapshot_id,
                    AssessmentRow.ruleset == assessment.ruleset,
                )
            )
            if taken is not None:
                message = "that assessment is stored already"
                raise AssessmentStoreError(message)
            row = AssessmentRow(
                location_id=location_id,
                snapshot_id=assessment.snapshot_id,
                ruleset=assessment.ruleset,
                as_of=assessment.as_of,
                level=int(assessment.level),
                rule=str(assessment.rule),
                complete=assessment.complete,
                thresholds=dump(assessment.thresholds),
                assessment=dump(assessment),
                stored_at=stored_at,
            )
            active.add(row)
            active.flush()
            active.add_all(_evidence_rows(row.id, assessment))
            active.add_all(
                AssessmentChangeRow(
                    assessment_id=row.id, position=position, kind=event.kind, event=dump(event)
                )
                for position, event in enumerate(changes)
            )
            active.flush()
            return StoredAssessment(row.id, assessment, tuple(changes), stored_at)

    def find(
        self,
        location_name: str,
        snapshot_id: UUID,
        ruleset: str,
        *,
        session: Session | None = None,
    ) -> StoredAssessment | None:
        """Return the assessment stored for a location, a snapshot, and a ruleset.

        Args:
            location_name: The location's name.
            snapshot_id: The snapshot's id.
            ruleset: The ruleset's fingerprint.
            session: A transaction to read in; a session of its own without one.

        Returns:
            The stored assessment, or ``None``.
        """
        statement = _of_location(location_name).where(
            AssessmentRow.snapshot_id == snapshot_id, AssessmentRow.ruleset == ruleset
        )
        with _reading(self._engine, session) as active:
            row = active.scalar(statement)
            return _stored(active, row) if row is not None else None

    def latest(
        self,
        location_name: str,
        *,
        at_or_before: datetime | None = None,
        session: Session | None = None,
    ) -> StoredAssessment | None:
        """Return a location's latest stored assessment, by its snapshot's instant.

        Args:
            location_name: The location's name.
            at_or_before: Only an assessment of a snapshot at or before this instant.
            session: A transaction to read in; a session of its own without one.

        Returns:
            The stored assessment, or ``None`` when none is stored.
        """
        statement = _of_location(location_name)
        if at_or_before is not None:
            statement = statement.where(AssessmentRow.as_of <= at_or_before)
        with _reading(self._engine, session) as active:
            row = active.scalar(statement.limit(1))
            return _stored(active, row) if row is not None else None

    def history(self, location_name: str, limit: int) -> tuple[StoredAssessment, ...]:
        """Return a location's stored assessments, newest first.

        Args:
            location_name: The location's name.
            limit: At most this many.

        Returns:
            The stored assessments.

        Raises:
            ValueError: The limit is below one.
        """
        if limit < 1:
            message = "a history holds at least one assessment"
            raise ValueError(message)
        with Session(self._engine) as session:
            rows = session.scalars(_of_location(location_name).limit(limit)).all()
            return tuple(_stored(session, row) for row in rows)

    def load(self, assessment_id: int) -> StoredAssessment | None:
        """Load a stored assessment back, equal to the one stored.

        Args:
            assessment_id: Its id.

        Returns:
            The stored assessment, or ``None`` when no assessment has that id.
        """
        with Session(self._engine) as session:
            row = session.get(AssessmentRow, assessment_id)
            return _stored(session, row) if row is not None else None


@contextmanager
def _reading(engine: Engine, session: Session | None) -> Generator[Session]:
    """Read in the caller's transaction, or in a session of its own."""
    if session is not None:
        yield session
        return
    with Session(engine) as own:
        yield own


# Settings ----------------------------------------------------------------------------------


class SettingsRepository:
    """Application state as JSON values by key, such as ``disclaimer_shown_at``."""

    def __init__(self, engine: Engine, *, now: Clock = _now) -> None:
        """Create the repository.

        Args:
            engine: The open database.
            now: The clock, for updated times.
        """
        self._engine = engine
        self._now = now

    def get(self, key: str) -> JsonValue | None:
        """Return a key's value.

        Args:
            key: The key.

        Returns:
            The value, or ``None`` when the key is not set.
        """
        with Session(self._engine) as session:
            row = session.get(SettingRow, key)
            return cast("JsonValue", row.value) if row is not None else None

    def set(self, key: str, value: JsonValue) -> None:
        """Set a key's value.

        Args:
            key: The key, at most 64 characters.
            value: Any JSON value.
        """
        with Session(self._engine) as session, session.begin():
            row = session.get(SettingRow, key)
            if row is None:
                session.add(SettingRow(key=key, value=value, updated_at=self._now()))
            else:
                row.value, row.updated_at = value, self._now()
