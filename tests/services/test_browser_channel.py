# tests/services/test_browser_channel.py
"""Tests for ``BrowserChannel``, ``serve_channels``, and quiet-hours ``interrupts`` holding."""

import asyncio

import pytest
from cli_support import FakeToast, runtime
from source_support import NOW

from weatherbot.cli.runtime import Context
from weatherbot.cli.serve import serve_channels
from weatherbot.services.config import AppPaths, NotificationSettings, Settings
from weatherbot.services.events import (
    BROWSER_OFF,
    NO_OPEN_DASHBOARD,
    BrowserChannel,
    EventHub,
)
from weatherbot.services.notifications import (
    CHANNEL_NAMES,
    TEST_BODY,
    TEST_TITLE,
    LogChannel,
    NotificationService,
)
from weatherbot.services.persistence.database import open_database


@pytest.mark.anyio
async def test_browser_channel_delivered_unavailable_and_disabled() -> None:
    paths = AppPaths.resolve()
    loop = asyncio.get_running_loop()
    hub = EventHub(loop, now=lambda: NOW)

    with open_database(paths, now=lambda: NOW) as database:
        # 1. Unavailable when no dashboard subscriber is connected.
        service_no_sub = NotificationService(
            database.engine,
            settings=Settings(),
            now=lambda: NOW,
            channels=(LogChannel(), BrowserChannel(hub, enabled=True)),
        )
        sent_unavail = await service_no_sub.send("test", title=TEST_TITLE, body=TEST_BODY)
        browser_unavail = next(d for d in sent_unavail.deliveries if d.channel == "browser")
        assert browser_unavail.result == "unavailable"
        assert browser_unavail.detail == NO_OPEN_DASHBOARD

        # 2. Delivered when two dashboards are subscribed, emitting `display=True`.
        sub_1 = hub.subscribe()
        sub_2 = hub.subscribe()
        sent_ok = await service_no_sub.send("test", title=TEST_TITLE, body=TEST_BODY)
        browser_ok = next(d for d in sent_ok.deliveries if d.channel == "browser")
        assert browser_ok.result == "delivered"
        assert browser_ok.detail == "to 2 open dashboards"

        ev_1 = await asyncio.wait_for(anext(sub_1), timeout=1.0)
        ev_2 = await asyncio.wait_for(anext(sub_2), timeout=1.0)
        for ev in (ev_1, ev_2):
            assert ev.kind == "notification"
            assert ev.notification_id == sent_ok.id
            assert ev.notification_kind == "test"
            assert ev.title == TEST_TITLE
            assert ev.body == TEST_BODY
            assert ev.display is True
            assert ev.invalidate == ("notifications", "timeline")

        # 3. Disabled when `[notifications] browser = false`.
        service_disabled = NotificationService(
            database.engine,
            settings=Settings(notifications=NotificationSettings(browser=False)),
            now=lambda: NOW,
            channels=(LogChannel(), BrowserChannel(hub, enabled=False)),
        )
        sent_disabled = await service_disabled.send("test", title=TEST_TITLE, body=TEST_BODY)
        browser_disabled = next(d for d in sent_disabled.deliveries if d.channel == "browser")
        assert browser_disabled.result == "disabled"
        assert browser_disabled.detail == BROWSER_OFF
        assert not sub_1.has_pending

        sub_1.close()
        sub_2.close()


def test_serve_channels_include_browser_while_context_channels_do_not() -> None:
    assert "browser" in CHANNEL_NAMES
    paths = AppPaths.resolve()
    rt = runtime()
    ctx = Context(runtime=rt, paths=paths, settings=Settings())
    assert [c.name for c in ctx.channels] == ["log", "toast"]

    hub = EventHub(now=lambda: NOW)
    combined = serve_channels(ctx, hub)
    assert [c.name for c in combined] == ["log", "toast", "browser"]


@pytest.mark.anyio
async def test_quiet_hours_hold_drops_both_toast_and_browser_keeping_only_log() -> None:
    paths = AppPaths.resolve()
    loop = asyncio.get_running_loop()
    hub = EventHub(loop, now=lambda: NOW)
    sub = hub.subscribe()
    toast = FakeToast("delivered")
    browser = BrowserChannel(hub, enabled=True)
    log = LogChannel()

    assert log.interrupts is False
    assert toast.interrupts is True
    assert browser.interrupts is True

    with open_database(paths, now=lambda: NOW) as database:
        service = NotificationService(
            database.engine,
            settings=Settings(),
            now=lambda: NOW,
            channels=(log, toast, browser),
        )
        sent = await service.send(
            "degraded",
            title="Weatherbot: source degraded.",
            body=("Weatherbot: source degraded.",),
            include_toast=False,
        )
        assert [(d.channel, d.result) for d in sent.deliveries] == [("log", "delivered")]
        assert toast.handed == []
        assert not sub.has_pending

    sub.close()
