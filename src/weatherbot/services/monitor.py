# src/weatherbot/services/monitor.py
"""The monitor cycle: the one path that fetches, stores, assesses, and records.

``MonitorService.run_cycle(trigger)`` takes the cycle lock (``data_dir/cycle.lock``, held
by whichever process runs a cycle); records the cycle as started; fetches and stores a
snapshot through ``SnapshotService``, or uses a stored one it is handed (``status
--no-fetch``); assesses and stores every location through ``AssessmentService``, unless
told not to (``fetch``, ``storms``, and ``alerts`` decide nothing); records the
heartbeats and the cycle's end in one transaction; calls each listener with the result;
and gives the lock back. A cycle that waits past ``[monitor] cycle_lock_wait_seconds``
for another is recorded as ``skipped``; any exception is recorded as ``error`` with its
class name, and propagates. Every command that fetches goes through here, so one lock
covers every writer of a cycle.

The heartbeat rules: each source a fetching cycle asked about records an attempt; ``ok``
and ``not_modified`` are successes, ``failed`` a failure with its error kind, and
``skipped`` (a source not needed) records the attempt alone and clears the row's cadence,
so a source that is not needed is never stale and never failing. A cycle over a stored
snapshot records no source. Only a scheduled runner promises a cadence (``cadence_s``);
every other writer leaves a row's cadence as it is, so a manual command never makes data
look stale. The runner's own row records each completed cycle as its success.

Log records name the runner, the trigger, the cycle, the status, and counts; a failure
is named by its exception class, never its message, and never a coordinate, a distance,
a bearing, an instant of arrival, or a URL.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from weatherbot.models import Snapshot, SourceOutcome
from weatherbot.services.assessments import AssessedLocation, AssessmentService
from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.locks import LockBusyError, ProcessLock
from weatherbot.services.network import Network
from weatherbot.services.notifications import Channel, NotificationService, StoredNotification
from weatherbot.services.persistence.database import writing_session
from weatherbot.services.persistence.repositories import (
    UNCHANGED,
    CycleRepository,
    DriftWarning,
    HeartbeatRepository,
    HeartbeatResult,
    LocationRepository,
    Unchanged,
)
from weatherbot.services.snapshots import SnapshotService

LOGGER: Final = logging.getLogger("weatherbot.services.monitor")

type CycleTrigger = Literal[
    "manual", "window", "roster", "alerts", "confirm", "retry", "startup", "resume", "fallback"
]
type CycleRunner = Literal[
    "serve", "check", "check-once", "fallback", "status", "fetch", "storms", "alerts"
]
type CycleStatus = Literal["complete", "partial", "failed", "skipped", "error"]
type CycleListener = Callable[["CycleResult"], None]

LOCK_HELD: Final = "another cycle held the lock"
SCHEDULED_SOURCE_CADENCE_S: Final = 10_800
"""What a scheduled runner promises for each source: NHC's three-hour product spacing."""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class CycleResult:
    """One cycle's outcome: its record, its snapshot, and every location's assessment.

    ``snapshot`` is ``None`` only for a ``skipped`` cycle; ``assessed`` is empty when the
    cycle decided nothing.
    """

    cycle_id: int
    trigger: CycleTrigger
    runner: CycleRunner
    status: CycleStatus
    snapshot: Snapshot | None
    assessed: tuple[AssessedLocation, ...]
    drift_warnings: tuple[DriftWarning, ...]
    started_at: datetime
    completed_at: datetime
    notifications: tuple[StoredNotification, ...] = ()
    confirm_at: datetime | None = None


def _source_result(outcome: SourceOutcome) -> HeartbeatResult:
    if outcome.status in {"ok", "not_modified"}:
        return "success"
    return "failure" if outcome.status == "failed" else "attempt"


class MonitorService:
    """Runs monitor cycles, one at a time across every process."""

    def __init__(  # noqa: PLR0913 - the database, then the cycle's settings, keyword-only
        self,
        engine: Engine,
        *,
        paths: AppPaths,
        settings: Settings,
        runner: CycleRunner,
        network: Network | None = None,
        now: Callable[[], datetime] = _now,
        listeners: Sequence[CycleListener] = (),
        cadence_s: int | None = None,
        channels: Sequence[Channel] | None = None,
    ) -> None:
        """Create the service on an open database.

        Args:
            engine: The database.
            paths: Where the cycle lock lives.
            settings: The thresholds and the cycle lock's wait.
            runner: The process that runs the cycles, such as ``status`` or ``serve``.
            network: The timeout and the fetcher factory.
            now: The clock.
            listeners: Called with each cycle's result after it is stored.
            cadence_s: The cadence a scheduled runner promises for the sources its cycles
                fetch; ``None``, as for every manual command, promises none.
            channels: Delivery channels for notifications; defaults to ``LogChannel`` only.
        """
        self._engine = engine
        self._paths = paths
        self._settings = settings
        self._runner: CycleRunner = runner
        self._network = network or Network()
        self._now = now
        self._listeners = tuple(listeners)
        self._channels = channels
        self._cadence: int | Literal[Unchanged.CADENCE] = (
            cadence_s if cadence_s is not None else UNCHANGED
        )
        self._cycles = CycleRepository(engine)
        self._heartbeats = HeartbeatRepository(engine, now=now)

    async def run_cycle(
        self, trigger: CycleTrigger, *, snapshot: Snapshot | None = None, assess: bool = True
    ) -> CycleResult:
        """Run one cycle under the cycle lock.

        Args:
            trigger: Why the cycle runs.
            snapshot: A stored snapshot to use instead of fetching one.
            assess: Assess and store every location; ``False`` fetches and records only.

        Returns:
            The result; ``skipped`` when another cycle held the lock for the whole wait.

        Raises:
            BaseException: Whatever the cycle raised, after it is recorded as ``error``.
        """
        lock = ProcessLock(self._paths.cycle_lock_path)
        started = self._now()
        try:
            await lock.acquire_async(self._settings.monitor.cycle_lock_wait_seconds)
        except LockBusyError:
            result = self._skipped(trigger, started)
        else:
            try:
                result = await self._locked(trigger, started, snapshot, assess=assess)
            finally:
                lock.release()
        self._log(result)
        self._tell(result)
        return result

    async def _locked(
        self, trigger: CycleTrigger, started: datetime, given: Snapshot | None, *, assess: bool
    ) -> CycleResult:
        cycle_id = self._cycles.start(self._runner, trigger, at=started)
        try:
            locations = LocationRepository(self._engine).list()
            warnings: tuple[DriftWarning, ...] = ()
            snapshot = given
            if snapshot is None:
                snapshots = SnapshotService(self._engine, network=self._network, now=self._now)
                fetched = await snapshots.fetch_snapshot(locations)
                snapshot, warnings = fetched.snapshot, fetched.drift_warnings
            assessed: tuple[AssessedLocation, ...] = ()
            notifications: tuple[StoredNotification, ...] = ()
            confirm_at: datetime | None = None
            if assess:
                service = AssessmentService(
                    self._engine, thresholds=self._settings.engine.thresholds(), now=self._now
                )
                assessed = service.assess(snapshot, locations)
                notifier = NotificationService(
                    self._engine,
                    settings=self._settings,
                    now=self._now,
                    channels=self._channels,
                )
                notifications = await notifier.decide_cycle(cycle_id, assessed)
                confirm_at = notifier.confirm_at
            completed = self._now()
            with writing_session(self._engine) as session:
                if given is None:
                    self._record_sources(session, snapshot, completed)
                self._heartbeats.record(
                    "runner", self._runner, at=completed, result="success", session=session
                )
                self._cycles.finish(
                    cycle_id,
                    status=snapshot.status,
                    at=completed,
                    snapshot_id=snapshot.snapshot_id,
                    session=session,
                )
        except BaseException as error:
            self._record_error(cycle_id, error)
            raise
        return CycleResult(
            cycle_id=cycle_id,
            trigger=trigger,
            runner=self._runner,
            status=snapshot.status,
            snapshot=snapshot,
            assessed=assessed,
            drift_warnings=warnings,
            started_at=started,
            completed_at=completed,
            notifications=notifications,
            confirm_at=confirm_at,
        )

    def _record_sources(self, session: Session, snapshot: Snapshot, at: datetime) -> None:
        for outcome in snapshot.source_outcomes:
            result = _source_result(outcome)
            self._heartbeats.record(
                "source",
                outcome.source_id,
                at=at,
                result=result,
                error_kind=outcome.error_kind,
                expected_every_s=None if outcome.status == "skipped" else self._cadence,
                session=session,
            )

    def _skipped(self, trigger: CycleTrigger, started: datetime) -> CycleResult:
        cycle_id = self._cycles.start(self._runner, trigger, at=started)
        completed = self._now()
        with writing_session(self._engine) as session:
            self._heartbeats.record(
                "runner", self._runner, at=completed, result="attempt", session=session
            )
            self._cycles.finish(
                cycle_id, status="skipped", at=completed, detail=LOCK_HELD, session=session
            )
        return CycleResult(
            cycle_id=cycle_id,
            trigger=trigger,
            runner=self._runner,
            status="skipped",
            snapshot=None,
            assessed=(),
            drift_warnings=(),
            started_at=started,
            completed_at=completed,
        )

    def _record_error(self, cycle_id: int, error: BaseException) -> None:
        """Record a cycle that raised, by the exception's class; the cycle's error wins."""
        kind = type(error).__name__
        try:
            completed = self._now()
            with writing_session(self._engine) as session:
                self._heartbeats.record(
                    "runner",
                    self._runner,
                    at=completed,
                    result="failure",
                    error_kind=kind,
                    session=session,
                )
                self._cycles.finish(
                    cycle_id, status="error", at=completed, detail=kind, session=session
                )
        except Exception as failure:  # noqa: BLE001 - the cycle's own exception propagates instead
            LOGGER.warning(
                "cycle %d: could not record its %s (%s)", cycle_id, kind, type(failure).__name__
            )
        LOGGER.warning("cycle %d (%s): error %s", cycle_id, self._runner, kind)

    def _log(self, result: CycleResult) -> None:
        LOGGER.info(
            "cycle %d (%s, %s): %s; %d locations assessed, %d drift warnings%s",
            result.cycle_id,
            result.runner,
            result.trigger,
            result.status,
            len(result.assessed),
            len(result.drift_warnings),
            f" ({LOCK_HELD})" if result.status == "skipped" else "",
        )

    def _tell(self, result: CycleResult) -> None:
        for listener in self._listeners:
            try:
                listener(result)
            except Exception as error:  # noqa: BLE001 - one listener's failure never fails the cycle
                LOGGER.warning(
                    "cycle %d: a listener failed (%s)", result.cycle_id, type(error).__name__
                )
