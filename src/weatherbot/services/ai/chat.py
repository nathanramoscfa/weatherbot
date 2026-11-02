# src/weatherbot/services/ai/chat.py
"""``ChatService``: the operator asks, and Claude looks, at the stored data only.

``turn(conversation_id, question, location)`` answers one question of 1 to 2,000
characters. Its user message is a short preamble naming the official level and the time
of the location asked about (or of every location), then the question. Each round is one
``AiCaller.stream`` request: kind ``chat``, the chat's frozen system prompt and the nine
tools (``tools.py``) each with a cache marker, ``tool_choice`` auto, adaptive thinking at
effort ``medium``, ``max_tokens`` 4,000, and no fine-grained input streaming, so the API
validates every tool input against its strict schema. The tool calls of a round run
together and return in one user message; a turn that still asks for a lookup after six
rounds ends unavailable ("the answer needed too many lookups").

Text deltas are held until a sentence ends (``.``, ``?``, or ``!`` before whitespace, or a
newline), and each sentence passes ``sentence_violations`` before it is shown: no URL, no
position that no NOAA text the tools returned states, and no statement that a location's
current level is other than the engine's latest. A failing sentence ends the turn with
``Withheld``, its text never shown, and closes the conversation.

Conversations live in memory only: append-only, with every content block kept as the API
returned it (thinking and tool blocks included), so each request replays the history byte
for byte; at most 8 conversations of 20 turns, each dropped after 2 idle hours or a
restart. A withheld or unavailable turn closes its conversation. When any location's
latest assessment changed since the previous turn, a ``role: "system"`` message stating
the new official levels follows the turn's user message, as the last entry of the
request: the only placement the API accepts.

Nothing here logs a question, a prompt, a tool result, or an answer. The module loads no
SDK.
"""

import asyncio
import hashlib
import json
import re
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final, Literal

from weatherbot.models import AlertLevel, Thresholds
from weatherbot.services.ai.context import NoaaText, SourceRef, to_hour
from weatherbot.services.ai.errors import AiUnavailable, AiUnavailableReason
from weatherbot.services.ai.prompts import chat_system_blocks, chat_system_prompt
from weatherbot.services.ai.service import AiService
from weatherbot.services.ai.tools import (
    TOOL_DEFINITIONS,
    TOOL_NAMES,
    Toolbox,
    ToolName,
    ToolResult,
    tool_params,
)
from weatherbot.services.ai.validate import ViolationRule, first_violation, sentence_violations
from weatherbot.services.persistence.repositories import AssessmentHead, AssessmentRepository

type ChatWithheldReason = ViolationRule | Literal["incomplete"]
type ChatUnavailableReason = (
    AiUnavailableReason
    | Literal[
        "no_assessment",
        "unknown_conversation",
        "conversation_closed",
        "conversation_full",
        "too_many_lookups",
    ]
)

MAX_TOOL_ROUNDS: Final = 6
MAX_CONVERSATIONS: Final = 8
MAX_TURNS: Final = 20
IDLE_AFTER: Final = timedelta(hours=2)
QUESTION_LIMIT: Final = 2_000
CHAT_MAX_TOKENS: Final = 4_000
CHAT_EFFORT: Final = "medium"
SENTENCE_END: Final = re.compile(r"[.?!](?=\s)|\n")
"""Where a sentence ends: a period, question mark, or exclamation mark before whitespace,
or a newline."""
LIST_NUMBER: Final = re.compile(r"\d{1,2}\.")
"""A list's number ("1."), which stays with the sentence it begins."""
EMPTY_DETAIL: Final = "the answer is empty"
INCOMPLETE_DETAIL: Final = "the answer did not arrive whole"
UNAVAILABLE_TEXT: Final[Mapping[str, str]] = {
    "no_assessment": "no assessment is stored for the location yet",
    "unknown_conversation": "the conversation has ended; start a new one",
    "conversation_closed": "the conversation was closed; start a new one",
    "conversation_full": "the conversation reached its 20 questions; start a new one",
    "too_many_lookups": "the answer needed too many lookups",
}
"""The chat's own unavailable reasons, as a person reads them."""


@dataclass(frozen=True)
class Started:
    """A turn began: its conversation, and the model that answers."""

    conversation_id: str
    model: str


@dataclass(frozen=True)
class Tool:
    """The model looked something up: the tool's name only."""

    name: ToolName | Literal["unknown_tool"]


@dataclass(frozen=True)
class Text:
    """One sentence of the answer, checked."""

    sentence: str


@dataclass(frozen=True)
class Done:
    """The answer is whole; its requests' ledger rows."""

    call_ids: tuple[int, ...]


@dataclass(frozen=True)
class Withheld:
    """The rest of the answer was withheld, and the conversation closed; never its text."""

    reason: ChatWithheldReason
    detail: str
    call_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Unavailable:
    """No answer could be given, and the conversation (if any) closed."""

    reason: ChatUnavailableReason
    call_ids: tuple[int, ...] = ()


type ChatEvent = Started | Tool | Text | Done | Withheld | Unavailable


def chat_prompt_version(thresholds: Thresholds) -> str:
    """Return the chat's prompt version: the SHA-256 of its tools and its system prompt.

    Args:
        thresholds: The thresholds the system prompt renders.

    Returns:
        The hexadecimal digest; the tools render before the prompt, so both count.
    """
    tools = json.dumps(TOOL_DEFINITIONS, ensure_ascii=False, separators=(",", ":"))
    text = f"{tools}\n{chat_system_prompt(thresholds)}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_sentences(text: str) -> tuple[list[str], str]:
    """Split held text into the sentences that have ended and the rest.

    Args:
        text: The text held so far.

    Returns:
        Each ended sentence, stripped (blank ones dropped), and the text still held. A
        list's number ("1.") begins the sentence after it instead of ending one.
    """
    sentences: list[str] = []
    start = 0
    for match in SENTENCE_END.finditer(text):
        piece = text[start : match.end()].strip()
        if LIST_NUMBER.fullmatch(piece):
            continue
        if piece:
            sentences.append(piece)
        start = match.end()
    return sentences, text[start:]


def _level_line(name: str, head: AssessmentHead) -> str:
    level = AlertLevel(head.level)
    floor = "at least " if not head.complete else ""
    when = to_hour(head.as_of).strftime("%Y-%m-%dT%H:%MZ")
    return f"{name}: {floor}level {int(level)}, {level.label}; assessed {when}"


def preamble(heads: Mapping[str, AssessmentHead], location: str | None) -> str:
    """Write the data preamble before a question: the official levels and their times.

    Args:
        heads: Each location's latest assessment.
        location: The location the question is about, or ``None`` for every location.

    Returns:
        The preamble, naming the location asked about (or each location) with its level,
        label, and assessment hour, and saying which one the question is about.
    """
    chosen = {location: heads[location]} if location is not None else dict(heads)
    lines = ["<official_levels>"]
    lines.extend(_level_line(name, head) for name, head in chosen.items())
    lines.append("</official_levels>")
    if location is not None:
        lines.append(f"The question is about {location}.")
    return "\n".join(lines)


def level_update(heads: Mapping[str, AssessmentHead]) -> str:
    """Write the system message that states new official levels mid-conversation.

    Args:
        heads: The locations whose latest assessment changed since the previous turn.

    Returns:
        The message.
    """
    lines = [
        (
            "Official update: Weatherbot stored a newer assessment since the previous question. "
            "The current official levels:"
        )
    ]
    lines.extend(_level_line(name, head) for name, head in heads.items())
    lines.append("They replace every level stated earlier in this conversation.")
    return "\n".join(lines)


@dataclass(frozen=True)
class _Grounding:
    """What a chat sentence is checked against: the NOAA texts the tools returned."""

    noaa: tuple[NoaaText, ...]
    sources: tuple[SourceRef, ...] = ()


@dataclass
class _Conversation:
    """One conversation: its history, appended to and never edited."""

    id: str
    last_used: datetime
    messages: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    seen: dict[str, int] = field(default_factory=dict[str, int])
    """Each location's latest assessment id as of the previous turn."""
    noaa: list[NoaaText] = field(default_factory=list[NoaaText])
    turns: int = 0
    closed: bool = False
    busy: bool = False


class _WithholdError(Exception):
    """A sentence failed, or the answer was empty or cut: the turn ends withheld."""

    def __init__(self, *, reason: ChatWithheldReason, detail: str) -> None:
        super().__init__(detail)
        self.reason: ChatWithheldReason = reason
        self.detail = detail


class _UnavailableError(Exception):
    """The turn cannot go on: the turn ends unavailable."""

    def __init__(self, *, reason: ChatUnavailableReason) -> None:
        super().__init__(reason)
        self.reason: ChatUnavailableReason = reason


def _tool_result(use_id: str, result: ToolResult) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": use_id,
        "content": result.content,
    }
    if result.is_error:
        block["is_error"] = True
    return block


def _tool_event(name: str) -> Tool:
    return Tool(name) if name in TOOL_NAMES else Tool("unknown_tool")


def _require_assessment(heads: Mapping[str, AssessmentHead], location: str | None) -> None:
    if not heads or (location is not None and location not in heads):
        raise _UnavailableError(reason="no_assessment")


def _check(sentence: str, grounding: _Grounding, levels: Mapping[str, AlertLevel]) -> Text:
    violation = first_violation(sentence_violations(sentence, grounding, levels))
    if violation is not None:
        raise _WithholdError(reason=violation.rule, detail=violation.detail)
    return Text(sentence)


class ChatService:
    """Answers questions from the stored data, through the nine tools and the one caller."""

    def __init__(self, service: AiService) -> None:
        """Create the service, with no conversation.

        Args:
            service: The AI service; its engine is the AI engine, which reads anything and
                writes only ``ai_calls`` and ``ai_outputs``.
        """
        self._service = service
        self._toolbox = Toolbox(service.engine, now=service.clock)
        self._conversations: dict[str, _Conversation] = {}

    @property
    def conversation_ids(self) -> tuple[str, ...]:
        """The conversations held in memory, open or closed."""
        return tuple(self._conversations)

    def _expire(self, now: datetime) -> None:
        for key, conversation in list(self._conversations.items()):
            if not conversation.busy and now - conversation.last_used >= IDLE_AFTER:
                del self._conversations[key]

    def _existing(self, conversation_id: str) -> _Conversation:
        found = self._conversations.get(conversation_id)
        if found is None:
            raise _UnavailableError(reason="unknown_conversation")
        if found.busy:
            raise _UnavailableError(reason="busy")
        if found.closed:
            raise _UnavailableError(reason="conversation_closed")
        if found.turns >= MAX_TURNS:
            found.closed = True
            raise _UnavailableError(reason="conversation_full")
        return found

    def _new(self, now: datetime) -> _Conversation:
        if len(self._conversations) >= MAX_CONVERSATIONS:
            idle = [item for item in self._conversations.values() if not item.busy]
            if not idle:
                raise _UnavailableError(reason="busy")
            # The least recently used goes first, a closed one before any open one.
            oldest = min(idle, key=lambda item: (not item.closed, item.last_used))
            del self._conversations[oldest.id]
        conversation = _Conversation(id=uuid.uuid4().hex, last_used=now)
        self._conversations[conversation.id] = conversation
        return conversation

    async def turn(
        self, conversation_id: str | None, question: str, location: str | None = None
    ) -> AsyncIterator[ChatEvent]:
        """Answer one question, in a new conversation or an open one.

        Args:
            conversation_id: The conversation to continue, or ``None`` to start one.
            question: The question, 1 to 2,000 characters.
            location: The location the question is about, or ``None`` for every one.

        Yields:
            ``Started``, then ``Tool`` and ``Text`` events as they happen, then ``Done``;
            or ``Withheld`` (after any sentences shown) or ``Unavailable``.

        Raises:
            ValueError: The question is empty or longer than 2,000 characters.
        """
        asked = question.strip()
        if not asked or len(question) > QUESTION_LIMIT:
            message = f"a question is 1 to {QUESTION_LIMIT} characters"
            raise ValueError(message)
        self._expire(self._service.clock())
        try:
            conversation, heads = await self._prepare(conversation_id, location)
        except (AiUnavailable, _UnavailableError) as error:
            yield Unavailable(error.reason)
            return
        conversation.busy = True
        finished = False
        try:
            yield Started(conversation.id, self._service.settings.model)
            async for event in self._answer(conversation, asked, location, heads):
                finished = isinstance(event, Done)
                yield event
        finally:
            conversation.busy = False
            conversation.last_used = self._service.clock()
            conversation.closed = conversation.closed or not finished

    async def _prepare(
        self, conversation_id: str | None, location: str | None
    ) -> tuple[_Conversation, dict[str, AssessmentHead]]:
        """The conversation to answer in, and the latest assessments; a refusal closes it."""
        existing = self._existing(conversation_id) if conversation_id is not None else None
        try:
            self._service.caller()
            heads = await asyncio.to_thread(AssessmentRepository(self._service.engine).latest_heads)
            _require_assessment(heads, location)
        except (AiUnavailable, _UnavailableError):
            if existing is not None:
                existing.closed = True
            raise
        return existing or self._new(self._service.clock()), heads

    def _open_turn(
        self,
        conversation: _Conversation,
        question: str,
        location: str | None,
        heads: Mapping[str, AssessmentHead],
    ) -> None:
        """Append the turn's user message, and the level update when an assessment changed."""
        conversation.messages.append(
            {"role": "user", "content": f"{preamble(heads, location)}\n\nQuestion: {question}"}
        )
        changed = {
            name: head for name, head in heads.items() if conversation.seen.get(name) != head.id
        }
        if conversation.turns and changed:
            conversation.messages.append({"role": "system", "content": level_update(changed)})
        conversation.seen = {name: head.id for name, head in heads.items()}

    def _params(self, conversation: _Conversation, thresholds: Thresholds) -> dict[str, Any]:
        return {
            "max_tokens": CHAT_MAX_TOKENS,
            "system": chat_system_blocks(thresholds),
            "tools": tool_params(),
            "tool_choice": {"type": "auto"},
            "messages": list(conversation.messages),
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": CHAT_EFFORT},
            "cache_control": {"type": "ephemeral"},
        }

    async def _answer(
        self,
        conversation: _Conversation,
        question: str,
        location: str | None,
        heads: Mapping[str, AssessmentHead],
    ) -> AsyncIterator[ChatEvent]:
        self._open_turn(conversation, question, location, heads)
        call_ids: list[int] = []
        shown = False
        try:
            async for event in self._rounds(conversation, location, heads, call_ids):
                shown = shown or isinstance(event, Text)
                yield event
        except _WithholdError as error:
            yield Withheld(error.reason, error.detail, tuple(call_ids))
        except _UnavailableError as error:
            yield Unavailable(error.reason, tuple(call_ids))
        except AiUnavailable as error:
            if error.call_id is not None and error.call_id not in call_ids:
                call_ids.append(error.call_id)
            if shown:
                yield Withheld("incomplete", INCOMPLETE_DETAIL, tuple(call_ids))
            else:
                yield Unavailable(error.reason, tuple(call_ids))

    async def _rounds(
        self,
        conversation: _Conversation,
        location: str | None,
        heads: Mapping[str, AssessmentHead],
        call_ids: list[int],
    ) -> AsyncIterator[ChatEvent]:
        """Run the tool loop: at most six requests, the calls of each answered together."""
        thresholds = next(iter(heads.values())).thresholds
        levels = {name: AlertLevel(head.level) for name, head in heads.items()}
        shown = False
        for round_number in range(1, MAX_TOOL_ROUNDS + 1):
            async for event in self._round(conversation, thresholds, location, levels, call_ids):
                shown = True
                yield event
            uses = self._tool_uses(conversation)
            if not uses:
                if not shown:
                    raise _WithholdError(reason="empty", detail=EMPTY_DETAIL)
                conversation.turns += 1
                yield Done(tuple(call_ids))
                return
            if round_number == MAX_TOOL_ROUNDS:
                raise _UnavailableError(reason="too_many_lookups")
            for name, _, _ in uses:
                yield _tool_event(name)
            await self._look_up(conversation, uses)

    async def _round(
        self,
        conversation: _Conversation,
        thresholds: Thresholds,
        location: str | None,
        levels: Mapping[str, AlertLevel],
        call_ids: list[int],
    ) -> AsyncIterator[Text]:
        """Stream one request, yielding each checked sentence; append its answer whole."""
        grounding = _Grounding(tuple(conversation.noaa))
        held = ""
        async with self._service.caller().stream(
            kind="chat",
            model=self._service.settings.model,
            location=location,
            prompt_version=chat_prompt_version(thresholds),
            params=self._params(conversation, thresholds),
        ) as events:
            call_ids.append(events.call_id)
            async for event in events:
                if event.type != "text":
                    continue
                sentences, held = split_sentences(held + event.text)
                for sentence in sentences:
                    yield _check(sentence, grounding, levels)
        final = events.final
        if final is None:
            raise _WithholdError(reason="incomplete", detail=INCOMPLETE_DETAIL)
        if held.strip():
            yield _check(held.strip(), grounding, levels)
        conversation.messages.append(
            {"role": "assistant", "content": [block.to_dict() for block in final.content]}
        )

    @staticmethod
    def _tool_uses(conversation: _Conversation) -> list[tuple[str, str, object]]:
        """The last answer's tool calls: each one's name, id, and input."""
        last = conversation.messages[-1]
        blocks: Sequence[dict[str, Any]] = last["content"]
        return [
            (str(block["name"]), str(block["id"]), block.get("input"))
            for block in blocks
            if block.get("type") == "tool_use"
        ]

    async def _look_up(
        self, conversation: _Conversation, uses: Sequence[tuple[str, str, object]]
    ) -> None:
        """Run a round's tool calls together and append their results in one user message."""
        results = await asyncio.to_thread(
            self._toolbox.run, [(name, arguments) for name, _, arguments in uses]
        )
        conversation.messages.append(
            {
                "role": "user",
                "content": [
                    _tool_result(use_id, result)
                    for (_, use_id, _), result in zip(uses, results, strict=True)
                ],
            }
        )
        for result in results:
            conversation.noaa.extend(result.noaa)
