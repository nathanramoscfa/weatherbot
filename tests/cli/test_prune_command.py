# tests/cli/test_prune_command.py
"""Tests for ``weatherbot prune``: idle, ``--dry-run``, ``--days``, ``--cutoff``, ``--vacuum``."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from cli_support import (
    MIAMI,
    add_landmark,
    parse,
    quiet_fetcher,
    recorded_services,
    run,
)
from source_support import NOW

from weatherbot.cli.documents import PruneDocument
from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.locks import ProcessLock
from weatherbot.services.monitor import MonitorService
from weatherbot.services.network import Network
from weatherbot.services.persistence.database import open_database

if TYPE_CHECKING:
    import pytest


def _seed_two_cycles(paths: AppPaths) -> None:
    base = NOW - timedelta(days=90)
    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0
        with open_database(paths) as db:
            for instant in (base, base + timedelta(minutes=30), NOW):
                monitor = MonitorService(
                    db.engine,
                    paths=paths,
                    settings=Settings(),
                    runner="check-once",
                    network=Network(
                        make_fetcher=lambda client, store, t=instant: quiet_fetcher(
                            client, store, now=t
                        )
                    ),
                    now=lambda t=instant: t,
                )
                asyncio.run(monitor.run_cycle("manual"))


def test_prune_when_disabled_dry_run_days_cutoff_vacuum_and_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WEATHERBOT_RETENTION_HISTORY_DAYS", raising=False)
    paths = AppPaths.resolve()
    _seed_two_cycles(paths)

    # 1. With history_days = 0 (default) and no flags, exits 0 and prints idle message.
    idle_res = run(["prune"])
    assert idle_res.exit_code == 0
    assert "Retention is off" in idle_res.stdout

    idle_json = run(["prune", "--json"])
    assert idle_json.exit_code == 0
    idle_doc = parse(idle_json, PruneDocument)
    assert idle_doc.data.mode == "disabled"

    # 2. --dry-run --days 30 previews the plan without deleting anything.
    dry_res = run(["prune", "--dry-run", "--days", "30", "--json"])
    assert dry_res.exit_code == 0
    dry_doc = parse(dry_res, PruneDocument)
    assert dry_doc.data.mode == "dry_run"
    assert dry_doc.data.history_days == 30  # noqa: PLR2004
    assert dry_doc.data.total_rows > 0
    assert dry_doc.data.cutoff is not None
    cutoff_iso = dry_doc.data.cutoff.isoformat()

    # Human --dry-run output
    dry_text = run(["prune", "--dry-run", "--days", "30"])
    assert dry_text.exit_code == 0
    assert "Dry-run retention plan" in dry_text.stdout

    # 3. --cutoff <cutoff> executes the exact dry-run plan!
    exec_res = run(["prune", "--cutoff", cutoff_iso, "--json"])
    assert exec_res.exit_code == 0
    exec_doc = parse(exec_res, PruneDocument)
    assert exec_doc.data.mode == "pruned"
    assert exec_doc.data.status == "complete"
    assert exec_doc.data.total_rows == dry_doc.data.total_rows

    # 4. --vacuum while monitor.lock is held exits 2!
    mon_lock = ProcessLock(paths.monitor_lock_path)
    assert mon_lock.try_acquire()
    try:
        busy_vac = run(["prune", "--vacuum"])
        assert busy_vac.exit_code == 2  # noqa: PLR2004
        assert "monitor.lock is held" in busy_vac.stderr

        busy_vac_json = run(["prune", "--vacuum", "--json"])
        assert busy_vac_json.exit_code == 2  # noqa: PLR2004
        assert "monitor.lock is held" in busy_vac_json.stderr
    finally:
        mon_lock.release()

    # 5. --vacuum when monitor is stopped runs VACUUM and validates against schema!
    vac_res = run(["prune", "--days", "30", "--vacuum", "--json"])
    assert vac_res.exit_code == 0
    vac_doc = parse(vac_res, PruneDocument)
    assert vac_doc.data.vacuumed is True
    assert (vac_doc.data.database_bytes_after_vacuum or 0) > 0

    # 6. Out-of-range --days exits 2
    bad_days = run(["prune", "--days", "10"])
    assert bad_days.exit_code == 2  # noqa: PLR2004
