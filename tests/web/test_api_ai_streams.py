# tests/web/test_api_ai_streams.py
"""The AI streams over a real loopback server: events in order, refusals, disconnects, slots.

An in-memory transport does not stream, so every test serves the app with ``WebServer``
on an ephemeral loopback port. The database is a per-module template holding both
landmarks and the recorded snapshot; recorded answers replay through the real SDK, and a
held answer (a stream that begins and then waits) stands in for a slow model.
"""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import AsyncExitStack, asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any

import anthropic
import httpx
import httpx2
import pytest
from ai_support import (
    ai_web_state,
    chunked_stream,
    copied_database,
    database_template,
    fake_api_key,
    ledger_rows,
    load_answer,
    load_rounds,
    replayed_service,
)
from eval.chat_cases import CHAT_CASES, store_case_data
from source_support import NOW

from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.schemas import BRIEFING_SECTIONS
from weatherbot.services.ai.service import AiService
from weatherbot.services.ai.tools import TOOL_NAMES
from weatherbot.services.config import AiSettings
from weatherbot.services.persistence.database import Database
from weatherbot.web.app import MAX_AI_STREAMS, WebState, create_app
from weatherbot.web.server import WebServer

pytestmark = pytest.mark.anyio

MIAMI = "Miami-Dade County Hall"
TIMEOUT_S = 10.0
BRIEFING = {"location": MIAMI, "new": True}


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return database_template(tmp_path_factory.mktemp("ai-streams"), store_case_data)


@pytest.fixture
def database(template: Path) -> Iterator[Database]:
    with copied_database(template) as opened:
        yield opened


@asynccontextmanager
async def _served(state: WebState) -> AsyncGenerator[httpx.AsyncClient]:
    """Serve the app on an ephemeral loopback port and yield a client for it."""
    server = WebServer(create_app(state), host="127.0.0.1", port=0, before_stop=(state.hub.close,))
    stop = asyncio.Event()
    task = asyncio.create_task(server.serve(stop))
    await asyncio.wait_for(server.started.wait(), timeout=TIMEOUT_S)
    try:
        async with httpx.AsyncClient(
            base_url=server.address, trust_env=False, timeout=TIMEOUT_S
        ) as client:
            yield client
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=TIMEOUT_S)


async def _events(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> list[Any]:
    async with client.stream("POST", path, json=body) as response:
        assert response.status_code == HTTPStatus.OK
        assert "text/event-stream" in response.headers["content-type"]
        assert response.headers["cache-control"] == "no-store"
        return [
            json.loads(line.removeprefix("data:"))
            async for line in response.aiter_lines()
            if line.startswith("data:")
        ]


async def _slots_free(state: WebState) -> int:
    """Count the free stream slots by taking each, then give them back."""
    taken = 0
    while not state.ai_streams.locked():
        await state.ai_streams.acquire()
        taken += 1
    for _ in range(taken):
        state.ai_streams.release()
    return taken


class _Held:
    """Answers every request with a stream that begins and then waits until it is cancelled."""

    def __init__(self) -> None:
        self.begun = 0
        self.all_begun = asyncio.Event()
        self.expected = 1

    def client(self) -> anthropic.AsyncAnthropic:
        return anthropic.AsyncAnthropic(
            api_key=fake_api_key(),
            max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(
                transport=httpx2.MockTransport(self._handler)
            ),
        )

    def _handler(self, _request: httpx2.Request) -> httpx2.Response:
        headers = {"content-type": "text/event-stream", "request-id": "req_held"}
        return httpx2.Response(HTTPStatus.OK, headers=headers, content=self._body())

    async def _body(self) -> AsyncIterator[bytes]:
        yield chunked_stream("", final=False, thinking=False).encode()
        self.begun += 1
        if self.begun >= self.expected:
            self.all_begun.set()
        await asyncio.Event().wait()


def _held_service(database: Database, held: _Held) -> AiService:
    client = held.client()
    return AiService(
        ai_engine(database.path),
        AiSettings(),
        factory=lambda: client,
        environ={},
        now=lambda: NOW,
    )


async def _settled(database: Database, count: int) -> list[str]:
    """Wait until ``count`` ledger rows are no longer reserved; return their statuses."""
    async with asyncio.timeout(TIMEOUT_S):
        while True:
            statuses = [row.status for row in ledger_rows(database.engine)]
            if len(statuses) == count and "reserved" not in statuses:
                return statuses
            await asyncio.sleep(0.02)


async def test_each_stream_emits_its_typed_events_in_order(database: Database) -> None:
    case = CHAT_CASES[0]
    service, replay = replayed_service(
        database,
        [
            load_answer("eval-briefing-recorded-miami-dade"),
            *load_rounds(case.name),
            load_answer("narration-atl-7d0"),
        ],
        settings=AiSettings(outlook_narration=True),
    )
    state = ai_web_state(database, service)

    async with _served(state) as client:
        briefing = await _events(client, "/api/ai/briefings", {"location": MIAMI})
        chat = await _events(
            client, "/api/ai/chat", {"question": case.question, "location": case.location}
        )
        narration = await _events(client, "/api/ai/narrations", {"basin": "atl", "horizon": "7d0"})
    free = await _slots_free(state)
    await service.close()

    assert [event["kind"] for event in briefing] == ["started", *["section"] * 5, "done"]
    assert briefing[0]["model_name"] == "Claude Sonnet 5.5"
    assert [event["section"] for event in briefing[1:-1]] == list(BRIEFING_SECTIONS)
    assert briefing[-1]["reused"] is False
    kinds = [event["kind"] for event in chat]
    assert (kinds[0], kinds[-1]) == ("started", "done")
    assert "text" in kinds
    assert {event["tool"] for event in chat if event["kind"] == "tool"} <= set(TOOL_NAMES)
    assert chat[-1]["call_ids"]
    assert [event["kind"] for event in narration] == ["started", "done"]
    assert narration[-1]["summary"]
    assert narration[-1]["areas"]
    assert {row.status for row in ledger_rows(database.engine)} == {"ok"}
    assert len(replay.requests) == len(ledger_rows(database.engine))
    assert free == MAX_AI_STREAMS


async def test_a_state_other_than_ready_answers_503_or_429_with_its_reason(
    database: Database,
) -> None:
    paused, paused_replay = replayed_service(database, [])
    capped, capped_replay = replayed_service(database, [], settings=AiSettings(daily_cap_usd=0))
    off, off_replay = replayed_service(database, [], settings=AiSettings(enabled=False))
    cases = (
        (None, HTTPStatus.SERVICE_UNAVAILABLE, "disabled"),
        (off, HTTPStatus.SERVICE_UNAVAILABLE, "disabled"),
        (capped, HTTPStatus.TOO_MANY_REQUESTS, "capped"),
        (paused, HTTPStatus.SERVICE_UNAVAILABLE, "paused"),
    )
    streams = (
        ("/api/ai/briefings", BRIEFING),
        ("/api/ai/chat", {"question": "What is the level?"}),
        ("/api/ai/narrations", {"basin": "atl", "horizon": "7d0"}),
    )
    answers: list[tuple[int, Any]] = []
    for service, _, _ in cases:
        if service is paused:
            paused.ledger.pause()  # the pause is the ledger's: it would hold for every case
        async with _served(ai_web_state(database, service)) as client:
            for path, body in streams:
                response = await client.post(path, json=body)
                answers.append((response.status_code, response.json()))
    for service in (paused, capped, off):
        await service.close()

    expected = [(status, reason) for _, status, reason in cases for _ in streams]
    assert [(code, body["detail"]["reason"]) for code, body in answers] == expected
    assert all(body["detail"]["message"] for _, body in answers)
    assert paused_replay.requests == capped_replay.requests == off_replay.requests == []
    assert [row.kind for row in ledger_rows(database.engine)] == ["pause"]


async def test_a_disconnect_cancels_the_request_and_the_ledger_settles(
    database: Database,
) -> None:
    held = _Held()
    service = _held_service(database, held)
    state = ai_web_state(database, service)

    async with _served(state) as client:
        async with client.stream("POST", "/api/ai/briefings", json=BRIEFING) as response:
            assert response.status_code == HTTPStatus.OK
            await asyncio.wait_for(held.all_begun.wait(), timeout=TIMEOUT_S)
        statuses = await _settled(database, 1)
        free = await _slots_free(state)
    await service.close()

    [row] = ledger_rows(database.engine)
    assert statuses == ["incomplete"]
    assert row.cost_micro_usd == row.ceiling_micro_usd
    assert free == MAX_AI_STREAMS


async def test_a_fifth_concurrent_stream_answers_429_busy(database: Database) -> None:
    held = _Held()
    held.expected = MAX_AI_STREAMS
    service = _held_service(database, held)
    state = ai_web_state(database, service)

    async with _served(state) as client, AsyncExitStack() as streams:
        for _ in range(MAX_AI_STREAMS):
            opened = await streams.enter_async_context(
                client.stream("POST", "/api/ai/briefings", json=BRIEFING)
            )
            assert opened.status_code == HTTPStatus.OK
        await asyncio.wait_for(held.all_begun.wait(), timeout=TIMEOUT_S)
        fifth = await client.post("/api/ai/chat", json={"question": "And now?"})
        await streams.aclose()
        statuses = await _settled(database, MAX_AI_STREAMS)
        free = await _slots_free(state)
    await service.close()

    assert fifth.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert fifth.json()["detail"]["reason"] == "busy"
    assert statuses == ["incomplete"] * MAX_AI_STREAMS
    assert free == MAX_AI_STREAMS
