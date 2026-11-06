# tests/services/test_phase7_alarms.py
"""Tests for Phase 7 operational alarms: ntfy 401, retention worker, and live settings."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Final

import httpx
import respx
from cli_support import (
    MIAMI,
    add_landmark,
    parse,
    quiet_fetcher,
    recorded_services,
    run,
    runtime,
)
from fastapi.testclient import TestClient
from source_support import NOW

from weatherbot.cli.documents import DoctorDocument
from weatherbot.services.config import (
    AppPaths,
    LiveSettings,
    NotificationSettings,
    RetentionSettings,
    Settings,
    load_settings,
    setting_origins,
)
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import HeartbeatRepository
from weatherbot.services.retention import (
    RETENTION_HEARTBEAT_CADENCE_S,
    RetentionService,
    RetentionWorker,
)
from weatherbot.services.schedule import MonitorSchedule
from weatherbot.web.app import WebState, create_app

if TYPE_CHECKING:
    import pytest

FAKE_TOPIC: Final = "weatherbot-alarm-topic-401"
SENSITIVE_TEXT: Final = "sensitive-marker-do-not-echo-999"


def _fake_token() -> str:
    return f"{'tk'}_{'b' * 29}"


def test_ntfy_401_alarm_across_notify_test_doctor_and_channels_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _fake_token()
    monkeypatch.setenv("WEATHERBOT_NOTIFICATIONS_NTFY", "true")
    monkeypatch.setenv("WEATHERBOT_NTFY_TOPIC", FAKE_TOPIC)
    monkeypatch.setenv("WEATHERBOT_NTFY_TOKEN", token)

    paths = AppPaths.resolve()
    environ = {
        "WEATHERBOT_NOTIFICATIONS_NTFY": "true",
        "WEATHERBOT_NTFY_TOPIC": FAKE_TOPIC,
        "WEATHERBOT_NTFY_TOKEN": token,
    }

    with respx.mock(assert_all_called=True) as router:
        router.post("https://ntfy.sh/").mock(
            return_value=httpx.Response(401, text=f"unauthorized for {FAKE_TOPIC} {token}")
        )
        test_res = run(["notify", "test"])

    assert test_res.exit_code == 1
    assert "ntfy: failed (HTTP 401)" in test_res.stdout
    assert FAKE_TOPIC not in test_res.stdout
    assert token not in test_res.stdout

    doctor_res = run(["doctor", "--offline", "--json"], runtime(now=NOW))
    assert doctor_res.exit_code == 1
    doc = parse(doctor_res, DoctorDocument)
    ntfy_check = next(check for check in doc.data.checks if check.name == "ntfy")
    assert ntfy_check.status == "fail"
    assert "HTTP 401" in ntfy_check.detail
    assert "docs/NOTIFICATIONS.md" in ntfy_check.detail
    assert FAKE_TOPIC not in doctor_res.stdout
    assert token not in doctor_res.stdout

    settings = Settings(notifications=NotificationSettings(ntfy=True))
    with open_database(paths) as db:
        state = WebState(
            database=db,
            paths=paths,
            settings=settings,
            setting_origins=setting_origins(paths, environ),
            clock=lambda: NOW,
            started_at=NOW,
            environ=environ,
        )
        client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")
        resp = client.get("/api/notifications/channels")

    assert resp.status_code == 200  # noqa: PLR2004
    assert FAKE_TOPIC not in resp.text
    assert token not in resp.text
    payload = resp.json()
    channels = payload["channels"]
    ntfy_card = next(ch for ch in channels if ch["name"] == "ntfy")
    assert ntfy_card["state"] == "on"
    assert ntfy_card["last_result"] == "failed"
    assert "ntfy.sh" in ntfy_card["detail"]


def test_retention_worker_failure_and_stale_heartbeat_in_doctor_and_dashboard(
    caplog: pytest.LogCaptureFixture,
) -> None:
    paths = AppPaths.resolve()
    settings = Settings(retention=RetentionSettings(history_days=30))
    stale_now = NOW + timedelta(seconds=2 * RETENTION_HEARTBEAT_CADENCE_S + 1)

    def failing_factory() -> RetentionService:
        msg = f"simulated disk error {SENSITIVE_TEXT}"
        raise RuntimeError(msg)

    with open_database(paths) as db:
        caplog.set_level(logging.ERROR, logger="weatherbot.services.retention")
        worker = RetentionWorker(
            db.engine,
            paths,
            settings=settings,
            clock=lambda: NOW,
            service_factory=failing_factory,
        )
        assert asyncio.run(worker.run_once()) is None

        hb_rows = HeartbeatRepository(db.engine, now=lambda: NOW).rows()
        ret_hb = next(r for r in hb_rows if r.kind == "watch" and r.name == "retention")
        assert ret_hb.consecutive_failures == 1
        assert ret_hb.last_error_kind == "RuntimeError"
        assert ret_hb.expected_every_s == RETENTION_HEARTBEAT_CADENCE_S
        assert any("RuntimeError" in record.message for record in caplog.records)
        assert all(SENSITIVE_TEXT not in record.message for record in caplog.records)

        # Record a succeeded retention heartbeat at NOW and advance clock past 2x cadence
        HeartbeatRepository(db.engine, now=lambda: NOW).record(
            "watch",
            "retention",
            at=NOW,
            result="success",
            expected_every_s=RETENTION_HEARTBEAT_CADENCE_S,
        )

        doctor_res = run(["doctor", "--offline", "--json"], runtime(now=stale_now))
        assert doctor_res.exit_code == 1
        doc = parse(doctor_res, DoctorDocument)
        hb_check = next(check for check in doc.data.checks if check.name == "heartbeat")
        assert hb_check.status == "fail"
        assert "stale: retention" in hb_check.detail

        state = WebState(
            database=db,
            paths=paths,
            settings=settings,
            setting_origins=setting_origins(paths, {}),
            clock=lambda: stale_now,
            started_at=NOW,
            environ={},
        )
        client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")
        health_resp = client.get("/api/health")
        assert health_resp.status_code == 200  # noqa: PLR2004
        health_hbs = health_resp.json()["heartbeats"]
        ret_health = next(
            item for item in health_hbs if item["kind"] == "watch" and item["name"] == "retention"
        )
        assert ret_health["stale"] is True


def test_unparseable_settings_file_logs_one_warning_and_next_cycle_runs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    paths = AppPaths.resolve()
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.settings_path.write_text(
        "[retention]\nhistory_days = 60\n[notifications]\ncooldown_hours = 8\n",
        encoding="utf-8",
    )
    initial = load_settings(paths, {})
    live = LiveSettings(paths, {}, initial)
    assert live().retention.history_days == 60  # noqa: PLR2004
    assert live().notifications.cooldown_hours == 8.0  # noqa: PLR2004

    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0

        # Corrupt weatherbot.toml with invalid TOML syntax containing a sensitive marker
        paths.settings_path.write_text(
            f"broken = [unclosed toml {SENSITIVE_TEXT}\n",
            encoding="utf-8",
        )

        caplog.set_level(logging.WARNING, logger="weatherbot.services.config")
        caplog.clear()

        with open_database(paths) as db:
            # First reload logs one WARNING; second reload stays quiet
            first_reload = live()
            second_reload = live()
            assert first_reload.retention.history_days == 60  # noqa: PLR2004
            assert second_reload.notifications.cooldown_hours == 8.0  # noqa: PLR2004

            schedule = MonitorSchedule(
                db.engine,
                paths,
                settings=initial,
                runner="serve",
                clock=lambda: NOW,
                make_fetcher=lambda client, store: quiet_fetcher(client, store, now=NOW),
                live_settings=live,
            )
            cycle = asyncio.run(schedule.execute_cycle("manual"))
            assert cycle.status == "complete"

            warnings = [
                record
                for record in caplog.records
                if record.name == "weatherbot.services.config" and record.levelno == logging.WARNING
            ]
            assert len(warnings) == 1
            assert "ConfigError" in warnings[0].message
            assert SENSITIVE_TEXT not in warnings[0].message

            state = WebState(
                database=db,
                paths=paths,
                settings=initial,
                setting_origins=(),
                clock=lambda: NOW,
                started_at=NOW,
                environ={},
            )
            client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")
            settings_resp = client.get("/api/settings")
            assert settings_resp.status_code == 200  # noqa: PLR2004
            body = settings_resp.json()
            assert body["settings_file_problem"] is not None
            assert "not valid TOML" in body["settings_file_problem"]
            assert SENSITIVE_TEXT not in body["settings_file_problem"]

    # Fixing weatherbot.toml clears the warning latch and applies the new next_cycle value
    paths.settings_path.write_text("[retention]\nhistory_days = 90\n", encoding="utf-8")
    recovered = live()
    assert recovered.retention.history_days == 90  # noqa: PLR2004
