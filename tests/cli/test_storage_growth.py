# tests/cli/test_storage_growth.py
"""A second cycle over unchanged answers stores links, never the products again.

Two ``weatherbot status`` runs over the recorded answers, for both public landmarks, the
runtime clock and the fetches 15 minutes apart, in the test's temporary data directory.
Before revision 0004 every such cycle grew the database by 2.0 MiB (measured on
2026-10-21), because every product of every snapshot was stored again. The sizes are read
after a WAL checkpoint, so the file holds every committed page; the test reports sizes
and row counts only.
"""

import sqlite3
from contextlib import closing
from datetime import timedelta
from functools import partial
from pathlib import Path

from cli_support import MIAMI, NASSAU, add_landmark, quiet_fetcher, recorded_services, run
from source_support import NOW

from weatherbot.cli.runtime import Runtime
from weatherbot.services.config import AppPaths

BUDGET = 128 * 1024
"""What a second, unchanged cycle may add to the file, in bytes."""
LATER = NOW + timedelta(minutes=15)
COUNTED = ("snapshots", "geometry_contents", "snapshot_provenances", "snapshot_geometries")


def _measured(path: Path) -> tuple[int, dict[str, int]]:
    """The file's size after a WAL checkpoint, and the counted tables' rows."""
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        counts = {
            table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608 - a constant table name
            for table in COUNTED
        }
    return path.stat().st_size, counts


def test_a_second_unchanged_cycle_adds_no_content_and_stays_under_budget() -> None:
    database = AppPaths.resolve().database_path
    # Every answer of the second cycle is fetched later, so its provenances differ.
    later = Runtime(
        make_fetcher=partial(quiet_fetcher, now=LATER), now=lambda: LATER, terminal=False
    )
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        add_landmark(NASSAU, "nassau")
        first = run(["status"])
        size_first, counts_first = _measured(database)
        second = run(["status"], later)
        size_second, counts_second = _measured(database)

    assert first.exit_code == second.exit_code == 0, second.stderr
    assert counts_second["snapshots"] == counts_first["snapshots"] + 1
    assert counts_second["geometry_contents"] == counts_first["geometry_contents"]
    assert counts_second["snapshot_geometries"] == 2 * counts_first["snapshot_geometries"]
    assert counts_second["snapshot_provenances"] == 2 * counts_first["snapshot_provenances"]
    growth = size_second - size_first
    assert growth < BUDGET, f"the second cycle grew the database by {growth} bytes"
