# tests/services/test_retention_worker.py
"""Tests for ``next_retention_wake`` and ``RetentionWorker`` daily scheduling and heartbeats."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import httpx
from cli_support import (
    MIAMI,
    add_landmark,
    quiet_fetcher,
    recorded_services,
)
from fixture_support import register_alert
from source_support import NOW

from weatherbot.services.config import AppPaths, RetentionSettings, Settings
from weatherbot.services.health import staleness
from weatherbot.services.monitor import MonitorService
from weatherbot.services.network import Network
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import HeartbeatRepository
from weatherbot.services.retention import (
    RETENTION_HEARTBEAT_CADENCE_S,
    RetentionService,
    RetentionWorker,
    next_retention_wake,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pytest

FORECAST_ZONE_URL = "https://api.weather.gov/zones/forecast/FLZ173"
FORECAST_ALERTS_URL = "https://api.weather.gov/alerts/active/zone/FLZ173"


def test_next_retention_wake_computes_03_30_local() -> None:
    eastern = ZoneInfo("America/New_York")
    # 02:15 EDT -> same day 03:30 EDT (07:30 UTC)
    before = datetime(2026, 10, 13, 6, 15, tzinfo=UTC)
    assert next_retention_wake(before, local_zone=eastern) == datetime(
        2026, 10, 13, 7, 30, tzinfo=UTC
    )
    # 03:30 EDT exact -> next day 03:30 EDT (07:30 UTC on Oct 14)
    at_wake = datetime(2026, 10, 13, 7, 30, tzinfo=UTC)
    assert next_retention_wake(at_wake, local_zone=eastern) == datetime(
        2026, 10, 14, 7, 30, tzinfo=UTC
    )


def test_worker_clears_cadence_when_disabled_and_defers_when_location_at_watch_or_higher(  # noqa: PLR0915
    caplog: pytest.LogCaptureFixture,
) -> None:
    paths = AppPaths.resolve()
    base = NOW
    current_now = base + timedelta(days=90)

    with recorded_services() as router:
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0
        with open_database(paths) as db:
            # Seed a cycle at Day 0 (prunable) and a cycle at Day 90 with a Tropical Storm Watch
            # (Level 3) on Miami!
            monitor_day0 = MonitorService(
                db.engine,
                paths=paths,
                settings=Settings(),
                runner="check-once",
                network=Network(
                    make_fetcher=lambda client, store: quiet_fetcher(client, store, now=base)
                ),
                now=lambda: base,
            )
            asyncio.run(monitor_day0.run_cycle("manual"))

            feature = register_alert(current_now)
            props = feature["properties"]
            assert isinstance(props, dict)
            props["id"] = "urn:oid:tswatch.worker"
            props["event"] = "Tropical Storm Watch"
            props["affectedZones"] = [FORECAST_ZONE_URL]

            router.get(FORECAST_ALERTS_URL).mock(
                return_value=httpx.Response(
                    200,
                    content=json.dumps({"type": "FeatureCollection", "features": [feature]}).encode(
                        "utf-8"
                    ),
                    headers={"content-type": "application/json"},
                )
            )
            monitor_now = MonitorService(
                db.engine,
                paths=paths,
                settings=Settings(),
                runner="check-once",
                network=Network(
                    make_fetcher=lambda client, store: quiet_fetcher(client, store, now=current_now)
                ),
                now=lambda: current_now,
            )
            asyncio.run(monitor_now.run_cycle("manual"))

            enabled_settings = Settings(retention=RetentionSettings(history_days=30))
            events: list[tuple[str, object, tuple[str, ...]]] = []

            def record_publish(kind: str, data: object, inv: Sequence[str]) -> None:
                events.append((kind, data, tuple(inv)))

            worker = RetentionWorker(
                db.engine,
                paths,
                settings=enabled_settings,
                clock=lambda: current_now,
                publish=record_publish,
            )

            # 1. Because Miami is at Level 3 (>= Watch), run_once records a fresh heartbeat
            #    with expected_every_s=172800 and prunes NOTHING!
            res_deferred = asyncio.run(worker.run_once())
            assert res_deferred is None
            hb_rows = HeartbeatRepository(db.engine, now=lambda: current_now).rows()
            ret_hb = next(r for r in hb_rows if r.kind == "watch" and r.name == "retention")
            assert ret_hb.expected_every_s == RETENTION_HEARTBEAT_CADENCE_S
            assert ret_hb.last_success_at == current_now
            assert not staleness([ret_hb], current_now)[0].stale
            # After > 2 * 172800s without an update, doctor/staleness reports it stale!
            assert staleness(
                [ret_hb],
                current_now + timedelta(seconds=2 * RETENTION_HEARTBEAT_CADENCE_S + 1),
            )[0].stale

            # 2. When history_days is changed to 0, run_once clears expected_every_s so
            #    doctor never reports watch/retention stale!
            disabled_worker = RetentionWorker(
                db.engine,
                paths,
                settings=Settings(retention=RetentionSettings(history_days=0)),
                clock=lambda: current_now,
            )
            assert asyncio.run(disabled_worker.run_once()) is None
            ret_hb_cleared = next(
                r
                for r in HeartbeatRepository(db.engine, now=lambda: current_now).rows()
                if r.kind == "watch" and r.name == "retention"
            )
            assert ret_hb_cleared.expected_every_s is None
            assert not staleness(
                [ret_hb_cleared],
                current_now + timedelta(days=30),
            )[0].stale

            # 3. Drop Miami back to Level 1 -> worker plans and runs prune, records success,
            #    and publishes health/settings invalidation!
            router.get(FORECAST_ALERTS_URL).mock(
                return_value=httpx.Response(
                    200,
                    content=b'{"type":"FeatureCollection","features":[]}',
                    headers={"content-type": "application/json"},
                )
            )
            later = current_now + timedelta(minutes=15)
            monitor_clear = MonitorService(
                db.engine,
                paths=paths,
                settings=Settings(),
                runner="check-once",
                network=Network(
                    make_fetcher=lambda client, store: quiet_fetcher(client, store, now=later)
                ),
                now=lambda: later,
            )
            asyncio.run(monitor_clear.run_cycle("manual"))

            worker_active = RetentionWorker(
                db.engine,
                paths,
                settings=enabled_settings,
                clock=lambda: later,
                publish=record_publish,
                service_factory=lambda: RetentionService(
                    db.engine, paths, now=lambda: later, sleep=lambda _: None
                ),
            )
            res_pruned = asyncio.run(worker_active.run_once())
            assert res_pruned is not None
            assert res_pruned.status == "complete"
            assert res_pruned.total_deleted > 0
            assert ("health", None, ("settings", "health")) in events

            # 4. Exception inside service logs ERROR and records failure heartbeat.
            def broken_factory() -> RetentionService:
                msg = "boom"
                raise RuntimeError(msg)

            caplog.set_level(logging.ERROR, logger="weatherbot.services.retention")
            worker_broken = RetentionWorker(
                db.engine,
                paths,
                settings=enabled_settings,
                clock=lambda: later,
                service_factory=broken_factory,
            )
            assert asyncio.run(worker_broken.run_once()) is None
            ret_hb_failed = next(
                r
                for r in HeartbeatRepository(db.engine, now=lambda: later).rows()
                if r.kind == "watch" and r.name == "retention"
            )
            assert ret_hb_failed.last_error_kind == "RuntimeError"
            assert any("RuntimeError" in r.message for r in caplog.records)
