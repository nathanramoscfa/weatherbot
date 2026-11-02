# scripts/record_ai_fixtures.py
"""Record Anthropic answers for the AI tests with the operator's credential.

Each named case sends one real request (it spends money; the operator says yes first),
with the request body ``AiCaller`` would send, checks that the answer validates, and
writes the response body exactly as received, ``<case>.json`` for a message or
``<case>.sse`` for the raw event stream, into ``tests/fixtures/ai/``, with
``manifest.json`` naming each case's kind, model, date, request body SHA-256, and size.
The cases are the round trips and the eval set (``tests/ai/eval/cases.py``): every
briefing case records as a stream and every change summary as a message, with the same
request body the services send; ``eval`` names them all. The chat and narration cases
(``tests/ai/eval/chat_cases.py``) follow: a chat case runs one turn of the real
``ChatService`` over a throwaway database in a temporary directory (both landmarks over
the recorded snapshot), and keeps every round's raw event stream in ``<case>.json`` as
``{"rounds": [...]}``, refusing the recording unless the turn ended whole; a narration
case records as a stream with the request ``NarrationService`` sends, and is refused
unless it passes the narration's validators. ``chat`` and ``narration`` name each group.
Nothing else is kept: never a request or response header, so never the credential or the
``anthropic-organization-id``. It refuses to overwrite a recording without ``--force``,
prints each recording's cost from its usage at list price, and writes nothing when the
directory would pass 1 MiB. The SDK resolves the credential (``ANTHROPIC_API_KEY`` or an
``ant auth login`` profile); this script never reads or prints it.

Usage::

    uv run python scripts/record_ai_fixtures.py --list
    uv run python scripts/record_ai_fixtures.py round-trip round-trip-stream
    uv run python scripts/record_ai_fixtures.py eval
    uv run python scripts/record_ai_fixtures.py chat narration
    uv run python scripts/record_ai_fixtures.py --force round-trip
"""

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final, Literal, override

import anthropic
import httpx2
from pydantic import BaseModel

from weatherbot.services.ai.caller import request_kwargs, usage_of, validate_output
from weatherbot.services.ai.pricing import TokenUsage, cost_micro_usd, usd_text
from weatherbot.services.ai.schemas import OutlookNarration
from weatherbot.services.ai.validate import first_violation, validate_narration

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
SUPPORT: Final = tuple(
    REPO_ROOT / name
    for name in (
        "scripts",
        "tests/contract",
        "tests/sources",
        "tests/cli",
        "tests/services",
        "tests/engine",
        "tests/ai",
    )
)
"""The test support directories the eval set imports from."""
EVAL_GROUP: Final = "eval"
"""The name that stands for every eval case."""
GROUPS: Final = (EVAL_GROUP, "chat", "narration")
"""Each name that stands for every case whose name begins with it and a hyphen."""
FIXTURES: Final = REPO_ROOT / "tests" / "fixtures" / "ai"
MANIFEST: Final = "manifest.json"
BUDGET_BYTES: Final = 1_048_576
MODEL: Final = "claude-sonnet-5-5"
KEPT_HEADERS: Final = ("content-type",)
"""What the SDK needs to read a recorded answer; no header is ever written to disk."""


class Ready(BaseModel):
    """The round trip's structured answer: one word."""

    word: str


type CaseKind = Literal["parse", "stream", "chat"]


@dataclass(frozen=True)
class Case:
    """One recording: how it is sent, the request body without ``model``, and its schema.

    A ``chat`` case sends no body of its own: it runs its turn of the real chat.
    """

    kind: CaseKind
    params: Mapping[str, Any]
    output_format: type[BaseModel] = Ready
    check: Callable[[BaseModel], str | None] | None = None
    """A further check of the output; it names a problem in fixed text, or ``None``."""


ROUND_TRIP: Final[Mapping[str, Any]] = {
    "max_tokens": 256,
    "output_config": {"effort": "low"},
    "messages": [{"role": "user", "content": "Reply with the single word ready."}],
}
CASES: Final[dict[str, Case]] = {
    "round-trip": Case("parse", ROUND_TRIP),
    "round-trip-stream": Case("stream", ROUND_TRIP),
}
"""The round trips; ``all_cases`` adds the eval set."""


def _support() -> None:
    for directory in reversed(SUPPORT):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))


def eval_cases() -> dict[str, Case]:
    """Build the eval set's recordings from ``tests/ai/eval/cases.py``.

    Returns:
        Each case by name: a briefing as a stream, a change summary as a message.
    """
    _support()
    from eval.cases import eval_cases as build  # noqa: PLC0415 - the test support, on demand

    return {
        case.name: Case(
            "stream" if case.kind == "briefing" else "parse", case.params(), case.output_format
        )
        for case in build()
    }


def _narration_check(two_text: str) -> Callable[[BaseModel], str | None]:
    def check(output: BaseModel) -> str | None:
        if not isinstance(output, OutlookNarration):
            return "the answer is not a narration"
        violation = first_violation(validate_narration(output, two_text))
        return f"{violation.rule}: {violation.detail}" if violation is not None else None

    return check


def chat_cases() -> dict[str, Case]:
    """Build the chat and narration recordings from ``tests/ai/eval/chat_cases.py``.

    Returns:
        Each chat case (a turn of the real chat) and each narration case (a stream with
        the request ``NarrationService`` sends), by name.
    """
    _support()
    from eval.chat_cases import (  # noqa: PLC0415 - the test support, on demand
        CHAT_CASES,
        NARRATION_CASES,
        narration_case_request,
    )

    found = {case.name: Case("chat", {}) for case in CHAT_CASES}
    for case in NARRATION_CASES:
        params, two_text = asyncio.run(narration_case_request(case))
        found[case.name] = Case("stream", params, OutlookNarration, _narration_check(two_text))
    return found


def all_cases() -> dict[str, Case]:
    """Every case: the round trips, the eval set, and the chat and narration cases.

    Returns:
        Each case by name.
    """
    return {**CASES, **eval_cases(), **chat_cases()}


def resolve(names: Sequence[str]) -> dict[str, Case]:
    """Find the named cases; ``eval``, ``chat``, and ``narration`` each stand for a group.

    Args:
        names: Case names.

    Returns:
        The cases by name, in the order named.

    Raises:
        RecordingError: No name, or a name that is no case.
    """
    known = CASES if all(name in CASES for name in names) else all_cases()
    groups = {group: [name for name in known if name.startswith(f"{group}-")] for group in GROUPS}
    expanded = [item for name in names for item in groups.get(name, [name])]
    unknown = [name for name in expanded if name not in known]
    if unknown or not expanded:
        message = f"name one or more cases from: {', '.join(CASES)}, or {', '.join(GROUPS)}"
        raise RecordingError(message)
    return {name: known[name] for name in expanded}


@dataclass(frozen=True)
class Exchange:
    """One request's body and its response body, as they crossed the wire."""

    request: bytes
    status: int
    body: bytes


class RecordingTransport(httpx2.AsyncBaseTransport):
    """Reads each response whole, keeps the bodies, and hands the SDK a header-light copy."""

    def __init__(self, inner: httpx2.AsyncBaseTransport) -> None:
        """Wrap a transport.

        Args:
            inner: The transport that sends the request.
        """
        self.inner = inner
        self.exchanges: list[Exchange] = []

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self.inner.handle_async_request(request)
        try:
            body = await response.aread()
        finally:
            await response.aclose()
        self.exchanges.append(Exchange(request.content, response.status_code, body))
        headers = {
            name: response.headers[name] for name in KEPT_HEADERS if name in response.headers
        }
        return httpx2.Response(response.status_code, headers=headers, content=body, request=request)

    @override
    async def aclose(self) -> None:
        await self.inner.aclose()


@dataclass(frozen=True)
class Recorded:
    """What one case wrote, what it used, and what it cost."""

    case: str
    file: str
    entry: dict[str, object]
    body: bytes
    cost_micro_usd: int
    usage: TokenUsage


class RecordingError(Exception):
    """A recording was refused; nothing was written."""


type ClientFactory = Callable[[httpx2.AsyncBaseTransport], anthropic.AsyncAnthropic]


def sdk_client(transport: httpx2.AsyncBaseTransport) -> anthropic.AsyncAnthropic:
    """Build a client over ``transport``; the SDK resolves the credential.

    Args:
        transport: The recording transport.

    Returns:
        The client, with no retries, so each case is one request.
    """
    return anthropic.AsyncAnthropic(
        max_retries=0,
        timeout=anthropic.Timeout(120.0, connect=10.0),
        http_client=anthropic.DefaultAsyncHttpxClient(transport=transport, follow_redirects=False),
    )


def _file_name(name: str, case: Case) -> str:
    return f"{name}.sse" if case.kind == "stream" else f"{name}.json"


async def _send(client: anthropic.AsyncAnthropic, case: Case) -> anthropic.types.Message:
    # The same request body AiCaller sends: the schema as output_config.format.
    kwargs = request_kwargs(case.params, case.output_format)
    if case.kind == "parse":
        message = await client.messages.create(model=MODEL, stream=False, **kwargs)
    else:
        async with client.messages.stream(model=MODEL, **kwargs) as stream:
            message = await stream.get_final_message()
    output = validate_output(case.output_format, message)
    problem = case.check(output) if case.check is not None else None
    if problem is not None:
        message = f"the answer failed its check ({problem}); nothing was written"
        raise RecordingError(message)
    return message


def stream_usage(body: bytes) -> TokenUsage:
    """Read a recorded event stream's final usage.

    Args:
        body: The raw stream.

    Returns:
        The usage of ``message_start`` merged with each ``message_delta``'s, by price.
    """
    usage: dict[str, Any] = {}
    for line in body.decode("utf-8").splitlines():
        if not line.startswith("data:"):
            continue
        event = json.loads(line.removeprefix("data:"))
        if event.get("type") == "message_start":
            usage.update(event["message"]["usage"])
        elif event.get("type") == "message_delta":
            usage.update({key: value for key, value in event["usage"].items() if value is not None})
    return usage_of(anthropic.types.Usage.model_validate(usage))


def _added(total: TokenUsage, more: TokenUsage) -> TokenUsage:
    return TokenUsage(
        **{
            item.name: getattr(total, item.name) + getattr(more, item.name)
            for item in fields(TokenUsage)
        }
    )


async def _converse(client: anthropic.AsyncAnthropic, name: str) -> None:
    """Run a chat case's turn over a throwaway database; refuse a turn that did not end whole."""
    from eval.chat_cases import (  # noqa: PLC0415 - the test support, on demand
        case_database,
        chat_case,
        run_chat_case,
        store_case_data,
    )
    from source_support import NOW  # noqa: PLC0415 - as above

    from weatherbot.services.ai.chat import Done  # noqa: PLC0415 - as above
    from weatherbot.services.ai.guard import ai_engine  # noqa: PLC0415 - as above
    from weatherbot.services.ai.service import AiService  # noqa: PLC0415 - as above
    from weatherbot.services.config import AiSettings  # noqa: PLC0415 - as above

    case = chat_case(name)
    with (
        tempfile.TemporaryDirectory(prefix="weatherbot-record-", ignore_cleanup_errors=True) as tmp,
        case_database(Path(tmp)) as database,
    ):
        await store_case_data(database, injection=case.injection)
        service = AiService(
            ai_engine(database.path),
            AiSettings(),
            factory=lambda: client,
            environ={},
            now=lambda: NOW,
            local_zone=UTC,
        )
        try:
            events = await run_chat_case(case, service)
        finally:
            service.engine.dispose()
    last = events[-1]
    if not isinstance(last, Done):
        reason = getattr(last, "reason", "")
        message = f"{name} ended {type(last).__name__} ({reason}); nothing was written"
        raise RecordingError(message)


async def _record_cases(
    cases: Mapping[str, Case], client_factory: ClientFactory, inner: httpx2.AsyncBaseTransport
) -> list[tuple[str, Exchange, TokenUsage]]:
    recorded: list[tuple[str, Exchange, TokenUsage]] = []
    transport = RecordingTransport(inner)
    async with client_factory(transport) as client:
        for name, case in cases.items():
            if case.kind != "chat":
                message = await _send(client, case)
                recorded.append((name, transport.exchanges[-1], usage_of(message.usage)))
                continue
            before = len(transport.exchanges)
            await _converse(client, name)
            rounds = transport.exchanges[before:]
            usage = TokenUsage()
            for exchange in rounds:
                usage = _added(usage, stream_usage(exchange.body))
            body = json.dumps({"rounds": [item.body.decode("utf-8") for item in rounds]}, indent=1)
            recorded.append((name, Exchange(rounds[-1].request, 200, body.encode()), usage))
    return recorded


def _directory_bytes(directory: Path, replaced: set[str]) -> int:
    if not directory.is_dir():
        return 0
    return sum(
        path.stat().st_size
        for path in directory.iterdir()
        if path.is_file() and path.name not in replaced and path.name != MANIFEST
    )


def record(  # noqa: PLR0913 - the cases, then keyword-only seams for the tests
    names: Sequence[str],
    *,
    directory: Path = FIXTURES,
    force: bool = False,
    today: date | None = None,
    client_factory: ClientFactory = sdk_client,
    inner: httpx2.AsyncBaseTransport | None = None,
) -> list[Recorded]:
    """Record the named cases and write their bodies and the manifest.

    Args:
        names: The cases, from ``all_cases``; ``eval`` stands for every eval case.
        directory: Where recordings live.
        force: Overwrite existing recordings.
        today: The manifest's date; today's UTC date when omitted.
        client_factory: Builds the client over the recording transport.
        inner: The transport that sends; a real HTTP transport when omitted.

    Returns:
        What was written.

    Raises:
        RecordingError: An unknown case, an existing recording without ``force``, or a
            directory that would pass 1 MiB. Nothing is written then.
        AnthropicError: Anthropic answered a case with an error; nothing is written.
    """
    cases = resolve(names)
    files = {name: _file_name(name, case) for name, case in cases.items()}
    existing = [file for file in files.values() if (directory / file).exists()]
    if existing and not force:
        message = f"refusing to overwrite {', '.join(existing)} without --force"
        raise RecordingError(message)
    # An error answer raises the SDK's typed error here, before anything is written.
    sent = asyncio.run(_record_cases(cases, client_factory, inner or httpx2.AsyncHTTPTransport()))
    day = (today or datetime.now(UTC).date()).isoformat()
    results = [
        Recorded(
            case=name,
            file=files[name],
            entry={
                "case": name,
                "kind": cases[name].kind,
                "model": MODEL,
                "date": day,
                "request_sha256": hashlib.sha256(exchange.request).hexdigest(),
                "bytes": len(exchange.body),
            },
            body=exchange.body,
            cost_micro_usd=cost_micro_usd(MODEL, usage),
            usage=usage,
        )
        for name, exchange, usage in sent
    ]
    manifest_path = directory / MANIFEST
    entries: dict[str, dict[str, object]] = {}
    if manifest_path.is_file():
        entries = {
            item["case"]: item for item in json.loads(manifest_path.read_text(encoding="utf-8"))
        }
    entries.update({result.case: result.entry for result in results})
    manifest = json.dumps([entries[key] for key in sorted(entries)], indent=2) + "\n"
    total = (
        _directory_bytes(directory, set(files.values()))
        + sum(len(result.body) for result in results)
        + len(manifest.encode())
    )
    if total > BUDGET_BYTES:
        message = f"the recordings would take {total} bytes, past the {BUDGET_BYTES}-byte budget"
        raise RecordingError(message)
    directory.mkdir(parents=True, exist_ok=True)
    for result in results:
        (directory / result.file).write_bytes(result.body)
    manifest_path.write_text(manifest, encoding="utf-8", newline="\n")
    return results


def main(argv: Sequence[str] | None = None) -> int:
    """Record the named cases, printing each one's size and cost."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("cases", nargs="*", help="the cases to record")
    parser.add_argument("--force", action="store_true", help="overwrite existing recordings")
    parser.add_argument("--list", action="store_true", help="list the cases and exit")
    arguments = parser.parse_args(argv)
    if arguments.list:
        for name, case in all_cases().items():
            print(f"{name}  ({case.kind}, {MODEL})")
        return 0
    try:
        results = record(arguments.cases, force=arguments.force)
    except RecordingError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except anthropic.AnthropicError as error:
        print(f"error: Anthropic refused the recording ({type(error).__name__})", file=sys.stderr)
        return 1
    total = 0
    for result in results:
        total += result.cost_micro_usd
        cost = f"{usd_text(result.cost_micro_usd)} ({result.cost_micro_usd} micro-dollars)"
        usage = result.usage
        tokens = (
            f"{usage.input_tokens} in, {usage.cache_read_tokens} cache read, "
            f"{usage.cache_write_5m_tokens} cache write, {usage.output_tokens} out"
        )
        print(f"recorded {result.file}: {result.entry['bytes']} bytes, {tokens}, {cost}")
    print(f"total cost at list price: {usd_text(total)} ({total} micro-dollars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
