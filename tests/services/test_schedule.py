# tests/services/test_schedule.py
"""``weatherbot.services.schedule``: windows, watches, retries, confirmation, and alarms."""

import asyncio
import json
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast

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
from source_support import NOW, entry, layer_name

from weatherbot.services.config import (
    AppPaths,
    Settings,
)
from weatherbot.services.notifications import (
    Channel,
    LogChannel,
    NotificationService,
)
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import (
    CycleRepository,
)
from weatherbot.services.schedule import MonitorSchedule
from weatherbot.sources import arcgis, nhc_map

FORECAST_ZONE_URL = "https://api.weather.gov/zones/forecast/FLZ173"
FORECAST_ALERTS_URL = "https://api.weather.gov/alerts/active/zone/FLZ173"
GRAPHICS_URL = "https://www.nhc.noaa.gov/xgtwo/two_atl_2d0.png"


@dataclass
class FakeScheduleClock:
    """UTC clock for ``MonitorSchedule`` tests."""

    now: datetime = datetime(2026, 10, 13, 3, 0, tzinfo=UTC)
    sleeps: list[float] = field(default_factory=list[float])

    def __call__(self) -> datetime:
        """Return the current UTC instant."""
        return self.now

    async def sleep(self, seconds: float) -> None:
        """Advance the clock by ``seconds``."""
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)
        await asyncio.sleep(0)


class FixedJitter:
    """Returns a constant uniform jitter draw."""

    def __init__(self, seconds: float = 0.0) -> None:
        """Create a fixed jitter source."""
        self.seconds = seconds

    def uniform(self, a: float, b: float) -> float:
        """Return ``self.seconds`` clamped to ``[a, b]``."""
        return max(a, min(b, self.seconds))


def _roster_bytes(*, empty: bool = False, adv_num: str = "022", issued_at: datetime = NOW) -> bytes:
    capture = directory("nhc-current-storms")
    (item,) = capture.entries
    doc = cast("dict[str, object]", json.loads(capture.payload(item)))
    if empty:
        doc["activeStorms"] = []
    else:
        storms = cast("list[dict[str, object]]", doc["activeStorms"])
        first = storms[0]
        iso = issued_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        for key in ("publicAdvisory", "trackCone"):
            prod = cast("dict[str, object]", first[key])
            prod["advNum"] = adv_num
            prod["issuance"] = iso
    return json.dumps(doc).encode("utf-8")


def _cone_attribute_url_and_response(adv_num: str) -> tuple[str, httpx.Response]:
    capture = directory("nhc-map-tropical-summary")
    for item in capture.entries:
        if str(item["file"]).startswith("query-") and layer_name(item) == nhc_map.FORECAST_CONE:
            layer_id = int(str(item["notes"]).rsplit("id ", 1)[1])
            url = (
                f"{arcgis.TROPICAL_SUMMARY.url}/{layer_id}/query"
                "?where=1%3D1&outFields=binnumber,advisnum&returnGeometry=false&f=json"
            )
            body = json.dumps(
                {"features": [{"attributes": {"binnumber": "EP5", "advisnum": adv_num}}]}
            ).encode("utf-8")
            return url, httpx.Response(
                200, content=body, headers={"content-type": "application/json"}
            )
    message = "Forecast Cone layer not found in summary capture"
    raise AssertionError(message)


def _alert_feature(
    sent: datetime,
    *,
    alert_id: str,
    event: str,
    affected_zones: tuple[str, ...] = (FORECAST_ZONE_URL,),
) -> dict[str, object]:
    feature = register_alert(sent)
    feature["id"] = f"https://api.weather.gov/alerts/{alert_id}"
    props = cast("dict[str, object]", feature["properties"])
    props["id"] = alert_id
    props["event"] = event
    props["headline"] = f"{event} issued by NWS Miami FL"
    props["affectedZones"] = list(affected_zones)
    geocode = cast("dict[str, object]", props["geocode"])
    geocode["UGC"] = [zone.rsplit("/", 1)[-1] for zone in affected_zones]
    return feature


def _alert_response(
    *,
    alerts: list[dict[str, object]],
) -> httpx.Response:
    capture = directory("nws-alerts-zone")
    doc = cast(
        "dict[str, object]",
        json.loads(capture.payload(entry(capture, "alerts-zone-FLZ173.geojson"))),
    )
    doc["features"] = alerts
    return httpx.Response(
        200,
        content=json.dumps(doc).encode("utf-8"),
        headers={"content-type": "application/geo+json"},
    )


@contextmanager
def _make_schedule(
    clock: FakeScheduleClock,
    *,
    settings: Settings | None = None,
    jitter_s: float = 0.0,
    channels: tuple[Channel, ...] | None = None,
    run_startup: bool = False,
) -> Generator[MonitorSchedule]:
    paths = AppPaths.resolve()
    with open_database(paths) as db:
        yield MonitorSchedule(
            db.engine,
            paths,
            settings=settings or Settings(),
            clock=clock,
            sleep=clock.sleep,
            random=FixedJitter(jitter_s),
            make_fetcher=lambda client, store: quiet_fetcher(client, store, now=clock()),
            channels=channels,
            run_startup=run_startup,
        )


def test_window_opens_at_t_plus_15_with_jitter_and_runs_immediately_when_no_storms() -> None:
    t0 = datetime(2026, 10, 13, 3, 0, tzinfo=UTC)
    clock = FakeScheduleClock(t0)
    cone_url, cone_resp = _cone_attribute_url_and_response("022")

    with (
        recorded_services(
            roster=_roster_bytes(empty=True),
            overrides={cone_url: cone_resp},
        ),
        _make_schedule(clock, jitter_s=45.0, run_startup=False) as sched,
    ):
        assert sched.next_window_due(t0) == datetime(2026, 10, 13, 3, 15, tzinfo=UTC)

        # Advance to T + 15m + 45s jitter and run the window job.
        clock.now = datetime(2026, 10, 13, 3, 15, 45, tzinfo=UTC)
        asyncio.run(sched.run_window(clock.now))

        with open_database(AppPaths.resolve()) as db:
            cycles = CycleRepository(db.engine).recent(5)
        assert len(cycles) == 1
        assert cycles[0].trigger == "window"
        assert cycles[0].started_at == datetime(2026, 10, 13, 3, 15, 45, tzinfo=UTC)


def test_window_polls_when_roster_leads_or_trails_cone_and_runs_at_t_plus_60_on_timeout() -> None:
    t0 = datetime(2026, 10, 13, 3, 0, tzinfo=UTC)
    clock = FakeScheduleClock(t0)
    cone_url, cone_021 = _cone_attribute_url_and_response("021")
    _, cone_022 = _cone_attribute_url_and_response("022")
    expected_cycles = 2

    # Case 1: Roster leads (at 022 issued at 03:00), cone trails at 021 then updates to 022.
    with (
        recorded_services(
            roster=_roster_bytes(adv_num="022", issued_at=t0),
            overrides={cone_url: cone_021},
        ) as router,
        _make_schedule(clock, run_startup=False) as sched,
    ):
        clock.now = datetime(2026, 10, 13, 3, 15, tzinfo=UTC)
        asyncio.run(sched.run_window(clock.now))
        # Not agreed yet -> rescheduled 5 minutes later (03:20) with 0 jitter.
        assert sched.next_window_due(clock.now) == datetime(2026, 10, 13, 3, 20, tzinfo=UTC)
        assert sched.window_job.jitter_s == 0.0

        # Case 2: Roster trails (issued before T at 00:00) while cone is already at 022.
        router.get(ROSTER_URL).mock(
            return_value=httpx.Response(
                200,
                content=_roster_bytes(adv_num="022", issued_at=t0 - timedelta(hours=3)),
                headers={"content-type": "application/json"},
            )
        )
        router.get(cone_url).mock(return_value=cone_022)
        clock.now = datetime(2026, 10, 13, 3, 20, tzinfo=UTC)
        asyncio.run(sched.run_window(clock.now))
        assert sched.next_window_due(clock.now) == datetime(2026, 10, 13, 3, 25, tzinfo=UTC)

        # Now roster updates to issued_at = T (03:00) -> both agree!
        router.get(ROSTER_URL).mock(
            return_value=httpx.Response(
                200,
                content=_roster_bytes(adv_num="022", issued_at=t0),
                headers={"content-type": "application/json"},
            )
        )
        clock.now = datetime(2026, 10, 13, 3, 25, tzinfo=UTC)
        asyncio.run(sched.run_window(clock.now))

        with open_database(AppPaths.resolve()) as db:
            cycles = CycleRepository(db.engine).recent(5)
        assert len(cycles) == 1
        assert cycles[0].trigger == "window"
        assert cycles[0].started_at == datetime(2026, 10, 13, 3, 25, tzinfo=UTC)

        # Next window is for T2 = 06:00 UTC. Suppose they never agree until T2 + 60m (07:00).
        t2 = datetime(2026, 10, 13, 6, 0, tzinfo=UTC)
        assert sched.next_window_due(clock.now) == t2 + timedelta(minutes=15)
        for minute in (15, 20, 25, 30, 35, 40, 45, 50, 55):
            clock.now = t2 + timedelta(minutes=minute)
            asyncio.run(sched.run_window(clock.now))
        assert sched.next_window_due(clock.now) == datetime(2026, 10, 13, 7, 0, tzinfo=UTC)

        clock.now = datetime(2026, 10, 13, 7, 0, tzinfo=UTC)
        asyncio.run(sched.run_window(clock.now))

        with open_database(AppPaths.resolve()) as db:
            cycles = CycleRepository(db.engine).recent(5)
        assert len(cycles) == expected_cycles
        assert cycles[0].started_at == datetime(2026, 10, 13, 7, 0, tzinfo=UTC)


def test_roster_watch_and_alert_watch_intervals_and_change_triggers() -> None:
    clock = FakeScheduleClock(NOW)
    expected_after_roster = 2
    expected_after_alerts = 3
    with recorded_services() as router:
        add_landmark(MIAMI, "miami-dade")
        with _make_schedule(clock, run_startup=True) as sched:
            # Run startup cycle -> Miami is at level 1 (All Clear).
            asyncio.run(sched.run_startup(clock.now))

            # At level 1: roster interval is 15m, alert watch is idle (None).
            assert sched.next_roster_due(clock.now) == NOW + timedelta(minutes=15)
            assert sched.next_alerts_due(clock.now) is None

            # Advance 15m and run roster watch with unchanged roster -> no new cycle.
            clock.now = NOW + timedelta(minutes=15)
            asyncio.run(sched.run_roster(clock.now))
            with open_database(AppPaths.resolve()) as db:
                assert len(CycleRepository(db.engine).recent(10)) == 1

            # Advance 15m and serve a changed roster + Tropical Storm Watch on FLZ173 ->
            # roster watch triggers a cycle, raising Miami above level 1!
            clock.now = NOW + timedelta(minutes=30)
            router.get(ROSTER_URL).mock(
                return_value=httpx.Response(
                    200,
                    content=_roster_bytes(adv_num="023", issued_at=clock.now),
                    headers={"content-type": "application/json"},
                )
            )
            router.get(FORECAST_ALERTS_URL).mock(
                return_value=_alert_response(
                    alerts=[
                        _alert_feature(
                            clock.now,
                            alert_id="urn:oid:tswatch.1",
                            event="Tropical Storm Watch",
                            affected_zones=(FORECAST_ZONE_URL,),
                        )
                    ]
                )
            )
            asyncio.run(sched.run_roster(clock.now))

            with open_database(AppPaths.resolve()) as db:
                cycles = CycleRepository(db.engine).recent(10)
            assert len(cycles) == expected_after_roster
            assert cycles[0].trigger == "roster"

            # Now Miami is above level 1: roster watch tightens to 5m, alert watch activates at 5m!
            assert sched.next_roster_due(clock.now) == clock.now + timedelta(minutes=5)
            assert sched.next_alerts_due(clock.now) == clock.now + timedelta(minutes=5)

            # Run alert watch 5m later with identical alert id & sent -> no cycle.
            clock.now += timedelta(minutes=5)
            asyncio.run(sched.run_alerts(clock.now))
            with open_database(AppPaths.resolve()) as db:
                assert len(CycleRepository(db.engine).recent(10)) == expected_after_roster

            # Run alert watch 5m later with updated sent instant -> triggers alerts cycle!
            clock.now += timedelta(minutes=5)
            router.get(FORECAST_ALERTS_URL).mock(
                return_value=_alert_response(
                    alerts=[
                        _alert_feature(
                            clock.now,
                            alert_id="urn:oid:tswatch.1",
                            event="Hurricane Warning",
                            affected_zones=(FORECAST_ZONE_URL,),
                        )
                    ]
                )
            )
            asyncio.run(sched.run_alerts(clock.now))
            with open_database(AppPaths.resolve()) as db:
                cycles = CycleRepository(db.engine).recent(10)
            assert len(cycles) == expected_after_alerts
            assert cycles[0].trigger == "alerts"


def test_retries_5_10_20_minutes_after_ladder_failures_and_degraded_alarm_with_recovery() -> None:
    clock = FakeScheduleClock(NOW)
    toast = FakeToast(result="delivered")
    channels: tuple[Channel, ...] = (LogChannel(), toast)
    unavailable = httpx.Response(503, headers={"content-type": "text/plain"})
    expected_after_recovery = 2

    with _make_schedule(clock, channels=channels, run_startup=True) as sched:
        # 1. A non-ladder failure (graphics) schedules NO retry.
        with recorded_services(overrides={GRAPHICS_URL: unavailable}):
            add_landmark(MIAMI, "miami-dade")
            asyncio.run(sched.run_startup(clock.now))
            assert sched.next_retry_due(clock.now) is None
        toast.handed.clear()

        # 2. A ladder source failure (SUMMARY_CATALOG) schedules retries at +5m, +10m, +20m,
        #    fires one degraded alarm on the 3rd consecutive failure, stops after 3 retries,
        #    and sends a recovered notification when the source answers again.
        with recorded_services(overrides={SUMMARY_CATALOG: unavailable}) as router:
            # Failure 1 at NOW -> retry 1 due at NOW + 5m.
            asyncio.run(sched.execute_cycle("window"))
            assert sched.next_retry_due(clock.now) == NOW + timedelta(minutes=5)
            assert len(toast.handed) == 0

            # Failure 2 (retry 1) at NOW + 5m -> retry 2 due at +10m (NOW + 15m).
            clock.now = NOW + timedelta(minutes=5)
            asyncio.run(sched.run_retry(clock.now))
            assert sched.next_retry_due(clock.now) == NOW + timedelta(minutes=15)
            assert len(toast.handed) == 0

            # Failure 3 (retry 2) at NOW + 15m -> retry 3 due at +20m (NOW + 35m),
            # AND degraded alarm fires once!
            clock.now = NOW + timedelta(minutes=15)
            asyncio.run(sched.run_retry(clock.now))
            assert sched.next_retry_due(clock.now) == NOW + timedelta(minutes=35)
            assert len(toast.handed) == 1
            assert toast.handed[0].kind == "degraded"
            assert (
                "Weatherbot: nhc-map-tropical-summary failed 3 times in a row since "
                "2026-10-13T01:30:00Z; levels may read as floors."
            ) in toast.handed[0].title

            # Failure 4 (retry 3) at NOW + 35m -> retry_count (3) reached, so no 4th retry,
            # and no second degraded alarm!
            clock.now = NOW + timedelta(minutes=35)
            asyncio.run(sched.run_retry(clock.now))
            assert sched.next_retry_due(clock.now) is None
            assert len(toast.handed) == 1

            # Recovery: restore SUMMARY_CATALOG and run a cycle -> recovered notification sent,
            # and retry counter resets so a subsequent failure starts at +5m again.
            capture = directory("nhc-map-tropical-summary")
            catalog_body = capture.payload(entry(capture, "catalog.json"))
            router.get(SUMMARY_CATALOG).mock(return_value=httpx.Response(200, content=catalog_body))
            clock.now = NOW + timedelta(minutes=45)
            asyncio.run(sched.execute_cycle("window"))
            assert len(toast.handed) == expected_after_recovery
            assert toast.handed[1].kind == "recovered"
            assert "nhc-map-tropical-summary recovered" in toast.handed[1].title


def test_held_drop_schedules_and_runs_confirmation_cycle_at_confirm_at() -> None:
    clock = FakeScheduleClock(NOW)
    toast = FakeToast(result="delivered")
    channels: tuple[Channel, ...] = (LogChannel(), toast)

    with recorded_services() as router:
        add_landmark(MIAMI, "miami-dade")
        with _make_schedule(clock, channels=channels, run_startup=False) as sched:
            # Cycle 1: Hurricane Warning on FLZ173 -> Miami escalates to level 5.
            router.get(FORECAST_ALERTS_URL).mock(
                return_value=_alert_response(
                    alerts=[
                        _alert_feature(
                            clock.now,
                            alert_id="urn:oid:hw.1",
                            event="Hurricane Warning",
                            affected_zones=(FORECAST_ZONE_URL,),
                        )
                    ]
                )
            )
            asyncio.run(sched.execute_cycle("startup"))
            assert sched.next_confirm_due(clock.now) is None

            # Cycle 2 (10m later): alert disappears before its expiry with no new advisory ->
            # policy holds the drop and sets confirm_at = clock.now + 5m.
            clock.now = NOW + timedelta(minutes=10)
            router.get(FORECAST_ALERTS_URL).mock(return_value=_alert_response(alerts=[]))
            result = asyncio.run(sched.execute_cycle("alerts"))
            expected_confirm = clock.now + timedelta(minutes=5)
            assert result.confirm_at == expected_confirm
            assert sched.next_confirm_due(clock.now) == expected_confirm

            # At confirm_at, the confirm job runs a "confirm" cycle and settles the drop.
            clock.now = expected_confirm
            asyncio.run(sched.run_confirm(clock.now))
            assert sched.next_confirm_due(clock.now) is None

            with open_database(AppPaths.resolve()) as db:
                cycles = CycleRepository(db.engine).recent(5)
                notifications = NotificationService(db.engine).recent(10)
            assert cycles[0].trigger == "confirm"
            assert any("fell" in n.title.lower() or n.level == 1 for n in notifications)
