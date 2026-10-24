# src/weatherbot/services/schedule.py
"""The monitor's scheduled jobs, watches, retries, degraded-data alarm, and heartbeat task.

``MonitorSchedule`` wires the six monitor jobs (``startup``, ``window``, ``roster``,
``alerts``, ``confirm``, and ``retry``) onto ``Scheduler``, shares one
``MemoryValidatorStore`` and a 60-second in-memory roster cache across the watches, drives
the degraded-data alarm and its recovery through ``NotificationService``, and runs the
independent process heartbeat task while jobs execute.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, Literal

from sqlalchemy import Engine

from weatherbot.models import (
    AdvisoryNumber,
    AlertLevel,
    Location,
    MapCatalog,
    SourceId,
    StormSlot,
    StormSummary,
)
from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.health import staleness
from weatherbot.services.locks import held
from weatherbot.services.monitor import (
    SCHEDULED_SOURCE_CADENCE_S,
    CycleListener,
    CycleResult,
    CycleRunner,
    CycleTrigger,
    MonitorService,
)
from weatherbot.services.network import FetcherFactory, Network
from weatherbot.services.notifications import Channel, NotificationService
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    Heartbeat,
    HeartbeatRepository,
    LocationRepository,
    SettingsRepository,
    SnapshotRepository,
)
from weatherbot.services.scheduler import (
    MAX_SLEEP_S,
    Job,
    RandomSource,
    Scheduler,
)
from weatherbot.sources import arcgis, nhc_current_storms, nhc_map, nws
from weatherbot.sources.errors import SourceError
from weatherbot.sources.http import Fetcher, MemoryValidatorStore

LOGGER: Final = logging.getLogger("weatherbot.services.schedule")

PRODUCT_HOURS: Final = (0, 3, 6, 9, 12, 15, 18, 21)
WINDOW_OFFSET_MINUTES: Final = 15
ROSTER_CACHE_TTL_S: Final = 60.0
WATCH_JITTER_S: Final = 30.0

LADDER_SOURCES: Final[tuple[SourceId, ...]] = (
    "nhc-current-storms",
    "nhc-map-tropical-summary",
    "nws-alerts-point",
    "nws-alerts-zone",
)
WATCH_NAMES: Final = ("roster", "alerts")

FALLBACK_HEARTBEAT_CADENCE_S: Final = 3600
FALLBACK_WAIT_S: Final = 180.0
FALLBACK_POLL_S: Final = 5.0
STALE_MONITOR_NOTIFIED_KEY: Final = "monitor.stale_notified_since"
STALE_FALLBACK_NOTIFIED_KEY: Final = "monitor.fallback_stale_notified_since"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_utc(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def product_times_from(anchor: datetime) -> tuple[datetime, ...]:
    """Return the UTC product instants around ``anchor``'s day, in order."""
    utc_anchor = anchor.astimezone(UTC)
    day_start = utc_anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    return tuple(
        (day_start + timedelta(days=day_offset)).replace(hour=hour)
        for day_offset in (-1, 0, 1)
        for hour in PRODUCT_HOURS
    )


def next_product_time_for_window(
    now: datetime, offset_minutes: int = WINDOW_OFFSET_MINUTES
) -> datetime:
    """Return the earliest UTC product instant ``T`` whose ``T + offset_minutes`` is >= ``now``."""
    utc_now = now.astimezone(UTC)
    offset = timedelta(minutes=offset_minutes)
    for candidate in product_times_from(utc_now):
        if candidate + offset >= utc_now:
            return candidate
    return (utc_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def next_product_time_after(product_time: datetime) -> datetime:
    """Return the next UTC product instant strictly after ``product_time``."""
    utc_time = product_time.astimezone(UTC)
    for candidate in product_times_from(utc_time):
        if candidate > utc_time:
            return candidate
    return (utc_time + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _roster_signature(
    storms: Sequence[StormSummary],
) -> frozenset[tuple[str, str, str | None, str | None]]:
    return frozenset(
        (
            storm.atcf_id,
            storm.slot,
            str(storm.public_advisory.advisory) if storm.public_advisory.advisory else None,
            str(storm.track_cone.advisory)
            if storm.track_cone and storm.track_cone.advisory
            else None,
        )
        for storm in storms
    )


def _window_agreed(
    storms: Sequence[StormSummary],
    cone_advisories: Mapping[StormSlot, AdvisoryNumber],
    product_time: datetime,
) -> bool:
    """Return whether every storm's public advisory is >= ``product_time`` and matches the cone."""
    for storm in storms:
        pub = storm.public_advisory
        if pub.advisory is None or pub.issued_at < product_time:
            return False
        if cone_advisories.get(storm.slot) != pub.advisory:
            return False
    return True


def _cycle_had_ladder_failure(result: CycleResult) -> bool:
    if result.status in ("error", "failed"):
        return True
    if result.snapshot is None:
        return False
    return any(
        outcome.source_id in LADDER_SOURCES and outcome.status == "failed"
        for outcome in result.snapshot.source_outcomes
    )


@dataclass(slots=True)
class _RosterCacheEntry:
    fetched_at: datetime
    storms: tuple[StormSummary, ...]


class MonitorSchedule:
    """State and jobs of one running monitor process (``serve`` or ``check``)."""

    def __init__(  # noqa: PLR0913 - monitor wiring takes database, paths, settings, and seams
        self,
        engine: Engine,
        paths: AppPaths,
        *,
        settings: Settings | None = None,
        runner: CycleRunner = "serve",
        clock: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        random: RandomSource | None = None,
        make_fetcher: FetcherFactory | None = None,
        channels: Sequence[Channel] | None = None,
        listeners: Sequence[CycleListener] = (),
        run_startup: bool = True,
    ) -> None:
        """Create the monitor schedule and its jobs."""
        self._engine = engine
        self._paths = paths
        self._settings = settings or Settings()
        self._runner: CycleRunner = runner
        self._clock = clock
        self._sleep = sleep
        self._random = random
        self._channels = channels
        self._listeners: tuple[CycleListener, ...] = tuple(listeners)
        self._validators = MemoryValidatorStore()
        self._network = (
            Network(timeout_seconds=self._settings.http.timeout_seconds)
            if make_fetcher is None
            else Network(
                timeout_seconds=self._settings.http.timeout_seconds,
                make_fetcher=make_fetcher,
            )
        )
        self._roster_cache: _RosterCacheEntry | None = None
        self._summary_catalog: MapCatalog | None = None

        initial_now = self._clock()
        self._startup_pending = run_startup
        self._startup_due = initial_now
        self._product_time = next_product_time_for_window(
            initial_now, self._settings.monitor.window_offset_minutes
        )
        self._window_poll_due: datetime | None = None
        self._last_roster_at: datetime = initial_now
        self._last_alerts_at: datetime = initial_now
        self._confirm_at: datetime | None = None
        self._retry_at: datetime | None = None
        self._retries_used: int = 0

        self._first_failure_at: dict[tuple[str, str], datetime] = {}
        self._alarmed: dict[tuple[str, str], bool] = {}
        self._toast_delivered: dict[tuple[str, str], bool] = {}

        self.window_job = Job(
            name="window",
            next_due=self.next_window_due,
            run=self.run_window,
            jitter_s=float(self._settings.monitor.window_jitter_seconds),
            on_error=self._on_job_error("window"),
        )
        self._roster_job = Job(
            name="roster",
            next_due=self.next_roster_due,
            run=self.run_roster,
            jitter_s=WATCH_JITTER_S,
            on_error=self._on_job_error("roster"),
        )
        self._alerts_job = Job(
            name="alerts",
            next_due=self.next_alerts_due,
            run=self.run_alerts,
            jitter_s=WATCH_JITTER_S,
            on_error=self._on_job_error("alerts"),
        )
        self._confirm_job = Job(
            name="confirm",
            next_due=self.next_confirm_due,
            run=self.run_confirm,
            jitter_s=0.0,
            on_error=self._on_job_error("confirm"),
        )
        self._retry_job = Job(
            name="retry",
            next_due=self.next_retry_due,
            run=self.run_retry,
            jitter_s=0.0,
            on_error=self._on_job_error("retry"),
        )
        self._startup_job = Job(
            name="startup",
            next_due=self.next_startup_due,
            run=self.run_startup,
            jitter_s=0.0,
            on_error=self._on_job_error("startup"),
        )

    @property
    def jobs(self) -> tuple[Job[None], ...]:
        """The monitor's scheduled jobs."""
        return (
            self._startup_job,
            self.window_job,
            self._roster_job,
            self._alerts_job,
            self._confirm_job,
            self._retry_job,
        )

    def scheduler(self, *, max_sleep_s: float = MAX_SLEEP_S) -> Scheduler:
        """Build a ``Scheduler`` over this monitor's jobs and resume callback."""
        return Scheduler(
            self.jobs,
            clock=self._clock,
            sleep=self._sleep,
            random=self._random,
            max_sleep_s=max_sleep_s,
            on_resume=self.run_resume,
        )

    def _heartbeats(self) -> HeartbeatRepository:
        return HeartbeatRepository(self._engine, now=self._clock)

    def _on_job_error(self, job_name: str) -> Callable[[datetime, Exception], Awaitable[None]]:
        async def _record(now: datetime, exc: Exception) -> None:
            kind = "watch" if job_name in WATCH_NAMES else "runner"
            name = job_name if job_name in WATCH_NAMES else self._runner
            self._heartbeats().record(
                kind,
                name,
                at=now,
                result="failure",
                error_kind=type(exc).__name__,
            )
            await self._check_degraded_alarms(now, cycle_id=None)

        return _record

    def _latest_levels_and_locations(self) -> tuple[int, list[Location]]:
        """Return the highest latest stored alert level and the US locations above level 1."""
        max_level = 1
        relevant_us: list[Location] = []
        locations = LocationRepository(self._engine, now=self._clock).list()
        assessments = AssessmentRepository(self._engine, now=self._clock)
        for location in locations:
            latest = assessments.latest(location.name)
            if latest is None:
                continue
            level = int(latest.assessment.level)
            max_level = max(max_level, level)
            if level > int(AlertLevel.ALL_CLEAR) and location.nws is not None:
                relevant_us.append(location)
        return max_level, relevant_us

    def _clear_idle_alerts_cadence(self, now: datetime) -> None:
        heartbeats = self._heartbeats()
        row = next(
            (r for r in heartbeats.rows() if r.kind == "watch" and r.name == "alerts"),
            None,
        )
        if row is None or row.expected_every_s is None:
            return
        heartbeats.record(
            "watch",
            "alerts",
            at=min(row.last_attempt_at, now),
            result="attempt",
            expected_every_s=None,
        )

    def _record_source_heartbeat(
        self, source_id: SourceId, now: datetime, *, ok: bool, error_kind: str | None = None
    ) -> None:
        self._heartbeats().record(
            "source",
            source_id,
            at=now,
            result="success" if ok else "failure",
            error_kind=error_kind,
            expected_every_s=SCHEDULED_SOURCE_CADENCE_S,
        )

    def _record_watch_heartbeat(
        self,
        name: str,
        now: datetime,
        *,
        ok: bool,
        expected_every_s: int | None,
        error_kind: str | None = None,
    ) -> None:
        self._heartbeats().record(
            "watch",
            name,
            at=now,
            result="success" if ok else "failure",
            error_kind=error_kind,
            expected_every_s=expected_every_s,
        )

    async def _fetch_roster_shared(
        self, fetcher: Fetcher, now: datetime
    ) -> tuple[StormSummary, ...]:
        """Return the roster, reusing an answer fetched less than 60 seconds ago."""
        if (
            self._roster_cache is not None
            and 0 <= (now - self._roster_cache.fetched_at).total_seconds() < ROSTER_CACHE_TTL_S
        ):
            return self._roster_cache.storms
        try:
            result = await nhc_current_storms.fetch_current_storms(fetcher)
        except SourceError as exc:
            self._record_source_heartbeat(
                "nhc-current-storms", now, ok=False, error_kind=type(exc).__name__
            )
            raise
        self._record_source_heartbeat("nhc-current-storms", now, ok=True)
        self._roster_cache = _RosterCacheEntry(fetched_at=now, storms=result.records)
        return result.records

    async def _fetch_cone_advisories(
        self, fetcher: Fetcher, now: datetime
    ) -> Mapping[StormSlot, AdvisoryNumber]:
        try:
            if self._summary_catalog is None:
                cat_result = await arcgis.fetch_catalog(fetcher, arcgis.TROPICAL_SUMMARY)
                self._summary_catalog = cat_result.records
            advisories = await nhc_map.fetch_cone_advisories(fetcher, self._summary_catalog)
        except SourceError as exc:
            self._summary_catalog = None
            self._record_source_heartbeat(
                "nhc-map-tropical-summary", now, ok=False, error_kind=type(exc).__name__
            )
            raise
        self._record_source_heartbeat("nhc-map-tropical-summary", now, ok=True)
        return advisories.records

    async def _check_degraded_alarms(self, now: datetime, *, cycle_id: int | None) -> None:
        threshold = self._settings.monitor.degraded_after_failures
        max_level, _ = self._latest_levels_and_locations()
        quiet_hours = self._settings.notifications.quiet_hours(local_zone=now.astimezone().tzinfo)
        quiet_holds_toast = (
            quiet_hours is not None
            and quiet_hours.contains(now)
            and max_level <= int(AlertLevel.TROPICAL_STORM_THREAT)
        )

        records: tuple[Heartbeat, ...] = self._heartbeats().rows()
        notifications = NotificationService(
            self._engine,
            settings=self._settings,
            now=self._clock,
            channels=self._channels,
        )

        for row in records:
            monitored = (row.kind == "source" and row.name in LADDER_SOURCES) or (
                row.kind == "watch" and row.name in WATCH_NAMES
            )
            if not monitored:
                continue
            key = (row.kind, row.name)
            if row.consecutive_failures > 0:
                if key not in self._first_failure_at or row.consecutive_failures == 1:
                    self._first_failure_at[key] = row.last_attempt_at
                if row.consecutive_failures >= threshold and not self._alarmed.get(key, False):
                    since = self._first_failure_at.get(key) or row.last_attempt_at
                    title = (
                        f"Weatherbot: {row.name} failed {row.consecutive_failures} times "
                        f"in a row since {_iso_utc(since)}; levels may read as floors."
                    )
                    sent = await notifications.send(
                        "degraded",
                        title=title,
                        body=(title,),
                        cycle_id=cycle_id,
                        include_toast=not quiet_holds_toast,
                    )
                    self._alarmed[key] = True
                    self._toast_delivered[key] = any(
                        d.channel == "toast" and d.result == "delivered" for d in sent.deliveries
                    )
            else:
                self._first_failure_at.pop(key, None)
                if self._alarmed.pop(key, False):
                    degraded_toasted = self._toast_delivered.pop(key, False)
                    title = f"Weatherbot: {row.name} recovered at {_iso_utc(now)}."
                    await notifications.send(
                        "recovered",
                        title=title,
                        body=(title,),
                        cycle_id=cycle_id,
                        include_toast=degraded_toasted and not quiet_holds_toast,
                    )

    async def execute_cycle(self, trigger: CycleTrigger) -> CycleResult:
        """Run one monitor cycle for ``trigger`` and update schedule state."""
        for row in self._heartbeats().rows():
            if (
                row.kind == "source"
                and row.name in LADDER_SOURCES
                and row.consecutive_failures == 1
            ):
                self._first_failure_at.setdefault((row.kind, row.name), row.last_attempt_at)

        service = MonitorService(
            self._engine,
            paths=self._paths,
            settings=self._settings,
            runner=self._runner,
            network=self._network,
            now=self._clock,
            listeners=self._listeners,
            cadence_s=SCHEDULED_SOURCE_CADENCE_S,
            channels=self._channels,
        )
        result = await service.run_cycle(trigger)
        now = self._clock()

        if result.snapshot is not None:
            nhc_ok = any(
                o.source_id == "nhc-current-storms" and o.status in ("ok", "not_modified")
                for o in result.snapshot.source_outcomes
            )
            if nhc_ok:
                self._roster_cache = _RosterCacheEntry(
                    fetched_at=result.completed_at,
                    storms=tuple(
                        product.summary
                        for product in result.snapshot.storms
                        if product.summary is not None
                    ),
                )

        if result.confirm_at is not None:
            self._confirm_at = result.confirm_at

        if result.status != "skipped":
            self._last_roster_at = now
            self._last_alerts_at = now
            if _cycle_had_ladder_failure(result):
                if self._retries_used < self._settings.monitor.retry_count:
                    delay_m = self._settings.monitor.retry_base_minutes * (2**self._retries_used)
                    self._retries_used += 1
                    self._retry_at = now + timedelta(minutes=delay_m)
                else:
                    self._retry_at = None
            else:
                self._retries_used = 0
                self._retry_at = None

        _, relevant_us = self._latest_levels_and_locations()
        if not relevant_us:
            self._clear_idle_alerts_cadence(now)

        await self._check_degraded_alarms(now, cycle_id=result.cycle_id)
        return result

    # Job callbacks -------------------------------------------------------------------------

    def next_startup_due(self, _now: datetime) -> datetime | None:
        """Return the ``startup`` job's due instant while startup is pending."""
        return self._startup_due if self._startup_pending else None

    async def run_startup(self, _now: datetime) -> None:
        """Run the one-shot ``startup`` cycle."""
        self._startup_pending = False
        await self.execute_cycle("startup")

    async def run_resume(self, now: datetime) -> None:
        """Advance past elapsed windows and run the ``resume`` cycle after a wake gap."""
        self._startup_pending = False
        self._window_poll_due = None
        while (
            self._product_time + timedelta(minutes=self._settings.monitor.window_close_minutes)
            <= now
        ):
            self._product_time = next_product_time_after(self._product_time)
        self.window_job.jitter_s = float(self._settings.monitor.window_jitter_seconds)
        self._last_roster_at = now
        self._last_alerts_at = now
        await self.execute_cycle("resume")

    def next_window_due(self, _now: datetime) -> datetime | None:
        """Return the ``window`` job's next due instant."""
        if self._window_poll_due is not None:
            return self._window_poll_due
        return self._product_time + timedelta(minutes=self._settings.monitor.window_offset_minutes)

    def _close_window(self) -> None:
        self._window_poll_due = None
        self._product_time = next_product_time_after(self._product_time)
        self.window_job.jitter_s = float(self._settings.monitor.window_jitter_seconds)

    async def run_window(self, now: datetime) -> None:
        """Poll the roster and cone layer once or run the ``window`` cycle."""
        window_close = self._product_time + timedelta(
            minutes=self._settings.monitor.window_close_minutes
        )
        if now >= window_close:
            self._close_window()
            await self.execute_cycle("window")
            return

        agreed = False
        no_storms = False
        try:
            async with self._network.fetcher(self._validators) as fetcher:
                storms = await self._fetch_roster_shared(fetcher, now)
                if not storms:
                    no_storms = True
                else:
                    cone_advisories = await self._fetch_cone_advisories(fetcher, now)
                    agreed = _window_agreed(storms, cone_advisories, self._product_time)
        except SourceError as exc:
            LOGGER.warning("window poll failed (%s): %s", exc.source_id, type(exc).__name__)
            await self._check_degraded_alarms(now, cycle_id=None)

        if no_storms or agreed:
            self._close_window()
            await self.execute_cycle("window")
            return

        next_poll = min(
            now + timedelta(minutes=self._settings.monitor.roster_poll_minutes),
            window_close,
        )
        if next_poll <= now:
            self._close_window()
            await self.execute_cycle("window")
            return
        self._window_poll_due = next_poll
        self.window_job.jitter_s = 0.0

    def _roster_interval_minutes(self) -> int:
        max_level, _ = self._latest_levels_and_locations()
        if max_level > int(AlertLevel.ALL_CLEAR):
            return self._settings.monitor.roster_interval_relevant_minutes
        return self._settings.monitor.roster_interval_minutes

    def next_roster_due(self, _now: datetime) -> datetime | None:
        """Return the ``roster`` watch's next due instant."""
        interval_m = self._roster_interval_minutes()
        return self._last_roster_at + timedelta(minutes=interval_m)

    async def run_roster(self, now: datetime) -> None:
        """Poll ``CurrentStorms.json`` and run a ``roster`` cycle when changed."""
        interval_m = self._roster_interval_minutes()
        expected_every_s = interval_m * 60
        self._last_roster_at = now
        try:
            async with self._network.fetcher(self._validators) as fetcher:
                storms = await self._fetch_roster_shared(fetcher, now)
        except SourceError as exc:
            LOGGER.warning("roster watch failed (%s): %s", exc.source_id, type(exc).__name__)
            self._record_watch_heartbeat(
                "roster",
                now,
                ok=False,
                expected_every_s=expected_every_s,
                error_kind=type(exc).__name__,
            )
            await self._check_degraded_alarms(now, cycle_id=None)
            return

        self._record_watch_heartbeat("roster", now, ok=True, expected_every_s=expected_every_s)
        await self._check_degraded_alarms(now, cycle_id=None)

        latest = SnapshotRepository(self._engine).latest()
        stored_storms = (
            tuple(product.summary for product in latest.storms if product.summary is not None)
            if latest is not None
            else ()
        )
        if latest is None or _roster_signature(storms) != _roster_signature(stored_storms):
            await self.execute_cycle("roster")
            self._last_roster_at = self._clock()

    def next_alerts_due(self, _now: datetime) -> datetime | None:
        """Return the ``alerts`` watch's next due instant, or ``None`` when idle."""
        _, relevant_us = self._latest_levels_and_locations()
        if not relevant_us:
            return None
        interval_m = self._settings.monitor.alert_interval_minutes
        return self._last_alerts_at + timedelta(minutes=interval_m)

    async def run_alerts(self, now: datetime) -> None:
        """Poll NWS alerts for US locations above level 1 and run an ``alerts`` cycle on change."""
        _, relevant_us = self._latest_levels_and_locations()
        if not relevant_us:
            self._clear_idle_alerts_cadence(now)
            return

        interval_m = self._settings.monitor.alert_interval_minutes
        expected_every_s = interval_m * 60
        self._last_alerts_at = now
        fetched_by_location: dict[str, frozenset[tuple[str, datetime]]] = {}
        try:
            async with self._network.fetcher(self._validators) as fetcher:
                for location in relevant_us:
                    result = await nws.fetch_alerts(fetcher, location)
                    fetched_by_location[location.name] = frozenset(
                        (alert.id, alert.sent) for alert in result.records
                    )
        except SourceError as exc:
            LOGGER.warning("alerts watch failed (%s): %s", exc.source_id, type(exc).__name__)
            self._record_source_heartbeat(
                exc.source_id, now, ok=False, error_kind=type(exc).__name__
            )
            self._record_watch_heartbeat(
                "alerts",
                now,
                ok=False,
                expected_every_s=expected_every_s,
                error_kind=type(exc).__name__,
            )
            await self._check_degraded_alarms(now, cycle_id=None)
            return

        self._record_watch_heartbeat("alerts", now, ok=True, expected_every_s=expected_every_s)
        await self._check_degraded_alarms(now, cycle_id=None)

        latest = SnapshotRepository(self._engine).latest()

        changed = False
        for location in relevant_us:
            stored_alerts = latest.alerts.get(location.name) if latest is not None else None
            stored_set = (
                frozenset((alert.id, alert.sent) for alert in stored_alerts)
                if stored_alerts is not None
                else None
            )
            if stored_set is None or fetched_by_location[location.name] != stored_set:
                changed = True
                break

        if changed:
            await self.execute_cycle("alerts")
            self._last_alerts_at = self._clock()

    def next_confirm_due(self, _now: datetime) -> datetime | None:
        """Return the ``confirm`` job's due instant when a drop is held."""
        return self._confirm_at

    async def run_confirm(self, _now: datetime) -> None:
        """Run the ``confirm`` cycle for a held drop."""
        self._confirm_at = None
        await self.execute_cycle("confirm")

    def next_retry_due(self, _now: datetime) -> datetime | None:
        """Return the ``retry`` job's due instant after a ladder failure."""
        return self._retry_at

    async def run_retry(self, _now: datetime) -> None:
        """Run a scheduled ``retry`` cycle."""
        self._retry_at = None
        await self.execute_cycle("retry")


async def _sleep_or_stop(
    seconds: float,
    stop: asyncio.Event,
    sleep: Callable[[float], Awaitable[None]] | None,
) -> None:
    if sleep is not None:
        await sleep(seconds)
        return
    sleep_task = asyncio.create_task(asyncio.sleep(seconds))
    stop_task = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait({sleep_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sleep_task, stop_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(sleep_task, stop_task, return_exceptions=True)


def _highest_stored_level(engine: Engine, clock: Callable[[], datetime]) -> int:
    max_level = 1
    locations = LocationRepository(engine, now=clock).list()
    assessments = AssessmentRepository(engine, now=clock)
    for location in locations:
        latest = assessments.latest(location.name)
        if latest is None:
            continue
        max_level = max(max_level, int(latest.assessment.level))
    return max_level


def _quiet_holds_toast(
    engine: Engine, settings: Settings, now: datetime, clock: Callable[[], datetime]
) -> bool:
    quiet_hours = settings.notifications.quiet_hours(local_zone=now.astimezone().tzinfo)
    if quiet_hours is None or not quiet_hours.contains(now):
        return False
    return _highest_stored_level(engine, clock) <= int(AlertLevel.TROPICAL_STORM_THREAT)


def _default_task_installed(task_name: str) -> bool:
    from weatherbot.services import tasks as tasks_service  # noqa: PLC0415 - avoids circular import

    if not tasks_service.ON_WINDOWS:
        return False
    try:
        found = tasks_service.query()
    except tasks_service.TaskSchedulerError:
        return False
    return any(item.name == task_name for item in found)


def _default_start_serve() -> None:
    from weatherbot.services import tasks as tasks_service  # noqa: PLC0415 - avoids circular import

    if not tasks_service.ON_WINDOWS:
        return
    try:
        tasks_service.run("serve")
    except (tasks_service.TaskSchedulerError, ValueError):
        return


async def _check_stale_fallback_row(  # noqa: PLR0913 - fallback watch state
    engine: Engine,
    now: datetime,
    *,
    clock: Callable[[], datetime],
    settings: Settings | None,
    channels: Sequence[Channel] | None,
    check_installed: Callable[[], bool] | bool | None,
) -> None:
    heartbeats = HeartbeatRepository(engine, now=clock)
    fallback_row = next(
        (r for r in heartbeats.rows() if r.kind == "runner" and r.name == "fallback"),
        None,
    )
    if fallback_row is None or fallback_row.expected_every_s is None:
        return
    settings_repo = SettingsRepository(engine)
    report = staleness([fallback_row], now)[0]
    if not report.stale:
        if settings_repo.get(STALE_FALLBACK_NOTIFIED_KEY):
            settings_repo.set(STALE_FALLBACK_NOTIFIED_KEY, "")
        return
    if isinstance(check_installed, bool):
        installed = check_installed
    elif check_installed is not None:
        installed = check_installed()
    else:
        installed = _default_task_installed("check")
    if not installed:
        return
    since = fallback_row.last_success_at or fallback_row.last_attempt_at
    since_text = _iso_utc(since)
    if settings_repo.get(STALE_FALLBACK_NOTIFIED_KEY) == since_text:
        return
    resolved_settings = settings or Settings()
    quiet_holds = _quiet_holds_toast(engine, resolved_settings, now, clock)
    title = f"Weatherbot: the hourly check has not run since {since_text}."
    notifications = NotificationService(
        engine,
        settings=resolved_settings,
        now=clock,
        channels=channels,
    )
    await notifications.send(
        "stale_monitor",
        title=title,
        body=(title,),
        include_toast=not quiet_holds,
    )
    settings_repo.set(STALE_FALLBACK_NOTIFIED_KEY, since_text)


async def run_heartbeat_task(  # noqa: PLR0913 - heartbeat loop parameters
    engine: Engine,
    runner: CycleRunner,
    *,
    heartbeat_minutes: int,
    stop: asyncio.Event,
    clock: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    settings: Settings | None = None,
    channels: Sequence[Channel] | None = None,
    check_installed: Callable[[], bool] | bool | None = None,
) -> None:
    """Record the runner's heartbeat every ``heartbeat_minutes`` and watch ``fallback``."""
    expected_every_s = heartbeat_minutes * 60
    heartbeats = HeartbeatRepository(engine, now=clock)
    settings_repo = SettingsRepository(engine)
    while not stop.is_set():
        now = clock()
        heartbeats.record(
            "runner",
            runner,
            at=now,
            result="success",
            expected_every_s=expected_every_s,
        )
        if runner in ("serve", "check") and settings_repo.get(STALE_MONITOR_NOTIFIED_KEY):
            settings_repo.set(STALE_MONITOR_NOTIFIED_KEY, "")
        if runner == "serve":
            await _check_stale_fallback_row(
                engine,
                now,
                clock=clock,
                settings=settings,
                channels=channels,
                check_installed=check_installed,
            )
        if stop.is_set():
            break
        await _sleep_or_stop(float(expected_every_s), stop, sleep)


def clear_runner_heartbeat_cadence(engine: Engine, runner: CycleRunner, *, now: datetime) -> None:
    """Clear the runner heartbeat's ``expected_every_s`` on a clean stop."""
    HeartbeatRepository(engine, now=lambda: now).record(
        "runner",
        runner,
        at=now,
        result="success",
        expected_every_s=None,
    )


type FallbackReason = Literal["monitor_fresh", "not_running", "not_responding", "unscheduled"]


@dataclass(frozen=True)
class FallbackResult:
    """The outcome of ``weatherbot check --once --if-stale``."""

    ran_cycle: bool
    cycle: CycleResult | None
    alarmed: bool
    started_serve: bool
    reason: FallbackReason


def _active_monitor_row(rows: Sequence[Heartbeat]) -> Heartbeat | None:
    runner_rows = [r for r in rows if r.kind == "runner" and r.name in ("serve", "check")]
    if not runner_rows:
        return None
    serve_rows = [r for r in runner_rows if r.name == "serve"]
    return serve_rows[0] if serve_rows else runner_rows[0]


def _runner_is_fresh(row: Heartbeat | None, now: datetime) -> bool:
    if row is None or row.expected_every_s is None or row.last_success_at is None:
        return False
    return not staleness([row], now)[0].stale


def _resolve_task_installed(*, seam: Callable[[], bool] | bool | None, task_name: str) -> bool:
    if isinstance(seam, bool):
        return seam
    if seam is not None:
        return seam()
    return _default_task_installed(task_name)


async def _wait_for_fresh_monitor(  # noqa: PLR0913 - wait loop parameters
    heartbeats: HeartbeatRepository,
    lock_path: Path,
    *,
    clock: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[None]] | None,
    lock_held: Callable[[Path], bool],
    wait_s: float,
    poll_s: float,
) -> tuple[bool, bool, Heartbeat | None]:
    deadline = clock() + timedelta(seconds=wait_s)
    currently_held = lock_held(lock_path)
    while currently_held:
        now = clock()
        row = _active_monitor_row(heartbeats.rows())
        if _runner_is_fresh(row, now):
            return True, True, row
        remaining = (deadline - now).total_seconds()
        if remaining <= 0:
            break
        step = min(poll_s, remaining)
        if sleep is not None:
            await sleep(step)
        else:
            await asyncio.sleep(step)
        currently_held = lock_held(lock_path)
    now = clock()
    row = _active_monitor_row(heartbeats.rows())
    return currently_held and _runner_is_fresh(row, now), currently_held, row


def _fallback_classification(
    *, currently_held: bool, installed: bool
) -> tuple[FallbackReason, str, bool, bool]:
    if currently_held:
        return (
            "not_responding",
            "Weatherbot: the monitor is not responding; a check ran instead.",
            True,
            False,
        )
    if installed:
        return (
            "not_running",
            "Weatherbot: the monitor is not running; a check ran instead.",
            True,
            True,
        )
    return ("unscheduled", "", False, False)


async def run_fallback_check(  # noqa: PLR0913 - fallback check orchestration
    engine: Engine,
    paths: AppPaths,
    *,
    settings: Settings | None = None,
    clock: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    make_fetcher: FetcherFactory | None = None,
    channels: Sequence[Channel] | None = None,
    listeners: Sequence[CycleListener] = (),
    lock_held: Callable[[Path], bool] = held,
    serve_installed: Callable[[], bool] | bool | None = None,
    start_serve: Callable[[], object] | None = None,
    wait_s: float = FALLBACK_WAIT_S,
    poll_s: float = FALLBACK_POLL_S,
) -> FallbackResult:
    """Run ``check --once --if-stale``: wait for a held monitor, alarm, and run a cycle."""
    resolved_settings = settings or Settings()
    heartbeats = HeartbeatRepository(engine, now=clock)
    settings_repo = SettingsRepository(engine)

    fresh, currently_held, row = await _wait_for_fresh_monitor(
        heartbeats,
        paths.monitor_lock_path,
        clock=clock,
        sleep=sleep,
        lock_held=lock_held,
        wait_s=wait_s,
        poll_s=poll_s,
    )
    now = clock()
    if fresh:
        LOGGER.info("fallback_skipped_monitor_healthy")
        if settings_repo.get(STALE_MONITOR_NOTIFIED_KEY):
            settings_repo.set(STALE_MONITOR_NOTIFIED_KEY, "")
        heartbeats.record(
            "runner",
            "fallback",
            at=now,
            result="success",
            expected_every_s=FALLBACK_HEARTBEAT_CADENCE_S,
        )
        return FallbackResult(
            ran_cycle=False,
            cycle=None,
            alarmed=False,
            started_serve=False,
            reason="monitor_fresh",
        )

    installed = _resolve_task_installed(seam=serve_installed, task_name="serve")
    marker = (
        f"since:{_iso_utc(row.last_success_at)}"
        if row is not None and row.last_success_at is not None
        else "since:never"
    )
    reason, title, should_alarm, should_start_serve = _fallback_classification(
        currently_held=currently_held, installed=installed
    )

    alarmed = False
    if should_alarm and settings_repo.get(STALE_MONITOR_NOTIFIED_KEY) != marker:
        quiet_holds = _quiet_holds_toast(engine, resolved_settings, now, clock)
        notifications = NotificationService(
            engine,
            settings=resolved_settings,
            now=clock,
            channels=channels,
        )
        await notifications.send(
            "stale_monitor",
            title=title,
            body=(title,),
            include_toast=not quiet_holds,
        )
        settings_repo.set(STALE_MONITOR_NOTIFIED_KEY, marker)
        alarmed = True

    started_serve = False
    if should_start_serve:
        if start_serve is not None:
            start_serve()
        else:
            _default_start_serve()
        started_serve = True

    network = (
        Network(timeout_seconds=resolved_settings.http.timeout_seconds)
        if make_fetcher is None
        else Network(
            timeout_seconds=resolved_settings.http.timeout_seconds,
            make_fetcher=make_fetcher,
        )
    )
    service = MonitorService(
        engine,
        paths=paths,
        settings=resolved_settings,
        runner="fallback",
        network=network,
        now=clock,
        listeners=listeners,
        cadence_s=SCHEDULED_SOURCE_CADENCE_S,
        channels=channels,
    )
    cycle = await service.run_cycle("fallback")
    heartbeats.record(
        "runner",
        "fallback",
        at=clock(),
        result="failure" if cycle.status == "error" else "success",
        error_kind="CycleError" if cycle.status == "error" else None,
        expected_every_s=FALLBACK_HEARTBEAT_CADENCE_S,
    )
    return FallbackResult(
        ran_cycle=True,
        cycle=cycle,
        alarmed=alarmed,
        started_serve=started_serve,
        reason=reason,
    )


async def run_monitor(  # noqa: PLR0913 - top-level monitor loop entry point
    engine: Engine,
    paths: AppPaths,
    *,
    settings: Settings,
    runner: CycleRunner,
    stop: asyncio.Event,
    clock: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    random: RandomSource | None = None,
    make_fetcher: FetcherFactory | None = None,
    channels: Sequence[Channel] | None = None,
    listeners: Sequence[CycleListener] = (),
    max_sleep_s: float = MAX_SLEEP_S,
    check_installed: Callable[[], bool] | bool | None = None,
) -> None:
    """Run the process heartbeat task and the ``MonitorSchedule`` loop until ``stop``."""
    clock_moved = asyncio.Event()

    async def _scheduler_sleep(seconds: float) -> None:
        if sleep is not None:
            await sleep(seconds)
        else:
            await asyncio.sleep(seconds)
        clock_moved.set()

    async def _heartbeat_sleep(seconds: float) -> None:
        if sleep is None:
            await asyncio.sleep(seconds)
            return
        target = clock() + timedelta(seconds=seconds)
        while not stop.is_set() and clock() < target:
            clock_moved.clear()
            if stop.is_set() or clock() >= target:
                break
            wait_clock = asyncio.create_task(clock_moved.wait())
            wait_stop = asyncio.create_task(stop.wait())
            try:
                await asyncio.wait({wait_clock, wait_stop}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in (wait_clock, wait_stop):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(wait_clock, wait_stop, return_exceptions=True)

    schedule = MonitorSchedule(
        engine,
        paths,
        settings=settings,
        runner=runner,
        clock=clock,
        sleep=_scheduler_sleep if sleep is not None else None,
        random=random,
        make_fetcher=make_fetcher,
        channels=channels,
        listeners=listeners,
    )
    sched = schedule.scheduler(max_sleep_s=max_sleep_s)
    heartbeat = asyncio.create_task(
        run_heartbeat_task(
            engine,
            runner,
            heartbeat_minutes=settings.monitor.heartbeat_minutes,
            stop=stop,
            clock=clock,
            sleep=_heartbeat_sleep if sleep is not None else None,
            settings=settings,
            channels=channels,
            check_installed=check_installed,
        )
    )
    try:
        await sched.run(stop)
    finally:
        stop.set()
        clock_moved.set()
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        clear_runner_heartbeat_cadence(engine, runner, now=clock())
