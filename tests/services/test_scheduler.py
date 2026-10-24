# tests/services/test_scheduler.py
"""``weatherbot.services.scheduler``: fake clock, sleep cap, jitter, resume, and DST."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import HeartbeatRepository
from weatherbot.services.schedule import next_product_time_for_window, run_heartbeat_task
from weatherbot.services.scheduler import MAX_SLEEP_S, Job, Scheduler

START = datetime(2026, 10, 23, 0, 0, tzinfo=UTC)


@dataclass
class ManualClock:
    """A UTC clock driven only by explicit advances or ``sleep`` calls."""

    now: datetime = START
    sleeps: list[float] = field(default_factory=list[float])
    extra_wake_gap_s: float = 0.0

    def __call__(self) -> datetime:
        """Return the current UTC instant."""
        return self.now

    async def sleep(self, seconds: float) -> None:
        """Record ``seconds`` and advance the clock (adding any simulated machine sleep gap)."""
        self.sleeps.append(seconds)
        gap = self.extra_wake_gap_s
        self.extra_wake_gap_s = 0.0
        self.now += timedelta(seconds=seconds + gap)
        await asyncio.sleep(0)


class FixedRandom:
    """Deterministic uniform draw returning a fixed value clamped to ``[a, b]``."""

    def __init__(self, value: float) -> None:
        """Create a fixed random draw source."""
        self.value = value
        self.draws = 0

    def uniform(self, a: float, b: float) -> float:
        """Return the configured draw within ``[a, b]``."""
        self.draws += 1
        return max(a, min(b, self.value))


def test_sleeps_never_exceed_60_seconds_and_job_runs_at_due_plus_drawn_delay() -> None:
    clock = ManualClock(START)
    rng = FixedRandom(17.0)
    stop = asyncio.Event()
    due_at = START + timedelta(minutes=3)
    ran_at: list[datetime] = []

    async def _run(now: datetime) -> None:
        ran_at.append(now)
        stop.set()

    job = Job(
        name="window",
        next_due=lambda _now: due_at if not ran_at else None,
        run=_run,
        jitter_s=30.0,
    )
    scheduler = Scheduler(
        (job,),
        clock=clock,
        sleep=clock.sleep,
        random=rng,
        max_sleep_s=MAX_SLEEP_S,
    )
    asyncio.run(scheduler.run(stop))

    assert ran_at == [due_at + timedelta(seconds=17)]
    assert rng.draws == 1
    assert all(0 < s <= MAX_SLEEP_S for s in clock.sleeps)
    assert clock.sleeps == [60.0, 60.0, 60.0, 17.0]


def test_a_running_job_is_never_started_twice() -> None:
    clock = ManualClock(START)
    gate = asyncio.Event()
    entered = asyncio.Event()
    starts = 0

    async def _slow_job() -> None:
        nonlocal starts
        starts += 1
        entered.set()
        await gate.wait()

    job = Job(name="once", next_due=lambda _now: START, run=_slow_job)
    scheduler = Scheduler((job,), clock=clock, sleep=clock.sleep)

    async def _exercise() -> None:
        first = asyncio.create_task(scheduler.step())
        await entered.wait()
        # While the first invocation is still running, another step must skip it.
        await scheduler.step()
        assert starts == 1
        gate.set()
        await first

    asyncio.run(_exercise())
    assert starts == 1


def test_failing_job_is_logged_with_class_name_and_loop_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = ManualClock(START)
    stop = asyncio.Event()
    errors_recorded: list[tuple[datetime, str]] = []
    second_ran: list[datetime] = []

    async def _boom() -> None:
        message = "sensitive detail that must not stop the loop"
        raise ValueError(message)

    async def _ok(now: datetime) -> None:
        second_ran.append(now)
        stop.set()

    failing = Job(
        name="broken",
        next_due=lambda _now: START,
        run=_boom,
        on_error=lambda now, exc: errors_recorded.append((now, type(exc).__name__)),
    )
    healthy = Job(
        name="healthy",
        next_due=lambda _now: START + timedelta(seconds=10),
        run=_ok,
    )
    scheduler = Scheduler((failing, healthy), clock=clock, sleep=clock.sleep)
    with caplog.at_level(logging.ERROR, logger="weatherbot.services.scheduler"):
        asyncio.run(scheduler.run(stop))

    assert errors_recorded == [(START, "ValueError")]
    assert second_ran == [START + timedelta(seconds=10)]
    assert any("ValueError" in rec.message for rec in caplog.records)


def test_three_hour_wake_gap_runs_one_resume_first_while_five_minute_job_is_not_a_gap(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = ManualClock(START)
    stop = asyncio.Event()
    events: list[str] = []

    async def _long_job() -> None:
        events.append("long_job")
        # Job itself takes 5 minutes on the clock; not a sleep gap.
        clock.now += timedelta(minutes=5)
        # Next sleep will experience a 3-hour machine suspend.
        clock.extra_wake_gap_s = 3 * 3600.0

    async def _after_wake() -> None:
        events.append("after_wake")
        stop.set()

    first_done = False

    def _first_due(_now: datetime) -> datetime | None:
        nonlocal first_done
        if not first_done:
            first_done = True
            return START
        return None

    job1 = Job(name="long", next_due=_first_due, run=_long_job)
    job2 = Job(
        name="later",
        next_due=lambda _now: START + timedelta(minutes=6),
        run=_after_wake,
    )
    scheduler = Scheduler(
        (job1, job2),
        clock=clock,
        sleep=clock.sleep,
        on_resume=lambda: events.append("resume"),
    )
    with caplog.at_level(logging.INFO, logger="weatherbot.services.scheduler"):
        asyncio.run(scheduler.run(stop))

    assert events == ["long_job", "resume", "after_wake"]
    resumed_logs = [r.message for r in caplog.records if "resumed after" in r.message]
    assert len(resumed_logs) == 1
    assert "181 minutes" in resumed_logs[0]


def test_heartbeat_task_keeps_writing_while_slow_cycle_runs() -> None:
    paths = AppPaths.resolve()
    clock = ManualClock(START)
    stop = asyncio.Event()
    recorded_during_cycle: list[datetime | None] = []
    expected_samples = 2

    with open_database(paths) as database:

        async def _heartbeat_sleep(seconds: float) -> None:
            clock.now += timedelta(seconds=seconds)
            await asyncio.sleep(0)

        async def _slow_cycle() -> None:
            for _ in range(expected_samples):
                await asyncio.sleep(0)
                hb = next(
                    r
                    for r in HeartbeatRepository(database.engine).rows()
                    if r.kind == "runner" and r.name == "serve"
                )
                recorded_during_cycle.append(hb.last_success_at)
            stop.set()

        async def _run_both() -> None:
            hb_task = asyncio.create_task(
                run_heartbeat_task(
                    database.engine,
                    "serve",
                    heartbeat_minutes=5,
                    stop=stop,
                    clock=clock,
                    sleep=_heartbeat_sleep,
                )
            )
            job = Job(name="slow", next_due=lambda _now: START, run=_slow_cycle)
            scheduler = Scheduler((job,), clock=clock, sleep=clock.sleep)
            await scheduler.run(stop)
            await hb_task

        asyncio.run(_run_both())

    assert len(recorded_during_cycle) == expected_samples
    assert recorded_during_cycle[0] == START
    assert recorded_during_cycle[1] == START + timedelta(minutes=5)


def test_crossing_2026_11_01_daylight_saving_transition_changes_no_due_instant() -> None:
    # 2026-11-01 06:00 UTC is 02:00 EDT -> 01:00 EST in America/New_York.
    eastern = ZoneInfo("America/New_York")
    before_transition = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert before_transition.astimezone(eastern).utcoffset() == timedelta(hours=-4)

    product_06 = next_product_time_for_window(before_transition, offset_minutes=15)
    assert product_06 == datetime(2026, 11, 1, 6, 0, tzinfo=UTC)

    due_06 = product_06 + timedelta(minutes=15)
    assert due_06 == datetime(2026, 11, 1, 6, 15, tzinfo=UTC)
    assert due_06.astimezone(eastern).utcoffset() == timedelta(hours=-5)

    clock = ManualClock(before_transition)
    stop = asyncio.Event()
    fired: list[datetime] = []

    async def _record(now: datetime) -> None:
        fired.append(now)
        stop.set()

    job = Job(name="window", next_due=lambda _now: due_06, run=_record, jitter_s=0.0)
    scheduler = Scheduler((job,), clock=clock, sleep=clock.sleep, random=FixedRandom(0.0))
    asyncio.run(scheduler.run(stop))

    assert fired == [datetime(2026, 11, 1, 6, 15, tzinfo=UTC)]
    assert (fired[0] - before_transition) == timedelta(minutes=45)
