# tests/desktop/test_toast_desktop.py
"""A real toast on the operator's desktop: run deliberately, with the operator's yes.

``uv run pytest -m desktop tests/desktop/test_toast_desktop.py`` shows one toast, which says
it is a test and names no location, through a real ``ToastChannel`` under the registered
identity (``weatherbot notify setup`` registers it first), and passes when Windows reports
``delivered``. Whether the toast stayed in the notification center is the operator's to
say; the pull request records it. No other test shows a toast: ``tests/conftest.py`` turns
the toast off, and this test turns it back on.
"""

import asyncio
import sys
from datetime import UTC, datetime

import pytest

from weatherbot.services.config import AppPaths, load_settings
from weatherbot.services.notifications import TEST_BODY, TEST_TITLE, Delivery, StoredNotification
from weatherbot.services.toast import ToastChannel, identity_registered, toast_channel


@pytest.mark.desktop
def test_a_real_toast_reaches_windows_and_reads_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    assert sys.platform == "win32", "the desktop tests run on the operator's Windows machine"
    assert identity_registered() is True, "run weatherbot notify setup first"
    monkeypatch.setenv("WEATHERBOT_NOTIFICATIONS_TOAST", "true")
    channel = toast_channel(load_settings(AppPaths.resolve()))
    assert isinstance(channel, ToastChannel)
    notification = StoredNotification(
        id=0,
        location_name=None,
        location_time_zone=None,
        assessment_id=None,
        cycle_id=None,
        kind="test",
        level=None,
        escalation=False,
        title=TEST_TITLE,
        body=TEST_BODY,
        created_at=datetime.now(UTC),
    )

    assert asyncio.run(channel.deliver(notification)) == Delivery("delivered")
