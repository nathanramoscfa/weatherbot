# src/weatherbot/services/ai/briefing.py
"""``BriefingService``: a plain-language briefing for one location, released section by section.

A briefing is written once per location, assessment, model, and prompt version. ``stream``
replays a stored briefing for the location's latest assessment as its sections and
``Done(reused=True)``, without a request, unless ``new`` is asked for. Otherwise it builds
the privacy-reduced context (``context.py``) from the stored assessment, its changes, its
snapshot's NOAA texts, and the stale sources, and streams one request through
``AiCaller.stream(..., output_format=Briefing)``: adaptive thinking, effort ``low``,
``max_tokens`` 6,000. Each ``text`` event's snapshot is parsed with
``pydantic_core.from_json(..., allow_partial="trailing-strings")``, and a section is
released once a later key appears (or the stream ends) and ``validate_section`` passes:
every check that can judge one section (level, source keys, URL, coordinates, emptiness,
bound). A failing section ends the stream with ``Withheld`` before any of its text is
released, and the briefing is stored withheld with its reason and no text. Once the
block ends, ``AiCaller`` validates the final text against the schema (an
``InvalidOutputError`` withholds the briefing), and ``validate_briefing`` checks the whole.
The one check left for the end, that every section arrived, fails on a ``max_tokens``
stop or a cut stream and ends with ``Withheld("incomplete")``, which tells a page to
remove the sections it showed (a terminal says so after them). A request refused before
it streamed is ``Unavailable`` with its reason, and nothing is stored.

Nothing here logs a prompt, a context, or an answer. The module loads no SDK.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, cast

from pydantic import TypeAdapter, ValidationError
from pydantic_core import from_json

from weatherbot.models import Thresholds
from weatherbot.services.ai.context import (
    BriefingContext,
    ContextTooLarge,
    SourceRef,
    briefing_context,
    render_context,
    stored_sources,
)
from weatherbot.services.ai.errors import AiUnavailable, AiUnavailableReason, InvalidOutputError
from weatherbot.services.ai.outputs import NewOutput, OutputRepository, StoredOutput
from weatherbot.services.ai.prompts import prompt_version, system_blocks, user_turn
from weatherbot.services.ai.schemas import (
    BRIEFING_SECTIONS,
    Briefing,
    SectionName,
    SourceNote,
    TimelineItem,
)
from weatherbot.services.ai.service import AiService
from weatherbot.services.ai.validate import (
    SectionValue,
    Violation,
    ViolationRule,
    first_violation,
    validate_briefing,
    validate_section,
)
from weatherbot.services.health import staleness
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    HeartbeatRepository,
    SnapshotRepository,
    StoredAssessment,
)

type WithheldReason = ViolationRule | Literal["incomplete", "invalid_output"]
type BriefingUnavailableReason = AiUnavailableReason | Literal["no_assessment"]

BRIEFING_MAX_TOKENS: Final = 6_000
BRIEFING_EFFORT: Final = "low"
INCOMPLETE_DETAIL: Final = "the briefing did not arrive whole"
INVALID_DETAIL: Final = "the answer did not match its schema"
_SECTION_TYPES: Final[Mapping[str, TypeAdapter[Any]]] = {
    "situation": TypeAdapter(str),
    "what_it_means_here": TypeAdapter(str),
    "timeline": TypeAdapter(list[TimelineItem]),
    "actions": TypeAdapter(list[str]),
    "sources": TypeAdapter(list[SourceNote]),
}
"""Each section's schema type, to read a finished section of a partial answer."""


@dataclass(frozen=True)
class Started:
    """A briefing began: its model, the assessment it is for, and the prompt's version."""

    model: str
    assessment_id: int
    as_of: datetime
    prompt_version: str


@dataclass(frozen=True)
class Section:
    """One validated section, as plain text."""

    name: SectionName
    text: str


@dataclass(frozen=True)
class Done:
    """The briefing is whole and stored (or was stored before, and reused)."""

    output_id: int
    briefing: Briefing
    created_at: datetime
    reused: bool


@dataclass(frozen=True)
class Withheld:
    """The briefing was withheld: its reason, and fixed text that never quotes the model."""

    reason: WithheldReason
    detail: str
    output_id: int | None = None
    """The stored withheld row, once it is stored."""


@dataclass(frozen=True)
class Unavailable:
    """No briefing could be asked for; nothing was stored."""

    reason: BriefingUnavailableReason


type BriefingEvent = Started | Section | Done | Withheld | Unavailable


@dataclass(frozen=True)
class BriefingState:
    """A location's newest stored briefing, and whether a newer assessment has arrived."""

    stored: StoredOutput | None
    stale: bool
    assessment_id: int | None
    """The location's latest assessment, or ``None`` when none is stored."""


def section_text(name: SectionName, value: SectionValue, sources: Sequence[SourceRef]) -> str:
    """Render a section as plain text, a source key followed by its product's title.

    Args:
        name: The section.
        value: Its value.
        sources: The context's sources, which map each key to its product.

    Returns:
        The text: a paragraph, or one line per item.
    """
    if isinstance(value, str):
        return value
    titles = {source.key: source.title for source in sources}
    lines: list[str] = []
    for item in value:
        if isinstance(item, TimelineItem):
            keys = f" [{', '.join(item.sources)}]" if item.sources else ""
            lines.append(f"{item.when}: {item.what}{keys}")
        elif isinstance(item, SourceNote):
            title = titles.get(item.key)
            lines.append(
                f"{item.key} ({title}): {item.why}" if title else f"{item.key}: {item.why}"
            )
        else:
            lines.append(item)
    del name
    return "\n".join(lines)


def briefing_params(context: BriefingContext, thresholds: Thresholds) -> dict[str, Any]:
    """Build a briefing request's body, without ``model`` or its output format.

    Args:
        context: The briefing's context.
        thresholds: The thresholds the frozen prompt renders.

    Returns:
        The body: the frozen system prompt with its cache marker, the user turn,
        adaptive thinking, effort ``low``, and ``max_tokens`` 6,000.

    Raises:
        ContextTooLarge: The rendered context passes its limit.
    """
    return {
        "max_tokens": BRIEFING_MAX_TOKENS,
        "system": system_blocks(thresholds),
        "messages": [{"role": "user", "content": user_turn(render_context(context), "briefing")}],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": BRIEFING_EFFORT},
    }


def stored_briefing(stored: StoredOutput) -> tuple[Briefing, tuple[SourceRef, ...]]:
    """Read a stored briefing's content back: the briefing and its sources.

    Args:
        stored: An ``ok`` briefing.

    Returns:
        The briefing and the sources its keys name.

    Raises:
        ValueError: The product holds no content.
    """
    if stored.content is None:
        message = "a withheld briefing holds no content"
        raise ValueError(message)
    briefing = Briefing.model_validate(stored.content["briefing"])
    return briefing, stored_sources(stored.content["sources"])


def _content(briefing: Briefing, context: BriefingContext) -> dict[str, Any]:
    return {
        "briefing": briefing.model_dump(mode="json"),
        "sources": [source.model_dump(mode="json") for source in context.sources],
    }


def completed_sections(text: str, released: int) -> list[tuple[str, object]]:
    """Read the sections a partial answer has finished, after those already released.

    Args:
        text: The answer's text so far.
        released: How many sections were released already.

    Returns:
        Each finished section's key and value, in the answer's order: a section is
        finished once a later key appears.
    """
    try:
        partial: object = from_json(text, allow_partial="trailing-strings")
    except ValueError:
        return []
    if not isinstance(partial, dict):
        return []
    found = cast("dict[str, object]", partial)
    keys = list(found)
    return [(key, found[key]) for key in keys[released : len(keys) - 1]]


class _WithholdError(Exception):
    """A section failed: the stream ends, withheld, before any of its text is released."""

    def __init__(self, *, reason: WithheldReason, detail: str) -> None:
        super().__init__(detail)
        self.reason: WithheldReason = reason
        self.detail = detail


class BriefingService:
    """Briefs a location on demand, through the one caller and the ledger."""

    def __init__(self, service: AiService) -> None:
        """Create the service.

        Args:
            service: The AI service; its engine is the AI engine, which reads anything and
                writes only ``ai_calls`` and ``ai_outputs``.
        """
        self._service = service
        self._outputs = OutputRepository(service.engine, now=service.clock, stored=service.stored)
        self._assessments = AssessmentRepository(service.engine)

    def output(self, output_id: int) -> StoredOutput | None:
        """Read one stored briefing.

        Args:
            output_id: Its id.

        Returns:
            The briefing, or ``None``.
        """
        return self._outputs.get(output_id)

    def latest(self, location: str) -> BriefingState:
        """Read a location's newest stored briefing, and whether it is stale.

        Args:
            location: The location's name.

        Returns:
            The briefing (withheld or not), whether a newer assessment has arrived since
            it was written, and the latest assessment's id.
        """
        stored = self._outputs.latest_briefing(location)
        latest = self._assessments.latest(location)
        latest_id = latest.id if latest is not None else None
        stale = stored is not None and latest_id is not None and stored.assessment_id != latest_id
        return BriefingState(stored, stale, latest_id)

    def context_for(self, stored: StoredAssessment) -> BriefingContext:
        """Build the context of a stored assessment: its snapshot's texts, the stale sources.

        Args:
            stored: The stored assessment.

        Returns:
            The context.

        Raises:
            ContextTooLarge: The rendered context passes its limit.
        """
        engine = self._service.engine
        snapshot = SnapshotRepository(engine).load(stored.assessment.snapshot_id)
        judged = staleness(HeartbeatRepository(engine).rows(), self._service.clock())
        stale = [item.name for item in judged if item.stale and item.kind == "source"]
        return briefing_context(stored.assessment, stored.changes, snapshot, stale)

    async def stream(self, location: str, *, new: bool = False) -> AsyncGenerator[BriefingEvent]:
        """Brief a location: replay its stored briefing, or stream a new one section by section.

        Args:
            location: The location's name.
            new: Ask for a new briefing even when one is stored for the latest assessment.

        Yields:
            ``Started``, then each ``Section`` as it passes, then ``Done``; or ``Withheld``
            (after any sections released) or ``Unavailable``.
        """
        stored = await asyncio.to_thread(self._assessments.latest, location)
        if stored is None:
            yield Unavailable("no_assessment")
            return
        model = self._service.settings.model
        thresholds = stored.assessment.thresholds
        version = prompt_version(thresholds)
        if not new:
            reused = await asyncio.to_thread(self._outputs.briefing_for, stored.id, model, version)
            if reused is not None:
                async for event in self._replay(reused, stored):
                    yield event
                return
        try:
            self._service.caller()
            context = await asyncio.to_thread(self.context_for, stored)
            params = briefing_params(context, thresholds)
        except AiUnavailable as error:
            yield Unavailable(error.reason)
            return
        except ContextTooLarge:
            yield Unavailable("too_large")
            return
        yield Started(model, stored.id, stored.assessment.as_of, version)
        async for event in self._request(stored, context, params, version):
            yield event

    async def _replay(
        self, reused: StoredOutput, stored: StoredAssessment
    ) -> AsyncIterator[BriefingEvent]:
        briefing, sources = stored_briefing(reused)
        yield Started(reused.model, stored.id, stored.assessment.as_of, reused.prompt_version)
        for name in BRIEFING_SECTIONS:
            yield Section(name, section_text(name, getattr(briefing, name), sources))
        yield Done(reused.id, briefing, reused.created_at, reused=True)

    async def _store(
        self,
        stored: StoredAssessment,
        version: str,
        call_id: int | None,
        outcome: Briefing | Withheld,
        context: BriefingContext,
    ) -> StoredOutput:
        ok = isinstance(outcome, Briefing)
        output = NewOutput(
            kind="briefing",
            model=self._service.settings.model,
            prompt_version=version,
            status="ok" if ok else "withheld",
            content=_content(outcome, context) if isinstance(outcome, Briefing) else None,
            location_name=stored.assessment.location_name,
            assessment_id=stored.id,
            snapshot_id=stored.assessment.snapshot_id,
            withheld_reason=None if isinstance(outcome, Briefing) else outcome.reason,
            call_id=call_id,
        )
        return await asyncio.to_thread(self._outputs.add, output)

    async def _request(
        self,
        stored: StoredAssessment,
        context: BriefingContext,
        params: dict[str, Any],
        version: str,
    ) -> AsyncIterator[BriefingEvent]:
        caller = self._service.caller()
        released: list[SectionName] = []
        started = False
        call_id: int | None = None
        outcome: Briefing | Withheld | Unavailable
        try:
            async with caller.stream(
                kind="briefing",
                model=self._service.settings.model,
                location=stored.assessment.location_name,
                prompt_version=version,
                params=params,
                output_format=Briefing,
            ) as events:
                call_id = events.call_id
                async for event in events:
                    started = True
                    if event.type != "text":
                        continue
                    for key, value in completed_sections(event.snapshot, len(released)):
                        section = _section(key, value, context)
                        released.append(section.name)
                        yield section
            for section in _finish(events.output, released, context):
                released.append(section.name)
                yield section
            outcome = cast("Briefing", events.output)
        except _WithholdError as error:
            outcome = Withheld(error.reason, error.detail)
        except (InvalidOutputError, AiUnavailable) as error:
            call_id = error.call_id or call_id
            outcome = _failed(error, released=bool(released), started=started)
        if isinstance(outcome, Unavailable):
            yield outcome
            return
        saved = await self._store(stored, version, call_id, outcome, context)
        if isinstance(outcome, Withheld):
            yield Withheld(outcome.reason, outcome.detail, saved.id)
            return
        yield Done(saved.id, outcome, saved.created_at, reused=False)


def _section(key: str, value: object, context: BriefingContext) -> Section:
    """A finished section, once it passes every section check."""
    if key not in _SECTION_TYPES:
        raise _WithholdError(reason="invalid_output", detail=INVALID_DETAIL)
    name = cast("SectionName", key)
    try:
        typed: SectionValue = _SECTION_TYPES[name].validate_python(value)
    except ValidationError:
        raise _WithholdError(reason="invalid_output", detail=INVALID_DETAIL) from None
    _require(validate_section(name, typed, context))
    return Section(name, section_text(name, typed, context.sources))


def _require(violations: Sequence[Violation]) -> None:
    """Withhold on the first violation."""
    violation = first_violation(violations)
    if violation is not None:
        raise _WithholdError(reason=violation.rule, detail=violation.detail)


def _finish(
    output: object, released: Sequence[SectionName], context: BriefingContext
) -> list[Section]:
    """The sections still to release once the stream ended, after the whole is checked."""
    if not isinstance(output, Briefing):
        raise _WithholdError(reason="incomplete", detail=INCOMPLETE_DETAIL)
    remaining = [
        _section(name, getattr(output, name), context)
        for name in BRIEFING_SECTIONS
        if name not in released
    ]
    _require(validate_briefing(output, context))
    return remaining


def _failed(
    error: InvalidOutputError | AiUnavailable, *, released: bool, started: bool
) -> Withheld | Unavailable:
    """How a request that ended in an error ends for the page.

    A text that missed its schema is withheld; a ``max_tokens`` stop, or any failure once
    sections were released or the stream had begun (but a refusal), is incomplete; any
    other failure leaves AI unavailable, and nothing is stored.
    """
    if isinstance(error, InvalidOutputError):
        return Withheld("invalid_output", INVALID_DETAIL)
    cut = error.reason == "truncated" or released or (started and error.reason != "declined")
    return Withheld("incomplete", INCOMPLETE_DETAIL) if cut else Unavailable(error.reason)
