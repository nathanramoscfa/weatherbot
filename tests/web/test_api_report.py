# tests/web/test_api_report.py
"""Tests for ``GET /api/report``: headers, CSP, attachment, briefing opt-in, 404/409, privacy."""

import asyncio
import html
import re
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from urllib.parse import quote

import httpx
from ai_support import FIXTURES, MODEL, stream_blocks
from scenarios import miami_dade, rebuilt, recorded_maps

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.engine import assess
from weatherbot.models import LatLon, Location, Thresholds
from weatherbot.services.ai.context import briefing_context
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.outputs import NewOutput, OutputRepository
from weatherbot.services.ai.prompts import prompt_version
from weatherbot.services.ai.schemas import Briefing
from weatherbot.services.config import AppPaths, load_settings
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    LocationRepository,
    SnapshotRepository,
)
from weatherbot.services.report import AI_LABEL_NOTE, REPORT_HEADER_CSP
from weatherbot.web.app import WebState, create_app

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
DECIMAL_COORDINATE = re.compile(r"(?<![\d.])\d{1,3}\.\d{3,}(?![\d.])")


def _make_paths(root: Path) -> AppPaths:
    return AppPaths(config_dir=root / "config", data_dir=root / "data")


def _store_briefing(db_file: Path, location: str, assessment_id: int, sources: list[object]) -> str:
    raw_sse = (FIXTURES / "eval-briefing-recorded-miami-dade.sse").read_text(encoding="utf-8")
    text_blocks = [b for b in stream_blocks(raw_sse) if b.get("type") == "text"]
    briefing_obj = Briefing.model_validate_json(str(text_blocks[0]["text"]))
    ai_eng = ai_engine(db_file)
    try:
        OutputRepository(ai_eng, now=lambda: NOW).add(
            NewOutput(
                kind="briefing",
                model=MODEL,
                prompt_version=prompt_version(Thresholds()),
                status="ok",
                content={
                    "briefing": briefing_obj.model_dump(mode="json"),
                    "sources": sources,
                },
                location_name=location,
                assessment_id=assessment_id,
            )
        )
    finally:
        ai_eng.dispose()
    return briefing_obj.situation


def test_get_report_409_when_empty_404_without_echoing_cross_site_403_and_attachment_headers(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path / "web-report")
    with open_database(paths, now=lambda: NOW) as database:
        state = WebState(
            database=database,
            paths=paths,
            settings=load_settings(paths),
            clock=lambda: NOW,
            started_at=NOW - timedelta(minutes=5),
        )
        app = create_app(state)

        async def _check_empty() -> tuple[httpx.Response, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                no_loc = await client.get("/api/report")
                unknown = await client.get("/api/report?location=SecretUnknownPlace999")
                return no_loc, unknown

        no_loc_resp, unknown_resp = asyncio.run(_check_empty())
        assert no_loc_resp.status_code == HTTPStatus.CONFLICT
        assert unknown_resp.status_code == HTTPStatus.NOT_FOUND
        assert "SecretUnknownPlace999" not in unknown_resp.text

        # Store a location without an assessment yet -> still 409
        loc = rebuilt(miami_dade(), name="Harbor")
        LocationRepository(database.engine, now=lambda: NOW).add(loc)

        async def _check_no_assessment() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return await client.get("/api/report?location=Harbor")

        no_assess_resp = asyncio.run(_check_no_assessment())
        assert no_assess_resp.status_code == HTTPStatus.CONFLICT

        # Store snapshot, assessment, and a recorded AI briefing
        snap = rebuilt(recorded_maps(), alerts={"Harbor": ()})
        SnapshotRepository(database.engine).save(snap)
        assessment = assess(snap, loc, Thresholds())
        stored = AssessmentRepository(database.engine, now=lambda: NOW).save(assessment, ())
        ctx = briefing_context(stored.assessment, stored.changes, None)
        expected_situation = _store_briefing(
            paths.database_path,
            "Harbor",
            stored.id,
            [src.model_dump(mode="json") for src in ctx.sources],
        )

        async def _exercise_populated() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                default_r = await client.get(
                    "/api/report?location=Harbor",
                    headers={"Sec-Fetch-Site": "same-origin"},
                )
                brief_r = await client.get(
                    "/api/report?location=Harbor&briefing=true",
                    headers={"Sec-Fetch-Site": "same-origin"},
                )
                cross_site_r = await client.get(
                    "/api/report?location=Harbor",
                    headers={"Sec-Fetch-Site": "cross-site"},
                )
                return default_r, brief_r, cross_site_r

        default_resp, brief_resp, cross_resp = asyncio.run(_exercise_populated())

    assert cross_resp.status_code == HTTPStatus.FORBIDDEN

    for resp in (default_resp, brief_resp):
        assert resp.status_code == HTTPStatus.OK
        assert resp.headers["content-type"].startswith("text/html")
        assert (
            resp.headers["content-disposition"]
            == 'attachment; filename="weatherbot-report-20261018T1200Z.html"'
        )
        assert resp.headers["content-security-policy"] == REPORT_HEADER_CSP
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert NOTICE in resp.text

    assert "report-ai-briefing" not in default_resp.text
    assert "report-ai-briefing" in brief_resp.text
    assert AI_LABEL_NOTE in brief_resp.text
    assert html.escape(expected_situation, quote=True) in brief_resp.text


def test_get_report_passes_api_privacy_coordinate_and_distance_scan(tmp_path: Path) -> None:
    lat_str, lon_str = synthetic_coordinates(load_landmarks(), (), seed=19)
    lat, lon = float(lat_str), float(lon_str)
    loc = Location(
        name="Synthetic Coastal Spot",
        point=LatLon(latitude=lat, longitude=lon),
        display_name="999 Private Ocean Lane, Synthetic County",
    )
    snap = rebuilt(recorded_maps(), alerts={"Synthetic Coastal Spot": ()})
    assessment = assess(snap, loc, Thresholds())

    paths = _make_paths(tmp_path / "web-report-privacy")
    with open_database(paths, now=lambda: NOW) as database:
        LocationRepository(database.engine, now=lambda: NOW).add(loc)
        SnapshotRepository(database.engine).save(snap)
        AssessmentRepository(database.engine, now=lambda: NOW).save(assessment, ())

        state = WebState(
            database=database,
            paths=paths,
            settings=load_settings(paths),
            clock=lambda: NOW,
            started_at=NOW,
        )
        app = create_app(state)

        async def _get() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return await client.get(f"/api/report?location={quote('Synthetic Coastal Spot')}")

        resp = asyncio.run(_get())

    assert resp.status_code == HTTPStatus.OK
    body = resp.text
    assert "999 Private Ocean Lane" not in body
    for coord in (
        lat_str,
        lon_str,
        f"{lat:.2f}",
        f"{abs(lon):.2f}",
        f"{lat:.4f}",
        f"{abs(lon):.4f}",
    ):
        assert coord not in body
    cleaned = body.replace("0.375rem", "")
    assert not DECIMAL_COORDINATE.search(cleaned)
    for threat in assessment.threats:
        if threat.distance_km is not None:
            assert f"{threat.distance_km:.1f}" not in body
