# tests/services/test_cycle_watcher.py
"""Tests for ``CycleWatcher`` polling high-water marks and skipping already-published events."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from scenarios import rebuilt
from snapshot_support import recorded_snapshot
from source_support import NOW

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.events import CycleWatcher, EventHub, HubEvent
from weatherbot.services.locations import LocationService
from weatherbot.services.monitor import MonitorService
from weatherbot.services.notifications import LogChannel
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import LocationRepository, SnapshotRepository


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
