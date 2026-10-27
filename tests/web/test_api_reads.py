# tests/web/test_api_reads.py
"""Offline tests for the Step 2 read routes, OpenAPI schema conformance, and bounds."""

import asyncio
import json
import os
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from cli_support import (
    CORPUS,
    MIAMI,
    NASSAU,
    add_landmark,
    county_statement,
    recorded_services,
    run,
    runtime,
)
from fixture_support import REPOSITORY_ROOT
from jsonschema import Draft202012Validator
from pydantic import BaseModel
from source_support import NOW

from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.notifications import NotificationService
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.replay import ReplayCorpus
from weatherbot.web.app import WebState, create_app
from weatherbot.web.map_layers import SNAPSHOT_CACHE
from weatherbot.web.schemas import (
    AlertsResponse,
    AssessmentsResponse,
    DisclaimerResponse,
    HealthResponse,
    LocationsResponse,
    MapResponse,
    NotificationsResponse,
    ReplayStormsResponse,
    SettingsResponse,
    StormsResponse,
    TimelineResponse,
)

OPENAPI_PATH = REPOSITORY_ROOT / "docs" / "api" / "openapi.json"

READ_ROUTE_MODELS: tuple[tuple[str, str, type[BaseModel]], ...] = (
    ("/api/health", "/api/health", HealthResponse),
    ("/api/locations", "/api/locations", LocationsResponse),
    ("/api/assessments", "/api/assessments", AssessmentsResponse),
    ("/api/storms", "/api/storms", StormsResponse),
    ("/api/alerts", "/api/alerts", AlertsResponse),
    ("/api/timeline", "/api/timeline", TimelineResponse),
    ("/api/notifications", "/api/notifications", NotificationsResponse),
    ("/api/settings", "/api/settings", SettingsResponse),
    ("/api/disclaimer", "/api/disclaimer", DisclaimerResponse),
    ("/api/map", "/api/map", MapResponse),
)


def _load_openapi() -> dict[str, Any]:
    doc: object = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return cast("dict[str, Any]", doc)


def _validate_against_openapi(
    openapi_doc: dict[str, Any], path_template: str, payload: dict[str, object]
) -> None:
    route_schema = openapi_doc["paths"][path_template]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    full_schema = {
        **route_schema,
        "components": openapi_doc["components"],
    }
    Draft202012Validator(full_schema).validate(payload)  # pyright: ignore[reportUnknownMemberType]


def _make_state(
    *,
    corpus: ReplayCorpus | None = None,
    started_at_offset: timedelta = timedelta(minutes=-10),
) -> tuple[WebState, Database]:
    SNAPSHOT_CACHE.clear()
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    settings = load_settings(paths)
    origins = setting_origins(paths)
    state = WebState(
        database=database,
        paths=paths,
        settings=settings,
        setting_origins=origins,
        clock=lambda: NOW,
        started_at=NOW + started_at_offset,
        static_dir=None,
        corpus=corpus,
    )
    return state, database


def test_every_read_route_answers_200_on_empty_database_and_matches_openapi() -> None:
    openapi_doc = _load_openapi()
    state, database = _make_state()
    try:
        app = create_app(state)

        async def _fetch_all() -> dict[str, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return {url: await client.get(url) for url, _tmpl, _model in READ_ROUTE_MODELS}

        responses = asyncio.run(_fetch_all())
    finally:
        database.close()

    for url, path_template, model_cls in READ_ROUTE_MODELS:
        res = responses[url]
        assert res.status_code == HTTPStatus.OK, (url, res.text)
        assert res.headers["cache-control"] == "no-store"
        body = res.json()
        _validate_against_openapi(openapi_doc, path_template, body)
        model_cls.model_validate_json(res.text)

    assert responses["/api/locations"].json()["locations"] == []
    assert responses["/api/assessments"].json()["snapshot"] is None
    assert responses["/api/assessments"].json()["locations"] == []
    assert responses["/api/storms"].json()["snapshot"] is None
    assert responses["/api/storms"].json()["storms"] == []
    assert responses["/api/alerts"].json()["snapshot"] is None
    assert responses["/api/alerts"].json()["locations"] == []
    assert responses["/api/timeline"].json()["entries"] == []
    assert responses["/api/notifications"].json()["notifications"] == []
    assert responses["/api/map"].json()["snapshot_id"] is None
    assert responses["/api/map"].json()["storms"] == []


def _assert_populated_route_details(responses: dict[str, httpx.Response]) -> None:
    locations_body = LocationsResponse.model_validate_json(responses["/api/locations"].text)
    assert [loc.name for loc in locations_body.locations] == [MIAMI, NASSAU]
    miami_loc = locations_body.locations[0]
    assert miami_loc.has_polygon is True
    assert miami_loc.polygon is not None
    assert miami_loc.polygon.crs.name == "EPSG:4326"
    assert miami_loc.evacuation_order_in_effect is True

    assessments_body = AssessmentsResponse.model_validate_json(responses["/api/assessments"].text)
    assert assessments_body.snapshot is not None
    miami_assessed = next(loc for loc in assessments_body.locations if loc.name == MIAMI)
    assert miami_assessed.assessment is not None
    assert miami_assessed.assessment.toggle_changed is True
    assert miami_assessed.assessment.toggle_note is not None
    assert any(p.is_county_context for p in miami_assessed.assessment.official)

    settings_body = SettingsResponse.model_validate_json(responses["/api/settings"].text)
    assert settings_body.settings_file_exists is True
    assert settings_body.file_modified_since_start is True

    filtered_timeline = TimelineResponse.model_validate_json(
        responses["/api/timeline?location=miami"].text
    )
    assert filtered_timeline.location == MIAMI
    assert filtered_timeline.limit == 10  # noqa: PLR2004
    assert {entry.kind for entry in filtered_timeline.entries} == {
        "assessment",
        "notification",
    }
    assert all(entry.location == MIAMI for entry in filtered_timeline.entries)


def test_every_read_route_answers_200_with_populated_data_and_validates_against_openapi(
    tmp_path: Path,
) -> None:
    openapi_doc = _load_openapi()
    with recorded_services(overrides=county_statement()):
        assert add_landmark(MIAMI, "miami-dade", "--polygon", "forecast").exit_code == 0
        assert add_landmark(NASSAU, "nassau").exit_code == 0
        assert run(["check", "--once"]).exit_code == 0
        # Flip evacuation toggle after the assessment was stored so toggle_changed is True.
        assert (
            run(
                ["locations", "evacuation", MIAMI, "on"],
                runtime(now=NOW + timedelta(minutes=1)),
            ).exit_code
            == 0
        )

    paths = AppPaths.resolve()
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.settings_path.write_text('[logging]\nlevel = "INFO"\n', encoding="utf-8")
    future_mtime = (NOW + timedelta(minutes=5)).timestamp()
    os.utime(paths.settings_path, (future_mtime, future_mtime))

    corpus = ReplayCorpus.open(CORPUS)
    state, database = _make_state(corpus=corpus)
    try:
        # Also record a test notification so /api/notifications and /api/timeline include it.
        notif_service = NotificationService(
            database.engine, settings=state.settings, now=lambda: NOW
        )
        asyncio.run(
            notif_service.send(
                kind="test",
                title="Weatherbot test notification",
                body=("Test notification line.",),
            )
        )
        app = create_app(state)
        routes_to_check: tuple[tuple[str, str, type[BaseModel]], ...] = (
            *READ_ROUTE_MODELS,
            ("/api/replay", "/api/replay", ReplayStormsResponse),
            (
                "/api/replay/AL112017/026A",
                "/api/replay/{atcf_id}/{advisory}",
                MapResponse,
            ),
        )

        async def _fetch_all() -> dict[str, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                out = {url: await client.get(url) for url, _tmpl, _model in routes_to_check}
                out["/api/timeline?location=miami"] = await client.get(
                    "/api/timeline", params={"location": MIAMI, "limit": 10}
                )
                return out

        responses = asyncio.run(_fetch_all())
    finally:
        database.close()

    for url, path_template, model_cls in routes_to_check:
        res = responses[url]
        assert res.status_code == HTTPStatus.OK, (url, res.text)
        body = res.json()
        _validate_against_openapi(openapi_doc, path_template, body)
        model_cls.model_validate_json(res.text)

    _assert_populated_route_details(responses)
    assert tmp_path.exists()


@pytest.mark.parametrize(
    ("url", "params", "expected_status", "secret_token"),
    [
        (
            "/api/timeline",
            {"location": "Secret-Unlisted-Place-99"},
            HTTPStatus.NOT_FOUND,
            "Secret-Unlisted-Place-99",
        ),
        (
            "/api/timeline",
            {"limit": "0"},
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "input",
        ),
        (
            "/api/timeline",
            {"limit": "501"},
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "input",
        ),
        (
            "/api/notifications",
            {"limit": "0"},
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "input",
        ),
        (
            "/api/notifications",
            {"limit": "501"},
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "input",
        ),
    ],
)
def test_unknown_location_and_out_of_bounds_limits_never_echo_input(
    url: str,
    params: dict[str, str],
    expected_status: HTTPStatus,
    secret_token: str,
) -> None:
    state, database = _make_state()
    try:
        app = create_app(state)

        async def _call() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return await client.get(url, params=params)

        response = asyncio.run(_call())
    finally:
        database.close()

    assert response.status_code == expected_status
    assert secret_token not in response.text
