# tests/ai/test_ai_chat.py
"""``ChatService``: the tool loop, sentence gating, the conversations' bounds, byte-for-byte replay.

The database holds both public landmarks assessed over the recorded snapshot. The
recorded chat turns (``tests/fixtures/ai/chat-*.json``) replay round by round through the
real SDK; the edge cases are hand-written streams.
"""

import hashlib
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterator, Sequence
from datetime import timedelta
from typing import Any, cast

import pytest
from ai_support import (
    FIXTURES,
    RecordedAnswer,
    Replay,
    chunked_stream,
    ledger_rows,
    load_rounds,
    recorded_tool_names,
    replayed_service,
    shared_recorded_snapshot,
    stored_later,
    stream_blocks,
    tool_stream,
)
from eval.chat_cases import CHAT_CASES, ChatCase, chat_case, store_case_data
from source_support import NOW

from weatherbot.models import Thresholds
from weatherbot.services.ai import chat as chat_module
from weatherbot.services.ai.chat import (
    CHAT_EFFORT,
    CHAT_MAX_TOKENS,
    IDLE_AFTER,
    MAX_CONVERSATIONS,
    MAX_TOOL_ROUNDS,
    ChatEvent,
    ChatService,
    Done,
    Started,
    Text,
    Tool,
    Unavailable,
    Withheld,
    chat_prompt_version,
    split_sentences,
)
from weatherbot.services.ai.prompts import chat_system_blocks
from weatherbot.services.ai.service import AiService
from weatherbot.services.ai.tools import TOOL_NAMES
from weatherbot.services.config import AiSettings, AppPaths
from weatherbot.services.logs import configure_logging
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import AssessmentRepository

pytestmark = pytest.mark.anyio

MIAMI = "Miami-Dade County Hall"
NASSAU = "Parliament Square"
QUESTION = "What is the official level here, and why?"
HIDDEN = "this sentence must never be shown"


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


class _Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> Any:  # noqa: ANN401 - a datetime, as the service's clock returns
        return self.now


def _text(text: str) -> RecordedAnswer:
    return RecordedAnswer.events(chunked_stream(text))


def _tools(*calls: tuple[str, object], text: str = "") -> RecordedAnswer:
    return RecordedAnswer.events(tool_stream(*calls, text=text))


async def _turn(
    chat: ChatService,
    question: str = QUESTION,
    location: str | None = MIAMI,
    conversation_id: str | None = None,
) -> list[ChatEvent]:
    return [event async for event in chat.turn(conversation_id, question, location)]


def _sentences(events: Sequence[ChatEvent]) -> list[str]:
    return [event.sentence for event in events if isinstance(event, Text)]


def _started(events: Sequence[ChatEvent]) -> str:
    first = events[0]
    assert isinstance(first, Started)
    return first.conversation_id


type ChatFactory = Callable[..., Awaitable[tuple[ChatService, AiService, Replay]]]


@pytest.fixture
async def chats(database: Database) -> AsyncIterator[ChatFactory]:
    """Build chats over the stored landmarks; every service is closed at teardown."""
    opened: list[AiService] = []
    stored = False

    async def build(
        answers: Sequence[RecordedAnswer],
        *,
        injection: bool = False,
        **options: Any,  # noqa: ANN401 - replayed_service's options
    ) -> tuple[ChatService, AiService, Replay]:
        nonlocal stored
        if not stored:
            await store_case_data(database, injection=injection)
            stored = True
        service, replay = replayed_service(database, answers, **options)
        opened.append(service)
        return ChatService(service), service, replay

    yield build
    for service in opened:
        await service.close()


def _messages(replay: Replay, request: int) -> list[dict[str, Any]]:
    messages = replay.requests[request].body["messages"]
    assert isinstance(messages, list)
    return messages  # pyright: ignore[reportUnknownVariableType] - a JSON list


# The recorded turns ------------------------------------------------------------------------


async def test_a_recorded_turn_answers_after_its_tool_round(
    database: Database, chats: ChatFactory
) -> None:
    case = chat_case("chat-one-round")
    chat, _, replay = await chats(load_rounds(case.name))

    events = await _turn(chat, case.question, case.location)

    assert isinstance(events[0], Started)
    assert events[0].model == "claude-sonnet-5-5"
    tools = [event.name for event in events if isinstance(event, Tool)]
    assert tools == recorded_tool_names(case.name)
    assert len(tools) == 1  # one lookup, then the answer
    assert _sentences(events)[0].startswith(f"{MIAMI} is at least level 1, All Clear")
    done = events[-1]
    assert isinstance(done, Done)
    assert len(replay.requests) == len(done.call_ids) == 2  # noqa: PLR2004 - a lookup, then the answer
    rows = ledger_rows(database.engine)
    assert [(row.kind, row.status) for row in rows] == [("chat", "ok"), ("chat", "ok")]
    assert [row.id for row in rows] == list(done.call_ids)
    assert {row.prompt_version for row in rows} == {chat_prompt_version(Thresholds())}


@pytest.mark.parametrize("case", CHAT_CASES, ids=[case.name for case in CHAT_CASES])
async def test_each_recorded_turn_replays_the_requests_it_was_recorded_with(
    case: ChatCase, chats: ChatFactory
) -> None:
    chat, _, replay = await chats(load_rounds(case.name), injection=case.injection)
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest if item["case"] == case.name)

    events = await _turn(chat, case.question, case.location)

    assert isinstance(events[-1], Done)
    assert hashlib.sha256(replay.requests[-1].content).hexdigest() == entry["request_sha256"]


async def test_parallel_calls_run_together_and_return_in_one_message(chats: ChatFactory) -> None:
    case = chat_case("chat-parallel")
    chat, _, replay = await chats(load_rounds(case.name))

    events = await _turn(chat, case.question, case.location)

    assert isinstance(events[-1], Done)
    rounds = json.loads((FIXTURES / f"{case.name}.json").read_text(encoding="utf-8"))["rounds"]
    for number in range(len(rounds) - 1):
        asked = [block for block in stream_blocks(rounds[number]) if block["type"] == "tool_use"]
        answered = _messages(replay, number + 1)[-1]
        assert answered["role"] == "user"
        assert [block["tool_use_id"] for block in answered["content"]] == [
            block["id"] for block in asked
        ]
    first = [block for block in stream_blocks(rounds[0]) if block["type"] == "tool_use"]
    assert len(first) > 1  # the first round asked for several lookups at once


# The request -------------------------------------------------------------------------------


async def test_each_round_is_the_chat_prompt_the_nine_tools_and_auto_choice(
    chats: ChatFactory,
) -> None:
    chat, _, replay = await chats([_tools(("get_ladder", {})), _text("Normal activities apply.")])

    await _turn(chat)

    body = replay.requests[0].body
    tools = body["tools"]
    assert isinstance(tools, list)
    assert [tool["name"] for tool in tools] == list(TOOL_NAMES)  # pyright: ignore[reportUnknownVariableType] - a JSON list
    assert tools[-1]["cache_control"] == {"type": "ephemeral"}  # pyright: ignore[reportUnknownMemberType] - a JSON list
    assert all("eager_input_streaming" not in tool for tool in tools)  # pyright: ignore[reportUnknownVariableType] - a JSON list
    assert body["tool_choice"] == {"type": "auto"}
    assert body["system"] == chat_system_blocks(Thresholds())
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"] == {"effort": CHAT_EFFORT}
    assert body["max_tokens"] == CHAT_MAX_TOKENS
    assert body["cache_control"] == {"type": "ephemeral"}
    assert not {"temperature", "top_p", "top_k"} & set(body)
    [user] = _messages(replay, 0)
    assert user["role"] == "user"
    assert user["content"].endswith(f"\n\nQuestion: {QUESTION}")
    assert f"{MIAMI}: at least level 1, All Clear; assessed 2026-10-13T02:00Z" in user["content"]
    assert NASSAU not in user["content"]


async def test_a_question_about_every_location_names_every_level(chats: ChatFactory) -> None:
    chat, _, replay = await chats([_text("Both are at least level 1.")])

    await _turn(chat, location=None)

    [user] = _messages(replay, 0)
    assert MIAMI in user["content"]
    assert NASSAU in user["content"]
    assert "The question is about" not in user["content"]


# The tool loop -----------------------------------------------------------------------------


async def test_after_six_rounds_the_turn_is_unavailable_and_the_conversation_closes(
    chats: ChatFactory,
) -> None:
    answers = [_tools(("list_locations", {})) for _ in range(MAX_TOOL_ROUNDS)]
    chat, _, replay = await chats(answers)

    events = await _turn(chat)

    last = events[-1]
    assert isinstance(last, Unavailable)
    assert last.reason == "too_many_lookups"
    assert len(replay.requests) == len(last.call_ids) == MAX_TOOL_ROUNDS
    assert [event.name for event in events if isinstance(event, Tool)] == ["list_locations"] * (
        MAX_TOOL_ROUNDS - 1
    )
    again = await _turn(chat, conversation_id=_started(events))
    assert again == [Unavailable("conversation_closed")]


async def test_an_unknown_tool_is_named_unknown_and_answered_with_an_error(
    chats: ChatFactory,
) -> None:
    chat, _, replay = await chats(
        [_tools(("fetch_url", {"url": "x"})), _text("I can read only stored data.")]
    )

    events = await _turn(chat)

    assert Tool("unknown_tool") in events
    [result] = _messages(replay, 1)[-1]["content"]
    assert result["is_error"] is True
    assert json.loads(result["content"])["allowed"] == list(TOOL_NAMES)


async def test_text_before_the_tool_calls_is_checked_and_shown(chats: ChatFactory) -> None:
    chat, _, _ = await chats(
        [_tools(("get_ladder", {}), text="Let me look that up"), _text("Done looking.")],
    )

    events = await _turn(chat)

    assert _sentences(events) == ["Let me look that up", "Done looking."]
    assert isinstance(events[-1], Done)


# Sentence gating ---------------------------------------------------------------------------


def test_text_is_held_until_a_sentence_ends() -> None:
    assert split_sentences("One. Two") == (["One."], " Two")
    assert split_sentences("Is it? Yes! Near 20.3N 106.9W. And") == (
        ["Is it?", "Yes!", "Near 20.3N 106.9W."],
        " And",
    )
    assert split_sentences("A line\nand 3.5 percent.") == (["A line"], "and 3.5 percent.")
    assert split_sentences("Levels:\n1. All Clear.\n2. Watch.") == (
        ["Levels:", "1. All Clear."],
        "2. Watch.",
    )
    assert split_sentences("\n\n") == ([], "")


@pytest.mark.parametrize(
    ("sentence", "rule"),
    [
        (f"{MIAMI} is now level 4; {HIDDEN}.", "level"),
        (f"The official level is 5, {HIDDEN}.", "level"),
        (f"Read more at www.example.invalid/storm, {HIDDEN}.", "url"),
        (f"The center is near 12.3N 45.6W, {HIDDEN}.", "coordinate"),
    ],
)
async def test_a_failing_sentence_withholds_the_rest_and_closes_the_conversation(
    database: Database,
    caplog: pytest.LogCaptureFixture,
    sentence: str,
    rule: str,
    chats: ChatFactory,
) -> None:
    answer = _text(f"{MIAMI} is at least level 1, All Clear. {sentence} The rest is hidden too.")
    chat, _, replay = await chats([answer])

    configure_logging("DEBUG")  # as a command logs: the SDK's loggers stay at WARNING
    with caplog.at_level(logging.DEBUG):
        events = await _turn(chat)

    assert _sentences(events) == [f"{MIAMI} is at least level 1, All Clear."]
    withheld = events[-1]
    assert isinstance(withheld, Withheld)
    assert withheld.reason == rule
    assert HIDDEN not in repr(events)
    assert "The rest" not in repr(events)
    assert QUESTION not in caplog.text
    assert HIDDEN not in caplog.text
    [row] = ledger_rows(database.engine)
    assert row.status == "incomplete"  # the stream was left before its final message
    again = await _turn(chat, conversation_id=_started(events))
    assert again == [Unavailable("conversation_closed")]
    assert len(replay.requests) == 1


async def test_a_storm_position_quoted_from_its_advisory_is_shown(chats: ChatFactory) -> None:
    chat, _, _ = await chats(
        [
            _tools(("get_storm", {"atcf_id": "EP202026"})),
            _text("NHC puts the center of Simon near 20.3N 106.9W."),
        ],
    )

    events = await _turn(chat)

    assert _sentences(events) == ["NHC puts the center of Simon near 20.3N 106.9W."]
    assert isinstance(events[-1], Done)


async def test_an_answer_with_no_text_is_withheld_as_empty(
    database: Database, chats: ChatFactory
) -> None:
    chat, _, _ = await chats([_text("")])

    events = await _turn(chat)

    [row] = ledger_rows(database.engine)
    assert events[-1] == Withheld("empty", "the answer is empty", (row.id,))
    assert row.status == "ok"  # the request itself ended normally


# Failures ----------------------------------------------------------------------------------


async def test_an_error_before_any_text_is_unavailable(chats: ChatFactory) -> None:
    chat, _, _ = await chats(
        [_tools(("get_ladder", {})), RecordedAnswer.error(529, "overloaded_error")],
    )

    events = await _turn(chat)

    last = events[-1]
    assert isinstance(last, Unavailable)
    assert last.reason == "overloaded"
    assert len(last.call_ids) == 2  # noqa: PLR2004 - the lookup and the refused request


async def test_a_cut_stream_after_text_is_withheld_as_incomplete(chats: ChatFactory) -> None:
    cut = RecordedAnswer.events(chunked_stream("First sentence. Second sentence.", final=False))
    chat, _, _ = await chats([cut])

    events = await _turn(chat)

    assert _sentences(events) == ["First sentence."]
    last = events[-1]
    assert isinstance(last, Withheld)
    assert last.reason == "incomplete"


async def test_a_max_tokens_stop_after_text_is_withheld_as_incomplete(
    database: Database, chats: ChatFactory
) -> None:
    truncated = RecordedAnswer.events(chunked_stream("One. Two", stop_reason="max_tokens"))
    chat, _, _ = await chats([truncated])

    events = await _turn(chat)

    assert isinstance(events[-1], Withheld)
    assert events[-1].reason == "incomplete"
    assert ledger_rows(database.engine)[0].error_kind == "truncated"


async def test_ai_turned_off_is_unavailable_and_starts_no_conversation(chats: ChatFactory) -> None:
    chat, _, replay = await chats([], settings=AiSettings(enabled=False))

    assert await _turn(chat) == [Unavailable("disabled")]
    assert replay.requests == []
    assert chat.conversation_ids == ()


async def test_a_request_past_the_cap_is_unavailable_and_closes_its_conversation(
    chats: ChatFactory,
) -> None:
    chat, _, replay = await chats([], settings=AiSettings(daily_cap_usd=0.001))

    events = await _turn(chat)

    assert events[-1] == Unavailable("capped")
    assert replay.requests == []
    assert await _turn(chat, conversation_id=_started(events)) == [
        Unavailable("conversation_closed")
    ]


async def test_a_location_without_an_assessment_is_unavailable(chats: ChatFactory) -> None:
    chat, _, replay = await chats([])

    assert await _turn(chat, location="Nowhere") == [Unavailable("no_assessment")]
    assert replay.requests == []


async def test_a_question_is_1_to_2000_characters(chats: ChatFactory) -> None:
    chat, _, _ = await chats([])

    for question in ("", "   ", "x" * 2_001):
        with pytest.raises(ValueError, match="a question is 1 to 2000 characters"):
            await _turn(chat, question)


# Conversations -----------------------------------------------------------------------------


async def test_the_next_request_replays_the_previous_turns_blocks_byte_for_byte(
    chats: ChatFactory,
) -> None:
    case = chat_case("chat-one-round")
    rounds = load_rounds(case.name)
    chat, _, replay = await chats([*rounds, _text("It has not changed.")])
    first = await _turn(chat, case.question, case.location)

    second = await _turn(chat, "Has that changed?", conversation_id=_started(first))

    assert isinstance(second[-1], Done)
    recorded = json.loads((FIXTURES / f"{case.name}.json").read_text(encoding="utf-8"))["rounds"]
    messages = _messages(replay, 2)
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1]["content"] == stream_blocks(recorded[0])
    assert messages[3]["content"] == stream_blocks(recorded[1])
    assert messages[:3] == _messages(replay, 1)  # the history is appended to, never edited


async def test_thinking_and_tool_blocks_return_unchanged_in_the_next_round(
    chats: ChatFactory,
) -> None:
    lookup = tool_stream(("get_evidence", {"location": MIAMI}), ("get_ladder", {}))
    chat, _, replay = await chats([RecordedAnswer.events(lookup), _text("At least level 1.")])

    await _turn(chat)

    assistant = _messages(replay, 1)[1]
    assert assistant == {"role": "assistant", "content": stream_blocks(lookup)}
    assert [block["type"] for block in assistant["content"]] == ["thinking", "tool_use", "tool_use"]
    assert assistant["content"][0]["signature"] == "c3ludGhldGlj"


async def test_a_new_assessment_between_turns_adds_a_system_message_after_the_question(
    database: Database, chats: ChatFactory
) -> None:
    chat, _, replay = await chats(
        [_text("At least level 1."), _tools(("get_ladder", {})), _text("Still at least level 1.")],
    )
    first = await _turn(chat)
    recorded = await shared_recorded_snapshot()
    previous = AssessmentRepository(database.engine).latest(MIAMI)
    assert previous is not None
    stored_later(database, recorded, previous.assessment)

    second = await _turn(chat, "Anything new?", conversation_id=_started(first))

    assert isinstance(second[-1], Done)
    turn = _messages(replay, 1)
    assert [message["role"] for message in turn[-2:]] == ["user", "system"]
    assert turn[-1]["content"].startswith("Official update:")
    assert MIAMI in turn[-1]["content"]
    assert NASSAU not in turn[-1]["content"]  # only the location that changed
    next_round = _messages(replay, 2)
    assert [message["role"] for message in next_round[-4:]] == [
        "user",
        "system",
        "assistant",
        "user",
    ]


async def test_no_system_message_when_no_assessment_changed(chats: ChatFactory) -> None:
    chat, _, replay = await chats([_text("One."), _text("Two.")])
    first = await _turn(chat)

    await _turn(chat, "And now?", conversation_id=_started(first))

    assert [message["role"] for message in _messages(replay, 1)] == ["user", "assistant", "user"]


async def test_at_most_eight_conversations_the_least_recently_used_dropped_first(
    chats: ChatFactory,
) -> None:
    clock = _Clock()
    answers = [_text(f"Answer {number}.") for number in range(MAX_CONVERSATIONS + 1)]
    chat, _, _ = await chats(answers, now=clock)
    started: list[str] = []
    for number in range(MAX_CONVERSATIONS + 1):
        clock.now = NOW + timedelta(minutes=number)
        started.append(_started(await _turn(chat)))

    assert len(chat.conversation_ids) == MAX_CONVERSATIONS
    assert started[0] not in chat.conversation_ids
    assert await _turn(chat, conversation_id=started[0]) == [Unavailable("unknown_conversation")]


async def test_a_conversation_holds_at_most_its_turns(
    monkeypatch: pytest.MonkeyPatch, chats: ChatFactory
) -> None:
    monkeypatch.setattr(chat_module, "MAX_TURNS", 2)
    chat, _, replay = await chats([_text("One."), _text("Two.")])
    first = await _turn(chat)
    conversation = _started(first)
    await _turn(chat, "Again?", conversation_id=conversation)

    assert await _turn(chat, "Once more?", conversation_id=conversation) == [
        Unavailable("conversation_full")
    ]
    assert await _turn(chat, "Still?", conversation_id=conversation) == [
        Unavailable("conversation_closed")
    ]
    assert len(replay.requests) == 2  # noqa: PLR2004 - the two turns


async def test_a_conversation_idle_two_hours_is_dropped(chats: ChatFactory) -> None:
    clock = _Clock()
    chat, _, _ = await chats([_text("One.")], now=clock)
    conversation = _started(await _turn(chat))

    clock.now = NOW + IDLE_AFTER

    assert await _turn(chat, conversation_id=conversation) == [Unavailable("unknown_conversation")]
    assert chat.conversation_ids == ()


async def test_a_conversation_answers_one_turn_at_a_time(chats: ChatFactory) -> None:
    chat, _, _ = await chats([_text("One."), _text("Two.")])
    conversation = _started(await _turn(chat))
    running = chat.turn(conversation, "First?", MIAMI)
    assert isinstance(await anext(running), Started)

    assert await _turn(chat, conversation_id=conversation) == [Unavailable("busy")]

    rest = [event async for event in running]
    assert isinstance(rest[-1], Done)


async def test_leaving_a_turn_early_closes_its_conversation(chats: ChatFactory) -> None:
    chat, _, _ = await chats([_text("One. Two. Three.")])
    running = cast("AsyncGenerator[ChatEvent]", chat.turn(None, QUESTION, MIAMI))
    conversation = _started([await anext(running)])

    await running.aclose()

    assert await _turn(chat, conversation_id=conversation) == [Unavailable("conversation_closed")]
