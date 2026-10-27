# tests/services/test_staleness_timer.py
"""Tests for ``StalenessTimer`` and ``next_staleness_boundary`` on a fake clock."""

import asyncio
from datetime import datetime, timedelta

import pytest
from source_support import NOW

from weatherbot.services.config import AppPaths
from weatherbot.services.events import EventHub, StalenessTimer, next_staleness_boundary
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import HeartbeatRepository


class FakeClock:
    """Controllable clock and gated sleep for deterministic staleness timer tests."""

    def __init__(self, initial: datetime) -> None:
        """Create a fake clock starting at ``initial``."""
        self.current = initial
        self.slept_delays: list[float] = []
        self.sleeping = asyncio.Event()
        self.release = asyncio.Event()

    def __call__(self) -> datetime:
        """Return the current fake UTC instant."""
        return self.current

    async def sleep(self, seconds: float) -> None:
        """Record the requested delay and wait until ``release`` is set."""
        self.slept_delays.append(seconds)
        self.sleeping.set()
        await self.release.wait()
        self.release.clear()


@pytest.mark.anyio
async def test_staleness_timer_schedules_boundary_and_reschedules_on_cycle_and_fire() -> None:
    paths = AppPaths.resolve()
    clock = FakeClock(NOW)
    loop = asyncio.get_running_loop()
    hub = EventHub(loop, now=clock)
    sub = hub.subscribe()

    with open_database(paths, now=clock) as database:
        heartbeats = HeartbeatRepository(database.engine, now=clock)
        # Row without a cadence (`expected_every_s=None`) schedules nothing.
        heartbeats.record(
            "runner",
            "status",
            at=NOW,
            result="success",
            expected_every_s=None,
        )
        assert next_staleness_boundary(heartbeats.rows(), NOW) is None

        timer = StalenessTimer(database.engine, hub, now=clock, sleep=clock.sleep)
        try:
            assert await timer.refresh() is None
            assert timer.scheduled_at is None
            assert clock.slept_delays == []

            # Add two rows with cadences: 60s (stale at NOW + 120s) and 300s (stale at NOW + 600s).
            heartbeats.record(
                "watch",
                "roster",
                at=NOW,
                result="success",
                expected_every_s=60,
            )
            heartbeats.record(
                "runner",
                "serve",
                at=NOW,
                result="success",
                expected_every_s=300,
            )

            boundary = await timer.refresh()
            assert boundary == NOW + timedelta(seconds=120)
            assert timer.scheduled_at == NOW + timedelta(seconds=120)
            await asyncio.wait_for(clock.sleeping.wait(), timeout=1.0)
            clock.sleeping.clear()
            assert clock.slept_delays[-1] == pytest.approx(120.0)

            # A cycle refreshes the `roster` watch at NOW + 30s -> new boundary is NOW + 150s.
            clock.current = NOW + timedelta(seconds=30)
            heartbeats.record(
                "watch",
                "roster",
                at=clock.current,
                result="success",
                expected_every_s=60,
            )
            hub.publish(
                "cycle",
                {"cycle_id": 1, "runner": "serve", "trigger": "window", "status": "complete"},
                ("health",),
            )
            cycle_ev = await asyncio.wait_for(anext(sub), timeout=1.0)
            assert cycle_ev.kind == "cycle"

            await asyncio.wait_for(clock.sleeping.wait(), timeout=1.0)
            clock.sleeping.clear()
            assert timer.scheduled_at == NOW + timedelta(seconds=150)
            assert clock.slept_delays[-1] == pytest.approx(120.0)

            # Fire the timer at NOW + 150s: emits one `health` event and reschedules for the next
            # row (`serve` at NOW + 600s).
            clock.current = NOW + timedelta(seconds=150)
            clock.release.set()
            health_ev = await asyncio.wait_for(anext(sub), timeout=1.0)
            assert health_ev.kind == "health"
            assert health_ev.invalidate == ("health",)

            await asyncio.wait_for(clock.sleeping.wait(), timeout=1.0)
            clock.sleeping.clear()
            assert timer.scheduled_at == NOW + timedelta(seconds=600)
            assert clock.slept_delays[-1] == pytest.approx(450.0)

            # Fire the second boundary at NOW + 600s: no future boundary remains.
            clock.current = NOW + timedelta(seconds=600)
            clock.release.set()
            second_health_ev = await asyncio.wait_for(anext(sub), timeout=1.0)
            assert second_health_ev.kind == "health"
            await asyncio.sleep(0.01)
            assert timer.scheduled_at is None
        finally:
            await timer.close()
            sub.close()
