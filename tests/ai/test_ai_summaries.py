# tests/ai/test_ai_summaries.py
"""``ChangeSummaryService``: one summary per qualifying assessment, never rewritten.

The first stored assessment of the Miami-Dade landmark has only its initial events, so it
is skipped; a later snapshot without the covering alert removes an official product, a
change worth a summary. The answers are hand-written messages replayed through the real
SDK.
"""

import json
from collections.abc import Iterator

import pytest
from ai_support import (
    RecordedAnswer,
    ledger_rows,
    message_body,
    output_rows,
    replayed_service,
    stored_later,
    stored_recorded,
)
from snapshot_support import RecordedSnapshot

from weatherbot.services.ai.service import AiService
from weatherbot.services.ai.summaries import (
    SUMMARY_MAX_TOKENS,
    ChangeSummaryService,
    SummaryOutcome,
    qualifies,
)
from weatherbot.services.config import AiSettings, AppPaths
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import StoredAssessment

pytestmark = pytest.mark.anyio

LOCATION = "Miami-Dade County Hall"
SUMMARY: dict[str, object] = {
    "summary": "The Rip Current Statement no longer covers the location; it stays at level 1.",
    "sources": [],
}


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


def _answer(**changes: object) -> RecordedAnswer:
    return RecordedAnswer.json(message_body(json.dumps(SUMMARY | changes)))


async def _changed(database: Database) -> tuple[RecordedSnapshot, StoredAssessment]:
    recorded, first = await stored_recorded(database)
    later = stored_later(database, recorded, first.assessment, alerts={})
    return recorded, later


async def _summarize(service: AiService, assessment_id: int) -> SummaryOutcome:
    return await ChangeSummaryService(service).summarize(assessment_id)


async def test_a_change_is_summarized_with_the_summary_model_and_stored(database: Database) -> None:
    _, later = await _changed(database)
    assert [event.kind for event in later.changes] == ["official_removed"]
    settings = AiSettings(summary_model="claude-haiku-5-5")
    service, replay = replayed_service(database, [_answer()], settings=settings)

    outcome = await _summarize(service, later.id)

    assert outcome.status == "ok"
    assert outcome.summary is not None
    assert outcome.summary.summary == SUMMARY["summary"]
    body = replay.requests[0].body
    assert body["model"] == "claude-haiku-5-5"
    assert body["max_tokens"] == SUMMARY_MAX_TOKENS
    assert body["output_config"]["effort"] == "low"  # pyright: ignore[reportIndexIssue, reportArgumentType, reportCallIssue] - a JSON body
    assert "Task: change summary" in json.dumps(body["messages"])
    [row] = output_rows(database.engine)
    assert (row.kind, row.status, row.assessment_id, row.model) == (
        "summary",
        "ok",
        later.id,
        "claude-haiku-5-5",
    )
    [call] = ledger_rows(database.engine)
    assert (call.kind, call.model, call.status) == ("summary", "claude-haiku-5-5", "ok")
    assert row.call_id == call.id
    await service.close()


async def test_a_stored_summary_is_never_rewritten(database: Database) -> None:
    _, later = await _changed(database)
    service, replay = replayed_service(database, [_answer(), _answer()])
    first = await _summarize(service, later.id)

    again = await _summarize(service, later.id)

    assert again.reused
    assert (again.status, again.output_id) == ("ok", first.output_id)
    assert again.summary == first.summary
    assert len(replay.requests) == 1
    assert len(output_rows(database.engine)) == 1
    await service.close()


async def test_a_first_assessment_and_an_unchanged_one_are_skipped(database: Database) -> None:
    recorded, first = await stored_recorded(database)
    same = stored_later(database, recorded, first.assessment)
    service, replay = replayed_service(database, [])

    assert await _summarize(service, first.id) == SummaryOutcome("skipped", reason="first")
    assert await _summarize(service, same.id) == SummaryOutcome("skipped", reason="no_changes")
    assert replay.requests == []
    assert not qualifies(())
    await service.close()


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (_answer(summary="It is level 4 now."), "level"),
        (_answer(sources=["S42"]), "source"),
        (_answer(summary="See www.example.invalid."), "url"),
        (RecordedAnswer.json(message_body('{"summary": "x"}')), "invalid_output"),
        (
            RecordedAnswer.json(message_body(json.dumps(SUMMARY), stop_reason="max_tokens")),
            "incomplete",
        ),
    ],
)
async def test_a_failing_summary_is_stored_withheld_without_its_text(
    database: Database, answer: RecordedAnswer, reason: str
) -> None:
    _, later = await _changed(database)
    service, _ = replayed_service(database, [answer])

    outcome = await _summarize(service, later.id)

    assert (outcome.status, outcome.reason, outcome.summary) == ("withheld", reason, None)
    [row] = output_rows(database.engine)
    assert (row.status, row.withheld_reason, row.content) == ("withheld", reason, None)
    assert row.call_id == ledger_rows(database.engine)[0].id
    reused = await _summarize(service, later.id)
    assert (reused.status, reused.reused) == ("withheld", True)
    await service.close()


@pytest.mark.parametrize(
    ("answer", "settings", "reason"),
    [
        (None, AiSettings(enabled=False), "disabled"),
        (RecordedAnswer.error(529, "overloaded_error"), None, "overloaded"),
        (RecordedAnswer.json(message_body("", stop_reason="refusal")), None, "declined"),
    ],
)
async def test_an_unavailable_summary_stores_nothing(
    database: Database,
    answer: RecordedAnswer | None,
    settings: AiSettings | None,
    reason: str,
) -> None:
    _, later = await _changed(database)
    service, _ = replayed_service(database, [answer] if answer else [], settings=settings)

    outcome = await _summarize(service, later.id)

    assert (outcome.status, outcome.reason) == ("unavailable", reason)
    assert output_rows(database.engine) == []
    await service.close()


async def test_an_unknown_assessment_and_a_huge_context_are_unavailable(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, later = await _changed(database)
    service, replay = replayed_service(database, [])

    assert await _summarize(service, 999) == SummaryOutcome("unavailable", reason="no_assessment")
    monkeypatch.setattr("weatherbot.services.ai.context.CONTEXT_LIMIT", 10)
    assert await _summarize(service, later.id) == SummaryOutcome("unavailable", reason="too_large")
    assert replay.requests == []
    await service.close()


async def test_the_latest_summaries_come_newest_first(database: Database) -> None:
    recorded, first = await stored_recorded(database)
    second = stored_later(database, recorded, first.assessment, 1, alerts={})
    third = stored_later(database, recorded, second.assessment, 2)
    service, replay = replayed_service(database, [_answer(), _answer()])
    summaries = ChangeSummaryService(service)
    await summaries.summarize(second.id)
    await summaries.summarize(third.id)

    listed = summaries.latest(LOCATION, 5)

    assert [event.kind for event in third.changes] == ["official_added"]
    assert len(replay.requests) == 2  # noqa: PLR2004 - one request per qualifying assessment
    assert [row.assessment_id for row in listed] == [third.id, second.id]
    assert [row.assessment_id for row in summaries.latest(LOCATION, 1)] == [third.id]
    assert summaries.latest("Elsewhere", 5) == ()
    await service.close()
