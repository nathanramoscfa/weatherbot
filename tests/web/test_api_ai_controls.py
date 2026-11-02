# tests/web/test_api_ai_controls.py
"""``PUT /api/ai/pause`` and ``POST /api/ai/allowance``: their limits and their events.

The pause writes a ``pause`` or ``resume`` control row only when it changes, and every
process reads it; an allowance adds more than nothing and at most one day's cap, three
times a day, and a fourth answers 409. Each control row publishes an ``ai`` event that
invalidates ``ai``, through the AI service's publish hook, which ``serve`` sets to the
event hub's ``publish``. Both answer the status, which never carries the credential.
"""

import asyncio
from collections.abc import Iterator
from http import HTTPStatus

import httpx
import pytest
from ai_support import ai_web_state, fake_api_key, ledger_rows, replayed_service

from weatherbot.services.ai.ledger import MAX_ALLOWANCES_PER_DAY
from weatherbot.services.config import AppPaths
from weatherbot.services.events import EventHub, HubEvent, Subscription
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.web.app import WebState, create_app

pytestmark = pytest.mark.anyio

CAP_MICRO_USD = 1_000_000
GRANTED_USD = (0.5, 1.0, 0.25)


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


async def _send(state: WebState, method: str, path: str, body: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app(state))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
        return await client.request(method, path, json=body)


async def _next_event(subscription: Subscription) -> HubEvent:
    return await asyncio.wait_for(anext(subscription), timeout=5.0)


async def _quiet(subscription: Subscription) -> bool:
    """Let a publication scheduled from a worker thread land, then say whether none did."""
    await asyncio.sleep(0.05)
    return not subscription.has_pending


async def test_the_pause_holds_until_lifted_and_publishes_each_change(database: Database) -> None:
    hub = EventHub(asyncio.get_running_loop())
    subscription = hub.subscribe()
    service, replay = replayed_service(database, [], publish=hub.publish)
    state = ai_web_state(database, service, hub=hub)

    paused = await _send(state, "PUT", "/api/ai/pause", {"paused": True})
    pause_event = await _next_event(subscription)
    again = await _send(state, "PUT", "/api/ai/pause", {"paused": True})
    repeated_quietly = await _quiet(subscription)
    resumed = await _send(state, "PUT", "/api/ai/pause", {"paused": False})
    resume_event = await _next_event(subscription)
    await service.close()

    assert (paused.status_code, paused.json()["state"], paused.json()["paused"]) == (
        HTTPStatus.OK,
        "paused",
        True,
    )
    assert again.json()["paused"] is True
    assert repeated_quietly
    assert (resumed.json()["state"], resumed.json()["paused"]) == ("ready", False)
    assert [row.kind for row in ledger_rows(database.engine)] == ["pause", "resume"]
    for event, kind in ((pause_event, "pause"), (resume_event, "resume")):
        assert (event.kind, event.invalidate, event.ai_kind, event.status) == (
            "ai",
            ("ai",),
            kind,
            "control",
        )
        assert event.call_id is not None
    assert fake_api_key() not in paused.text
    assert replay.requests == []


async def test_an_allowance_holds_its_limits_and_publishes_each_one(database: Database) -> None:
    hub = EventHub(asyncio.get_running_loop())
    subscription = hub.subscribe()
    service, _ = replayed_service(database, [], publish=hub.publish)
    state = ai_web_state(database, service, hub=hub)

    refused = [
        await _send(state, "POST", "/api/ai/allowance", {"usd": usd})
        for usd in (0, -1, 0.0000001, 1.01)
    ]
    granted = [await _send(state, "POST", "/api/ai/allowance", {"usd": usd}) for usd in GRANTED_USD]
    events = [await _next_event(subscription) for _ in granted]
    fourth = await _send(state, "POST", "/api/ai/allowance", {"usd": 0.25})
    fourth_quietly = await _quiet(subscription)
    await service.close()

    assert [response.status_code for response in refused] == [HTTPStatus.UNPROCESSABLE_CONTENT] * 4
    assert [response.status_code for response in granted] == [HTTPStatus.OK] * 3
    lefts = [response.json()["today"]["allowances_left"] for response in granted]
    assert lefts == [MAX_ALLOWANCES_PER_DAY - n for n in range(1, MAX_ALLOWANCES_PER_DAY + 1)]
    today = granted[-1].json()["today"]
    assert today["allowance_micro_usd"] == round(sum(GRANTED_USD) * CAP_MICRO_USD)
    assert today["cap_micro_usd"] == CAP_MICRO_USD
    assert fourth.status_code == HTTPStatus.CONFLICT
    assert fourth_quietly
    assert [row.kind for row in ledger_rows(database.engine)] == ["allowance"] * 3
    assert {(event.kind, event.invalidate, event.ai_kind) for event in events} == {
        ("ai", ("ai",), "allowance")
    }


async def test_the_controls_answer_503_without_an_ai_service(database: Database) -> None:
    state = ai_web_state(database, None)

    pause = await _send(state, "PUT", "/api/ai/pause", {"paused": True})
    allowance = await _send(state, "POST", "/api/ai/allowance", {"usd": 0.5})

    for response in (pause, allowance):
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json()["detail"]["reason"] == "disabled"
    assert ledger_rows(database.engine) == []
