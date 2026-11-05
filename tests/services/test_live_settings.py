# tests/services/test_live_settings.py
"""Tests for ``LiveSettings`` reload across cycles and alarms."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import httpx
from cli_support import (
    MIAMI,
    ROSTER_URL,
    SUMMARY_CATALOG,
    FakeToast,
    add_landmark,
    directory,
    quiet_fetcher,
    recorded_services,
)
from fixture_support import register_alert
from source_support import NOW
from sqlalchemy import select
from sqlalchemy.orm import Session

from weatherbot.services.config import AppPaths, LiveSettings, load_settings
from weatherbot.services.notifications import Channel, LogChannel, NotificationService
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import HeartbeatRepository
from weatherbot.services.persistence.tables import NotificationDecisionRow
from weatherbot.services.schedule import MonitorSchedule, run_heartbeat_task

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

FORECAST_ZONE_URL = "https://api.weather.gov/zones/forecast/FLZ173"
FORECAST_ALERTS_URL = "https://api.weather.gov/alerts/active/zone/FLZ173"


@dataclass
class FakeClock:
    """Controllable UTC clock for ``MonitorSchedule``."""

    now: datetime = NOW
    sleeps: list[float] = field(default_factory=list[float])

    def __call__(self) -> datetime:
        """Return the current UTC instant."""
        return self.now

    async def sleep(self, seconds: float) -> None:
        """Advance the clock."""
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)
        await asyncio.sleep(0)


class ZeroJitter:
    """Zero uniform jitter."""

    def uniform(self, a: float, b: float) -> float:  # noqa: ARG002
        """Return 0.0."""
        return 0.0


def _roster_bytes(adv_num: str, issued_at: datetime) -> bytes:
    capture = directory("nhc-current-storms")
    (item,) = capture.entries
    doc = cast("dict[str, object]", json.loads(capture.payload(item)))
    storms = cast("list[dict[str, object]]", doc["activeStorms"])
    first = storms[0]
    iso = issued_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for key in ("publicAdvisory", "trackCone"):
        prod = cast("dict[str, object]", first[key])
        prod["advNum"] = adv_num
        prod["issuance"] = iso
    return json.dumps(doc).encode("utf-8")


def _alert_response(sent: datetime, *, include_watch: bool) -> httpx.Response:
    features: list[dict[str, object]] = []
    if include_watch:
        feature = register_alert(sent)
        props = cast("dict[str, object]", feature["properties"])
        props["id"] = "urn:oid:tsw.live.1"
        props["event"] = "Tropical Storm Watch"
        props["affectedZones"] = [FORECAST_ZONE_URL]
        features.append(feature)
    body = json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8")
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def test_live_settings_reloads_and_logs_one_warning_when_file_stops_parsing(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = AppPaths.resolve()
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.settings_path.write_text("[retention]\nhistory_days = 90\n", encoding="utf-8")

    started = load_settings(paths, {})
    live = LiveSettings(paths, environ={}, first=started)
    assert live().retention.history_days == 90  # noqa: PLR2004

    paths.settings_path.write_text(
        '[notifications]\nquiet_hours_start = "22:00"\nquiet_hours_end = "07:00"\n'
        "[retention]\nhistory_days = 180\n",
        encoding="utf-8",
    )
    updated = live()
    assert updated.retention.history_days == 180  # noqa: PLR2004
    assert updated.notifications.quiet_hours_start == "22:00"

    # Invalid TOML keeps the last good Settings and logs only one WARNING across calls.
    caplog.set_level(logging.WARNING, logger="weatherbot.services.config")
    caplog.clear()
    paths.settings_path.write_text("[retention]\nhistory_days = not_toml\n", encoding="utf-8")
    assert live() == updated
    assert live() == updated
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1

    # Invalid UTF-8 also keeps the last good Settings without spamming a second warning.
    paths.settings_path.write_bytes(b"\xff\xfe\x00\x00")
    assert live() == updated
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1

    # Restore valid TOML -> reloads cleanly and clears warning latch.
    paths.settings_path.write_text("[retention]\nhistory_days = 365\n", encoding="utf-8")
    recovered = live()
    assert recovered.retention.history_days == 365  # noqa: PLR2004

    # OSError on read_text after recovery logs one new warning and returns recovered.
    def fail_read(_self: Path, **_kwargs: object) -> str:
        msg = "locked"
        raise PermissionError(msg)

    monkeypatch.setattr(type(paths.settings_path), "read_text", fail_read)
    assert live() == recovered
    assert live() == recovered
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2  # noqa: PLR2004


def test_quiet_hours_change_between_cycles_decides_second_cycle_and_degraded_alarm() -> None:
    clock = FakeClock(NOW)
    toast = FakeToast(result="delivered")
    channels: tuple[Channel, ...] = (LogChannel(), toast)
    paths = AppPaths.resolve()
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    started = load_settings(paths, {})
    live = LiveSettings(paths, environ={}, first=started)

    with recorded_services() as router:
        add_landmark(MIAMI, "miami-dade")
        with open_database(paths) as db:
            sched = MonitorSchedule(
                db.engine,
                paths,
                settings=started,
                live_settings=live,
                clock=clock,
                sleep=clock.sleep,
                random=ZeroJitter(),
                make_fetcher=lambda client, store: quiet_fetcher(client, store, now=clock()),
                channels=channels,
                run_startup=False,
            )

            # Cycle 1: Tropical Storm Watch on FLZ173 -> Miami escalates to level 3 (sent).
            router.get(FORECAST_ALERTS_URL).mock(
                return_value=_alert_response(clock.now, include_watch=True)
            )
            asyncio.run(sched.execute_cycle("startup"))
            assert len(toast.handed) == 1
            assert toast.handed[0].level == 3  # noqa: PLR2004

            # Between Cycle 1 and Cycle 2, write quiet hours covering 00:00..24:00 UTC.
            paths.settings_path.write_text(
                '[notifications]\nquiet_hours_start = "00:00"\n'
                'quiet_hours_end = "24:00"\n'
                'quiet_hours_time_zone = "UTC"\n',
                encoding="utf-8",
            )

            # Cycle 2: watch cleared AND new NHC advisory issued -> drop to level 1 is
            # confirmed immediately, and quiet hours hold the level-1 notification!
            clock.now = NOW + timedelta(minutes=15)
            router.get(FORECAST_ALERTS_URL).mock(
                return_value=_alert_response(clock.now, include_watch=False)
            )
            router.get(ROSTER_URL).mock(
                return_value=httpx.Response(
                    200,
                    content=_roster_bytes("023", clock.now),
                    headers={"content-type": "application/json"},
                )
            )
            asyncio.run(sched.execute_cycle("window"))

            with Session(db.engine) as session:
                decisions = list(
                    session.scalars(
                        select(NotificationDecisionRow).where(
                            NotificationDecisionRow.trigger == "level",
                            NotificationDecisionRow.level_after == 1,
                        )
                    )
                )
            assert len(decisions) == 1
            assert decisions[0].decision == "quiet_hours"
            assert len(toast.handed) == 1

            # Now fail a ladder source 3 times -> degraded alarm reads the live quiet hours
            # and holds interrupting channels (toast) while logging to LogChannel!
            router.get(SUMMARY_CATALOG).mock(
                return_value=httpx.Response(503, headers={"content-type": "text/plain"})
            )
            clock.now += timedelta(minutes=5)
            asyncio.run(sched.execute_cycle("window"))
            clock.now += timedelta(minutes=5)
            asyncio.run(sched.run_retry(clock.now))
            clock.now += timedelta(minutes=10)
            asyncio.run(sched.run_retry(clock.now))

            alarms = [n for n in NotificationService(db.engine).recent(10) if n.kind == "degraded"]
            assert len(alarms) == 1
            assert [d.channel for d in alarms[0].deliveries] == ["log"]
            assert len(toast.handed) == 1


def test_stale_alarm_in_heartbeat_task_reads_live_quiet_hours() -> None:
    clock = FakeClock(NOW)
    toast = FakeToast(result="delivered")
    channels: tuple[Channel, ...] = (LogChannel(), toast)
    paths = AppPaths.resolve()
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    started = load_settings(paths, {})
    live = LiveSettings(paths, environ={}, first=started)

    with open_database(paths) as db:
        HeartbeatRepository(db.engine, now=clock).record(
            "runner",
            "fallback",
            at=NOW - timedelta(hours=3),
            result="success",
            expected_every_s=900,
        )
        # Enable all-day quiet hours in weatherbot.toml after startup.
        paths.settings_path.write_text(
            '[notifications]\nquiet_hours_start = "00:00"\n'
            'quiet_hours_end = "24:00"\n'
            'quiet_hours_time_zone = "UTC"\n',
            encoding="utf-8",
        )
        stop = asyncio.Event()

        async def sleep_then_stop(seconds: float) -> None:
            clock.now += timedelta(seconds=seconds)
            stop.set()

        asyncio.run(
            run_heartbeat_task(
                db.engine,
                "serve",
                heartbeat_minutes=started.monitor.heartbeat_minutes,
                stop=stop,
                clock=clock,
                sleep=sleep_then_stop,
                settings=started,
                live_settings=live,
                channels=channels,
                check_installed=True,
            )
        )

        stale_rows = [
            n for n in NotificationService(db.engine).recent(10) if n.kind == "stale_monitor"
        ]
        assert len(stale_rows) == 1
        assert [d.channel for d in stale_rows[0].deliveries] == ["log"]
        assert toast.handed == []
