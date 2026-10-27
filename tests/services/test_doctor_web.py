# tests/services/test_doctor_web.py
"""Unit and loopback tests for ``doctor``'s ``web`` check."""

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
from source_support import NOW

from weatherbot import __version__
from weatherbot.services.config import AppPaths, Settings, WebSettings
from weatherbot.services.doctor import Check, web_check
from weatherbot.services.health import staleness
from weatherbot.services.persistence.database import head_revision, open_database
from weatherbot.services.persistence.repositories import Heartbeat
from weatherbot.web.app import WebState, create_app
from weatherbot.web.server import WebServer


def _serve_heartbeat(*, expected_every_s: int | None = 300, minutes_ago: int = 1) -> Heartbeat:
    instant = NOW - timedelta(minutes=minutes_ago)
    return Heartbeat(
        kind="runner",
        name="serve",
        last_attempt_at=instant,
        last_success_at=instant,
        consecutive_failures=0,
        last_error_kind=None,
        expected_every_s=expected_every_s,
        updated_at=instant,
    )


def test_web_check_skips_under_override_closed_db_not_running_or_stale() -> None:
    fresh = staleness([_serve_heartbeat(expected_every_s=300, minutes_ago=1)], NOW)
    stopped = staleness([_serve_heartbeat(expected_every_s=None, minutes_ago=1)], NOW)
    stale = staleness([_serve_heartbeat(expected_every_s=300, minutes_ago=20)], NOW)

    overridden = asyncio.run(web_check(fresh, data_dir_overridden=True))
    assert overridden.status == "skip"
    assert "WEATHERBOT_DATA_DIR" in overridden.detail

    closed = asyncio.run(web_check(None, data_dir_overridden=False))
    assert closed.status == "skip"

    absent = asyncio.run(web_check((), data_dir_overridden=False))
    assert absent.status == "skip"
    assert "serve is not running" in absent.detail

    stopped_res = asyncio.run(web_check(stopped, data_dir_overridden=False))
    assert stopped_res.status == "skip"
    assert "serve is not running" in stopped_res.detail

    stale_res = asyncio.run(web_check(stale, data_dir_overridden=False))
    assert stale_res.status == "skip"
    assert "stale" in stale_res.detail


def test_web_check_passes_against_running_loopback_server_and_fails_on_mismatch(
    tmp_path: Path,
) -> None:
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    fresh = staleness([_serve_heartbeat(expected_every_s=300, minutes_ago=1)], NOW)
    try:
        state = WebState(
            database=database,
            paths=paths,
            settings=Settings(),
            clock=lambda: NOW,
            started_at=NOW,
            static_dir=static_dir,
        )
        app = create_app(state)
        server = WebServer(app, host="127.0.0.1", port=0)

        async def _probe_live() -> tuple[Check, Check]:
            stop = asyncio.Event()
            task = asyncio.create_task(server.serve(stop))
            await asyncio.wait_for(server.started.wait(), timeout=5.0)
            assert server.bound_port is not None
            ws = WebSettings(host="127.0.0.1", port=server.bound_port)
            passed = await web_check(
                fresh,
                web_settings=ws,
                data_dir_overridden=False,
            )
            mismatched = await web_check(
                fresh,
                web_settings=ws,
                data_dir_overridden=False,
                expected_version="0.0.0-other",
                expected_head=head_revision(),
            )
            stop.set()
            await asyncio.wait_for(task, timeout=5.0)
            return passed, mismatched

        passed, mismatched = asyncio.run(_probe_live())
    finally:
        database.close()

    assert passed.status == "pass"
    assert f"http://127.0.0.1:{server.bound_port}" in passed.detail
    assert mismatched.status == "fail"
    assert __version__ in mismatched.detail


def test_web_check_fails_when_server_unreachable_or_errors() -> None:
    fresh = staleness([_serve_heartbeat(expected_every_s=300, minutes_ago=1)], NOW)

    def _refuse(_request: httpx.Request) -> httpx.Response:
        msg = "connection refused"
        raise httpx.ConnectError(msg)

    unreachable = asyncio.run(
        web_check(
            fresh,
            web_settings=WebSettings(host="127.0.0.1", port=8765),
            data_dir_overridden=False,
            transport=httpx.MockTransport(_refuse),
        )
    )
    assert unreachable.status == "fail"
    assert "ConnectError" in unreachable.detail

    bad_status = asyncio.run(
        web_check(
            fresh,
            web_settings=WebSettings(host="127.0.0.1", port=8765),
            data_dir_overridden=False,
            transport=httpx.MockTransport(lambda _r: httpx.Response(503)),
        )
    )
    assert bad_status.status == "fail"
    assert "503" in bad_status.detail
