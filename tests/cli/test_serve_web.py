# tests/cli/test_serve_web.py
"""``weatherbot serve`` embedded web server, ``--open/--no-open``, and ``monitor.lock`` URL."""

import socket
from typing import Final

import httpx
import pytest
from cli_support import MIAMI, add_landmark, quiet_fetcher, recorded_services, run, runtime
from source_support import NOW

from weatherbot.cli.runtime import Runtime
from weatherbot.services.config import AppPaths
from weatherbot.services.locks import ProcessLock
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import CycleRepository
from weatherbot.web import server as server_module

USAGE: Final = 2


def test_serve_starts_web_server_answers_health_and_honors_open_flag() -> None:
    opened: list[str] = []
    health_status: list[int] = []

    async def _query_health_then_stop(_seconds: float) -> None:
        assert len(opened) == 1
        async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
            res = await client.get(f"{opened[0]}/api/health")
            health_status.append(res.status_code)
        raise KeyboardInterrupt

    with recorded_services() as router:
        router.route(host="127.0.0.1").pass_through()
        add_landmark(MIAMI, "miami-dade")
        base = runtime(now=NOW)
        rt = Runtime(
            environ=base.environ,
            make_fetcher=quiet_fetcher,
            make_toast=base.make_toast,
            identity=base.identity,
            task_runner=base.task_runner,
            windows=base.windows,
            open_browser=opened.append,
            now=lambda: NOW,
            sleep=_query_health_then_stop,
            terminal=False,
        )
        result = run(["serve", "--open"], rt)

    assert result.exit_code == 0, result.stderr
    assert len(opened) == 1
    assert opened[0].startswith("http://127.0.0.1:")
    assert health_status == [200]


def test_serve_opens_browser_by_default_only_in_terminal_and_no_open_suppresses_it() -> None:
    opened_terminal: list[str] = []
    opened_no_open: list[str] = []

    async def _stop_immediately(_seconds: float) -> None:
        raise KeyboardInterrupt

    with recorded_services() as router:
        router.route(host="127.0.0.1").pass_through()
        add_landmark(MIAMI, "miami-dade")
        base = runtime(now=NOW)
        rt_term = Runtime(
            environ=base.environ,
            make_fetcher=quiet_fetcher,
            make_toast=base.make_toast,
            identity=base.identity,
            task_runner=base.task_runner,
            windows=base.windows,
            open_browser=opened_terminal.append,
            now=lambda: NOW,
            sleep=_stop_immediately,
            terminal=True,
        )
        assert run(["serve"], rt_term).exit_code == 0

        rt_no_open = Runtime(
            environ=base.environ,
            make_fetcher=quiet_fetcher,
            make_toast=base.make_toast,
            identity=base.identity,
            task_runner=base.task_runner,
            windows=base.windows,
            open_browser=opened_no_open.append,
            now=lambda: NOW,
            sleep=_stop_immediately,
            terminal=True,
        )
        assert run(["serve", "--no-open"], rt_no_open).exit_code == 0

    assert len(opened_terminal) == 1
    assert opened_no_open == []


def test_serve_continues_monitor_when_web_port_cannot_be_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = AppPaths.resolve()
    opened: list[str] = []

    def _fail_bind(_host: str, _port: int) -> socket.socket:
        msg = "port busy"
        raise OSError(msg)

    async def _stop_on_first_sleep(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(server_module, "DEFAULT_RETRY_DELAY_S", 0.0)
    monkeypatch.setattr(server_module, "_create_bound_socket", _fail_bind)

    with recorded_services() as router:
        router.route(host="127.0.0.1").pass_through()
        add_landmark(MIAMI, "miami-dade")
        base = runtime(now=NOW)
        rt = Runtime(
            environ=base.environ,
            make_fetcher=quiet_fetcher,
            make_toast=base.make_toast,
            identity=base.identity,
            task_runner=base.task_runner,
            windows=base.windows,
            open_browser=opened.append,
            now=lambda: NOW,
            sleep=_stop_on_first_sleep,
            terminal=True,
        )
        result = run(["serve"], rt)

    assert result.exit_code == 0, result.stderr
    assert opened == []
    with open_database(paths) as database:
        cycles = CycleRepository(database.engine).recent(5)
    assert len(cycles) == 1
    assert cycles[0].status == "complete"


def test_check_without_once_runs_monitor_without_starting_web_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_created = False

    def _forbidden_bind(_host: str, _port: int) -> socket.socket:
        nonlocal web_created
        web_created = True
        msg = "check must not bind web socket"
        raise AssertionError(msg)

    async def _stop_on_first_sleep(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(server_module, "_create_bound_socket", _forbidden_bind)

    with recorded_services() as router:
        router.route(host="127.0.0.1").pass_through()
        add_landmark(MIAMI, "miami-dade")
        base = runtime(now=NOW)
        rt = Runtime(
            environ=base.environ,
            make_fetcher=quiet_fetcher,
            make_toast=base.make_toast,
            identity=base.identity,
            task_runner=base.task_runner,
            windows=base.windows,
            now=lambda: NOW,
            sleep=_stop_on_first_sleep,
            terminal=False,
        )
        result = run(["check"], rt)

    assert result.exit_code == 0, result.stderr
    assert web_created is False


def test_serve_exits_2_with_holder_pid_start_time_and_dashboard_url_when_locked() -> None:
    paths = AppPaths.resolve()
    holder = ProcessLock(paths.monitor_lock_path)
    assert holder.try_acquire()
    try:
        result = run(["serve"])
    finally:
        holder.release()

    assert result.exit_code == USAGE
    assert "the monitor is already running" in result.stderr
    assert "pid " in result.stderr
    assert "since " in result.stderr
    assert "dashboard at http://127.0.0.1:8765" in result.stderr
