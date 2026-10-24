# tests/services/test_doctor_machine.py
"""Unit tests for ``doctor``'s ``tasks`` and ``path`` machine checks and ``heartbeat`` task rule."""

import asyncio
from datetime import timedelta
from pathlib import Path

from cli_support import parse, quiet_fetcher, run, runtime
from source_support import NOW

from weatherbot.cli.documents import DoctorDocument
from weatherbot.services.config import AppPaths
from weatherbot.services.doctor import (
    diagnose,
    heartbeat_check,
    path_check,
    tasks_check,
)
from weatherbot.services.health import staleness
from weatherbot.services.network import Network
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import Heartbeat
from weatherbot.services.tasks import (
    CHECK_ARGUMENTS,
    SERVE_ARGUMENTS,
    TASK_NOT_RUN_RESULT,
    TASK_RUNNING_RESULT,
    ScheduledTask,
)


def _task(  # noqa: PLR0913 - task fields for test cases
    name: str,
    *,
    state: str = "Ready",
    enabled: bool = True,
    command: str = r"C:\tools\weatherbot\Scripts\pythonw.exe",
    arguments: str = SERVE_ARGUMENTS,
    logon_type: str = "InteractiveToken",
    run_level: str = "LeastPrivilege",
    last_task_result: int | None = 0,
) -> ScheduledTask:
    return ScheduledTask(
        name=name,
        state=state,
        enabled=enabled,
        command=command,
        arguments=arguments,
        working_directory=r"C:\data\weatherbot",
        logon_type=logon_type,
        run_level=run_level,
        last_run_time=NOW - timedelta(minutes=10),
        next_run_time=NOW + timedelta(minutes=50) if name == "check" else None,
        last_task_result=last_task_result,
    )


def test_tasks_check_skips_under_override_off_windows_and_when_no_task_installed() -> None:
    both = (_task("serve"), _task("check", arguments=CHECK_ARGUMENTS))

    overridden = tasks_check(both, data_dir_overridden=True, interpreter_exists=lambda _p: True)
    assert overridden.status == "skip"
    assert "WEATHERBOT_DATA_DIR" in overridden.detail

    non_windows = tasks_check(
        both, windows=False, data_dir_overridden=False, interpreter_exists=lambda _p: True
    )
    assert non_windows.status == "skip"

    none_installed = tasks_check(
        (), windows=True, data_dir_overridden=False, interpreter_exists=lambda _p: True
    )
    assert none_installed.status == "skip"


def test_tasks_check_passes_for_healthy_tasks_and_fails_with_reasons() -> None:
    healthy = (
        _task("serve", state="Running", last_task_result=TASK_RUNNING_RESULT),
        _task(
            "check", state="Ready", arguments=CHECK_ARGUMENTS, last_task_result=TASK_NOT_RUN_RESULT
        ),
    )
    passed = tasks_check(healthy, interpreter_exists=lambda _p: True)
    assert passed.status == "pass"
    assert len(passed.name) <= 10  # noqa: PLR2004 - column width cap

    running_after_ignore_new = (
        _task("serve", state="Running", last_task_result=0x800710E0),
        _task("check", state="Ready", arguments=CHECK_ARGUMENTS, last_task_result=0),
    )
    assert (
        tasks_check(running_after_ignore_new, interpreter_exists=lambda _p: True).status == "pass"
    )

    broken = (
        _task(
            "serve",
            state="Disabled",
            enabled=False,
            logon_type="Password",
            run_level="HighestAvailable",
            last_task_result=1,
        ),
    )
    failed = tasks_check(broken, interpreter_exists=lambda _p: False)
    assert failed.status == "fail"
    assert "serve: disabled" in failed.detail
    assert "InteractiveToken" in failed.detail
    assert "LeastPrivilege" in failed.detail
    assert "interpreter does not exist" in failed.detail
    assert "last result 0x1" in failed.detail
    assert "check: not installed" in failed.detail

    errored = tasks_check((), query_error="PowerShell failed")
    assert errored.status == "fail"
    assert "PowerShell failed" in errored.detail


def test_path_check_skips_under_override_and_checkout_and_checks_which(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    venv_scripts = checkout / ".venv" / "Scripts"
    venv_scripts.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text(
        '[project]\nname = "weatherbot"\nversion = "2.0.0.dev0"\n',
        encoding="utf-8",
    )
    checkout_python = venv_scripts / "python.exe"
    checkout_python.write_bytes(b"")

    assert path_check(data_dir_overridden=True).status == "skip"
    assert path_check(interpreter=checkout_python).status == "skip"

    tool_dir = tmp_path / "tools" / "weatherbot" / "Scripts"
    tool_dir.mkdir(parents=True)
    tool_python = tool_dir / "pythonw.exe"
    tool_python.write_bytes(b"")
    tool_cli = tool_dir / "weatherbot.exe"
    tool_cli.write_bytes(b"")

    passed = path_check(interpreter=tool_python, which=lambda _cmd: str(tool_cli))
    assert passed.status == "pass"
    assert len(passed.name) <= 10  # noqa: PLR2004 - column width cap

    missing = path_check(interpreter=tool_python, which=lambda _cmd: None)
    assert missing.status == "fail"
    assert "not on PATH" in missing.detail

    shadow_cli = tmp_path / "old-venv" / "Scripts" / "weatherbot.exe"
    shadowed = path_check(interpreter=tool_python, which=lambda _cmd: str(shadow_cli))
    assert shadowed.status == "fail"
    assert str(shadow_cli.parent) in shadowed.detail
    assert "~/.local/bin" in shadowed.detail


def test_heartbeat_check_requires_fresh_serve_row_on_default_data_dir_when_serve_installed() -> (
    None
):
    absent = heartbeat_check((), serve_installed=True, data_dir_overridden=False)
    assert absent.status == "fail"
    assert "serve task is installed" in absent.detail

    skipped_override = heartbeat_check((), serve_installed=True, data_dir_overridden=True)
    assert skipped_override.status == "skip"

    stale_row = Heartbeat(
        kind="runner",
        name="serve",
        last_attempt_at=NOW - timedelta(minutes=25),
        last_success_at=NOW - timedelta(minutes=25),
        consecutive_failures=0,
        last_error_kind=None,
        expected_every_s=300,
        updated_at=NOW - timedelta(minutes=25),
    )
    judged_stale = staleness([stale_row], NOW)
    failed = heartbeat_check(judged_stale, serve_installed=True, data_dir_overridden=False)
    assert failed.status == "fail"
    assert "serve" in failed.detail

    fresh_row = Heartbeat(
        kind="runner",
        name="serve",
        last_attempt_at=NOW - timedelta(minutes=1),
        last_success_at=NOW - timedelta(minutes=1),
        consecutive_failures=0,
        last_error_kind=None,
        expected_every_s=300,
        updated_at=NOW - timedelta(minutes=1),
    )
    judged_fresh = staleness([fresh_row], NOW)
    passed = heartbeat_check(judged_fresh, serve_installed=True, data_dir_overridden=False)
    assert passed.status == "pass"


def test_diagnose_and_doctor_cli_exit_zero_on_fresh_temp_database(tmp_path: Path) -> None:
    paths = AppPaths.resolve()
    tool_dir = tmp_path / "tools" / "Scripts"
    tool_dir.mkdir(parents=True)
    tool_python = tool_dir / "pythonw.exe"
    tool_python.write_bytes(b"")
    tool_cli = tool_dir / "weatherbot.exe"
    tool_cli.write_bytes(b"")

    with open_database(paths) as database:
        report = asyncio.run(
            diagnose(
                settings_problem=None,
                settings_file_exists=False,
                database=database,
                database_problem=None,
                created=True,
                offline=True,
                network=Network(make_fetcher=quiet_fetcher),
                now=NOW,
                identity=True,
                toast_on=True,
                data_dir_overridden=False,
                windows=True,
                tasks=(
                    _task("serve", command=str(tool_python)),
                    _task("check", command=str(tool_python), arguments=CHECK_ARGUMENTS),
                ),
                interpreter=tool_python,
                interpreter_exists=lambda _p: True,
                which=lambda _cmd: str(tool_cli),
            )
        )
    by_name = {c.name: c for c in report.checks}
    assert by_name["tasks"].status == "pass"
    assert by_name["path"].status == "pass"
    assert by_name["heartbeat"].status == "fail"
    assert len(report.tasks) == 2  # noqa: PLR2004 - serve and check

    # Under the test suite's WEATHERBOT_DATA_DIR override, a fresh temp database still exits 0.
    ran = run(["doctor", "--offline", "--json"], runtime())
    assert ran.exit_code == 0
    doc = parse(ran, DoctorDocument)
    assert doc.data.failed is False
    checks = {c.name: c.status for c in doc.data.checks}
    assert checks["tasks"] == "skip"
    assert checks["path"] == "skip"
    assert checks["heartbeat"] == "skip"
