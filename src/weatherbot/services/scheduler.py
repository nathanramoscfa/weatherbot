# src/weatherbot/services/scheduler.py
"""Deterministic asyncio job scheduler with injected UTC clock, sleep, and randomness.

``Scheduler`` runs one short job at a time in due order, draws one positive random delay
per due instant, sleeps at most ``max_sleep_s`` (60 seconds) per iteration, isolates job
exceptions, and runs one ``resume`` callback before any job when a wake arrives more than
60 seconds after its sleep was due to end. It imports no I/O library and reads no clock,
sleep, or randomness except the injected callables.
"""

import asyncio
import inspect
import logging
import secrets
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Protocol, cast

LOGGER: Final = logging.getLogger("weatherbot.services.scheduler")

MAX_SLEEP_S: Final = 60.0
RESUME_GAP_S: Final = 60.0
_MICROSECOND: Final = timedelta(microseconds=1)


class RandomSource(Protocol):
    """Source of uniform draws ``uniform(a, b)``."""

    def uniform(self, a: float, b: float, /) -> float:
        """Return a random floating-point number in ``[a, b]``."""
        ...


type NextDue[StateT] = (
    Callable[[datetime], datetime | None] | Callable[[datetime, StateT], datetime | None]
)
type JobRun[StateT] = (
    Callable[[datetime, StateT], Awaitable[StateT] | StateT]
    | Callable[[datetime], Awaitable[StateT] | StateT]
    | Callable[[], Awaitable[StateT] | StateT]
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def _maybe_await(value: object) -> object:
    if inspect.isawaitable(value):
        return await cast("Awaitable[object]", value)
    return value


def _arity(callable_obj: Callable[..., object]) -> int:
    params = [
        p
        for p in inspect.signature(callable_obj).parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(params)


@dataclass(slots=True)
class Job[StateT = Any]:
    """One scheduled job.

    ``next_due`` accepts either ``(now, state)`` or ``(now,)`` and returns the job's next
    base due instant in UTC (before jitter) or ``None`` when the job is idle. ``run``
    accepts ``(now, state)``, ``(now,)``, or ``()``; when ``next_due`` takes two arguments,
    ``run``'s return value replaces ``state``.
    """

    name: str
    next_due: NextDue[StateT]
    run: JobRun[StateT]
    jitter_s: float = 0.0
    state: Any = None
    on_error: Callable[[datetime, Exception], Awaitable[object] | object] | None = None
    _next_due_arity: int = field(init=False, repr=False)
    _run_arity: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Cache the positional arities of ``next_due`` and ``run``."""
        self._next_due_arity = _arity(self.next_due)
        self._run_arity = _arity(self.run)

    def due_at(self, now: datetime) -> datetime | None:
        """Evaluate ``next_due`` at ``now``."""
        fn = cast("Callable[..., datetime | None]", self.next_due)
        if self._next_due_arity >= 2:  # noqa: PLR2004 - (now, state)
            return fn(now, self.state)
        return fn(now)

    async def execute(self, now: datetime) -> None:
        """Run the job once at ``now`` and update ``state`` when stateful."""
        fn = cast("Callable[..., object]", self.run)
        if self._run_arity >= 2:  # noqa: PLR2004 - (now, state)
            result = await _maybe_await(fn(now, self.state))
            self.state = cast("StateT", result)
        elif self._run_arity == 1:
            result = await _maybe_await(fn(now))
            if self._next_due_arity >= 2:  # noqa: PLR2004 - stateful next_due
                self.state = cast("StateT", result)
        else:
            result = await _maybe_await(fn())
            if self._next_due_arity >= 2:  # noqa: PLR2004 - stateful next_due
                self.state = cast("StateT", result)


@dataclass(slots=True)
class _JobSchedule:
    """Per-job scheduling state inside ``Scheduler``."""

    base_due: datetime | None = None
    effective_due: datetime | None = None
    last_completed_due: datetime | None = None


async def _sleep_until_stopped(seconds: float, stop: asyncio.Event) -> None:
    sleep_task = asyncio.create_task(asyncio.sleep(seconds))
    stop_task = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait({sleep_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sleep_task, stop_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(sleep_task, stop_task, return_exceptions=True)


class Scheduler:
    """Runs ``Job`` instances one at a time on an injected UTC clock and sleep."""

    def __init__(  # noqa: PLR0913 - scheduler dependencies are all injected
        self,
        jobs: Sequence[Job[Any]],
        *,
        clock: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        random: RandomSource | None = None,
        max_sleep_s: float = MAX_SLEEP_S,
        on_resume: Callable[..., Awaitable[object] | object] | None = None,
    ) -> None:
        """Create the scheduler.

        Args:
            jobs: The jobs to schedule.
            clock: Callable returning the current UTC ``datetime``.
            sleep: Async callable ``sleep(seconds)``; defaults to ``asyncio.sleep``.
            random: Source of ``uniform(0, jitter_s)``; defaults to ``random.Random()``.
            max_sleep_s: Maximum duration of a single sleep call in seconds (default 60).
            on_resume: Optional callback invoked once before any job when a wake arrives
                more than 60 seconds after its sleep was due to end.
        """
        if max_sleep_s <= 0:
            message = "max_sleep_s must be positive"
            raise ValueError(message)
        self._jobs: tuple[Job[Any], ...] = tuple(jobs)
        self._clock = clock
        self._sleep = sleep
        self._random: RandomSource = random if random is not None else secrets.SystemRandom()
        self._max_sleep_s = float(max_sleep_s)
        self._on_resume = on_resume
        self._on_resume_arity = _arity(on_resume) if on_resume is not None else 0
        self._schedules: list[_JobSchedule] = [_JobSchedule() for _ in self._jobs]
        self._running: set[str] = set()

    def _refresh_due(self, index: int, now: datetime) -> datetime | None:
        job = self._jobs[index]
        sched = self._schedules[index]
        candidate = job.due_at(now)
        if (
            candidate is not None
            and sched.last_completed_due is not None
            and candidate <= sched.last_completed_due
        ):
            candidate = job.due_at(sched.last_completed_due + _MICROSECOND)
            if candidate is not None and candidate <= sched.last_completed_due:
                candidate = None
        if candidate is None:
            sched.base_due = None
            sched.effective_due = None
            return None
        if candidate != sched.base_due or sched.effective_due is None:
            delay_s = (
                max(0.0, float(self._random.uniform(0.0, float(job.jitter_s))))
                if job.jitter_s > 0
                else 0.0
            )
            sched.base_due = candidate
            sched.effective_due = candidate + timedelta(seconds=delay_s)
        return sched.effective_due

    async def _execute_job(self, index: int, now: datetime) -> None:
        job = self._jobs[index]
        if job.name in self._running:
            return
        sched = self._schedules[index]
        completed_base = sched.base_due
        self._running.add(job.name)
        try:
            await job.execute(now)
        except Exception as exc:  # noqa: BLE001 - isolate job failures so the scheduler continues
            LOGGER.error("job %s failed with %s", job.name, type(exc).__name__)  # noqa: TRY400 - log error class only
            if job.on_error is not None:
                try:
                    await _maybe_await(job.on_error(self._clock(), exc))
                except Exception as hook_exc:  # noqa: BLE001 - error hook must not stop loop
                    LOGGER.error(  # noqa: TRY400 - log error class only
                        "job %s error hook failed with %s", job.name, type(hook_exc).__name__
                    )
        finally:
            self._running.discard(job.name)
            sched.last_completed_due = completed_base
            sched.base_due = None
            sched.effective_due = None

    async def step(self, stop: asyncio.Event | None = None) -> None:
        """Run every job currently due at ``clock()``, one at a time in due order."""
        now = self._clock()
        due: list[tuple[datetime, int]] = []
        for index, job in enumerate(self._jobs):
            if job.name in self._running:
                continue
            effective = self._refresh_due(index, now)
            if effective is not None and effective <= now:
                due.append((effective, index))
        due.sort()
        for _effective, index in due:
            if stop is not None and stop.is_set():
                return
            await self._execute_job(index, self._clock())

    async def _run_resume(self, now: datetime) -> None:
        if self._on_resume is None:
            return
        try:
            if self._on_resume_arity >= 1:
                await _maybe_await(self._on_resume(now))
            else:
                await _maybe_await(self._on_resume())
        except Exception as exc:  # noqa: BLE001 - resume cycle failure must not crash loop
            LOGGER.error("resume callback failed with %s", type(exc).__name__)  # noqa: TRY400 - log error class only

    async def run(self, stop: asyncio.Event) -> None:
        """Run the scheduling loop until ``stop`` is set."""
        while not stop.is_set():
            await self.step(stop)
            if stop.is_set():
                break

            now = self._clock()
            next_times = [
                effective
                for index in range(len(self._jobs))
                if (effective := self._refresh_due(index, now)) is not None
            ]
            if next_times:
                until_next_s = max(0.0, (min(next_times) - now).total_seconds())
                sleep_s = min(self._max_sleep_s, until_next_s)
            else:
                sleep_s = self._max_sleep_s

            if sleep_s <= 0:
                continue

            expected_wake = now + timedelta(seconds=sleep_s)
            if self._sleep is not None:
                await self._sleep(sleep_s)
            else:
                await _sleep_until_stopped(sleep_s, stop)

            if stop.is_set():
                break

            woke_at = self._clock()
            gap_s = (woke_at - expected_wake).total_seconds()
            if gap_s > RESUME_GAP_S:
                total_offline_m = max(1, round((woke_at - now).total_seconds() / 60))
                LOGGER.info("resumed after %d minutes", total_offline_m)
                await self._run_resume(woke_at)
