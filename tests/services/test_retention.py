# tests/services/test_retention.py
"""Tests for ``RetentionService``: plans, row-for-row deletes, validators, PNGs, AI, and backups."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from cli_support import (
    MIAMI,
    add_landmark,
    quiet_fetcher,
    recorded_services,
)
from source_support import NOW
from sqlalchemy import text
from sqlalchemy.orm import Session

from weatherbot.services import retention as retention_mod
from weatherbot.services.ai.ledger import Ledger
from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.locks import ProcessLock
from weatherbot.services.monitor import MonitorService
from weatherbot.services.network import Network
from weatherbot.services.notifications import NotificationService
from weatherbot.services.persistence.database import (
    DatabaseError,
    open_database,
    writing_session,
)
from weatherbot.services.persistence.raw_cache import RawResponseCache, stored_png
from weatherbot.services.persistence.repositories import (
    HeartbeatRepository,
    SnapshotRepository,
)
from weatherbot.services.persistence.tables import AiCallRow, AiOutputRow
from weatherbot.services.retention import (
    DELETABLE_TABLES,
    NEVER_DELETED_TABLES,
    MonitorRunningError,
    RetentionBusyError,
    RetentionCutoffError,
    RetentionService,
)

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Engine


def _table_counts(engine: Engine, tables: tuple[str, ...] | frozenset[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    with Session(engine) as session:
        for table in tables:
            count = session.scalar(text(f"SELECT COUNT(*) FROM {table}"))  # noqa: S608
            result[table] = int(count or 0)
    return result


def _run_cycle(paths: AppPaths, engine: Engine, instant: datetime) -> None:
    settings = Settings()
    monitor = MonitorService(
        engine,
        paths=paths,
        settings=settings,
        runner="check-once",
        network=Network(
            make_fetcher=lambda client, store: quiet_fetcher(client, store, now=instant)
        ),
        now=lambda: instant,
    )
    asyncio.run(monitor.run_cycle("manual"))


def test_plan_matches_run_row_for_row_and_preserves_validators_pngs_ai_and_protected_tables() -> (  # noqa: PLR0915
    None
):
    paths = AppPaths.resolve()
    base = NOW

    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0

        with open_database(paths) as db:
            # Cycle 1 at Day 0 (base, kept as anchor), Cycles 2 & 3 at Day 0 + 30m/60m (prunable),
            # Cycle 4 at Day 90 (current_now, kept as newest).
            _run_cycle(paths, db.engine, base)
            _run_cycle(paths, db.engine, base + timedelta(minutes=30))
            _run_cycle(paths, db.engine, base + timedelta(minutes=60))

            # Add an old system notification (Day 5) and an old narration AI output (Day 5)
            notif = NotificationService(db.engine, now=lambda: base + timedelta(days=5))
            asyncio.run(
                notif.send(
                    "test",
                    title="Old test notification",
                    body=("Old test body",),
                )
            )

            # Add a pause control row 400 days before current_now, an old settled AI call
            # 60 days before current_now, and a today AI call at Day 90.
            current_now = base + timedelta(days=90)
            old_pause_time = current_now - timedelta(days=400)
            old_call_time = current_now - timedelta(days=60)

            with writing_session(db.engine) as session:
                old_call = AiCallRow(
                    kind="summary",
                    model="claude-sonnet-5-5",
                    location_name=MIAMI,
                    status="ok",
                    day=old_call_time.date().isoformat(),
                    started_at=old_call_time,
                    finished_at=old_call_time + timedelta(seconds=2),
                    ceiling_micro_usd=5000,
                    cost_micro_usd=1200,
                    allowance_micro_usd=0,
                    input_tokens=100,
                    cache_write_5m_tokens=0,
                    cache_write_1h_tokens=0,
                    cache_read_tokens=0,
                    output_tokens=50,
                    prices_as_of="2026-10-01",
                )
                session.add(old_call)
                session.flush()
                session.add(
                    AiOutputRow(
                        call_id=old_call.id,
                        kind="narration",
                        location_name=None,
                        snapshot_id=None,
                        assessment_id=None,
                        graphic_sha256="a" * 64,
                        model="claude-sonnet-5-5",
                        prompt_version="v1",
                        status="ok",
                        withheld_reason=None,
                        content={"summary": "Old narration"},
                        created_at=old_call_time,
                    )
                )
                # Pause row set over a year ago (newest control row)
                session.add(
                    AiCallRow(
                        kind="pause",
                        model=None,
                        location_name=None,
                        status="control",
                        day=old_pause_time.date().isoformat(),
                        started_at=old_pause_time,
                        finished_at=old_pause_time,
                        ceiling_micro_usd=0,
                        cost_micro_usd=0,
                        allowance_micro_usd=0,
                        input_tokens=0,
                        cache_write_5m_tokens=0,
                        cache_write_1h_tokens=0,
                        cache_read_tokens=0,
                        output_tokens=0,
                        prices_as_of="2026-10-01",
                    )
                )
                # Today's settled AI call
                session.add(
                    AiCallRow(
                        kind="briefing",
                        model="claude-sonnet-5-5",
                        location_name=MIAMI,
                        status="ok",
                        day=current_now.astimezone().date().isoformat(),
                        started_at=current_now - timedelta(minutes=10),
                        finished_at=current_now - timedelta(minutes=9),
                        ceiling_micro_usd=10000,
                        cost_micro_usd=4500,
                        allowance_micro_usd=0,
                        input_tokens=500,
                        cache_write_5m_tokens=0,
                        cache_write_1h_tokens=0,
                        cache_read_tokens=0,
                        output_tokens=150,
                        prices_as_of="2026-10-01",
                    )
                )

            # Cycle 3 at Day 90 (current_now) so the newest snapshot is at Day 90.
            _run_cycle(paths, db.engine, current_now)
            HeartbeatRepository(db.engine, now=lambda: current_now).record(
                "runner",
                "serve",
                at=current_now,
                result="success",
                expected_every_s=300,
            )

            ledger = Ledger(
                db.engine,
                cap_micro_usd=1_000_000,
                now=lambda: current_now,
            )
            today_before = ledger.today()
            assert today_before.paused is True
            assert today_before.spent_micro_usd == 4500  # noqa: PLR2004

            before_deletable = _table_counts(db.engine, DELETABLE_TABLES)
            before_protected = _table_counts(db.engine, NEVER_DELETED_TABLES)

            retention = RetentionService(
                db.engine,
                paths,
                now=lambda: current_now,
                sleep=lambda _: None,
            )
            plan = retention.plan(30)
            assert plan.total_rows > 0
            assert plan.estimated_bytes > 0
            assert plan.counts["snapshots"] == 2  # noqa: PLR2004
            assert plan.counts["ai_calls"] == 1
            assert plan.counts["ai_outputs"] == 1

            result = retention.run(plan.cutoff)
            assert result.status == "complete"
            assert result.counts == plan.counts
            assert result.total_deleted == plan.total_rows
            assert result.backup_path is not None
            assert result.backup_path.exists()

            after_deletable = _table_counts(db.engine, DELETABLE_TABLES)
            after_protected = _table_counts(db.engine, NEVER_DELETED_TABLES)

            # Every table in DELETABLE_TABLES decreased by exactly plan.counts[table]!
            for table in DELETABLE_TABLES:
                assert before_deletable[table] - after_deletable[table] == plan.counts[table], (
                    f"table {table}: before={before_deletable[table]} "
                    f"after={after_deletable[table]} planned={plan.counts[table]}"
                )

            # Protected tables never shrink (`settings` gains `retention_last_run` key).
            for table in NEVER_DELETED_TABLES - {"settings"}:
                assert after_protected[table] == before_protected[table]
            assert after_protected["settings"] >= before_protected["settings"]

            # Today's AI ledger and the 400-day-old pause control row survive!
            today_after = ledger.today()
            assert today_after == today_before
            assert today_after.paused is True

            # Conditional HTTP validators of the newest raw_responses survive!
            cache = RawResponseCache(db.engine)
            roster_cached = cache.load("https://www.nhc.noaa.gov/CurrentStorms.json")
            assert roster_cached is not None
            assert roster_cached.etag is not None or roster_cached.last_modified is not None

            # /api/outlook's PNGs from the newest snapshot survive!
            latest_snap = SnapshotRepository(db.engine).latest()
            assert latest_snap is not None
            assert len(latest_snap.outlook_graphics) > 0
            for graphic in latest_snap.outlook_graphics:
                png = stored_png(db.engine, graphic.provenance.sha256)
                assert png is not None
                assert png.startswith(b"\x89PNG\r\n\x1a\n")

            # A second run at the same cutoff deletes 0 rows and creates no second backup.
            second = retention.run(plan.cutoff)
            assert second.status == "complete"
            assert second.total_deleted == 0
            assert second.batches == 0
            assert second.backup_path is None

            # A newer cycle at Day 90 + 1h followed by a run at the earlier cutoff removes nothing.
            later = current_now + timedelta(hours=1)
            _run_cycle(paths, db.engine, later)
            third = RetentionService(
                db.engine,
                paths,
                now=lambda: later,
                sleep=lambda _: None,
            ).run(plan.cutoff)
            assert third.total_deleted == 0


def test_cycle_lock_yields_partial_run_and_retention_lock_refuses_overlap() -> None:
    paths = AppPaths.resolve()
    base = NOW
    current_now = base + timedelta(days=90)

    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0
        with open_database(paths) as db:
            _run_cycle(paths, db.engine, base)
            _run_cycle(paths, db.engine, base + timedelta(minutes=30))
            _run_cycle(paths, db.engine, current_now)

            plan = RetentionService(db.engine, paths, now=lambda: current_now).plan(30)
            assert plan.total_rows > 0

            # 1. Overlapping retention.lock is refused with RetentionBusyError.
            ret_lock = ProcessLock(paths.retention_lock_path)
            assert ret_lock.try_acquire()
            try:
                with pytest.raises(RetentionBusyError, match="already running"):
                    RetentionService(db.engine, paths, now=lambda: current_now).run(plan.cutoff)
            finally:
                ret_lock.release()

            # 2. If a monitor cycle acquires cycle.lock between batch 1 and batch 2,
            #    run() stops cleanly with status == "partial".
            held_lock: ProcessLock | None = None

            def lock_cycle_after_first_batch(_seconds: float) -> None:
                nonlocal held_lock
                if held_lock is None:
                    held_lock = ProcessLock(paths.cycle_lock_path)
                    assert held_lock.try_acquire()

            try:
                partial = RetentionService(
                    db.engine,
                    paths,
                    now=lambda: current_now,
                    sleep=lock_cycle_after_first_batch,
                    cycle_lock_wait_s=0.0,
                ).run(plan.cutoff)
            finally:
                if held_lock is not None:
                    held_lock.release()

            assert partial.status == "partial"
            assert partial.batches == 1
            assert partial.counts["snapshots"] == 1
            last = RetentionService(db.engine, paths, now=lambda: current_now).last_run()
            assert last is not None
            assert last.status == "partial"


def test_failed_backup_deletes_nothing_and_prune_backups_throttle_7d_and_keep_2_newest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = AppPaths.resolve()
    base = NOW
    current_now = base + timedelta(days=90)

    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0
        with open_database(paths) as db:
            _run_cycle(paths, db.engine, base)
            _run_cycle(paths, db.engine, base + timedelta(days=10))
            _run_cycle(paths, db.engine, base + timedelta(days=20))
            _run_cycle(paths, db.engine, current_now)

            before = _table_counts(db.engine, DELETABLE_TABLES)
            cutoff = current_now - timedelta(days=30)

            # 1. Failed backup raises DatabaseError and deletes nothing.
            def fail_backup(_paths: AppPaths, _now: datetime, _rev: str) -> Path:
                msg = "simulated disk full during backup"
                raise DatabaseError(msg)

            with pytest.raises(DatabaseError, match="simulated disk full"):
                RetentionService(
                    db.engine,
                    paths,
                    now=lambda: current_now,
                    backup_fn=fail_backup,
                ).run(cutoff)

            assert _table_counts(db.engine, DELETABLE_TABLES) == before

            # 2. Seed a migration backup (must never be touched by prune backup rotation).
            paths.backup_dir.mkdir(parents=True, exist_ok=True)
            migration_backup = paths.backup_dir / "weatherbot-20261001T000000Z-0009.sqlite3"
            migration_backup.write_bytes(b"migration-backup")

            # Direct test of _backup_database_for_prune rotation and 7-day throttle:
            t1 = current_now
            b1 = retention_mod._backup_database_for_prune(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                paths, now=t1, revision="0010"
            )
            assert b1.exists()
            assert b1.name.endswith("-0010-prune.sqlite3")

            # Within 7 days (e.g. +3 days), returns b1 without creating a new copy.
            b1_repeat = retention_mod._backup_database_for_prune(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                paths, now=t1 + timedelta(days=3), revision="0010"
            )
            assert b1_repeat == b1

            # At +8 days, creates b2; both b1 and b2 exist.
            t2 = t1 + timedelta(days=8)
            b2 = retention_mod._backup_database_for_prune(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                paths, now=t2, revision="0010"
            )
            assert b2 != b1
            assert b1.exists()
            assert b2.exists()

            # At +16 days, creates b3 and rotates out b1, keeping the 2 newest (b2, b3)
            # AND leaving migration_backup untouched!
            t3 = t2 + timedelta(days=8)
            b3 = retention_mod._backup_database_for_prune(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                paths, now=t3, revision="0010"
            )
            assert b3.exists()
            assert b2.exists()
            assert not b1.exists()
            assert migration_backup.exists()

            # Also verify sqlite3.Error during backup cleans up destination and raises DatabaseError
            def broken_connect(*_args: object, **_kwargs: object) -> sqlite3.Connection:
                msg = "cannot open"
                raise sqlite3.OperationalError(msg)

            monkeypatch.setattr("weatherbot.services.retention.sqlite3.connect", broken_connect)
            with pytest.raises(DatabaseError, match="failed to copy database"):
                retention_mod._backup_database_for_prune(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                    paths, now=t3 + timedelta(days=8), revision="0010"
                )


def test_cutoff_validation_and_vacuum_refusal_when_monitor_running() -> None:
    paths = AppPaths.resolve()
    now = NOW
    with open_database(paths) as db:
        service = RetentionService(db.engine, paths, now=lambda: now)
        with pytest.raises(RetentionCutoffError):
            service.plan(29)
        with pytest.raises(RetentionCutoffError):
            service.plan(3651)
        with pytest.raises(RetentionCutoffError):
            service.plan_cutoff(now - timedelta(days=10))
        with pytest.raises(RetentionCutoffError):
            service.plan_cutoff(datetime(2026, 1, 1))  # noqa: DTZ001

        mon_lock = ProcessLock(paths.monitor_lock_path)
        assert mon_lock.try_acquire()
        try:
            with pytest.raises(MonitorRunningError, match=r"monitor\.lock is held"):
                service.vacuum()
        finally:
            mon_lock.release()
        size = service.vacuum()
        assert size > 0
