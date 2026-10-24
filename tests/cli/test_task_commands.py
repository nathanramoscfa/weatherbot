# tests/cli/test_task_commands.py
"""CLI command tests for ``install-task``, ``uninstall-task``, and ``check --once --if-stale``."""

import json
import os
from datetime import timedelta
from pathlib import Path

from cli_support import (
    FakeRegistry,
    FakeTaskRunner,
    parse,
    recorded_services,
    run,
    runtime,
)
from source_support import NOW

from weatherbot.cli.documents import (
    CheckDocument,
    InstallTaskDocument,
    UninstallTaskDocument,
)
from weatherbot.services.config import AppPaths
from weatherbot.services.locks import ProcessLock
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import HeartbeatRepository
from weatherbot.services.tasks import CHECK_ARGUMENTS, SERVE_ARGUMENTS
from weatherbot.services.toast import Identity


def _tool_interpreter(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "uv-tools" / "weatherbot" / "Scripts"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "pythonw.exe").write_bytes(b"")
    python_exe = bin_dir / "python.exe"
    python_exe.write_bytes(b"")
    return python_exe


def _checkout_interpreter(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    bin_dir = checkout / ".venv" / "Scripts"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (checkout / "pyproject.toml").write_text(
        '[project]\nname = "weatherbot"\nversion = "2.0.0.dev0"\n',
        encoding="utf-8",
    )
    (bin_dir / "pythonw.exe").write_bytes(b"")
    python_exe = bin_dir / "python.exe"
    python_exe.write_bytes(b"")
    return python_exe


def _query_json(pythonw: Path) -> str:
    return json.dumps(
        [
            {
                "name": "serve",
                "state": "Ready",
                "enabled": True,
                "command": str(pythonw),
                "arguments": SERVE_ARGUMENTS,
                "working_directory": r"C:\data\weatherbot",
                "logon_type": "InteractiveToken",
                "run_level": "LeastPrivilege",
                "last_run_time": None,
                "next_run_time": None,
                "last_task_result": 0x41303,
            },
            {
                "name": "check",
                "state": "Ready",
                "enabled": True,
                "command": str(pythonw),
                "arguments": CHECK_ARGUMENTS,
                "working_directory": r"C:\data\weatherbot",
                "logon_type": "InteractiveToken",
                "run_level": "LeastPrivilege",
                "last_run_time": None,
                "next_run_time": "2026-10-12T21:25:00+00:00",
                "last_task_result": 0x41303,
            },
        ]
    )


def _env_with_user() -> dict[str, str]:
    base = dict(os.environ)
    base["USERNAME"] = "operator"
    base["USERDOMAIN"] = "EXAMPLE"
    return base


def test_install_task_refuses_off_windows_and_checkout_without_allow_checkout(
    tmp_path: Path,
) -> None:
    tool_py = _tool_interpreter(tmp_path)
    checkout_py = _checkout_interpreter(tmp_path)

    off_win = run(
        ["install-task"],
        runtime(windows=False, interpreter=tool_py, environ=_env_with_user()),
    )
    assert off_win.exit_code == 2  # noqa: PLR2004 - usage error
    assert "Windows" in off_win.stderr

    refused = run(
        ["install-task"],
        runtime(windows=True, interpreter=checkout_py, environ=_env_with_user()),
    )
    assert refused.exit_code == 2  # noqa: PLR2004 - usage error
    assert "uv tool install --from" in refused.stderr


def test_install_task_registers_identity_and_tasks_and_validates_schema(
    tmp_path: Path,
) -> None:
    tool_py = _tool_interpreter(tmp_path)
    pythonw = tool_py.with_name("pythonw.exe")
    runner = FakeTaskRunner(query_json=_query_json(pythonw))
    registry = FakeRegistry(None)

    ran = run(
        ["install-task", "--json"],
        runtime(
            windows=True,
            interpreter=tool_py,
            task_runner=runner,
            identity=Identity(registry),
            environ=_env_with_user(),
        ),
    )

    assert ran.exit_code == 0
    doc = parse(ran, InstallTaskDocument)
    assert doc.data.identity_outcome == "registered"
    assert doc.data.failed is False
    assert [o.name for o in doc.data.outcomes] == ["serve", "check"]
    assert [t.name for t in doc.data.tasks] == ["serve", "check"]
    assert registry.writes == 1
    assert set(runner.written_xml) == {r"\Weatherbot\serve", r"\Weatherbot\check"}

    # Plain-text mode and --allow-checkout on a checkout interpreter also succeed.
    checkout_py = _checkout_interpreter(tmp_path)
    plain = run(
        ["install-task", "--allow-checkout"],
        runtime(
            windows=True,
            interpreter=checkout_py,
            task_runner=runner,
            identity=Identity(registry),
            environ=_env_with_user(),
        ),
    )
    assert plain.exit_code == 0
    assert "Scheduled tasks registered" in plain.stdout
    assert "Task Scheduler state" in plain.stdout


def test_install_task_exits_one_when_registration_fails(tmp_path: Path) -> None:
    tool_py = _tool_interpreter(tmp_path)
    runner = FakeTaskRunner(create_returncode=1, query_json="[]")

    ran = run(
        ["install-task", "--json"],
        runtime(
            windows=True,
            interpreter=tool_py,
            task_runner=runner,
            environ=_env_with_user(),
        ),
    )
    assert ran.exit_code == 1
    doc = parse(ran, InstallTaskDocument)
    assert doc.data.failed is True


def test_uninstall_task_stops_serve_removes_tasks_and_validates_schema() -> None:
    off_win = run(["uninstall-task"], runtime(windows=False))
    assert off_win.exit_code == 2  # noqa: PLR2004 - usage error

    runner = FakeTaskRunner()
    ran = run(
        ["uninstall-task", "--json"],
        runtime(windows=True, task_runner=runner),
    )
    assert ran.exit_code == 0
    doc = parse(ran, UninstallTaskDocument)
    assert doc.data.stopped_serve is True
    assert doc.data.failed is False
    assert [o.name for o in doc.data.outcomes] == ["serve", "check"]

    plain = run(
        ["uninstall-task"],
        runtime(windows=True, task_runner=runner),
    )
    assert plain.exit_code == 0
    assert "Scheduled tasks removed" in plain.stdout


def test_check_if_stale_cli_validates_once_flag_and_runs_or_skips() -> None:
    bad = run(["check", "--if-stale"], runtime())
    assert bad.exit_code == 2  # noqa: PLR2004 - usage error
    assert "--if-stale requires --once" in bad.stderr

    paths = AppPaths.resolve()
    with open_database(paths) as database:
        HeartbeatRepository(database.engine, now=lambda: NOW).record(
            "runner",
            "serve",
            at=NOW - timedelta(minutes=1),
            result="success",
            expected_every_s=300,
        )

    lock = ProcessLock(paths.monitor_lock_path)
    assert lock.try_acquire()
    try:
        skipped = run(["check", "--once", "--if-stale"], runtime())
        assert skipped.exit_code == 0
        assert "Monitor is healthy" in skipped.stdout
    finally:
        lock.release()

    with recorded_services():
        ran = run(["check", "--once", "--if-stale", "--json"], runtime())
    assert ran.exit_code == 0
    doc = parse(ran, CheckDocument)
    assert doc.data.cycle.runner == "fallback"
    assert doc.data.cycle.trigger == "fallback"
