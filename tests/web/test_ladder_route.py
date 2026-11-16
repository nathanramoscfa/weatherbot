# tests/web/test_ladder_route.py
"""Tests for ``GET /api/ladder``."""

import asyncio
import inspect
import re
from http import HTTPStatus
from pathlib import Path

import httpx
from source_support import NOW

from check_personal_data import Allowlist, Scanner, load_landmarks, synthetic_coordinates
from weatherbot.engine import RULES
from weatherbot.engine.official import LADDER_CODES, LADDER_EVENTS
from weatherbot.models import AlertLevel
from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.database import open_database
from weatherbot.web.app import WebState, create_app
from weatherbot.web.routes.ladder import get_ladder
from weatherbot.web.schemas import LadderResponse

DECIMAL_COORDINATE = re.compile(r"(?<![\d.])\d{1,3}\.\d{3,}(?![\d.])")


def test_get_ladder_route_is_synchronous() -> None:
    assert not inspect.iscoroutinefunction(get_ladder)


def test_get_ladder_serves_startup_thresholds_even_after_settings_file_changes_and_passes_privacy(
    tmp_path: Path,
) -> None:
    paths = AppPaths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.settings_path.write_text(
        "[engine]\n"
        "coastal_reach_km = 30.0\n"
        "segment_end_tolerance_km = 6.0\n"
        "cone_horizon_h = 96\n"
        "hurricane_wind_floor_pct = 20\n"
        "tropical_storm_wind_floor_pct = 10\n"
        "development_chance_floor_pct = 10\n",
        encoding="utf-8",
    )

    startup_settings = load_settings(paths, environ={})
    startup_origins = setting_origins(paths, environ={})

    with open_database(paths, now=lambda: NOW) as database:
        state = WebState(
            database=database,
            paths=paths,
            settings=startup_settings,
            setting_origins=startup_origins,
            clock=lambda: NOW,
            started_at=NOW,
            environ={},
        )
        app = create_app(state)

        # Modify [engine] on disk after startup: LiveSettings does not reload [engine],
        # so /api/ladder must still report the startup thresholds the engine is running.
        paths.settings_path.write_text(
            "[engine]\n"
            "coastal_reach_km = 75.0\n"
            "segment_end_tolerance_km = 15.0\n"
            "cone_horizon_h = 48\n"
            "hurricane_wind_floor_pct = 50\n"
            "tropical_storm_wind_floor_pct = 30\n"
            "development_chance_floor_pct = 40\n",
            encoding="utf-8",
        )

        async def _fetch() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://127.0.0.1:8765",
            ) as client:
                return await client.get("/api/ladder")

        response = asyncio.run(_fetch())

    assert response.status_code == HTTPStatus.OK
    assert response.headers.get("cache-control") == "no-store"

    parsed = LadderResponse.model_validate_json(response.text)
    assert parsed.notice == NOTICE
    assert [lvl.number for lvl in parsed.levels] == [int(level) for level in AlertLevel]
    assert [lvl.label for lvl in parsed.levels] == [level.label for level in AlertLevel]
    assert [rule.id for rule in parsed.rules] == [rule.id for rule in RULES]
    assert [ev.event for ev in parsed.events] == list(LADDER_EVENTS)
    assert [c.code for c in parsed.codes] == list(LADDER_CODES)

    by_name = {th.name: th.value for th in parsed.thresholds}
    assert by_name == {
        "coastal_reach_km": 30.0,
        "segment_end_tolerance_km": 6.0,
        "cone_horizon_h": 96,
        "hurricane_wind_floor_pct": 20,
        "tropical_storm_wind_floor_pct": 10,
        "development_chance_floor_pct": 10,
    }
    assert parsed.ruleset == startup_settings.engine.thresholds().fingerprint()

    # Privacy scan: no synthetic or landmark coordinates or 3+-decimal numbers.
    landmarks = load_landmarks()
    lat, lon = synthetic_coordinates(landmarks, (), seed=9)
    assert lat not in response.text
    assert lon not in response.text
    assert not DECIMAL_COORDINATE.search(response.text)

    payload_file = tmp_path / "ladder-response.json"
    payload_file.write_text(response.text, encoding="utf-8")
    scanner = Scanner(
        root=tmp_path,
        allowlist=Allowlist.from_landmarks(landmarks),
        denylist=None,
    )
    assert scanner.scan(["ladder-response.json"]) == []
