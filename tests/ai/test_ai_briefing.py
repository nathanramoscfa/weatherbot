# tests/ai/test_ai_briefing.py
"""``BriefingService``: sections released in order, a bad one never, reuse, staleness, failures.

The location is the Miami-Dade landmark over the recorded snapshot, stored as ``status``
stores it. The answers are hand-written streams replayed through the real SDK, their text
arriving in pieces after an omitted thinking block, as a structured stream arrives.
"""

import json
import logging
from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from ai_support import (
    RecordedAnswer,
    chunked_stream,
    ledger_rows,
    message_body,
    output_rows,
    replayed_service,
    stored_later,
    stored_recorded,
)

from weatherbot.models import Thresholds
from weatherbot.services.ai.briefing import (
    BRIEFING_MAX_TOKENS,
    BriefingEvent,
    BriefingService,
    Done,
    Section,
    Started,
    Unavailable,
    Withheld,
    completed_sections,
    section_text,
)
from weatherbot.services.ai.context import SourceRef
from weatherbot.services.ai.prompts import prompt_version
from weatherbot.services.ai.schemas import BRIEFING_SECTIONS, SourceNote, TimelineItem
from weatherbot.services.ai.service import AiService
from weatherbot.services.config import AiSettings, AppPaths
from weatherbot.services.persistence.database import Database, open_database

pytestmark = pytest.mark.anyio

LOCATION = "Miami-Dade County Hall"
HIDDEN_SENTENCE = "this sentence must never be shown or stored"
VALID: dict[str, Any] = {
    "situation": "Hurricane Simon is far to the west, beyond 800 km (500 mi) away [S1].",
    "what_it_means_here": (
        "Weatherbot's level for Miami-Dade County Hall is at least level 1, All Clear: no "
        "rule matched, and some inputs were not available [S2]."
    ),
    "timeline": [
        {"when": "2026-10-16T18:00Z", "what": "Simon passes far away.", "sources": ["S2"]}
    ],
    "actions": ["Normal activities.", "Follow the instructions of your local officials."],
    "sources": [{"key": "S1", "why": "the covering alert"}, {"key": "S2", "why": "wind odds"}],
}


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


def _text(**changes: object) -> str:
    return json.dumps(VALID | changes)


def _stream(text: str, **options: Any) -> RecordedAnswer:  # noqa: ANN401 - chunked_stream's options
    return RecordedAnswer.events(chunked_stream(text, **options))


async def _events(service: AiService, *, new: bool = False) -> list[BriefingEvent]:
    briefings = BriefingService(service)
    return [event async for event in briefings.stream(LOCATION, new=new)]


def _sections(events: Sequence[BriefingEvent]) -> list[str]:
    return [event.name for event in events if isinstance(event, Section)]


# Released in order ------------------------------------------------------------------------


async def test_sections_release_in_order_and_the_briefing_is_stored(database: Database) -> None:
    _, stored = await stored_recorded(database)
    service, replay = replayed_service(database, [_stream(_text())])

    events = await _events(service)

    assert isinstance(events[0], Started)
    assert events[0].assessment_id == stored.id
    assert events[0].prompt_version == prompt_version(Thresholds())
    assert _sections(events) == list(BRIEFING_SECTIONS)
    done = events[-1]
    assert isinstance(done, Done)
    assert not done.reused
    assert done.briefing.situation == VALID["situation"]
    [row] = output_rows(database.engine)
    assert (row.kind, row.status, row.withheld_reason) == ("briefing", "ok", None)
    assert row.assessment_id == stored.id
    assert row.content is not None
    assert row.content["briefing"]["actions"] == VALID["actions"]
    assert [source["key"] for source in row.content["sources"]][:2] == ["S1", "S2"]
    assert len(replay.requests) == 1
    await service.close()


async def test_the_request_is_the_frozen_prompt_and_the_context(database: Database) -> None:
    await stored_recorded(database)
    service, replay = replayed_service(database, [_stream(_text())])

    await _events(service)

    body = replay.requests[0].body
    system = body["system"]
    assert isinstance(system, list)
    assert system[-1]["cache_control"] == {"type": "ephemeral"}  # pyright: ignore[reportUnknownMemberType] - a JSON body
    assert body["max_tokens"] == BRIEFING_MAX_TOKENS
    assert body["thinking"] == {"type": "adaptive"}
    output_config = body["output_config"]
    assert isinstance(output_config, dict)
    assert output_config["effort"] == "low"
    assert output_config["format"]["type"] == "json_schema"  # pyright: ignore[reportUnknownMemberType] - a JSON body
    turn = json.dumps(body["messages"])
    assert "<noaa_product" in turn
    assert "Task: briefing" in turn
    assert "https://" not in turn
    await service.close()


def test_a_section_is_finished_once_a_later_key_appears() -> None:
    text = _text()
    cut = text.index('"what_it_means_here"')

    assert completed_sections(text[: cut - 5], 0) == []
    assert completed_sections(text[: cut + 25], 0) == [("situation", VALID["situation"])]
    assert [key for key, _ in completed_sections(text, 1)] == list(BRIEFING_SECTIONS[1:-1])
    assert completed_sections("not json", 0) == []
    assert completed_sections("[1, 2", 0) == []


def test_a_section_renders_as_plain_text_with_its_sources_titles() -> None:
    sources = (SourceRef(key="S1", source_id="nhc-text-products", title="NHC public advisory"),)
    timeline = [TimelineItem(when="18Z", what="Closest approach.", sources=["S1"])]
    notes = [SourceNote(key="S1", why="the advisory"), SourceNote(key="S2", why="other")]

    assert section_text("situation", "A paragraph.", sources) == "A paragraph."
    assert section_text("timeline", timeline, sources) == "18Z: Closest approach. [S1]"
    assert section_text("actions", ["One.", "Two."], sources) == "One.\nTwo."
    assert section_text("sources", notes, sources) == (
        "S1 (NHC public advisory): the advisory\nS2: other"
    )


# Never released ---------------------------------------------------------------------------


async def test_a_section_stating_another_level_is_never_released_and_is_stored_withheld(
    database: Database, caplog: pytest.LogCaptureFixture
) -> None:
    await stored_recorded(database)
    bad: list[dict[str, object]] = [
        {"when": "soon", "what": f"Level 4 now; {HIDDEN_SENTENCE}.", "sources": []}
    ]
    service, _ = replayed_service(database, [_stream(_text(timeline=bad))])

    with caplog.at_level(logging.DEBUG):
        events = await _events(service)

    assert _sections(events) == ["situation", "what_it_means_here"]
    withheld = events[-1]
    assert isinstance(withheld, Withheld)
    assert withheld.reason == "level"
    assert HIDDEN_SENTENCE not in repr(events)
    assert HIDDEN_SENTENCE not in caplog.text
    [row] = output_rows(database.engine)
    assert (row.status, row.withheld_reason, row.content) == ("withheld", "level", None)
    assert withheld.output_id == row.id
    [call] = ledger_rows(database.engine)
    assert call.status == "incomplete"  # the stream was left before its final message
    assert row.call_id == call.id
    await service.close()


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"situation": "Read more at www.example.invalid/storm."}, "url"),
        ({"situation": "The center is near 12.3N 45.6W."}, "coordinate"),
        ({"situation": "As the advisory says [S99]."}, "source"),
        ({"what_it_means_here": " "}, "empty"),
        ({"actions": [f"Step {n}." for n in range(9)]}, "length"),
    ],
)
async def test_every_section_rule_withholds_the_briefing(
    database: Database, changes: dict[str, object], reason: str
) -> None:
    await stored_recorded(database)
    service, _ = replayed_service(database, [_stream(_text(**changes))])

    events = await _events(service)

    withheld = events[-1]
    assert isinstance(withheld, Withheld)
    assert withheld.reason == reason
    assert next(iter(changes)) not in _sections(events)
    await service.close()


async def test_a_max_tokens_stop_withdraws_the_sections_shown_as_incomplete(
    database: Database,
) -> None:
    await stored_recorded(database)
    service, _ = replayed_service(database, [_stream(_text(), stop_reason="max_tokens")])

    events = await _events(service)

    assert "situation" in _sections(events)
    withheld = events[-1]
    assert isinstance(withheld, Withheld)
    assert (withheld.reason, withheld.output_id) == (
        "incomplete",
        output_rows(database.engine)[0].id,
    )
    [call] = ledger_rows(database.engine)
    assert (call.status, call.error_kind) == ("failed", "truncated")
    await service.close()


async def test_a_cut_stream_is_incomplete(database: Database) -> None:
    await stored_recorded(database)
    text = _text()
    service, _ = replayed_service(database, [_stream(text[: len(text) // 2], final=False)])

    events = await _events(service)

    withheld = events[-1]
    assert isinstance(withheld, Withheld)
    assert withheld.reason == "incomplete"
    assert output_rows(database.engine)[0].status == "withheld"
    await service.close()


async def test_text_that_misses_the_schema_is_withheld(database: Database) -> None:
    await stored_recorded(database)
    service, _ = replayed_service(database, [_stream('{"situation": "Only this."}')])

    events = await _events(service)

    assert events[-1] == Withheld("invalid_output", "the answer did not match its schema", 1)
    [call] = ledger_rows(database.engine)
    assert (call.status, call.error_kind) == ("failed", "invalid_output")
    await service.close()


# Reuse and staleness -----------------------------------------------------------------------


async def test_a_stored_briefing_is_reused_without_a_request_unless_new(database: Database) -> None:
    await stored_recorded(database)
    service, replay = replayed_service(database, [_stream(_text()), _stream(_text())])
    first = await _events(service)

    again = await _events(service)

    assert _sections(again) == list(BRIEFING_SECTIONS)
    reused = again[-1]
    assert isinstance(reused, Done)
    assert reused.reused
    assert isinstance(first[-1], Done)
    assert reused.output_id == first[-1].output_id
    assert len(replay.requests) == 1

    renewed = await _events(service, new=True)

    assert isinstance(renewed[-1], Done)
    assert not renewed[-1].reused
    assert len(replay.requests) == 2  # noqa: PLR2004 - the first and the new briefing
    await service.close()


async def test_a_withheld_briefing_is_not_reused(database: Database) -> None:
    await stored_recorded(database)
    bad = _stream(_text(situation="Level 5 now."))
    service, replay = replayed_service(database, [bad, _stream(_text())])
    await _events(service)

    events = await _events(service)

    assert isinstance(events[-1], Done)
    assert len(replay.requests) == 2  # noqa: PLR2004 - the withheld and the new briefing
    await service.close()


async def test_a_newer_assessment_makes_the_stored_briefing_stale(database: Database) -> None:
    recorded, first = await stored_recorded(database)
    service, _ = replayed_service(database, [_stream(_text())])
    briefings = BriefingService(service)
    assert briefings.latest(LOCATION).stored is None

    await _events(service)
    fresh = briefings.latest(LOCATION)
    later = stored_later(database, recorded, first.assessment)
    stale = briefings.latest(LOCATION)

    assert (fresh.stale, fresh.assessment_id) == (False, first.id)
    assert (stale.stale, stale.assessment_id) == (True, later.id)
    assert stale.stored is not None
    assert stale.stored.assessment_id == first.id
    await service.close()


# Unavailable ------------------------------------------------------------------------------


async def test_a_location_with_no_assessment_is_unavailable(database: Database) -> None:
    service, replay = replayed_service(database, [])

    assert await _events(service) == [Unavailable("no_assessment")]
    assert replay.requests == []
    await service.close()


@pytest.mark.parametrize(
    ("settings", "reason"),
    [(AiSettings(enabled=False), "disabled"), (AiSettings(daily_cap_usd=0.001), "capped")],
)
async def test_ai_off_or_capped_is_unavailable_and_sends_nothing(
    database: Database, settings: AiSettings, reason: str
) -> None:
    await stored_recorded(database)
    service, replay = replayed_service(database, [], settings=settings)

    events = await _events(service)

    assert events[-1] == Unavailable(reason)  # pyright: ignore[reportArgumentType] - a reason
    assert replay.requests == []
    assert output_rows(database.engine) == []
    await service.close()


async def test_a_pause_is_unavailable(database: Database) -> None:
    await stored_recorded(database)
    service, replay = replayed_service(database, [])
    service.ledger.pause()

    assert (await _events(service))[-1] == Unavailable("paused")
    assert replay.requests == []
    await service.close()


async def test_a_context_past_its_limit_is_too_large(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    await stored_recorded(database)
    monkeypatch.setattr("weatherbot.services.ai.context.CONTEXT_LIMIT", 100)
    service, replay = replayed_service(database, [])

    assert await _events(service) == [Unavailable("too_large")]
    assert replay.requests == []
    await service.close()


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (RecordedAnswer.error(529, "overloaded_error"), "overloaded"),
        (RecordedAnswer.error(429, "rate_limit_error"), "rate_limited"),
        (RecordedAnswer.error(401, "authentication_error"), "auth_failed"),
        (RecordedAnswer.unreachable(), "network"),
    ],
)
async def test_an_error_before_the_stream_is_unavailable_and_stores_nothing(
    database: Database, answer: RecordedAnswer, reason: str
) -> None:
    await stored_recorded(database)
    service, _ = replayed_service(database, [answer])

    events = await _events(service)

    assert isinstance(events[0], Started)
    assert events[-1] == Unavailable(reason)  # pyright: ignore[reportArgumentType] - a reason
    assert output_rows(database.engine) == []
    [call] = ledger_rows(database.engine)
    assert call.status == "failed"
    await service.close()


async def test_a_refusal_is_unavailable_declined(database: Database) -> None:
    await stored_recorded(database)
    refusal = _stream("", stop_reason="refusal", thinking=False)
    service, _ = replayed_service(database, [refusal])

    events = await _events(service)

    assert events[-1] == Unavailable("declined")
    assert output_rows(database.engine) == []
    assert ledger_rows(database.engine)[0].status == "declined"
    await service.close()


async def test_a_message_answer_in_place_of_a_stream_is_never_shown(database: Database) -> None:
    await stored_recorded(database)
    service, _ = replayed_service(database, [RecordedAnswer.json(message_body(_text()))])

    events = await _events(service)

    assert not isinstance(events[-1], Done)
    await service.close()
