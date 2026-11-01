# tests/ai/test_ai_pricing.py
"""The price table, each usage component's arithmetic, the rounding, and the ceiling."""

import pytest

from weatherbot.services.ai.pricing import (
    MAX_PROMPT_TOKENS,
    PRICES,
    PRICES_AS_OF,
    TokenUsage,
    UnpricedModelError,
    ceiling_micro_usd,
    cost_micro_usd,
    usd_text,
)

SONNET = "claude-sonnet-5-5"
MILLION = 1_000_000


def test_the_table_holds_the_three_models_at_their_list_prices() -> None:
    assert set(PRICES) == {"claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"}
    sonnet = PRICES[SONNET]
    assert (sonnet.input, sonnet.cache_write_5m, sonnet.cache_write_1h) == (
        2_000_000,
        2_500_000,
        4_000_000,
    )
    assert (sonnet.cache_read, sonnet.output) == (100_000, 10_000_000)
    haiku = PRICES["claude-haiku-5-5"]
    assert (haiku.input, haiku.cache_read, haiku.output) == (100_000, 10_000, 500_000)
    opus = PRICES["claude-opus-5-5"]
    assert (opus.input, opus.cache_write_1h, opus.output) == (4_000_000, 8_000_000, 20_000_000)
    assert PRICES_AS_OF == "2026-10-30"


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (TokenUsage(input_tokens=MILLION), 2_000_000),
        (TokenUsage(cache_write_5m_tokens=MILLION), 2_500_000),
        (TokenUsage(cache_write_1h_tokens=MILLION), 4_000_000),
        (TokenUsage(cache_read_tokens=MILLION), 100_000),
        (TokenUsage(output_tokens=MILLION), 10_000_000),
        (TokenUsage(input_tokens=6_200, output_tokens=1_500), 27_400),
    ],
)
def test_each_component_is_priced_at_its_own_rate(usage: TokenUsage, expected: int) -> None:
    assert cost_micro_usd(SONNET, usage) == expected


def test_the_sum_is_rounded_half_up_once() -> None:
    # 1 cache-read token on Haiku is 0.01 micro-dollars: each alone rounds to nothing,
    # but the sum is rounded once, not per component.
    assert cost_micro_usd("claude-haiku-5-5", TokenUsage(cache_read_tokens=49)) == 0
    assert cost_micro_usd("claude-haiku-5-5", TokenUsage(cache_read_tokens=50)) == 1
    assert cost_micro_usd("claude-haiku-5-5", TokenUsage(cache_read_tokens=30, input_tokens=2)) == 1


def test_an_unpriced_model_is_refused() -> None:
    with pytest.raises(UnpricedModelError, match="not in the price table"):
        cost_micro_usd("claude-unknown", TokenUsage(input_tokens=1))


def test_the_ceiling_rounds_up_and_prices_the_prompt_as_input() -> None:
    assert ceiling_micro_usd(SONNET, 1, 0) == PRICES[SONNET].input // MILLION
    # 2,000 in at $2 and 1,500 out at $10: $0.004 and $0.015.
    assert ceiling_micro_usd(SONNET, 2_000, 1_500) == 4_000 + 15_000


def test_the_prompt_limit_keeps_haiku_below_its_long_prompt_tier() -> None:
    assert MAX_PROMPT_TOKENS == 100 * 1_000


@pytest.mark.parametrize(
    ("micro_usd", "text"), [(0, "$0.00"), (4_999, "$0.00"), (5_000, "$0.01"), (1_000_000, "$1.00")]
)
def test_dollars_are_spelled_to_the_cent(micro_usd: int, text: str) -> None:
    assert usd_text(micro_usd) == text
