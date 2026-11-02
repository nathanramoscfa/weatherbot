# tests/ai/ai_support.py
"""Recorded Anthropic answers replayed through the real SDK, for the AI tests.

The SDK talks through ``httpx2``, which respx never sees, so a replayed client is an
``AsyncAnthropic`` whose ``http_client`` is the SDK's ``DefaultAsyncHttpxClient`` around an
``httpx2.MockTransport``. ``Replay`` serves ``RecordedAnswer``s in order (a JSON body, a
server-sent event body, or a status with an error body) and logs each request's path and
decoded body, never its headers. The key is built at run time, so no tracked byte holds a
key shape; ``tests/conftest.py`` keeps every test away from the operator's credential.

Recorded answers live in ``tests/fixtures/ai/`` (``scripts/record_ai_fixtures.py``);
hand-written error bodies and stops are built here, with synthetic messages.
"""

import asyncio
import json
import shutil
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Self, cast
from uuid import UUID

import anthropic
import httpx2
from snapshot_support import RecordedSnapshot, recorded_snapshot
from source_support import NOW
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from weatherbot.engine import assess, diff
from weatherbot.models import Assessment, Snapshot, Thresholds
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.service import AiPublish, AiService
from weatherbot.services.config import AiSettings, AppPaths, Settings
from weatherbot.services.events import EventHub
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    LocationRepository,
    SnapshotRepository,
    StoredAssessment,
)
from weatherbot.services.persistence.tables import AiCallRow, AiOutputRow
from weatherbot.web.app import WebState

FIXTURES: Final = Path(__file__).resolve().parents[1] / "fixtures" / "ai"
MODEL: Final = "claude-sonnet-5-5"
REQUEST_ID: Final = "req_replayed_0001"
CONNECTION_FAILURE: Final = 0
"""The status that makes the replay fail the connection instead of answering."""
HEADER_NAMES: Final = (
    "authorization",
    "x-api-key",
    "anthropic-organization-id",
    "anthropic-version",
    "anthropic-ratelimit",
    "request-id",
    "retry-after",
    "set-cookie",
    "cf-ray",
    "x-stainless",
)
"""Header names a recording must never carry; ``test_ai_fixtures`` scans for each."""


def fake_api_key() -> str:
    """Build a key-shaped string at run time; no tracked byte holds one.

    Returns:
        A syntactically plausible, worthless key.
    """
    return "sk-" + "ant-" + "test-" + "0" * 40


@dataclass(frozen=True)
class RecordedAnswer:
    """One answer the replay serves: a status, a body, and its content type."""

    status: int = 200
    body: bytes = b""
    content_type: str = "application/json"
    request_id: str | None = REQUEST_ID

    @classmethod
    def json(cls, payload: object, *, status: int = 200) -> Self:
        """A JSON answer.

        Args:
            payload: The body.
            status: The HTTP status.

        Returns:
            The answer.
        """
        return cls(status=status, body=json.dumps(payload).encode())

    @classmethod
    def events(cls, text: str) -> Self:
        """A server-sent event stream.

        Args:
            text: The raw stream.

        Returns:
            The answer.
        """
        return cls(body=text.encode(), content_type="text/event-stream")

    @classmethod
    def error(cls, status: int, error_type: str) -> Self:
        """A hand-written error answer with a synthetic message.

        Args:
            status: The HTTP status.
            error_type: The API's error type, such as ``rate_limit_error``.

        Returns:
            The answer.
        """
        payload = {
            "type": "error",
            "error": {"type": error_type, "message": f"{error_type} (synthetic)"},
        }
        return cls.json(payload, status=status)

    @classmethod
    def unreachable(cls) -> Self:
        """A connection that fails before any answer.

        Returns:
            The answer; the replay raises ``httpx2.ConnectError`` for it.
        """
        return cls(status=CONNECTION_FAILURE, request_id=None)


@dataclass(frozen=True)
class LoggedRequest:
    """What the replay saw of a request: its path and body, decoded and raw; never a header."""

    path: str
    body: dict[str, object]
    content: bytes = b""


@dataclass
class Replay:
    """Serves recorded answers in order and logs every request."""

    answers: list[RecordedAnswer]
    requests: list[LoggedRequest] = field(default_factory=list[LoggedRequest])

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        """Answer one request with the next recorded answer.

        Args:
            request: The SDK's request.

        Returns:
            The answer.
        """
        body: object = json.loads(request.content) if request.content else {}
        assert isinstance(body, dict)
        self.requests.append(LoggedRequest(request.url.path, body, request.content))  # pyright: ignore[reportUnknownArgumentType]
        assert self.answers, "the replay has no answer left"
        answer = self.answers.pop(0)
        if answer.status == CONNECTION_FAILURE:
            message = "connection refused (synthetic)"
            raise httpx2.ConnectError(message, request=request)
        headers = {"content-type": answer.content_type}
        if answer.request_id is not None:
            headers["request-id"] = answer.request_id
        return httpx2.Response(answer.status, content=answer.body, headers=headers)


def replay_client(answers: Sequence[RecordedAnswer]) -> tuple[anthropic.AsyncAnthropic, Replay]:
    """Build a client that replays answers through the real SDK, with no retries.

    Args:
        answers: The answers, in the order requests will get them.

    Returns:
        The client and its replay.
    """
    replay = Replay(list(answers))
    client = anthropic.AsyncAnthropic(
        api_key=fake_api_key(),
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(
            transport=httpx2.MockTransport(replay.handler)
        ),
    )
    return client, replay


def load_answer(name: str) -> RecordedAnswer:
    """Load a recorded answer from ``tests/fixtures/ai/``: ``<name>.json`` or ``<name>.sse``.

    Args:
        name: The case.

    Returns:
        The answer.
    """
    as_json = FIXTURES / f"{name}.json"
    if as_json.is_file():
        return RecordedAnswer(body=as_json.read_bytes())
    return RecordedAnswer.events((FIXTURES / f"{name}.sse").read_text(encoding="utf-8"))


def load_rounds(name: str) -> list[RecordedAnswer]:
    """Load a recorded chat turn's rounds from ``tests/fixtures/ai/<name>.json``, in order.

    Args:
        name: The chat case.

    Returns:
        One event-stream answer per round.
    """
    document = _mapping(json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")))
    rounds = cast("list[str]", document["rounds"])
    return [RecordedAnswer.events(text) for text in rounds]


def recorded_tool_names(name: str) -> list[str]:
    """The tools a recorded chat turn looked up, in order.

    Args:
        name: The chat case.

    Returns:
        Each ``tool_use`` block's name, round by round.
    """
    document = _mapping(json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")))
    return [
        str(block["name"])
        for text in cast("list[str]", document["rounds"])
        for block in stream_blocks(text)
        if block["type"] == "tool_use"
    ]


def stream_blocks(text: str) -> list[dict[str, object]]:
    """Rebuild a recorded stream's final content blocks as the API sent them.

    Args:
        text: A raw event stream.

    Returns:
        Each block from its ``content_block_start``, with its text, thinking, signature,
        and tool input deltas applied, in index order.
    """
    blocks: dict[int, dict[str, object]] = {}
    partial: dict[int, str] = {}
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        event = _mapping(json.loads(line.removeprefix("data:")))
        if event.get("type") == "content_block_start":
            index = cast("int", event["index"])
            blocks[index] = dict(_mapping(event["content_block"]))
        elif event.get("type") == "content_block_delta":
            index = cast("int", event["index"])
            delta = _mapping(event["delta"])
            block = blocks[index]
            kind = delta["type"]
            if kind == "text_delta":
                block["text"] = cast("str", block["text"]) + cast("str", delta["text"])
            elif kind == "thinking_delta":
                block["thinking"] = cast("str", block["thinking"]) + cast("str", delta["thinking"])
            elif kind == "signature_delta":
                block["signature"] = cast("str", delta["signature"])
            elif kind == "input_json_delta":
                partial[index] = partial.get(index, "") + cast("str", delta["partial_json"])
    for index, raw in partial.items():
        blocks[index]["input"] = json.loads(raw) if raw else {}
    return [blocks[index] for index in sorted(blocks)]


def recorded_usage(name: str) -> dict[str, int]:
    """Read a recording's final usage: the JSON body's, or the stream's merged events'.

    Args:
        name: The case.

    Returns:
        The usage's integer fields.
    """
    as_json = FIXTURES / f"{name}.json"
    usage: dict[str, object] = {}
    if as_json.is_file():
        usage.update(_mapping(_mapping(json.loads(as_json.read_text(encoding="utf-8")))["usage"]))
    else:
        for line in (FIXTURES / f"{name}.sse").read_text(encoding="utf-8").splitlines():
            if not line.startswith("data:"):
                continue
            event = _mapping(json.loads(line.removeprefix("data:")))
            if event.get("type") == "message_start":
                usage.update(_mapping(_mapping(event["message"])["usage"]))
            elif event.get("type") == "message_delta":
                delta = _mapping(event["usage"])
                usage.update({key: value for key, value in delta.items() if value is not None})
    flat = {key: value for key, value in usage.items() if isinstance(value, int)}
    creation = _mapping(usage.get("cache_creation") or {})
    flat.update({key: value for key, value in creation.items() if isinstance(value, int)})
    return flat


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def message_body(
    text: str,
    *,
    stop_reason: str = "end_turn",
    stop_details: dict[str, object] | None = None,
    input_tokens: int = 20,
    output_tokens: int = 5,
) -> dict[str, object]:
    """A hand-written message body, for stops a recording cannot provoke.

    Args:
        text: The answer's text.
        stop_reason: Why it stopped.
        stop_details: A refusal's details.
        input_tokens: Uncached input.
        output_tokens: Output.

    Returns:
        The body.
    """
    return {
        "id": "msg_synthetic",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "stop_details": stop_details,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


def event_stream(text: str, *, final: bool = True, output_tokens: int = 5) -> str:
    """A hand-written event stream; ``final=False`` ends it before ``message_stop``.

    Args:
        text: The streamed text.
        final: Whether the stream carries its final events.
        output_tokens: The output the final ``message_delta`` reports.

    Returns:
        The raw stream.
    """
    start = message_body("", output_tokens=1)
    start["content"] = []
    start["stop_reason"] = None
    events: list[tuple[str, object]] = [
        ("message_start", {"type": "message_start", "message": start}),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text},
            },
        ),
    ]
    if final:
        events += [
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": output_tokens},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


def ledger_rows(engine: Engine) -> list[AiCallRow]:
    """Read every ledger row, oldest first.

    Args:
        engine: Any engine on the database.

    Returns:
        The rows, detached.
    """
    with Session(engine, expire_on_commit=False) as session:
        return list(session.scalars(select(AiCallRow).order_by(AiCallRow.id)).all())


def chunked_stream(  # noqa: PLR0913 - a stream's shape, keyword-only
    text: str,
    *,
    chunk: int = 40,
    stop_reason: str = "end_turn",
    final: bool = True,
    output_tokens: int = 50,
    thinking: bool = True,
) -> str:
    """A hand-written stream whose text arrives in pieces, after a thinking block.

    Args:
        text: The streamed text.
        chunk: How many characters each text delta carries.
        stop_reason: Why the message stopped.
        final: Whether the stream carries its final events; ``False`` cuts it.
        output_tokens: The output the final ``message_delta`` reports.
        thinking: Whether an (omitted) thinking block comes first.

    Returns:
        The raw stream.
    """
    start = message_body("", output_tokens=1)
    start["content"] = []
    start["stop_reason"] = None
    events: list[tuple[str, object]] = [
        ("message_start", {"type": "message_start", "message": start})
    ]
    index = 0
    if thinking:
        events += [
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "thinking", "thinking": "", "signature": ""},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "signature_delta", "signature": "c3ludGhldGlj"},
                },
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ]
        index = 1
    events.append(
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": index,
                "content_block": {"type": "text", "text": ""},
            },
        )
    )
    events += [
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "text_delta", "text": text[offset : offset + chunk]},
            },
        )
        for offset in range(0, len(text), chunk)
    ]
    if final:
        events += [
            ("content_block_stop", {"type": "content_block_stop", "index": index}),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                    "usage": {"output_tokens": output_tokens},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


def tool_stream(*calls: tuple[str, object], text: str = "") -> str:
    """A hand-written stream that asks for tools: an omitted thinking block, any text, the calls.

    Args:
        *calls: Each call's tool name and input, in order; ids are ``toolu_1``, ``toolu_2``...
        text: Text the model writes before its calls.

    Returns:
        The raw stream, ending with the ``tool_use`` stop.
    """
    start = message_body("", output_tokens=1)
    start["content"] = []
    start["stop_reason"] = None
    events: list[tuple[str, object]] = [
        ("message_start", {"type": "message_start", "message": start}),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking", "thinking": "", "signature": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "signature_delta", "signature": "c3ludGhldGlj"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
    ]
    blocks: list[tuple[dict[str, object], dict[str, object] | None]] = []
    if text:
        written: dict[str, object] = {"type": "text_delta", "text": text}
        blocks.append(({"type": "text", "text": ""}, written))
    for number, (name, arguments) in enumerate(calls, start=1):
        call: dict[str, object] = {
            "type": "tool_use",
            "id": f"toolu_{number}",
            "name": name,
            "input": {},
        }
        partial: dict[str, object] = {
            "type": "input_json_delta",
            "partial_json": json.dumps(arguments),
        }
        blocks.append((call, partial))
    for index, (block, delta) in enumerate(blocks, start=1):
        events.append(
            (
                "content_block_start",
                {"type": "content_block_start", "index": index, "content_block": block},
            )
        )
        if delta is not None:
            events.append(
                (
                    "content_block_delta",
                    {"type": "content_block_delta", "index": index, "delta": delta},
                )
            )
        events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
    events += [
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                "usage": {"output_tokens": 30},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


_RECORDED: list[RecordedSnapshot] = []
"""The recorded snapshot, built once per process: its models are frozen, so tests share it."""


async def shared_recorded_snapshot() -> RecordedSnapshot:
    """Build the recorded snapshot once per process and share it.

    Returns:
        The recorded snapshot, its location, and its answers.
    """
    if not _RECORDED:
        _RECORDED.append(await recorded_snapshot())
    return _RECORDED[0]


async def stored_recorded(database: Database) -> tuple[RecordedSnapshot, StoredAssessment]:
    """Store the Miami-Dade landmark, the recorded snapshot, and its first assessment.

    Args:
        database: The open database.

    Returns:
        The recorded snapshot and the stored assessment.
    """
    recorded = await shared_recorded_snapshot()
    LocationRepository(database.engine).add(recorded.location)
    SnapshotRepository(database.engine).save(recorded.snapshot, recorded.responses)
    assessment = assess(recorded.snapshot, recorded.location, Thresholds())
    stored = AssessmentRepository(database.engine).save(assessment, diff(None, assessment))
    return recorded, stored


def stored_later(
    database: Database,
    recorded: RecordedSnapshot,
    previous: Assessment,
    number: int = 1,
    **changes: object,
) -> StoredAssessment:
    """Store the recorded records as a later snapshot, ``number`` hours on, and its assessment.

    Args:
        database: The open database.
        recorded: The recorded snapshot.
        previous: The location's previous assessment.
        number: How many hours later.
        **changes: Snapshot fields to replace, such as ``alerts={}``.

    Returns:
        The stored assessment, with its changes from ``previous``.
    """
    fields = {name: getattr(recorded.snapshot, name) for name in Snapshot.model_fields}
    at = recorded.snapshot.completed_at + timedelta(hours=number)
    moved = {"snapshot_id": UUID(int=number), "started_at": at, "completed_at": at}
    later = Snapshot.model_validate(fields | moved | changes)
    SnapshotRepository(database.engine).save(later)
    assessment = assess(later, recorded.location, Thresholds())
    return AssessmentRepository(database.engine).save(assessment, diff(previous, assessment))


def replayed_service(
    database: Database,
    answers: Sequence[RecordedAnswer],
    *,
    settings: AiSettings | None = None,
    now: Callable[[], datetime] = lambda: NOW,
    publish: AiPublish | None = None,
) -> tuple[AiService, Replay]:
    """An AI service on the AI engine whose client replays answers.

    Args:
        database: The open database.
        answers: The answers, in order.
        settings: The ``[ai]`` table; the defaults when omitted.
        now: The clock.
        publish: The service's publish hook, such as an event hub's ``publish``.

    Returns:
        The service and its replay.
    """
    client, replay = replay_client(answers)
    service = AiService(
        ai_engine(database.path),
        settings or AiSettings(),
        factory=lambda: client,
        environ={},
        now=now,
        local_zone=UTC,
        publish=publish,
    )
    return service, replay


def database_template(
    directory: Path, store: Callable[[Database], Coroutine[Any, Any, object]]
) -> Path:
    """Build a database once, at the head revision, with whatever ``store`` writes.

    A module fixture builds it once and each test copies it (``copied_database``), so a
    test does not store the recorded snapshot again (issue #82).

    Args:
        directory: An empty directory of the module's own.
        store: Writes the records, such as ``stored_recorded`` or ``store_case_data``.

    Returns:
        The closed database file.
    """
    paths = AppPaths(config_dir=directory / "config", data_dir=directory / "data")
    with open_database(paths, now=lambda: NOW) as database:
        asyncio.run(store(database))
    return paths.database_path


def copied_database(template: Path) -> Database:
    """Open a copy of a template as this test's database (its data directory's own file).

    Args:
        template: A file ``database_template`` built.

    Returns:
        The open database; close it when done.
    """
    paths = AppPaths.resolve()
    paths.database_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, paths.database_path)
    return open_database(paths, now=lambda: NOW)


def ai_web_state(
    database: Database,
    ai: AiService | None,
    *,
    hub: EventHub | None = None,
    clock: Callable[[], datetime] = lambda: NOW,
) -> WebState:
    """A web state over the test's database with an AI service (or none).

    Args:
        database: The open database.
        ai: The AI service, or ``None`` for AI off.
        hub: The event hub; a new one when omitted.
        clock: The server's clock.

    Returns:
        The state.
    """
    return WebState(
        database=database,
        paths=AppPaths.resolve(),
        settings=Settings(),
        clock=clock,
        started_at=clock(),
        hub=hub or EventHub(),
        ai=ai,
    )


def sse_payloads(text: str) -> list[dict[str, object]]:
    """Read every ``data:`` frame of a server-sent event body as JSON.

    Args:
        text: The body.

    Returns:
        Each frame's object, in order.
    """
    return [
        _mapping(json.loads(line.removeprefix("data:")))
        for line in text.splitlines()
        if line.startswith("data:")
    ]


def output_rows(engine: Engine) -> list[AiOutputRow]:
    """Read every stored AI output, oldest first.

    Args:
        engine: Any engine on the database.

    Returns:
        The rows, detached.
    """
    with Session(engine, expire_on_commit=False) as session:
        return list(session.scalars(select(AiOutputRow).order_by(AiOutputRow.id)).all())
