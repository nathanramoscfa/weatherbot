# tests/web/test_api_privacy.py
"""Privacy tests holding coordinates to ``/api/locations`` and the map's location layers."""

import asyncio
import json
import logging
import re
from datetime import timedelta
from http import HTTPStatus
from typing import cast

import httpx
import pytest
from cli_support import CORPUS, history, recorded_services, run
from source_support import NOW

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.persistence.database import open_database
from weatherbot.services.replay import ReplayCorpus
from weatherbot.web.app import WebState, create_app
from weatherbot.web.map_layers import SNAPSHOT_CACHE

DECIMAL_COORDINATE = re.compile(r"(?<![\d.])\d{1,3}\.\d{3,}(?![\d.])")
NAME = "Synthetic place"


@pytest.fixture
def coordinates() -> tuple[str, str]:
    """A synthetic latitude and longitude generated at run time, far from every landmark."""
    return synthetic_coordinates(load_landmarks(), (), seed=6)


def _coordinate_renderings(coordinates: tuple[str, str]) -> set[str]:
    return {
        rendering
        for value in coordinates
        for rendering in (
            value,
            str(float(value)),
            f"{float(value):.4f}",
            value.lstrip("-"),
        )
    }


def _leaks_coordinate(text: str, coordinates: tuple[str, str]) -> bool:
    renderings = _coordinate_renderings(coordinates)
    return any(value in text for value in renderings)


def _leaks_coordinate_or_decimal(text: str, coordinates: tuple[str, str]) -> bool:
    return _leaks_coordinate(text, coordinates) or bool(DECIMAL_COORDINATE.search(text))


def _distance_renderings(value: float) -> set[str]:
    written = {repr(value), f"{value:.1f}", f"{value:.2f}"}
    whole = f"{value:.0f}"
    return written | ({whole} if len(whole) >= 3 else set())  # noqa: PLR2004


def test_only_locations_and_map_location_layers_carry_coordinates_and_logs_stay_clean(
    coordinates: tuple[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    lat, lon = coordinates
    with recorded_services():
        added = run(
            [
                "locations",
                "add",
                NAME,
                "--lat",
                lat,
                "--lon",
                lon,
                "--polygon",
                "forecast",
            ]
        )
        checked = run(["check", "--once"])

    assert added.exit_code == 0, added.stderr
    assert checked.exit_code == 0, checked.stderr

    SNAPSHOT_CACHE.clear()
    paths = AppPaths.resolve()
    corpus = ReplayCorpus.open(CORPUS)
    database = open_database(paths, now=lambda: NOW)
    caplog.clear()
    caplog.set_level(logging.DEBUG)
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
        routes = (
            "/api/health",
            "/api/locations",
            "/api/assessments",
            "/api/storms",
            "/api/alerts",
            "/api/timeline",
            "/api/notifications",
            "/api/settings",
            "/api/disclaimer",
            "/api/map",
            "/api/replay",
            "/api/replay/AL112017/026A",
        )

        async def _fetch_all() -> dict[str, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return {url: await client.get(url) for url in routes}

        responses = asyncio.run(_fetch_all())
    finally:
        database.close()

    for url, res in responses.items():
        assert res.status_code == HTTPStatus.OK, (url, res.text)

    # /api/locations carries the stored location's coordinates.
    locations_text = responses["/api/locations"].text
    assert str(float(lat)) in locations_text
    assert str(float(lon)) in locations_text

    # /api/map and /api/replay/{atcf_id}/{advisory} carry the location's coordinates
    # ONLY inside `locations` and `location_polygons`.
    for map_url in ("/api/map", "/api/replay/AL112017/026A"):
        map_payload = cast("dict[str, object]", responses[map_url].json())
        assert str(float(lat)) in json.dumps(map_payload["locations"])
        stripped = {
            k: v for k, v in map_payload.items() if k not in {"locations", "location_polygons"}
        }
        stripped_text = json.dumps(stripped)
        assert not _leaks_coordinate(stripped_text, coordinates), map_url

    # Every other read route holds no coordinate rendering and no 3+-decimal coordinate.
    non_coordinate_routes = (
        "/api/health",
        "/api/assessments",
        "/api/storms",
        "/api/alerts",
        "/api/timeline",
        "/api/notifications",
        "/api/settings",
        "/api/disclaimer",
        "/api/replay",
    )
    for url in non_coordinate_routes:
        text = responses[url].text
        assert not _leaks_coordinate(text, coordinates), (url, text)
        # DISCLAIMER.md includes the static NOAA Weather Radio band "162.400-162.550 MHz".
        sanitized = text.replace("162.400-162.550 MHz", "")
        assert not _leaks_coordinate_or_decimal(sanitized, coordinates), (url, text)

    # No log record above DEBUG holds a coordinate, a 3+-decimal number, a distance, or a bearing.
    assessments = [stored.assessment for stored in history(NAME)]
    assert assessments
    measured = [
        value
        for assessment in assessments
        for threat in assessment.threats
        for value in (
            threat.distance_km,
            threat.bearing_deg,
            threat.closest_approach_km,
            threat.lead_h,
        )
        if value is not None
    ]
    measured += [
        value
        for assessment in assessments
        for value in (
            *(p.distance_km for p in assessment.official),
            *(e.distance_km for e in assessment.evidence),
        )
        if value is not None
    ]
    assert measured
    distance_strings = set[str]().union(*(_distance_renderings(val) for val in measured))
    distance_patterns = [
        re.compile(rf"(?<![\d.]){re.escape(val)}(?![\d])") for val in distance_strings
    ]

    above_debug = [r.getMessage() for r in caplog.records if r.levelno > logging.DEBUG]
    assert not [msg for msg in above_debug if _leaks_coordinate_or_decimal(msg, coordinates)]
    assert not [
        (msg, pat.pattern) for msg in above_debug for pat in distance_patterns if pat.search(msg)
    ]
