# tests/web/test_api_health_ai.py
"""``GET /api/health``'s ``ai`` block: every state, read without a request, and no secret."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
from ai_support import RecordedAnswer, Replay, fake_api_key, replay_client

from weatherbot.services.ai.client import default_client
from weatherbot.services.ai.errors import AiUnavailable
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.service import AiService, smallest_ceiling
from weatherbot.services.config import AiSettings, AppPaths, Settings
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.web.app import WebState, create_app

NOW = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
CAP = 1_000_000


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve(), now=lambda: NOW) as opened:
        yield opened


def _health(database: Database, ai: AiService | None) -> dict[str, object]:
    state = WebState(
        database=database,
        paths=AppPaths.resolve(),
        settings=Settings(),
        clock=lambda: NOW,
        started_at=NOW,
        ai=ai,
    )

    async def query() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(state))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8765"
        ) as client:
            return await client.get("/api/health")

    response = asyncio.run(query())
    assert response.status_code == httpx.codes.OK
    assert fake_api_key() not in response.text
    body = response.json()
    assert isinstance(body, dict)
    ai_block = body["ai"]  # pyright: ignore[reportUnknownVariableType]
    assert isinstance(ai_block, dict)
    return ai_block  # pyright: ignore[reportUnknownVariableType]


def _service(
    database: Database,
    *,
    settings: AiSettings | None = None,
    environ: dict[str, str] | None = None,
    answers: list[RecordedAnswer] | None = None,
) -> tuple[AiService, Replay]:
    client, replay = replay_client(answers or [])
    service = AiService(
        ai_engine(database.path),
        settings or AiSettings(),
        factory=lambda: client,
        environ={"ANTHROPIC_API_KEY": fake_api_key()} if environ is None else environ,
        now=lambda: NOW,
        local_zone=UTC,
    )
    return service, replay


def test_without_an_ai_service_it_reads_off_disabled(database: Database) -> None:
    assert _health(database, None) == {
        "state": "off",
        "reason": "disabled",
        "spent_micro_usd": 0,
        "cap_micro_usd": 0,
    }


def test_with_no_credential_it_reads_off_no_credential_and_sends_nothing(
    database: Database,
) -> None:
    service = AiService(
        ai_engine(database.path),
        AiSettings(),
        factory=default_client,
        environ={"ANTHROPIC_API_KEY": ""},
        now=lambda: NOW,
        local_zone=UTC,
    )

    block = _health(database, service)
    asyncio.run(service.close())

    assert block == {
        "state": "off",
        "reason": "no_credential",
        "spent_micro_usd": 0,
        "cap_micro_usd": CAP,
    }


def test_with_a_credential_it_reads_ready_without_a_request(database: Database) -> None:
    service, replay = _service(database)

    block = _health(database, service)
    asyncio.run(service.close())

    assert (block["state"], block["reason"]) == ("ready", None)
    assert replay.requests == []


def test_todays_spend_counts_settled_cost_and_open_reservations(database: Database) -> None:
    service, _ = _service(database)
    service.ledger.reserve("briefing", "claude-sonnet-5-5", None, None, 30_000)
    service.ledger.allow(250_000)

    block = _health(database, service)
    asyncio.run(service.close())

    assert (block["spent_micro_usd"], block["cap_micro_usd"]) == (30_000, CAP + 250_000)


def test_the_pause_reads_paused(database: Database) -> None:
    service, _ = _service(database)
    service.ledger.pause()

    block = _health(database, service)
    asyncio.run(service.close())

    assert (block["state"], block["reason"]) == ("paused", "paused")


def test_a_spent_cap_reads_capped(database: Database) -> None:
    cap = smallest_ceiling("claude-sonnet-5-5") - 1
    service, _ = _service(database, settings=AiSettings(daily_cap_usd=cap / 1_000_000))

    block = _health(database, service)
    asyncio.run(service.close())

    assert (block["state"], block["reason"]) == ("capped", "capped")


def test_ai_turned_off_reads_off_disabled(database: Database) -> None:
    service, _ = _service(database, settings=AiSettings(enabled=False))

    block = _health(database, service)
    asyncio.run(service.close())

    assert (block["state"], block["reason"]) == ("off", "disabled")


def test_three_authentication_failures_read_unavailable(database: Database) -> None:
    unauthorized = RecordedAnswer.error(401, "authentication_error")
    service, _ = _service(database, answers=[unauthorized] * 3)
    params = {"max_tokens": 8, "messages": [{"role": "user", "content": "hi"}]}

    async def send() -> None:
        await service.caller().create(
            kind="chat",
            model="claude-sonnet-5-5",
            location=None,
            prompt_version=None,
            params=params,
        )

    for _ in range(3):
        with pytest.raises(AiUnavailable, match="authentication failed"):
            asyncio.run(send())
    block = _health(database, service)
    asyncio.run(service.close())

    assert (block["state"], block["reason"]) == ("unavailable", "auth_failed")
