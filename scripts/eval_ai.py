# scripts/eval_ai.py
"""Grade the AI eval set: the recordings by default, or new answers with ``--live``.

Every case of ``tests/ai/eval/cases.py`` is graded as ``tests/ai/test_ai_eval.py`` grades
it (``tests/ai/eval/grading.py``): the answer matches its schema, passes its validators
against its own context, and states the engine's level; an injection twin also carries no
URL and no other level. The script prints each case's verdict, then each product's prompt
tokens, output tokens, and cost (minimum, median, 95th percentile, maximum) and the total.

- With no option it grades the recordings in ``tests/fixtures/ai/`` and sends nothing.
- ``--count`` adds a free ``count_tokens`` request for every case's prompt (the
  measurement ``docs/AI.md`` records) and needs the operator's credential.
- ``--live`` regenerates every case with the operator's credential (it spends money,
  about $1 a run: the operator says yes first), grades the new answers, and prints their
  usage. It refuses to run without a credential.

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
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final

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

from eval.cases import EvalCase, eval_cases  # noqa: E402
from eval.grading import (  # noqa: E402
    MODEL,
    Spread,
    grade,
    spreads,
    text_of_recording,
    usage_of_recording,
)

from weatherbot.services.ai.caller import request_kwargs, text_of, usage_of  # noqa: E402
from weatherbot.services.ai.client import credential_source, default_client  # noqa: E402
from weatherbot.services.ai.pricing import TokenUsage, usd_text  # noqa: E402

NO_CREDENTIAL: Final = "error: set ANTHROPIC_API_KEY or run ant auth login first"


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        max_retries=0,
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


async def _live(cases: Sequence[EvalCase]) -> dict[str, tuple[str, TokenUsage]]:
    answers: dict[str, tuple[str, TokenUsage]] = {}
    async with _client() as client:
        for case in cases:
            kwargs = request_kwargs(case.params(), case.output_format)
            if case.kind == "briefing":
                async with client.messages.stream(model=MODEL, **kwargs) as stream:
                    message = await stream.get_final_message()
            else:
                message = await client.messages.create(model=MODEL, stream=False, **kwargs)
            answers[case.name] = (text_of(message), usage_of(message.usage))
    return answers


def _spread(label: str, spread: Spread, money: bool = False) -> str:  # noqa: FBT001, FBT002 - a print helper
    def show(value: int) -> str:
        return usd_text(value) if money else str(value)

    return (
        f"  {label}: min {show(spread.minimum)}, median {show(spread.median)}, "
        f"p95 {show(spread.p95)}, max {show(spread.maximum)}"
    )


def _report(
    cases: Sequence[EvalCase],
    texts: Callable[[EvalCase], str],
    usage: Callable[[EvalCase], TokenUsage],
    counted: Mapping[str, int] | None = None,
) -> int:
    failed = 0
    for case in cases:
        problems = grade(case, texts(case))
        failed += bool(problems)
        tokens = usage(case)
        count = f", counted {counted[case.name]} in" if counted else ""
        verdict = "pass" if not problems else "FAIL"
        print(f"{verdict}  {case.name}  ({tokens.output_tokens} out{count})")
        for problem in problems:
            print(f"      {problem}")
    total = 0
    for kind, (prompt, output, cost, spent) in spreads(cases, usage).items():
        print(f"{kind}: {sum(case.kind == kind for case in cases)} cases")
        print(_spread("prompt tokens", prompt))
        print(_spread("output tokens", output))
        print(_spread("cost", cost, money=True))
        if counted:
            values = [counted[case.name] for case in cases if case.kind == kind]
            print(_spread("counted prompt tokens", Spread.of(values)))
        total += spent
    print(f"total cost at list price: {usd_text(total)} ({total} micro-dollars)")
    print(f"{len(cases) - failed} of {len(cases)} cases pass")
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
            answers = asyncio.run(_live(cases))
            return _report(
                cases, lambda case: answers[case.name][0], lambda case: answers[case.name][1]
            )
        counted = asyncio.run(_count(cases)) if arguments.count else None
    except anthropic.AnthropicError as error:
        print(f"error: Anthropic refused a request ({type(error).__name__})", file=sys.stderr)
        return 1
    return _report(cases, text_of_recording, usage_of_recording, counted)


if __name__ == "__main__":
    sys.exit(main())
