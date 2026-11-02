# tests/web/test_api_outlook.py
"""``GET /api/outlook`` and ``GET /api/outlook/{basin}/{horizon}``: NHC's maps, stored.

The image route serves the latest snapshot's PNG from the raw-response cache by the
SHA-256 its provenance records, with the API's ``no-store`` and security headers, and
answers 404 for an unknown basin or horizon, a path that is not one, no snapshot, and a
body that is not what was stored. The database is a per-module template holding the
recorded snapshot with every recorded answer, the outlook graphics' bodies among them.
"""

import hashlib
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from typing import Any

import httpx
import pytest
from ai_support import ai_web_state, copied_database, database_template, stored_recorded
from sqlalchemy import update

from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import Database, open_database, writing_session
from weatherbot.services.persistence.raw_cache import PNG_SIGNATURE
from weatherbot.services.persistence.repositories import SnapshotRepository
from weatherbot.services.persistence.tables import ResponseBodyRow
from weatherbot.web.app import create_app
from weatherbot.web.map_layers import SNAPSHOT_CACHE

pytestmark = pytest.mark.anyio

NOT_ROUTES = (
    "/api/outlook/xyz/7d0",
    "/api/outlook/atl/3d0",
    "/api/outlook/ATL/7d0",
    "/api/outlook/..%2F..%2Fweatherbot.sqlite3/7d0",
)


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return database_template(tmp_path_factory.mktemp("outlook"), stored_recorded)


@pytest.fixture
def database(template: Path) -> Iterator[Database]:
    SNAPSHOT_CACHE.clear()
    with copied_database(template) as opened:
        yield opened


@pytest.fixture
def empty() -> Iterator[Database]:
    SNAPSHOT_CACHE.clear()
    with open_database(AppPaths.resolve()) as opened:
        yield opened


async def _get(database: Database, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app(ai_web_state(database, None)))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
        return await client.get(path)


def _graphics(database: Database) -> list[Any]:
    repository = SnapshotRepository(database.engine)
    snapshot_id = repository.latest_id()
    assert snapshot_id is not None
    snapshot = repository.load(snapshot_id)
    assert snapshot is not None
    return list(snapshot.outlook_graphics)


async def test_each_stored_graphic_is_served_as_its_png(database: Database) -> None:
    graphics = _graphics(database)
    assert graphics

    for graphic in graphics:
        response = await _get(database, f"/api/outlook/{graphic.basin}/{graphic.horizon}")
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-type"] == "image/png"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.content.startswith(PNG_SIGNATURE)
        assert hashlib.sha256(response.content).hexdigest() == graphic.provenance.sha256


async def test_the_listing_names_each_stored_graphic(database: Database) -> None:
    graphics = _graphics(database)

    response = await _get(database, "/api/outlook")

    body = response.json()
    assert response.status_code == HTTPStatus.OK
    assert [
        (item["basin"], item["horizon"], item["width_px"], item["height_px"], item["sha256"])
        for item in body["graphics"]
    ] == [(g.basin, g.horizon, g.width_px, g.height_px, g.provenance.sha256) for g in graphics]
    assert body["notice"]


async def test_anything_but_a_stored_graphic_answers_404(database: Database) -> None:
    for path in NOT_ROUTES:
        response = await _get(database, path)
        assert response.status_code == HTTPStatus.NOT_FOUND, path
        assert response.headers["content-type"].startswith("application/json"), path


async def test_a_body_that_is_not_what_was_stored_answers_404(database: Database) -> None:
    graphic = next(item for item in _graphics(database) if item.basin == "atl")
    with writing_session(database.engine) as session:
        session.execute(
            update(ResponseBodyRow)
            .where(ResponseBodyRow.sha256 == graphic.provenance.sha256)
            .values(size=1)
        )

    response = await _get(database, f"/api/outlook/atl/{graphic.horizon}")

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_no_snapshot_means_no_graphic(empty: Database) -> None:
    listing = await _get(empty, "/api/outlook")
    image = await _get(empty, "/api/outlook/atl/7d0")

    assert (listing.json()["snapshot_id"], listing.json()["graphics"]) == (None, [])
    assert image.status_code == HTTPStatus.NOT_FOUND
