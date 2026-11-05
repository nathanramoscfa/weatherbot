# tests/web/test_charts_route.py
"""Tests for ``GET /api/charts``, ``AssessmentRepository.level_points``, and ``wind_series``."""

import asyncio
from datetime import timedelta
from http import HTTPStatus
from typing import Final
from urllib.parse import quote

import httpx
import pytest
from cli_support import (
    MIAMI,
    NASSAU,
    add_landmark,
    county_statement,
    recorded_services,
    run,
    runtime,
)
from source_support import NOW
from sqlalchemy import update
from sqlalchemy.orm import Session

from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import AssessmentRepository
from weatherbot.services.persistence.tables import AssessmentRow
from weatherbot.web.app import WebState, create_app
from weatherbot.web.schemas import ChartsResponse

EXPECTED_MIAMI_POINTS: Final = 2
EXPECTED_WIND_THRESHOLDS: Final = 3


def _seed_two_cycles() -> None:
    later = NOW + timedelta(minutes=1)
    with recorded_services(overrides=county_statement()):
        assert add_landmark(MIAMI, "miami-dade", "--polygon", "forecast").exit_code == 0
        assert run(["locations", "evacuation", MIAMI, "on"]).exit_code == 0
        assert run(["check", "--once"]).exit_code == 0
        assert add_landmark(NASSAU, "nassau").exit_code == 0
        assert run(["locations", "evacuation", MIAMI, "off"], runtime(now=later)).exit_code == 0
        assert run(["check", "--once"], runtime(now=later)).exit_code == 0


def _open_web_state() -> tuple[WebState, Database]:
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    state = WebState(
        database=database,
        paths=paths,
        settings=load_settings(paths),
        setting_origins=setting_origins(paths),
        clock=lambda: NOW + timedelta(minutes=2),
        started_at=NOW - timedelta(minutes=10),
    )
    return state, database


def test_charts_route_returns_levels_and_deduplicated_wind_for_one_and_multiple_assessments() -> (
    None
):
    _seed_two_cycles()
    state, database = _open_web_state()
    try:
        app = create_app(state)

        async def _exercise() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                miami_res = await client.get(f"/api/charts?location={quote(MIAMI)}")
                nassau_res = await client.get(f"/api/charts?location={quote(NASSAU)}")
                limited_res = await client.get(f"/api/charts?location={quote(MIAMI)}&limit=1")
                return miami_res, nassau_res, limited_res

        miami_res, nassau_res, limited_res = asyncio.run(_exercise())
    finally:
        database.close()

    assert miami_res.status_code == HTTPStatus.OK
    miami_doc = ChartsResponse.model_validate(miami_res.json())
    assert miami_doc.location == MIAMI
    assert miami_doc.time_zone == "America/New_York"
    assert len(miami_doc.levels) == EXPECTED_MIAMI_POINTS
    assert [pt.level for pt in miami_doc.levels] == [1, 4]
    assert [pt.rule for pt in miami_doc.levels] == ["all_clear", "evacuation_order"]
    assert all(pt.as_of_local is not None for pt in miami_doc.levels)
    # Wind readings are deduplicated per (threshold_kt, synoptic_at).
    wind_keys = [(w.threshold_kt, w.synoptic_at) for w in miami_doc.wind]
    assert len(wind_keys) == len(set(wind_keys)) == EXPECTED_WIND_THRESHOLDS

    # A location with 1 assessment still answers 200 OK with 1 level point.
    assert nassau_res.status_code == HTTPStatus.OK
    nassau_doc = ChartsResponse.model_validate(nassau_res.json())
    assert nassau_doc.location == NASSAU
    assert len(nassau_doc.levels) == 1
    assert nassau_doc.levels[0].level == 1

    # limit=1 restricts the inspected assessments.
    assert limited_res.status_code == HTTPStatus.OK
    limited_doc = ChartsResponse.model_validate(limited_res.json())
    assert limited_doc.limit == 1
    assert len(limited_doc.levels) == 1
    assert limited_doc.levels[0].level == 1


def test_charts_route_rejects_unknown_location_and_out_of_range_limits_without_echoing_input() -> (
    None
):
    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade", "--polygon", "forecast").exit_code == 0
    state, database = _open_web_state()
    unknown_name = "UnknownPlaceProbe98765"
    try:
        app = create_app(state)

        async def _exercise() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                unknown = await client.get(f"/api/charts?location={quote(unknown_name)}")
                low = await client.get(f"/api/charts?location={quote(MIAMI)}&limit=0")
                high = await client.get(f"/api/charts?location={quote(MIAMI)}&limit=501")
                return unknown, low, high

        unknown_res, low_res, high_res = asyncio.run(_exercise())
    finally:
        database.close()

    assert unknown_res.status_code == HTTPStatus.NOT_FOUND
    assert unknown_res.json() == {"detail": "unknown location query parameter: location"}
    assert unknown_name not in unknown_res.text
    assert low_res.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert high_res.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_level_points_reads_columns_without_decoding_assessment_json() -> None:
    _seed_two_cycles()
    paths = AppPaths.resolve()
    with open_database(paths, now=lambda: NOW) as database:
        repo = AssessmentRepository(database.engine, now=lambda: NOW)
        with pytest.raises(ValueError, match="at least one"):
            repo.level_points(MIAMI, 0)
        with pytest.raises(ValueError, match="at least one"):
            repo.wind_series(MIAMI, 0)

        # Corrupt the JSON assessment payload in SQLite to prove level_points never decodes it.
        with Session(database.engine) as session:
            session.execute(update(AssessmentRow).values(assessment={"corrupted": True}))
            session.commit()

        points = repo.level_points(MIAMI, 10)
        assert len(points) == EXPECTED_MIAMI_POINTS
        assert [int(pt.level) for pt in points] == [1, 4]
