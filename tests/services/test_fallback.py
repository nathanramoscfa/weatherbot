# tests/services/test_fallback.py
"""Unit tests for ``run_fallback_check`` and ``serve``'s watch over the ``fallback`` runner row."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from cli_support import FakeToast, quiet_fetcher, recorded_services
from source_support import NOW

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.notifications import LogChannel, NotificationService
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import (
    CycleRepository,
    HeartbeatRepository,
)
from weatherbot.services.schedule import (
    FALLBACK_HEARTBEAT_CADENCE_S,
    run_fallback_check,
    run_heartbeat_task,
)


@dataclass
class _Clock:
    now: datetime = NOW
    sleeps: list[float] = field(default_factory=list[float])

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)
        await asyncio.sleep(0)


def test_fallback_skips_when_monitor_holds_lock_and_row_is_fresh() -> None:
    clock = _Clock(now=NOW)
    paths = AppPaths.resolve()
    with open_database(paths) as database:
        heartbeats = HeartbeatRepository(database.engine, now=clock)
        heartbeats.record(
            "runner",
            "serve",
            at=NOW - timedelta(minutes=2),
            result="success",
            expected_every_s=300,
        )

        toast = FakeToast()
        result = asyncio.run(
            run_fallback_check(
                database.engine,
                paths,
                settings=Settings(),
                clock=clock,
                sleep=clock.sleep,
                make_fetcher=quiet_fetcher,
                channels=(LogChannel(), toast),
                lock_held=lambda _p: True,
                serve_installed=True,
            )
        )

        assert result.ran_cycle is False
        assert result.cycle is None
        assert result.alarmed is False
        assert result.started_serve is False
        assert result.reason == "monitor_fresh"
        assert toast.handed == []
        assert CycleRepository(database.engine).recent(10) == ()

        fallback_row = next(
            r for r in heartbeats.rows() if r.kind == "runner" and r.name == "fallback"
        )
        assert fallback_row.expected_every_s == FALLBACK_HEARTBEAT_CADENCE_S
        assert fallback_row.last_success_at == NOW


def test_fallback_waits_for_held_lock_row_to_turn_fresh_without_alarm() -> None:
    clock = _Clock(now=NOW)
    paths = AppPaths.resolve()
    with open_database(paths) as database:
        heartbeats = HeartbeatRepository(database.engine, now=clock)
        heartbeats.record(
            "runner",
            "serve",
            at=NOW - timedelta(minutes=20),
            result="success",
            expected_every_s=300,
        )

        async def _sleep_and_refresh(seconds: float) -> None:
            await clock.sleep(seconds)
            if len(clock.sleeps) == 2:  # noqa: PLR2004 - second 5-second poll
                heartbeats.record(
                    "runner",
                    "serve",
                    at=clock.now,
                    result="success",
                    expected_every_s=300,
                )

        toast = FakeToast()
        result = asyncio.run(
            run_fallback_check(
                database.engine,
                paths,
                settings=Settings(),
                clock=clock,
                sleep=_sleep_and_refresh,
                make_fetcher=quiet_fetcher,
                channels=(LogChannel(), toast),
                lock_held=lambda _p: True,
                serve_installed=True,
            )
        )

        assert result.ran_cycle is False
        assert result.alarmed is False
        assert result.reason == "monitor_fresh"
        assert len(clock.sleeps) == 2  # noqa: PLR2004 - waited two polls
        assert toast.handed == []


def test_fallback_free_lock_with_serve_installed_alarms_once_starts_serve_and_runs_cycle() -> None:
    clock = _Clock(now=NOW)
    paths = AppPaths.resolve()
    started: list[str] = []
    toast = FakeToast()

    with recorded_services(), open_database(paths) as database:
        heartbeats = HeartbeatRepository(database.engine, now=clock)
        heartbeats.record(
            "runner",
            "serve",
            at=NOW - timedelta(minutes=30),
            result="success",
            expected_every_s=300,
        )

        first = asyncio.run(
            run_fallback_check(
                database.engine,
                paths,
                settings=Settings(),
                clock=clock,
                sleep=clock.sleep,
                make_fetcher=quiet_fetcher,
                channels=(LogChannel(), toast),
                lock_held=lambda _p: False,
                serve_installed=True,
                start_serve=lambda: started.append("serve"),
            )
        )

        assert first.ran_cycle is True
        assert first.alarmed is True
        assert first.started_serve is True
        assert first.reason == "not_running"
        assert first.cycle is not None
        assert first.cycle.runner == "fallback"
        assert first.cycle.trigger == "fallback"
        assert started == ["serve"]
        assert len(toast.handed) == 1
        assert toast.handed[0].kind == "stale_monitor"
        assert (
            toast.handed[0].title == "Weatherbot: the monitor is not running; a check ran instead."
        )

        # Second stale run without a fresh monitor row in between sends no second notification.
        clock.now += timedelta(hours=1)
        second = asyncio.run(
            run_fallback_check(
                database.engine,
                paths,
                settings=Settings(),
                clock=clock,
                sleep=clock.sleep,
                make_fetcher=quiet_fetcher,
                channels=(LogChannel(), toast),
                lock_held=lambda _p: False,
                serve_installed=True,
                start_serve=lambda: started.append("serve"),
            )
        )
        assert second.ran_cycle is True
        assert second.alarmed is False
        assert len(toast.handed) == 1


def test_fallback_held_lock_staying_stale_sends_not_responding_and_resets_after_fresh_row() -> None:
    clock = _Clock(now=NOW)
    paths = AppPaths.resolve()
    started: list[str] = []
    toast = FakeToast()

    with recorded_services(), open_database(paths) as database:
        heartbeats = HeartbeatRepository(database.engine, now=clock)
        heartbeats.record(
            "runner",
            "serve",
            at=NOW - timedelta(minutes=30),
            result="success",
            expected_every_s=300,
        )

        result = asyncio.run(
            run_fallback_check(
                database.engine,
                paths,
                settings=Settings(),
                clock=clock,
                sleep=clock.sleep,
                make_fetcher=quiet_fetcher,
                channels=(LogChannel(), toast),
                lock_held=lambda _p: True,
                serve_installed=True,
                start_serve=lambda: started.append("serve"),
                wait_s=15.0,
                poll_s=5.0,
            )
        )

        assert result.ran_cycle is True
        assert result.alarmed is True
        assert result.started_serve is False
        assert result.reason == "not_responding"
        assert started == []
        assert len(toast.handed) == 1
        assert (
            toast.handed[0].title
            == "Weatherbot: the monitor is not responding; a check ran instead."
        )

        # Monitor writes a fresh heartbeat and fallback sees it -> clears notification latch.
        clock.now += timedelta(minutes=5)
        heartbeats.record(
            "runner",
            "serve",
            at=clock.now,
            result="success",
            expected_every_s=300,
        )
        healthy = asyncio.run(
            run_fallback_check(
                database.engine,
                paths,
                settings=Settings(),
                clock=clock,
                sleep=clock.sleep,
                make_fetcher=quiet_fetcher,
                channels=(LogChannel(), toast),
                lock_held=lambda _p: True,
                serve_installed=True,
            )
        )
        assert healthy.ran_cycle is False

        # When it goes stale again later, the alarm fires again.
        clock.now += timedelta(minutes=30)
        again = asyncio.run(
            run_fallback_check(
                database.engine,
                paths,
                settings=Settings(),
                clock=clock,
                sleep=clock.sleep,
                make_fetcher=quiet_fetcher,
                channels=(LogChannel(), toast),
                lock_held=lambda _p: False,
                serve_installed=True,
            )
        )
        assert again.alarmed is True
        assert len(toast.handed) == 2  # noqa: PLR2004 - second distinct stale period


def test_fallback_without_serve_task_installed_runs_cycle_without_alarm() -> None:
    clock = _Clock(now=NOW)
    paths = AppPaths.resolve()
    toast = FakeToast()

    with recorded_services(), open_database(paths) as database:
        result = asyncio.run(
            run_fallback_check(
                database.engine,
                paths,
                settings=Settings(),
                clock=clock,
                sleep=clock.sleep,
                make_fetcher=quiet_fetcher,
                channels=(LogChannel(), toast),
                lock_held=lambda _p: False,
                serve_installed=False,
            )
        )

        assert result.ran_cycle is True
        assert result.alarmed is False
        assert result.started_serve is False
        assert result.reason == "unscheduled"
        assert toast.handed == []


def test_serve_heartbeat_task_alarms_once_when_fallback_row_goes_stale() -> None:
    clock = _Clock(now=NOW)
    paths = AppPaths.resolve()
    toast = FakeToast()

    with open_database(paths) as database:
        heartbeats = HeartbeatRepository(database.engine, now=clock)
        stale_instant = NOW - timedelta(hours=3)
        heartbeats.record(
            "runner",
            "fallback",
            at=stale_instant,
            result="success",
            expected_every_s=FALLBACK_HEARTBEAT_CADENCE_S,
        )

        stop = asyncio.Event()
        ticks = 0

        async def _two_ticks(seconds: float) -> None:
            nonlocal ticks
            ticks += 1
            await clock.sleep(seconds)
            if ticks >= 2:  # noqa: PLR2004 - two heartbeat ticks
                stop.set()

        asyncio.run(
            run_heartbeat_task(
                database.engine,
                "serve",
                heartbeat_minutes=5,
                stop=stop,
                clock=clock,
                sleep=_two_ticks,
                settings=Settings(),
                channels=(LogChannel(), toast),
                check_installed=True,
            )
        )

        assert len(toast.handed) == 1
        assert toast.handed[0].kind == "stale_monitor"
        assert (
            toast.handed[0].title
            == "Weatherbot: the hourly check has not run since 2026-10-12T22:30:00Z."
        )
        stored = NotificationService(database.engine).recent(limit=5)
        assert len(stored) == 1
