# scripts/record_ai_fixtures.py
"""Record Anthropic answers for the AI tests with the operator's credential.

Each named case sends one real request (it spends money; the operator says yes first),
with the request body ``AiCaller`` would send, checks that the answer validates, and
writes the response body exactly as received, ``<case>.json`` for a message or
``<case>.sse`` for the raw event stream, into ``tests/fixtures/ai/``, with
``manifest.json`` naming each case's kind, model, date, request body SHA-256, and size.
Nothing else is kept: never a request or response header, so never the credential or the
``anthropic-organization-id``. It refuses to overwrite a recording without ``--force``,
prints each recording's cost from its usage at list price, and writes nothing when the
directory would pass 1 MiB. The SDK resolves the credential (``ANTHROPIC_API_KEY`` or an
``ant auth login`` profile); this script never reads or prints it.

Usage::

    uv run python scripts/record_ai_fixtures.py --list
    uv run python scripts/record_ai_fixtures.py round-trip round-trip-stream
    uv run python scripts/record_ai_fixtures.py --force round-trip
"""

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final, Literal, override

import anthropic
import httpx2
from pydantic import BaseModel

from weatherbot.services.ai.caller import request_kwargs, usage_of, validate_output
from weatherbot.services.ai.pricing import cost_micro_usd, usd_text

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
FIXTURES: Final = REPO_ROOT / "tests" / "fixtures" / "ai"
MANIFEST: Final = "manifest.json"
BUDGET_BYTES: Final = 1_048_576
MODEL: Final = "claude-sonnet-5-5"
KEPT_HEADERS: Final = ("content-type",)
"""What the SDK needs to read a recorded answer; no header is ever written to disk."""


class Ready(BaseModel):
    """The round trip's structured answer: one word."""

    word: str


type CaseKind = Literal["parse", "stream"]


@dataclass(frozen=True)
class Case:
    """One recording: how it is sent, and the request body without ``model``."""

    kind: CaseKind
    params: Mapping[str, Any]


ROUND_TRIP: Final[Mapping[str, Any]] = {
    "max_tokens": 256,
    "output_config": {"effort": "low"},
    "messages": [{"role": "user", "content": "Reply with the single word ready."}],
}
CASES: Final[dict[str, Case]] = {
    "round-trip": Case("parse", ROUND_TRIP),
    "round-trip-stream": Case("stream", ROUND_TRIP),
}


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
    """What one case wrote, and what it cost."""

    case: str
    file: str
    entry: dict[str, object]
    body: bytes
    cost_micro_usd: int


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
    kwargs = request_kwargs(case.params, Ready)
    if case.kind == "parse":
        message = await client.messages.create(model=MODEL, stream=False, **kwargs)
    else:
        async with client.messages.stream(model=MODEL, **kwargs) as stream:
            message = await stream.get_final_message()
    validate_output(Ready, message)
    return message


async def _record_cases(
    names: Sequence[str], client_factory: ClientFactory, inner: httpx2.AsyncBaseTransport
) -> list[tuple[str, Exchange, int]]:
    recorded: list[tuple[str, Exchange, int]] = []
    transport = RecordingTransport(inner)
    async with client_factory(transport) as client:
        for name in names:
            message = await _send(client, CASES[name])
            exchange = transport.exchanges[-1]
            recorded.append((name, exchange, cost_micro_usd(MODEL, usage_of(message.usage))))
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
        names: The cases, from ``CASES``.
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
    unknown = [name for name in names if name not in CASES]
    if unknown or not names:
        message = f"name one or more cases from: {', '.join(CASES)}"
        raise RecordingError(message)
    files = {name: _file_name(name, CASES[name]) for name in names}
    existing = [file for file in files.values() if (directory / file).exists()]
    if existing and not force:
        message = f"refusing to overwrite {', '.join(existing)} without --force"
        raise RecordingError(message)
    # An error answer raises the SDK's typed error here, before anything is written.
    sent = asyncio.run(_record_cases(names, client_factory, inner or httpx2.AsyncHTTPTransport()))
    day = (today or datetime.now(UTC).date()).isoformat()
    results = [
        Recorded(
            case=name,
            file=files[name],
            entry={
                "case": name,
                "kind": CASES[name].kind,
                "model": MODEL,
                "date": day,
                "request_sha256": hashlib.sha256(exchange.request).hexdigest(),
                "bytes": len(exchange.body),
            },
            body=exchange.body,
            cost_micro_usd=cost,
        )
        for name, exchange, cost in sent
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
        for name, case in CASES.items():
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
        print(f"recorded {result.file}: {result.entry['bytes']} bytes, {cost}")
    print(f"total cost at list price: {usd_text(total)} ({total} micro-dollars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
