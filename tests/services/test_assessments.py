# tests/services/test_assessments.py
"""The assessment service stores each location's assessment, its evidence, and its changes.

The live snapshot is the recorded one (``snapshot_support``), stored first as ``status``
stores it; the locations are the public landmarks. A later snapshot is the same records
under a new id and a later instant.
"""

from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID

import pytest
from fixture_support import REPOSITORY_ROOT
from snapshot_support import (
    LANDMARK_NAME,
    RecordedSnapshot,
    landmark_point,
    recorded_snapshot,
)
from source_support import NOW
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from weatherbot.engine import assess
from weatherbot.models import (
    AlertLevel,
    Assessment,
    LatLon,
    Location,
    RuleId,
    Snapshot,
    Thresholds,
)
from weatherbot.services.assessments import (
    AssessedLocation,
    AssessmentError,
    AssessmentService,
    is_county_context,
    official_products,
)
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    AssessmentStoreError,
    LocationRepository,
    SnapshotRepository,
)
from weatherbot.services.persistence.tables import (
    AssessmentChangeRow,
    AssessmentEvidenceRow,
    AssessmentRow,
)
from weatherbot.services.replay import ReplayCorpus

pytestmark = pytest.mark.anyio

NASSAU_NAME = "Parliament Square"
REPLAY = REPOSITORY_ROOT / "tests" / "fixtures" / "replay"
TABLES = (AssessmentRow, AssessmentEvidenceRow, AssessmentChangeRow)


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


@pytest.fixture
async def recorded() -> RecordedSnapshot:
    return await recorded_snapshot()


def _nassau() -> Location:
    lat, lon = landmark_point("nassau")
    return Location(name=NASSAU_NAME, point=LatLon(latitude=lat, longitude=lon))


def _stored(database: Database, recorded: RecordedSnapshot) -> tuple[Location, ...]:
    """Store both landmarks and the recorded snapshot, as ``status`` finds them."""
    locations = LocationRepository(database.engine)
    locations.add(recorded.location)
    locations.add(_nassau())
    SnapshotRepository(database.engine).save(recorded.snapshot, recorded.responses)
    return locations.list()


def _later(snapshot: Snapshot, number: int, **changes: object) -> Snapshot:
    """The same records as a later snapshot: a new id, ``number`` half-hours on."""
    fields = {name: getattr(snapshot, name) for name in Snapshot.model_fields}
    at = snapshot.completed_at + timedelta(minutes=30 * number)
    moved = {"snapshot_id": UUID(int=number), "started_at": at, "completed_at": at}
    return Snapshot.model_validate(fields | moved | changes)


def _service(database: Database, minutes: int = 0) -> AssessmentService:
    stamp = NOW + timedelta(minutes=minutes)
    return AssessmentService(database.engine, thresholds=Thresholds(), now=lambda: stamp)


def _counts(database: Database) -> tuple[int, ...]:
    with Session(database.engine) as session:
        return tuple(
            session.scalar(select(func.count()).select_from(table)) or 0  # pyright: ignore[reportArgumentType] - a mapped class
            for table in TABLES
        )


def _by_name(results: tuple[AssessedLocation, ...]) -> dict[str, Assessment]:
    return {item.location.name: item.stored.assessment for item in results}


# One run -----------------------------------------------------------------------------------


async def test_every_location_is_assessed_and_stored_with_its_evidence_and_changes(
    database: Database, recorded: RecordedSnapshot
) -> None:
    locations = _stored(database, recorded)

    results = _service(database).assess(recorded.snapshot, locations)

    assessed = _by_name(results)
    assert set(assessed) == {LANDMARK_NAME, NASSAU_NAME}
    assert all(item.created for item in results)
    miami = assessed[LANDMARK_NAME]
    assert (miami.level, miami.rule, miami.origin) == (
        AlertLevel.ALL_CLEAR,
        RuleId.ALL_CLEAR,
        "live",
    )
    # The recorded Rip Current Statement covers the landmark and sets no level (issue #10).
    (rip,) = miami.official
    assert (rip.code, rip.covers, rip.rule) == ("Rip Current Statement", True, None)
    # The arrival-time stand-in has no cone and no points: the level reads as a floor.
    assert not miami.complete
    assert {item.kind for item in miami.unavailable} == {"cone", "forecast_points"}
    repository = AssessmentRepository(database.engine)
    for item in results:
        loaded = repository.load(item.stored.id)
        assert loaded == item.stored
        assert loaded is not None
        assert loaded.assessment == item.stored.assessment
        first = loaded.changes[0]
        assert (first.kind, first.direction) == ("level_changed", "initial")
        # The initial events: the level, each storm's advisory, each covering product.
        covering = {"official_added"} if item.location.name == LANDMARK_NAME else set[str]()
        kinds = {event.kind for event in loaded.changes}
        assert kinds == {"level_changed", "advisory_issued"} | covering
    evidence_rows, change_rows = _counts(database)[1:]
    assert evidence_rows == sum(len(a.evidence) + len(a.official) for a in assessed.values())
    assert change_rows == sum(len(item.stored.changes) for item in results)


async def test_the_breakpoint_span_is_filled_from_the_snapshot_catalogue(
    database: Database, recorded: RecordedSnapshot
) -> None:
    locations = _stored(database, recorded)
    assert all(location.breakpoint_span is None for location in locations)

    results = _service(database).assess(recorded.snapshot, locations)

    stored = {location.name: location for location in LocationRepository(database.engine).list()}
    miami = stored[LANDMARK_NAME].breakpoint_span
    nassau = stored[NASSAU_NAME].breakpoint_span
    assert miami is not None
    assert nassau is not None
    assert miami.names == ("Ocean Reef", "Miami-Dade/Broward County Line")
    assert (miami.country, miami.is_region) == ("United States", False)
    assert nassau.is_region
    assert nassau.names[0].startswith("Bahamas")
    assert {item.location.name: item.location.breakpoint_span for item in results} == {
        LANDMARK_NAME: miami,
        NASSAU_NAME: nassau,
    }


async def test_a_snapshot_without_a_catalogue_keeps_the_stored_span(
    database: Database, recorded: RecordedSnapshot
) -> None:
    locations = _stored(database, recorded)
    _service(database).assess(recorded.snapshot, locations)
    repository = LocationRepository(database.engine)
    spanned = repository.list()
    without = _later(recorded.snapshot, 1, breakpoints=())
    SnapshotRepository(database.engine).save(without)

    results = _service(database, 30).assess(without, spanned)

    assert repository.list() == spanned
    assert [item.stored.assessment.breakpoint_span for item in results] == [
        location.breakpoint_span for location in spanned
    ]


async def test_a_rerun_over_the_same_snapshot_returns_what_is_stored_and_stores_nothing(
    database: Database, recorded: RecordedSnapshot
) -> None:
    locations = _stored(database, recorded)
    first = _service(database).assess(recorded.snapshot, locations)
    counts = _counts(database)

    again = _service(database, 5).assess(
        recorded.snapshot, LocationRepository(database.engine).list()
    )

    assert _counts(database) == counts
    assert not any(item.created for item in again)
    assert [item.stored for item in again] == [item.stored for item in first]


async def test_another_ruleset_over_the_same_snapshot_is_stored_beside_it(
    database: Database, recorded: RecordedSnapshot
) -> None:
    locations = _stored(database, recorded)
    _service(database).assess(recorded.snapshot, locations)
    narrower = AssessmentService(
        database.engine, thresholds=Thresholds(coastal_reach_km=10.0), now=lambda: NOW
    )

    results = narrower.assess(recorded.snapshot, LocationRepository(database.engine).list())

    assert all(item.created for item in results)
    assert _counts(database)[0] == 2 * len(locations)
    # The level held, so the second assessment of the same instant changes nothing.
    assert [item.stored.changes for item in results] == [(), ()]


# History -----------------------------------------------------------------------------------


async def test_a_later_run_diffs_against_the_previous_stored_assessment(
    database: Database, recorded: RecordedSnapshot
) -> None:
    locations = _stored(database, recorded)
    _service(database).assess(recorded.snapshot, locations)
    toggled_at = NOW + timedelta(minutes=10)
    repository = LocationRepository(database.engine)
    repository.set_evacuation_order(LANDMARK_NAME, on=True, at=toggled_at)
    later = _later(recorded.snapshot, 1)
    SnapshotRepository(database.engine).save(later)

    results = _service(database, 30).assess(later, repository.list())

    miami = next(item.stored for item in results if item.location.name == LANDMARK_NAME)
    assert (miami.assessment.level, miami.assessment.rule) == (
        AlertLevel.WARNING_WATCH_EVACUATION,
        RuleId.EVACUATION_ORDER,
    )
    (evidence,) = miami.assessment.evidence
    assert evidence.issued_at == toggled_at
    assert "since 2026-" in evidence.detail
    (change,) = miami.changes
    assert (change.kind, change.direction, change.previous_level) == (
        "level_changed",
        "up",
        AlertLevel.ALL_CLEAR,
    )
    nassau = next(item.stored for item in results if item.location.name == NASSAU_NAME)
    assert nassau.changes == ()
    history = AssessmentRepository(database.engine).history(LANDMARK_NAME, 10)
    assert [stored.assessment.snapshot_id for stored in history] == [
        later.snapshot_id,
        recorded.snapshot.snapshot_id,
    ]
    assert AssessmentRepository(database.engine).latest(LANDMARK_NAME) == history[0]
    with Session(database.engine) as session:
        kinds = session.scalars(
            select(AssessmentEvidenceRow.kind).where(
                AssessmentEvidenceRow.assessment_id == miami.id,
                AssessmentEvidenceRow.role == "evidence",
            )
        ).all()
    assert kinds == ["evacuation_toggle"]


async def test_the_previous_assessment_is_the_latest_at_or_before_the_snapshot(
    database: Database, recorded: RecordedSnapshot
) -> None:
    locations = _stored(database, recorded)
    later = _later(recorded.snapshot, 2)
    SnapshotRepository(database.engine).save(later)
    _service(database).assess(later, locations)
    repository = AssessmentRepository(database.engine)

    # An older snapshot assessed afterwards has no earlier assessment to diff against.
    (miami, _) = _service(database, 5).assess(recorded.snapshot, locations)

    assert miami.stored.changes[0].direction == "initial"
    assert repository.latest(LANDMARK_NAME, at_or_before=NOW) == miami.stored
    latest = repository.latest(LANDMARK_NAME)
    assert latest is not None
    assert latest.assessment.snapshot_id == later.snapshot_id
    with pytest.raises(ValueError, match="at least one"):
        repository.history(LANDMARK_NAME, 0)


async def test_removing_a_location_removes_its_assessments_evidence_and_changes(
    database: Database, recorded: RecordedSnapshot
) -> None:
    locations = _stored(database, recorded)
    results = _service(database).assess(recorded.snapshot, locations)
    nassau = next(item.stored for item in results if item.location.name == NASSAU_NAME)

    assert LocationRepository(database.engine).remove(LANDMARK_NAME)

    repository = AssessmentRepository(database.engine)
    assert repository.latest(LANDMARK_NAME) is None
    assert repository.history(NASSAU_NAME, 5) == (nassau,)
    expected = (
        1,
        len(nassau.assessment.evidence) + len(nassau.assessment.official),
        len(nassau.changes),
    )
    assert _counts(database) == expected


# Refusals ----------------------------------------------------------------------------------


def test_a_replay_snapshot_is_never_assessed_into_history(database: Database) -> None:
    corpus = ReplayCorpus.open(REPLAY)
    atcf_id = next(iter(corpus.manifest.storms))
    snapshot = next(corpus.snapshots(atcf_id))
    location = _nassau()
    LocationRepository(database.engine).add(location)

    with pytest.raises(AssessmentError, match="history is live only"):
        _service(database).assess(snapshot, [location])

    replayed = assess(snapshot, location, Thresholds())
    with pytest.raises(AssessmentStoreError, match="history is live only"):
        AssessmentRepository(database.engine).save(replayed, ())
    assert _counts(database) == (0, 0, 0)


async def test_an_assessment_needs_its_location_and_its_snapshot_stored(
    database: Database, recorded: RecordedSnapshot
) -> None:
    current = assess(recorded.snapshot, recorded.location, Thresholds())
    repository = AssessmentRepository(database.engine)

    with pytest.raises(AssessmentStoreError, match="location that is not stored"):
        repository.save(current, ())
    LocationRepository(database.engine).add(recorded.location)
    with pytest.raises(AssessmentStoreError, match="snapshot is not stored"):
        repository.save(current, ())
    SnapshotRepository(database.engine).save(recorded.snapshot, recorded.responses)
    repository.save(current, ())
    with pytest.raises(AssessmentStoreError, match="stored already"):
        repository.save(current, ())
    assert _counts(database)[0] == 1


# Official coverage -------------------------------------------------------------------------


async def test_official_products_say_which_alerts_and_segments_cover_a_location(
    recorded: RecordedSnapshot,
) -> None:
    corpus = ReplayCorpus.open(REPLAY)
    dorian = next(
        snapshot
        for snapshot in corpus.snapshots("AL052019")
        if snapshot.storms[0].cone is not None
        and str(snapshot.storms[0].cone.advisory.number) == "30"
    )

    alerts = official_products(recorded.snapshot, recorded.location, Thresholds())
    segments = official_products(dorian, _nassau(), Thresholds())

    (rip,) = alerts
    assert (rip.kind, rip.covers) == ("nws_alert", True)
    assert rip.reason.startswith("the point query returned it")
    assert not is_county_context(rip)
    assert segments
    assert all(p.kind == "watch_warning_segment" and p.covers for p in segments)
    assert "HWR" in {p.code for p in segments}
    assert all(p.distance_km is not None for p in segments)
