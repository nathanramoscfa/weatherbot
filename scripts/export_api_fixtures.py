# scripts/export_api_fixtures.py
"""Export deterministic read-API JSON fixtures for ``frontend/src/test/fixtures/``.

Builds a temporary SQLite database over the recorded answers with both public landmarks
(Miami-Dade County Hall and Parliament Square, Nassau) and the committed replay corpus,
calls every read route (including ``/api/replay`` and ``/api/replay/AL112017/036``)
through ``httpx.ASGITransport``, replaces random ``uuid4`` snapshot IDs, the settings
file path, and the static bundle hash with deterministic placeholders, rounds GeoJSON
geometry coordinates to two decimal places so ``scripts/check_personal_data.py`` rule R2
passes, and writes UTF-8 JSON with sorted keys and LF line endings to
``frontend/src/test/fixtures/<name>.json``.

Usage::

    uv run python scripts/export_api_fixtures.py           # write fixtures
    uv run python scripts/export_api_fixtures.py --check   # exit 1 if stale
"""

import argparse
import asyncio
import json
import re
import sys
import tempfile
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Final, cast

import httpx

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for _support_dir in (
    REPO_ROOT / "scripts",
    REPO_ROOT / "tests" / "contract",
    REPO_ROOT / "tests" / "sources",
    REPO_ROOT / "tests" / "cli",
):
    _dir_str = str(_support_dir)
    if _dir_str not in sys.path:
        sys.path.insert(0, _dir_str)

from cli_support import (  # noqa: E402
    MIAMI,
    NASSAU,
    county_statement,
    quiet_fetcher,
    recorded_services,
)
from source_support import NOW  # noqa: E402

from ladder_data import public_landmarks  # noqa: E402
from weatherbot.services.config import AppPaths, load_settings, setting_origins  # noqa: E402
from weatherbot.services.events import BrowserChannel, EventHub  # noqa: E402
from weatherbot.services.locations import LocationService  # noqa: E402
from weatherbot.services.monitor import MonitorService  # noqa: E402
from weatherbot.services.network import Network  # noqa: E402
from weatherbot.services.notifications import (  # noqa: E402
    TEST_BODY,
    TEST_TITLE,
    LogChannel,
    NotificationService,
)
from weatherbot.services.persistence.database import open_database  # noqa: E402
from weatherbot.services.replay import ReplayCorpus  # noqa: E402
from weatherbot.services.toast import TOAST_OFF, NullChannel  # noqa: E402
from weatherbot.web.app import WebState, create_app  # noqa: E402
from weatherbot.web.map_layers import SNAPSHOT_CACHE  # noqa: E402

LOOPBACK_HOST: Final = "127.0.0.1"
FIXTURES_DIR: Final = REPO_ROOT / "frontend" / "src" / "test" / "fixtures"
REPLAY_DIR: Final = REPO_ROOT / "tests" / "fixtures" / "replay"

PLACEHOLDER_SETTINGS_FILE: Final = "/placeholder/config/weatherbot.toml"
PLACEHOLDER_UI_SHA256: Final = "000000000000"
UUID_RE: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

ROUTE_FIXTURES: Final[tuple[tuple[str, str], ...]] = (
    ("health.json", "/api/health"),
    ("locations.json", "/api/locations"),
    ("assessments.json", "/api/assessments"),
    ("storms.json", "/api/storms"),
    ("alerts.json", "/api/alerts"),
    ("timeline.json", "/api/timeline"),
    ("notifications.json", "/api/notifications"),
    ("settings.json", "/api/settings"),
    ("disclaimer.json", "/api/disclaimer"),
    ("map.json", "/api/map"),
    ("replay.json", "/api/replay"),
    ("replay-advisory.json", "/api/replay/AL112017/036"),
)


def _round_coordinates(value: object) -> object:
    """Recursively round numeric values in a GeoJSON ``coordinates`` structure to 2 decimals."""
    if isinstance(value, float | int) and not isinstance(value, bool):
        rounded = round(float(value), 2)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [_round_coordinates(item) for item in items]
    return value


def _sanitize_value(
    value: object,
    uuid_map: dict[str, str],
    *,
    key: str | None = None,
) -> object:
    """Replace random UUIDs, filesystem paths, and UI hashes, and round GeoJSON coordinates."""
    if key == "settings_file" and isinstance(value, str):
        return PLACEHOLDER_SETTINGS_FILE
    if key == "ui" and isinstance(value, dict):
        return {
            "index_sha256": PLACEHOLDER_UI_SHA256,
            "present": True,
        }
    if isinstance(value, str) and UUID_RE.match(value):
        lowered = value.lower()
        if lowered not in uuid_map:
            index = len(uuid_map) + 1
            uuid_map[lowered] = f"00000000-0000-4000-8000-{index:012d}"
        return uuid_map[lowered]
    if isinstance(value, dict):
        mapping = cast("dict[str, object]", value)
        is_geojson = isinstance(mapping.get("type"), str) and "coordinates" in mapping
        result: dict[str, object] = {}
        for child_key, child_val in mapping.items():
            if is_geojson and child_key == "coordinates":
                result[child_key] = _round_coordinates(child_val)
            else:
                result[child_key] = _sanitize_value(child_val, uuid_map, key=child_key)
        return result
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [_sanitize_value(item, uuid_map) for item in items]
    return value


async def _build_raw_payloads() -> dict[str, str]:
    """Populate a temporary SQLite database over recorded fixtures and query every route."""
    landmarks = public_landmarks()
    miami_landmark = landmarks["miami-dade"]
    nassau_landmark = landmarks["nassau"]
    corpus = ReplayCorpus.open(REPLAY_DIR)

    SNAPSHOT_CACHE.clear()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = AppPaths(config_dir=root / "config", data_dir=root / "data")
        settings = load_settings(paths, environ={})
        origins = setting_origins(paths, environ={})
        hub = EventHub()
        channels = (
            LogChannel(),
            NullChannel(TOAST_OFF),
            BrowserChannel(hub, enabled=True),
        )
        network = Network(make_fetcher=quiet_fetcher)

        with open_database(paths, now=lambda: NOW) as database:
            with recorded_services(overrides=county_statement()):
                loc_service_t0 = LocationService(
                    database.engine,
                    network=network,
                    now=lambda: NOW,
                )
                await loc_service_t0.add(
                    MIAMI,
                    miami_landmark.point.latitude,
                    miami_landmark.point.longitude,
                    polygon="forecast",
                )
                await loc_service_t0.add(
                    NASSAU,
                    nassau_landmark.point.latitude,
                    nassau_landmark.point.longitude,
                    polygon=None,
                )
                loc_service_t0.set_evacuation_order(MIAMI, on=True)

                monitor_t0 = MonitorService(
                    database.engine,
                    paths=paths,
                    settings=settings,
                    runner="serve",
                    network=network,
                    now=lambda: NOW,
                    channels=channels,
                )
                await monitor_t0.run_cycle("startup")

                t1 = NOW + timedelta(minutes=1)
                loc_service_t1 = LocationService(
                    database.engine,
                    network=network,
                    now=lambda: t1,
                )
                loc_service_t1.set_evacuation_order(MIAMI, on=False)
                monitor_t1 = MonitorService(
                    database.engine,
                    paths=paths,
                    settings=settings,
                    runner="serve",
                    network=network,
                    now=lambda: t1,
                    channels=channels,
                )
                await monitor_t1.run_cycle("manual")

                t2 = NOW + timedelta(minutes=2)
                notif_service = NotificationService(
                    database.engine,
                    settings=settings,
                    now=lambda: t2,
                    channels=channels,
                )
                await notif_service.send("test", title=TEST_TITLE, body=TEST_BODY)

            state = WebState(
                database=database,
                paths=paths,
                settings=settings,
                setting_origins=origins,
                clock=lambda: NOW + timedelta(minutes=5),
                started_at=NOW,
                corpus=corpus,
                hub=hub,
                channels=channels,
            )
            app = create_app(state)
            transport = httpx.ASGITransport(app=app)
            uuid_map: dict[str, str] = {}
            rendered: dict[str, str] = {}

            async with httpx.AsyncClient(
                transport=transport,
                base_url=f"http://{LOOPBACK_HOST}:8765",
                headers={"Host": f"{LOOPBACK_HOST}:8765"},
            ) as client:
                for filename, route in ROUTE_FIXTURES:
                    response = await client.get(route)
                    if response.status_code != 200:  # noqa: PLR2004
                        msg = f"{route} returned HTTP {response.status_code}"
                        raise RuntimeError(msg)
                    sanitized = _sanitize_value(response.json(), uuid_map)
                    rendered[filename] = (
                        json.dumps(sanitized, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
                    )

            return rendered


def render_fixtures() -> dict[str, str]:
    """Return the mapping of ``filename -> JSON text`` for every exported API fixture."""
    return asyncio.run(_build_raw_payloads())


def is_stale(directory: Path = FIXTURES_DIR) -> bool:
    """Return whether any fixture file in ``directory`` is missing or differs from fresh output."""
    expected = render_fixtures()
    for filename, content in expected.items():
        target = directory / filename
        if not target.is_file():
            return True
        if target.read_text(encoding="utf-8") != content:
            return True
    return False


def write_fixtures(directory: Path = FIXTURES_DIR) -> tuple[Path, ...]:
    """Write every exported API fixture to ``directory`` with UTF-8 and LF line endings."""
    directory.mkdir(parents=True, exist_ok=True)
    expected = render_fixtures()
    written: list[Path] = []
    for filename, content in expected.items():
        target = directory / filename
        target.write_text(content, encoding="utf-8", newline="\n")
        written.append(target)
    return tuple(written)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entry point for ``scripts/export_api_fixtures.py``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if any committed fixture in frontend/src/test/fixtures/ is stale.",
    )
    args = parser.parse_args(argv)

    if args.check:
        if is_stale():
            sys.stderr.write(
                "frontend/src/test/fixtures/ is out of date; "
                "run `uv run python scripts/export_api_fixtures.py`.\n"
            )
            return 1
        return 0

    written = write_fixtures()
    for path in written:
        print(path.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
