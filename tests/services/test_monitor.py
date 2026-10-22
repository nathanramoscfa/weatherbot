# tests/services/test_monitor.py
"""The monitor cycle: one path that fetches, stores, assesses, and records, under one lock.

Offline, against every recorded answer (``cli_support.recorded_services``), with the public
landmarks added through ``locations add``, in the test's temporary data directory. The
cycles run through ``MonitorService`` directly, and the commands through the command line.
"""

from collections.abc import Iterator
from datetime import timedelta
from typing import Final

import httpx
import pytest
from cli_support import (
    MIAMI,
    NASSAU,
    SUMMARY_CATALOG,
    add_landmark,
    quiet_fetcher,
    recorded_services,
    run,
    runtime,
)
from snapshot_support import recorded_snapshot
from source_support import NOW
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from weatherbot.services.config import AppPaths, MonitorSettings, Settings
from weatherbot.services.health import staleness
from weatherbot.services.locks import ProcessLock, held
from weatherbot.services.monitor import (
    LOCK_HELD,
    SCHEDULED_SOURCE_CADENCE_S,
    CycleListener,
    CycleResult,
    CycleRunner,
    MonitorService,
)
from weatherbot.services.network import Network
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import (
    CycleRepository,
    Heartbeat,
    HeartbeatRepository,
    LocationRepository,
    SnapshotRepository,
)
from weatherbot.services.persistence.tables import AssessmentRow, SnapshotRow
from weatherbot.services.snapshots import SNAPSHOT_SOURCES
from weatherbot.sources.http import Fetcher, ValidatorStore

pytestmark = pytest.mark.anyio

UNAVAILABLE: Final = 503
SUMMARY: Final = "nhc-map-tropical-summary"
ALERT_SOURCES: Final = ("nws-alerts-point", "nws-alerts-zone")


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


# ``locations add`` runs its own event loop, so the landmarks are added before a test's loop.
@pytest.fixture
def miami() -> None:
    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0


@pytest.fixture
def nassau() -> None:
    with recorded_services():
        assert add_landmark(NASSAU, "nassau").exit_code == 0


def _monitor(  # noqa: PLR0913 - the database, then each cycle setting a test varies
    database: Database,
    *,
    runner: CycleRunner = "check-once",
    minutes: int = 0,
    settings: Settings | None = None,
    cadence_s: int | None = None,
    network: Network | None = None,
    listeners: tuple[CycleListener, ...] = (),
) -> MonitorService:
    at = NOW + timedelta(minutes=minutes)
    return MonitorService(
        database.engine,
        paths=AppPaths.resolve(),
        settings=settings or Settings(),
        runner=runner,
        network=network or Network(make_fetcher=quiet_fetcher),
        now=lambda: at,
        listeners=listeners,
        cadence_s=cadence_s,
    )


def _beats(database: Database) -> dict[tuple[str, str], Heartbeat]:
    return {(row.kind, row.name): row for row in HeartbeatRepository(database.engine).rows()}


def _count(database: Database, table: type[SnapshotRow] | type[AssessmentRow]) -> int:
    with Session(database.engine) as session:
        return session.scalar(select(func.count()).select_from(table)) or 0


@pytest.mark.usefixtures("miami", "nassau")
async def test_a_cycle_stores_the_snapshot_assessments_heartbeats_and_a_complete_cycle(
    database: Database,
) -> None:
    with recorded_services():
        result = await _monitor(database).run_cycle("manual")

    assert result.status == "complete"
    assert result.snapshot is not None
    assert (result.trigger, result.runner) == ("manual", "check-once")
    assert [assessed.location.name for assessed in result.assessed] == [MIAMI, NASSAU]
    assert all(assessed.created for assessed in result.assessed)
    assert (_count(database, SnapshotRow), _count(database, AssessmentRow)) == (1, 2)
    beats = _beats(database)
    assert {name for kind, name in beats if kind == "source"} == set(SNAPSHOT_SOURCES)
    assert all(beats["source", name].last_success_at == NOW for name in SNAPSHOT_SOURCES)
    runner = beats["runner", "check-once"]
    assert (runner.last_success_at, runner.consecutive_failures) == (NOW, 0)
    cycle = CycleRepository(database.engine).get(result.cycle_id)
    assert cycle is not None
    assert (cycle.status, cycle.snapshot_id, cycle.detail) == (
        "complete",
        result.snapshot.snapshot_id,
        None,
    )
    assert (cycle.started_at, cycle.completed_at) == (NOW, NOW)


@pytest.mark.usefixtures("miami")
async def test_a_failed_source_counts_its_failures_and_a_later_success_resets_them(
    database: Database,
) -> None:
    failing = {SUMMARY_CATALOG: httpx.Response(UNAVAILABLE, headers={"content-type": "text/plain"})}
    with recorded_services(overrides=failing):
        first = await _monitor(database).run_cycle("manual")
        second = await _monitor(database, minutes=5).run_cycle("retry")
    after_failures = _beats(database)["source", SUMMARY]
    with recorded_services():
        await _monitor(database, minutes=10).run_cycle("retry")
    recovered = _beats(database)["source", SUMMARY]

    assert (first.status, second.status) == ("partial", "partial")
    assert after_failures.consecutive_failures == 2  # noqa: PLR2004 - two failed cycles
    assert after_failures.last_error_kind == "unavailable"
    assert after_failures.last_success_at is None
    assert after_failures.last_attempt_at == NOW + timedelta(minutes=5)
    assert recovered.consecutive_failures == 0
    assert recovered.last_error_kind is None
    assert recovered.last_success_at == NOW + timedelta(minutes=10)


@pytest.mark.usefixtures("nassau")  # outside NWS coverage: the alert sources are skipped
async def test_a_skipped_source_is_never_stale_and_never_failing(database: Database) -> None:
    with recorded_services():
        await _monitor(database, cadence_s=SCHEDULED_SOURCE_CADENCE_S).run_cycle("window")
    beats = _beats(database)
    judged = {item.name: item for item in staleness(tuple(beats.values()), NOW + timedelta(days=9))}

    for name in ALERT_SOURCES:
        skipped = beats["source", name]
        assert skipped.last_attempt_at == NOW
        assert (skipped.last_success_at, skipped.consecutive_failures) == (None, 0)
        assert skipped.expected_every_s is None
        assert not judged[name].stale
    assert beats["source", SUMMARY].expected_every_s == SCHEDULED_SOURCE_CADENCE_S
    assert judged[SUMMARY].stale


async def test_a_held_cycle_lock_gives_a_skipped_cycle(database: Database) -> None:
    holder = ProcessLock(AppPaths.resolve().cycle_lock_path)
    assert holder.try_acquire()
    quick = Settings(monitor=MonitorSettings(cycle_lock_wait_seconds=1))
    try:
        result = await _monitor(database, settings=quick).run_cycle("manual")
    finally:
        holder.release()

    assert result.status == "skipped"
    assert (result.snapshot, result.assessed) == (None, ())
    cycle = CycleRepository(database.engine).get(result.cycle_id)
    assert cycle is not None
    assert (cycle.status, cycle.detail, cycle.snapshot_id) == ("skipped", LOCK_HELD, None)
    runner = _beats(database)["runner", "check-once"]
    assert (runner.last_attempt_at, runner.last_success_at) == (NOW, None)
    assert _count(database, SnapshotRow) == 0


class _BrokenError(RuntimeError):
    """A failure the test injects into the fetch."""


def _broken_fetcher(client: httpx.AsyncClient, validators: ValidatorStore) -> Fetcher:
    del client, validators
    message = "the run's client could not be built"
    raise _BrokenError(message)


async def test_an_exception_records_an_error_cycle_releases_the_lock_and_propagates(
    database: Database,
) -> None:
    broken = Network(make_fetcher=_broken_fetcher)

    with pytest.raises(_BrokenError):
        await _monitor(database, network=broken).run_cycle("manual")

    (cycle,) = CycleRepository(database.engine).recent(5)
    assert (cycle.status, cycle.detail) == ("error", "_BrokenError")
    runner = _beats(database)["runner", "check-once"]
    assert (runner.consecutive_failures, runner.last_error_kind) == (1, "_BrokenError")
    assert not held(AppPaths.resolve().cycle_lock_path)


@pytest.mark.usefixtures("miami")
async def test_listeners_see_the_committed_result_and_a_failing_one_changes_nothing(
    database: Database,
) -> None:
    seen: list[tuple[CycleResult, str | None]] = []

    def listen(result: CycleResult) -> None:
        cycle = CycleRepository(database.engine).get(result.cycle_id)
        seen.append((result, cycle.status if cycle else None))

    def fail(result: CycleResult) -> None:
        message = f"listener of cycle {result.cycle_id}"
        raise ValueError(message)

    with recorded_services():
        result = await _monitor(database, listeners=(fail, listen)).run_cycle("manual")

    assert seen == [(result, "complete")]


async def test_a_cycle_over_a_stored_snapshot_records_no_source(database: Database) -> None:
    recorded = await recorded_snapshot()
    LocationRepository(database.engine).add(recorded.location)
    SnapshotRepository(database.engine).save(recorded.snapshot, recorded.responses)
    stored = SnapshotRepository(database.engine).latest()
    assert stored is not None

    result = await _monitor(database, runner="status").run_cycle("manual", snapshot=stored)

    assert result.status == stored.status
    assert len(result.assessed) == 1
    assert set(_beats(database)) == {("runner", "status")}
    cycle = CycleRepository(database.engine).get(result.cycle_id)
    assert cycle is not None
    assert cycle.snapshot_id == stored.snapshot_id


@pytest.mark.usefixtures("miami")
async def test_a_fetch_only_cycle_assesses_nothing(database: Database) -> None:
    with recorded_services():
        result = await _monitor(database, runner="fetch").run_cycle("manual", assess=False)

    assert result.status == "complete"
    assert result.assessed == ()
    assert _count(database, AssessmentRow) == 0
    assert ("source", SUMMARY) in _beats(database)


def test_every_command_records_its_runner_and_none_sets_a_cadence() -> None:
    later = runtime(now=NOW + timedelta(minutes=20))
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        ran = [
            run(["fetch"]),
            run(["storms"], later),
            run(["alerts"], later),
            run(["status"], later),
            run(["check", "--once"], later),
            run(["status", "--no-fetch"], later),
            run(["storms", "--no-fetch"], later),
        ]

    assert [result.exit_code for result in ran] == [0] * len(ran), [r.stderr for r in ran]
    with open_database(AppPaths.resolve()) as database:
        beats = _beats(database)
        cycles = CycleRepository(database.engine).recent(20)
    runners = {name for kind, name in beats if kind == "runner"}
    assert runners == {"fetch", "storms", "alerts", "status", "check-once"}
    assert [cycle.runner for cycle in reversed(cycles)] == [
        "fetch",
        "storms",
        "alerts",
        "status",
        "check-once",
        "status",
        "storms",
    ]
    assert all(cycle.status == "complete" for cycle in cycles)
    assert all(cycle.trigger == "manual" for cycle in cycles)
    assert all(beat.expected_every_s is None for beat in beats.values())
