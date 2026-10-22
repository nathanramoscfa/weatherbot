# tests/cli/test_doctor_heartbeat.py
"""``doctor``'s ``heartbeat`` check: skipped until a cadence is promised, then pass or fail.

A fresh database and manual cycles promise no cadence, so both alarm proofs keep exiting 0;
after a scheduled cycle the check passes within twice the cadence and fails past it; when
the database does not open, the check is skipped and the database is the only failure.
"""

import sqlite3
from contextlib import closing
from datetime import timedelta
from typing import Final

from cli_support import MIAMI, add_landmark, parse, recorded_services, run, runtime, scheduled_cycle
from source_support import NOW

from weatherbot.cli.documents import DoctorDocument
from weatherbot.services.config import AppPaths

FAILED: Final = 1


def _doctor(hours: int = 0) -> tuple[int, DoctorDocument, dict[str, str]]:
    ran = run(["doctor", "--offline", "--json"], runtime(now=NOW + timedelta(hours=hours)))
    document = parse(ran, DoctorDocument)
    return ran.exit_code, document, {check.name: check.status for check in document.data.checks}


def test_a_fresh_database_skips_the_heartbeat_check_and_exits_0() -> None:
    code, document, checks = _doctor()

    assert code == 0
    assert checks["heartbeat"] == "skip"
    assert document.data.heartbeats == ()


def test_manual_cycles_alone_keep_the_check_skipped() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        assert run(["status"]).exit_code == 0

    code, document, checks = _doctor(hours=48)

    assert code == 0
    assert checks["heartbeat"] == "skip"
    assert document.data.heartbeats
    assert not any(beat.stale for beat in document.data.heartbeats)


def test_after_a_scheduled_cycle_the_check_passes_then_fails_past_twice_its_cadence() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        assert scheduled_cycle().status == "complete"

    fresh_code, _, fresh = _doctor(hours=1)
    stale_code, document, stale = _doctor(hours=7)
    printed = run(["doctor", "--offline"], runtime(now=NOW + timedelta(hours=7)))

    assert (fresh_code, fresh["heartbeat"]) == (0, "pass")
    assert (stale_code, stale["heartbeat"]) == (FAILED, "fail")
    detail = next(c.detail for c in document.data.checks if c.name == "heartbeat")
    assert "nhc-current-storms" in detail
    assert document.data.failed
    assert "Heartbeats" in printed.stdout
    assert "nhc-current-storms" in printed.stdout


def test_a_database_that_does_not_open_skips_the_heartbeat_check() -> None:
    code, _, _ = _doctor()
    assert code == 0
    with closing(sqlite3.connect(AppPaths.resolve().database_path)) as connection:
        connection.execute("UPDATE alembic_version SET version_num = 'unknown-revision'")
        connection.commit()

    code, document, checks = _doctor()

    assert code == FAILED
    assert checks["heartbeat"] == "skip"
    assert [name for name, status in checks.items() if status == "fail"] == ["database"]
    assert document.data.heartbeats == ()
