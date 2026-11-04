# tests/services/test_doctor_ntfy.py
"""Tests for ``doctor``'s ``ntfy`` check and ``diagnose`` integration."""

from datetime import UTC, datetime

import pytest
from cli_support import parse, run, runtime

from weatherbot.cli.documents import DoctorDocument
from weatherbot.services.config import AppPaths, NotificationSettings, Settings
from weatherbot.services.doctor import (
    MISSING_NTFY_TOPIC,
    NTFY_OFF,
    diagnose,
    ntfy_check,
)
from weatherbot.services.network import Network
from weatherbot.services.notifications import LogChannel, NotificationService, StoredDelivery
from weatherbot.services.persistence.database import open_database
from weatherbot.services.toast import NullChannel

FAKE_TOPIC = "weatherbot-doctor-topic-987654"


def _fake_token() -> str:
    return f"{'tk'}_{'b' * 29}"


def test_ntfy_check_skips_when_off_and_fails_when_topic_missing_with_runbook() -> None:
    skipped = ntfy_check(ntfy_on=False, environ={})
    assert (skipped.name, skipped.status, skipped.detail) == ("ntfy", "skip", NTFY_OFF)

    missing = ntfy_check(ntfy_on=True, environ={"WEATHERBOT_NTFY_TOPIC": "   "})
    assert (missing.name, missing.status, missing.detail) == ("ntfy", "fail", MISSING_NTFY_TOPIC)
    assert "docs/NOTIFICATIONS.md" in missing.detail


def test_ntfy_check_fails_when_latest_delivery_failed_and_never_leaks_secrets() -> None:
    token = _fake_token()
    failed_delivery = StoredDelivery(
        id=4,
        channel="ntfy",
        attempted_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
        result="failed",
        detail="HTTP 502",
    )
    failed = ntfy_check(
        ntfy_on=True,
        ntfy_server="https://ntfy.example.com:8443",
        environ={
            "WEATHERBOT_NTFY_TOPIC": FAKE_TOPIC,
            "WEATHERBOT_NTFY_TOKEN": token,
        },
        latest=failed_delivery,
    )
    assert failed.status == "fail"
    assert "ntfy.example.com" in failed.detail
    assert "HTTP 502" in failed.detail
    assert "docs/NOTIFICATIONS.md" in failed.detail
    assert FAKE_TOPIC not in failed.detail
    assert token not in failed.detail


def test_ntfy_check_passes_with_host_token_presence_and_latest_delivery_state() -> None:
    token = _fake_token()
    no_delivery = ntfy_check(
        ntfy_on=True,
        ntfy_server="https://ntfy.sh",
        environ={"WEATHERBOT_NTFY_TOPIC": FAKE_TOPIC},
        latest=None,
    )
    assert no_delivery.status == "pass"
    assert no_delivery.detail == "server ntfy.sh (no bearer token); no delivery stored yet"
    assert FAKE_TOPIC not in no_delivery.detail

    delivered = StoredDelivery(
        id=5,
        channel="ntfy",
        attempted_at=datetime(2026, 11, 4, 12, 5, tzinfo=UTC),
        result="delivered",
        detail=None,
    )
    with_token = ntfy_check(
        ntfy_on=True,
        ntfy_server="https://ntfy.example.com",
        environ={
            "WEATHERBOT_NTFY_TOPIC": FAKE_TOPIC,
            "WEATHERBOT_NTFY_TOKEN": token,
        },
        latest=delivered,
    )
    assert with_token.status == "pass"
    assert with_token.detail == (
        "server ntfy.example.com (with bearer token); latest delivery delivered"
    )
    assert FAKE_TOPIC not in with_token.detail
    assert token not in with_token.detail


@pytest.mark.anyio
async def test_diagnose_includes_ntfy_check() -> None:
    paths = AppPaths.resolve()
    with open_database(paths) as database:
        service = NotificationService(
            database.engine,
            settings=Settings(notifications=NotificationSettings(ntfy=True)),
            channels=(LogChannel(), NullChannel("HTTP 500", channel_name="ntfy", result="failed")),
        )
        await service.send("test", title="Test", body=("Body",))

        report = await diagnose(
            settings_problem=None,
            settings_file_exists=False,
            database=database,
            database_problem=None,
            created=False,
            offline=True,
            network=Network(),
            ntfy_on=True,
            ntfy_server="https://ntfy.sh",
            environ={"WEATHERBOT_NTFY_TOPIC": FAKE_TOPIC},
        )
    ntfy_row = next(c for c in report.checks if c.name == "ntfy")
    assert ntfy_row.status == "fail"
    assert "HTTP 500" in ntfy_row.detail
    assert FAKE_TOPIC not in ntfy_row.detail


def test_cli_doctor_offline_fresh_run_exits_zero() -> None:
    # Fresh temporary directory with defaults (ntfy=False) -> doctor --offline --json exits 0.
    fresh = run(["doctor", "--offline", "--json"], runtime())
    assert fresh.exit_code == 0, fresh.stderr
    doc = parse(fresh, DoctorDocument)
    ntfy_doc_row = next(c for c in doc.data.checks if c.name == "ntfy")
    assert ntfy_doc_row.status == "skip"
