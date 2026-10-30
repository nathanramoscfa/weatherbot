# src/weatherbot/services/events.py
"""The in-process event hub, polling cycle watcher, staleness timer, and browser channel.

``EventHub`` fans out ``HubEvent`` records to at most 16 subscribed open dashboard pages,
each backed by a bounded queue of 100 events. Publishing is safe from the event loop's
thread and from worker threads (via ``loop.call_soon_threadsafe``), and every
"already published?" decision is made on the loop's thread where publication lands.

``EventHub.cycle_listener`` turns a completed ``CycleResult`` into ``cycle``, ``snapshot``,
``assessment``, ``alert``, and ``notification`` events naming the query keys a page must
refetch. ``CycleWatcher`` polls four high-water marks off the loop's thread every 10
seconds so cycles, notifications, assessments, and location changes stored by other
processes reach open pages without duplicate publication. ``StalenessTimer`` schedules one
``health`` event at the earliest future instant any heartbeat with a cadence turns stale.
``BrowserChannel`` implements ``Channel`` (``name == "browser"``, ``interrupts == True``)
and delivers notifications to open dashboards over the hub.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal, Self
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from weatherbot.services.health import STALE_AFTER_CADENCES
from weatherbot.services.notifications import (
    Delivery,
    NotificationKind,
    NotificationService,
    StoredNotification,
)
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    CycleRepository,
    Heartbeat,
    HeartbeatRepository,
    MonitorCycle,
    StoredAssessment,
)
from weatherbot.services.persistence.tables import (
    AssessmentRow,
    LocationRow,
    MonitorCycleRow,
    NotificationRow,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from weatherbot.services.monitor import CycleResult, CycleRunner, CycleStatus, CycleTrigger

type EventKind = Literal[
    "hello",
    "cycle",
    "snapshot",
    "assessment",
    "alert",
    "notification",
    "location",
    "health",
]
EVENT_KINDS: Final[tuple[EventKind, ...]] = (
    "hello",
    "cycle",
    "snapshot",
    "assessment",
    "alert",
    "notification",
    "location",
    "health",
)

type QueryKey = Literal[
    "health",
    "locations",
    "assessments",
    "storms",
    "alerts",
    "map",
    "timeline",
    "notifications",
    "settings",
]
QUERY_KEYS: Final[tuple[QueryKey, ...]] = (
    "health",
    "locations",
    "assessments",
    "storms",
    "alerts",
    "map",
    "timeline",
    "notifications",
    "settings",
)

MAX_SUBSCRIBERS: Final = 16
MAX_QUEUE_SIZE: Final = 100
DEFAULT_WATCH_INTERVAL_S: Final = 10.0

BROWSER_OFF: Final = "turned off by [notifications] browser"
NO_OPEN_DASHBOARD: Final = "no open dashboard"


def _now() -> datetime:
    return datetime.now(UTC)


class SubscriberLimitError(Exception):
    """Raised when a seventeenth subscriber attempts to subscribe to ``EventHub``."""


@dataclass(frozen=True, slots=True)
class HubEvent:
    """One event published through ``EventHub``.

    Carries only identifiers, location names, threat levels, kinds, and query keys to
    invalidate — never coordinates, distances, or bearings.
    """

    id: int
    kind: EventKind
    at: datetime
    invalidate: tuple[QueryKey, ...] = ()
    started_at: datetime | None = None
    cycle_id: int | None = None
    runner: CycleRunner | str | None = None
    trigger: CycleTrigger | str | None = None
    status: CycleStatus | str | None = None
    snapshot_id: UUID | None = None
    location: str | None = None
    assessment_id: int | None = None
    level: int | None = None
    complete: bool | None = None
    notification_id: int | None = None
    notification_kind: NotificationKind | None = None
    escalation: bool | None = None
    title: str | None = None
    body: tuple[str, ...] | None = None
    display: bool = False


class Subscription(AsyncIterator[HubEvent]):
    """A bounded async event iterator for one subscribed dashboard connection."""

    def __init__(
        self,
        hub: EventHub,
        *,
        max_queue_size: int,
        hello: HubEvent,
        loop: asyncio.AbstractEventLoop | None,
    ) -> None:
        """Create a subscription bound to ``hub``."""
        self._hub = hub
        self._max_queue_size = max_queue_size
        self._hello = hello
        self._loop = loop
        self._items: deque[HubEvent | None] = deque()
        self._wake: asyncio.Event | None = None
        self._closed = False

    @property
    def hello(self) -> HubEvent:
        """The initial ``hello`` event created when this subscription opened."""
        return self._hello

    @property
    def closed(self) -> bool:
        """Whether this subscription has been closed or overflowed."""
        return self._closed

    @property
    def has_pending(self) -> bool:
        """Whether queued events are waiting to be consumed."""
        return bool(self._items)

    def __enter__(self) -> Self:
        """Enter sync context manager."""
        return self

    def __exit__(self, *_exc: object) -> None:
        """Close the subscription on sync context exit."""
        self.close()

    async def __aenter__(self) -> Self:
        """Enter async context manager."""
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Close the subscription on async context exit."""
        self.close()

    def __aiter__(self) -> Self:
        """Return self as an async iterator."""
        return self

    async def __anext__(self) -> HubEvent:
        """Yield the next published ``HubEvent``, or stop when closed or overflowed."""
        while True:
            if self._items:
                item = self._items.popleft()
                if item is None:
                    self.close()
                    raise StopAsyncIteration
                return item
            if self._closed:
                raise StopAsyncIteration
            if self._wake is None:
                self._wake = asyncio.Event()
            else:
                self._wake.clear()
            if self._items or self._closed:
                continue
            await self._wake.wait()

    def enqueue_on_loop(self, event: HubEvent) -> bool:
        """Append ``event`` on the loop thread; return ``False`` if the queue overflowed."""
        if self._closed:
            return False
        if len(self._items) >= self._max_queue_size:
            self._closed = True
            self._items.append(None)
            self._signal()
            return False
        self._items.append(event)
        self._signal()
        return True

    def end_on_loop(self) -> None:
        """Mark the subscription ended on the loop thread and wake any waiter."""
        if not self._closed:
            self._closed = True
            self._items.append(None)
            self._signal()

    def _signal(self) -> None:
        if self._wake is not None:
            self._wake.set()

    def close(self) -> None:
        """Release this subscription from ``EventHub`` and stop iteration."""
        self._closed = True
        self._hub.unsubscribe(self)
        if self._wake is not None:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is self._loop or self._loop is None or not self._loop.is_running():
                self._wake.set()
            else:
                self._loop.call_soon_threadsafe(self._wake.set)


class EventHub:
    """In-process publish-subscribe hub for open dashboard event streams."""

    def __init__(  # noqa: PLR0913 - hub configuration and injectable limits/clock
        self,
        loop: asyncio.AbstractEventLoop | None = None,
        *,
        now: Callable[[], datetime] = _now,
        started_at: datetime | None = None,
        newest_cycle_id: int | None = None,
        max_subscribers: int = MAX_SUBSCRIBERS,
        max_queue_size: int = MAX_QUEUE_SIZE,
    ) -> None:
        """Create an ``EventHub`` attached to ``loop``."""
        if loop is None:
            with contextlib.suppress(RuntimeError):
                loop = asyncio.get_running_loop()
        self._loop = loop
        self._now = now
        self._started_at = started_at if started_at is not None else now()
        self._newest_cycle_id = newest_cycle_id
        self._max_subscribers = max_subscribers
        self._max_queue_size = max_queue_size
        self._lock = threading.Lock()
        self._next_event_id = 0
        self._subscribers: list[Subscription] = []
        self._closed = False

        # High-water / deduplication state owned by the loop thread:
        self._published_cycles: set[int] = set()
        if newest_cycle_id is not None:
            self._published_cycles.add(newest_cycle_id)
        self._published_snapshots: set[UUID] = set()
        self._published_assessments: set[int] = set()
        self._published_notifications: set[int] = set()
        self._published_locations: dict[str, tuple[bool, datetime | None] | None] = {}
        self._cycle_callbacks: list[Callable[[], None]] = []

    @property
    def started_at(self) -> datetime:
        """UTC instant when the hub was created."""
        return self._started_at

    @property
    def newest_cycle_id(self) -> int | None:
        """Newest completed cycle id known to the hub in memory."""
        return self._newest_cycle_id

    @property
    def subscriber_count(self) -> int:
        """Number of currently active subscribers."""
        with self._lock:
            return len(self._subscribers)

    def seed_cycle_id(self, cycle_id: int | None) -> None:
        """Record the initial newest cycle id read at startup without publishing."""
        if cycle_id is None:
            return
        if self._newest_cycle_id is None or cycle_id > self._newest_cycle_id:
            self._newest_cycle_id = cycle_id
        self._published_cycles.add(cycle_id)

    def on_cycle(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register ``callback`` to run on the loop thread after every ``cycle`` event."""
        self._cycle_callbacks.append(callback)

        def _remove() -> None:
            with contextlib.suppress(ValueError):
                self._cycle_callbacks.remove(callback)

        return _remove

    def _allocate_id(self) -> int:
        with self._lock:
            self._next_event_id += 1
            return self._next_event_id

    def subscribe(self) -> Subscription:
        """Open a new subscriber queue, or raise ``SubscriberLimitError`` above 16."""
        if self._loop is None:
            with contextlib.suppress(RuntimeError):
                self._loop = asyncio.get_running_loop()
        with self._lock:
            if len(self._subscribers) >= self._max_subscribers:
                message = f"at most {self._max_subscribers} open dashboards may subscribe at once"
                raise SubscriberLimitError(message)
            self._next_event_id += 1
            hello = HubEvent(
                id=self._next_event_id,
                kind="hello",
                at=self._now(),
                invalidate=QUERY_KEYS,
                started_at=self._started_at,
                cycle_id=self._newest_cycle_id,
            )
            sub = Subscription(
                self,
                max_queue_size=self._max_queue_size,
                hello=hello,
                loop=self._loop,
            )
            if self._closed:
                sub.end_on_loop()
            else:
                self._subscribers.append(sub)
            return sub

    def unsubscribe(self, sub: Subscription) -> None:
        """Remove ``sub`` from the active subscriber list."""
        with self._lock, contextlib.suppress(ValueError):
            self._subscribers.remove(sub)

    def prime_location(
        self,
        name: str,
        state: tuple[bool, datetime | None],
    ) -> None:
        """Seed the initial location state for ``name`` without overwriting newer state."""
        self._published_locations.setdefault(name, state)

    def publish(
        self,
        event_kind: EventKind,
        data: Mapping[str, Any] | None = None,
        invalidate: Iterable[QueryKey] = (),
        *,
        deduplicate: bool = False,
        **kwargs: object,
    ) -> None:
        """Publish an event to all active subscribers (safe from any thread)."""
        payload: dict[str, Any] = {}
        if data is not None:
            payload.update(data)
        if kwargs:
            payload.update(kwargs)
        inv_tuple = tuple(invalidate)
        self._run_on_loop(
            lambda: self._publish_on_loop(
                event_kind,
                payload,
                inv_tuple,
                deduplicate=deduplicate,
            )
        )

    def _run_on_loop(self, func: Callable[[], None]) -> None:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if self._loop is None and running is not None:
            self._loop = running
        if running is self._loop or self._loop is None or not self._loop.is_running():
            func()
        else:
            self._loop.call_soon_threadsafe(func)

    def _publish_on_loop(
        self,
        event_kind: EventKind,
        payload: dict[str, Any],
        invalidate: tuple[QueryKey, ...],
        *,
        deduplicate: bool,
    ) -> None:
        if self._closed:
            return
        if not self._record_publication(event_kind, payload, deduplicate=deduplicate):
            return

        event = HubEvent(
            id=self._allocate_id(),
            kind=event_kind,
            at=self._now(),
            invalidate=invalidate,
            started_at=payload.get("started_at"),
            cycle_id=payload.get("cycle_id"),
            runner=payload.get("runner"),
            trigger=payload.get("trigger"),
            status=payload.get("status"),
            snapshot_id=payload.get("snapshot_id"),
            location=payload.get("location"),
            assessment_id=payload.get("assessment_id"),
            level=int(payload["level"]) if payload.get("level") is not None else None,
            complete=payload.get("complete"),
            notification_id=payload.get("notification_id"),
            notification_kind=payload.get("notification_kind"),
            escalation=payload.get("escalation"),
            title=payload.get("title"),
            body=tuple(payload["body"]) if payload.get("body") is not None else None,
            display=bool(payload.get("display", False)),
        )

        with self._lock:
            subscribers = list(self._subscribers)
        overflowed = [sub for sub in subscribers if not sub.enqueue_on_loop(event)]
        if overflowed:
            with self._lock:
                for sub in overflowed:
                    with contextlib.suppress(ValueError):
                        self._subscribers.remove(sub)

        if event_kind == "cycle":
            for callback in list(self._cycle_callbacks):
                callback()

    def _record_publication(
        self,
        event_kind: EventKind,
        payload: dict[str, Any],
        *,
        deduplicate: bool,
    ) -> bool:
        """Record high-water marks on the loop thread and return whether to publish."""
        if event_kind == "cycle":
            return self._record_cycle_publication(payload.get("cycle_id"), deduplicate=deduplicate)
        if event_kind == "snapshot":
            return self._record_id_publication(
                payload.get("snapshot_id"),
                UUID,
                self._published_snapshots,
                deduplicate=deduplicate,
            )
        if event_kind == "assessment":
            return self._record_id_publication(
                payload.get("assessment_id"),
                int,
                self._published_assessments,
                deduplicate=deduplicate,
            )
        if event_kind == "notification":
            return self._record_id_publication(
                payload.get("notification_id"),
                int,
                self._published_notifications,
                deduplicate=deduplicate,
            )
        if event_kind == "location" and "_location_state" in payload:
            return self._record_location_publication(payload, deduplicate=deduplicate)
        return True

    def _record_cycle_publication(self, cycle_id: object, *, deduplicate: bool) -> bool:
        if not isinstance(cycle_id, int):
            return True
        if deduplicate and cycle_id in self._published_cycles:
            return False
        self._published_cycles.add(cycle_id)
        if self._newest_cycle_id is None or cycle_id > self._newest_cycle_id:
            self._newest_cycle_id = cycle_id
        return True

    @staticmethod
    def _record_id_publication[T](
        item_id: object,
        expected_type: type[T],
        seen: set[T],
        *,
        deduplicate: bool,
    ) -> bool:
        if not isinstance(item_id, expected_type):
            return True
        if deduplicate and item_id in seen:
            return False
        seen.add(item_id)
        return True

    def _record_location_publication(
        self,
        payload: dict[str, Any],
        *,
        deduplicate: bool,
    ) -> bool:
        loc_name = payload.get("location")
        state = payload.pop("_location_state")
        if not isinstance(loc_name, str):
            return True
        if deduplicate and self._published_locations.get(loc_name, ()) == state:
            return False
        self._published_locations[loc_name] = state
        return True

    def record_location_change(
        self,
        name: str,
        *,
        evacuation_order_in_effect: bool,
        evacuation_order_set_at: datetime | None,
    ) -> None:
        """Publish a ``location`` event and record its state so ``CycleWatcher`` skips it."""
        self.publish(
            "location",
            {
                "location": name,
                "_location_state": (evacuation_order_in_effect, evacuation_order_set_at),
            },
            ("locations", "assessments", "map"),
        )

    def cycle_listener(self, result: CycleResult) -> None:
        """Publish the events for a ``CycleResult`` completed in this process."""
        self.publish(
            "cycle",
            {
                "cycle_id": result.cycle_id,
                "runner": result.runner,
                "trigger": result.trigger,
                "status": result.status,
            },
            ("health",),
            deduplicate=True,
        )
        if result.snapshot is not None:
            self.publish(
                "snapshot",
                {
                    "cycle_id": result.cycle_id,
                    "snapshot_id": result.snapshot.snapshot_id,
                    "status": result.snapshot.status,
                },
                ("storms", "map", "alerts"),
                deduplicate=True,
            )
        for item in result.assessed:
            if item.created:
                self.publish(
                    "assessment",
                    {
                        "cycle_id": result.cycle_id,
                        "location": item.location.name,
                        "assessment_id": item.stored.id,
                        "level": int(item.stored.assessment.level),
                        "complete": item.stored.assessment.complete,
                    },
                    ("assessments", "timeline"),
                    deduplicate=True,
                )
        for item in result.assessed:
            if item.created and any(
                change.kind.startswith("official_") for change in item.stored.changes
            ):
                self.publish(
                    "alert",
                    {
                        "cycle_id": result.cycle_id,
                        "location": item.location.name,
                        "assessment_id": item.stored.id,
                    },
                    ("alerts",),
                )
        for note in result.notifications:
            self.publish(
                "notification",
                {
                    "cycle_id": result.cycle_id,
                    "notification_id": note.id,
                    "notification_kind": note.kind,
                    "assessment_id": note.assessment_id,
                    "location": note.location_name,
                    "level": int(note.level) if note.level is not None else None,
                    "escalation": note.escalation,
                    "display": False,
                },
                ("notifications", "timeline"),
                deduplicate=True,
            )

    def close(self) -> None:
        """Close all open subscriptions so ``EventSourceResponse`` streams exit cleanly."""
        self._run_on_loop(self._close_on_loop)

    def _close_on_loop(self) -> None:
        self._closed = True
        with self._lock:
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for sub in subscribers:
            sub.end_on_loop()


@dataclass(frozen=True, slots=True)
class _WatchedState:
    cycles: tuple[MonitorCycle, ...]
    notifications: tuple[StoredNotification, ...]
    assessments: dict[str, StoredAssessment]
    locations: dict[str, tuple[bool, datetime | None]]
    max_cycle_id: int = 0
    max_notification_id: int = 0
    latest_assessment_ids: dict[str, int] | None = None


class CycleWatcher:
    """Polls four high-water marks off the loop's thread for changes from other processes."""

    def __init__(
        self,
        engine: Engine,
        hub: EventHub,
        interval_s: float = DEFAULT_WATCH_INTERVAL_S,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Create a ``CycleWatcher`` polling ``engine`` every ``interval_s`` seconds."""
        self._engine = engine
        self._hub = hub
        self._interval_s = interval_s
        self._sleep = sleep
        self._primed = False
        self._cycle_id = 0
        self._notification_id = 0
        self._assessment_ids: dict[str, int] = {}
        self._locations: dict[str, tuple[bool, datetime | None]] = {}

    def _read_state(self) -> _WatchedState:
        with Session(self._engine) as session:
            max_cycle_id = (
                session.scalar(
                    select(MonitorCycleRow.id)
                    .where(MonitorCycleRow.completed_at.is_not(None))
                    .order_by(MonitorCycleRow.id.desc())
                    .limit(1)
                )
                or 0
            )
            max_notif_id = (
                session.scalar(
                    select(NotificationRow.id).order_by(NotificationRow.id.desc()).limit(1)
                )
                or 0
            )
            loc_rows = session.execute(
                select(
                    LocationRow.id,
                    LocationRow.name,
                    LocationRow.evacuation_order_in_effect,
                    LocationRow.evacuation_order_set_at,
                ).order_by(LocationRow.name)
            ).all()
            latest_assessment_ids: dict[str, int] = {}
            locations: dict[str, tuple[bool, datetime | None]] = {}
            for loc_id, loc_name, evac_on, evac_at in loc_rows:
                locations[loc_name] = (evac_on, evac_at)
                latest_id = session.scalar(
                    select(AssessmentRow.id)
                    .where(AssessmentRow.location_id == loc_id)
                    .order_by(AssessmentRow.as_of.desc(), AssessmentRow.id.desc())
                    .limit(1)
                )
                if latest_id is not None:
                    latest_assessment_ids[loc_name] = int(latest_id)

        if not self._primed:
            return _WatchedState(
                cycles=(),
                notifications=(),
                assessments={},
                locations=locations,
                max_cycle_id=int(max_cycle_id),
                max_notification_id=int(max_notif_id),
                latest_assessment_ids=latest_assessment_ids,
            )

        cycles = (
            tuple(
                cycle
                for cycle in CycleRepository(self._engine).recent(25)
                if cycle.completed_at is not None
            )
            if max_cycle_id > self._cycle_id
            else ()
        )
        notifications = (
            NotificationService(self._engine).recent(25)
            if max_notif_id > self._notification_id
            else ()
        )
        assessments: dict[str, StoredAssessment] = {}
        changed_locations = [
            name
            for name, latest_id in latest_assessment_ids.items()
            if latest_id > self._assessment_ids.get(name, 0)
        ]
        if changed_locations:
            assessments_repo = AssessmentRepository(self._engine)
            for name in changed_locations:
                latest = assessments_repo.latest(name)
                if latest is not None:
                    assessments[name] = latest
        return _WatchedState(
            cycles=cycles,
            notifications=notifications,
            assessments=assessments,
            locations=locations,
            max_cycle_id=int(max_cycle_id),
            max_notification_id=int(max_notif_id),
            latest_assessment_ids=latest_assessment_ids,
        )

    async def poll(self) -> None:
        """Read the four high-water marks off the loop's thread and publish newer records."""
        read_future = asyncio.get_running_loop().run_in_executor(None, self._read_state)
        try:
            state = await asyncio.shield(read_future)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await read_future
            raise
        if not self._primed:
            self._prime_state(state)
            return
        self._publish_new_cycles(state.cycles)
        self._publish_new_assessments(state.assessments, state.locations)
        self._publish_new_notifications(state.notifications)
        self._publish_location_changes(state.locations)

    def _prime_state(self, state: _WatchedState) -> None:
        self._primed = True
        self._cycle_id = state.max_cycle_id or max((c.id for c in state.cycles), default=0)
        if self._cycle_id > 0:
            self._hub.seed_cycle_id(self._cycle_id)
        self._notification_id = state.max_notification_id or max(
            (n.id for n in state.notifications), default=0
        )
        self._assessment_ids = (
            dict(state.latest_assessment_ids)
            if state.latest_assessment_ids is not None
            else {name: item.id for name, item in state.assessments.items()}
        )
        self._locations = dict(state.locations)
        for name, loc_state in state.locations.items():
            self._hub.prime_location(name, loc_state)

    def _publish_new_cycles(self, cycles: tuple[MonitorCycle, ...]) -> None:
        new_cycles = sorted((c for c in cycles if c.id > self._cycle_id), key=lambda c: c.id)
        for cycle in new_cycles:
            self._cycle_id = max(self._cycle_id, cycle.id)
            self._hub.publish(
                "cycle",
                {
                    "cycle_id": cycle.id,
                    "runner": cycle.runner,
                    "trigger": cycle.trigger,
                    "status": cycle.status,
                },
                ("health",),
                deduplicate=True,
            )
            if cycle.snapshot_id is not None:
                self._hub.publish(
                    "snapshot",
                    {
                        "cycle_id": cycle.id,
                        "snapshot_id": cycle.snapshot_id,
                        "status": cycle.status
                        if cycle.status in ("complete", "partial", "failed")
                        else None,
                    },
                    ("storms", "map", "alerts"),
                    deduplicate=True,
                )

    def _publish_new_assessments(
        self,
        assessments: dict[str, StoredAssessment],
        locations: dict[str, tuple[bool, datetime | None]],
    ) -> None:
        for name, stored in assessments.items():
            prev_id = self._assessment_ids.get(name, 0)
            if stored.id > prev_id:
                self._assessment_ids[name] = stored.id
                self._hub.publish(
                    "assessment",
                    {
                        "location": name,
                        "assessment_id": stored.id,
                        "level": int(stored.assessment.level),
                        "complete": stored.assessment.complete,
                    },
                    ("assessments", "timeline"),
                    deduplicate=True,
                )
                if any(change.kind.startswith("official_") for change in stored.changes):
                    self._hub.publish(
                        "alert",
                        {
                            "location": name,
                            "assessment_id": stored.id,
                        },
                        ("alerts",),
                        deduplicate=True,
                    )
        for removed_name in list(self._assessment_ids):
            if removed_name not in locations:
                self._assessment_ids.pop(removed_name, None)

    def _publish_new_notifications(
        self,
        notifications: tuple[StoredNotification, ...],
    ) -> None:
        new_notifications = sorted(
            (n for n in notifications if n.id > self._notification_id),
            key=lambda n: n.id,
        )
        for note in new_notifications:
            self._notification_id = max(self._notification_id, note.id)
            self._hub.publish(
                "notification",
                {
                    "cycle_id": note.cycle_id,
                    "notification_id": note.id,
                    "notification_kind": note.kind,
                    "assessment_id": note.assessment_id,
                    "location": note.location_name,
                    "level": int(note.level) if note.level is not None else None,
                    "escalation": note.escalation,
                    "title": None,
                    "body": None,
                    "display": False,
                },
                ("notifications", "timeline"),
                deduplicate=True,
            )

    def _publish_location_changes(
        self,
        locations: dict[str, tuple[bool, datetime | None]],
    ) -> None:
        for name, loc_state in locations.items():
            if self._locations.get(name) != loc_state:
                self._hub.publish(
                    "location",
                    {"location": name, "_location_state": loc_state},
                    ("locations", "assessments", "map"),
                    deduplicate=True,
                )
        for removed_name in set(self._locations) - set(locations):
            self._hub.publish(
                "location",
                {"location": removed_name, "_location_state": None},
                ("locations", "assessments", "map"),
                deduplicate=True,
            )
        self._locations = dict(locations)

    async def _sleep_once(self) -> None:
        await self._sleep(self._interval_s)

    async def run(self, stop: asyncio.Event) -> None:
        """Prime high-water marks and poll every ``interval_s`` until ``stop`` is set."""
        await self.poll()
        while not stop.is_set():
            sleep_task = asyncio.create_task(self._sleep_once())
            stop_task = asyncio.create_task(stop.wait())
            try:
                await asyncio.wait({sleep_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in (sleep_task, stop_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(sleep_task, stop_task, return_exceptions=True)
            if stop.is_set():
                break
            await self.poll()


def next_staleness_boundary(rows: Sequence[Heartbeat], now: datetime) -> datetime | None:
    """Return the earliest future instant at which a heartbeat with a cadence turns stale."""
    boundaries = [
        row.last_success_at + timedelta(seconds=STALE_AFTER_CADENCES * row.expected_every_s)
        for row in rows
        if row.expected_every_s is not None and row.last_success_at is not None
    ]
    future = [instant for instant in boundaries if instant > now]
    return min(future) if future else None


class StalenessTimer:
    """Schedules one ``health`` event at the earliest future heartbeat staleness boundary."""

    def __init__(
        self,
        engine: Engine,
        hub: EventHub,
        *,
        now: Callable[[], datetime] = _now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Create a ``StalenessTimer`` watching ``engine``'s heartbeats."""
        self._heartbeats = HeartbeatRepository(engine, now=now)
        self._hub = hub
        self._now = now
        self._sleep = sleep
        self._scheduled_at: datetime | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._refresh_task: asyncio.Task[datetime | None] | None = None
        self._generation = 0
        self._closed = False
        self._remove_cycle_listener = self._hub.on_cycle(self._on_cycle_event)

    @property
    def scheduled_at(self) -> datetime | None:
        """The UTC instant currently scheduled for the next ``health`` event, or ``None``."""
        return self._scheduled_at

    def _on_cycle_event(self) -> None:
        if self._closed:
            return
        if self._wait_task is not None and not self._wait_task.done():
            self._wait_task.cancel()
        self._refresh_task = asyncio.create_task(self.refresh())

    async def refresh(self, *, after: datetime | None = None) -> datetime | None:
        """Read heartbeats off the loop's thread and replace any scheduled timer."""
        if self._closed:
            return None
        self._generation += 1
        gen = self._generation
        if (
            self._wait_task is not None
            and not self._wait_task.done()
            and self._wait_task is not asyncio.current_task()
        ):
            self._wait_task.cancel()
        self._wait_task = None

        read_future = asyncio.get_running_loop().run_in_executor(None, self._heartbeats.rows)
        try:
            rows = await asyncio.shield(read_future)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await read_future
            raise
        if self._closed or gen != self._generation:
            return self._scheduled_at

        now = self._now()
        cutoff = max(now, after) if after is not None else now
        boundary = next_staleness_boundary(rows, cutoff)
        self._scheduled_at = boundary
        if boundary is not None:
            self._wait_task = asyncio.create_task(self._wait_and_fire(boundary, gen))
        return boundary

    async def _wait_and_fire(self, boundary: datetime, gen: int) -> None:
        delay = max((boundary - self._now()).total_seconds(), 0.0)
        try:
            await self._sleep(delay)
        except asyncio.CancelledError:
            return
        if self._closed or gen != self._generation:
            return
        self._scheduled_at = None
        self._hub.publish("health", invalidate=("health",))
        await self.refresh(after=boundary)

    async def run(self, stop: asyncio.Event) -> None:
        """Run the staleness timer until ``stop`` is set."""
        await self.refresh()
        try:
            await stop.wait()
        finally:
            await self.close()

    async def close(self) -> None:
        """Cancel any scheduled timer and unregister from ``EventHub``."""
        self._closed = True
        self._remove_cycle_listener()
        self._scheduled_at = None
        tasks = [t for t in (self._wait_task, self._refresh_task) if t is not None]
        self._wait_task = None
        self._refresh_task = None
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


class BrowserChannel:
    """Delivers notifications to open dashboards over ``EventHub``."""

    def __init__(self, hub: EventHub, *, enabled: bool = True) -> None:
        """Create a browser channel backed by ``hub``."""
        self._hub = hub
        self._enabled = enabled

    @property
    def name(self) -> str:
        """The channel's identifier."""
        return "browser"

    @property
    def interrupts(self) -> bool:
        """A browser notification interrupts the operator."""
        return True

    async def deliver(self, notification: StoredNotification) -> Delivery:
        """Publish ``notification`` with ``display=True`` when enabled and a page is open."""
        if not self._enabled:
            return Delivery(result="disabled", detail=BROWSER_OFF)
        count = self._hub.subscriber_count
        if count == 0:
            return Delivery(result="unavailable", detail=NO_OPEN_DASHBOARD)
        self._hub.publish(
            "notification",
            {
                "cycle_id": notification.cycle_id,
                "notification_id": notification.id,
                "notification_kind": notification.kind,
                "assessment_id": notification.assessment_id,
                "location": notification.location_name,
                "level": int(notification.level) if notification.level is not None else None,
                "escalation": notification.escalation,
                "title": notification.title,
                "body": notification.body,
                "display": True,
            },
            ("notifications", "timeline"),
            deduplicate=True,
        )
        noun = "dashboard" if count == 1 else "dashboards"
        return Delivery(result="delivered", detail=f"to {count} open {noun}")
