# tests/services/test_repositories.py
"""The repositories store the domain models and give them back unchanged.

The snapshot comes from the recorded fixtures through the real parsers
(``snapshot_support``); the locations are the public landmarks.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from snapshot_support import (
    LANDMARK_NAME,
    RecordedSnapshot,
    landmark_location,
    recorded_snapshot,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from weatherbot.models import (
    WGS84,
    BreakpointSpan,
    Crs,
    Geometry,
    Snapshot,
    SourceOutcome,
)
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import (
    LocationExistsError,
    LocationRepository,
    SettingsRepository,
    SnapshotRepository,
    SnapshotStoreError,
)
from weatherbot.services.persistence.tables import (
    AlertObservationRow,
    AlertRow,
    OutcomeResponseRow,
    RawResponseRow,
    ResponseBodyRow,
    StormRow,
)

pytestmark = pytest.mark.anyio


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


# Snapshots ---------------------------------------------------------------------------------


async def test_a_recorded_snapshot_is_saved_and_loaded_back_equal(
    database: Database, recorded: RecordedSnapshot
) -> None:
    snapshot = recorded.snapshot
    assert snapshot.storms, "the recorded roster has an active storm"
    assert snapshot.storms[0].cone is not None
    assert any(p.origin == "kmz" for s in snapshot.storms for p in s.arrival_times)
    assert snapshot.alerts[LANDMARK_NAME], "the 2026-10-17 capture holds an alert"
    sections = (
        snapshot.outlook_areas,
        snapshot.wind_probabilities,
        snapshot.text_products,
        snapshot.gis_feed_items,
        snapshot.outlook_graphics,
        snapshot.breakpoints,
        snapshot.display_layers,
    )
    assert all(sections), "every part of the snapshot holds records"
    LocationRepository(database.engine).add(recorded.location)
    repository = SnapshotRepository(database.engine)

    repository.save(snapshot, recorded.responses)

    assert repository.load(snapshot.snapshot_id) == snapshot
    assert repository.latest() == snapshot


async def test_every_answer_is_linked_to_its_outcome_and_bodies_are_stored_once(
    database: Database, recorded: RecordedSnapshot
) -> None:
    LocationRepository(database.engine).add(recorded.location)
    SnapshotRepository(database.engine).save(recorded.snapshot, recorded.responses)

    distinct_bodies = {cached.result.sha256 for cached in recorded.responses}
    assert _count(database, OutcomeResponseRow) == len(recorded.responses)
    assert _count(database, ResponseBodyRow) == len(distinct_bodies)
    assert _count(database, RawResponseRow) <= len(recorded.responses)


async def test_a_second_snapshot_reuses_the_stored_records(
    database: Database, recorded: RecordedSnapshot
) -> None:
    LocationRepository(database.engine).add(recorded.location)
    repository = SnapshotRepository(database.engine)
    first = recorded.snapshot
    later = first.completed_at + timedelta(hours=1)
    second = first.model_copy(
        update={
            "snapshot_id": UUID(int=first.snapshot_id.int + 1),
            "started_at": later,
            "completed_at": later,
        }
    )

    repository.save(first, recorded.responses)
    repository.save(second, recorded.responses)

    assert repository.load(first.snapshot_id) == first
    assert repository.load(second.snapshot_id) == second
    assert repository.latest() == second
    assert _count(database, StormRow) == len(first.storms)
    assert _count(database, AlertRow) == len(first.alerts[LANDMARK_NAME])
    assert _count(database, RawResponseRow) == len(
        {(c.result.source_id, c.product_key, c.result.sha256) for c in recorded.responses}
    )


def test_an_unknown_snapshot_loads_as_none(database: Database) -> None:
    repository = SnapshotRepository(database.engine)

    assert repository.latest() is None
    assert repository.load(UUID(int=7)) is None


def _minimal(snapshot_id: int = 1, **update: object) -> Snapshot:
    now = datetime(2026, 10, 17, 12, tzinfo=UTC)
    fields: dict[str, object] = {
        "snapshot_id": UUID(int=snapshot_id),
        "started_at": now,
        "completed_at": now,
        "source_outcomes": (
            SourceOutcome(source_id="nhc-current-storms", status="ok"),
            SourceOutcome(source_id="nws-alerts-point", status="failed", error_kind="timeout"),
        ),
    }
    return Snapshot.model_validate({**fields, **update})


def test_an_empty_alert_list_is_kept_apart_from_a_location_not_asked(database: Database) -> None:
    LocationRepository(database.engine).add(landmark_location())
    repository = SnapshotRepository(database.engine)
    asked = _minimal(1, alerts={LANDMARK_NAME: ()})
    not_asked = _minimal(2)

    repository.save(asked)
    repository.save(not_asked)

    assert repository.load(asked.snapshot_id) == asked
    assert repository.load(not_asked.snapshot_id) == not_asked
    loaded = repository.load(asked.snapshot_id)
    assert loaded is not None
    assert loaded.status == "partial"


def test_a_snapshot_is_stored_once(database: Database) -> None:
    repository = SnapshotRepository(database.engine)
    repository.save(_minimal())

    with pytest.raises(SnapshotStoreError, match="stored already"):
        repository.save(_minimal())


def test_alerts_for_a_location_that_is_not_stored_are_refused(database: Database) -> None:
    with pytest.raises(SnapshotStoreError, match="not stored"):
        SnapshotRepository(database.engine).save(_minimal(alerts={LANDMARK_NAME: ()}))
    assert SnapshotRepository(database.engine).latest() is None


async def test_an_answer_without_an_outcome_is_refused_and_nothing_is_saved(
    database: Database, recorded: RecordedSnapshot
) -> None:
    roster = next(c for c in recorded.responses if c.result.source_id == "nhc-current-storms")
    stray = next(c for c in recorded.responses if c.result.source_id == "nhc-gis-rss")

    with pytest.raises(SnapshotStoreError, match="no outcome"):
        SnapshotRepository(database.engine).save(_minimal(), (roster, stray))
    assert SnapshotRepository(database.engine).latest() is None
    assert _count(database, RawResponseRow) == 0


# Locations ---------------------------------------------------------------------------------


def _square(crs: Crs) -> Geometry:
    lat, lon = landmark_location().point.latitude, landmark_location().point.longitude
    ring = ((lon, lat), (lon + 0.01, lat), (lon + 0.01, lat + 0.01), (lon, lat))
    return Geometry(type="Polygon", coordinates=(ring,), crs=crs)


@pytest.mark.parametrize(
    "crs",
    [WGS84, Crs(name="native", wkt='GEOGCS["GCS_Sphere"]', datum="D_Sphere")],
    ids=["epsg-4326", "native"],
)
def test_a_location_round_trips_with_its_polygon_and_crs(database: Database, crs: Crs) -> None:
    location = landmark_location().model_copy(
        update={"polygon": _square(crs), "country_code": "US", "display_name": "County Hall"}
    )
    repository = LocationRepository(database.engine)

    repository.add(location)

    assert repository.get(LANDMARK_NAME) == location
    assert repository.list() == (location,)


def test_a_location_round_trips_with_its_breakpoint_span(database: Database) -> None:
    span = BreakpointSpan(
        names=("Ocean Reef", "Miami-Dade/Broward County Line"),
        country="United States",
        is_region=False,
        catalog_loaded_at=datetime(2026, 4, 30, 18, 42, 35, tzinfo=UTC),
    )
    spanned = landmark_location().model_copy(update={"breakpoint_span": span})
    bare = landmark_location().model_copy(update={"name": "No span"})
    repository = LocationRepository(database.engine)

    repository.add(spanned)
    repository.add(bare)

    assert repository.get(LANDMARK_NAME) == spanned
    assert repository.get("No span") == bare
    assert bare.breakpoint_span is None


async def test_a_covered_location_round_trips_with_its_coverage(
    database: Database, recorded: RecordedSnapshot
) -> None:
    repository = LocationRepository(database.engine)

    repository.add(recorded.location)

    assert repository.get(recorded.location.name) == recorded.location


def test_locations_are_listed_by_name_and_names_are_unique(database: Database) -> None:
    repository = LocationRepository(database.engine)
    second = landmark_location().model_copy(update={"name": "A second name"})
    repository.add(landmark_location())
    repository.add(second)

    with pytest.raises(LocationExistsError):
        repository.add(landmark_location())
    assert [location.name for location in repository.list()] == ["A second name", LANDMARK_NAME]
    assert repository.get("missing") is None


async def test_removing_a_location_deletes_its_alert_observations_and_nothing_else(
    database: Database, recorded: RecordedSnapshot
) -> None:
    locations = LocationRepository(database.engine)
    other = recorded.location.model_copy(update={"name": "Other"})
    locations.add(recorded.location)
    locations.add(other)
    snapshot = recorded.snapshot.model_copy(
        update={"alerts": {**recorded.snapshot.alerts, "Other": ()}}
    )
    snapshots = SnapshotRepository(database.engine)
    snapshots.save(snapshot, recorded.responses)
    alerts_before = _count(database, AlertRow)

    assert locations.remove(LANDMARK_NAME)

    assert not locations.remove(LANDMARK_NAME)
    assert locations.list() == (other,)
    assert _count(database, AlertRow) == alerts_before
    assert _count(database, AlertObservationRow) == 1
    loaded = snapshots.load(snapshot.snapshot_id)
    assert loaded is not None
    assert loaded.alerts == {"Other": ()}
    assert loaded.model_copy(update={"alerts": snapshot.alerts}) == snapshot


def test_the_toggle_and_the_span_are_updated_in_place(database: Database) -> None:
    repository = LocationRepository(database.engine)
    repository.add(landmark_location())
    span = BreakpointSpan(names=("Bahamas (NW)",), country="Bahamas", is_region=True)
    at = datetime(2026, 10, 20, 12, tzinfo=UTC)

    toggled = repository.set_evacuation_order(LANDMARK_NAME, on=True, at=at)
    assert repository.set_breakpoint_span(LANDMARK_NAME, span)

    stored = repository.get(LANDMARK_NAME)
    assert toggled is not None
    assert (toggled.evacuation_order_in_effect, toggled.evacuation_order_set_at) == (True, at)
    assert stored is not None
    assert (stored.breakpoint_span, stored.evacuation_order_set_at) == (span, at)
    assert repository.set_breakpoint_span(LANDMARK_NAME, None)
    assert repository.get(LANDMARK_NAME) == toggled
    assert repository.set_evacuation_order("missing", on=True, at=at) is None
    assert not repository.set_breakpoint_span("missing", span)


# Settings ----------------------------------------------------------------------------------


def test_settings_store_json_values_by_key(database: Database) -> None:
    clock = iter([datetime(2026, 10, 17, 12, tzinfo=UTC), datetime(2026, 10, 17, 13, tzinfo=UTC)])
    repository = SettingsRepository(database.engine, now=lambda: next(clock))

    assert repository.get("disclaimer_shown_at") is None
    repository.set("disclaimer_shown_at", "2026-10-17T12:00:00Z")
    repository.set("disclaimer_shown_at", {"at": "2026-10-17T13:00:00Z", "version": 1})

    assert repository.get("disclaimer_shown_at") == {"at": "2026-10-17T13:00:00Z", "version": 1}
