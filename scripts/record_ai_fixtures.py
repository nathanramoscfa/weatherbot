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
The scenario cases (``scripts/demo_scenarios.py``) record each scenario's briefings, one
per landmark, and the landfall scenario's two escalation summaries: twelve requests. Each
scenario's database is built in a temporary directory by the code ``serve_demo.py
--scenario`` runs, then each case runs the real ``BriefingService`` or
``ChangeSummaryService`` over it, and a recording is refused unless the product ended
``ok``. ``--scenario NAME`` (or ``all``, or the group name ``scenario``) names them; before
any request it refuses without a credential, prints the request count and the ceiling,
and asks. Nothing else is kept: never a request or response header, so never the credential or the
``anthropic-organization-id``. It refuses to overwrite a recording without ``--force``,
prints each recording's cost from its usage at list price, and writes nothing when the
directory would pass 1 MiB. The SDK resolves the credential (``ANTHROPIC_API_KEY`` or an
``ant auth login`` profile); this script never reads or prints it.

Usage::

    uv run python scripts/record_ai_fixtures.py --list
    uv run python scripts/record_ai_fixtures.py round-trip round-trip-stream
    uv run python scripts/record_ai_fixtures.py eval
    uv run python scripts/record_ai_fixtures.py chat narration
    uv run python scripts/record_ai_fixtures.py --scenario all       # twelve requests, <= $0.60
    uv run python scripts/record_ai_fixtures.py --force round-trip
"""

import argparse
import asyncio
import contextlib
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

from weatherbot.services.ai.caller import (
    estimate_prompt_tokens,
    request_kwargs,
    usage_of,
    validate_output,
)
from weatherbot.services.ai.pricing import (
    TokenUsage,
    ceiling_micro_usd,
    cost_micro_usd,
    usd_text,
)
from weatherbot.services.ai.schemas import Briefing, ChangeSummary, OutlookNarration
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
SCENARIO_GROUP: Final = "scenario"
"""The name that stands for every scenario case."""
GROUPS: Final = (EVAL_GROUP, "chat", "narration", SCENARIO_GROUP)
"""Each name that stands for every case whose name begins with it and a hyphen."""
FIXTURES: Final = REPO_ROOT / "tests" / "fixtures" / "ai"
MANIFEST: Final = "manifest.json"
BUDGET_BYTES: Final = 1_048_576
MODEL: Final = "claude-sonnet-5-5"
KEPT_HEADERS: Final = ("content-type",)
"""What the SDK needs to read a recorded answer; no header is ever written to disk."""
WORST_REQUEST_MICRO_USD: Final = 50_000
"""The most one briefing or summary has cost at Sonnet 5.5's list price: $0.05, Phase 6's
worst measured briefing (a briefing measured about $0.03 and a summary about $0.01), so
twelve scenario requests are at most $0.60 (``docs/roadmap/phase08-roadmap.md``,
Decision 3)."""


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
    scenario: tuple[str, str] | None = None
    """A scenario case's scenario and landmark: it runs the real service over the scenario."""


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


def scenario_cases() -> dict[str, Case]:
    """Build the scenario recordings from ``scripts/demo_scenarios.py``.

    Returns:
        Each scenario's briefing for each landmark (a stream), then, in a scenario with a
        history, each landmark's escalation summary (a message), by name.
    """
    _support()
    from demo_scenarios import HISTORY, LANDMARKS, SCENARIOS, case_name  # noqa: PLC0415 - on demand

    found: dict[str, Case] = {}
    for scenario in SCENARIOS:
        for location in LANDMARKS:
            name = case_name(scenario, location, "briefing")
            found[name] = Case("stream", {}, Briefing, scenario=(scenario, location))
        if scenario in HISTORY:
            for location in LANDMARKS:
                name = case_name(scenario, location, "summary")
                found[name] = Case("parse", {}, ChangeSummary, scenario=(scenario, location))
    return found


def scenario_names(choice: str) -> list[str]:
    """The cases ``--scenario`` names: one scenario's, or every scenario's for ``all``.

    Args:
        choice: A scenario, or ``all``.

    Returns:
        The case names, in order.
    """
    return [
        name
        for name, case in scenario_cases().items()
        if case.scenario is not None and choice in {"all", case.scenario[0]}
    ]


def all_cases() -> dict[str, Case]:
    """Every case: the round trips, the eval set, the chat and narration cases, the scenarios.

    Returns:
        Each case by name.
    """
    return {**CASES, **eval_cases(), **chat_cases(), **scenario_cases()}


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


def _scenario_service(built: Any, factory: Callable[[], anthropic.AsyncAnthropic]) -> Any:  # noqa: ANN401 - demo_scenarios loads on demand
    from weatherbot.services.ai.guard import ai_engine  # noqa: PLC0415 - as above
    from weatherbot.services.ai.service import AiService  # noqa: PLC0415 - as above
    from weatherbot.services.config import AiSettings  # noqa: PLC0415 - as above

    return AiService(
        ai_engine(built.paths.database_path),
        AiSettings(),
        factory=factory,
        environ={},
        now=built.clock,
        local_zone=UTC,
    )


async def _scenario_turn(
    client: anthropic.AsyncAnthropic,
    name: str,
    case: Case,
    built: Any,  # noqa: ANN401 - a demo_scenarios.ScenarioDatabase, loaded on demand
) -> None:
    """Run a scenario case's briefing or summary through the real service; refuse unless ok."""
    from weatherbot.services.ai.briefing import BriefingService, Done  # noqa: PLC0415 - as above
    from weatherbot.services.ai.summaries import ChangeSummaryService  # noqa: PLC0415 - as above
    from weatherbot.services.persistence.repositories import AssessmentRepository  # noqa: PLC0415

    if case.scenario is None:
        message = f"{name} is not a scenario case"
        raise RecordingError(message)
    location = case.scenario[1]
    service = _scenario_service(built, lambda: client)
    problem: str | None = None
    try:
        if case.kind == "stream":
            ended: object = None
            async for event in BriefingService(service).stream(location, new=True):
                ended = event
            if not isinstance(ended, Done):
                problem = f"ended {type(ended).__name__} ({getattr(ended, 'reason', '')})"
        else:
            stored = AssessmentRepository(service.engine).latest(location)
            if stored is None:
                problem = "has no assessment to summarize"
            else:
                outcome = await ChangeSummaryService(service).summarize(stored.id)
                if outcome.status != "ok":
                    problem = f"ended {outcome.status} ({outcome.reason})"
    finally:
        service.engine.dispose()
    if problem is not None:
        message = f"{name} {problem}; nothing was written"
        raise RecordingError(message)


@dataclass(frozen=True)
class ScenarioPlan:
    """What a scenario recording will send: its requests and their hard ceiling."""

    briefings: int
    summaries: int
    hard_ceiling_micro_usd: int
    """Every request's prompt estimate at the input price plus ``max_tokens`` out."""

    @property
    def requests(self) -> int:
        """How many requests will be sent."""
        return self.briefings + self.summaries


def _plan(cases: Mapping[str, Case], built: Mapping[str, Any]) -> ScenarioPlan:
    from weatherbot.services.ai.briefing import BriefingService, briefing_params  # noqa: PLC0415
    from weatherbot.services.ai.context import change_context  # noqa: PLC0415 - as above
    from weatherbot.services.ai.summaries import summary_params  # noqa: PLC0415 - as above
    from weatherbot.services.persistence.repositories import AssessmentRepository  # noqa: PLC0415

    briefings = summaries = ceiling = 0
    for case in cases.values():
        if case.scenario is None:
            continue
        scenario, location = case.scenario

        def refuse() -> anthropic.AsyncAnthropic:
            message = "planning sends nothing"
            raise RecordingError(message)

        service = _scenario_service(built[scenario], refuse)
        try:
            stored = AssessmentRepository(service.engine).latest(location)
            if stored is None:
                continue
            thresholds = stored.assessment.thresholds
            if case.kind == "stream":
                briefings += 1
                context = BriefingService(service).context_for(stored)
                params = briefing_params(context, thresholds)
            else:
                summaries += 1
                params = summary_params(
                    change_context(stored.assessment, stored.changes), thresholds
                )
            prompt = estimate_prompt_tokens(MODEL, request_kwargs(params, case.output_format))
            ceiling += ceiling_micro_usd(MODEL, prompt, int(params["max_tokens"]))
        finally:
            service.engine.dispose()
    return ScenarioPlan(briefings, summaries, ceiling)


def _build_scenarios(cases: Mapping[str, Case], stack: contextlib.ExitStack) -> dict[str, Any]:
    """Build each named scenario's database once, in a temporary directory the stack removes."""
    _support()
    from demo_scenarios import build_database  # noqa: PLC0415 - on demand

    built: dict[str, Any] = {}
    for case in cases.values():
        if case.scenario is not None and case.scenario[0] not in built:
            directory = stack.enter_context(
                tempfile.TemporaryDirectory(prefix="weatherbot-record-", ignore_cleanup_errors=True)
            )
            built[case.scenario[0]] = build_database(case.scenario[0], Path(directory))
    return built


def _usage(case: Case, exchange: Exchange) -> TokenUsage:
    if case.kind == "stream":
        return stream_usage(exchange.body)
    return usage_of(anthropic.types.Message.model_validate_json(exchange.body).usage)


async def _record_cases(
    cases: Mapping[str, Case],
    client_factory: ClientFactory,
    inner: httpx2.AsyncBaseTransport,
    built: Mapping[str, Any] | None = None,
) -> tuple[list[tuple[str, Exchange, TokenUsage]], list[str]]:
    """Send every case; a scenario case that does not end ``ok`` is refused, and the rest go on.

    Returns:
        What was recorded, and each refused scenario case's reason in fixed text.
    """
    recorded: list[tuple[str, Exchange, TokenUsage]] = []
    refused: list[str] = []
    transport = RecordingTransport(inner)
    async with client_factory(transport) as client:
        for name, case in cases.items():
            if case.scenario is not None and built is not None:
                before = len(transport.exchanges)
                try:
                    await _scenario_turn(client, name, case, built[case.scenario[0]])
                except RecordingError as error:
                    refused.append(str(error))
                    print(f"refused {error}", flush=True)
                    continue
                if len(transport.exchanges) == before:
                    refused.append(f"{name} sent no request; nothing was written")
                    continue
                exchange = transport.exchanges[-1]
                recorded.append((name, exchange, _usage(case, exchange)))
                print(f"passed {name}", flush=True)
                continue
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
    return recorded, refused


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
    confirm: Callable[[ScenarioPlan], bool] | None = None,
) -> list[Recorded]:
    """Record the named cases and write their bodies and the manifest.

    Args:
        names: The cases, from ``all_cases``; ``eval`` stands for every eval case.
        directory: Where recordings live.
        force: Overwrite existing recordings.
        today: The manifest's date; today's UTC date when omitted.
        client_factory: Builds the client over the recording transport.
        inner: The transport that sends; a real HTTP transport when omitted.
        confirm: Asked with the scenario cases' plan once their databases are built and
            before any request; a ``False`` sends nothing.

    Returns:
        What was written.

    Raises:
        RecordingError: An unknown case, an existing recording without ``force``, a
            declined plan, or a directory that would pass 1 MiB, and nothing is written; or
            a scenario product that did not end ``ok``, after the scenario cases that did
            are written.
        AnthropicError: Anthropic answered a case with an error; nothing is written.
    """
    cases = resolve(names)
    files = {name: _file_name(name, case) for name, case in cases.items()}
    existing = [file for file in files.values() if (directory / file).exists()]
    if existing and not force:
        message = f"refusing to overwrite {', '.join(existing)} without --force"
        raise RecordingError(message)
    with contextlib.ExitStack() as stack:
        built = _build_scenarios(cases, stack)
        if confirm is not None and not confirm(_plan(cases, built)):
            message = "the recording was declined; nothing was sent"
            raise RecordingError(message)
        # An error answer raises the SDK's typed error here, before anything is written.
        sent, refused = asyncio.run(
            _record_cases(cases, client_factory, inner or httpx2.AsyncHTTPTransport(), built)
        )
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
    if refused:
        # The scenario cases that passed are kept, so a rerun names only the refused ones.
        kept = ", ".join(result.case for result in results) or "none"
        message = f"kept {kept}; refused {len(refused)}: {'; '.join(refused)}"
        raise RecordingError(message)
    return results


def credential_found() -> bool:
    """Whether the SDK resolves a credential, as the recording client would; never its value.

    Returns:
        Whether ``ANTHROPIC_API_KEY``, an auth token, or a profile supplies one.
    """
    from weatherbot.services.ai.client import has_credential  # noqa: PLC0415 - the SDK's view

    try:
        client = sdk_client(httpx2.AsyncHTTPTransport())
    except anthropic.AnthropicError:
        return False
    try:
        return has_credential(client)
    finally:
        asyncio.run(client.close())


def confirm_plan(plan: ScenarioPlan) -> bool:
    """Print a scenario recording's request count and ceiling, and ask before sending.

    Args:
        plan: What the recording will send.

    Returns:
        Whether the operator answered yes.
    """
    print(
        f"{plan.requests} requests to {MODEL}: {plan.briefings} briefings and "
        f"{plan.summaries} change summaries."
    )
    print(
        f"Ceiling: {usd_text(plan.requests * WORST_REQUEST_MICRO_USD)} at most "
        f"({usd_text(WORST_REQUEST_MICRO_USD)} a request, the worst measured, at list price); "
        f"{usd_text(plan.hard_ceiling_micro_usd)} only if every answer ran to its max_tokens."
    )
    try:
        answer = input("Send them? [y/N] ")
    except EOFError:
        return False
    # Windows PowerShell 5.1 pipes a byte-order mark before the answer it writes to stdin.
    return answer.strip().removeprefix("﻿").strip().lower() in {"y", "yes"}


def main(argv: Sequence[str] | None = None) -> int:
    """Record the named cases, printing each one's size and cost."""
    _support()
    from demo_scenarios import SCENARIO_NAMES  # noqa: PLC0415 - on demand

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("cases", nargs="*", help="the cases to record")
    parser.add_argument("--force", action="store_true", help="overwrite existing recordings")
    parser.add_argument("--list", action="store_true", help="list the cases and exit")
    parser.add_argument(
        "--scenario",
        choices=(*SCENARIO_NAMES, "all"),
        default=None,
        help="record a demonstration scenario's briefings and summaries (all: twelve)",
    )
    arguments = parser.parse_args(argv)
    if arguments.list:
        for name, case in all_cases().items():
            print(f"{name}  ({case.kind}, {MODEL})")
        return 0
    names: list[str] = list(arguments.cases)
    confirm: Callable[[ScenarioPlan], bool] | None = None
    if arguments.scenario is not None:
        if names:
            print("error: name cases or --scenario, not both", file=sys.stderr)
            return 1
        if not credential_found():
            print(
                "error: no Anthropic credential (ANTHROPIC_API_KEY or an `ant auth login` "
                "profile); nothing was sent",
                file=sys.stderr,
            )
            return 1
        names, confirm = scenario_names(arguments.scenario), confirm_plan
    try:
        results = record(names, force=arguments.force, confirm=confirm)
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
