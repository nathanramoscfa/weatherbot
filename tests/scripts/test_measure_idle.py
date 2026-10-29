# tests/scripts/test_measure_idle.py
"""Offline tests for ``scripts/measure_idle.py`` output tracking and budget evaluation."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from measure_idle import (  # noqa: E402
    IDLE_BUDGET_PCT,
    _DemoOutputTracker,  # pyright: ignore[reportPrivateUsage]
    evaluate_idle_shares,
)


def test_demo_output_tracker_parses_startup_and_counts_window_events() -> None:
    tracker = _DemoOutputTracker()
    tracker.feed_line("cycle id=1 trigger=startup status=complete")
    tracker.feed_line("pid=4242 address=http://127.0.0.1:8799")

    assert tracker.ready_event.is_set()
    assert tracker.pid == 4242  # noqa: PLR2004
    assert tracker.address == "http://127.0.0.1:8799"
    assert tracker.roster_polls_in_window == 0
    assert tracker.cycles_in_window == 0

    tracker.set_window_active(active=True)
    tracker.feed_line("roster_poll at=2026-10-12T19:33:10+00:00")
    tracker.feed_line("cycle id=2 trigger=advisory_change status=complete")
    tracker.set_window_active(active=False)
    tracker.feed_line("roster_poll at=2026-10-12T19:48:10+00:00")

    assert tracker.roster_polls_in_window == 1
    assert tracker.cycles_in_window == 1


def test_evaluate_idle_shares_enforces_strict_half_percent_budget() -> None:
    assert IDLE_BUDGET_PCT == 0.5  # noqa: PLR2004
    assert evaluate_idle_shares(server_cpu_pct=0.05, tab_cpu_pct=0.02) is True
    assert evaluate_idle_shares(server_cpu_pct=0.5, tab_cpu_pct=0.02) is False
    assert evaluate_idle_shares(server_cpu_pct=0.05, tab_cpu_pct=0.5) is False
    assert evaluate_idle_shares(server_cpu_pct=0.8, tab_cpu_pct=0.1) is False
