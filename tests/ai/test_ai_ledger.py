# tests/ai/test_ai_ledger.py
"""The ledger: reserve, settle, abandon; the cap; allowances; the pause; the local day."""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone

import pytest
from ai_support import ledger_rows
from sqlalchemy import Engine

from weatherbot.services.ai.errors import AiUnavailable
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.ledger import (
    ABANDON_AFTER,
    AllowanceRefusedError,
    Ledger,
    Outcome,
    micro_usd,
)
from weatherbot.services.ai.pricing import PRICES_AS_OF, TokenUsage, cost_micro_usd
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import Database, open_database

SONNET = "claude-sonnet-5-5"
NOW = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
CAP = micro_usd(1.0)
EASTERN = timezone(timedelta(hours=-4))
CEILING = 40_000
SETTLED_COST = 14_700
"""1,200 in, 2,000 written, 3,000 read, 700 out on Sonnet 5.5."""
ABANDONED_CEILING = 600_000


class Clock:
    """A clock a test moves by hand."""

    def __init__(self, at: datetime = NOW) -> None:
        """Start at ``at``."""
        self.at = at

    def __call__(self) -> datetime:
        """Read the clock."""
        return self.at


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


@pytest.fixture
def engine(database: Database) -> Iterator[Engine]:
    guarded = ai_engine(database.path)
    yield guarded
    guarded.dispose()


def _ledger(engine: Engine, clock: Clock | None = None, *, cap: int = CAP) -> Ledger:
    return Ledger(engine, cap_micro_usd=cap, now=clock or Clock(), local_zone=UTC)


def test_a_reservation_is_a_reserved_row_at_its_ceiling(engine: Engine) -> None:
    ledger = _ledger(engine)

    reservation = ledger.reserve("briefing", SONNET, "Miami-Dade County Hall", "abc123", CEILING)
    [row] = ledger_rows(engine)

    assert (row.id, row.kind, row.model, row.status) == (
        reservation.id,
        "briefing",
        SONNET,
        "reserved",
    )
    assert (row.location_name, row.prompt_version, row.day) == (
        "Miami-Dade County Hall",
        "abc123",
        "2026-10-31",
    )
    assert (row.ceiling_micro_usd, row.cost_micro_usd, row.prices_as_of) == (
        40_000,
        None,
        PRICES_AS_OF,
    )
    assert row.started_at == NOW
    assert ledger.today().reserved_micro_usd == CEILING


def test_settle_writes_the_usage_and_its_cost(engine: Engine) -> None:
    clock = Clock()
    ledger = _ledger(engine, clock)
    reservation = ledger.reserve("summary", SONNET, None, None, 40_000)
    usage = TokenUsage(
        input_tokens=1_200,
        cache_write_5m_tokens=2_000,
        cache_write_1h_tokens=0,
        cache_read_tokens=3_000,
        output_tokens=700,
    )
    clock.at = NOW + timedelta(seconds=9)

    ledger.settle(reservation, Outcome("ok", usage, stop_reason="end_turn", request_id="req_1"))
    [row] = ledger_rows(engine)

    assert row.status == "ok"
    assert row.cost_micro_usd == cost_micro_usd(SONNET, usage) == SETTLED_COST
    assert (
        row.input_tokens,
        row.cache_write_5m_tokens,
        row.cache_read_tokens,
        row.output_tokens,
    ) == (
        1_200,
        2_000,
        3_000,
        700,
    )
    assert (row.stop_reason, row.request_id, row.finished_at) == ("end_turn", "req_1", clock.at)
    today = ledger.today()
    assert (today.spent_micro_usd, today.reserved_micro_usd, today.requests) == (14_700, 0, 1)


def test_an_incomplete_request_settles_at_its_ceiling(engine: Engine) -> None:
    ledger = _ledger(engine)
    reservation = ledger.reserve("briefing", SONNET, None, None, 40_000)

    ledger.settle(reservation, Outcome("incomplete", TokenUsage(input_tokens=900)))
    [row] = ledger_rows(engine)

    assert (row.status, row.cost_micro_usd, row.input_tokens) == ("incomplete", 40_000, 900)


def test_a_failed_request_settles_at_zero_with_its_reason(engine: Engine) -> None:
    ledger = _ledger(engine)
    reservation = ledger.reserve("chat", SONNET, None, None, 40_000)

    ledger.settle(reservation, Outcome("failed", error_kind="rate_limited"))
    [row] = ledger_rows(engine)

    assert (row.status, row.cost_micro_usd, row.error_kind) == ("failed", 0, "rate_limited")


def test_a_request_past_the_cap_is_refused_and_writes_nothing(engine: Engine) -> None:
    ledger = _ledger(engine)

    with pytest.raises(AiUnavailable) as error:
        ledger.reserve("briefing", SONNET, None, None, CAP + 1)

    assert error.value.reason == "capped"
    assert ledger_rows(engine) == []


def test_the_cap_counts_spend_and_open_reservations_and_allows_exactly_the_cap(
    engine: Engine,
) -> None:
    ledger = _ledger(engine)
    settled = ledger.reserve("briefing", SONNET, None, None, 300_000)
    ledger.settle(settled, Outcome("ok", TokenUsage(output_tokens=30_000)))  # $0.30
    ledger.reserve("chat", SONNET, None, None, 400_000)  # open

    with pytest.raises(AiUnavailable, match="cap"):
        ledger.reserve("chat", SONNET, None, None, 300_001)
    ledger.reserve("chat", SONNET, None, None, 300_000)

    assert ledger.today().headroom_micro_usd == 0


def test_an_abandoned_reservation_counts_at_its_ceiling(engine: Engine) -> None:
    clock = Clock()
    ledger = _ledger(engine, clock)
    ledger.reserve("briefing", SONNET, None, None, ABANDONED_CEILING)
    clock.at = NOW + ABANDON_AFTER + timedelta(seconds=1)

    with pytest.raises(AiUnavailable, match="cap"):
        ledger.reserve("chat", SONNET, None, None, 400_001)
    ledger.reserve("chat", SONNET, None, None, 400_000)
    first = ledger_rows(engine)[0]

    assert (first.status, first.cost_micro_usd, first.error_kind) == (
        "abandoned",
        600_000,
        "abandoned",
    )
    assert ledger.today().spent_micro_usd == ABANDONED_CEILING


def test_a_fresh_reservation_is_not_abandoned(engine: Engine) -> None:
    clock = Clock()
    ledger = _ledger(engine, clock)
    ledger.reserve("briefing", SONNET, None, None, 1_000)
    clock.at = NOW + ABANDON_AFTER

    ledger.reserve("chat", SONNET, None, None, 1_000)

    assert [row.status for row in ledger_rows(engine)] == ["reserved", "reserved"]


def test_an_allowance_raises_only_its_own_day(engine: Engine) -> None:
    clock = Clock()
    ledger = _ledger(engine, clock)
    ledger.allow(500_000)

    ledger.reserve("briefing", SONNET, None, None, 1_500_000)
    clock.at = NOW + timedelta(days=1)
    with pytest.raises(AiUnavailable, match="cap"):
        ledger.reserve("briefing", SONNET, None, None, 1_000_001)

    allowance = ledger_rows(engine)[0]
    assert (allowance.kind, allowance.status, allowance.allowance_micro_usd) == (
        "allowance",
        "control",
        500_000,
    )
    assert (allowance.input_tokens, allowance.output_tokens, allowance.cost_micro_usd) == (0, 0, 0)


def test_allowances_are_bounded_by_one_days_cap_and_three_a_day(engine: Engine) -> None:
    ledger = _ledger(engine)

    with pytest.raises(AllowanceRefusedError, match="one day's cap"):
        ledger.allow(CAP + 1)
    with pytest.raises(AllowanceRefusedError, match="more than zero"):
        ledger.allow(0)
    for _ in range(3):
        ledger.allow(CAP)
    with pytest.raises(AllowanceRefusedError, match="at most 3"):
        ledger.allow(1)

    today = ledger.today()
    assert (today.allowances, today.limit_micro_usd) == (3, 4 * CAP)


def test_the_pause_refuses_every_request_until_a_resume(engine: Engine) -> None:
    ledger = _ledger(engine)
    ledger.pause()

    with pytest.raises(AiUnavailable) as error:
        ledger.reserve("summary", SONNET, None, None, 1)
    assert error.value.reason == "paused"
    assert ledger.today().paused

    ledger.resume()
    ledger.reserve("summary", SONNET, None, None, 1)
    assert not ledger.today().paused
    assert [row.kind for row in ledger_rows(engine)] == ["pause", "resume", "summary"]


def test_the_pause_outlasts_midnight(engine: Engine) -> None:
    clock = Clock()
    ledger = _ledger(engine, clock)
    ledger.pause()
    clock.at = NOW + timedelta(days=2)

    with pytest.raises(AiUnavailable, match="paused"):
        ledger.reserve("summary", SONNET, None, None, 1)


def test_the_day_is_the_local_calendar_day_across_midnight(engine: Engine) -> None:
    clock = Clock(datetime(2026, 11, 1, 3, 30, tzinfo=UTC))  # 23:30 on Oct 31 in UTC-4
    ledger = Ledger(engine, cap_micro_usd=CAP, now=clock, local_zone=EASTERN)
    late = ledger.reserve("briefing", SONNET, None, None, 900_000)
    ledger.settle(late, Outcome("incomplete"))

    with pytest.raises(AiUnavailable, match="cap"):
        ledger.reserve("chat", SONNET, None, None, 100_001)
    clock.at = datetime(2026, 11, 1, 4, 30, tzinfo=UTC)  # 00:30 on Nov 1 in UTC-4
    ledger.reserve("chat", SONNET, None, None, 1_000_000)

    assert [row.day for row in ledger_rows(engine)] == ["2026-10-31", "2026-11-01"]
    assert ledger.day_of(clock.at) == "2026-11-01"


def test_the_machine_zone_is_the_default() -> None:
    ledger = Ledger(ai_engine(AppPaths.resolve().database_path), cap_micro_usd=CAP, now=Clock())

    assert ledger.day_of(NOW) == NOW.astimezone().date().isoformat()


def test_recent_reads_newest_first_without_any_prompt(engine: Engine) -> None:
    ledger = _ledger(engine)
    ledger.reserve("briefing", SONNET, "Parliament Square", None, 10)
    ledger.pause()

    recent = ledger.recent(5)

    assert [entry.kind for entry in recent] == ["pause", "briefing"]
    assert recent[1].location_name == "Parliament Square"
    assert not hasattr(recent[1], "prompt")


def test_two_engines_reserving_concurrently_never_pass_the_cap(database: Database) -> None:
    engines = [ai_engine(database.path), ai_engine(database.path)]
    ceiling = 70_000
    granted: list[int] = []
    lock = threading.Lock()
    start = threading.Barrier(len(engines))

    def reserve_until_capped(engine: Engine) -> None:
        ledger = Ledger(engine, cap_micro_usd=CAP, now=Clock(), local_zone=UTC)
        start.wait()
        while True:
            try:
                reservation = ledger.reserve("chat", SONNET, None, None, ceiling)
            except AiUnavailable:
                return
            with lock:
                granted.append(reservation.id)

    threads = [threading.Thread(target=reserve_until_capped, args=(e,)) for e in engines]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    total = Ledger(engines[0], cap_micro_usd=CAP, now=Clock(), local_zone=UTC).today()
    for engine in engines:
        engine.dispose()

    assert len(granted) == CAP // ceiling
    assert total.reserved_micro_usd == len(granted) * ceiling <= CAP
