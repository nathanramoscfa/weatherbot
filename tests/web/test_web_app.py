# tests/web/test_web_app.py
"""``create_app`` and ``GET /api/health`` over ``httpx.ASGITransport``."""

import asyncio
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Final

import httpx
from source_support import NOW

from weatherbot import __version__
from weatherbot.services.config import AppPaths, Settings, setting_origins
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.database import Database, head_revision, open_database
from weatherbot.services.persistence.repositories import HeartbeatRepository
from weatherbot.web.app import WebState, create_app

CADENCE_S: Final = 300
AGE_S: Final = 30.0


def _make_state(
    paths: AppPaths,
    *,
    now: datetime = NOW,
    started_at: datetime = NOW - timedelta(minutes=10),
    static_dir: Path | None = None,
) -> tuple[WebState, Database]:
    database = open_database(paths, now=lambda: now)
    settings = Settings()
    origins = setting_origins(paths)
    state = WebState(
        database=database,
        paths=paths,
        settings=settings,
        setting_origins=origins,
        clock=lambda: now,
        started_at=started_at,
        static_dir=static_dir,
    )
    return state, database


def test_health_endpoint_reports_process_database_scheduler_and_heartbeats(
    tmp_path: Path,
) -> None:
    paths = AppPaths.resolve()
    empty_static = tmp_path / "empty-static"
    empty_static.mkdir()
    state, database = _make_state(paths, static_dir=empty_static)
    try:
        HeartbeatRepository(database.engine, now=lambda: NOW).record(
            "runner",
            "serve",
            at=NOW - timedelta(seconds=30),
            result="success",
            expected_every_s=CADENCE_S,
        )
        app = create_app(state)

        async def _query() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return await client.get("/api/health")

        response = asyncio.run(_query())
    finally:
        database.close()

    assert response.status_code == HTTPStatus.OK
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["version"] == __version__
    assert datetime.fromisoformat(body["started_at"]) == NOW - timedelta(minutes=10)
    assert datetime.fromisoformat(body["now"]) == NOW
    assert body["database"] == {
        "revision": head_revision(),
        "head": head_revision(),
        "current": True,
    }
    assert body["scheduler"]["expected_every_s"] == CADENCE_S
    assert body["scheduler"]["stale"] is False
    assert len(body["heartbeats"]) == 1
    assert body["heartbeats"][0]["name"] == "serve"
    assert body["heartbeats"][0]["age_s"] == AGE_S
    assert body["stale"] is False
    assert datetime.fromisoformat(body["next_product_at"]) > NOW.astimezone(UTC)
    assert body["ui"] == {"present": False, "index_sha256": None}
    assert body["corpus"] is False
    assert body["notice"] == NOTICE


def test_openapi_is_served_at_api_openapi_and_unknown_api_paths_return_json_404(
    tmp_path: Path,
) -> None:
    paths = AppPaths.resolve()
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        '<!doctype html><html><head><style nonce="__CSP_NONCE__"></style></head></html>',
        encoding="utf-8",
    )
    state, database = _make_state(paths, static_dir=static_dir)
    try:
        app = create_app(state)

        async def _run() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                openapi_res = await client.get("/api/openapi.json")
                missing_api = await client.get("/api/does-not-exist")
                docs_res = await client.get("/docs")
                redoc_res = await client.get("/redoc")
                return openapi_res, missing_api, docs_res, redoc_res

        openapi_res, missing_api, docs_res, redoc_res = asyncio.run(_run())
    finally:
        database.close()

    assert openapi_res.status_code == HTTPStatus.OK
    schema = openapi_res.json()
    assert str(schema["openapi"]).startswith("3.1.")
    assert "/api/health" in schema["paths"]
    assert "/docs" not in schema["paths"]
    assert "/redoc" not in schema["paths"]

    assert missing_api.status_code == HTTPStatus.NOT_FOUND
    assert missing_api.headers["content-type"].startswith("application/json")
    assert missing_api.headers["cache-control"] == "no-store"
    assert missing_api.json() == {"detail": "Not Found"}

    assert "swagger-ui" not in docs_res.text.lower()
    assert "redoc" not in redoc_res.text.lower()
