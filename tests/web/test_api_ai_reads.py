# tests/web/test_api_ai_reads.py
"""The AI reads: schemas, a ledger with no text, links to public pages only, staleness.

Each read answers in its committed OpenAPI schema; the ledger carries no text; a source
links only to a public page that names no point; and a briefing turns stale. The database
is a per-module template holding the Miami-Dade landmark, the recorded snapshot, and its
first assessment; the products are written through the real services with recorded
answers replayed through the real SDK.
"""

import json
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast, get_args
from urllib.parse import urlsplit

import httpx
import pytest
from ai_support import (
    RecordedAnswer,
    ai_web_state,
    copied_database,
    database_template,
    fake_api_key,
    load_answer,
    message_body,
    replayed_service,
    shared_recorded_snapshot,
    stored_later,
    stored_recorded,
)
from fixture_support import REPOSITORY_ROOT
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from weatherbot.models import LOCATED_SOURCES, SourceId
from weatherbot.services.ai.briefing import BriefingService
from weatherbot.services.ai.display import PUBLIC_PAGES, public_page
from weatherbot.services.ai.narration import NarrationService
from weatherbot.services.ai.service import AiService
from weatherbot.services.ai.summaries import ChangeSummaryService
from weatherbot.services.config import AiSettings
from weatherbot.services.persistence.database import Database
from weatherbot.services.persistence.repositories import AssessmentRepository
from weatherbot.web.app import create_app
from weatherbot.web.map_layers import SNAPSHOT_CACHE
from weatherbot.web.schemas import (
    AiCallsResponse,
    AiStatusResponse,
    BriefingsResponse,
    NarrationsResponse,
    OutlookGraphicsResponse,
    SummariesResponse,
)

pytestmark = pytest.mark.anyio

MIAMI = "Miami-Dade County Hall"
OPENAPI_PATH = REPOSITORY_ROOT / "docs" / "api" / "openapi.json"
READS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("/api/ai", AiStatusResponse),
    ("/api/ai/calls", AiCallsResponse),
    ("/api/ai/briefings", BriefingsResponse),
    ("/api/ai/summaries", SummariesResponse),
    ("/api/ai/narrations", NarrationsResponse),
    ("/api/outlook", OutlookGraphicsResponse),
)
SUMMARY = "The rip current statement for the coast has ended."
PUBLIC_HOSTS = frozenset({"www.nhc.noaa.gov", "alerts.weather.gov"})
CALL_FIELDS = frozenset(
    {
        "id",
        "kind",
        "model",
        "location",
        "status",
        "started_at",
        "finished_at",
        "input_tokens",
        "cache_write_tokens",
        "cache_read_tokens",
        "output_tokens",
        "cost_micro_usd",
        "allowance_micro_usd",
        "stop_reason",
        "refusal_category",
        "error_kind",
    }
)


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return database_template(tmp_path_factory.mktemp("ai-reads"), stored_recorded)


@pytest.fixture
def database(template: Path) -> Iterator[Database]:
    SNAPSHOT_CACHE.clear()
    with copied_database(template) as opened:
        yield opened


async def _get(state: Any, path: str) -> httpx.Response:  # noqa: ANN401 - a WebState
    transport = httpx.ASGITransport(app=create_app(state))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
        return await client.get(path)


def _openapi() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(OPENAPI_PATH.read_text(encoding="utf-8")))


def _conforms(document: dict[str, Any], path: str, payload: object) -> None:
    route = document["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]
    schema = {**route["schema"], "components": document["components"]}
    Draft202012Validator(schema).validate(payload)  # pyright: ignore[reportUnknownMemberType]


async def _products(database: Database) -> AiService:
    """Store a briefing, a change summary, and a narration through replayed answers."""
    recorded = await shared_recorded_snapshot()
    first = AssessmentRepository(database.engine).latest(MIAMI)
    assert first is not None
    later = stored_later(database, recorded, first.assessment, alerts={})
    summary = json.dumps({"summary": SUMMARY, "sources": []})
    service, _ = replayed_service(
        database,
        [
            load_answer("eval-briefing-recorded-miami-dade"),
            RecordedAnswer.json(message_body(summary)),
            load_answer("narration-atl-7d0"),
        ],
        settings=AiSettings(outlook_narration=True),
    )
    briefing = [event async for event in BriefingService(service).stream(MIAMI)]
    assert type(briefing[-1]).__name__ == "Done"
    outcome = await ChangeSummaryService(service).summarize(later.id)
    assert outcome.status == "ok"
    narration = [event async for event in NarrationService(service).stream("atl", "7d0")]
    assert type(narration[-1]).__name__ == "Done"
    return service


async def test_every_ai_read_answers_in_its_schema_without_an_ai_service(
    database: Database,
) -> None:
    document = _openapi()
    state = ai_web_state(database, None)

    for path, model in READS:
        response = await _get(state, path)
        assert response.status_code == HTTPStatus.OK, (path, response.text)
        assert response.headers["cache-control"] == "no-store"
        _conforms(document, path, response.json())
        model.model_validate_json(response.text)

    status = AiStatusResponse.model_validate_json((await _get(state, "/api/ai")).text)
    assert (status.state, status.reason, status.credential_source) == ("off", "disabled", None)


async def test_every_ai_read_answers_in_its_schema_with_stored_products(
    database: Database,
) -> None:
    document = _openapi()
    service = await _products(database)
    state = ai_web_state(database, service)

    bodies: dict[str, Any] = {}
    for path, model in READS:
        response = await _get(state, path)
        assert response.status_code == HTTPStatus.OK, (path, response.text)
        assert fake_api_key() not in response.text
        _conforms(document, path, response.json())
        model.model_validate_json(response.text)
        bodies[path] = response.json()
    await service.close()

    status = bodies["/api/ai"]
    assert status["state"] == "ready"
    kinds = [kind["kind"] for kind in status["today"]["by_kind"]]
    assert kinds == ["briefing", "summary", "narration"]
    assert status["today"]["calls"] == len(bodies["/api/ai/calls"]["calls"]) == len(kinds)
    [location] = bodies["/api/ai/briefings"]["locations"]
    assert location["briefing"]["status"] == "ok"
    assert location["briefing"]["situation"]
    [summary] = bodies["/api/ai/summaries"]["summaries"]
    assert (summary["status"], summary["summary"]) == ("ok", SUMMARY)
    [narration] = bodies["/api/ai/narrations"]["narrations"]
    assert (narration["basin"], narration["horizon"], narration["status"]) == ("atl", "7d0", "ok")
    assert narration["two"]["code"] == "TWO"


async def test_the_ledger_read_carries_no_text(database: Database) -> None:
    service = await _products(database)
    briefing = BriefingService(service).latest(MIAMI).stored
    assert briefing is not None
    assert briefing.content is not None
    situation = briefing.content["briefing"]["situation"]
    state = ai_web_state(database, service)

    response = await _get(state, "/api/ai/calls?limit=100")
    await service.close()

    calls = response.json()["calls"]
    assert calls
    assert all(set(call) == CALL_FIELDS for call in calls)
    assert situation not in response.text
    assert SUMMARY not in response.text
    assert "prompt" not in response.text


def test_a_source_links_only_to_a_public_page_that_names_no_point() -> None:
    assert set(PUBLIC_PAGES) <= set(get_args(SourceId.__value__))
    assert all(public_page(source_id) is None for source_id in LOCATED_SOURCES)
    assert public_page("nws-zones") is None
    for page in PUBLIC_PAGES.values():
        parts = urlsplit(page)
        assert parts.scheme == "https"
        assert parts.hostname in PUBLIC_HOSTS
        assert (parts.query, parts.fragment) == ("", "")


async def test_a_briefing_resolves_its_sources_from_their_records(database: Database) -> None:
    service = await _products(database)
    state = ai_web_state(database, service)

    response = await _get(state, "/api/ai/briefings")
    await service.close()

    [location] = response.json()["locations"]
    sources = location["briefing"]["sources"]
    assert sources
    for source in sources:
        assert source["url"] == public_page(source["source_id"])
        assert source["title"]
    assert {source["url"] for source in sources} <= {None, *PUBLIC_PAGES.values()}


async def test_a_briefing_turns_stale_once_a_newer_assessment_is_stored(
    database: Database,
) -> None:
    service = await _products(database)
    state = ai_web_state(database, service)
    before = (await _get(state, f"/api/ai/briefings?location={MIAMI}")).json()
    recorded = await shared_recorded_snapshot()
    latest = AssessmentRepository(database.engine).latest(MIAMI)
    assert latest is not None
    newer = stored_later(database, recorded, latest.assessment, number=2)

    after = (await _get(state, f"/api/ai/briefings?location={MIAMI}")).json()
    await service.close()

    assert before["locations"][0]["briefing"]["stale"] is False
    [location] = after["locations"]
    assert location["assessment_id"] == newer.id
    assert location["briefing"]["stale"] is True
    assert location["briefing"]["assessment_id"] != newer.id


async def test_a_withheld_product_is_shown_with_its_reason_and_no_text(
    database: Database,
) -> None:
    recorded = await shared_recorded_snapshot()
    first = AssessmentRepository(database.engine).latest(MIAMI)
    assert first is not None
    later = stored_later(database, recorded, first.assessment, alerts={})
    stated = json.dumps({"summary": "It is now level 5, Hurricane Warning.", "sources": []})
    service, _ = replayed_service(database, [RecordedAnswer.json(message_body(stated))])
    outcome = await ChangeSummaryService(service).summarize(later.id)
    state = ai_web_state(database, service)

    response = await _get(state, "/api/ai/summaries")
    await service.close()

    assert outcome.status == "withheld"
    [summary] = response.json()["summaries"]
    assert summary["status"] == "withheld"
    assert summary["withheld_reason"] == outcome.reason
    assert summary["summary"] is None
    assert "Hurricane Warning" not in response.text


async def test_reads_refuse_an_unknown_location_and_a_limit_past_its_bound(
    database: Database,
) -> None:
    state = ai_web_state(database, None)

    unknown = [
        await _get(state, "/api/ai/briefings?location=Nowhere"),
        await _get(state, "/api/ai/summaries?location=Nowhere"),
    ]
    bounds = [
        await _get(state, "/api/ai/calls?limit=101"),
        await _get(state, "/api/ai/calls?limit=0"),
        await _get(state, "/api/ai/summaries?limit=201"),
    ]

    assert [response.status_code for response in unknown] == [HTTPStatus.NOT_FOUND] * 2
    assert [response.status_code for response in bounds] == [HTTPStatus.UNPROCESSABLE_CONTENT] * 3
    assert all("Nowhere" not in response.text for response in unknown)
