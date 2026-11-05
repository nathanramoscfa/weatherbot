# tests/services/test_retention_keeplist.py
"""Tests that retention pruning preserves ``NotificationService._load_state`` and ``diff``."""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast

import httpx
from cli_support import (
    MIAMI,
    NASSAU,
    add_landmark,
    quiet_fetcher,
    recorded_services,
)
from fixture_support import register_alert
from source_support import NOW
from sqlalchemy import select
from sqlalchemy.orm import Session

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.monitor import MonitorService
from weatherbot.services.network import Network
from weatherbot.services.notifications import NotificationService
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.tables import LocationRow, NotificationDecisionRow
from weatherbot.services.policy import PolicyState
from weatherbot.services.retention import RetentionService

if TYPE_CHECKING:
    from pathlib import Path

    from weatherbot.models import ChangeEvent

LONGEST_COOLDOWN = timedelta(hours=48)

FORECAST_ZONE_URL = "https://api.weather.gov/zones/forecast/FLZ173"
FORECAST_ALERTS_URL = "https://api.weather.gov/alerts/active/zone/FLZ173"


def _alert_response(sent: datetime, *, alert_id: str, event: str | None) -> httpx.Response:
    features: list[dict[str, object]] = []
    if event is not None:
        feature = register_alert(sent)
        props = cast("dict[str, object]", feature["properties"])
        props["id"] = alert_id
        props["event"] = event
        props["affectedZones"] = [FORECAST_ZONE_URL]
        # Give a long expiry so removing the alert without a new advisory triggers a held drop.
        expires = (sent + timedelta(days=200)).strftime("%Y-%m-%dT%H:%M:%SZ")
        props["expires"] = expires
        props["ends"] = expires
        features.append(feature)
    body = json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8")
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def _strip_expired_cooldowns(state: PolicyState, cutoff: datetime) -> PolicyState:
    return PolicyState(
        announced_level=state.announced_level,
        announced_unavailable=state.announced_unavailable,
        announced_expiries=state.announced_expiries,
        pending_held=state.pending_held,
        last_sent={k: v for k, v in state.last_sent.items() if v >= cutoff},
    )


def _run_cycle_and_decide(
    paths: AppPaths,
    instant: datetime,
) -> tuple[dict[str, tuple[ChangeEvent, ...]], dict[str, tuple[tuple[str, str, int | None], ...]]]:
    settings = Settings()
    with open_database(paths) as db:
        monitor = MonitorService(
            db.engine,
            paths=paths,
            settings=settings,
            runner="check-once",
            network=Network(
                make_fetcher=lambda client, store: quiet_fetcher(client, store, now=instant)
            ),
            now=lambda: instant,
        )
        notif = NotificationService(
            db.engine,
            settings=settings,
            now=lambda: instant,
        )
        cycle = asyncio.run(monitor.run_cycle("manual"))
        asyncio.run(notif.decide_cycle(cycle.cycle_id, cycle.assessed))

        changes_by_loc = {item.location.name: tuple(item.stored.changes) for item in cycle.assessed}
        decisions_by_loc: dict[str, tuple[tuple[str, str, int | None], ...]] = {}
        with Session(db.engine) as session:
            for loc in (MIAMI, NASSAU):
                loc_id = session.scalar(select(LocationRow.id).where(LocationRow.name == loc))
                rows = list(
                    session.scalars(
                        select(NotificationDecisionRow)
                        .where(
                            NotificationDecisionRow.location_id == loc_id,
                            NotificationDecisionRow.decided_at == instant,
                        )
                        .order_by(NotificationDecisionRow.id.asc())
                    )
                )
                decisions_by_loc[loc] = tuple(
                    (
                        r.trigger,
                        r.decision,
                        int(r.level_after) if r.level_after is not None else None,
                    )
                    for r in rows
                )
        return changes_by_loc, decisions_by_loc


def test_pruning_preserves_load_state_held_drops_and_next_cycle_decisions(  # noqa: PLR0915
    tmp_path: Path,
) -> None:
    paths = AppPaths.resolve()
    base = NOW

    # Build history across 90 days:
    # - Day 0 (base): both miami-dade and nassau start at Level 1 (All Clear).
    #   nassau stays at Level 1 for the entire 90-day span (> 30-day retention window).
    # - Day 5: miami-dade escalates to Level 2 (Tropical Storm Wind Speed Probabilities / Statement)
    #   via Rip Current Statement? No: Coastal Flood Advisory or Tropical Storm Watch:
    #   Wait: let's step miami-dade through:
    #   * Day 0: Level 1 (All Clear)
    #   * Day 10: Level 3 (Tropical Storm Watch)
    #   * Day 20: Level 4 (Hurricane Watch)
    #   * Day 30: Level 5 (Hurricane Warning)
    #   * Day 40: Alert vanishes before expiry -> Level 1 assessment held for confirmation!
    #     Both the announcing assessment (Day 30) and held-drop assessment (Day 40) are
    #     50..60 days before current_now (Day 90), older than the 30-day retention cutoff (Day 60)!
    with recorded_services() as router:
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0
        assert add_landmark(NASSAU, "nassau").exit_code == 0

        # Day 0: Level 1 for both miami-dade and nassau
        router.get(FORECAST_ALERTS_URL).mock(
            return_value=_alert_response(base, alert_id="none", event=None)
        )
        _run_cycle_and_decide(paths, base)

        # Day 10: Level 3 (Tropical Storm Watch)
        t10 = base + timedelta(days=10)
        router.get(FORECAST_ALERTS_URL).mock(
            return_value=_alert_response(
                t10, alert_id="urn:oid:tswatch.10", event="Tropical Storm Watch"
            )
        )
        _run_cycle_and_decide(paths, t10)

        # Day 20: Level 4 (Hurricane Watch)
        t20 = base + timedelta(days=20)
        router.get(FORECAST_ALERTS_URL).mock(
            return_value=_alert_response(t20, alert_id="urn:oid:hwatch.20", event="Hurricane Watch")
        )
        _run_cycle_and_decide(paths, t20)

        # Day 30: Level 5 (Hurricane Warning)
        t30 = base + timedelta(days=30)
        router.get(FORECAST_ALERTS_URL).mock(
            return_value=_alert_response(
                t30, alert_id="urn:oid:hwarn.30", event="Hurricane Warning"
            )
        )
        _run_cycle_and_decide(paths, t30)

        # Day 40: Alert disappears before expiry -> drop to Level 1 is HELD (pending_held count=1)
        t40 = base + timedelta(days=40)
        router.get(FORECAST_ALERTS_URL).mock(
            return_value=_alert_response(t40, alert_id="none", event=None)
        )
        _run_cycle_and_decide(paths, t40)

        # Copy the database to a second isolated AppPaths before pruning.
        unpruned_root = tmp_path / "unpruned"
        unpruned_paths = AppPaths(
            config_dir=unpruned_root / "config",
            data_dir=unpruned_root / "data",
        )
        unpruned_paths.data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(paths.database_path, unpruned_paths.database_path)

        # At Day 90, prune the primary database with a 30-day window (cutoff = Day 60).
        # Every cycle from Day 0..Day 40 is older than the cutoff!
        current_now = base + timedelta(days=90)
        with open_database(paths) as pruned_db:
            retention = RetentionService(
                pruned_db.engine,
                paths,
                now=lambda: current_now,
                sleep=lambda _: None,
            )
            plan = retention.plan(30)
            assert plan.counts["monitor_cycles"] > 0
            assert plan.counts["assessments"] > 0
            result = retention.run(plan.cutoff)
            assert result.status == "complete"
            assert result.counts == plan.counts

        # Verify _load_state on pruned vs unpruned for both MIAMI and NASSAU!
        cooldown_cutoff = plan.cutoff - LONGEST_COOLDOWN
        with (
            open_database(paths) as pruned_db,
            open_database(unpruned_paths) as unpruned_db,
        ):
            pruned_notif = NotificationService(pruned_db.engine, now=lambda: current_now)
            unpruned_notif = NotificationService(unpruned_db.engine, now=lambda: current_now)
            for loc in (MIAMI, NASSAU):
                pruned_state = pruned_notif._load_state(loc)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                unpruned_state = unpruned_notif._load_state(loc)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                assert _strip_expired_cooldowns(pruned_state, cooldown_cutoff) == (
                    _strip_expired_cooldowns(unpruned_state, cooldown_cutoff)
                )
            # Specifically check MIAMI's announced_level (5) and pending_held (level 1, count 1)
            miami_state = pruned_notif._load_state(MIAMI)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            assert int(miami_state.announced_level or 0) == 5  # noqa: PLR2004
            assert miami_state.pending_held is not None
            assert int(miami_state.pending_held.level) == 1
            assert miami_state.pending_held.count == 1
            # And NASSAU's announced_level (1)
            nassau_state = pruned_notif._load_state(NASSAU)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            assert int(nassau_state.announced_level or 0) == 1

        # Now run a subsequent cycle at Day 90 on both copies:
        # 1) With Hurricane Warning restored -> MIAMI withdraws the held drop without
        #    re-escalating, and NASSAU stays at Level 1 without re-announcing!
        router.get(FORECAST_ALERTS_URL).mock(
            return_value=_alert_response(
                current_now, alert_id="urn:oid:hwarn.30", event="Hurricane Warning"
            )
        )
        pruned_changes, pruned_decisions = _run_cycle_and_decide(paths, current_now)
        unpruned_changes, unpruned_decisions = _run_cycle_and_decide(unpruned_paths, current_now)

        assert pruned_changes == unpruned_changes
        assert pruned_decisions == unpruned_decisions
        assert pruned_decisions[NASSAU] == ()
        assert ("held", "withdrawn", 5) in pruned_decisions[MIAMI]
        assert all(d[1] != "escalation" for d in pruned_decisions[MIAMI])
