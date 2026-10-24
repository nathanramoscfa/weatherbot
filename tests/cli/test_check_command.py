# tests/cli/test_check_command.py
"""``weatherbot check --once`` runs one cycle and exits 0, 1, or 2 as its cycle ended.

Offline, against the recorded answers, for both public landmarks; each ``--json`` document
is validated against its committed schema before it is read.
"""

from typing import Final

import httpx
import pytest
from cli_support import (
    MIAMI,
    NASSAU,
    SUMMARY_CATALOG,
    add_landmark,
    parse,
    recorded_services,
    run,
)
from source_support import NOW

from weatherbot.cli.documents import CheckDocument
from weatherbot.services.config import AppPaths
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.locks import ProcessLock
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import CycleRepository, HeartbeatRepository

UNAVAILABLE: Final = 503
FAILED: Final = 1
USAGE: Final = 2


def test_check_once_runs_a_complete_cycle_and_prints_each_level() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        add_landmark(NASSAU, "nassau")
        result = run(["check", "--once"])

    assert result.exit_code == 0, result.stderr
    assert ": complete." in result.stdout
    assert f"\n{MIAMI}: level 1, All Clear\n" in result.stdout
    assert f"\n{NASSAU}: level 1, All Clear\n" in result.stdout
    assert "The first assessment is at level 1 (All Clear), by the rule all_clear." in (
        result.stdout
    )
    assert "Cycle 1 (check-once, manual): complete." in result.stdout
    assert result.stdout.rstrip().endswith(NOTICE)


def test_check_once_json_holds_the_cycle_and_validates_against_its_schema() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        document = parse(run(["check", "--once", "--json"]), CheckDocument)

    cycle = document.data.cycle
    assert (cycle.runner, cycle.trigger, cycle.status) == ("check-once", "manual", "complete")
    assert (cycle.started_at, cycle.completed_at) == (NOW, NOW)
    (miami,) = document.data.locations
    assert (miami.name, miami.level, miami.rule, miami.complete) == (MIAMI, 1, "all_clear", True)
    assert [change.kind for change in miami.changes] == [
        "level_changed",
        "advisory_issued",
        "official_added",
    ]
    assert not miami.stored_before
    assert document.snapshot.status == "complete"
    with open_database(AppPaths.resolve()) as database:
        stored = CycleRepository(database.engine).get(cycle.cycle_id)
        runners = {row.name for row in HeartbeatRepository(database.engine).rows()}
    assert stored is not None
    assert stored.snapshot_id == document.snapshot.snapshot_id
    assert "check-once" in runners


def test_a_partial_cycle_exits_1() -> None:
    failed = httpx.Response(UNAVAILABLE, headers={"content-type": "text/plain"})
    with recorded_services(overrides={SUMMARY_CATALOG: failed}):
        add_landmark(MIAMI, "miami-dade")
        result = run(["check", "--once"])

    assert result.exit_code == FAILED
    assert f"{MIAMI}: at least level 1, All Clear" in result.stdout
    assert "Cycle 1 (check-once, manual): partial." in result.stdout


def test_a_skipped_cycle_says_another_is_running_and_exits_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEATHERBOT_MONITOR_CYCLE_LOCK_WAIT_SECONDS", "1")
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        holder = ProcessLock(AppPaths.resolve().cycle_lock_path)
        assert holder.try_acquire()
        try:
            result = run(["check", "--once", "--json"])
        finally:
            holder.release()

    assert result.exit_code == FAILED
    assert result.stdout == ""
    assert "another cycle is running; try again" in result.stderr
    with open_database(AppPaths.resolve()) as database:
        (cycle,) = CycleRepository(database.engine).recent(5)
    assert cycle.status == "skipped"


def test_check_json_without_once_is_a_usage_error() -> None:
    result = run(["check", "--json"])

    assert result.exit_code == USAGE
    assert "--json requires --once" in result.stderr


def test_check_once_with_no_location_still_runs_the_cycle() -> None:
    with recorded_services():
        result = run(["check", "--once"])

    assert result.exit_code == 0, result.stderr
    assert "No location is stored, so none was assessed" in result.stdout
    assert "Cycle 1 (check-once, manual): complete." in result.stdout
