# tests/services/test_location_preferences.py
"""Tests for per-location notification preferences, ``muted`` deliveries, and all-clear."""

from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import uuid4

import httpx
import pytest
import respx
from cli_support import FakeToast
from scenarios import (
    as_hurricane_warning,
    development_region_location,
    miami_dade,
    rebuilt,
    recorded_maps,
    rip_current,
    with_alerts,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from weatherbot.models import WGS84, AlertLevel, Geometry, LocationPreferences
from weatherbot.services.assessments import AssessmentService
from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.doctor import ntfy_check, toast_check
from weatherbot.services.events import BrowserChannel, EventHub
from weatherbot.services.locations import LocationError, LocationService
from weatherbot.services.notifications import (
    TEST_BODY,
    TEST_TITLE,
    LogChannel,
    NotificationService,
)
from weatherbot.services.ntfy import NtfyChannel
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import (
    LocationNotFoundError,
    LocationRepository,
    SnapshotRepository,
)
from weatherbot.services.persistence.tables import NotificationDeliveryRow

FAKE_TOPIC = "weatherbot-prefs-topic-123456789"
EXPECTED_CALLS_AFTER_ALL_CLEAR: Final = 2


@pytest.fixture(autouse=True)
def _prime_recorded_maps() -> None:
    recorded_maps()


def test_location_preferences_round_trip_and_unknown_location_raises() -> None:
    paths = AppPaths.resolve()
    loc = miami_dade()

    with open_database(paths) as database:
        repo = LocationRepository(database.engine)
        repo.add(loc)
        stored = repo.get(loc.name)
        assert stored is not None
        assert stored.preferences == LocationPreferences(
            toast=True,
            browser=True,
            phone=True,
            phone_min_level=2,
        )

        service = LocationService(database.engine)
        updated = service.set_preferences(
            loc.name,
            LocationPreferences(toast=False, browser=False, phone=True, phone_min_level=4),
        )
        assert updated.preferences == LocationPreferences(
            toast=False,
            browser=False,
            phone=True,
            phone_min_level=4,
        )
        reloaded = repo.get(loc.name)
        assert reloaded is not None
        assert reloaded.preferences == updated.preferences

        with pytest.raises(LocationNotFoundError):
            repo.set_preferences("Unknown Place", LocationPreferences(), now=datetime.now(UTC))

        with pytest.raises(LocationError):
            service.set_preferences("Unknown Place", LocationPreferences())


@pytest.mark.anyio
async def test_muted_channels_record_muted_without_calling_channel_and_leave_doctor_intact() -> (
    None
):
    paths = AppPaths.resolve()
    loc = miami_dade()
    settings = Settings()
    snap = with_alerts([as_hurricane_warning(rip_current())])
    t0 = snap.completed_at

    with open_database(paths) as database, respx.mock(assert_all_called=False) as router:
        ntfy_route = router.post("https://ntfy.sh/").mock(
            return_value=httpx.Response(200, json={"id": "m1"})
        )
        repo = LocationRepository(database.engine)
        repo.add(loc)
        # First store a real failed toast and delivered ntfy via a no-location test notification.
        failing_toast = FakeToast("failed", "0x80070490")
        hub = EventHub()
        browser = BrowserChannel(hub, enabled=True)
        ntfy = NtfyChannel("https://ntfy.sh", FAKE_TOPIC, None)
        channels = (LogChannel(), failing_toast, browser, ntfy)

        service = NotificationService(
            database.engine,
            settings=settings,
            now=lambda: t0,
            channels=channels,
        )
        with hub.subscribe():
            test_sent = await service.send("test", title=TEST_TITLE, body=TEST_BODY)
        assert [(d.channel, d.result) for d in test_sent.deliveries] == [
            ("log", "delivered"),
            ("toast", "failed"),
            ("browser", "delivered"),
            ("ntfy", "delivered"),
        ]
        assert ntfy_route.call_count == 1
        failing_toast.handed.clear()

        # Now turn off toast, browser, and phone for the location.
        repo.set_preferences(
            loc.name,
            LocationPreferences(toast=False, browser=False, phone=False, phone_min_level=2),
        )
        SnapshotRepository(database.engine).save(snap, ())
        assessor = AssessmentService(
            database.engine, thresholds=settings.engine.thresholds(), now=lambda: t0
        )
        assessed = assessor.assess(snap, (repo.get(loc.name) or loc,))
        (loc_sent,) = await service.decide_cycle(None, assessed)

        assert [(d.channel, d.result, d.detail) for d in loc_sent.deliveries] == [
            ("log", "delivered", None),
            ("toast", "muted", "turned off for this location"),
            ("browser", "muted", "turned off for this location"),
            ("ntfy", "muted", "turned off for this location"),
        ]
        # Neither toast nor ntfy was called for the muted location notification.
        assert failing_toast.handed == []
        assert ntfy_route.call_count == 1

        # latest_delivery skips muted rows: the earlier toast failure and ntfy success still show!
        latest_toast = service.latest_delivery("toast")
        latest_ntfy = service.latest_delivery("ntfy")
        assert latest_toast is not None
        assert latest_toast.result == "failed"
        assert latest_ntfy is not None
        assert latest_ntfy.result == "delivered"

        t_check = toast_check(latest_toast, identity=True, toast_on=True, delivered_before=True)
        n_check = ntfy_check(
            ntfy_on=True,
            environ={"WEATHERBOT_NTFY_TOPIC": FAKE_TOPIC},
            latest=latest_ntfy,
        )
        assert t_check.status == "fail"
        assert n_check.status == "pass"


@pytest.mark.anyio
async def test_phone_min_level_mutes_lower_levels_but_delivers_all_clear_after_alarm() -> None:
    paths = AppPaths.resolve()
    loc = rebuilt(
        development_region_location(),
        preferences=LocationPreferences(phone_min_level=3),
    )
    settings = Settings()

    # Snapshots for development_region_location (with phone_min_level=3):
    # 1. snap1 -> Level 2 Tropical Storm Threat (< phone_min_level=3) -> muted on ntfy.
    # 2. snap2 -> Level 5 Emergency (>= phone_min_level=3) -> delivered on ntfy!
    # 3. snap3 -> Level 1 All Clear (< phone_min_level=3), after warning expiry, with
    #    previous location notification delivered on ntfy -> all-clear IS delivered on ntfy!
    base = recorded_maps()
    t0 = base.completed_at
    t1 = t0 + timedelta(hours=2)
    t2 = t1 + timedelta(hours=2)
    snap1 = rebuilt(base, alerts={})
    hw_alert = rebuilt(
        as_hurricane_warning(rip_current()),
        geometry=Geometry(
            type="Point",
            coordinates=(loc.point.longitude, loc.point.latitude),
            crs=WGS84,
        ),
        expires=t1 + timedelta(hours=1),
    )
    snap2 = rebuilt(
        base,
        snapshot_id=uuid4(),
        started_at=t1,
        completed_at=t1,
        alerts={loc.name: (hw_alert,)},
    )
    snap3 = rebuilt(
        base,
        snapshot_id=uuid4(),
        started_at=t2,
        completed_at=t2,
        outlook_areas=(),
        storms=(),
        alerts={},
    )

    with open_database(paths) as database, respx.mock(assert_all_called=True) as router:
        ntfy_route = router.post("https://ntfy.sh/").mock(
            return_value=httpx.Response(200, json={"id": "ok"})
        )
        repo = LocationRepository(database.engine)
        repo.add(loc)
        snap_repo = SnapshotRepository(database.engine)
        for s in (snap1, snap2, snap3):
            snap_repo.save(s, ())

        ntfy = NtfyChannel("https://ntfy.sh", FAKE_TOPIC, None)
        channels = (LogChannel(), ntfy)

        # Cycle 1: level 2 -> muted on ntfy ("below this location's phone level").
        assessor1 = AssessmentService(
            database.engine, thresholds=settings.engine.thresholds(), now=lambda: snap1.completed_at
        )
        notif1 = NotificationService(
            database.engine, settings=settings, now=lambda: snap1.completed_at, channels=channels
        )
        (sent1,) = await notif1.decide_cycle(None, assessor1.assess(snap1, (loc,)))
        assert sent1.level == AlertLevel.TROPICAL_STORM_THREAT
        assert [(d.channel, d.result, d.detail) for d in sent1.deliveries] == [
            ("log", "delivered", None),
            ("ntfy", "muted", "below this location's phone level"),
        ]
        assert ntfy_route.call_count == 0

        # Cycle 2: escalates to level 5 -> delivered on ntfy!
        assessor2 = AssessmentService(
            database.engine, thresholds=settings.engine.thresholds(), now=lambda: snap2.completed_at
        )
        notif2 = NotificationService(
            database.engine, settings=settings, now=lambda: snap2.completed_at, channels=channels
        )
        (sent2,) = await notif2.decide_cycle(None, assessor2.assess(snap2, (loc,)))
        assert sent2.level == AlertLevel.HURRICANE_WARNING
        assert [(d.channel, d.result) for d in sent2.deliveries] == [
            ("log", "delivered"),
            ("ntfy", "delivered"),
        ]
        assert ntfy_route.call_count == 1

        # Cycle 3: drops from level 5 to level 1 after warning expiry -> settles immediately
        # and delivers the all-clear to ntfy even though level 1 < phone_min_level (3)!
        assessor3 = AssessmentService(
            database.engine, thresholds=settings.engine.thresholds(), now=lambda: snap3.completed_at
        )
        notif3 = NotificationService(
            database.engine, settings=settings, now=lambda: snap3.completed_at, channels=channels
        )
        (sent3,) = await notif3.decide_cycle(None, assessor3.assess(snap3, (loc,)))
        assert sent3.level == AlertLevel.ALL_CLEAR
        assert [(d.channel, d.result) for d in sent3.deliveries] == [
            ("log", "delivered"),
            ("ntfy", "delivered"),
        ]
        assert ntfy_route.call_count == EXPECTED_CALLS_AFTER_ALL_CLEAR

        with Session(database.engine) as session:
            ntfy_rows = session.scalars(
                select(NotificationDeliveryRow)
                .where(NotificationDeliveryRow.channel == "ntfy")
                .order_by(NotificationDeliveryRow.id)
            ).all()
            assert [(r.result, r.detail) for r in ntfy_rows] == [
                ("muted", "below this location's phone level"),
                ("delivered", None),
                ("delivered", None),
            ]
