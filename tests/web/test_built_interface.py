# tests/web/test_built_interface.py
"""In-memory built interface serving, per-response CSP nonces, caching headers, and fallback."""

import asyncio
import hashlib
import re
import shutil
from http import HTTPStatus
from pathlib import Path

import httpx
from source_support import NOW

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.persistence.database import open_database
from weatherbot.web.app import WebState, create_app


def test_built_interface_serves_from_memory_with_fresh_nonce_and_cache_headers(
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)

    index_html = (
        "<!doctype html><html><head>"
        '<style nonce="__CSP_NONCE__">body{margin:0}</style>'
        '<script type="module" src="/assets/app-abc123.js"></script>'
        '</head><body><div id="root"></div></body></html>'
    )
    index_bytes = index_html.encode("utf-8")
    expected_sha = hashlib.sha256(index_bytes).hexdigest()[:12]
    (static_dir / "index.html").write_bytes(index_bytes)
    (assets_dir / "app-abc123.js").write_text("console.log('ready');\n", encoding="utf-8")
    (static_dir / "theme-init.js").write_text(
        "document.documentElement.dataset.theme='dark';\n", encoding="utf-8"
    )
    (static_dir / "licenses.json").write_text('[{"name": "react"}]\n', encoding="utf-8")

    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
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
        # Remove the directory after startup to prove all responses come from memory.
        shutil.rmtree(static_dir)

        async def _fetch() -> dict[str, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return {
                    "root1": await client.get("/"),
                    "root2": await client.get("/history"),
                    "asset": await client.get("/assets/app-abc123.js"),
                    "missing_asset": await client.get("/assets/missing.js"),
                    "theme": await client.get("/theme-init.js"),
                    "licenses": await client.get("/licenses.json"),
                    "health": await client.get("/api/health"),
                }

        res = asyncio.run(_fetch())
    finally:
        database.close()

    assert res["root1"].status_code == HTTPStatus.OK
    assert res["root2"].status_code == HTTPStatus.OK
    assert res["root1"].headers["cache-control"] == "no-store"
    assert res["root2"].headers["cache-control"] == "no-store"
    assert "__CSP_NONCE__" not in res["root1"].text
    assert "__CSP_NONCE__" not in res["root2"].text

    m1 = re.search(r'nonce="([^"]+)"', res["root1"].text)
    m2 = re.search(r'nonce="([^"]+)"', res["root2"].text)
    assert m1 is not None
    assert m2 is not None
    nonce1, nonce2 = m1.group(1), m2.group(1)
    assert nonce1 != nonce2
    assert f"style-src 'self' 'nonce-{nonce1}'" in res["root1"].headers["content-security-policy"]
    assert f"style-src 'self' 'nonce-{nonce2}'" in res["root2"].headers["content-security-policy"]

    assert res["asset"].status_code == HTTPStatus.OK
    assert res["asset"].headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "console.log('ready')" in res["asset"].text

    assert res["missing_asset"].status_code == HTTPStatus.NOT_FOUND

    assert res["theme"].status_code == HTTPStatus.OK
    assert res["theme"].headers["cache-control"] == "no-cache"
    assert res["licenses"].status_code == HTTPStatus.OK
    assert res["licenses"].headers["cache-control"] == "no-cache"

    health = res["health"].json()
    assert health["ui"] == {"present": True, "index_sha256": expected_sha}


def test_absent_index_html_serves_fallback_page_and_reports_ui_absent(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    try:
        state = WebState(
            database=database,
            paths=paths,
            settings=Settings(),
            clock=lambda: NOW,
            started_at=NOW,
            static_dir=empty_dir,
        )
        app = create_app(state)

        async def _fetch() -> tuple[httpx.Response, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return await client.get("/"), await client.get("/api/health")

        root_res, health_res = asyncio.run(_fetch())
    finally:
        database.close()

    assert root_res.status_code == HTTPStatus.OK
    assert "CONTRIBUTING.md" in root_res.text
    assert "/api/health" in root_res.text
    assert health_res.json()["ui"] == {"present": False, "index_sha256": None}
