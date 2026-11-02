# tests/services/test_cycle_watcher.py
"""Tests for ``CycleWatcher`` polling high-water marks and skipping already-published events."""

import asyncio
from datetime import UTC, timedelta
from uuid import uuid4

import pytest
from scenarios import rebuilt
from snapshot_support import recorded_snapshot
from source_support import NOW

from weatherbot.services.ai.client import default_client
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.ledger import Ledger, Outcome
from weatherbot.services.ai.outputs import NewOutput, OutputRepository
from weatherbot.services.ai.service import AiService
from weatherbot.services.config import AiSettings, AppPaths, Settings
from weatherbot.services.events import (
    DEFAULT_WATCH_INTERVAL_S,
    CycleWatcher,
    EventHub,
    HubEvent,
    Subscription,
)
from weatherbot.services.locations import LocationService
from weatherbot.services.monitor import MonitorService
from weatherbot.services.notifications import LogChannel
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import LocationRepository, SnapshotRepository

MODEL = "claude-sonnet-5-5"


@pytest.mark.anyio
async def test_watcher_first_read_publishes_nothing_and_skips_listener_publications() -> None:
    paths = AppPaths.resolve()
    recorded = await recorded_snapshot()
    second_snap = rebuilt(
        recorded.snapshot,
        snapshot_id=uuid4(),
        completed_at=recorded.snapshot.completed_at + timedelta(minutes=15),
    )
    third_snap = rebuilt(
        recorded.snapshot,
        snapshot_id=uuid4(),
        completed_at=recorded.snapshot.completed_at + timedelta(minutes=30),
    )

    loop = asyncio.get_running_loop()
    hub = EventHub(loop, now=lambda: NOW)
    sub = hub.subscribe()

    with open_database(paths) as database:
        LocationRepository(database.engine).add(recorded.location)
        SnapshotRepository(database.engine).save(recorded.snapshot, recorded.responses)
        SnapshotRepository(database.engine).save(second_snap, ())
        SnapshotRepository(database.engine).save(third_snap, ())

        # Pre-existing cycle before the watcher starts.
        initial_monitor = MonitorService(
            database.engine,
            paths=paths,
            settings=Settings(),
            runner="status",
            now=lambda: recorded.snapshot.completed_at,
            channels=(LogChannel(),),
        )
        await initial_monitor.run_cycle("manual", snapshot=recorded.snapshot, assess=True)

        watcher = CycleWatcher(database.engine, hub, interval_s=0.02)
        await watcher.poll()
        # First read primes high-water marks and publishes nothing.
        assert not sub.has_pending

        # Cycle run in this process with `hub.cycle_listener` registered:
        in_process_monitor = MonitorService(
            database.engine,
            paths=paths,
            settings=Settings(),
            runner="serve",
            now=lambda: second_snap.completed_at,
            listeners=(hub.cycle_listener,),
            channels=(LogChannel(),),
        )
        await in_process_monitor.run_cycle("window", snapshot=second_snap, assess=True)
        in_process_events: list[HubEvent] = []
        while sub.has_pending:
            in_process_events.append(await anext(sub))
        assert [e.kind for e in in_process_events] == ["cycle", "snapshot", "assessment"]

        # Next watcher poll sees those same rows and repeats nothing.
        await watcher.poll()
        assert not sub.has_pending

        await _verify_external_changes_published(
            engine=database.engine,
            paths=paths,
            watcher=watcher,
            sub=sub,
            location_name=recorded.location.name,
            third_snap=third_snap,
        )

    sub.close()


async def _verify_external_changes_published(  # noqa: PLR0913 - test helper for external process poll
    *,
    engine: object,
    paths: AppPaths,
    watcher: CycleWatcher,
    sub: object,
    location_name: str,
    third_snap: object,
) -> None:
    from sqlalchemy import Engine  # noqa: PLC0415

    from weatherbot.models import Snapshot  # noqa: PLC0415
    from weatherbot.services.events import Subscription  # noqa: PLC0415

    assert isinstance(engine, Engine)
    assert isinstance(sub, Subscription)
    assert isinstance(third_snap, Snapshot)

    stop = asyncio.Event()
    watch_task = asyncio.create_task(watcher.run(stop))
    try:
        other_monitor = MonitorService(
            engine,
            paths=paths,
            settings=Settings(),
            runner="status",
            now=lambda: third_snap.completed_at,
            channels=(LogChannel(),),
        )
        LocationService(
            engine,
            now=lambda: third_snap.completed_at,
        ).set_evacuation_order(location_name, on=True)
        await other_monitor.run_cycle("manual", snapshot=third_snap, assess=True)

        watched_events: list[HubEvent] = []
        expected_kinds = {"cycle", "snapshot", "assessment", "notification", "location"}
        while not expected_kinds.issubset({e.kind for e in watched_events}):
            event = await asyncio.wait_for(anext(sub), timeout=2.0)
            watched_events.append(event)
    finally:
        stop.set()
        await watch_task

    kinds = [e.kind for e in watched_events]
    assert "cycle" in kinds
    assert "snapshot" in kinds
    assert "assessment" in kinds
    assert "notification" in kinds
    assert "location" in kinds

    watched_notif = next(e for e in watched_events if e.kind == "notification")
    assert watched_notif.title is None
    assert watched_notif.body is None
    assert watched_notif.display is False
    assert watched_notif.invalidate == ("notifications", "timeline")

    watched_loc = next(e for e in watched_events if e.kind == "location")
    assert watched_loc.location == location_name
    assert watched_loc.invalidate == ("locations", "assessments", "map")


async def _drain(sub: Subscription) -> list[HubEvent]:
    events: list[HubEvent] = []
    while sub.has_pending:
        events.append(await anext(sub))
    return events


@pytest.mark.anyio
async def test_watcher_publishes_ai_rows_another_process_wrote_and_none_twice() -> None:
    hub = EventHub(asyncio.get_running_loop(), now=lambda: NOW)
    sub = hub.subscribe()
    with open_database(AppPaths.resolve()) as database:
        other_engine = ai_engine(database.path)
        other = Ledger(other_engine, cap_micro_usd=1_000_000, now=lambda: NOW, local_zone=UTC)
        other_outputs = OutputRepository(other_engine, now=lambda: NOW)
        mine = AiService(
            ai_engine(database.path),
            AiSettings(),
            factory=default_client,
            environ={},
            now=lambda: NOW,
            local_zone=UTC,
            publish=hub.publish,
        )
        early = other.reserve("chat", MODEL, None, None, 1_000)
        watcher = CycleWatcher(database.engine, hub, interval_s=0.05)
        await watcher.poll()
        await watcher.poll()
        primed_quietly = not sub.has_pending

        other.settle(early, Outcome("ok"))
        later = other.reserve("briefing", MODEL, "Parliament Square", None, 1_000)
        other.settle(later, Outcome("failed", error_kind="overloaded"))
        other_outputs.add(_output("Parliament Square"))
        await watcher.poll()
        from_other = [await anext(sub) for _ in range(3)]

        mine.ledger.settle(mine.ledger.reserve("summary", MODEL, None, None, 1_000), Outcome("ok"))
        OutputRepository(mine.engine, now=lambda: NOW, stored=mine.stored).add(_output(None))
        own = [await anext(sub) for _ in range(2)]
        await watcher.poll()
        repeated = await _drain(sub)

        stop = asyncio.Event()
        running = asyncio.create_task(watcher.run(stop))
        other.settle(other.reserve("chat", MODEL, None, None, 1_000), Outcome("ok"))
        within = await asyncio.wait_for(anext(sub), timeout=15)
        stop.set()
        await running
        await mine.close()
        other_engine.dispose()
    sub.close()

    assert primed_quietly
    assert [(e.call_id, e.status, e.invalidate) for e in from_other[:2]] == [
        (early.id, "ok", ("ai",)),
        (later.id, "failed", ("ai",)),
    ]
    assert (from_other[2].output_id, from_other[2].invalidate, from_other[2].location) == (
        1,
        ("briefings",),
        "Parliament Square",
    )
    assert [(e.kind, e.ai_kind, e.invalidate) for e in own] == [
        ("ai", "summary", ("ai",)),
        ("ai", "briefing", ("briefings",)),
    ]
    assert repeated == []
    assert (within.kind, within.ai_kind, within.status) == ("ai", "chat", "ok")
    assert DEFAULT_WATCH_INTERVAL_S < 15  # noqa: PLR2004 - the 15-second promise to a page


def _output(location: str | None) -> NewOutput:
    return NewOutput(
        kind="briefing",
        model=MODEL,
        prompt_version="0" * 64,
        status="withheld",
        content=None,
        location_name=location,
        withheld_reason="incomplete",
    )
