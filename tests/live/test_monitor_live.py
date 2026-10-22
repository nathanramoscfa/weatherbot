# tests/live/test_monitor_live.py
"""``check --once`` against the live services, for both public landmarks.

It stores a complete cycle with a fresh heartbeat for every source and for its runner, in
the test's temporary database. Marked ``live`` and ``enable_socket``: it runs only with
``pytest -m live``. The isolation fixture pins the data directory under the test's
temporary directory; the only coordinates sent are the two landmarks of
``scripts/public_landmarks.toml``, added through ``locations add``.
"""

from datetime import UTC, datetime, timedelta

import pytest
from cli_support import MIAMI, NASSAU, landmark, parse, run

from weatherbot.cli.documents import CheckDocument
from weatherbot.cli.runtime import Runtime
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import CycleRepository, HeartbeatRepository
from weatherbot.services.snapshots import SNAPSHOT_SOURCES

pytestmark = [pytest.mark.live, pytest.mark.enable_socket]

LIVE = Runtime(terminal=False)
"""The real fetcher: the register's pacing, retries, and timeouts."""


def test_check_once_stores_a_complete_cycle_with_fresh_heartbeats() -> None:
    for name, key in ((MIAMI, "miami-dade"), (NASSAU, "nassau")):
        lat, lon = landmark(key)
        added = run(["locations", "add", name, "--lat", lat, "--lon", lon], LIVE)
        assert added.exit_code == 0, added.stderr
    started = datetime.now(UTC)

    ran = run(["check", "--once", "--json"], LIVE)
    document = parse(ran, CheckDocument)

    failed = [o.source_id for o in document.snapshot.source_outcomes if o.status == "failed"]
    assert ran.exit_code == 0, failed
    assert document.data.cycle.status == "complete"
    assert [entry.name for entry in document.data.locations] == [MIAMI, NASSAU]
    with open_database(AppPaths.resolve()) as database:
        cycle = CycleRepository(database.engine).get(document.data.cycle.cycle_id)
        beats = {(row.kind, row.name): row for row in HeartbeatRepository(database.engine).rows()}
    assert cycle is not None
    assert (cycle.status, cycle.snapshot_id) == ("complete", document.snapshot.snapshot_id)
    fresh = started - timedelta(seconds=1)
    assert {name for kind, name in beats if kind == "source"} == set(SNAPSHOT_SOURCES)
    assert all(beats["source", name].last_attempt_at >= fresh for name in SNAPSHOT_SOURCES)
    assert all(beat.consecutive_failures == 0 for beat in beats.values())
    runner = beats["runner", "check-once"]
    assert runner.last_success_at is not None
    assert runner.last_success_at >= fresh
    assert all(beat.expected_every_s is None for beat in beats.values())
