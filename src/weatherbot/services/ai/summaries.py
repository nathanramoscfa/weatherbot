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
``unavailable`` and stores nothing. ``latest`` reads a location's summaries, newest first.
Phase 6 Step 4 wires the service into ``serve``.

Nothing here logs a prompt, a context, or an answer. The module loads no SDK.
"""

import asyncio
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
from weatherbot.services.ai.service import AiService
from weatherbot.services.ai.validate import first_violation, validate_summary
from weatherbot.services.persistence.repositories import AssessmentRepository, StoredAssessment

type SummaryStatus = Literal["ok", "withheld", "skipped", "unavailable"]

SUMMARY_MAX_TOKENS: Final = 1_500
SUMMARY_EFFORT: Final = "low"


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
        self._outputs = OutputRepository(service.engine, now=service.clock)
        self._assessments = AssessmentRepository(service.engine)

    def latest(self, location: str, limit: int) -> tuple[StoredOutput, ...]:
        """Read a location's change summaries, newest first.

        Args:
            location: The location's name.
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
