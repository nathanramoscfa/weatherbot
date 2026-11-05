# tests/web/test_wind_probability_route.py
"""Tests for live and replay ``/wind-probabilities`` routes."""

import asyncio
from datetime import timedelta
from http import HTTPStatus
from uuid import uuid4

import httpx
from cli_support import CORPUS, MIAMI, add_landmark, recorded_services, run
from source_support import NOW

from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.persistence.database import open_database
from weatherbot.services.replay import ReplayCorpus
from weatherbot.web.app import WebState, create_app
from weatherbot.web.map_layers import (
    SNAPSHOT_CACHE,
    WIND_PROBABILITY_SIMPLIFY_NOTE,
)
from weatherbot.web.schemas import WindProbabilityResponse

MAX_WIND_PROBABILITY_BYTES = 400_000


def test_live_and_replay_wind_probability_routes_size_budget_order_and_errors() -> None:
    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0
        assert run(["check", "--once"]).exit_code == 0

    SNAPSHOT_CACHE.clear()
    paths = AppPaths.resolve()
    corpus = ReplayCorpus.open(CORPUS)
    database = open_database(paths, now=lambda: NOW)
    unknown_id = uuid4()
    try:
        state = WebState(
            database=database,
            paths=paths,
            settings=load_settings(paths),
            setting_origins=setting_origins(paths),
            clock=lambda: NOW,
            started_at=NOW - timedelta(minutes=10),
            corpus=corpus,
        )
        app = create_app(state)

        async def _exercise() -> dict[str, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return {
                    "live34": await client.get("/api/map/wind-probabilities?threshold_kt=34"),
                    "live50": await client.get("/api/map/wind-probabilities?threshold_kt=50"),
                    "live64": await client.get("/api/map/wind-probabilities?threshold_kt=64"),
                    "bad_kt": await client.get("/api/map/wind-probabilities?threshold_kt=45"),
                    "unknown_snap": await client.get(
                        f"/api/map/wind-probabilities?threshold_kt=34&snapshot_id={unknown_id}"
                    ),
                    "replay34": await client.get(
                        "/api/replay/AL112017/036/wind-probabilities?threshold_kt=34"
                    ),
                    "replay_unknown": await client.get(
                        "/api/replay/AL992099/001/wind-probabilities?threshold_kt=34"
                    ),
                }

        res = asyncio.run(_exercise())
    finally:
        database.close()

    assert res["live34"].status_code == HTTPStatus.OK
    assert res["live50"].status_code == HTTPStatus.OK
    assert res["live64"].status_code == HTTPStatus.OK
    assert res["bad_kt"].status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    assert res["unknown_snap"].status_code == HTTPStatus.NOT_FOUND
    assert res["unknown_snap"].json() == {"detail": "unknown snapshot parameter: snapshot_id"}
    assert str(unknown_id) not in res["unknown_snap"].text

    assert res["replay_unknown"].status_code == HTTPStatus.NOT_FOUND
    assert res["replay_unknown"].json() == {"detail": "unknown replay storm parameter: atcf_id"}
    assert "AL992099" not in res["replay_unknown"].text

    # Recorded 34-kt answer stays under 400 KB after 0.03-deg topology-preserving simplification.
    assert len(res["live34"].content) < MAX_WIND_PROBABILITY_BYTES

    parsed34 = WindProbabilityResponse.model_validate_json(res["live34"].text)
    assert parsed34.threshold_kt == 34  # noqa: PLR2004
    assert parsed34.coverage is None
    assert len(parsed34.bands.features) > 0

    lowers34 = [
        int(f.properties["lower_pct"])  # type: ignore[arg-type]
        for f in parsed34.bands.features
    ]
    assert lowers34 == sorted(lowers34)
    for feat in parsed34.bands.features:
        assert WIND_PROBABILITY_SIMPLIFY_NOTE in str(feat.properties.get("geometry_note", ""))

    parsed50 = WindProbabilityResponse.model_validate_json(res["live50"].text)
    assert parsed50.threshold_kt == 50  # noqa: PLR2004
    assert len(parsed50.bands.features) > 0

    parsed64 = WindProbabilityResponse.model_validate_json(res["live64"].text)
    assert parsed64.threshold_kt == 64  # noqa: PLR2004
    assert len(parsed64.bands.features) > 0

    parsed_replay = WindProbabilityResponse.model_validate_json(res["replay34"].text)
    assert parsed_replay.threshold_kt == 34  # noqa: PLR2004
    assert len(parsed_replay.bands.features) > 0
    assert parsed_replay.coverage is not None
    assert parsed_replay.coverage.geometry.type in {"Polygon", "MultiPolygon"}
