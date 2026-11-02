# src/weatherbot/services/ai/summaries.py
"""``ChangeSummaryService``: a short summary of what changed, once per assessment.

``summarize(assessment_id)`` writes one change summary for a stored assessment whose
changes are more than its first: an assessment with no changes, or whose changes are the
location's initial events, is skipped. A stored summary, withheld or not, is never
rewritten. Otherwise it builds the change context (``context.change_context``: the two
levels, the changes, the deciding evidence, the sources) and sends one
``AiCaller.parse`` with ``[ai] summary_model``, adaptive thinking, effort ``low``, and
``max_tokens`` 1,500. ``validate_summary`` allows the previous and the new level only; a
failing summary, an ``InvalidOutputError``, and a ``max_tokens`` stop are stored withheld
with their reason and no text. A request refused before it was answered is
``unavailable`` and stores nothing. ``latest`` reads summaries, newest first.

``ChangeSummarizer`` is how ``serve`` writes them: primed at start to the newest stored
assessment, woken after every cycle, it summarizes the assessments stored since, newest
first and one at a time, while ``[ai] change_summaries`` is on and the AI is ``ready``.
Its mark moves past every assessment it reads, summarized or not, so a summary missed
while ``serve`` was down or the AI was off, paused, or capped is never written later (a
briefing covers it), and history is never backfilled.

Nothing here logs a prompt, a context, or an answer. The module loads no SDK.
"""

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from weatherbot.models import ChangeEvent, Thresholds
from weatherbot.services.ai.context import (
    ChangeContext,
    ContextTooLarge,
    change_context,
    render_context,
)
from weatherbot.services.ai.errors import AiUnavailable, InvalidOutputError
from weatherbot.services.ai.outputs import NewOutput, OutputRepository, StoredOutput
from weatherbot.services.ai.prompts import prompt_version, system_blocks, user_turn
from weatherbot.services.ai.schemas import ChangeSummary
from weatherbot.services.ai.service import AiPublish, AiService
from weatherbot.services.ai.validate import first_violation, validate_summary
from weatherbot.services.persistence.repositories import AssessmentRepository, StoredAssessment

type SummaryStatus = Literal["ok", "withheld", "skipped", "unavailable"]

LOGGER: Final = logging.getLogger("weatherbot.services.ai")
SUMMARY_MAX_TOKENS: Final = 1_500
SUMMARY_EFFORT: Final = "low"
MAX_NEW_ASSESSMENTS: Final = 20
"""At most this many assessments, the newest, are read after one wake."""


@dataclass(frozen=True)
class SummaryOutcome:
    """How one assessment's change summary ended."""

    status: SummaryStatus
    output_id: int | None = None
    summary: ChangeSummary | None = None
    reason: str | None = None
    """Why it was withheld, skipped, or unavailable; never the model's text."""
    reused: bool = False
    """Whether the summary was stored before, so no request was sent."""


def qualifies(changes: Sequence[ChangeEvent]) -> bool:
    """Whether an assessment's changes are more than its first: it has a summary to write.

    Args:
        changes: The assessment's changes from the previous one.

    Returns:
        False for no changes, and for a location's first assessment (its changes are its
        initial events).
    """
    initial = any(event.direction == "initial" for event in changes)
    return bool(changes) and not initial


def summary_params(context: ChangeContext, thresholds: Thresholds) -> dict[str, Any]:
    """Build a change summary request's body, without ``model`` or its output format.

    Args:
        context: The summary's context.
        thresholds: The thresholds the frozen prompt renders.

    Returns:
        The body: the frozen system prompt with its cache marker, the user turn, adaptive
        thinking, effort ``low``, and ``max_tokens`` 1,500.

    Raises:
        ContextTooLarge: The rendered context passes its limit.
    """
    turn = user_turn(render_context(context), "change summary")
    return {
        "max_tokens": SUMMARY_MAX_TOKENS,
        "system": system_blocks(thresholds),
        "messages": [{"role": "user", "content": turn}],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": SUMMARY_EFFORT},
    }


def stored_summary(stored: StoredOutput) -> ChangeSummary | None:
    """Read a stored summary's content back.

    Args:
        stored: A stored summary.

    Returns:
        The summary, or ``None`` for a withheld one.
    """
    if stored.content is None:
        return None
    return ChangeSummary.model_validate(stored.content["summary"])


class ChangeSummaryService:
    """Summarizes each qualifying assessment once, through the one caller and the ledger."""

    def __init__(self, service: AiService) -> None:
        """Create the service.

        Args:
            service: The AI service.
        """
        self._service = service
        self._outputs = OutputRepository(service.engine, now=service.clock, stored=service.stored)
        self._assessments = AssessmentRepository(service.engine)

    def latest(self, location: str | None, limit: int) -> tuple[StoredOutput, ...]:
        """Read change summaries, newest first.

        Args:
            location: The location's name, or ``None`` for every location.
            limit: At most this many.

        Returns:
            The summaries, withheld ones included.
        """
        return self._outputs.summaries(location, limit)

    async def summarize(self, assessment_id: int) -> SummaryOutcome:
        """Write an assessment's change summary, unless it is stored or not needed.

        Args:
            assessment_id: The stored assessment.

        Returns:
            How it ended.
        """
        stored = await asyncio.to_thread(self._assessments.load, assessment_id)
        if stored is None:
            return SummaryOutcome("unavailable", reason="no_assessment")
        if not qualifies(stored.changes):
            return SummaryOutcome("skipped", reason="first" if stored.changes else "no_changes")
        existing = await asyncio.to_thread(self._outputs.summary_for, assessment_id)
        if existing is not None:
            status: SummaryStatus = "ok" if existing.status == "ok" else "withheld"
            return SummaryOutcome(
                status,
                existing.id,
                stored_summary(existing),
                existing.withheld_reason,
                reused=True,
            )
        return await self._request(stored)

    async def _request(self, stored: StoredAssessment) -> SummaryOutcome:
        thresholds = stored.assessment.thresholds
        version = prompt_version(thresholds)
        try:
            caller = self._service.caller()
            context = change_context(stored.assessment, stored.changes)
            params = summary_params(context, thresholds)
            parsed = await caller.parse(
                kind="summary",
                model=self._service.settings.summary_model,
                location=stored.assessment.location_name,
                prompt_version=version,
                params=params,
                output_format=ChangeSummary,
            )
        except ContextTooLarge:
            return SummaryOutcome("unavailable", reason="too_large")
        except InvalidOutputError as error:
            return await self._withheld(stored, version, error.call_id, "invalid_output")
        except AiUnavailable as error:
            if error.reason != "truncated":
                return SummaryOutcome("unavailable", reason=error.reason)
            return await self._withheld(stored, version, error.call_id, "incomplete")
        violation = first_violation(validate_summary(parsed.output, context))
        if violation is not None:
            return await self._withheld(stored, version, parsed.call_id, violation.rule)
        content = {
            "summary": parsed.output.model_dump(mode="json"),
            "sources": [source.model_dump(mode="json") for source in context.sources],
        }
        saved = await asyncio.to_thread(
            self._outputs.add,
            self._output(stored, version, parsed.call_id, content=content),
        )
        return SummaryOutcome("ok", saved.id, parsed.output)

    def _output(
        self,
        stored: StoredAssessment,
        version: str,
        call_id: int | None,
        *,
        content: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> NewOutput:
        return NewOutput(
            kind="summary",
            model=self._service.settings.summary_model,
            prompt_version=version,
            status="ok" if content is not None else "withheld",
            content=content,
            location_name=stored.assessment.location_name,
            assessment_id=stored.id,
            snapshot_id=stored.assessment.snapshot_id,
            withheld_reason=reason,
            call_id=call_id,
        )

    async def _withheld(
        self, stored: StoredAssessment, version: str, call_id: int | None, reason: str
    ) -> SummaryOutcome:
        saved = await asyncio.to_thread(
            self._outputs.add, self._output(stored, version, call_id, reason=reason)
        )
        return SummaryOutcome("withheld", saved.id, reason=reason)


class ChangeSummarizer:
    """Writes ``serve``'s change summaries: one per qualifying new assessment, never a backlog."""

    def __init__(
        self, summaries: ChangeSummaryService, service: AiService, *, publish: AiPublish
    ) -> None:
        """Create the summarizer, unprimed.

        Args:
            summaries: The service that writes one assessment's summary.
            service: The AI service, for its settings, its state, and its engine.
            publish: Publishes each stored summary (the event hub's ``publish``).
        """
        self._summaries = summaries
        self._service = service
        self._publish = publish
        self._assessments = AssessmentRepository(service.engine)
        self._mark: int | None = None
        self._woken = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def mark(self) -> int | None:
        """The id of the newest assessment read; ``None`` until primed."""
        return self._mark

    def prime(self) -> int:
        """Mark the newest stored assessment, so only assessments stored later are summarized.

        Returns:
            The mark: the newest id, or 0 when none is stored.
        """
        self._mark = self._assessments.newest_id() or 0
        return self._mark

    def wake(self) -> None:
        """Ask ``run`` to read the new assessments; safe from any thread."""
        loop = self._loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if loop is None or running is loop:
            self._woken.set()
            return
        with contextlib.suppress(RuntimeError):  # the loop has closed: nothing is waiting
            loop.call_soon_threadsafe(self._woken.set)

    async def run(self, stop: asyncio.Event) -> None:
        """Wait for a wake, summarize what is new, and repeat until ``stop`` is set.

        Args:
            stop: Set when ``serve`` stops.
        """
        self._loop = asyncio.get_running_loop()
        while not stop.is_set():
            woken = asyncio.create_task(self._woken.wait())
            stopped = asyncio.create_task(stop.wait())
            try:
                await asyncio.wait({woken, stopped}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in (woken, stopped):
                    task.cancel()
                await asyncio.gather(woken, stopped, return_exceptions=True)
            if stop.is_set():
                break
            self._woken.clear()
            await self.summarize_new()

    async def summarize_new(self) -> tuple[SummaryOutcome, ...]:
        """Summarize the assessments stored after the mark, newest first, one at a time.

        Returns:
            How each summarized assessment ended; empty when nothing was new, the feature
            is off, AI is not ready, or the pass failed (logged by its error's type only).
        """
        try:
            return await self._summarize_new()
        except Exception as error:  # noqa: BLE001 - a summary never stops serve's loop
            LOGGER.warning("change summaries failed (%s)", type(error).__name__)
            return ()

    async def _summarize_new(self) -> tuple[SummaryOutcome, ...]:
        mark = self._mark if self._mark is not None else await asyncio.to_thread(self.prime)
        new = await asyncio.to_thread(self._assessments.stored_after, mark, MAX_NEW_ASSESSMENTS)
        if not new:
            return ()
        self._mark = max(mark, new[0][0])
        if not self._service.settings.change_summaries:
            LOGGER.info("change summaries are off; %d new assessment(s) not summarized", len(new))
            return ()
        outcomes: list[SummaryOutcome] = []
        for assessment_id, location in new:
            state = await asyncio.to_thread(self._service.state)
            if state.state != "ready":
                LOGGER.info("change summaries skipped: AI is %s (%s)", state.state, state.reason)
                break
            outcome = await self._summaries.summarize(assessment_id)
            LOGGER.info(
                "change summary for assessment %d: %s (%s)",
                assessment_id,
                outcome.status,
                outcome.reason or "-",
            )
            if outcome.output_id is not None and not outcome.reused:
                self._publish(
                    "ai",
                    {"output_id": outcome.output_id, "ai_kind": "summary", "location": location},
                    ("briefings",),
                    deduplicate=True,
                )
            outcomes.append(outcome)
        return tuple(outcomes)
