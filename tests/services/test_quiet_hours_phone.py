# tests/services/test_quiet_hours_phone.py
"""Tests that quiet hours hold a level-2 repeat and pass an escalation through ``NtfyChannel``."""

from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import uuid4

import httpx
import pytest
import respx
from scenarios import (
    as_hurricane_warning,
    development_region_location,
    rebuilt,
    recorded_maps,
    rip_current,
)

from weatherbot.models import WGS84, AlertLevel, Geometry
from weatherbot.services.assessments import AssessmentService
from weatherbot.services.config import AppPaths, NotificationSettings, Settings
from weatherbot.services.notifications import LogChannel, NotificationService
from weatherbot.services.ntfy import NtfyChannel
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import LocationRepository, SnapshotRepository

FAKE_TOPIC = "weatherbot-quiet-hours-topic-123456"
EXPECTED_CALLS_AFTER_ESCALATION: Final = 2


@pytest.fixture(autouse=True)
def _prime_recorded_maps() -> None:
    recorded_maps()


@pytest.mark.anyio
async def test_quiet_hours_hold_level_2_repeat_and_pass_escalation_to_ntfy() -> None:
    paths = AppPaths.resolve()
    # Phase 3's level-2 scenario: development_region_location() on recorded_maps().
    loc = development_region_location()
    # Configure quiet hours covering 22:00..07:00 UTC and a 1-hour cooldown.
    settings = Settings(
        notifications=NotificationSettings(
            ntfy=True,
            cooldown_hours=1,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            quiet_hours_time_zone="UTC",
        )
    )
    # t0 = 14:00 UTC (outside quiet hours): initial level-2 assessment (Development Region).
    t0 = datetime(2026, 10, 13, 14, 0, tzinfo=UTC)
    base_snap = recorded_maps()
    snap1 = rebuilt(
        base_snap,
        snapshot_id=uuid4(),
        started_at=t0,
        completed_at=t0,
        alerts={},
    )
    # t_quiet = 23:30 UTC (inside quiet hours, > 1h after t0):
    # A new advisory on EP5 while still at level 2 -> inside quiet hours, a level-2
    # non-escalation notification has include_toast=False (or quiet_hours decision) so
    # interrupting channels (ntfy) are NOT called!
    t_quiet = datetime(2026, 10, 13, 23, 30, tzinfo=UTC)
    ep5 = base_snap.storms[0]
    assert ep5.cone is not None
    new_adv = rebuilt(
        ep5.cone.advisory,
        number=ep5.cone.advisory.number.parse("23"),
        issued_at=t_quiet - timedelta(minutes=15),
    )
    new_ep5 = rebuilt(ep5, cone=rebuilt(ep5.cone, advisory=new_adv))
    snap2_repeat_in_quiet = rebuilt(
        base_snap,
        snapshot_id=uuid4(),
        started_at=t_quiet,
        completed_at=t_quiet,
        storms=(new_ep5, *base_snap.storms[1:]),
        alerts={},
    )
    # At the same quiet-hours window (23:35 UTC): an escalation to level 5 (Hurricane Warning
    # covering the location's point) bypasses quiet hours and reaches ntfy!
    t_quiet_esc = datetime(2026, 10, 13, 23, 35, tzinfo=UTC)
    hw_alert = rebuilt(
        as_hurricane_warning(rip_current()),
        geometry=Geometry(
            type="Point",
            coordinates=(loc.point.longitude, loc.point.latitude),
            crs=WGS84,
        ),
    )
    snap3_escalation_in_quiet = rebuilt(
        snap2_repeat_in_quiet,
        snapshot_id=uuid4(),
        started_at=t_quiet_esc,
        completed_at=t_quiet_esc,
        alerts={loc.name: (hw_alert,)},
    )

    with open_database(paths) as database, respx.mock(assert_all_called=True) as router:
        ntfy_route = router.post("https://ntfy.sh/").mock(
            return_value=httpx.Response(200, json={"id": "q1"})
        )
        LocationRepository(database.engine).add(loc)
        repo = SnapshotRepository(database.engine)
        for s in (snap1, snap2_repeat_in_quiet, snap3_escalation_in_quiet):
            repo.save(s, ())

        ntfy = NtfyChannel("https://ntfy.sh", FAKE_TOPIC, None)
        channels = (LogChannel(), ntfy)

        # Cycle 1 (14:00 UTC): initial level-2 announcement -> delivered to ntfy.
        assessor1 = AssessmentService(
            database.engine, thresholds=settings.engine.thresholds(), now=lambda: t0
        )
        notif1 = NotificationService(
            database.engine, settings=settings, now=lambda: t0, channels=channels
        )
        out1 = await notif1.decide_cycle(None, assessor1.assess(snap1, (loc,)))
        assert len(out1) == 1
        assert out1[0].level == AlertLevel.TROPICAL_STORM_THREAT
        assert ntfy_route.call_count == 1

        # Cycle 2 (23:30 UTC, inside quiet hours): advisory change at level 2 -> suppressed by
        # quiet hours, sends nothing to ntfy!
        assessor2 = AssessmentService(
            database.engine, thresholds=settings.engine.thresholds(), now=lambda: t_quiet
        )
        notif2 = NotificationService(
            database.engine, settings=settings, now=lambda: t_quiet, channels=channels
        )
        out2 = await notif2.decide_cycle(None, assessor2.assess(snap2_repeat_in_quiet, (loc,)))
        assert out2 == ()
        assert ntfy_route.call_count == 1

        # Cycle 3 (23:35 UTC, inside quiet hours): escalation to level 5 -> reaches ntfy!
        assessor3 = AssessmentService(
            database.engine, thresholds=settings.engine.thresholds(), now=lambda: t_quiet_esc
        )
        notif3 = NotificationService(
            database.engine, settings=settings, now=lambda: t_quiet_esc, channels=channels
        )
        out3 = await notif3.decide_cycle(None, assessor3.assess(snap3_escalation_in_quiet, (loc,)))
        assert len(out3) == 1
        assert out3[0].escalation is True
        assert out3[0].level == AlertLevel.HURRICANE_WARNING
        assert [(d.channel, d.result) for d in out3[0].deliveries] == [
            ("log", "delivered"),
            ("ntfy", "delivered"),
        ]
        assert ntfy_route.call_count == EXPECTED_CALLS_AFTER_ESCALATION
