# tests/web/test_web_server.py
"""``WebServer`` loopback socket binding, graceful stop, ``before_stop`` hooks, and bind failure."""

import asyncio
import logging
import socket
from http import HTTPStatus
from pathlib import Path
from typing import Final

import httpx
import pytest
from source_support import NOW

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.persistence.database import open_database
from weatherbot.web import server as server_module
from weatherbot.web.app import WebState, create_app
from weatherbot.web.server import WebServer

EXPECTED_ATTEMPTS: Final = 6


def test_web_server_binds_ephemeral_port_serves_health_and_runs_before_stop(
    tmp_path: Path,
) -> None:
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    hooks_called: list[str] = []
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
        web_server = WebServer(
            app,
            host="localhost",
            port=0,
            before_stop=[lambda: hooks_called.append("stopped")],
        )

        async def _drive() -> httpx.Response:
            stop = asyncio.Event()
            serve_task = asyncio.create_task(web_server.serve(stop))
            await asyncio.wait_for(web_server.started.wait(), timeout=5.0)
            assert web_server.bound_port is not None
            assert web_server.bound_port > 0
            assert web_server.address == f"http://localhost:{web_server.bound_port}"
            async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
                response = await client.get(f"http://127.0.0.1:{web_server.bound_port}/api/health")
            stop.set()
            await asyncio.wait_for(serve_task, timeout=5.0)
            return response

        response = asyncio.run(_drive())
    finally:
        database.close()

    assert response.status_code == HTTPStatus.OK
    assert response.json()["database"]["current"] is True
    assert hooks_called == ["stopped"]


def test_web_server_logs_warning_and_returns_after_bind_retries(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    attempts = 0
    sleeps: list[float] = []

    def _refuse_bind(_host: str, _port: int) -> socket.socket:
        nonlocal attempts
        attempts += 1
        msg = "address in use"
        raise OSError(msg)

    async def _fast_sleep(seconds: float) -> None:
        sleeps.append(seconds)

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
        web_server = WebServer(
            app,
            host="127.0.0.1",
            port=8765,
            retries=5,
            retry_delay_s=2.0,
            sleep=_fast_sleep,
            socket_factory=_refuse_bind,
        )
        with caplog.at_level(logging.WARNING, logger="weatherbot.web.server"):
            asyncio.run(web_server.serve(asyncio.Event()))
    finally:
        database.close()

    assert attempts == EXPECTED_ATTEMPTS
    assert sleeps == [2.0, 2.0, 2.0, 2.0, 2.0]
    assert "the web server could not start: OSError" in caplog.text


def test_web_server_catches_system_exit_from_uvicorn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    static_dir = tmp_path / "static"
    static_dir.mkdir()

    async def _raise_system_exit(_self: object, sockets: list[socket.socket] | None = None) -> None:
        del sockets
        raise SystemExit(1)

    monkeypatch.setattr(server_module.EmbeddedUvicornServer, "serve", _raise_system_exit)
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
        web_server = WebServer(app, host="127.0.0.1", port=0)
        with caplog.at_level(logging.WARNING, logger="weatherbot.web.server"):
            asyncio.run(web_server.serve(asyncio.Event()))
    finally:
        database.close()

    assert "the web server could not start: SystemExit" in caplog.text
