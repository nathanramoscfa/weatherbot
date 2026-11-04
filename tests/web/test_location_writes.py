# tests/web/test_location_writes.py
"""Tests for ``POST /api/locations/search``, ``/api/locations/remove``, and 502 logging."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any, cast

import httpx
import pytest
from cli_support import directory, landmark, quiet_fetcher, recorded_services
from source_support import NOW, entry

from weatherbot.services.config import AppPaths, MonitorSettings, Settings
from weatherbot.services.events import EventHub, HubEvent
from weatherbot.services.locks import ProcessLock
from weatherbot.services.logs import SecretFilter
from weatherbot.services.network import Network
from weatherbot.services.persistence.database import open_database
from weatherbot.sources import nominatim, nws
from weatherbot.sources.http import RedactingFilter
from weatherbot.web.app import WebState, create_app

SAME_ORIGIN = {"Origin": "http://127.0.0.1:8765"}
JSON = {"content-type": "application/json; charset=utf-8"}


class MutableClock:
    """Mutable UTC clock for search cooldown tests."""

    def __init__(self, current: datetime = NOW) -> None:
        """Create the clock starting at ``current``."""
        self.current = current

    def __call__(self) -> datetime:
        """Return the current UTC instant."""
        return self.current


def test_search_and_remove_refuse_cross_site_and_non_json_requests() -> None:
    paths = AppPaths.resolve()
    with open_database(paths, now=lambda: NOW) as database:
        state = WebState(
            database=database,
            paths=paths,
            settings=Settings(),
            clock=lambda: NOW,
            started_at=NOW,
        )
        app = create_app(state)
        writes: tuple[tuple[str, dict[str, object]], ...] = (
            ("/api/locations/search", {"query": "Nassau, Bahamas"}),
            ("/api/locations/remove", {"location": "Home"}),
        )

        async def _check() -> None:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                for path, payload in writes:
                    foreign = await client.post(
                        path,
                        json=payload,
                        headers={"Origin": "https://attacker.example"},
                    )
                    assert foreign.status_code == HTTPStatus.FORBIDDEN

                    cross_site = await client.post(
                        path,
                        json=payload,
                        headers={
                            "Origin": "http://127.0.0.1:8765",
                            "Sec-Fetch-Site": "cross-site",
                        },
                    )
                    assert cross_site.status_code == HTTPStatus.FORBIDDEN

                    plain_text = await client.post(
                        path,
                        content=b"not-json",
                        headers={**SAME_ORIGIN, "Content-Type": "text/plain"},
                    )
                    assert plain_text.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE

        asyncio.run(_check())


def test_search_route_returns_candidates_enforces_two_second_cooldown_and_caches_results() -> None:
    paths = AppPaths.resolve()
    clock = MutableClock(NOW)
    with open_database(paths, now=clock) as database, recorded_services() as router:
        state = WebState(
            database=database,
            paths=paths,
            settings=Settings(),
            clock=clock,
            started_at=NOW,
            network=Network(make_fetcher=quiet_fetcher),
        )
        app = create_app(state)
        search_url = nominatim.search_url("Nassau, Bahamas")
        geocode = directory("geocode-nominatim")
        search_item = entry(geocode, "search-nassau.json")
        route = router.get(search_url).mock(
            return_value=httpx.Response(200, content=geocode.payload(search_item), headers=JSON)
        )

        async def _exercise() -> None:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                first = await client.post(
                    "/api/locations/search",
                    json={"query": "Nassau, Bahamas"},
                    headers=SAME_ORIGIN,
                )
                assert first.status_code == HTTPStatus.OK
                payload = first.json()
                assert len(payload["candidates"]) >= 1
                assert "OpenStreetMap" in payload["attribution"]
                assert route.call_count == 1

                # Within 2 seconds: 429 with Retry-After
                clock.current = NOW + timedelta(seconds=1)
                too_soon = await client.post(
                    "/api/locations/search",
                    json={"query": "Nassau, Bahamas"},
                    headers=SAME_ORIGIN,
                )
                assert too_soon.status_code == HTTPStatus.TOO_MANY_REQUESTS
                assert "Retry-After" in too_soon.headers

                # After 2 seconds: served from SearchCache without a second HTTP request
                clock.current = NOW + timedelta(seconds=3)
                cached = await client.post(
                    "/api/locations/search",
                    json={"query": "  nassau, bahamas "},
                    headers=SAME_ORIGIN,
                )
                assert cached.status_code == HTTPStatus.OK
                assert cached.json() == payload
                assert route.call_count == 1

        asyncio.run(_exercise())


def test_create_location_502_logs_field_error_at_warning_without_coordinates_and_returns_detail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    paths = AppPaths.resolve()
    lat_str, lon_str = landmark("miami-dade")
    lat, lon = float(lat_str), float(lon_str)

    points_dir = directory("nws-points")
    broken_doc = cast(
        "dict[str, Any]",
        json.loads(points_dir.payload(entry(points_dir, "points-miami-dade.json"))),
    )
    cast("dict[str, Any]", broken_doc["properties"]).pop("timeZone", None)

    logger = logging.getLogger("weatherbot.web.routes.actions")
    coord_filter = RedactingFilter()
    secret_filter = SecretFilter()
    logger.addFilter(coord_filter)
    logger.addFilter(secret_filter)
    caplog.set_level(logging.WARNING, logger="weatherbot.web.routes.actions")

    try:
        with open_database(paths, now=lambda: NOW) as database, recorded_services() as router:
            router.get(nws.points_url(lat, lon)).mock(
                return_value=httpx.Response(
                    200,
                    content=json.dumps(broken_doc).encode("utf-8"),
                    headers={"content-type": "application/geo+json"},
                )
            )
            state = WebState(
                database=database,
                paths=paths,
                settings=Settings(),
                clock=lambda: NOW,
                started_at=NOW,
                network=Network(make_fetcher=quiet_fetcher),
            )
            app = create_app(state)

            async def _exercise() -> None:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://127.0.0.1:8765"
                ) as client:
                    resp = await client.post(
                        "/api/locations",
                        json={"name": "Broken", "latitude": lat, "longitude": lon},
                        headers=SAME_ORIGIN,
                    )
                    assert resp.status_code == HTTPStatus.BAD_GATEWAY
                    detail = resp.json()["detail"]
                    assert "timeZone" in detail
                    assert lat_str not in detail
                    assert lon_str not in detail

            asyncio.run(_exercise())

        warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("timeZone" in msg for msg in warnings)
        for msg in warnings:
            assert lat_str not in msg
            assert lon_str not in msg
    finally:
        logger.removeFilter(coord_filter)
        logger.removeFilter(secret_filter)


def test_remove_route_deletes_location_publishes_event_and_handles_404_and_409() -> None:
    paths = AppPaths.resolve()
    lat_str, lon_str = landmark("nassau")
    lat, lon = float(lat_str), float(lon_str)
    hub = EventHub()
    sub = hub.subscribe()

    with open_database(paths, now=lambda: NOW) as database, recorded_services():
        state = WebState(
            database=database,
            paths=paths,
            settings=Settings(monitor=MonitorSettings(cycle_lock_wait_seconds=1)),
            clock=lambda: NOW,
            started_at=NOW,
            hub=hub,
            network=Network(make_fetcher=quiet_fetcher),
        )
        app = create_app(state)

        async def _exercise() -> list[HubEvent]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                created = await client.post(
                    "/api/locations",
                    json={"name": "Nassau", "latitude": lat, "longitude": lon},
                    headers=SAME_ORIGIN,
                )
                assert created.status_code == HTTPStatus.CREATED

                # 404 for unknown name without echoing the unknown name
                missing = await client.post(
                    "/api/locations/remove",
                    json={"location": "SecretUnknownPlace"},
                    headers=SAME_ORIGIN,
                )
                assert missing.status_code == HTTPStatus.NOT_FOUND
                assert "SecretUnknownPlace" not in missing.text

                # 409 when cycle.lock is held
                lock = ProcessLock(paths.cycle_lock_path)
                lock.acquire(0.0)
                try:
                    busy = await client.post(
                        "/api/locations/remove",
                        json={"location": "Nassau"},
                        headers=SAME_ORIGIN,
                    )
                finally:
                    lock.release()
                assert busy.status_code == HTTPStatus.CONFLICT

                # 200 when lock is free
                removed = await client.post(
                    "/api/locations/remove",
                    json={"location": "Nassau"},
                    headers=SAME_ORIGIN,
                )
                assert removed.status_code == HTTPStatus.OK
                body = removed.json()
                assert body["removed"] == "Nassau"
                assert "DISCLAIMER.md" in body["notice"]

                collected: list[HubEvent] = []
                while sub.has_pending:
                    collected.append(await anext(sub))
                return collected

        events = asyncio.run(_exercise())

    remove_events = [e for e in events if e.kind == "location" and "timeline" in e.invalidate]
    assert len(remove_events) == 1
    assert set(remove_events[0].invalidate) == {
        "locations",
        "assessments",
        "map",
        "alerts",
        "timeline",
    }
