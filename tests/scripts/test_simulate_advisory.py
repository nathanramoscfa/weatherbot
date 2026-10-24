# tests/scripts/test_simulate_advisory.py
"""Offline test of ``scripts/simulate_advisory.py`` on a fake toast and fake clock."""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

from cli_support import FakeToast
from source_support import NOW

from weatherbot.models import AlertLevel

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from simulate_advisory import (  # noqa: E402
    MAX_INTERVAL_S,
    SIMULATED_MIAMI,
    run_simulation,
)


class _DeterministicRandom:
    def uniform(self, _a: float, _b: float) -> float:
        return 12.0


class _ManualClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)
        await asyncio.sleep(0)


def test_simulate_advisory_stores_level_5_escalation_within_one_interval(
    tmp_path: Path,
) -> None:
    clock = _ManualClock(NOW)
    toast = FakeToast(result="delivered")

    outcome = asyncio.run(
        run_simulation(
            tmp_path,
            toast=toast,
            clock=clock,
            sleep=clock.sleep,
            random=_DeterministicRandom(),
        )
    )

    assert outcome.notification.location_name == SIMULATED_MIAMI
    assert outcome.notification.level == AlertLevel.HURRICANE_WARNING
    assert outcome.notification.escalation is True
    assert outcome.toast_result == "delivered"
    assert 0 < outcome.elapsed_s <= MAX_INTERVAL_S
    assert any(
        n.location_name == SIMULATED_MIAMI
        and n.level == AlertLevel.HURRICANE_WARNING
        and n.escalation
        for n in toast.handed
    )
