# tests/services/test_tasks.py
"""Unit tests for Windows Task Scheduler XML definitions, install, uninstall, run, and query."""

import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import HeartbeatRepository
from weatherbot.services.tasks import (
    CHECK_ARGUMENTS,
    CHECK_INTERVAL,
    CHECK_TIME_LIMIT,
    CREATE_NO_WINDOW,
    POWERSHELL_EXE,
    QUERY_SCRIPT,
    SCHTASKS_EXE,
    SERVE_ARGUMENTS,
    SERVE_TIME_LIMIT,
    TASK_FOLDER,
    TASK_NOT_RUN_RESULT,
    TASK_RUNNING_RESULT,
    TaskSchedulerError,
    check_start_boundary,
    current_user_id,
    definition_xml,
    install,
    is_checkout_interpreter,
    query,
    resolve_pythonw,
    run,
    run_subprocess,
    task_xml,
    uninstall,
)

USER_ID = r"EXAMPLE\operator"
EDT = timezone(timedelta(hours=-4))


def _make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
    )


def _fake_pythonw(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "uv-tools" / "weatherbot" / "Scripts"
    bin_dir.mkdir(parents=True, exist_ok=True)
    pythonw = bin_dir / "pythonw.exe"
    pythonw.write_bytes(b"")
    (bin_dir / "python.exe").write_bytes(b"")
    return pythonw


def test_task_xml_renders_serve_and_check_with_escaped_values(tmp_path: Path) -> None:
    special_dir = tmp_path / "dir & <test>"
    pythonw = special_dir / "pythonw.exe"
    special_user = r"EXAMPLE\op&<erator>"
    ref = datetime(2026, 10, 24, 14, 10, 0, tzinfo=EDT)

    serve_doc = task_xml(
        "serve",
        user_id=special_user,
        interpreter=pythonw,
        working_directory=special_dir,
        start=ref,
    )
    check_doc = task_xml(
        "check",
        user_id=special_user,
        interpreter=pythonw,
        working_directory=special_dir,
        start=ref,
    )

    for doc in (serve_doc, check_doc):
        assert '<Task version="1.2"' in doc
        assert "<UserId>EXAMPLE\\op&amp;&lt;erator&gt;</UserId>" in doc
        assert "<LogonType>InteractiveToken</LogonType>" in doc
        assert "<RunLevel>LeastPrivilege</RunLevel>" in doc
        assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in doc
        assert "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>" in doc
        assert "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>" in doc
        assert "<AllowStartOnDemand>true</AllowStartOnDemand>" in doc
        assert "<Enabled>true</Enabled>" in doc
        assert "<WakeToRun>false</WakeToRun>" in doc
        assert "<Priority>7</Priority>" in doc
        assert "dir &amp; &lt;test&gt;" in doc
        assert "Registered by weatherbot install-task" in doc

    assert "<LogonTrigger>" in serve_doc
    assert f"<ExecutionTimeLimit>{SERVE_TIME_LIMIT}</ExecutionTimeLimit>" in serve_doc
    assert "<StartWhenAvailable>false</StartWhenAvailable>" in serve_doc
    assert f"<Arguments>{SERVE_ARGUMENTS}</Arguments>" in serve_doc

    assert "<TimeTrigger>" in check_doc
    assert f"<Interval>{CHECK_INTERVAL}</Interval>" in check_doc
    assert "<Duration>" not in check_doc
    assert "<StartBoundary>2026-10-24T14:25:00-04:00</StartBoundary>" in check_doc
    assert f"<ExecutionTimeLimit>{CHECK_TIME_LIMIT}</ExecutionTimeLimit>" in check_doc
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in check_doc
    assert f"<Arguments>{CHECK_ARGUMENTS}</Arguments>" in check_doc


def test_check_start_boundary_rolls_to_next_hour_after_minute_25() -> None:
    before = datetime(2026, 10, 24, 14, 24, 59, tzinfo=EDT)
    after = datetime(2026, 10, 24, 14, 25, 1, tzinfo=EDT)

    assert check_start_boundary(before) == datetime(2026, 10, 24, 14, 25, 0, tzinfo=EDT)
    assert check_start_boundary(after) == datetime(2026, 10, 24, 15, 25, 0, tzinfo=EDT)


def test_install_writes_utf16_bom_xml_registers_both_tasks_and_deletes_temp_files(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    pythonw = _fake_pythonw(tmp_path)
    calls: list[tuple[tuple[str, ...], int]] = []
    captured_bytes: dict[str, bytes] = {}

    def runner(
        argv: Sequence[str], *, creationflags: int = CREATE_NO_WINDOW
    ) -> subprocess.CompletedProcess[str]:
        args = tuple(argv)
        calls.append((args, creationflags))
        xml_file = Path(args[args.index("/XML") + 1])
        assert xml_file.parent == paths.data_dir
        raw = xml_file.read_bytes()
        assert raw.startswith(b"\xff\xfe")
        captured_bytes[args[args.index("/TN") + 1]] = raw
        return subprocess.CompletedProcess(list(args), 0, stdout="SUCCESS\n", stderr="")

    outcomes = install(
        paths,
        interpreter=pythonw.with_name("python.exe"),
        user_id=USER_ID,
        start=datetime(2026, 10, 24, 14, 0, 0, tzinfo=EDT),
        runner=runner,
    )

    assert [o.name for o in outcomes] == ["serve", "check"]
    assert all(o.ok for o in outcomes)
    assert len(calls) == 2  # noqa: PLR2004 - serve and check registrations
    for (args, flags), name in zip(calls, ("serve", "check"), strict=True):
        assert flags == CREATE_NO_WINDOW
        assert args[0] == SCHTASKS_EXE
        assert "system32" in args[0].lower()
        assert args[1:4] == ("/Create", "/TN", f"{TASK_FOLDER}{name}")
        assert args[4] == "/XML"
        assert args[6] == "/F"
        assert not (paths.data_dir / f"task-{name}.xml").exists()

    serve_text = captured_bytes[r"\Weatherbot\serve"].decode("utf-16")
    assert str(pythonw) in serve_text


def test_uninstall_ends_serve_first_deletes_both_and_clears_serve_cadence(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    now = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)
    with open_database(paths) as database:
        HeartbeatRepository(database.engine, now=lambda: now).record(
            "runner",
            "serve",
            at=now,
            result="success",
            expected_every_s=300,
        )

    calls: list[tuple[tuple[str, ...], int]] = []

    def runner(
        argv: Sequence[str], *, creationflags: int = CREATE_NO_WINDOW
    ) -> subprocess.CompletedProcess[str]:
        args = tuple(argv)
        calls.append((args, creationflags))
        if "/Delete" in args and args[args.index("/TN") + 1].endswith("check"):
            return subprocess.CompletedProcess(
                list(args),
                1,
                stdout="",
                stderr="ERROR: The system cannot find the file specified.\n",
            )
        return subprocess.CompletedProcess(list(args), 0, stdout="SUCCESS\n", stderr="")

    result = uninstall(paths=paths, now=now, runner=runner)

    assert result.stopped_serve is True
    assert all(item.ok for item in result.outcomes)
    assert result.outcomes[1].detail == "absent"
    assert [c[0][:4] for c in calls] == [
        (SCHTASKS_EXE, "/End", "/TN", r"\Weatherbot\serve"),
        (SCHTASKS_EXE, "/Delete", "/TN", r"\Weatherbot\serve"),
        (SCHTASKS_EXE, "/Delete", "/TN", r"\Weatherbot\check"),
    ]
    assert all(c[1] == CREATE_NO_WINDOW for c in calls)

    with open_database(paths) as database:
        rows = HeartbeatRepository(database.engine, now=lambda: now).rows()
    serve_row = next(r for r in rows if r.kind == "runner" and r.name == "serve")
    assert serve_row.expected_every_s is None


def test_run_invokes_schtasks_run_with_create_no_window() -> None:
    calls: list[tuple[tuple[str, ...], int]] = []

    def runner(
        argv: Sequence[str], *, creationflags: int = CREATE_NO_WINDOW
    ) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(argv), creationflags))
        return subprocess.CompletedProcess(list(argv), 0, stdout="SUCCESS\n", stderr="")

    outcome = run("serve", runner=runner)

    assert outcome.ok is True
    assert calls == [((SCHTASKS_EXE, "/Run", "/TN", r"\Weatherbot\serve"), CREATE_NO_WINDOW)]

    with pytest.raises(ValueError, match="Unknown task name"):
        run("unknown", runner=runner)


def test_query_script_and_json_parsing_for_zero_one_two_and_running_tasks() -> None:
    assert "@(" in QUERY_SCRIPT
    assert ".ToString('o')" in QUERY_SCRIPT
    assert "-Depth 4" in QUERY_SCRIPT
    assert "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8" in QUERY_SCRIPT

    calls: list[tuple[tuple[str, ...], int]] = []
    payload: str = "[]"

    def runner(
        argv: Sequence[str], *, creationflags: int = CREATE_NO_WINDOW
    ) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(argv), creationflags))
        return subprocess.CompletedProcess(list(argv), 0, stdout=payload, stderr="")

    assert query(runner=runner) == ()
    assert calls[-1][0][:4] == (
        POWERSHELL_EXE,
        "-NoProfile",
        "-NonInteractive",
        "-Command",
    )
    assert calls[-1][1] == CREATE_NO_WINDOW

    one_task = {
        "name": "serve",
        "state": "Running",
        "enabled": True,
        "command": r"C:\tools\weatherbot\Scripts\pythonw.exe",
        "arguments": SERVE_ARGUMENTS,
        "working_directory": r"C:\data\weatherbot",
        "logon_type": "InteractiveToken",
        "run_level": "LeastPrivilege",
        "last_run_time": "2026-10-24T12:00:00.0000000-04:00",
        "next_run_time": None,
        "last_task_result": TASK_RUNNING_RESULT,
    }
    payload = json.dumps(one_task)
    single = query(runner=runner)
    assert len(single) == 1
    assert single[0].name == "serve"
    assert single[0].state == "Running"
    assert single[0].last_task_result == TASK_RUNNING_RESULT
    assert single[0].last_run_time == datetime(2026, 10, 24, 16, 0, tzinfo=UTC)

    two_tasks = [
        one_task,
        {
            "name": "check",
            "state": "Ready",
            "enabled": True,
            "command": r"C:\tools\weatherbot\Scripts\pythonw.exe",
            "arguments": CHECK_ARGUMENTS,
            "working_directory": r"C:\data\weatherbot",
            "logon_type": "InteractiveToken",
            "run_level": "LeastPrivilege",
            "last_run_time": "1999-11-30T00:00:00.0000000",
            "next_run_time": "2026-10-24T13:25:00.0000000-04:00",
            "last_task_result": 0x41303,
        },
    ]
    payload = json.dumps(two_tasks)
    both = query(runner=runner)
    assert [t.name for t in both] == ["serve", "check"]
    assert both[1].last_run_time is None
    assert both[1].next_run_time == datetime(2026, 10, 24, 17, 25, tzinfo=UTC)
    assert both[1].last_task_result == TASK_NOT_RUN_RESULT


def test_is_checkout_interpreter_detects_weatherbot_pyproject(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    venv_scripts = checkout / ".venv" / "Scripts"
    venv_scripts.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text(
        '[project]\nname = "weatherbot"\nversion = "2.0.0.dev0"\n',
        encoding="utf-8",
    )
    checkout_python = venv_scripts / "python.exe"
    checkout_python.write_bytes(b"")

    tool_python = _fake_pythonw(tmp_path)

    assert is_checkout_interpreter(checkout_python) is True
    assert is_checkout_interpreter(tool_python) is False


def test_helpers_validate_inputs_and_subprocess_guards(tmp_path: Path) -> None:
    assert current_user_id({"USERNAME": "operator", "USERDOMAIN": "EXAMPLE"}) == USER_ID
    with pytest.raises(TaskSchedulerError, match="USERNAME"):
        current_user_id({"USERNAME": ""})

    missing = tmp_path / "missing" / "python.exe"
    with pytest.raises(TaskSchedulerError, match=r"pythonw\.exe"):
        resolve_pythonw(missing)

    with pytest.raises(ValueError, match="System32"):
        run_subprocess(["cmd.exe"], creationflags=CREATE_NO_WINDOW)

    with pytest.raises(ValueError, match="Unknown task name"):
        task_xml(
            "invalid",  # type: ignore[arg-type]
            user_id=USER_ID,
            interpreter="pythonw.exe",
            working_directory=tmp_path,
        )

    doc = definition_xml(
        r"\Weatherbot\probe",
        user_id=USER_ID,
        command="cmd.exe",
        arguments="/c exit 0",
        working_directory=tmp_path,
        trigger="logon",
        enabled=False,
    )
    assert "<Enabled>false</Enabled>" in doc
