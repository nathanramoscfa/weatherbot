# src/weatherbot/services/retention.py
"""Database retention planning, batched pruning, online backup rotation, and daily worker.

``RetentionService`` plans and executes history pruning while preserving the invariants the
engine, notification policy, raw-response validator cache, and AI spend ledger rely on:

- The newest snapshot is always kept.
- Each watched location's latest stored assessment is always kept.
- For each watched location, the assessment of its newest non-``held`` ``level`` decision
  and of every decision row after it is kept.
- Every snapshot backing a kept assessment is kept, so no kept assessment (or its
  cascading evidence, changes, notifications, decisions, deliveries, or AI outputs) is ever
  removed.
- The newest ``raw_responses`` row for each ``(source_id, product_key)`` is kept so
  conditional HTTP validators survive.
- The newest ``pause`` or ``resume`` control row in ``ai_calls`` is kept regardless of age,
  and ``ai_calls`` rows from the last 31 days (and today's local day) are never removed.
- ``locations``, ``storms``, ``advisories``, ``settings``, and ``heartbeats`` are never
  deleted from.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from weatherbot.models import AlertLevel
from weatherbot.services.config import (
    RETENTION_MAX_DAYS,
    RETENTION_MIN_DAYS,
    AppPaths,
    Settings,
    ensure_directory,
)
from weatherbot.services.locks import LockBusyError, ProcessLock, held
from weatherbot.services.persistence.database import (
    DatabaseError,
    current_revision,
    writing_session,
)
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    HeartbeatRepository,
    SettingsRepository,
)
from weatherbot.services.persistence.tables import (
    AiCallRow,
    AiOutputRow,
    AlertObservationRow,
    AlertRow,
    AssessmentChangeRow,
    AssessmentEvidenceRow,
    AssessmentRow,
    DriftWarningRow,
    FeedItemObservationRow,
    FeedItemRow,
    GeometryContentRow,
    LocationRow,
    MonitorCycleRow,
    NotificationDecisionRow,
    NotificationDeliveryRow,
    NotificationRow,
    OutcomeResponseRow,
    ProductGeometryRow,
    RawResponseRow,
    ResponseBodyRow,
    SnapshotGeometryRow,
    SnapshotProvenanceRow,
    SnapshotRow,
    SourceOutcomeRow,
    StormObservationRow,
    TextProductObservationRow,
    TextProductRow,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator, Sequence
    from pathlib import Path
    from uuid import UUID

    from sqlalchemy.engine import Engine


@contextlib.contextmanager
def _acquire_lock(path: Path, wait_s: float) -> Generator[None]:
    lock = ProcessLock(path)
    lock.acquire(wait_s)
    try:
        yield
    finally:
        lock.release()


LOGGER: Final = logging.getLogger("weatherbot.services.retention")

SNAPSHOT_BATCH_SIZE: Final = 100
ORPHAN_BATCH_SIZE: Final = 500
BATCH_PAUSE_SECONDS: Final = 1.0
CYCLE_LOCK_WAIT_SECONDS: Final = 5.0
PRUNE_BACKUP_INTERVAL: Final = timedelta(days=7)
MAX_PRUNE_BACKUPS: Final = 2
AI_CALLS_MIN_AGE: Final = timedelta(days=31)
RETENTION_HEARTBEAT_CADENCE_S: Final = 172_800
RETENTION_LAST_RUN_KEY: Final = "retention_last_run"
RETENTION_WAKE_HOUR: Final = 3
RETENTION_WAKE_MINUTE: Final = 30
WORKER_MAX_SLEEP_S: Final = 60.0

_PRUNE_BACKUP_RE: Final = re.compile(r"^weatherbot-(\d{8}T\d{6}Z)-[0-9A-Za-z_]+-prune\.sqlite3$")

DELETABLE_TABLES: Final[tuple[str, ...]] = (
    "snapshots",
    "source_outcomes",
    "outcome_responses",
    "raw_responses",
    "response_bodies",
    "storm_observations",
    "product_geometries",
    "snapshot_provenances",
    "snapshot_geometries",
    "geometry_contents",
    "text_product_observations",
    "text_products",
    "feed_item_observations",
    "feed_items",
    "alert_observations",
    "alerts",
    "drift_warnings",
    "assessments",
    "assessment_evidence",
    "assessment_changes",
    "monitor_cycles",
    "notifications",
    "notification_decisions",
    "notification_deliveries",
    "ai_calls",
    "ai_outputs",
)
"""Every table a retention run can remove rows from, directly or by foreign-key cascade."""

NEVER_DELETED_TABLES: Final[frozenset[str]] = frozenset(
    {
        "locations",
        "storms",
        "advisories",
        "settings",
        "heartbeats",
    }
)
"""Tables a retention run never deletes from."""


class RetentionError(Exception):
    """Base error for retention planning, pruning, and vacuuming."""


class RetentionCutoffError(RetentionError):
    """The requested cutoff or day count is outside ``30..3650`` days."""


class RetentionBusyError(RetentionError):
    """``retention.lock`` is already held by another process."""


class MonitorRunningError(RetentionError):
    """``monitor.lock`` is held, so ``VACUUM`` is refused."""


@dataclass(frozen=True)
class _KeepList:
    """Identifiers protected from deletion at a point in time."""

    newest_snapshot_id: UUID | None
    latest_assessment_ids: frozenset[int]
    decision_assessment_ids: frozenset[int]
    kept_snapshot_ids: frozenset[UUID]
    newest_raw_response_ids: frozenset[int]
    kept_ai_control_id: int | None


@dataclass(frozen=True)
class RetentionPlan:
    """Read-only preview of what a prune at ``cutoff`` will delete and keep."""

    cutoff: datetime
    days: int | None
    counts: dict[str, int]
    total_rows: int
    estimated_bytes: int
    kept: tuple[str, ...]
    kept_snapshots: int
    kept_assessments: int


@dataclass(frozen=True)
class RetentionResult:
    """Outcome of ``RetentionService.run(cutoff)``."""

    cutoff: datetime
    ran_at: datetime
    status: Literal["complete", "partial"]
    batches: int
    counts: dict[str, int]
    total_deleted: int
    backup_path: Path | None


@dataclass(frozen=True)
class RetentionLastRun:
    """Summary of the most recent retention run stored in ``settings``."""

    ran_at: datetime
    cutoff: datetime
    status: Literal["complete", "partial"]
    batches: int
    total_deleted: int
    counts: dict[str, int]
    backup_file: str | None


@dataclass(frozen=True)
class RetentionOverview:
    """Database sizes, snapshot bounds, row counts, and last run for ``GET /api/retention``."""

    database_bytes: int
    wal_bytes: int
    oldest_snapshot_at: datetime | None
    newest_snapshot_at: datetime | None
    row_counts: dict[str, int]
    last_run: RetentionLastRun | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _local_day(now: datetime, local_zone: tzinfo | None = None) -> str:
    zone = local_zone or now.astimezone().tzinfo or UTC
    return now.astimezone(zone).date().isoformat()


def validate_days(days: int) -> int:
    """Validate that ``days`` is an integer in ``30..3650``."""
    if isinstance(days, bool) or not (RETENTION_MIN_DAYS <= days <= RETENTION_MAX_DAYS):
        message = f"retention days must be between {RETENTION_MIN_DAYS} and {RETENTION_MAX_DAYS}"
        raise RetentionCutoffError(message)
    return days


def validate_cutoff(cutoff: datetime, *, now: datetime) -> datetime:
    """Validate that ``cutoff`` is timezone-aware and lies ``30..3650`` days before ``now``."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        message = "cutoff must be a timezone-aware UTC instant"
        raise RetentionCutoffError(message)
    utc_cutoff = cutoff.astimezone(UTC)
    age = now.astimezone(UTC) - utc_cutoff
    min_age = timedelta(days=RETENTION_MIN_DAYS)
    max_age = timedelta(days=RETENTION_MAX_DAYS, hours=1)
    if age < min_age or age > max_age:
        message = f"cutoff must be between {RETENTION_MIN_DAYS} and {RETENTION_MAX_DAYS} days ago"
        raise RetentionCutoffError(message)
    return utc_cutoff


def _compute_keeplist(session: Session) -> _KeepList:
    """Compute the current keep-list inside ``session``."""
    newest_snapshot_id = session.scalar(
        select(SnapshotRow.id)
        .order_by(SnapshotRow.completed_at.desc(), SnapshotRow.id.desc())
        .limit(1)
    )

    location_ids = list(session.scalars(select(LocationRow.id)))
    latest_assessment_ids: set[int] = set()
    decision_assessment_ids: set[int] = set()

    for loc_id in location_ids:
        latest_id = session.scalar(
            select(AssessmentRow.id)
            .where(AssessmentRow.location_id == loc_id)
            .order_by(AssessmentRow.as_of.desc(), AssessmentRow.id.desc())
            .limit(1)
        )
        if latest_id is not None:
            latest_assessment_ids.add(latest_id)

        anchor_decision_id = session.scalar(
            select(func.max(NotificationDecisionRow.id)).where(
                NotificationDecisionRow.location_id == loc_id,
                NotificationDecisionRow.trigger == "level",
                NotificationDecisionRow.decision != "held",
            )
        )
        if anchor_decision_id is not None:
            after_assessment_ids = session.scalars(
                select(NotificationDecisionRow.assessment_id).where(
                    NotificationDecisionRow.location_id == loc_id,
                    NotificationDecisionRow.id >= anchor_decision_id,
                )
            )
            decision_assessment_ids.update(after_assessment_ids)
        else:
            held_assessment_ids = session.scalars(
                select(NotificationDecisionRow.assessment_id).where(
                    NotificationDecisionRow.location_id == loc_id,
                )
            )
            decision_assessment_ids.update(held_assessment_ids)

    all_kept_assessment_ids = latest_assessment_ids | decision_assessment_ids
    kept_snapshot_ids: set[UUID] = set()
    if newest_snapshot_id is not None:
        kept_snapshot_ids.add(newest_snapshot_id)
    if all_kept_assessment_ids:
        snap_ids = session.scalars(
            select(AssessmentRow.snapshot_id).where(AssessmentRow.id.in_(all_kept_assessment_ids))
        )
        kept_snapshot_ids.update(snap_ids)

    # Newest raw_responses row for each (source_id, product_key)
    raw_rows = session.execute(
        select(
            RawResponseRow.id,
            RawResponseRow.source_id,
            RawResponseRow.product_key,
            RawResponseRow.fetched_at,
        ).order_by(
            RawResponseRow.source_id.asc(),
            RawResponseRow.product_key.asc(),
            RawResponseRow.fetched_at.desc(),
            RawResponseRow.id.desc(),
        )
    ).all()
    newest_raw_ids: set[int] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for row_id, source_id, product_key, _fetched_at in raw_rows:
        pair = (source_id, product_key)
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            newest_raw_ids.add(row_id)

    kept_ai_control_id = session.scalar(
        select(AiCallRow.id)
        .where(AiCallRow.kind.in_(("pause", "resume")))
        .order_by(AiCallRow.id.desc())
        .limit(1)
    )

    return _KeepList(
        newest_snapshot_id=newest_snapshot_id,
        latest_assessment_ids=frozenset(latest_assessment_ids),
        decision_assessment_ids=frozenset(decision_assessment_ids),
        kept_snapshot_ids=frozenset(kept_snapshot_ids),
        newest_raw_response_ids=frozenset(newest_raw_ids),
        kept_ai_control_id=kept_ai_control_id,
    )


def _kept_reasons(keep: _KeepList) -> tuple[str, ...]:
    reasons: list[str] = []
    if keep.newest_snapshot_id is not None:
        reasons.append("newest snapshot")
    if keep.latest_assessment_ids:
        reasons.append(f"{len(keep.latest_assessment_ids)} latest location assessment(s)")
    if keep.decision_assessment_ids:
        reasons.append(
            f"{len(keep.decision_assessment_ids)} assessment(s) anchoring notification decisions"
        )
    if keep.kept_snapshot_ids:
        reasons.append(f"{len(keep.kept_snapshot_ids)} snapshot(s) backing kept state")
    if keep.newest_raw_response_ids:
        reasons.append(f"{len(keep.newest_raw_response_ids)} newest raw response validator row(s)")
    if keep.kept_ai_control_id is not None:
        reasons.append("newest AI pause/resume control row")
    return tuple(reasons)


def _count_snapshot_cascades(
    session: Session,
    snap_ids: Sequence[UUID],
    counts: dict[str, int],
) -> None:
    """Add the counts of ``snap_ids`` and every row that cascades from them into ``counts``."""
    if not snap_ids:
        return
    counts["snapshots"] += len(snap_ids)

    outcome_ids = list(
        session.scalars(
            select(SourceOutcomeRow.id).where(SourceOutcomeRow.snapshot_id.in_(snap_ids))
        )
    )
    counts["source_outcomes"] += len(outcome_ids)
    if outcome_ids:
        counts["outcome_responses"] += int(
            session.scalar(
                select(func.count()).where(OutcomeResponseRow.outcome_id.in_(outcome_ids))
            )
            or 0
        )

    counts["storm_observations"] += int(
        session.scalar(select(func.count()).where(StormObservationRow.snapshot_id.in_(snap_ids)))
        or 0
    )
    counts["product_geometries"] += int(
        session.scalar(select(func.count()).where(ProductGeometryRow.snapshot_id.in_(snap_ids)))
        or 0
    )

    prov_ids = list(
        session.scalars(
            select(SnapshotProvenanceRow.id).where(SnapshotProvenanceRow.snapshot_id.in_(snap_ids))
        )
    )
    counts["snapshot_provenances"] += len(prov_ids)
    if prov_ids:
        counts["snapshot_geometries"] += int(
            session.scalar(
                select(func.count()).where(SnapshotGeometryRow.provenance_id.in_(prov_ids))
            )
            or 0
        )

    counts["text_product_observations"] += int(
        session.scalar(
            select(func.count()).where(TextProductObservationRow.snapshot_id.in_(snap_ids))
        )
        or 0
    )
    counts["feed_item_observations"] += int(
        session.scalar(select(func.count()).where(FeedItemObservationRow.snapshot_id.in_(snap_ids)))
        or 0
    )
    counts["alert_observations"] += int(
        session.scalar(select(func.count()).where(AlertObservationRow.snapshot_id.in_(snap_ids)))
        or 0
    )
    counts["drift_warnings"] += int(
        session.scalar(select(func.count()).where(DriftWarningRow.snapshot_id.in_(snap_ids))) or 0
    )

    assessment_ids = list(
        session.scalars(select(AssessmentRow.id).where(AssessmentRow.snapshot_id.in_(snap_ids)))
    )
    counts["assessments"] += len(assessment_ids)
    if assessment_ids:
        counts["assessment_evidence"] += int(
            session.scalar(
                select(func.count()).where(AssessmentEvidenceRow.assessment_id.in_(assessment_ids))
            )
            or 0
        )
        counts["assessment_changes"] += int(
            session.scalar(
                select(func.count()).where(AssessmentChangeRow.assessment_id.in_(assessment_ids))
            )
            or 0
        )
        counts["notification_decisions"] += int(
            session.scalar(
                select(func.count()).where(
                    NotificationDecisionRow.assessment_id.in_(assessment_ids)
                )
            )
            or 0
        )
        notif_ids = list(
            session.scalars(
                select(NotificationRow.id).where(NotificationRow.assessment_id.in_(assessment_ids))
            )
        )
        counts["notifications"] += len(notif_ids)
        if notif_ids:
            counts["notification_deliveries"] += int(
                session.scalar(
                    select(func.count()).where(
                        NotificationDeliveryRow.notification_id.in_(notif_ids)
                    )
                )
                or 0
            )
        counts["ai_outputs"] += int(
            session.scalar(
                select(func.count()).where(AiOutputRow.assessment_id.in_(assessment_ids))
            )
            or 0
        )


def _parse_prune_backup_stamp(path: Path) -> datetime | None:
    match = _PRUNE_BACKUP_RE.match(path.name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _backup_database_for_prune(paths: AppPaths, *, now: datetime, revision: str) -> Path:
    """Create a ``-prune.sqlite3`` online backup and rotate older prune copies."""
    ensure_directory(paths.backup_dir)
    existing: list[tuple[datetime, Path]] = []
    for candidate in paths.backup_dir.iterdir():
        if not candidate.is_file():
            continue
        stamp = _parse_prune_backup_stamp(candidate)
        if stamp is not None:
            existing.append((stamp, candidate))

    existing.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    if existing and (now - existing[0][0]) < PRUNE_BACKUP_INTERVAL:
        return existing[0][1]

    stamp_text = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = paths.backup_dir / f"weatherbot-{stamp_text}-{revision}-prune.sqlite3"
    if destination.exists():
        message = f"prune backup {destination} already exists"
        raise DatabaseError(message)

    try:
        with (
            closing(sqlite3.connect(paths.database_path)) as source,
            closing(sqlite3.connect(destination)) as target,
        ):
            source.backup(target)
    except sqlite3.Error as error:
        destination.unlink(missing_ok=True)
        message = f"failed to copy database before prune ({type(error).__name__})"
        raise DatabaseError(message) from error

    all_prune = [(now, destination), *existing]
    all_prune.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    for _stamp, old_path in all_prune[MAX_PRUNE_BACKUPS:]:
        old_path.unlink(missing_ok=True)

    return destination


class RetentionService:
    """Plan, execute, inspect, and vacuum database retention."""

    def __init__(  # noqa: PLR0913 - service dependencies and injectable seams
        self,
        engine: Engine,
        paths: AppPaths,
        *,
        now: Callable[[], datetime] = _utc_now,
        local_zone: tzinfo | None = None,
        sleep: Callable[[float], None] = time.sleep,
        cycle_lock_wait_s: float = CYCLE_LOCK_WAIT_SECONDS,
        backup_fn: Callable[[AppPaths, datetime, str], Path] | None = None,
        stop_check: Callable[[], bool] | None = None,
    ) -> None:
        """Bind the database engine, paths, clock, and batch pause seam."""
        self._engine = engine
        self._paths = paths
        self._now = now
        self._local_zone = local_zone
        self._sleep = sleep
        self._cycle_lock_wait_s = cycle_lock_wait_s
        self._backup_fn = backup_fn
        self._stop_check = stop_check

    def plan(self, days: int) -> RetentionPlan:
        """Compute the read-only retention plan for ``days`` (``30..3650``)."""
        validated_days = validate_days(days)
        now = self._now().astimezone(UTC)
        cutoff = now - timedelta(days=validated_days)
        return self._plan_for_cutoff(cutoff, now=now, days=validated_days)

    def plan_cutoff(self, cutoff: datetime) -> RetentionPlan:
        """Compute the read-only retention plan for an explicit ``cutoff`` instant."""
        now = self._now().astimezone(UTC)
        validated_cutoff = validate_cutoff(cutoff, now=now)
        return self._plan_for_cutoff(validated_cutoff, now=now, days=None)

    def _plan_for_cutoff(  # noqa: C901, PLR0915 - computes per-table retention counts and keep-list
        self,
        cutoff: datetime,
        *,
        now: datetime,
        days: int | None,
    ) -> RetentionPlan:
        counts: dict[str, int] = dict.fromkeys(DELETABLE_TABLES, 0)
        with Session(self._engine) as session:
            keep = _compute_keeplist(session)
            snap_query = select(SnapshotRow.id).where(SnapshotRow.completed_at < cutoff)
            if keep.kept_snapshot_ids:
                snap_query = snap_query.where(SnapshotRow.id.notin_(keep.kept_snapshot_ids))
            snap_ids = list(
                session.scalars(
                    snap_query.order_by(SnapshotRow.completed_at.asc(), SnapshotRow.id.asc())
                )
            )
            _count_snapshot_cascades(session, snap_ids, counts)

            surviving_outcomes = select(SourceOutcomeRow.id)
            if snap_ids:
                surviving_outcomes = surviving_outcomes.where(
                    SourceOutcomeRow.snapshot_id.notin_(snap_ids)
                )
            linked_raw_ids = select(OutcomeResponseRow.raw_response_id).where(
                OutcomeResponseRow.outcome_id.in_(surviving_outcomes)
            )
            raw_del_query = select(RawResponseRow.id, RawResponseRow.sha256).where(
                RawResponseRow.fetched_at < cutoff,
                RawResponseRow.id.notin_(linked_raw_ids),
            )
            if keep.newest_raw_response_ids:
                raw_del_query = raw_del_query.where(
                    RawResponseRow.id.notin_(keep.newest_raw_response_ids)
                )
            deleted_raw_rows = session.execute(raw_del_query).all()
            deleted_raw_ids = [row[0] for row in deleted_raw_rows]
            counts["raw_responses"] = len(deleted_raw_ids)

            surviving_raw_sha256 = select(RawResponseRow.sha256)
            if deleted_raw_ids:
                surviving_raw_sha256 = surviving_raw_sha256.where(
                    RawResponseRow.id.notin_(deleted_raw_ids)
                )
            body_rows = session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(func.octet_length(ResponseBodyRow.body)), 0),
                ).where(ResponseBodyRow.sha256.notin_(surviving_raw_sha256))
            ).one()
            counts["response_bodies"] = int(body_rows[0] or 0)
            body_bytes = int(body_rows[1] or 0)

            surviving_provs = select(SnapshotProvenanceRow.id)
            if snap_ids:
                surviving_provs = surviving_provs.where(
                    SnapshotProvenanceRow.snapshot_id.notin_(snap_ids)
                )
            surviving_content_ids = select(SnapshotGeometryRow.content_id).where(
                SnapshotGeometryRow.provenance_id.in_(surviving_provs)
            )
            geom_rows = session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(func.octet_length(GeometryContentRow.body)), 0),
                ).where(GeometryContentRow.id.notin_(surviving_content_ids))
            ).one()
            counts["geometry_contents"] = int(geom_rows[0] or 0)
            geom_bytes = int(geom_rows[1] or 0)

            surviving_text_obs = select(TextProductObservationRow.text_product_id)
            if snap_ids:
                surviving_text_obs = surviving_text_obs.where(
                    TextProductObservationRow.snapshot_id.notin_(snap_ids)
                )
            text_rows = session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(func.octet_length(TextProductRow.text)), 0),
                ).where(
                    TextProductRow.issued_at < cutoff,
                    TextProductRow.id.notin_(surviving_text_obs),
                )
            ).one()
            counts["text_products"] = int(text_rows[0] or 0)
            text_bytes = int(text_rows[1] or 0)

            surviving_feed_obs = select(FeedItemObservationRow.feed_item_id)
            if snap_ids:
                surviving_feed_obs = surviving_feed_obs.where(
                    FeedItemObservationRow.snapshot_id.notin_(snap_ids)
                )
            counts["feed_items"] = int(
                session.scalar(
                    select(func.count()).where(
                        FeedItemRow.last_seen < cutoff,
                        FeedItemRow.id.notin_(surviving_feed_obs),
                    )
                )
                or 0
            )

            surviving_alert_obs = select(AlertObservationRow.alert_id).where(
                AlertObservationRow.alert_id.is_not(None)
            )
            if snap_ids:
                surviving_alert_obs = surviving_alert_obs.where(
                    AlertObservationRow.snapshot_id.notin_(snap_ids)
                )
            counts["alerts"] = int(
                session.scalar(
                    select(func.count()).where(
                        AlertRow.last_seen < cutoff,
                        AlertRow.id.notin_(surviving_alert_obs),
                    )
                )
                or 0
            )

            counts["monitor_cycles"] = int(
                session.scalar(select(func.count()).where(MonitorCycleRow.started_at < cutoff)) or 0
            )

            orphan_notif_ids = list(
                session.scalars(
                    select(NotificationRow.id).where(
                        NotificationRow.location_id.is_(None),
                        NotificationRow.assessment_id.is_(None),
                        NotificationRow.created_at < cutoff,
                    )
                )
            )
            counts["notifications"] += len(orphan_notif_ids)
            if orphan_notif_ids:
                counts["notification_deliveries"] += int(
                    session.scalar(
                        select(func.count()).where(
                            NotificationDeliveryRow.notification_id.in_(orphan_notif_ids)
                        )
                    )
                    or 0
                )

            ai_cutoff = min(cutoff, now - AI_CALLS_MIN_AGE)
            local_day = _local_day(now, self._local_zone)
            ai_call_query = select(func.count()).where(
                AiCallRow.started_at < ai_cutoff,
                AiCallRow.day != local_day,
            )
            if keep.kept_ai_control_id is not None:
                ai_call_query = ai_call_query.where(AiCallRow.id != keep.kept_ai_control_id)
            counts["ai_calls"] = int(session.scalar(ai_call_query) or 0)

            counts["ai_outputs"] += int(
                session.scalar(
                    select(func.count()).where(
                        AiOutputRow.assessment_id.is_(None),
                        AiOutputRow.created_at < cutoff,
                    )
                )
                or 0
            )

            total_rows = sum(counts.values())
            estimated_bytes = body_bytes + geom_bytes + text_bytes + (total_rows * 128)
            all_kept_assessments = keep.latest_assessment_ids | keep.decision_assessment_ids
            return RetentionPlan(
                cutoff=cutoff,
                days=days,
                counts=counts,
                total_rows=total_rows,
                estimated_bytes=estimated_bytes if total_rows > 0 else 0,
                kept=_kept_reasons(keep),
                kept_snapshots=len(keep.kept_snapshot_ids),
                kept_assessments=len(all_kept_assessments),
            )

    def run(self, cutoff: datetime) -> RetentionResult:
        """Execute a retention prune for the explicit ``cutoff`` under ``retention.lock``."""
        now = self._now().astimezone(UTC)
        validated_cutoff = validate_cutoff(cutoff, now=now)

        try:
            with _acquire_lock(self._paths.retention_lock_path, 0.0):
                return self._run_locked(validated_cutoff)
        except LockBusyError as error:
            message = "another retention prune is already running"
            raise RetentionBusyError(message) from error

    def _run_locked(  # noqa: C901, PLR0912, PLR0915 - batched snapshot and orphan delete loop
        self, cutoff: datetime
    ) -> RetentionResult:
        counts: dict[str, int] = dict.fromkeys(DELETABLE_TABLES, 0)
        preview = self._plan_for_cutoff(cutoff, now=self._now().astimezone(UTC), days=None)
        if preview.total_rows == 0:
            ran_at = self._now().astimezone(UTC)
            result = RetentionResult(
                cutoff=cutoff,
                ran_at=ran_at,
                status="complete",
                batches=0,
                counts=counts,
                total_deleted=0,
                backup_path=None,
            )
            self._record_last_run(result)
            return result

        revision = current_revision(self._engine) or "head"
        backup_now = self._now().astimezone(UTC)
        if self._backup_fn is not None:
            backup_path = self._backup_fn(self._paths, backup_now, revision)
        else:
            backup_path = _backup_database_for_prune(self._paths, now=backup_now, revision=revision)

        batches = 0
        status: Literal["complete", "partial"] = "complete"

        # 1. Batched snapshot deletes (100 per batch, oldest first)
        while True:
            if batches > 0:
                if self._stop_check is not None and self._stop_check():
                    status = "partial"
                    break
                self._sleep(BATCH_PAUSE_SECONDS)
            try:
                with (
                    _acquire_lock(self._paths.cycle_lock_path, self._cycle_lock_wait_s),
                    writing_session(self._engine) as session,
                ):
                    keep = _compute_keeplist(session)
                    snap_query = select(SnapshotRow.id).where(SnapshotRow.completed_at < cutoff)
                    if keep.kept_snapshot_ids:
                        snap_query = snap_query.where(SnapshotRow.id.notin_(keep.kept_snapshot_ids))
                    batch_ids = list(
                        session.scalars(
                            snap_query.order_by(
                                SnapshotRow.completed_at.asc(), SnapshotRow.id.asc()
                            ).limit(SNAPSHOT_BATCH_SIZE)
                        )
                    )
                    if not batch_ids:
                        break
                    _count_snapshot_cascades(session, batch_ids, counts)
                    session.execute(delete(SnapshotRow).where(SnapshotRow.id.in_(batch_ids)))
                    batches += 1
            except LockBusyError:
                status = "partial"
                break

        # 2. Batched orphan deletes (500 per batch) in dependency order
        if status == "complete":
            for step in (
                self._delete_orphan_raw_responses,
                self._delete_orphan_response_bodies,
                self._delete_orphan_geometry_contents,
                self._delete_orphan_text_products,
                self._delete_orphan_feed_items,
                self._delete_orphan_alerts,
                self._delete_old_monitor_cycles,
                self._delete_old_system_notifications,
                self._delete_old_ai_calls,
                self._delete_old_narration_outputs,
            ):
                while True:
                    if batches > 0:
                        if self._stop_check is not None and self._stop_check():
                            status = "partial"
                            break
                        self._sleep(BATCH_PAUSE_SECONDS)
                    try:
                        with (
                            _acquire_lock(self._paths.cycle_lock_path, self._cycle_lock_wait_s),
                            writing_session(self._engine) as session,
                        ):
                            deleted_in_batch = step(session, cutoff, counts)
                            if deleted_in_batch == 0:
                                break
                            batches += 1
                    except LockBusyError:
                        status = "partial"
                        break
                if status == "partial":
                    break

        ran_at = self._now().astimezone(UTC)
        total_deleted = sum(counts.values())
        result = RetentionResult(
            cutoff=cutoff,
            ran_at=ran_at,
            status=status,
            batches=batches,
            counts=counts,
            total_deleted=total_deleted,
            backup_path=backup_path,
        )
        with contextlib.suppress(LockBusyError, DatabaseError):
            self._record_last_run(result)
        return result

    def _delete_orphan_raw_responses(
        self,
        session: Session,
        cutoff: datetime,
        counts: dict[str, int],
    ) -> int:
        keep = _compute_keeplist(session)
        linked = exists(select(1).where(OutcomeResponseRow.raw_response_id == RawResponseRow.id))
        query = select(RawResponseRow.id).where(
            RawResponseRow.fetched_at < cutoff,
            ~linked,
        )
        if keep.newest_raw_response_ids:
            query = query.where(RawResponseRow.id.notin_(keep.newest_raw_response_ids))
        batch_ids = list(
            session.scalars(query.order_by(RawResponseRow.id.asc()).limit(ORPHAN_BATCH_SIZE))
        )
        if not batch_ids:
            return 0
        session.execute(delete(RawResponseRow).where(RawResponseRow.id.in_(batch_ids)))
        counts["raw_responses"] += len(batch_ids)
        return len(batch_ids)

    def _delete_orphan_response_bodies(
        self,
        session: Session,
        _cutoff: datetime,
        counts: dict[str, int],
    ) -> int:
        referenced = exists(select(1).where(RawResponseRow.sha256 == ResponseBodyRow.sha256))
        batch_hashes = list(
            session.scalars(
                select(ResponseBodyRow.sha256)
                .where(~referenced)
                .order_by(ResponseBodyRow.sha256.asc())
                .limit(ORPHAN_BATCH_SIZE)
            )
        )
        if not batch_hashes:
            return 0
        session.execute(delete(ResponseBodyRow).where(ResponseBodyRow.sha256.in_(batch_hashes)))
        counts["response_bodies"] += len(batch_hashes)
        return len(batch_hashes)

    def _delete_orphan_geometry_contents(
        self,
        session: Session,
        _cutoff: datetime,
        counts: dict[str, int],
    ) -> int:
        referenced = exists(
            select(1).where(SnapshotGeometryRow.content_id == GeometryContentRow.id)
        )
        batch_ids = list(
            session.scalars(
                select(GeometryContentRow.id)
                .where(~referenced)
                .order_by(GeometryContentRow.id.asc())
                .limit(ORPHAN_BATCH_SIZE)
            )
        )
        if not batch_ids:
            return 0
        session.execute(delete(GeometryContentRow).where(GeometryContentRow.id.in_(batch_ids)))
        counts["geometry_contents"] += len(batch_ids)
        return len(batch_ids)

    def _delete_orphan_text_products(
        self,
        session: Session,
        cutoff: datetime,
        counts: dict[str, int],
    ) -> int:
        referenced = exists(
            select(1).where(TextProductObservationRow.text_product_id == TextProductRow.id)
        )
        batch_ids = list(
            session.scalars(
                select(TextProductRow.id)
                .where(TextProductRow.issued_at < cutoff, ~referenced)
                .order_by(TextProductRow.id.asc())
                .limit(ORPHAN_BATCH_SIZE)
            )
        )
        if not batch_ids:
            return 0
        session.execute(delete(TextProductRow).where(TextProductRow.id.in_(batch_ids)))
        counts["text_products"] += len(batch_ids)
        return len(batch_ids)

    def _delete_orphan_feed_items(
        self,
        session: Session,
        cutoff: datetime,
        counts: dict[str, int],
    ) -> int:
        referenced = exists(select(1).where(FeedItemObservationRow.feed_item_id == FeedItemRow.id))
        batch_ids = list(
            session.scalars(
                select(FeedItemRow.id)
                .where(FeedItemRow.last_seen < cutoff, ~referenced)
                .order_by(FeedItemRow.id.asc())
                .limit(ORPHAN_BATCH_SIZE)
            )
        )
        if not batch_ids:
            return 0
        session.execute(delete(FeedItemRow).where(FeedItemRow.id.in_(batch_ids)))
        counts["feed_items"] += len(batch_ids)
        return len(batch_ids)

    def _delete_orphan_alerts(
        self,
        session: Session,
        cutoff: datetime,
        counts: dict[str, int],
    ) -> int:
        referenced = exists(select(1).where(AlertObservationRow.alert_id == AlertRow.id))
        batch_ids = list(
            session.scalars(
                select(AlertRow.id)
                .where(AlertRow.last_seen < cutoff, ~referenced)
                .order_by(AlertRow.id.asc())
                .limit(ORPHAN_BATCH_SIZE)
            )
        )
        if not batch_ids:
            return 0
        session.execute(delete(AlertRow).where(AlertRow.id.in_(batch_ids)))
        counts["alerts"] += len(batch_ids)
        return len(batch_ids)

    def _delete_old_monitor_cycles(
        self,
        session: Session,
        cutoff: datetime,
        counts: dict[str, int],
    ) -> int:
        batch_ids = list(
            session.scalars(
                select(MonitorCycleRow.id)
                .where(MonitorCycleRow.started_at < cutoff)
                .order_by(MonitorCycleRow.id.asc())
                .limit(ORPHAN_BATCH_SIZE)
            )
        )
        if not batch_ids:
            return 0
        session.execute(delete(MonitorCycleRow).where(MonitorCycleRow.id.in_(batch_ids)))
        counts["monitor_cycles"] += len(batch_ids)
        return len(batch_ids)

    def _delete_old_system_notifications(
        self,
        session: Session,
        cutoff: datetime,
        counts: dict[str, int],
    ) -> int:
        batch_ids = list(
            session.scalars(
                select(NotificationRow.id)
                .where(
                    NotificationRow.location_id.is_(None),
                    NotificationRow.assessment_id.is_(None),
                    NotificationRow.created_at < cutoff,
                )
                .order_by(NotificationRow.id.asc())
                .limit(ORPHAN_BATCH_SIZE)
            )
        )
        if not batch_ids:
            return 0
        deliveries = int(
            session.scalar(
                select(func.count()).where(NotificationDeliveryRow.notification_id.in_(batch_ids))
            )
            or 0
        )
        session.execute(delete(NotificationRow).where(NotificationRow.id.in_(batch_ids)))
        counts["notifications"] += len(batch_ids)
        counts["notification_deliveries"] += deliveries
        return len(batch_ids)

    def _delete_old_ai_calls(
        self,
        session: Session,
        cutoff: datetime,
        counts: dict[str, int],
    ) -> int:
        now = self._now().astimezone(UTC)
        ai_cutoff = min(cutoff, now - AI_CALLS_MIN_AGE)
        local_day = _local_day(now, self._local_zone)
        keep = _compute_keeplist(session)
        query = select(AiCallRow.id).where(
            AiCallRow.started_at < ai_cutoff,
            AiCallRow.day != local_day,
        )
        if keep.kept_ai_control_id is not None:
            query = query.where(AiCallRow.id != keep.kept_ai_control_id)
        batch_ids = list(
            session.scalars(query.order_by(AiCallRow.id.asc()).limit(ORPHAN_BATCH_SIZE))
        )
        if not batch_ids:
            return 0
        session.execute(delete(AiCallRow).where(AiCallRow.id.in_(batch_ids)))
        counts["ai_calls"] += len(batch_ids)
        return len(batch_ids)

    def _delete_old_narration_outputs(
        self,
        session: Session,
        cutoff: datetime,
        counts: dict[str, int],
    ) -> int:
        batch_ids = list(
            session.scalars(
                select(AiOutputRow.id)
                .where(
                    AiOutputRow.assessment_id.is_(None),
                    AiOutputRow.created_at < cutoff,
                )
                .order_by(AiOutputRow.id.asc())
                .limit(ORPHAN_BATCH_SIZE)
            )
        )
        if not batch_ids:
            return 0
        session.execute(delete(AiOutputRow).where(AiOutputRow.id.in_(batch_ids)))
        counts["ai_outputs"] += len(batch_ids)
        return len(batch_ids)

    def _record_last_run(self, result: RetentionResult) -> None:
        payload = {
            "ran_at": result.ran_at.astimezone(UTC).isoformat(),
            "cutoff": result.cutoff.astimezone(UTC).isoformat(),
            "status": result.status,
            "batches": result.batches,
            "total_deleted": result.total_deleted,
            "counts": result.counts,
            "backup_file": result.backup_path.name if result.backup_path is not None else None,
        }
        SettingsRepository(self._engine, now=self._now).set(
            RETENTION_LAST_RUN_KEY, json.dumps(payload, sort_keys=True)
        )

    def last_run(self) -> RetentionLastRun | None:
        """Read the last retention run summary from ``settings``, if recorded."""
        raw = SettingsRepository(self._engine, now=self._now).get(RETENTION_LAST_RUN_KEY)
        if not isinstance(raw, str) or not raw:
            return None
        try:
            data = cast("dict[str, Any]", json.loads(raw))
            status_val: Literal["complete", "partial"] = (
                "partial" if data.get("status") == "partial" else "complete"
            )
            counts_raw = cast("dict[str, Any]", data.get("counts", {}))
            counts = {k: int(counts_raw.get(k, 0)) for k in DELETABLE_TABLES}
            backup_file = data.get("backup_file")
            return RetentionLastRun(
                ran_at=datetime.fromisoformat(str(data["ran_at"])).astimezone(UTC),
                cutoff=datetime.fromisoformat(str(data["cutoff"])).astimezone(UTC),
                status=status_val,
                batches=int(data.get("batches", 0)),
                total_deleted=int(data.get("total_deleted", 0)),
                counts=counts,
                backup_file=str(backup_file) if isinstance(backup_file, str) else None,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def overview(self) -> RetentionOverview:
        """Return database and WAL sizes, snapshot range, row counts, and last run."""
        db_path = self._paths.database_path
        wal_path = db_path.with_name(f"{db_path.name}-wal")
        try:
            db_bytes = db_path.stat().st_size
        except OSError:
            db_bytes = 0
        try:
            wal_bytes = wal_path.stat().st_size
        except OSError:
            wal_bytes = 0

        with Session(self._engine) as session:
            oldest = session.scalar(select(func.min(SnapshotRow.completed_at)))
            newest = session.scalar(select(func.max(SnapshotRow.completed_at)))
            row_counts: dict[str, int] = {
                "snapshots": int(
                    session.scalar(select(func.count()).select_from(SnapshotRow)) or 0
                ),
                "assessments": int(
                    session.scalar(select(func.count()).select_from(AssessmentRow)) or 0
                ),
                "notifications": int(
                    session.scalar(select(func.count()).select_from(NotificationRow)) or 0
                ),
                "raw_responses": int(
                    session.scalar(select(func.count()).select_from(RawResponseRow)) or 0
                ),
                "response_bodies": int(
                    session.scalar(select(func.count()).select_from(ResponseBodyRow)) or 0
                ),
                "geometry_contents": int(
                    session.scalar(select(func.count()).select_from(GeometryContentRow)) or 0
                ),
                "monitor_cycles": int(
                    session.scalar(select(func.count()).select_from(MonitorCycleRow)) or 0
                ),
                "ai_calls": int(session.scalar(select(func.count()).select_from(AiCallRow)) or 0),
                "ai_outputs": int(
                    session.scalar(select(func.count()).select_from(AiOutputRow)) or 0
                ),
            }

        return RetentionOverview(
            database_bytes=db_bytes,
            wal_bytes=wal_bytes,
            oldest_snapshot_at=oldest,
            newest_snapshot_at=newest,
            row_counts=row_counts,
            last_run=self.last_run(),
        )

    def check_vacuum_allowed(self, *, lock_held: Callable[[Path], bool] = held) -> None:
        """Raise ``MonitorRunningError`` if ``monitor.lock`` is held."""
        if lock_held(self._paths.monitor_lock_path):
            message = (
                "cannot run VACUUM while weatherbot serve or check is running "
                "(monitor.lock is held)"
            )
            raise MonitorRunningError(message)

    def vacuum(self, *, lock_held: Callable[[Path], bool] = held) -> int:
        """Run ``VACUUM`` on an autocommit connection while holding ``cycle.lock``.

        Returns:
            The database file size in bytes after ``VACUUM``.

        Raises:
            MonitorRunningError: ``monitor.lock`` is held.
            RetentionBusyError: ``cycle.lock`` could not be acquired.
        """
        self.check_vacuum_allowed(lock_held=lock_held)
        try:
            with _acquire_lock(self._paths.cycle_lock_path, self._cycle_lock_wait_s):
                self.check_vacuum_allowed(lock_held=lock_held)
                self._engine.dispose()
                with closing(
                    sqlite3.connect(
                        self._paths.database_path,
                        isolation_level=None,
                        timeout=30.0,
                    )
                ) as conn:
                    conn.execute("VACUUM")
        except LockBusyError as error:
            message = "another cycle is running; try again"
            raise RetentionBusyError(message) from error
        try:
            return self._paths.database_path.stat().st_size
        except OSError:
            return 0


def next_retention_wake(now: datetime, *, local_zone: tzinfo | None = None) -> datetime:
    """Return the next ``03:30`` local wall-clock instant as a UTC ``datetime``."""
    zone = local_zone or now.astimezone().tzinfo or UTC
    local_now = now.astimezone(zone)
    candidate = local_now.replace(
        hour=RETENTION_WAKE_HOUR,
        minute=RETENTION_WAKE_MINUTE,
        second=0,
        microsecond=0,
    )
    if candidate <= local_now:
        next_day = local_now.date() + timedelta(days=1)
        candidate = datetime(
            next_day.year,
            next_day.month,
            next_day.day,
            RETENTION_WAKE_HOUR,
            RETENTION_WAKE_MINUTE,
            0,
            tzinfo=zone,
        )
    return candidate.astimezone(UTC)


class RetentionWorker:
    """Daily ``03:30`` local background worker for ``weatherbot serve``."""

    def __init__(  # noqa: PLR0913 - background worker dependencies and seams
        self,
        engine: Engine,
        paths: AppPaths,
        *,
        settings: Settings | None = None,
        live_settings: Callable[[], Settings] | None = None,
        clock: Callable[[], datetime] = _utc_now,
        local_zone: tzinfo | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        publish: Callable[..., None] | None = None,
        service_factory: Callable[[], RetentionService] | None = None,
    ) -> None:
        """Configure the daily retention worker."""
        self._engine = engine
        self._paths = paths
        self._settings = settings or Settings()
        self._live_settings = live_settings
        self._clock = clock
        self._local_zone = local_zone
        self._sleep = sleep
        self._publish = publish
        self._service_factory = service_factory
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def _current_settings(self) -> Settings:
        if self._live_settings is not None:
            return self._live_settings()
        return self._settings

    def _clear_cadence_if_present(self, now: datetime) -> None:
        heartbeats = HeartbeatRepository(self._engine, now=self._clock)
        row = next(
            (r for r in heartbeats.rows() if r.kind == "watch" and r.name == "retention"),
            None,
        )
        if row is None or row.expected_every_s is None:
            return
        heartbeats.record(
            "watch",
            "retention",
            at=min(row.last_attempt_at, now),
            result="attempt",
            expected_every_s=None,
        )

    def _run_once_sync(self, stop_event: asyncio.Event | None = None) -> RetentionResult | None:
        settings = self._current_settings()
        history_days = settings.retention.history_days
        now = self._clock().astimezone(UTC)
        if history_days <= 0:
            self._clear_cadence_if_present(now)
            return None

        heartbeats = HeartbeatRepository(self._engine, now=self._clock)
        heartbeats.record(
            "watch",
            "retention",
            at=now,
            result="attempt",
            expected_every_s=RETENTION_HEARTBEAT_CADENCE_S,
        )
        levels = AssessmentRepository(self._engine, now=self._clock).latest_levels()
        max_level = max(levels.values(), default=1)
        if max_level >= int(AlertLevel.WATCH_HURRICANE_THREAT):
            heartbeats.record(
                "watch",
                "retention",
                at=now,
                result="success",
                expected_every_s=RETENTION_HEARTBEAT_CADENCE_S,
            )
            return None

        stop_check = stop_event.is_set if stop_event is not None else self._stop.is_set
        try:
            service = (
                self._service_factory()
                if self._service_factory is not None
                else RetentionService(
                    self._engine,
                    self._paths,
                    now=self._clock,
                    local_zone=self._local_zone,
                    stop_check=stop_check,
                )
            )
            plan = service.plan(history_days)
            result = service.run(plan.cutoff)
        except Exception as error:  # noqa: BLE001 - worker isolates any error and records failure heartbeat
            LOGGER.error(  # noqa: TRY400 - log exception class only, never traceback or message
                "retention worker failed (%s)", type(error).__name__
            )
            heartbeats.record(
                "watch",
                "retention",
                at=self._clock().astimezone(UTC),
                result="failure",
                error_kind=type(error).__name__,
                expected_every_s=RETENTION_HEARTBEAT_CADENCE_S,
            )
            return None

        heartbeats.record(
            "watch",
            "retention",
            at=self._clock().astimezone(UTC),
            result="success",
            expected_every_s=RETENTION_HEARTBEAT_CADENCE_S,
        )
        if self._publish is not None:
            self._publish("health", None, ("settings", "health"))
        return result

    async def run_once(
        self,
        *,
        stop_event: asyncio.Event | None = None,
    ) -> RetentionResult | None:
        """Execute one daily check at ``03:30`` local time off the event loop thread."""
        task = asyncio.ensure_future(asyncio.to_thread(self._run_once_sync, stop_event))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await task
            raise

    async def _sleep_until(self, due: datetime, stop_event: asyncio.Event) -> bool:
        while not stop_event.is_set():
            now = self._clock().astimezone(UTC)
            remaining = (due - now).total_seconds()
            if remaining <= 0:
                return True
            step = min(remaining, WORKER_MAX_SLEEP_S)
            if self._sleep is not None:
                await self._sleep(step)
            else:
                wait_task = asyncio.create_task(stop_event.wait())
                try:
                    await asyncio.wait_for(wait_task, timeout=step)
                except TimeoutError:
                    pass
                finally:
                    if not wait_task.done():
                        wait_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await wait_task
        return False

    async def run(self, stop: asyncio.Event | None = None) -> None:
        """Run the daily ``03:30`` local retention loop until ``stop`` is set."""
        stop_event = stop if stop is not None else self._stop
        settings = self._current_settings()
        if settings.retention.history_days <= 0:
            clear_task = asyncio.ensure_future(
                asyncio.to_thread(self._clear_cadence_if_present, self._clock().astimezone(UTC))
            )
            try:
                await asyncio.shield(clear_task)
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    await clear_task
                raise
        while not stop_event.is_set():
            due = next_retention_wake(self._clock().astimezone(UTC), local_zone=self._local_zone)
            if not await self._sleep_until(due, stop_event):
                break
            await self.run_once(stop_event=stop_event)

    def start(self) -> None:
        """Start the daily retention loop on the running event loop."""
        if self._task is None:
            self._task = asyncio.create_task(self.run(self._stop))

    async def stop(self) -> None:
        """Signal the loop to stop and wait for any in-flight check to finish."""
        self._stop.set()
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
