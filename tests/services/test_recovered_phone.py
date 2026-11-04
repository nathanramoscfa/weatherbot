# tests/services/test_recovered_phone.py
"""Tests that ``MonitorSchedule`` delivers a ``recovered`` notice to ``ntfy`` when toast is off."""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Final, cast

import httpx
from cli_support import (
    MIAMI,
    SUMMARY_CATALOG,
    FakeToast,
    add_landmark,
    directory,
    quiet_fetcher,
    recorded_services,
)
from source_support import NOW, entry

from weatherbot.services.config import AppPaths, NotificationSettings, Settings
from weatherbot.services.notifications import Channel, LogChannel
from weatherbot.services.ntfy import NtfyChannel
from weatherbot.services.persistence.database import open_database
from weatherbot.services.schedule import MonitorSchedule

FAKE_TOPIC = "weatherbot-recovered-topic-123456"
EXPECTED_NTFY_CALLS: Final = 2


class _Clock:
    def __init__(self, initial: datetime) -> None:
        self.now = initial

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def test_degraded_alarm_delivered_only_to_ntfy_still_sends_recovered_to_ntfy() -> None:
    clock = _Clock(NOW)
    toast = FakeToast(result="disabled", detail="turned off by [notifications] toast")
    ntfy = NtfyChannel("https://ntfy.sh", FAKE_TOPIC, None)
    channels: tuple[Channel, ...] = (LogChannel(), toast, ntfy)
    settings = Settings(notifications=NotificationSettings(toast=False, ntfy=True))
    unavailable = httpx.Response(503, headers={"content-type": "text/plain"})
    paths = AppPaths.resolve()
    titles: list[str] = []

    def _capture_ntfy(request: httpx.Request) -> httpx.Response:
        titles.append(cast("str", json.loads(request.content.decode("utf-8"))["title"]))
        return httpx.Response(200, json={"id": "ok"})

    with (
        open_database(paths) as db,
        recorded_services(overrides={SUMMARY_CATALOG: unavailable}) as router,
    ):
        add_landmark(MIAMI, "miami-dade")
        ntfy_route = router.post("https://ntfy.sh/").mock(side_effect=_capture_ntfy)
        sched = MonitorSchedule(
            db.engine,
            paths,
            settings=settings,
            clock=clock,
            sleep=clock.sleep,
            make_fetcher=lambda client, store: quiet_fetcher(client, store, now=clock()),
            channels=channels,
            run_startup=False,
        )

        # 3 consecutive failures on SUMMARY_CATALOG trigger the degraded alarm on ntfy.
        asyncio.run(sched.execute_cycle("window"))
        clock.now = NOW + timedelta(minutes=5)
        asyncio.run(sched.run_retry(clock.now))
        clock.now = NOW + timedelta(minutes=15)
        asyncio.run(sched.run_retry(clock.now))

        # Restore SUMMARY_CATALOG and run a cycle -> recovered must also be delivered to ntfy!
        capture = directory("nhc-map-tropical-summary")
        catalog_body = capture.payload(entry(capture, "catalog.json"))
        router.get(SUMMARY_CATALOG).mock(return_value=httpx.Response(200, content=catalog_body))
        clock.now = NOW + timedelta(minutes=45)
        asyncio.run(sched.execute_cycle("window"))

        assert ntfy_route.call_count >= EXPECTED_NTFY_CALLS
        assert any("failed 3 times in a row" in title for title in titles)
        assert any("nhc-map-tropical-summary recovered" in title for title in titles)
