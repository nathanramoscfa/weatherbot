# tests/services/test_event_hub.py
"""Tests for ``EventHub``, queue overflow, worker-thread publication, and ``cycle_listener``."""

import asyncio
import re
import threading
from datetime import timedelta
from uuid import uuid4

import pytest
from scenarios import as_hurricane_warning, rebuilt
from snapshot_support import recorded_snapshot
from source_support import NOW

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.models import LatLon, Location
from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.events import (
    MAX_QUEUE_SIZE,
    MAX_SUBSCRIBERS,
    BrowserChannel,
    EventHub,
    HubEvent,
    SubscriberLimitError,
)
from weatherbot.services.monitor import MonitorService
from weatherbot.services.notifications import LogChannel
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import LocationRepository, SnapshotRepository
from weatherbot.web.routes.events import hub_event_to_stream_event

DECIMAL_COORDINATE = re.compile(r"(?<![\d.])\d{1,3}\.\d{3,}(?![\d.])")
TWO_SUBSCRIBERS = 2
INITIAL_CYCLE_ID = 7
NEXT_CYCLE_ID = 8


def _leaks_coordinate(text: str, coordinates: tuple[str, str]) -> bool:
    renderings = {
        rendering
        for value in coordinates
        for rendering in (value, str(float(value)), f"{float(value):.4f}", value.lstrip("-"))
    }
    return any(value in text for value in renderings) or bool(DECIMAL_COORDINATE.search(text))


@pytest.mark.anyio
async def test_ordered_delivery_to_two_subscribers_and_worker_thread_publish() -> None:
    loop = asyncio.get_running_loop()
    hub = EventHub(loop, now=lambda: NOW, started_at=NOW, newest_cycle_id=INITIAL_CYCLE_ID)

    sub_a = hub.subscribe()
    sub_b = hub.subscribe()
    assert hub.subscriber_count == TWO_SUBSCRIBERS
    assert sub_a.hello.kind == "hello"
    assert sub_a.hello.started_at == NOW
    assert sub_a.hello.cycle_id == INITIAL_CYCLE_ID
    assert sub_b.hello.id > sub_a.hello.id

    hub.publish(
        "cycle",
        {
            "cycle_id": NEXT_CYCLE_ID,
            "runner": "serve",
            "trigger": "manual",
            "status": "complete",
        },
        ("health",),
    )

    done = threading.Event()

    def _worker() -> None:
        hub.publish("location", {"location": "Miami"}, ("locations", "assessments", "map"))
        done.set()

    thread = threading.Thread(target=_worker)
    thread.start()
    done.wait(timeout=5.0)
    thread.join(timeout=5.0)

    ev_a1 = await asyncio.wait_for(anext(sub_a), timeout=2.0)
    ev_a2 = await asyncio.wait_for(anext(sub_a), timeout=2.0)
    ev_b1 = await asyncio.wait_for(anext(sub_b), timeout=2.0)
    ev_b2 = await asyncio.wait_for(anext(sub_b), timeout=2.0)

    assert (ev_a1.kind, ev_a2.kind) == ("cycle", "location")
    assert (ev_b1.kind, ev_b2.kind) == ("cycle", "location")
    assert ev_a1.id == ev_b1.id
    assert ev_a2.id == ev_b2.id
    assert ev_a1.id < ev_a2.id
    assert ev_a2.location == "Miami"
    assert hub.newest_cycle_id == NEXT_CYCLE_ID

    sub_a.close()
    sub_b.close()
    assert hub.subscriber_count == 0


@pytest.mark.anyio
async def test_overflowing_subscriber_ends_while_active_subscriber_continues() -> None:
    loop = asyncio.get_running_loop()
    hub = EventHub(loop, now=lambda: NOW)

    slow = hub.subscribe()
    fast = hub.subscribe()
    assert hub.subscriber_count == TWO_SUBSCRIBERS

    received_fast: list[HubEvent] = []
    for index in range(MAX_QUEUE_SIZE):
        hub.publish("health", {"cycle_id": index + 1}, ("health",))
        received_fast.append(await asyncio.wait_for(anext(fast), timeout=1.0))

    assert len(received_fast) == MAX_QUEUE_SIZE
    assert hub.subscriber_count == TWO_SUBSCRIBERS

    # Publishing the 101st event overflows `slow` (which has read 0 events), while `fast` continues.
    hub.publish("health", {"cycle_id": MAX_QUEUE_SIZE + 1}, ("health",))
    assert hub.subscriber_count == 1
    assert slow.closed

    slow_events = [event async for event in slow]
    assert len(slow_events) == MAX_QUEUE_SIZE

    extra = await asyncio.wait_for(anext(fast), timeout=1.0)
    assert extra.cycle_id == MAX_QUEUE_SIZE + 1
    fast.close()


@pytest.mark.anyio
async def test_subscriber_limit_refuses_seventeenth_subscriber() -> None:
    loop = asyncio.get_running_loop()
    hub = EventHub(loop, now=lambda: NOW)
    subs = [hub.subscribe() for _ in range(MAX_SUBSCRIBERS)]
    assert hub.subscriber_count == MAX_SUBSCRIBERS

    with pytest.raises(SubscriberLimitError, match="16"):
        hub.subscribe()

    subs[0].close()
    assert hub.subscriber_count == MAX_SUBSCRIBERS - 1
    replacement = hub.subscribe()
    replacement.close()
    for sub in subs[1:]:
        sub.close()


@pytest.mark.anyio
async def test_cycle_listener_emits_events_in_order_and_no_event_holds_a_coordinate() -> None:
    coordinates = synthetic_coordinates(load_landmarks(), (), seed=6)
    lat_str, lon_str = coordinates
    paths = AppPaths.resolve()
    recorded = await recorded_snapshot()
    synthetic_location = Location(
        name="Synthetic place",
        point=LatLon(latitude=float(lat_str), longitude=float(lon_str)),
        country_code="US",
        display_name=recorded.location.display_name,
        nws=recorded.location.nws,
        polygon=recorded.location.polygon,
        breakpoint_span=recorded.location.breakpoint_span,
    )
    (base_alert,) = recorded.snapshot.alerts[recorded.location.name]
    snap_baseline = rebuilt(
        recorded.snapshot,
        alerts={synthetic_location.name: ()},
    )
    snap_with_warning = rebuilt(
        recorded.snapshot,
        snapshot_id=uuid4(),
        completed_at=recorded.snapshot.completed_at + timedelta(minutes=15),
        alerts={synthetic_location.name: (as_hurricane_warning(base_alert),)},
    )

    loop = asyncio.get_running_loop()
    hub = EventHub(loop, now=lambda: NOW)
    sub = hub.subscribe()

    with open_database(paths) as database:
        LocationRepository(database.engine).add(synthetic_location)
        SnapshotRepository(database.engine).save(snap_baseline, recorded.responses)
        SnapshotRepository(database.engine).save(snap_with_warning, ())
        channels = (LogChannel(), BrowserChannel(hub, enabled=True))

        # Cycle 1: baseline assessment stored.
        monitor1 = MonitorService(
            database.engine,
            paths=paths,
            settings=Settings(),
            runner="serve",
            now=lambda: snap_baseline.completed_at,
            listeners=(hub.cycle_listener,),
            channels=channels,
        )
        first = await monitor1.run_cycle("startup", snapshot=snap_baseline, assess=True)
        first_events: list[HubEvent] = []
        while sub.has_pending:
            first_events.append(await anext(sub))

        assert [e.kind for e in first_events] == ["cycle", "snapshot", "assessment"]
        assert first_events[0].invalidate == ("health",)
        assert first_events[1].invalidate == ("storms", "map", "alerts")
        assert first_events[2].invalidate == ("assessments", "timeline")
        assert first_events[2].location == synthetic_location.name

        # Cycle 2: official_added change (Hurricane Warning) triggers `alert` event too.
        monitor2 = MonitorService(
            database.engine,
            paths=paths,
            settings=Settings(),
            runner="serve",
            now=lambda: snap_with_warning.completed_at,
            listeners=(hub.cycle_listener,),
            channels=(LogChannel(), BrowserChannel(hub, enabled=False)),
        )
        second = await monitor2.run_cycle("manual", snapshot=snap_with_warning, assess=True)
        assert second.assessed[0].created is True
        second_events: list[HubEvent] = []
        while sub.has_pending:
            second_events.append(await anext(sub))

        assert [e.kind for e in second_events] == [
            "cycle",
            "snapshot",
            "assessment",
            "alert",
            "notification",
        ]
        alert_ev = next(e for e in second_events if e.kind == "alert")
        assert alert_ev.location == synthetic_location.name
        assert alert_ev.invalidate == ("alerts",)
        notif_ev = next(e for e in second_events if e.kind == "notification")
        assert notif_ev.display is False
        assert notif_ev.invalidate == ("notifications", "timeline")

        # Cycle 3: rerun over the same snapshot -> assessment already stored (`created=False`),
        # so no `assessment` or `alert` event is emitted.
        third = await monitor2.run_cycle("manual", snapshot=snap_with_warning, assess=True)
        assert third.assessed[0].created is False
        third_events: list[HubEvent] = []
        while sub.has_pending:
            third_events.append(await anext(sub))
        assert [e.kind for e in third_events] == ["cycle"]

    for event in [sub.hello, *first_events, *second_events, *third_events]:
        serialized = hub_event_to_stream_event(event).model_dump_json()
        assert not _leaks_coordinate(serialized, coordinates), serialized
        assert not _leaks_coordinate(repr(event), coordinates), repr(event)

    sub.close()
    assert first.cycle_id < second.cycle_id < third.cycle_id
