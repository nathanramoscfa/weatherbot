# tests/web/test_api_privacy.py
"""Privacy tests holding coordinates to ``/api/locations`` and the map's location layers."""

import asyncio
import json
import logging
import re
from datetime import timedelta
from http import HTTPStatus
from typing import cast
from urllib.parse import quote

import httpx
import pytest
import respx
from cli_support import CORPUS, history, quiet_fetcher, recorded_services, run
from source_support import NOW

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.logs import configure_logging
from weatherbot.services.network import Network
from weatherbot.services.persistence.database import open_database
from weatherbot.services.replay import ReplayCorpus
from weatherbot.sources.nominatim import search_url
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


def test_only_locations_and_map_location_layers_carry_coordinates_and_logs_stay_clean(  # noqa: PLR0915
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
        charts_url = f"/api/charts?location={quote(NAME)}"
        report_url = f"/api/report?location={quote(NAME)}"
        replay_timeline_url = f"/api/replay/AL112017/timeline?location={quote(NAME)}"
        replay_assessment_url = f"/api/replay/AL112017/026A/assessment?location={quote(NAME)}"
        routes = (
            "/api/health",
            "/api/locations",
            "/api/assessments",
            charts_url,
            "/api/report",
            report_url,
            "/api/storms",
            "/api/alerts",
            "/api/timeline",
            "/api/notifications",
            "/api/notifications/channels",
            "/api/settings",
            "/api/retention",
            "/api/disclaimer",
            "/api/map",
            "/api/map/advisories",
            "/api/map/depth",
            "/api/map/wind-probabilities?threshold_kt=34",
            "/api/replay",
            replay_timeline_url,
            "/api/replay/AL112017/026A",
            replay_assessment_url,
            "/api/replay/AL112017/026A/wind-probabilities?threshold_kt=34",
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

    # The new map depth, advisories, and wind-probability routes carry no location coordinates.
    for map_sub_url in (
        "/api/map/advisories",
        "/api/map/depth",
        "/api/map/wind-probabilities?threshold_kt=34",
        "/api/replay/AL112017/026A/wind-probabilities?threshold_kt=34",
    ):
        assert not _leaks_coordinate(responses[map_sub_url].text, coordinates), map_sub_url

    # Every other read route holds no coordinate rendering and no 3+-decimal coordinate.
    non_coordinate_routes = (
        "/api/health",
        "/api/assessments",
        charts_url,
        "/api/report",
        report_url,
        "/api/storms",
        "/api/alerts",
        "/api/timeline",
        "/api/notifications",
        "/api/notifications/channels",
        "/api/settings",
        "/api/retention",
        "/api/disclaimer",
        "/api/map/advisories",
        "/api/replay",
        replay_timeline_url,
        replay_assessment_url,
    )
    for url in non_coordinate_routes:
        text = responses[url].text
        assert not _leaks_coordinate(text, coordinates), (url, text)
        # DISCLAIMER.md includes the static NOAA Weather Radio band "162.400-162.550 MHz",
        # and the HTML report stylesheet includes "0.375rem".
        sanitized = text.replace("162.400-162.550 MHz", "").replace("0.375rem", "")
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
    assert not [pat.pattern for pat in distance_patterns if pat.search(responses[charts_url].text)]
    assert not [pat.pattern for pat in distance_patterns if pat.search(responses[report_url].text)]


def test_place_search_route_never_logs_or_echoes_search_query_in_errors_or_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_query = "SecretTypedPlaceQuery54321"
    paths = AppPaths.resolve()
    configure_logging("INFO")
    caplog.clear()
    caplog.set_level(logging.INFO, logger="weatherbot")
    with (
        open_database(paths, now=lambda: NOW) as database,
        respx.mock(assert_all_called=False) as router,
    ):
        router.get(search_url(private_query)).mock(return_value=httpx.Response(503))
        state = WebState(
            database=database,
            paths=paths,
            settings=load_settings(paths),
            clock=lambda: NOW,
            started_at=NOW,
            network=Network(make_fetcher=quiet_fetcher),
        )
        app = create_app(state)

        async def _exercise() -> tuple[httpx.Response, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                headers = {"Origin": "http://127.0.0.1:8765"}
                bad = await client.post(
                    "/api/locations/search",
                    json={"query": "ab\n"},
                    headers=headers,
                )
                failed = await client.post(
                    "/api/locations/search",
                    json={"query": private_query},
                    headers=headers,
                )
                return failed, bad

        failed_resp, bad_resp = asyncio.run(_exercise())

    assert failed_resp.status_code == HTTPStatus.BAD_GATEWAY
    assert bad_resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert private_query not in failed_resp.text
    for record in caplog.records:
        assert private_query not in record.getMessage()
