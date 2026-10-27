# tests/web/test_api_guards.py
"""Host allowlist, ``Sec-Fetch-Site``, ``Origin``, JSON write content-type, and security headers."""

import asyncio
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
from source_support import NOW

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.web.app import WebState, create_app


class _EchoPayload(BaseModel):
    name: str


def _app_with_write_route(tmp_path: Path) -> tuple[FastAPI, Database]:
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    static_dir = tmp_path / "static"
    static_dir.mkdir(exist_ok=True)
    state = WebState(
        database=database,
        paths=paths,
        settings=Settings(),
        clock=lambda: NOW,
        started_at=NOW,
        static_dir=static_dir,
    )
    app = create_app(state)
    router = APIRouter()

    @router.post("/api/probe-write")
    def probe_write(payload: _EchoPayload) -> dict[str, str]:
        return {"ok": payload.name}

    # Insert before the /api/{rest:path} fallback routes.
    app.router.routes.insert(0, router.routes[0])
    return app, database


def _assert_security_headers(headers: httpx.Headers, *, is_api: bool) -> None:
    csp = headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "https://tile.openstreetmap.org" in csp
    assert "frame-ancestors 'none'" in csp
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert headers["cross-origin-opener-policy"] == "same-origin"
    assert headers["cross-origin-resource-policy"] == "same-origin"
    assert headers["permissions-policy"] == "geolocation=(), camera=(), microphone=()"
    if is_api:
        assert headers["cache-control"] == "no-store"
    assert not any(k.lower().startswith("access-control-allow-") for k in headers)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "127.0.0.1:8765",
        "localhost",
        "localhost:8765",
        "[::1]",
        "[::1]:8765",
    ],
)
def test_trusted_loopback_hosts_pass(tmp_path: Path, host: str) -> None:
    app, database = _app_with_write_route(tmp_path)
    try:

        async def _call() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as c:
                return await c.get("/api/health", headers={"Host": host})

        response = asyncio.run(_call())
    finally:
        database.close()

    assert response.status_code == HTTPStatus.OK
    _assert_security_headers(response.headers, is_api=True)


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:8765",
        "192.168.1.5",
        "0.0.0.0",  # noqa: S104 - testing rejection of untrusted all-interfaces Host header
    ],
)
def test_untrusted_host_returns_400_with_security_headers(tmp_path: Path, host: str) -> None:
    app, database = _app_with_write_route(tmp_path)
    try:

        async def _call() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as c:
                return await c.get("/api/health", headers={"Host": host})

        response = asyncio.run(_call())
    finally:
        database.close()

    assert response.status_code == HTTPStatus.BAD_REQUEST
    _assert_security_headers(response.headers, is_api=True)


def test_sec_fetch_site_and_write_guards_enforce_same_origin_and_json(tmp_path: Path) -> None:
    app, database = _app_with_write_route(tmp_path)
    try:

        async def _exercise() -> dict[str, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as c:
                return {
                    "get_cross": await c.get(
                        "/api/health", headers={"Sec-Fetch-Site": "cross-site"}
                    ),
                    "get_same_site": await c.get(
                        "/api/health", headers={"Sec-Fetch-Site": "same-site"}
                    ),
                    "get_same_origin": await c.get(
                        "/api/health", headers={"Sec-Fetch-Site": "same-origin"}
                    ),
                    "get_none": await c.get("/api/health", headers={"Sec-Fetch-Site": "none"}),
                    "post_no_ct": await c.post("/api/probe-write", content=b'{"name":"a"}'),
                    "post_form": await c.post(
                        "/api/probe-write",
                        content=b"name=a",
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    ),
                    "post_bad_origin": await c.post(
                        "/api/probe-write",
                        json={"name": "a"},
                        headers={"Origin": "http://evil.example"},
                    ),
                    "post_cross_site": await c.post(
                        "/api/probe-write",
                        json={"name": "a"},
                        headers={"Sec-Fetch-Site": "cross-site"},
                    ),
                    "post_none_site": await c.post(
                        "/api/probe-write",
                        json={"name": "a"},
                        headers={"Sec-Fetch-Site": "none"},
                    ),
                    "post_valid_browser": await c.post(
                        "/api/probe-write",
                        json={"name": "browser"},
                        headers={
                            "Origin": "http://127.0.0.1:8765",
                            "Sec-Fetch-Site": "same-origin",
                        },
                    ),
                    "post_valid_cli": await c.post(
                        "/api/probe-write",
                        json={"name": "cli"},
                    ),
                    "options": await c.options(
                        "/api/probe-write",
                        headers={
                            "Origin": "http://evil.example",
                            "Access-Control-Request-Method": "POST",
                        },
                    ),
                }

        results = asyncio.run(_exercise())
    finally:
        database.close()

    assert results["get_cross"].status_code == HTTPStatus.FORBIDDEN
    assert results["get_same_site"].status_code == HTTPStatus.FORBIDDEN
    assert results["get_same_origin"].status_code == HTTPStatus.OK
    assert results["get_none"].status_code == HTTPStatus.OK
    assert results["post_no_ct"].status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    assert results["post_form"].status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    assert results["post_bad_origin"].status_code == HTTPStatus.FORBIDDEN
    assert results["post_cross_site"].status_code == HTTPStatus.FORBIDDEN
    assert results["post_none_site"].status_code == HTTPStatus.FORBIDDEN
    assert results["post_valid_browser"].status_code == HTTPStatus.OK
    assert results["post_valid_browser"].json() == {"ok": "browser"}
    assert results["post_valid_cli"].status_code == HTTPStatus.OK
    assert results["post_valid_cli"].json() == {"ok": "cli"}
    assert results["options"].status_code == HTTPStatus.METHOD_NOT_ALLOWED

    for response in results.values():
        _assert_security_headers(response.headers, is_api=True)
