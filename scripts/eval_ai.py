# scripts/eval_ai.py
"""Grade the AI eval set: the recordings by default, or new answers with ``--live``.

Every case is graded as the tests grade it (``tests/ai/eval/grading.py``):

- each briefing and change summary of ``tests/ai/eval/cases.py``: the answer matches its
  schema, passes its validators against its own context, and states the engine's level;
  an injection twin also carries no URL and no other level;
- each chat turn of ``tests/ai/eval/chat_cases.py``, run through the real chat over a
  throwaway database: it ended whole, looked up only the nine tools, and no sentence
  carries a URL or another current level; the injection twin also states its location's
  level and repeats none of the hostile text;
- each narration: it matches its schema and passes its validators against its TWO.

The script prints each case's verdict, then each product's prompt and output tokens per
request and cost per case (minimum, median, 95th percentile, maximum) and the total.

- With no option it grades the recordings in ``tests/fixtures/ai/`` and sends nothing
  (a chat turn replays its recorded rounds).
- ``--count`` adds a free ``count_tokens`` request for every briefing and summary prompt
  (the measurement ``docs/AI.md`` records) and needs the operator's credential.
- ``--live`` regenerates every case with the operator's credential (it spends money,
  about $0.40 a run: the operator says yes first), grades the new answers, and prints
  their usage. It refuses to run without a credential.

It never writes a fixture, and it never prints a prompt, a context, or an answer: only
case names, verdicts, problems in fixed text, and numbers. The SDK resolves the
credential; this script never reads or prints it.

Usage::

    uv run python scripts/eval_ai.py
    uv run python scripts/eval_ai.py --count
    uv run python scripts/eval_ai.py --live
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import anthropic

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for _support in ("tests/ai", "tests/engine", "tests/services", "tests/cli", "tests/sources"):
    _path = str(REPO_ROOT / _support)
    if _path not in sys.path:
        sys.path.insert(0, _path)
for _support in ("tests/contract", "scripts"):
    _path = str(REPO_ROOT / _support)
    if _path not in sys.path:
        sys.path.append(_path)

from ai_support import FIXTURES, load_rounds, replay_client  # noqa: E402
from eval.cases import EvalCase, eval_cases  # noqa: E402
from eval.chat_cases import (  # noqa: E402
    CHAT_CASES,
    NARRATION_CASES,
    NarrationCase,
    converse,
    narration_case_request,
)
from eval.grading import (  # noqa: E402
    MODEL,
    Spread,
    grade,
    grade_narration,
    grade_turn,
    prompt_tokens,
    stream_text,
    stream_usage,
    text_of_recording,
    usage_of_recording,
)

from weatherbot.services.ai.caller import request_kwargs, text_of, usage_of  # noqa: E402
from weatherbot.services.ai.client import credential_source, default_client  # noqa: E402
from weatherbot.services.ai.pricing import TokenUsage, cost_micro_usd, usd_text  # noqa: E402
from weatherbot.services.ai.schemas import OutlookNarration  # noqa: E402

NO_CREDENTIAL: Final = "error: set ANTHROPIC_API_KEY or run ant auth login first"
KINDS: Final = ("briefing", "summary", "chat", "narration")
MICRO_PER_USD: Final = 1_000_000

type Narrate = Callable[[NarrationCase, dict[str, Any]], Awaitable[tuple[str, TokenUsage]]]


@dataclass(frozen=True)
class Graded:
    """One case's verdict: its problems and each of its requests' usage."""

    name: str
    kind: str
    problems: list[str]
    requests: list[TokenUsage]
    counted: int | None = None


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        max_retries=2,
        timeout=anthropic.Timeout(120.0, connect=10.0),
        http_client=anthropic.DefaultAsyncHttpxClient(follow_redirects=False),
    )


async def _count(cases: Sequence[EvalCase]) -> dict[str, int]:
    counted: dict[str, int] = {}
    async with _client() as client:
        for case in cases:
            kwargs = request_kwargs(case.params(), case.output_format)
            kwargs.pop("max_tokens")
            answer = await client.messages.count_tokens(model=MODEL, **kwargs)
            counted[case.name] = answer.input_tokens
    return counted


async def _live_answers(
    client: anthropic.AsyncAnthropic, cases: Sequence[EvalCase]
) -> dict[str, tuple[str, TokenUsage]]:
    answers: dict[str, tuple[str, TokenUsage]] = {}
    for case in cases:
        kwargs = request_kwargs(case.params(), case.output_format)
        if case.kind == "briefing":
            async with client.messages.stream(model=MODEL, **kwargs) as stream:
                message = await stream.get_final_message()
        else:
            message = await client.messages.create(model=MODEL, stream=False, **kwargs)
        answers[case.name] = (text_of(message), usage_of(message.usage))
    return answers


def _graded_cases(
    cases: Sequence[EvalCase],
    texts: Callable[[EvalCase], str],
    usage: Callable[[EvalCase], TokenUsage],
    counted: Mapping[str, int] | None = None,
) -> list[Graded]:
    return [
        Graded(
            case.name,
            case.kind,
            grade(case, texts(case)),
            [usage(case)],
            counted[case.name] if counted else None,
        )
        for case in cases
    ]


async def _graded_turns(
    factory_for: Callable[[str], Callable[[], anthropic.AsyncAnthropic]],
) -> list[Graded]:
    graded: list[Graded] = []
    for case in CHAT_CASES:
        turn = await converse(case, factory_for(case.name))
        graded.append(Graded(case.name, "chat", grade_turn(case, turn), turn.usage))
    return graded


async def _graded_narrations(narrate: Narrate) -> list[Graded]:
    graded: list[Graded] = []
    for case in NARRATION_CASES:
        params, two_text = await narration_case_request(case)
        text, usage = await narrate(case, params)
        graded.append(Graded(case.name, "narration", grade_narration(text, two_text), [usage]))
    return graded


async def _recorded_conversations() -> list[Graded]:
    replays: list[anthropic.AsyncAnthropic] = []

    def factory_for(name: str) -> Callable[[], anthropic.AsyncAnthropic]:
        client, _ = replay_client(load_rounds(name))
        replays.append(client)
        return lambda: client

    async def recorded(case: NarrationCase, _params: dict[str, Any]) -> tuple[str, TokenUsage]:
        path = FIXTURES / f"{case.name}.sse"
        return stream_text(path), stream_usage(path)

    try:
        return [*await _graded_turns(factory_for), *await _graded_narrations(recorded)]
    finally:
        for client in replays:
            await client.close()


async def _live(cases: Sequence[EvalCase]) -> list[Graded]:
    async with _client() as client:
        answers = await _live_answers(client, cases)

        async def narrate(_case: NarrationCase, params: dict[str, Any]) -> tuple[str, TokenUsage]:
            kwargs = request_kwargs(params, OutlookNarration)
            async with client.messages.stream(model=MODEL, **kwargs) as stream:
                message = await stream.get_final_message()
            return text_of(message), usage_of(message.usage)

        turns = await _graded_turns(lambda _name: lambda: client)
        narrations = await _graded_narrations(narrate)
    graded = _graded_cases(
        cases, lambda case: answers[case.name][0], lambda case: answers[case.name][1]
    )
    return [*graded, *turns, *narrations]


def _spread(label: str, spread: Spread, money: bool = False) -> str:  # noqa: FBT001, FBT002 - a print helper
    def show(value: int) -> str:
        return f"${value / MICRO_PER_USD:.4f}" if money else str(value)

    return (
        f"  {label}: min {show(spread.minimum)}, median {show(spread.median)}, "
        f"p95 {show(spread.p95)}, max {show(spread.maximum)}"
    )


def _report(graded: Sequence[Graded]) -> int:
    failed = 0
    for item in graded:
        failed += bool(item.problems)
        output = sum(usage.output_tokens for usage in item.requests)
        count = f", counted {item.counted} in" if item.counted is not None else ""
        requests = f"{len(item.requests)} requests, " if len(item.requests) != 1 else ""
        verdict = "pass" if not item.problems else "FAIL"
        print(f"{verdict}  {item.name}  ({requests}{output} out{count})")
        for problem in item.problems:
            print(f"      {problem}")
    total = 0
    for kind in KINDS:
        chosen = [item for item in graded if item.kind == kind]
        requests = [usage for item in chosen for usage in item.requests]
        if not requests:
            continue
        costs = [sum(cost_micro_usd(MODEL, usage) for usage in item.requests) for item in chosen]
        print(f"{kind}: {len(chosen)} cases, {len(requests)} requests")
        print(_spread("prompt tokens a request", Spread.of([prompt_tokens(u) for u in requests])))
        print(_spread("output tokens a request", Spread.of([u.output_tokens for u in requests])))
        print(_spread("cost a case", Spread.of(costs), money=True))
        counted = [item.counted for item in chosen if item.counted is not None]
        if counted:
            print(_spread("counted prompt tokens", Spread.of(counted)))
        total += sum(costs)
    print(f"total cost at list price: {usd_text(total)} ({total} micro-dollars)")
    print(f"{len(graded) - failed} of {len(graded)} cases pass")
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Grade the eval set and print its verdicts and its token and cost spreads."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--count", action="store_true", help="also count every prompt (free)")
    mode.add_argument("--live", action="store_true", help="regenerate every case (spends)")
    arguments = parser.parse_args(argv)
    if (arguments.count or arguments.live) and credential_source(
        os.environ, default_client
    ) == "none":
        print(NO_CREDENTIAL, file=sys.stderr)
        return 1
    cases = eval_cases()
    try:
        if arguments.live:
            return _report(asyncio.run(_live(cases)))
        counted = asyncio.run(_count(cases)) if arguments.count else None
        conversations = asyncio.run(_recorded_conversations())
    except anthropic.AnthropicError as error:
        print(f"error: Anthropic refused a request ({type(error).__name__})", file=sys.stderr)
        return 1
    recorded = _graded_cases(cases, text_of_recording, usage_of_recording, counted)
    return _report([*recorded, *conversations])


if __name__ == "__main__":
    sys.exit(main())
