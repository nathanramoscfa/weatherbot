# tests/web/test_notification_channels.py
"""Tests for ``GET /api/notifications/channels`` and ``PUT /api/locations/preferences``."""

import asyncio
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from scenarios import miami_dade
from source_support import NOW

from weatherbot.services.config import AppPaths, NotificationSettings, Settings
from weatherbot.services.notifications import LogChannel, NotificationService
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import LocationRepository
from weatherbot.services.toast import NullChannel
from weatherbot.web.app import WebState, create_app

FAKE_TOPIC = "weatherbot-web-topic-987654321"
WRITE_HEADERS = {"Origin": "http://127.0.0.1:8765"}


def _fake_token() -> str:
    return f"{'tk'}_{'d' * 29}"


@contextmanager
def _make_state(
    *,
    settings: Settings | None = None,
    environ: Mapping[str, str] | None = None,
) -> Generator[WebState]:
    paths = AppPaths.resolve()
    with open_database(paths, now=lambda: NOW) as database:
        yield WebState(
            database=database,
            paths=paths,
            settings=settings or Settings(),
            clock=lambda: NOW,
            started_at=NOW,
            environ=environ,
        )


def test_get_notification_channels_reports_states_and_latest_deliveries_without_secrets() -> None:
    token = _fake_token()
    # 1. Default settings: ntfy is off.
    with _make_state() as state:
        client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")
        resp = client.get("/api/notifications/channels")
        assert resp.status_code == HTTPStatus.OK
        payload = resp.json()
        by_name = {ch["name"]: ch for ch in payload["channels"]}
        assert list(by_name) == ["log", "toast", "browser", "ntfy"]
        assert by_name["log"]["state"] == "on"
        assert by_name["ntfy"]["state"] == "off"

    # 2. ntfy enabled without topic -> unconfigured.
    settings_on = Settings(
        notifications=NotificationSettings(
            toast=True,
            browser=True,
            ntfy=True,
            ntfy_server="https://ntfy.example.com:8443",
        )
    )
    with _make_state(settings=settings_on, environ={}) as state:
        client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")
        resp = client.get("/api/notifications/channels")
        assert resp.status_code == HTTPStatus.OK
        by_name = {ch["name"]: ch for ch in resp.json()["channels"]}
        assert by_name["ntfy"]["state"] == "unconfigured"
        assert "WEATHERBOT_NTFY_TOPIC" in by_name["ntfy"]["detail"]

    # 3. ntfy enabled with topic and token -> on, never leaks topic or token.
    env = {
        "WEATHERBOT_NTFY_TOPIC": FAKE_TOPIC,
        "WEATHERBOT_NTFY_TOKEN": token,
    }
    with _make_state(settings=settings_on, environ=env) as state:
        service = NotificationService(
            state.database.engine,
            settings=settings_on,
            channels=(LogChannel(), NullChannel("ok", channel_name="ntfy", result="delivered")),
        )
        asyncio.run(service.send("test", title="Test", body=("Body",)))

        client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")
        resp = client.get("/api/notifications/channels")
        assert resp.status_code == HTTPStatus.OK
        raw = resp.text
        assert FAKE_TOPIC not in raw
        assert token not in raw
        by_name = {ch["name"]: ch for ch in resp.json()["channels"]}
        assert by_name["ntfy"]["state"] == "on"
        assert by_name["ntfy"]["last_result"] == "delivered"
        assert "ntfy.example.com" in by_name["ntfy"]["detail"]
        assert "bearer token set" in by_name["ntfy"]["detail"]


@pytest.mark.parametrize("bad_level", [1, 6])
def test_put_location_preferences_updates_and_validates_bounds_and_404(bad_level: int) -> None:
    loc = miami_dade()
    with _make_state() as state:
        LocationRepository(state.database.engine).add(loc)
        client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")

        # Valid update
        ok = client.put(
            "/api/locations/preferences",
            headers=WRITE_HEADERS,
            json={
                "location": loc.name,
                "preferences": {
                    "toast": False,
                    "browser": True,
                    "phone": False,
                    "phone_min_level": 4,
                },
            },
        )
        assert ok.status_code == HTTPStatus.OK
        assert ok.json()["preferences"] == {
            "toast": False,
            "browser": True,
            "phone": False,
            "phone_min_level": 4,
        }

        # Unknown location -> 404
        missing = client.put(
            "/api/locations/preferences",
            headers=WRITE_HEADERS,
            json={
                "location": "No Such Place",
                "preferences": {
                    "toast": True,
                    "browser": True,
                    "phone": True,
                    "phone_min_level": 2,
                },
            },
        )
        assert missing.status_code == HTTPStatus.NOT_FOUND

        # Invalid phone_min_level -> 422
        invalid = client.put(
            "/api/locations/preferences",
            headers=WRITE_HEADERS,
            json={
                "location": loc.name,
                "preferences": {
                    "toast": True,
                    "browser": True,
                    "phone": True,
                    "phone_min_level": bad_level,
                },
            },
        )
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
