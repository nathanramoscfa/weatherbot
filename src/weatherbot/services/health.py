# src/weatherbot/services/health.py
"""The staleness rule: a heartbeat is stale once its last success is two cadences old.

``staleness(rows, now)`` is pure: it reads each heartbeat and the instant it is asked at,
and nothing else. A row whose writer promised a cadence (``expected_every_s``) is stale
when it has never succeeded or its last success is more than twice that cadence before
``now``; a row with no cadence is reported and never stale, so a manual command, which
promises none, never makes data look stale. ``status`` shows the stale rows in a banner,
and ``doctor`` judges them in its ``heartbeat`` check.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from weatherbot.services.persistence.repositories import Heartbeat, HeartbeatKind

STALE_AFTER_CADENCES: Final = 2
"""How many cadences may pass after a row's last success before it is stale."""


@dataclass(frozen=True)
class Staleness:
    """One heartbeat, judged at an instant.

    ``age_s`` is the whole seconds since its last success, or ``None`` when it never
    succeeded.
    """

    kind: HeartbeatKind
    name: str
    last_success_at: datetime | None
    expected_every_s: int | None
    age_s: int | None
    stale: bool


def _judge(row: Heartbeat, now: datetime) -> Staleness:
    last = row.last_success_at
    age = None if last is None else max(int((now - last).total_seconds()), 0)
    cadence = row.expected_every_s
    stale = cadence is not None and (
        last is None or now - last > timedelta(seconds=STALE_AFTER_CADENCES * cadence)
    )
    return Staleness(row.kind, row.name, last, cadence, age, stale)


def staleness(rows: Sequence[Heartbeat], now: datetime) -> tuple[Staleness, ...]:
    """Judge every heartbeat at ``now``.

    Args:
        rows: The heartbeats.
        now: The instant to judge them at.

    Returns:
        One judgement per row, in the rows' order.
    """
    return tuple(_judge(row, now) for row in rows)


def duration_text(seconds: int) -> str:
    """Say a duration in its two largest units: ``7 h``, ``1 d 2 h``, ``45 min``, ``30 s``.

    Args:
        seconds: Whole seconds, at least 0.

    Returns:
        The text.
    """
    units = (("d", 86_400), ("h", 3_600), ("min", 60), ("s", 1))
    parts: list[str] = []
    remaining = seconds
    for name, size in units:
        count, remaining = divmod(remaining, size)
        if count or parts:
            parts.append(f"{count} {name}")
        if len(parts) == 2:  # noqa: PLR2004 - the two largest units
            break
    shown = [part for part in parts if not part.startswith("0 ")]
    return " ".join(shown) or "0 s"
