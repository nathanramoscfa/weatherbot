# tests/services/test_geometry_storage.py
"""Each product's content is stored once, and every snapshot still loads back equal.

Revision 0004 stores a product's content, everything but its provenance, once by its
SHA-256 in ``geometry_contents``, each distinct provenance once per snapshot, and one link
per product. The snapshots come from the recorded fixtures through the real parsers
(``snapshot_support``); the locations are the public landmarks. The assertions compare
models and count rows: nothing here prints a provenance, a URL, or a geometry.
"""

from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from pydantic import BaseModel
from snapshot_support import (
    LANDMARK_NAME,
    RecordedSnapshot,
    recorded_snapshot,
    with_second_storm,
)
from sqlalchemy import Engine, delete, distinct, func, select, update
from sqlalchemy.orm import Session

from weatherbot.models import (
    ArrivalTimeProduct,
    Breakpoint,
    ConeGeometry,
    DisplayLayer,
    DomainModel,
    ForecastTrack,
    OutlookArea,
    OutlookGraphic,
    Provenance,
    Snapshot,
    TrackPoint,
    WatchWarningSegment,
    WindProbabilityProduct,
    WindRadii,
)
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence import repositories
from weatherbot.services.persistence.codec import encode_product
from weatherbot.services.persistence.database import (
    Database,
    alembic_config,
    create_database_engine,
    open_database,
)
from weatherbot.services.persistence.raw_cache import CorruptBodyError
from weatherbot.services.persistence.repositories import LocationRepository, SnapshotRepository
from weatherbot.services.persistence.tables import (
    GeometryContentRow,
    ProductGeometryRow,
    SnapshotGeometryRow,
    SnapshotProvenanceRow,
    SnapshotRow,
)

pytestmark = pytest.mark.anyio

type Product = (
    ConeGeometry
    | ForecastTrack
    | TrackPoint
    | WatchWarningSegment
    | WindRadii
    | ArrivalTimeProduct
    | OutlookArea
    | WindProbabilityProduct
    | Breakpoint
    | DisplayLayer
    | OutlookGraphic
)


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


@pytest.fixture
async def recorded() -> RecordedSnapshot:
    return await recorded_snapshot()


def _count(database: Database, model: type[object]) -> int:
    with Session(database.engine) as session:
        return session.scalar(select(func.count()).select_from(model)) or 0  # pyright: ignore[reportArgumentType] - a mapped class


def _records(snapshot: Snapshot) -> list[Product]:
    """Every product a snapshot links, its storms' first."""
    storms = [
        record
        for storm in snapshot.storms
        for record in (
            storm.cone,
            storm.track,
            *storm.track_points,
            *storm.watch_warnings,
            *storm.wind_radii,
            *storm.arrival_times,
        )
        if record is not None
    ]
    return [
        *storms,
        *snapshot.outlook_areas,
        *snapshot.wind_probabilities,
        *snapshot.breakpoints,
        *snapshot.display_layers,
        *snapshot.outlook_graphics,
    ]


def _refetched(value: object, at: datetime) -> object:
    """A value with every provenance inside it fetched at ``at``, and nothing else changed."""
    if isinstance(value, Provenance):
        return value.model_copy(update={"fetched_at": at})
    if isinstance(value, BaseModel):
        names = type(value).model_fields
        return value.model_copy(
            update={name: _refetched(getattr(value, name), at) for name in names}
        )
    if isinstance(value, tuple):
        return tuple(_refetched(item, at) for item in cast("tuple[object, ...]", value))
    if isinstance(value, dict):
        items = cast("dict[object, object]", value).items()
        return {key: _refetched(item, at) for key, item in items}
    return value


def _later(snapshot: Snapshot, minutes: int) -> Snapshot:
    """The same products fetched again, minutes later, as another snapshot."""
    later = snapshot.completed_at + timedelta(minutes=minutes)
    refetched = cast("Snapshot", _refetched(snapshot, later))
    return refetched.model_copy(
        update={
            "snapshot_id": UUID(int=snapshot.snapshot_id.int + minutes),
            "started_at": later,
            "completed_at": later,
        }
    )


# Saved at 0004 ------------------------------------------------------------------------------


async def test_a_recorded_snapshot_saved_at_0004_loads_back_equal(
    database: Database, recorded: RecordedSnapshot
) -> None:
    snapshot = recorded.snapshot
    records = _records(snapshot)
    LocationRepository(database.engine).add(recorded.location)
    repository = SnapshotRepository(database.engine)

    repository.save(snapshot, recorded.responses)

    assert repository.load(snapshot.snapshot_id) == snapshot
    assert _count(database, ProductGeometryRow) == 0
    assert _count(database, SnapshotGeometryRow) == len(records)
    assert 0 < _count(database, GeometryContentRow) <= len(records)
    distinct_provenances = len({r.provenance.model_dump_json() for r in records})
    assert _count(database, SnapshotProvenanceRow) == distinct_provenances


async def test_a_snapshot_with_two_active_storms_loads_back_equal(
    database: Database, recorded: RecordedSnapshot
) -> None:
    snapshot = with_second_storm(recorded.snapshot)
    LocationRepository(database.engine).add(recorded.location)
    repository = SnapshotRepository(database.engine)

    repository.save(snapshot, recorded.responses)

    loaded = repository.load(snapshot.snapshot_id)
    assert loaded == snapshot
    assert loaded is not None
    for stored, storm in zip(loaded.storms, snapshot.storms, strict=True):
        assert stored.summary == storm.summary
        assert stored.track_points == storm.track_points
        assert stored.wind_radii == storm.wind_radii
    # Positions restart for each storm, so the two storms' products share positions.
    with Session(database.engine) as session:
        shared = session.execute(
            select(SnapshotGeometryRow.product_kind, SnapshotGeometryRow.position)
            .group_by(SnapshotGeometryRow.product_kind, SnapshotGeometryRow.position)
            .having(func.count(distinct(SnapshotGeometryRow.advisory_id)) > 1)
        ).all()
    assert {("cone", 0), ("track", 0), ("track_point", 0), ("wind_radii", 0)} <= set(shared)


async def test_two_snapshots_of_the_same_products_share_every_content_row(
    database: Database, recorded: RecordedSnapshot
) -> None:
    first = recorded.snapshot
    second = _later(first, minutes=15)
    LocationRepository(database.engine).add(recorded.location)
    repository = SnapshotRepository(database.engine)
    repository.save(first, recorded.responses)
    contents = _count(database, GeometryContentRow)
    links = _count(database, SnapshotGeometryRow)
    provenances = _count(database, SnapshotProvenanceRow)

    repository.save(second, recorded.responses)

    assert _count(database, GeometryContentRow) == contents
    assert _count(database, SnapshotGeometryRow) == 2 * links
    assert _count(database, SnapshotProvenanceRow) == 2 * provenances
    assert repository.load(first.snapshot_id) == first
    loaded = repository.load(second.snapshot_id)
    assert loaded == second
    assert loaded is not None
    assert {r.provenance.fetched_at for r in _records(loaded)} == {second.completed_at}


async def test_the_records_of_one_response_share_one_provenance_row(
    database: Database, recorded: RecordedSnapshot
) -> None:
    snapshot = recorded.snapshot
    LocationRepository(database.engine).add(recorded.location)

    SnapshotRepository(database.engine).save(snapshot, recorded.responses)

    # The breakpoint catalogue's points (549 in the recording) come from one response.
    with Session(database.engine) as session:
        links, provenances = session.execute(
            select(func.count(), func.count(distinct(SnapshotGeometryRow.provenance_id))).where(
                SnapshotGeometryRow.product_kind == "breakpoint"
            )
        ).one()
    assert len(snapshot.breakpoints) > 1
    assert (links, provenances) == (len(snapshot.breakpoints), 1)


# Stored before 0004 -------------------------------------------------------------------------


def _at_revision(paths: AppPaths, revision: str) -> Engine:
    """A new database migrated to ``revision``."""
    paths.data_dir.mkdir(parents=True)
    engine = create_database_engine(paths.database_path)
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), revision)
    return engine


def _written_as_before(
    session: Session,
    snapshot_id: UUID,
    products: Sequence[tuple[str, int, DomainModel, int | None]],
) -> None:
    """The writer before revision 0004: every product into ``product_geometries``."""
    for kind, position, record, advisory_id in products:
        encoded = encode_product(kind, record)
        session.add(
            ProductGeometryRow(
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
        )


async def test_a_snapshot_stored_before_0004_loads_back_equal_after_the_upgrade(
    recorded: RecordedSnapshot, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = AppPaths.resolve()
    old = recorded.snapshot
    engine = _at_revision(paths, "0003")
    with monkeypatch.context() as patched:
        patched.setattr(repositories, "_save_products", _written_as_before)
        LocationRepository(engine).add(recorded.location)
        SnapshotRepository(engine).save(old, recorded.responses)
    engine.dispose()

    with open_database(paths) as opened:
        assert opened.backup_path is not None
        repository = SnapshotRepository(opened.engine)
        new = _later(old, minutes=15)
        repository.save(new, recorded.responses)

        assert repository.load(old.snapshot_id) == old
        assert repository.load(new.snapshot_id) == new
        assert _count(opened, ProductGeometryRow) == len(_records(old))
        assert _count(opened, SnapshotGeometryRow) == len(_records(new))


# Removal ------------------------------------------------------------------------------------


async def test_removing_a_location_or_a_snapshot_never_removes_a_content(
    database: Database, recorded: RecordedSnapshot
) -> None:
    snapshot = recorded.snapshot
    LocationRepository(database.engine).add(recorded.location)
    SnapshotRepository(database.engine).save(snapshot, recorded.responses)
    contents = _count(database, GeometryContentRow)
    links = _count(database, SnapshotGeometryRow)

    assert LocationRepository(database.engine).remove(LANDMARK_NAME)

    assert _count(database, GeometryContentRow) == contents
    assert _count(database, SnapshotGeometryRow) == links
    with Session(database.engine) as session, session.begin():
        session.execute(delete(SnapshotRow))
    assert _count(database, SnapshotProvenanceRow) == 0
    assert _count(database, SnapshotGeometryRow) == 0
    assert _count(database, GeometryContentRow) == contents


async def test_a_corrupt_content_is_refused_on_load(
    database: Database, recorded: RecordedSnapshot
) -> None:
    snapshot = recorded.snapshot
    LocationRepository(database.engine).add(recorded.location)
    repository = SnapshotRepository(database.engine)
    repository.save(snapshot, recorded.responses)
    with Session(database.engine) as session, session.begin():
        session.execute(update(GeometryContentRow).values(size=GeometryContentRow.size + 1))

    with pytest.raises(CorruptBodyError, match="is corrupt"):
        repository.load(snapshot.snapshot_id)
