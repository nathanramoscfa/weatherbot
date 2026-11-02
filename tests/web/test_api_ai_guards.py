# tests/web/test_api_ai_guards.py
"""Every AI route sits behind Phase 5's guards: a hostile page can neither spend nor read.

Each spending route (the three streams and the two controls) refuses a foreign ``Origin``
and a cross-site ``Sec-Fetch-Site`` with 403 and a body that is not JSON with 415, before
it reaches the AI service: no request is sent and no ledger row is written. Each AI read
refuses a request a browser marks cross-site.
"""

from collections.abc import Iterator
from http import HTTPStatus

import httpx
import pytest
from ai_support import ai_web_state, ledger_rows, replayed_service

from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.web.app import create_app

pytestmark = pytest.mark.anyio

WRITES: tuple[tuple[str, str, dict[str, object]], ...] = (
    ("POST", "/api/ai/briefings", {"location": "Miami-Dade County Hall"}),
    ("POST", "/api/ai/chat", {"question": "What is the level?"}),
    ("POST", "/api/ai/narrations", {"basin": "atl", "horizon": "7d0"}),
    ("PUT", "/api/ai/pause", {"paused": True}),
    ("POST", "/api/ai/allowance", {"usd": 0.5}),
)
READS: tuple[str, ...] = (
    "/api/ai",
    "/api/ai/calls",
    "/api/ai/briefings",
    "/api/ai/summaries",
    "/api/ai/narrations",
    "/api/outlook",
    "/api/outlook/atl/7d0",
)
SAME_ORIGIN = "http://127.0.0.1:8765"


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


async def test_every_ai_write_refuses_a_cross_site_or_non_json_request(
    database: Database,
) -> None:
    service, replay = replayed_service(database, [])
    transport = httpx.ASGITransport(app=create_app(ai_web_state(database, service)))

    refused: list[tuple[str, int, int, int]] = []
    async with httpx.AsyncClient(transport=transport, base_url=SAME_ORIGIN) as client:
        for method, path, body in WRITES:
            foreign = await client.request(
                method, path, json=body, headers={"Origin": "https://attacker.example"}
            )
            cross_site = await client.request(
                method,
                path,
                json=body,
                headers={"Origin": SAME_ORIGIN, "Sec-Fetch-Site": "cross-site"},
            )
            form = await client.request(
                method,
                path,
                content=b"paused=true",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            refused.append((path, foreign.status_code, cross_site.status_code, form.status_code))
    await service.close()

    forbidden, unsupported = HTTPStatus.FORBIDDEN, HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    assert refused == [(path, forbidden, forbidden, unsupported) for _, path, _ in WRITES]
    assert replay.requests == []
    assert ledger_rows(database.engine) == []


async def test_every_ai_read_refuses_a_cross_site_request(database: Database) -> None:
    transport = httpx.ASGITransport(app=create_app(ai_web_state(database, None)))

    async with httpx.AsyncClient(transport=transport, base_url=SAME_ORIGIN) as client:
        answers = {
            path: (
                await client.get(path, headers={"Sec-Fetch-Site": "cross-site"}),
                await client.get(path, headers={"Sec-Fetch-Site": "same-site"}),
            )
            for path in READS
        }

    for path, (cross_site, same_site) in answers.items():
        assert cross_site.status_code == HTTPStatus.FORBIDDEN, path
        assert same_site.status_code == HTTPStatus.FORBIDDEN, path
        assert cross_site.headers["cache-control"] == "no-store", path
