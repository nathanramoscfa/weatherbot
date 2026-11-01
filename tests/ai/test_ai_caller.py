# tests/ai/test_ai_caller.py
"""``AiCaller``: every request reserved, sent through the real SDK, and settled.

The round trips replay the recordings ``scripts/record_ai_fixtures.py`` made with the
operator's credential; the error answers and unusable stops are hand-written, with
synthetic messages.
"""

import asyncio
import base64
import json
import math
import struct
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta

import anthropic
import pytest
from ai_support import (
    MODEL,
    REQUEST_ID,
    RecordedAnswer,
    Replay,
    event_stream,
    ledger_rows,
    load_answer,
    message_body,
    recorded_usage,
    replay_client,
)
from pydantic import BaseModel
from sqlalchemy import Engine

from weatherbot.services.ai.caller import (
    AiCaller,
    estimate_prompt_tokens,
    image_tokens,
    png_size,
)
from weatherbot.services.ai.errors import (
    AUTH_FAILURES_TO_HOLD,
    AUTH_HOLD,
    AiUnavailable,
    AuthGuard,
    InvalidOutputError,
)
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.ledger import Ledger
from weatherbot.services.ai.pricing import MAX_PROMPT_TOKENS, TokenUsage, cost_micro_usd
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database

NOW = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
ROUND_TRIP = {
    "max_tokens": 256,
    "output_config": {"effort": "low"},
    "messages": [{"role": "user", "content": "Reply with the single word ready."}],
}
SHORT = {"max_tokens": 64, "messages": [{"role": "user", "content": "Say ok."}]}
SAMPLING = ("temperature", "top_p", "top_k")
SYNTHETIC_INPUT_TOKENS = 20
"""``message_body``'s default input."""
OUTLOOK_TOKENS = 825
"""A 900 by 679 outlook map: 33 by 25 tiles of 28 pixels."""


class Ready(BaseModel):
    """The round trip's answer."""

    word: str


class Clock:
    """A clock a test moves by hand."""

    def __init__(self) -> None:
        """Start at ``NOW``."""
        self.at = NOW

    def __call__(self) -> datetime:
        """Read the clock."""
        return self.at


@pytest.fixture
def engine() -> Iterator[Engine]:
    with open_database(AppPaths.resolve()) as database:
        guarded = ai_engine(database.path)
        yield guarded
        guarded.dispose()


def _caller(
    engine: Engine,
    answers: list[RecordedAnswer],
    *,
    cap: int = 1_000_000,
    clock: Clock | None = None,
    auth: AuthGuard | None = None,
) -> tuple[AiCaller, Replay]:
    client, replay = replay_client(answers)
    now = clock or Clock()
    ledger = Ledger(engine, cap_micro_usd=cap, now=now, local_zone=UTC)
    return AiCaller(lambda: client, ledger, now=now, auth=auth), replay


def _usage(recorded: dict[str, int]) -> TokenUsage:
    has_split = "ephemeral_5m_input_tokens" in recorded
    return TokenUsage(
        input_tokens=recorded["input_tokens"],
        cache_write_5m_tokens=(
            recorded.get("ephemeral_5m_input_tokens", 0)
            if has_split
            else recorded.get("cache_creation_input_tokens", 0)
        ),
        cache_write_1h_tokens=recorded.get("ephemeral_1h_input_tokens", 0),
        cache_read_tokens=recorded.get("cache_read_input_tokens", 0),
        output_tokens=recorded["output_tokens"],
    )


def _row_usage(engine: Engine) -> TokenUsage:
    [row] = ledger_rows(engine)
    return TokenUsage(
        input_tokens=row.input_tokens,
        cache_write_5m_tokens=row.cache_write_5m_tokens,
        cache_write_1h_tokens=row.cache_write_1h_tokens,
        cache_read_tokens=row.cache_read_tokens,
        output_tokens=row.output_tokens,
    )


async def _parse(caller: AiCaller, params: Mapping[str, object] = ROUND_TRIP) -> Ready | None:
    parsed = await caller.parse(
        kind="briefing",
        model=MODEL,
        location="Miami-Dade County Hall",
        prompt_version="v1",
        params=params,
        output_format=Ready,
    )
    return parsed.output


async def _stream(caller: AiCaller) -> list[str]:
    seen: list[str] = []
    async with caller.stream(
        kind="chat",
        model=MODEL,
        location=None,
        prompt_version=None,
        params=ROUND_TRIP,
        output_format=Ready,
    ) as events:
        seen.extend([event.type async for event in events])
    if events.final is not None:
        assert isinstance(events.output, Ready)
    return seen


def test_a_replayed_parse_settles_one_row_at_the_recorded_usage(engine: Engine) -> None:
    caller, replay = _caller(engine, [load_answer("round-trip")])

    parsed = asyncio.run(_parse(caller))
    [row] = ledger_rows(engine)
    expected = _usage(recorded_usage("round-trip"))

    assert parsed is not None
    assert parsed.word.strip().lower().startswith("ready")
    assert _row_usage(engine) == expected
    assert row.cost_micro_usd == cost_micro_usd(MODEL, expected)
    assert (row.status, row.kind, row.location_name, row.request_id) == (
        "ok",
        "briefing",
        "Miami-Dade County Hall",
        REQUEST_ID,
    )
    assert row.cost_micro_usd is not None
    assert row.cost_micro_usd < row.ceiling_micro_usd
    assert len(replay.requests) == 1


def test_a_replayed_stream_settles_one_row_at_the_recorded_usage(engine: Engine) -> None:
    caller, _ = _caller(engine, [load_answer("round-trip-stream")])

    seen = asyncio.run(_stream(caller))
    [row] = ledger_rows(engine)
    expected = _usage(recorded_usage("round-trip-stream"))

    assert seen[0] == "message_start"
    assert seen[-1] == "message_stop"
    assert _row_usage(engine) == expected
    assert row.cost_micro_usd == cost_micro_usd(MODEL, expected)
    assert (row.status, row.request_id) == ("ok", REQUEST_ID)


def test_no_request_carries_a_sampling_parameter_and_every_one_carries_max_tokens(
    engine: Engine,
) -> None:
    caller, replay = _caller(engine, [load_answer("round-trip"), load_answer("round-trip-stream")])

    asyncio.run(_parse(caller))
    asyncio.run(_stream(caller))

    assert len(replay.requests) == len(SAMPLING) - 1
    for request in replay.requests:
        assert not set(SAMPLING) & set(request.body)
        assert request.body["max_tokens"] == ROUND_TRIP["max_tokens"]


@pytest.mark.parametrize("parameter", SAMPLING)
def test_a_sampling_parameter_is_refused_before_anything_is_sent(
    engine: Engine, parameter: str
) -> None:
    caller, replay = _caller(engine, [])

    with pytest.raises(ValueError, match="never carries"):
        asyncio.run(_parse(caller, {**SHORT, parameter: 0.5}))

    assert replay.requests == []
    assert ledger_rows(engine) == []


def test_a_request_without_max_tokens_is_refused(engine: Engine) -> None:
    caller, replay = _caller(engine, [])

    with pytest.raises(TypeError, match="max_tokens"):
        asyncio.run(_parse(caller, {"messages": SHORT["messages"]}))
    assert replay.requests == []


def test_a_request_over_the_cap_is_refused_before_anything_is_sent(engine: Engine) -> None:
    caller, replay = _caller(
        engine, [RecordedAnswer.json(message_body('{"word": "ready"}'))], cap=100
    )

    with pytest.raises(AiUnavailable) as error:
        asyncio.run(_parse(caller))

    assert error.value.reason == "capped"
    assert replay.requests == []
    assert ledger_rows(engine) == []


def test_a_prompt_past_the_limit_is_too_large_and_never_sent(engine: Engine) -> None:
    caller, replay = _caller(engine, [], cap=10**9)
    huge = {
        "max_tokens": 10,
        "messages": [{"role": "user", "content": "x" * (MAX_PROMPT_TOKENS * 3)}],
    }

    with pytest.raises(AiUnavailable, match="too large"):
        asyncio.run(_parse(caller, huge))
    assert replay.requests == []


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (RecordedAnswer.error(429, "rate_limit_error"), "rate_limited"),
        (RecordedAnswer.error(529, "overloaded_error"), "overloaded"),
        (RecordedAnswer.error(503, "api_error"), "server_error"),
        (RecordedAnswer.error(500, "api_error"), "server_error"),
        (RecordedAnswer.error(400, "invalid_request_error"), "bad_request"),
        (RecordedAnswer.error(403, "permission_error"), "permission"),
        (RecordedAnswer.error(404, "not_found_error"), "not_found"),
        (RecordedAnswer.error(413, "request_too_large"), "too_large"),
        (RecordedAnswer.error(401, "authentication_error"), "auth_failed"),
        (RecordedAnswer.unreachable(), "network"),
    ],
)
def test_an_error_answer_maps_to_its_reason_and_settles_failed_at_zero(
    engine: Engine, answer: RecordedAnswer, reason: str
) -> None:
    caller, _ = _caller(engine, [answer])

    with pytest.raises(AiUnavailable) as error:
        asyncio.run(_parse(caller, SHORT))
    [row] = ledger_rows(engine)

    assert error.value.reason == reason
    assert "synthetic" not in str(error.value)
    assert (row.status, row.cost_micro_usd, row.error_kind) == ("failed", 0, reason)


def test_a_refusal_is_declined_with_its_category_and_its_usage(engine: Engine) -> None:
    body = message_body(
        "", stop_reason="refusal", stop_details={"type": "refusal", "category": "cyber"}
    )
    caller, _ = _caller(engine, [RecordedAnswer.json(body)])

    with pytest.raises(AiUnavailable) as error:
        asyncio.run(_parse(caller, SHORT))
    [row] = ledger_rows(engine)

    assert (error.value.reason, error.value.category) == ("declined", "cyber")
    assert (row.status, row.refusal_category, row.stop_reason) == ("declined", "cyber", "refusal")
    assert row.cost_micro_usd == cost_micro_usd(MODEL, TokenUsage(input_tokens=20, output_tokens=5))


def test_a_max_tokens_stop_is_truncated(engine: Engine) -> None:
    caller, _ = _caller(
        engine, [RecordedAnswer.json(message_body('{"word": "re', stop_reason="max_tokens"))]
    )

    with pytest.raises(AiUnavailable) as error:
        asyncio.run(_parse(caller, SHORT))
    [row] = ledger_rows(engine)

    assert error.value.reason == "truncated"
    assert (row.status, row.error_kind, row.stop_reason) == ("failed", "truncated", "max_tokens")


def test_an_answer_that_misses_its_schema_is_invalid_output_at_its_usage(engine: Engine) -> None:
    caller, _ = _caller(engine, [RecordedAnswer.json(message_body("ready, no JSON here"))])

    with pytest.raises(InvalidOutputError) as error:
        asyncio.run(_parse(caller, SHORT))
    [row] = ledger_rows(engine)

    assert "no JSON" not in str(error.value)
    assert (row.status, row.error_kind, row.stop_reason) == ("failed", "invalid_output", "end_turn")
    assert row.cost_micro_usd == cost_micro_usd(MODEL, TokenUsage(input_tokens=20, output_tokens=5))


def test_a_structured_request_carries_its_schema_as_the_output_format(engine: Engine) -> None:
    caller, replay = _caller(engine, [RecordedAnswer.json(message_body('{"word": "ready"}'))])

    asyncio.run(_parse(caller, {**SHORT, "output_config": {"effort": "low"}}))
    config = replay.requests[0].body["output_config"]

    assert config == {
        "effort": "low",
        "format": {
            "type": "json_schema",
            "schema": anthropic.transform_schema(Ready.model_json_schema()),
        },
    }


def test_a_context_window_stop_is_too_large(engine: Engine) -> None:
    body = message_body("", stop_reason="model_context_window_exceeded")
    caller, _ = _caller(engine, [RecordedAnswer.json(body)])

    with pytest.raises(AiUnavailable, match="too large"):
        asyncio.run(
            caller.create(
                kind="chat", model=MODEL, location=None, prompt_version=None, params=SHORT
            )
        )


def test_three_401s_hold_auth_failed_until_an_hour_passes_and_a_success_clears_it(
    engine: Engine,
) -> None:
    clock = Clock()
    guard = AuthGuard(clock)
    unauthorized = RecordedAnswer.error(401, "authentication_error")
    ok = RecordedAnswer.json(message_body('{"word": "ready"}'))
    caller, replay = _caller(engine, [unauthorized] * 4 + [ok], clock=clock, auth=guard)

    for _ in range(3):
        with pytest.raises(AiUnavailable, match="authentication failed"):
            asyncio.run(_parse(caller, SHORT))
    assert guard.held
    with pytest.raises(AiUnavailable) as held:
        asyncio.run(_parse(caller, SHORT))
    assert held.value.reason == "auth_failed"
    assert len(replay.requests) == AUTH_FAILURES_TO_HOLD

    clock.at = NOW + AUTH_HOLD
    with pytest.raises(AiUnavailable, match="authentication failed"):
        asyncio.run(_parse(caller, SHORT))  # the one probe, refused again: held again
    assert guard.held
    clock.at = NOW + 2 * AUTH_HOLD
    asyncio.run(_parse(caller, SHORT))  # the next probe succeeds

    assert not guard.held
    assert len(replay.requests) == AUTH_FAILURES_TO_HOLD + 2


def test_another_error_answer_breaks_a_run_of_401s(engine: Engine) -> None:
    guard = AuthGuard(Clock())
    unauthorized = RecordedAnswer.error(401, "authentication_error")
    limited = RecordedAnswer.error(429, "rate_limit_error")
    caller, _ = _caller(engine, [unauthorized, unauthorized, limited, unauthorized], auth=guard)

    for _ in range(4):
        with pytest.raises(AiUnavailable):
            asyncio.run(_parse(caller, SHORT))

    assert not guard.held


def test_a_stream_that_ends_without_its_final_message_settles_at_its_ceiling(
    engine: Engine,
) -> None:
    caller, _ = _caller(engine, [RecordedAnswer.events(event_stream("partial", final=False))])

    seen = asyncio.run(_stream(caller))
    [row] = ledger_rows(engine)

    assert "message_stop" not in seen
    assert row.status == "incomplete"
    assert row.cost_micro_usd == row.ceiling_micro_usd
    assert row.input_tokens == SYNTHETIC_INPUT_TOKENS


def test_a_cancelled_stream_settles_at_its_ceiling_and_reraises(engine: Engine) -> None:
    caller, _ = _caller(engine, [RecordedAnswer.events(event_stream("a long answer"))])

    async def consume(first: asyncio.Event) -> None:
        async with caller.stream(
            kind="chat", model=MODEL, location=None, prompt_version=None, params=SHORT
        ) as events:
            async for _ in events:
                first.set()
                await asyncio.Event().wait()

    async def run() -> None:
        first = asyncio.Event()
        task = asyncio.create_task(consume(first))
        await first.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    [row] = ledger_rows(engine)

    assert row.status == "incomplete"
    assert row.cost_micro_usd == row.ceiling_micro_usd


def test_a_stream_error_answer_settles_failed_at_zero(engine: Engine) -> None:
    caller, _ = _caller(engine, [RecordedAnswer.error(529, "overloaded_error")])

    with pytest.raises(AiUnavailable, match="overloaded"):
        asyncio.run(_stream(caller))
    [row] = ledger_rows(engine)

    assert (row.status, row.cost_micro_usd) == ("failed", 0)


def _png(width: int, height: int) -> str:
    header = (
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)
    )
    return base64.b64encode(header + b"\x08\x06\x00\x00\x00" + b"\x00" * 200_000).decode()


def test_an_image_counts_at_its_visual_tokens_not_its_base64_text() -> None:
    data = _png(900, 679)
    with_image = {
        "max_tokens": 10,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": data},
                    },
                    {"type": "text", "text": "Describe it."},
                ],
            }
        ],
    }
    without_data = {
        "max_tokens": 10,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": ""},
                    },
                    {"type": "text", "text": "Describe it."},
                ],
            }
        ],
    }

    text_tokens = math.ceil(len(json.dumps({"model": MODEL, **without_data})) / 2.5)

    assert png_size(data) == (900, 679)
    assert image_tokens(900, 679) == 33 * 25 == OUTLOOK_TOKENS
    assert estimate_prompt_tokens(MODEL, with_image) == text_tokens + OUTLOOK_TOKENS
    assert estimate_prompt_tokens(MODEL, with_image) < 2 * OUTLOOK_TOKENS + text_tokens


def test_an_image_that_is_not_a_png_is_refused() -> None:
    with pytest.raises(ValueError, match="PNG"):
        png_size(base64.b64encode(b"GIF89a" + b"\x00" * 40).decode())


def test_the_sdk_raises_typed_errors_the_map_never_copies() -> None:
    assert issubclass(anthropic.OverloadedError, anthropic.APIStatusError)
    assert issubclass(anthropic.APITimeoutError, anthropic.APIConnectionError)
    assert timedelta(hours=1) == AUTH_HOLD
