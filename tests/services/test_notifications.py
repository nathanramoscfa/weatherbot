# tests/services/test_notifications.py
"""Tests for ``NotificationService``, cycle wiring, and ``check --once`` notifications."""

from datetime import timedelta
from uuid import uuid4

import anyio
import httpx
import pytest
from cli_support import (
    MIAMI,
    SUMMARY_CATALOG,
    FakeToast,
    add_landmark,
    recorded_services,
    run,
    runtime,
)
from scenarios import (
    alerts_failed,
    as_hurricane_warning,
    miami_dade,
    rebuilt,
    rip_current,
    with_alerts,
)
from snapshot_support import recorded_snapshot
from source_support import NOW
from sqlalchemy import select
from sqlalchemy.orm import Session

from weatherbot.services.assessments import AssessmentService
from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.locations import LocationService
from weatherbot.services.monitor import MonitorService
from weatherbot.services.notifications import LogChannel, NotificationService
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import LocationRepository, SnapshotRepository
from weatherbot.services.persistence.tables import (
    NotificationDecisionRow,
    NotificationDeliveryRow,
    NotificationRow,
)
from weatherbot.services.policy import PolicyState, decide

UNAVAILABLE_HTTP = 503


@pytest.mark.anyio
async def test_cycle_stores_decisions_notification_and_log_delivery_and_rerun_decides_nothing() -> (
    None
):
    paths = AppPaths.resolve()
    recorded = await recorded_snapshot()
    settings = Settings()

    with open_database(paths) as database:
        LocationRepository(database.engine).add(recorded.location)
        SnapshotRepository(database.engine).save(recorded.snapshot, recorded.responses)
        monitor = MonitorService(
            database.engine,
            paths=paths,
            settings=settings,
            runner="status",
            now=lambda: recorded.snapshot.completed_at,
        )
        first = await monitor.run_cycle("manual", snapshot=recorded.snapshot, assess=True)
        assert len(first.notifications) == 1
        notif = first.notifications[0]
        assert notif.location_name == recorded.location.name
        assert notif.kind == "location"
        assert len(notif.deliveries) == 1
        assert (notif.deliveries[0].channel, notif.deliveries[0].result) == ("log", "delivered")
        assert len(notif.decisions) >= 1

        with Session(database.engine) as session:
            decisions_count = len(session.scalars(select(NotificationDecisionRow)).all())
            notifications_count = len(session.scalars(select(NotificationRow)).all())
            deliveries_count = len(session.scalars(select(NotificationDeliveryRow)).all())
        assert decisions_count == len(notif.decisions)
        assert notifications_count == 1
        assert deliveries_count == 1

        # Rerun over the same snapshot: created is False, so nothing is decided again.
        second = await monitor.run_cycle("manual", snapshot=recorded.snapshot, assess=True)
        assert second.notifications == ()
        with Session(database.engine) as session:
            assert len(session.scalars(select(NotificationDecisionRow)).all()) == decisions_count
            assert len(session.scalars(select(NotificationRow)).all()) == notifications_count
            assert len(session.scalars(select(NotificationDeliveryRow)).all()) == deliveries_count

        # Calling decide_cycle directly on an already-decided assessment is a no-op.
        service = NotificationService(
            database.engine, settings=settings, now=lambda: recorded.snapshot.completed_at
        )
        direct = await service.decide_cycle(first.cycle_id, first.assessed)
        assert direct == ()
        assert len(service.recent(limit=5)) == 1
        with pytest.raises(ValueError, match="limit must be at least 1"):
            service.recent(limit=0)


@pytest.mark.anyio
async def test_a_notification_through_the_log_and_a_fake_toast_stores_both_deliveries() -> None:
    paths = AppPaths.resolve()
    recorded = await recorded_snapshot()
    toast = FakeToast("failed", "0x80070490")

    with open_database(paths) as database:
        LocationRepository(database.engine).add(recorded.location)
        SnapshotRepository(database.engine).save(recorded.snapshot, recorded.responses)
        monitor = MonitorService(
            database.engine,
            paths=paths,
            settings=Settings(),
            runner="status",
            now=lambda: recorded.snapshot.completed_at,
            channels=(LogChannel(), toast),
        )
        result = await monitor.run_cycle("manual", snapshot=recorded.snapshot, assess=True)
        with Session(database.engine) as session:
            rows = session.scalars(
                select(NotificationDeliveryRow).order_by(NotificationDeliveryRow.id)
            ).all()
            stored = [(row.channel, row.result, row.detail) for row in rows]

    (notification,) = result.notifications
    expected = [("log", "delivered", None), ("toast", "failed", "0x80070490")]
    assert [(d.channel, d.result, d.detail) for d in notification.deliveries] == expected
    assert stored == expected
    assert [item.id for item in toast.handed] == [notification.id]


@pytest.mark.anyio
async def test_removing_a_location_cascades_to_its_notifications_decisions_and_deliveries() -> None:
    paths = AppPaths.resolve()
    recorded = await recorded_snapshot()
    settings = Settings()

    with open_database(paths) as database:
        LocationRepository(database.engine).add(recorded.location)
        SnapshotRepository(database.engine).save(recorded.snapshot, recorded.responses)
        monitor = MonitorService(
            database.engine,
            paths=paths,
            settings=settings,
            runner="status",
            now=lambda: recorded.snapshot.completed_at,
        )
        result = await monitor.run_cycle("manual", snapshot=recorded.snapshot, assess=True)
        assert len(result.notifications) == 1

        LocationService(database.engine).remove(recorded.location.name)
        with Session(database.engine) as session:
            assert session.scalars(select(NotificationRow)).all() == []
            assert session.scalars(select(NotificationDecisionRow)).all() == []
            assert session.scalars(select(NotificationDeliveryRow)).all() == []


def test_state_reconstructs_held_drop_and_confirm_at_across_stored_cycles() -> None:
    paths = AppPaths.resolve()
    loc = miami_dade()
    settings = Settings()
    snap_high = with_alerts([as_hurricane_warning(rip_current())])
    t0 = snap_high.completed_at
    snap_failed = rebuilt(
        alerts_failed(),
        snapshot_id=uuid4(),
        started_at=t0 + timedelta(minutes=15),
        completed_at=t0 + timedelta(minutes=15),
    )
    snap_recovered = rebuilt(
        snap_high,
        snapshot_id=uuid4(),
        started_at=t0 + timedelta(minutes=20),
        completed_at=t0 + timedelta(minutes=20),
    )

    async def _run() -> None:
        with open_database(paths) as database:
            LocationRepository(database.engine).add(loc)
            repo = SnapshotRepository(database.engine)
            repo.save(snap_high, ())
            repo.save(snap_failed, ())
            repo.save(snap_recovered, ())

            assessor = AssessmentService(
                database.engine, thresholds=settings.engine.thresholds(), now=lambda: t0
            )
            notifier1 = NotificationService(database.engine, settings=settings, now=lambda: t0)
            out1 = await notifier1.decide_cycle(None, assessor.assess(snap_high, (loc,)))
            assert len(out1) == 1
            assert out1[0].escalation is True
            assert notifier1.confirm_at is None

            # Second cycle: NWS alert sources fail -> drop held, confirm_at set.
            t1 = snap_failed.completed_at
            notifier2 = NotificationService(database.engine, settings=settings, now=lambda: t1)
            out2 = await notifier2.decide_cycle(None, assessor.assess(snap_failed, (loc,)))
            assert out2 == ()
            assert notifier2.confirm_at == t1 + timedelta(minutes=5)

            # Third cycle: NWS alert sources recover at level 5 -> held drop withdrawn!
            t2 = snap_recovered.completed_at
            notifier3 = NotificationService(database.engine, settings=settings, now=lambda: t2)
            out3 = await notifier3.decide_cycle(None, assessor.assess(snap_recovered, (loc,)))
            assert out3 == ()
            assert notifier3.confirm_at is None

    anyio.run(_run)


type DecisionRow = tuple[str, int, str | None, str, int | None]


def test_stored_state_decides_as_the_in_memory_policy_across_holds_and_a_cooldown() -> None:
    paths = AppPaths.resolve()
    loc = miami_dade()
    settings = Settings()
    snap_high = with_alerts([as_hurricane_warning(rip_current())])
    t0 = snap_high.completed_at
    # Level 5; the NWS alerts fail four times (three holds, then the "at least" drop); the
    # warning returns inside the cooldown of its first official_added.
    later = (alerts_failed(),) * 4 + (snap_high,)
    snapshots = [snap_high] + [
        rebuilt(
            source,
            snapshot_id=uuid4(),
            started_at=t0 + timedelta(minutes=5 * index),
            completed_at=t0 + timedelta(minutes=5 * index),
        )
        for index, source in enumerate(later, start=1)
    ]
    stored: list[tuple[DecisionRow, ...]] = []
    expected: list[tuple[DecisionRow, ...]] = []

    async def _run() -> None:
        with open_database(paths) as database:
            LocationRepository(database.engine).add(loc)
            repo = SnapshotRepository(database.engine)
            for snap in snapshots:
                repo.save(snap, ())
            assessor = AssessmentService(
                database.engine, thresholds=settings.engine.thresholds(), now=lambda: t0
            )
            state = PolicyState()
            for snap in snapshots:
                at = snap.completed_at
                item = assessor.assess(snap, (loc,))[0]
                notifier = NotificationService(
                    database.engine, settings=settings, now=lambda at=at: at
                )
                await notifier.decide_cycle(None, (item,))
                with Session(database.engine) as session:
                    rows = session.scalars(
                        select(NotificationDecisionRow)
                        .where(NotificationDecisionRow.assessment_id == item.stored.id)
                        .order_by(NotificationDecisionRow.id)
                    ).all()
                stored.append(
                    tuple(
                        (r.trigger, r.change_position, r.event_key, r.decision, r.level_after)
                        for r in rows
                    )
                )
                decided = decide(
                    state,
                    item.stored.assessment,
                    item.stored.changes,
                    settings.policy_settings(),
                    at,
                )
                state = decided.state
                expected.append(
                    tuple(
                        (d.trigger, d.position, d.event_key, d.decision, d.level_after)
                        for d in decided.decisions
                    )
                )

    anyio.run(_run)

    level = [next(row[3] for row in step if row[0] == "level") for step in stored]
    assert level == ["escalation", "held", "held", "held", "sent", "escalation"]
    assert ("official_added", "repeat") in {(row[0], row[3]) for row in stored[-1]}
    assert stored == expected


def test_check_once_prints_sent_notification_and_confirmation_instant() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        first = run(["check", "--once"])

    assert first.exit_code == 0, first.stderr
    assert f"Notification sent: {MIAMI}: level 1, All Clear" in first.stdout
    assert "NWS Miami FL issued a Rip Current Statement that covers the location." in first.stdout

    # Trigger a held drop via evacuation toggle on, then off on a partial cycle.
    failed = httpx.Response(UNAVAILABLE_HTTP, headers={"content-type": "text/plain"})
    with recorded_services():
        run(["locations", "evacuation", MIAMI, "on"], runtime(now=NOW + timedelta(minutes=5)))
        escalated = run(["check", "--once"], runtime(now=NOW + timedelta(minutes=10)))
        assert f"Notification sent: {MIAMI}: level 4, Warning / Watch / Evacuation" in (
            escalated.stdout
        )
        run(["locations", "evacuation", MIAMI, "off"], runtime(now=NOW + timedelta(minutes=15)))

    with recorded_services(overrides={SUMMARY_CATALOG: failed}):
        held = run(["check", "--once"], runtime(now=NOW + timedelta(minutes=20)))
    assert "Confirmation cycle due at " in held.stdout
