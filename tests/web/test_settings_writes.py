# tests/web/test_settings_writes.py
"""Tests for ``GET /api/settings`` and ``PUT /api/settings``."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from source_support import NOW

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.persistence.database import open_database
from weatherbot.web.app import WebState, create_app

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

WRITE_HEADERS = {"Origin": "http://127.0.0.1:8765"}
CROSS_SITE_HEADERS = {"Origin": "https://evil.example"}


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
            clock=lambda: NOW + timedelta(minutes=5),
            started_at=NOW,
            environ={} if environ is None else environ,
        )


def test_put_settings_saves_next_cycle_and_next_start_keys_and_updates_restart_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WEATHERBOT_NOTIFICATIONS_TOAST", raising=False)
    with _make_state(environ={}) as state:
        client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")

        initial = client.get("/api/settings").json()
        assert initial["restart_keys"] == []
        assert initial["settings_file_problem"] is None
        sha0 = initial["settings_file_sha256"]

        # 1. Save quiet hours (next_cycle) -> restart_keys remains empty!
        resp1 = client.put(
            "/api/settings",
            headers=WRITE_HEADERS,
            json={
                "expected_sha256": sha0,
                "changes": [
                    {
                        "table": "notifications",
                        "key": "quiet_hours_start",
                        "value": "22:00",
                    },
                    {
                        "table": "notifications",
                        "key": "quiet_hours_end",
                        "value": "07:00",
                    },
                    {
                        "table": "retention",
                        "key": "history_days",
                        "value": 180,
                    },
                ],
            },
        )
        assert resp1.status_code == HTTPStatus.OK
        body1 = resp1.json()
        assert body1["applied_next_cycle"] == [
            "[notifications] quiet_hours_start",
            "[notifications] quiet_hours_end",
            "[retention] history_days",
        ]
        assert body1["applied_next_start"] == []
        assert body1["restart_keys"] == []

        # Read back immediately via GET /api/settings
        after1 = client.get("/api/settings").json()
        assert after1["settings_file_exists"] is True
        assert after1["file_modified_since_start"] is True
        assert after1["restart_keys"] == []
        by_pair = {(s["table"], s["key"]): s for s in after1["settings"]}
        assert by_pair["notifications", "quiet_hours_start"]["value"] == "22:00"
        assert by_pair["notifications", "quiet_hours_start"]["origin"] == "file"
        assert by_pair["retention", "history_days"]["value"] == 180  # noqa: PLR2004

        # 2. Save a next_start key ([notifications] toast = false and [ai] daily_cap_usd = 2.5)
        #    -> restart_keys lists both!
        resp2 = client.put(
            "/api/settings",
            headers=WRITE_HEADERS,
            json={
                "expected_sha256": body1["settings_file_sha256"],
                "changes": [
                    {"table": "notifications", "key": "toast", "value": False},
                    {"table": "ai", "key": "daily_cap_usd", "value": 2.5},
                ],
            },
        )
        assert resp2.status_code == HTTPStatus.OK
        body2 = resp2.json()
        assert body2["applied_next_start"] == [
            "[notifications] toast",
            "[ai] daily_cap_usd",
        ]
        assert set(body2["restart_keys"]) == {
            "[notifications] toast",
            "[ai] daily_cap_usd",
        }


@pytest.mark.parametrize(
    ("table", "key", "value"),
    [
        ("web", "host", "0.0.0.0"),  # noqa: S104
        ("web", "port", 9000),
        ("notifications", "ntfy_server", "https://ntfy.example.com"),
        ("ai", "model", "claude-opus-4-7"),
        ("engine", "coastal_reach_km", 40.0),
        ("monitor", "confirm_after_minutes", 10),
        ("logging", "level", "DEBUG"),
    ],
)
def test_put_settings_refuses_non_allowlisted_keys_with_422(
    table: str,
    key: str,
    value: str | float,
) -> None:
    with _make_state(environ={}) as state:
        client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")
        sha = client.get("/api/settings").json()["settings_file_sha256"]

        resp = client.put(
            "/api/settings",
            headers=WRITE_HEADERS,
            json={
                "expected_sha256": sha,
                "changes": [{"table": table, "key": key, "value": value}],
            },
        )
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert f"[{table}] {key}" in resp.json()["detail"]


def test_put_settings_refuses_env_override_409_stale_sha_409_cross_field_422_and_cross_site_403() -> (  # noqa: E501
    None
):
    env = {"WEATHERBOT_NOTIFICATIONS_QUIET_HOURS_START": "22:00"}
    with _make_state(environ=env) as state:
        state.paths.config_dir.mkdir(parents=True, exist_ok=True)
        state.paths.settings_path.write_text(
            '[notifications]\nquiet_hours_start = "22:00"\nquiet_hours_end = "07:00"\n',
            encoding="utf-8",
        )
        client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")
        sha = client.get("/api/settings").json()["settings_file_sha256"]

        # 1. Cross-site request refused (403)
        cross = client.put(
            "/api/settings",
            headers=CROSS_SITE_HEADERS,
            json={
                "expected_sha256": sha,
                "changes": [{"table": "retention", "key": "history_days", "value": 90}],
            },
        )
        assert cross.status_code == HTTPStatus.FORBIDDEN

        # 2. Editing a setting overridden by an environment variable -> 409 naming variable
        env_conflict = client.put(
            "/api/settings",
            headers=WRITE_HEADERS,
            json={
                "expected_sha256": sha,
                "changes": [
                    {
                        "table": "notifications",
                        "key": "quiet_hours_start",
                        "value": "23:00",
                    }
                ],
            },
        )
        assert env_conflict.status_code == HTTPStatus.CONFLICT
        assert "WEATHERBOT_NOTIFICATIONS_QUIET_HOURS_START" in env_conflict.json()["detail"]

        # 3. Cross-field validation failure when env sets start and file clears end -> 422
        cross_field = client.put(
            "/api/settings",
            headers=WRITE_HEADERS,
            json={
                "expected_sha256": sha,
                "changes": [
                    {
                        "table": "notifications",
                        "key": "quiet_hours_end",
                        "value": "",
                    }
                ],
            },
        )
        assert cross_field.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "quiet_hours_end" in cross_field.json()["detail"]

        # 4. Stale expected_sha256 -> 409
        stale = client.put(
            "/api/settings",
            headers=WRITE_HEADERS,
            json={
                "expected_sha256": "0" * 64,
                "changes": [{"table": "retention", "key": "history_days", "value": 90}],
            },
        )
        assert stale.status_code == HTTPStatus.CONFLICT
        assert "changed on disk" in stale.json()["detail"]


def test_get_settings_reports_settings_file_problem_and_keeps_last_good_origins() -> None:
    with _make_state(environ={}) as state:
        state.paths.config_dir.mkdir(parents=True, exist_ok=True)
        state.paths.settings_path.write_text(
            "[retention]\nhistory_days = 120\n",
            encoding="utf-8",
        )
        client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")

        good = client.get("/api/settings").json()
        assert good["settings_file_problem"] is None
        ret_good = next(
            s for s in good["settings"] if s["table"] == "retention" and s["key"] == "history_days"
        )
        assert ret_good["value"] == 120  # noqa: PLR2004
        assert ret_good["origin"] == "file"

        # Break weatherbot.toml with invalid TOML -> GET /api/settings returns 200 with
        # settings_file_problem set and preserves the last good origins!
        state.paths.settings_path.write_text(
            "[retention]\nhistory_days = broken_toml\n",
            encoding="utf-8",
        )
        broken = client.get("/api/settings").json()
        assert broken["settings_file_problem"] is not None
        assert "not valid TOML" in broken["settings_file_problem"]
        ret_broken = next(
            s
            for s in broken["settings"]
            if s["table"] == "retention" and s["key"] == "history_days"
        )
        assert ret_broken["value"] == 120  # noqa: PLR2004
        assert ret_broken["origin"] == "file"
