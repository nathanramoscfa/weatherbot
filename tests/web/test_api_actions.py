# tests/web/test_api_actions.py
"""Tests for the four guarded write routes in ``weatherbot.web.routes.actions``."""

import asyncio
import json
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import cast

import httpx
import pytest
import respx
from cli_support import (
    MIAMI,
    NASSAU,
    FakeToast,
    directory,
    landmark,
    quiet_fetcher,
    recorded_services,
)
from fixture_support import register_alert
from source_support import NOW, entry

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.events import BrowserChannel, EventHub, Subscription
from weatherbot.services.locations import LocationNameTakenError, LocationService
from weatherbot.services.monitor import CycleResult
from weatherbot.services.network import Network
from weatherbot.services.notifications import LogChannel
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import CycleRepository
from weatherbot.services.schedule import MonitorSchedule
from weatherbot.web.app import WebState, create_app

FORECAST_ZONE_URL = "https://api.weather.gov/zones/forecast/FLZ173"
FORECAST_ALERTS_URL = "https://api.weather.gov/alerts/active/zone/FLZ173"
SAME_ORIGIN = {"Origin": "http://127.0.0.1:8765"}


class MutableClock:
    """Mutable UTC clock for rate-limit and schedule tests."""

    def __init__(self, current: datetime = NOW) -> None:
        """Create a mutable clock starting at ``current``."""
        self.current = current

    def __call__(self) -> datetime:
        """Return the current UTC instant."""
        return self.current


def _alert_response(*, has_hurricane_warning: bool) -> httpx.Response:
    capture = directory("nws-alerts-zone")
    doc = cast(
        "dict[str, object]",
        json.loads(capture.payload(entry(capture, "alerts-zone-FLZ173.geojson"))),
    )
    if has_hurricane_warning:
        feature = register_alert(NOW)
        feature["id"] = "https://api.weather.gov/alerts/urn:oid:hw.1"
        props = cast("dict[str, object]", feature["properties"])
        props["id"] = "urn:oid:hw.1"
        props["event"] = "Hurricane Warning"
        props["headline"] = "Hurricane Warning issued by NWS Miami FL"
        props["affectedZones"] = [FORECAST_ZONE_URL]
        geocode = cast("dict[str, object]", props["geocode"])
        geocode["UGC"] = ["FLZ173"]
        doc["features"] = [feature]
    else:
        doc["features"] = []
    return httpx.Response(
        200,
        content=json.dumps(doc).encode("utf-8"),
        headers={"content-type": "application/geo+json"},
    )


def test_every_write_refuses_cross_site_and_non_json_requests() -> None:
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    try:
        state = WebState(
            database=database,
            paths=paths,
            settings=Settings(),
            clock=lambda: NOW,
            started_at=NOW,
        )
        app = create_app(state)
        writes: tuple[tuple[str, str, dict[str, object]], ...] = (
            ("POST", "/api/locations", {"name": "Home", "latitude": 25.0, "longitude": -80.0}),
            ("PUT", "/api/locations/evacuation", {"location": "Home", "on": True}),
            ("POST", "/api/cycles", {}),
            ("POST", "/api/notifications/test", {}),
        )

        async def _check() -> None:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://127.0.0.1:8765",
            ) as client:
                for method, path, payload in writes:
                    foreign = await client.request(
                        method,
                        path,
                        json=payload,
                        headers={"Origin": "https://attacker.example"},
                    )
                    assert foreign.status_code == HTTPStatus.FORBIDDEN, (method, path)

                    cross_site = await client.request(
                        method,
                        path,
                        json=payload,
                        headers={
                            "Origin": "http://127.0.0.1:8765",
                            "Sec-Fetch-Site": "cross-site",
                        },
                    )
                    assert cross_site.status_code == HTTPStatus.FORBIDDEN, (method, path)

                    non_json = await client.request(
                        method,
                        path,
                        content=b"plain text",
                        headers={
                            "Origin": "http://127.0.0.1:8765",
                            "Content-Type": "text/plain",
                        },
                    )
                    assert non_json.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE, (
                        method,
                        path,
                    )

        asyncio.run(_check())
    finally:
        database.close()


async def _exercise_location_and_evacuation_writes(
    client: httpx.AsyncClient,
    database: Database,
    router: respx.MockRouter,
    clock: MutableClock,
    sub: Subscription,
) -> None:
    miami_lat, miami_lon = landmark("miami-dade")
    nassau_lat, nassau_lon = landmark("nassau")

    created = await client.post(
        "/api/locations",
        json={
            "name": MIAMI,
            "latitude": float(miami_lat),
            "longitude": float(miami_lon),
            "polygon": "forecast",
        },
    )
    assert created.status_code == HTTPStatus.CREATED, created.text
    body = created.json()
    assert body["name"] == MIAMI
    assert body["has_polygon"] is True
    assert body["nws"]["forecast_zone"] == "FLZ173"

    loc_ev = await asyncio.wait_for(anext(sub), timeout=1.0)
    assert loc_ev.kind == "location"
    assert loc_ev.location == MIAMI
    assert loc_ev.invalidate == ("locations", "assessments", "map")

    with pytest.raises(LocationNameTakenError):
        await LocationService(
            database.engine,
            network=Network(make_fetcher=quiet_fetcher),
            now=clock,
        ).add(MIAMI, float(miami_lat), float(miami_lon))

    taken = await client.post(
        "/api/locations",
        json={
            "name": MIAMI,
            "latitude": float(miami_lat),
            "longitude": float(miami_lon),
            "polygon": None,
        },
    )
    assert taken.status_code == HTTPStatus.CONFLICT

    outside_nws = await client.post(
        "/api/locations",
        json={
            "name": NASSAU,
            "latitude": float(nassau_lat),
            "longitude": float(nassau_lon),
            "polygon": "county",
        },
    )
    assert outside_nws.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert nassau_lat not in outside_nws.text

    extra_field = await client.post(
        "/api/locations",
        json={
            "name": "Extra",
            "latitude": float(miami_lat),
            "longitude": float(miami_lon),
            "unexpected": "secret_value",
        },
    )
    assert extra_field.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "secret_value" not in extra_field.text

    router.routes.clear()
    router.route(host__in=("127.0.0.1", "localhost", "::1")).pass_through()
    router.get(url__regex=r"https://api\.weather\.gov/points/.*").mock(
        return_value=httpx.Response(503)
    )
    upstream_fail = await client.post(
        "/api/locations",
        json={
            "name": "Upstream Fail",
            "latitude": float(miami_lat),
            "longitude": float(miami_lon),
            "polygon": None,
        },
    )
    assert upstream_fail.status_code == HTTPStatus.BAD_GATEWAY
    assert "nws-points" in upstream_fail.json()["detail"]
    assert miami_lat not in upstream_fail.text

    clock.current = NOW + timedelta(minutes=5)
    evac_on = await client.put(
        "/api/locations/evacuation",
        json={"location": MIAMI, "on": True},
    )
    assert evac_on.status_code == HTTPStatus.OK
    evac_body = evac_on.json()
    assert evac_body["changed"] is True
    assert evac_body["location"]["evacuation_order_in_effect"] is True

    evac_ev = await asyncio.wait_for(anext(sub), timeout=1.0)
    assert evac_ev.kind == "location"
    assert evac_ev.location == MIAMI

    evac_repeat = await client.put(
        "/api/locations/evacuation",
        json={"location": MIAMI, "on": True},
    )
    assert evac_repeat.status_code == HTTPStatus.OK
    assert evac_repeat.json()["changed"] is False

    evac_unknown = await client.put(
        "/api/locations/evacuation",
        json={"location": "Unknown Place", "on": True},
    )
    assert evac_unknown.status_code == HTTPStatus.NOT_FOUND


def test_post_locations_and_put_evacuation_answers_errors_and_events() -> None:
    clock = MutableClock(NOW)
    with recorded_services() as router:
        paths = AppPaths.resolve()
        database = open_database(paths, now=clock)
        try:

            async def _drive() -> None:
                hub = EventHub(asyncio.get_running_loop(), now=clock, started_at=NOW)
                sub = hub.subscribe()
                state = WebState(
                    database=database,
                    paths=paths,
                    settings=Settings(),
                    clock=clock,
                    started_at=NOW,
                    hub=hub,
                    network=Network(make_fetcher=quiet_fetcher),
                )
                transport = httpx.ASGITransport(app=create_app(state))
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://127.0.0.1:8765",
                    headers=SAME_ORIGIN,
                ) as client:
                    await _exercise_location_and_evacuation_writes(
                        client,
                        database,
                        router,
                        clock,
                        sub,
                    )
                sub.close()

            asyncio.run(_drive())
        finally:
            database.close()


async def _exercise_cycles_and_test_notifications(  # noqa: PLR0913 - test helper for cycle and notification routes
    *,
    client: httpx.AsyncClient,
    database: Database,
    router: respx.MockRouter,
    clock: MutableClock,
    state: WebState,
    schedule: MonitorSchedule,
    gate: asyncio.Event,
    sub: Subscription,
) -> None:
    miami_lat, miami_lon = landmark("miami-dade")
    created = await client.post(
        "/api/locations",
        json={
            "name": MIAMI,
            "latitude": float(miami_lat),
            "longitude": float(miami_lon),
            "polygon": None,
        },
    )
    assert created.status_code == HTTPStatus.CREATED
    _ = await asyncio.wait_for(anext(sub), timeout=1.0)

    gate.clear()
    router.get(FORECAST_ALERTS_URL).mock(return_value=_alert_response(has_hurricane_warning=True))
    accepted = await client.post("/api/cycles", json={})
    assert accepted.status_code == HTTPStatus.ACCEPTED
    assert accepted.json()["trigger"] == "manual"
    assert state.cycle_in_flight is True

    conflict = await client.post("/api/cycles", json={})
    assert conflict.status_code == HTTPStatus.CONFLICT

    gate.set()
    assert state.cycle_task is not None
    first_result = await state.cycle_task
    assert first_result is not None
    assert first_result.runner == "serve"
    assert first_result.trigger == "manual"
    assert state.cycle_in_flight is False

    clock.current = NOW + timedelta(seconds=30)
    too_soon = await client.post("/api/cycles", json={})
    assert too_soon.status_code == HTTPStatus.TOO_MANY_REQUESTS

    clock.current = NOW + timedelta(seconds=60)
    router.get(FORECAST_ALERTS_URL).mock(return_value=_alert_response(has_hurricane_warning=False))
    second_accepted = await client.post("/api/cycles", json={})
    assert second_accepted.status_code == HTTPStatus.ACCEPTED
    assert state.cycle_task is not None
    second_result = await state.cycle_task
    assert second_result is not None
    expected_confirm = clock.current + timedelta(minutes=5)
    assert second_result.confirm_at == expected_confirm
    assert schedule.next_confirm_due(clock.current) == expected_confirm

    stored_cycles = CycleRepository(database.engine).recent(5)
    assert stored_cycles[0].runner == "serve"
    assert stored_cycles[0].trigger == "manual"

    await _exercise_test_notifications_endpoint(client, clock, sub)


async def _exercise_test_notifications_endpoint(
    client: httpx.AsyncClient,
    clock: MutableClock,
    sub: Subscription,
) -> None:
    while sub.has_pending:
        await anext(sub)

    test_res = await client.post("/api/notifications/test", json={})
    assert test_res.status_code == HTTPStatus.OK
    test_body = test_res.json()
    assert test_body["kind"] == "test"
    by_channel = {d["channel"]: d["result"] for d in test_body["deliveries"]}
    assert by_channel == {
        "log": "delivered",
        "toast": "delivered",
        "browser": "delivered",
    }
    stream_notif = await asyncio.wait_for(anext(sub), timeout=1.0)
    assert stream_notif.kind == "notification"
    assert stream_notif.display is True

    clock.current += timedelta(seconds=5)
    rate_limited = await client.post("/api/notifications/test", json={})
    assert rate_limited.status_code == HTTPStatus.TOO_MANY_REQUESTS

    clock.current += timedelta(seconds=6)
    allowed_again = await client.post("/api/notifications/test", json={})
    assert allowed_again.status_code == HTTPStatus.OK


def test_post_cycles_and_post_notifications_test_rate_limits_single_flight_and_held_drop() -> None:
    clock = MutableClock(NOW)
    with recorded_services() as router:
        paths = AppPaths.resolve()
        database = open_database(paths, now=clock)
        try:

            async def _drive() -> None:
                hub = EventHub(asyncio.get_running_loop(), now=clock, started_at=NOW)
                sub = hub.subscribe()
                toast = FakeToast("delivered")
                channels = (LogChannel(), toast, BrowserChannel(hub, enabled=True))
                schedule = MonitorSchedule(
                    database.engine,
                    paths,
                    settings=Settings(),
                    runner="serve",
                    clock=clock,
                    make_fetcher=quiet_fetcher,
                    channels=channels,
                    listeners=(hub.cycle_listener,),
                )
                gate = asyncio.Event()
                gate.set()

                async def _request_cycle() -> CycleResult:
                    await gate.wait()
                    return await schedule.execute_cycle("manual")

                state = WebState(
                    database=database,
                    paths=paths,
                    settings=Settings(),
                    clock=clock,
                    started_at=NOW,
                    hub=hub,
                    channels=channels,
                    network=Network(make_fetcher=quiet_fetcher),
                    request_cycle=_request_cycle,
                )
                transport = httpx.ASGITransport(app=create_app(state))
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://127.0.0.1:8765",
                    headers=SAME_ORIGIN,
                ) as client:
                    await _exercise_cycles_and_test_notifications(
                        client=client,
                        database=database,
                        router=router,
                        clock=clock,
                        state=state,
                        schedule=schedule,
                        gate=gate,
                        sub=sub,
                    )
                sub.close()

            asyncio.run(_drive())
        finally:
            database.close()
