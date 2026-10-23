# tests/services/test_doctor_toast.py
"""``doctor``'s ``toast`` check, judged from the stored toast deliveries.

It is skipped off Windows, with the toast off, before any toast delivery is stored, and when
the database did not open, so a fresh install still exits 0. It fails when the latest toast
failed, was disabled, or was unavailable on Windows with the toast on, and when the identity
is missing although a toast was delivered before; it passes otherwise. Its detail names the
setting or the HRESULT, never a notification's text.
"""

import asyncio
from datetime import UTC, datetime
from typing import Final

import pytest
from cli_support import FakeToast

from weatherbot.services.config import AppPaths
from weatherbot.services.doctor import DATABASE_CLOSED, Check, diagnose, toast_check
from weatherbot.services.network import Network
from weatherbot.services.notifications import (
    TEST_BODY,
    TEST_TITLE,
    DeliveryResult,
    LogChannel,
    NotificationService,
    StoredDelivery,
)
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.toast import TOAST_OFF

AT: Final = datetime(2026, 10, 23, 12, tzinfo=UTC)


def _delivery(result: DeliveryResult, detail: str | None = None) -> StoredDelivery:
    return StoredDelivery(id=1, channel="toast", attempted_at=AT, result=result, detail=detail)


def _check(
    latest: StoredDelivery | None,
    *,
    identity: bool | None = True,
    toast_on: bool = True,
    delivered_before: bool = False,
) -> Check:
    return toast_check(
        latest, identity=identity, toast_on=toast_on, delivered_before=delivered_before
    )


def test_off_windows_or_with_the_toast_off_the_check_is_skipped() -> None:
    failed = _delivery("failed", "0x80070490")

    assert _check(failed, identity=None) == Check(
        "toast", "skip", "not Windows: there is no toast channel"
    )
    assert _check(failed, toast_on=False) == Check("toast", "skip", TOAST_OFF)


def test_before_any_toast_delivery_the_check_is_skipped() -> None:
    assert _check(None) == Check("toast", "skip", "no toast delivery is stored")
    assert _check(None, identity=False).status == "skip"


@pytest.mark.parametrize(
    ("result", "detail"),
    [
        ("failed", "0x80070490"),
        ("disabled", "DisabledForUser"),
        ("unavailable", "run weatherbot notify setup"),
    ],
)
def test_a_failed_disabled_or_unavailable_latest_toast_fails_naming_its_detail(
    result: DeliveryResult, detail: str
) -> None:
    check = _check(_delivery(result, detail), delivered_before=True)

    assert check.status == "fail"
    assert check.detail == (
        f"the latest toast {result} ({detail}); weatherbot notify test sends another"
    )


def test_a_missing_identity_fails_only_after_a_toast_was_delivered() -> None:
    delivered = _delivery("delivered")

    assert _check(delivered, identity=False, delivered_before=True) == Check(
        "toast",
        "fail",
        "the identity Weatherbot.Monitor is missing, although a toast was delivered before; "
        "run weatherbot notify setup",
    )
    assert _check(delivered, identity=True, delivered_before=True) == Check(
        "toast", "pass", "the latest toast delivered"
    )


def _send(database: Database, result: DeliveryResult, detail: str | None = None) -> None:
    service = NotificationService(
        database.engine, now=lambda: AT, channels=(LogChannel(), FakeToast(result, detail))
    )
    asyncio.run(service.send("test", title=TEST_TITLE, body=TEST_BODY))


def _diagnosed(database: Database | None, *, identity: bool | None) -> tuple[Check, bool]:
    report = asyncio.run(
        diagnose(
            settings_problem=None,
            settings_file_exists=False,
            database=database,
            database_problem=None if database is not None else "refused",
            created=False,
            offline=True,
            network=Network(),
            now=AT,
            identity=identity,
        )
    )
    return next(check for check in report.checks if check.name == "toast"), report.failed


def test_diagnose_judges_the_stored_toast_deliveries() -> None:
    with open_database(AppPaths.resolve()) as database:
        fresh, fresh_failed = _diagnosed(database, identity=False)
        _send(database, "delivered")
        _send(database, "disabled", "DisabledForUser")
        disabled, disabled_failed = _diagnosed(database, identity=True)
        _send(database, "delivered")
        removed, removed_failed = _diagnosed(database, identity=False)
        healthy, healthy_failed = _diagnosed(database, identity=True)
        elsewhere, _ = _diagnosed(database, identity=None)

    assert (fresh.status, fresh_failed) == ("skip", False)
    assert (disabled.status, disabled_failed) == ("fail", True)
    assert "DisabledForUser" in disabled.detail
    assert TEST_TITLE not in disabled.detail
    assert TEST_BODY[0] not in disabled.detail
    assert (removed.status, removed_failed) == ("fail", True)
    assert (healthy.status, healthy_failed) == ("pass", False)
    assert elsewhere.status == "skip"


def test_a_database_that_did_not_open_skips_the_check() -> None:
    check, _ = _diagnosed(None, identity=True)

    assert check == Check("toast", "skip", DATABASE_CLOSED)
