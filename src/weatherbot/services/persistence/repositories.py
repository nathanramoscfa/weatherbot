# src/weatherbot/services/persistence/repositories.py
"""Repositories: the domain models in, the same models out.

``LocationRepository`` keeps the watched locations, ``SnapshotRepository`` stores a whole
``Snapshot`` with its raw responses in one transaction and loads it back equal, and
``SettingsRepository`` keeps application state such as when the disclaimer was shown.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, cast
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from weatherbot.models import (
    Advisory,
    AdvisoryNumber,
    ArrivalTimeProduct,
    Breakpoint,
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
    crs_columns,
    crs_from_columns,
    decode_product,
    dump,
    encode_product,
    geojson,
    validated,
    with_crs,
)
from weatherbot.services.persistence.raw_cache import CachedFetch, record_fetch
from weatherbot.services.persistence.tables import (
    AdvisoryRow,
    AlertObservationRow,
    AlertRow,
    DriftWarningRow,
    FeedItemObservationRow,
    FeedItemRow,
    LocationRow,
    OutcomeResponseRow,
    ProductGeometryRow,
    SettingRow,
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


@dataclass(frozen=True)
class DriftWarning:
    """A Source-drift warning a fetch logged: its source and a coordinate-free message."""

    source_id: SourceId
    message: str


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
        breakpoint_span=None,
        evacuation_order_in_effect=location.evacuation_order_in_effect,
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
        """Remove a location and its alert observations, and nothing else.

        Args:
            name: The location's name.

        Returns:
            Whether a location was removed.
        """
        with Session(self._engine) as session, session.begin():
            row = session.scalar(select(LocationRow).where(LocationRow.name == name))
            if row is None:
                return False
            session.delete(row)  # the database cascades to its alert observations
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


def _product_row(
    snapshot_id: UUID, kind: str, position: int, record: DomainModel, advisory_id: int | None
) -> ProductGeometryRow:
    encoded = encode_product(kind, record)
    return ProductGeometryRow(
        snapshot_id=snapshot_id,
        advisory_id=advisory_id,
        product_kind=kind,
        position=position,
        crs=encoded.crs,
        crs_datum=encoded.crs_datum,
        geojson=encoded.geojson,
        properties=encoded.properties,
        provenance=encoded.provenance,
    )


def _record_advisory(record: DomainModel) -> tuple[str, Advisory | AdvisoryNumber]:
    if isinstance(record, WindRadii):
        return record.atcf_id, record.advisory
    advised = cast("ConeGeometry", record)  # every other storm product is an AdvisoryRecord
    return advised.atcf_id, advised.advisory


class SnapshotRepository:
    """Every snapshot, stored whole and loaded back equal."""

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
            SnapshotStoreError: The snapshot is stored already, an answer's source has no
                outcome, or an alert names a location that is not stored.
        """
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
            self._save_storms(session, snapshot)
            for kind, position, record in _snapshot_records(snapshot):
                session.add(_product_row(snapshot.snapshot_id, kind, position, record, None))
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
    def _save_storms(session: Session, snapshot: Snapshot) -> None:
        storm_ids: dict[str, int] = {}
        for position, products in enumerate(snapshot.storms):
            summary = products.summary
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
                session.add(_product_row(snapshot.snapshot_id, kind, index, record, advisory_id))
        session.flush()

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


def _storms(session: Session, snapshot_id: UUID) -> tuple[StormProducts, ...]:
    observed = session.execute(
        select(StormObservationRow.summary, StormRow.atcf_id)
        .join(StormRow, StormRow.id == StormObservationRow.storm_id)
        .where(StormObservationRow.snapshot_id == snapshot_id)
        .order_by(StormObservationRow.position)
    ).all()
    rows = session.execute(
        select(ProductGeometryRow, StormRow.atcf_id)
        .join(AdvisoryRow, AdvisoryRow.id == ProductGeometryRow.advisory_id)
        .join(StormRow, StormRow.id == AdvisoryRow.storm_id)
        .where(
            ProductGeometryRow.snapshot_id == snapshot_id,
            ProductGeometryRow.product_kind.in_(_STORM_KINDS),
        )
        .order_by(ProductGeometryRow.position)
    ).all()
    grouped: dict[tuple[str, str], list[DomainModel]] = defaultdict(list)
    for row, atcf_id in rows:
        grouped[atcf_id, row.product_kind].append(_decoded(row))
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
    rows = session.scalars(
        select(ProductGeometryRow)
        .where(
            ProductGeometryRow.snapshot_id == snapshot_id,
            ProductGeometryRow.product_kind.in_(_SNAPSHOT_KINDS),
        )
        .order_by(ProductGeometryRow.position)
    )
    grouped: dict[str, list[DomainModel]] = defaultdict(list)
    for row in rows:
        grouped[row.product_kind].append(_decoded(row))
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
