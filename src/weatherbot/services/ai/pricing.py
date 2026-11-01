# src/weatherbot/services/ai/pricing.py
"""Anthropic's list prices, in integer micro-dollars, and what a request's usage costs.

The table is the cap's only source of truth: a model missing from it cannot be priced, so
the configuration refuses it. Prices change with Anthropic's pricing page, which this
module names with the date it was read; a change updates ``PRICES``, ``PRICES_AS_OF``,
and ``docs/AI.md`` together. This module imports no SDK.
"""

from dataclasses import dataclass
from typing import Final

MICRO_USD_PER_USD: Final = 1_000_000
TOKENS_PER_PRICE_UNIT: Final = 1_000_000
"""A price is per million tokens."""


@dataclass(frozen=True)
class Price:
    """One model's list prices, in micro-dollars per million tokens."""

    input: int
    cache_write_5m: int
    cache_write_1h: int
    cache_read: int
    output: int


@dataclass(frozen=True)
class TokenUsage:
    """What one request used, by the price it is billed at."""

    input_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0


PRICES: Final[dict[str, Price]] = {
    "claude-sonnet-5-5": Price(
        input=2_000_000,
        cache_write_5m=2_500_000,
        cache_write_1h=4_000_000,
        cache_read=100_000,
        output=10_000_000,
    ),
    # Haiku 5.5's prices hold for prompts up to 100,000 tokens. Beyond that they are
    # $0.50 input, $0.625 and $1 cache writes, $0.05 cache read, and $2.50 output, which
    # are never reached: MAX_PROMPT_TOKENS refuses such a request before it is sent.
    "claude-haiku-5-5": Price(
        input=100_000,
        cache_write_5m=125_000,
        cache_write_1h=200_000,
        cache_read=10_000,
        output=500_000,
    ),
    "claude-opus-5-5": Price(
        input=4_000_000,
        cache_write_5m=5_000_000,
        cache_write_1h=8_000_000,
        cache_read=200_000,
        output=20_000_000,
    ),
}
PRICES_AS_OF: Final = "2026-10-30"
PRICES_SOURCE: Final = "Anthropic's pricing page (platform.claude.com, About Claude, Pricing)"
MAX_PROMPT_TOKENS: Final = 100_000
"""An estimated prompt past this is refused: no product needs one, and it would move
Haiku 5.5 to its long-prompt prices."""


class UnpricedModelError(ValueError):
    """A model the price table does not hold; the cap cannot price it."""

    def __init__(self, model: str) -> None:
        """Create the error.

        Args:
            model: The model's id, which is configuration and never a secret.
        """
        super().__init__(f"{model} is not in the price table")
        self.model = model


def price_of(model: str) -> Price:
    """Return a model's prices.

    Args:
        model: The model's id.

    Returns:
        Its prices.

    Raises:
        UnpricedModelError: The table does not hold the model.
    """
    try:
        return PRICES[model]
    except KeyError:
        raise UnpricedModelError(model) from None


def cost_micro_usd(model: str, usage: TokenUsage) -> int:
    """Price a request's usage: each component's tokens at its price, rounded once.

    Args:
        model: The model the request ran on.
        usage: What it used.

    Returns:
        The cost in micro-dollars, the exact sum divided by a million and rounded half up.

    Raises:
        UnpricedModelError: The table does not hold the model.
    """
    price = price_of(model)
    total = (
        usage.input_tokens * price.input
        + usage.cache_write_5m_tokens * price.cache_write_5m
        + usage.cache_write_1h_tokens * price.cache_write_1h
        + usage.cache_read_tokens * price.cache_read
        + usage.output_tokens * price.output
    )
    return (total + TOKENS_PER_PRICE_UNIT // 2) // TOKENS_PER_PRICE_UNIT


def ceiling_micro_usd(model: str, prompt_tokens: int, max_tokens: int) -> int:
    """Price the most a request can cost: its prompt at the input price, ``max_tokens`` out.

    Args:
        model: The model.
        prompt_tokens: The estimated prompt.
        max_tokens: The request's output limit.

    Returns:
        The ceiling in micro-dollars, rounded up.
    """
    price = price_of(model)
    total = prompt_tokens * price.input + max_tokens * price.output
    return -(-total // TOKENS_PER_PRICE_UNIT)


def usd_text(micro_usd: int) -> str:
    """Spell micro-dollars as dollars and cents for a person: ``$0.03``.

    Args:
        micro_usd: An amount in micro-dollars.

    Returns:
        The amount rounded half up to the cent.
    """
    cents = (micro_usd + 5_000) // 10_000
    return f"${cents // 100}.{cents % 100:02d}"
