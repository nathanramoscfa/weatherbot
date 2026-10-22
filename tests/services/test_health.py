# tests/services/test_health.py
"""The staleness rule, under a frozen clock: stale past twice the cadence, never without one."""

from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from weatherbot.services.health import Staleness, duration_text, staleness
from weatherbot.services.persistence.repositories import Heartbeat

NOW: Final = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
THREE_HOURS: Final = 10_800


def _row(
    name: str, *, succeeded_ago: timedelta | None, cadence: int | None = THREE_HOURS
) -> Heartbeat:
    last = NOW - succeeded_ago if succeeded_ago is not None else None
    return Heartbeat(
        kind="source",
        name=name,
        last_attempt_at=NOW - timedelta(minutes=1),
        last_success_at=last,
        consecutive_failures=0 if last is not None else 2,
        last_error_kind=None if last is not None else "unavailable",
        expected_every_s=cadence,
        updated_at=NOW - timedelta(minutes=1),
    )


def test_a_source_seven_hours_past_its_success_on_a_three_hour_cadence_is_stale() -> None:
    (judged,) = staleness([_row("nhc-current-storms", succeeded_ago=timedelta(hours=7))], NOW)

    assert judged == Staleness(
        kind="source",
        name="nhc-current-storms",
        last_success_at=NOW - timedelta(hours=7),
        expected_every_s=THREE_HOURS,
        age_s=7 * 3600,
        stale=True,
    )


def test_a_source_five_hours_past_its_success_is_not_stale() -> None:
    (judged,) = staleness([_row("nhc-gis-rss", succeeded_ago=timedelta(hours=5))], NOW)

    assert not judged.stale
    assert judged.age_s == 5 * 3600


def test_exactly_two_cadences_is_not_yet_stale() -> None:
    rows = [
        _row("at", succeeded_ago=timedelta(hours=6)),
        _row("past", succeeded_ago=timedelta(hours=6, seconds=1)),
    ]

    assert [judged.stale for judged in staleness(rows, NOW)] == [False, True]


def test_a_row_with_no_cadence_is_never_stale() -> None:
    rows = [
        _row("old", succeeded_ago=timedelta(days=30), cadence=None),
        _row("never", succeeded_ago=None, cadence=None),
    ]

    assert [judged.stale for judged in staleness(rows, NOW)] == [False, False]


def test_a_row_that_never_succeeded_is_stale_when_a_cadence_is_promised() -> None:
    (judged,) = staleness([_row("nws-alerts-zone", succeeded_ago=None)], NOW)

    assert judged.stale
    assert judged.age_s is None


def test_the_rule_reads_only_the_rows_and_the_instant_it_is_given() -> None:
    rows = [_row("nhc-current-storms", succeeded_ago=timedelta(hours=7))]

    assert staleness(rows, NOW - timedelta(hours=2)) != staleness(rows, NOW)
    assert staleness(rows, NOW) == staleness(rows, NOW)


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "0 s"),
        (45, "45 s"),
        (60, "1 min"),
        (2700, "45 min"),
        (10_800, "3 h"),
        (25_200, "7 h"),
        (27_000, "7 h 30 min"),
        (93_600, "1 d 2 h"),
    ],
)
def test_durations_read_in_their_two_largest_units(seconds: int, text: str) -> None:
    assert duration_text(seconds) == text
