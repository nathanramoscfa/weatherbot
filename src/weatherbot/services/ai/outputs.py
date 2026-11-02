# src/weatherbot/services/ai/outputs.py
"""``OutputRepository``: the AI's stored products, read and written through the AI engine.

A product is stored once, as it ended: ``ok`` with its validated content (the product and
the sources its keys name, never a URL), or ``withheld`` with its reason and no content,
because a withheld product's text is never stored. A briefing is written once per
location, assessment, model, and prompt version (``briefing_for`` finds the one to reuse);
a change summary once per assessment, never rewritten (``summary_for``); a narration once
per outlook graphic, the TWO text it was checked against (whose SHA-256 its content
holds), model, and prompt version (``narration_for``). The repository
runs on the AI engine (``guard.ai_engine``), whose authorizer lets it write ``ai_outputs``
and ``ai_calls`` and nothing else, and every write begins ``IMMEDIATE``. Once a product is
committed, the ``stored`` hook (the AI service's) hears of it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, get_args
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from weatherbot.services.persistence.database import writing_session
from weatherbot.services.persistence.tables import AiOutputRow

type OutputKind = Literal["briefing", "summary", "narration"]
type OutputStatus = Literal["ok", "withheld"]

OUTPUT_KINDS: Final[tuple[OutputKind, ...]] = get_args(OutputKind.__value__)
MAX_REASON_LENGTH: Final = 32


@dataclass(frozen=True)
class NewOutput:
    """A product to store: what wrote it, for what, and how it ended."""

    kind: OutputKind
    model: str
    prompt_version: str
    status: OutputStatus
    content: dict[str, Any] | None
    location_name: str | None = None
    assessment_id: int | None = None
    snapshot_id: UUID | None = None
    graphic_sha256: str | None = None
    withheld_reason: str | None = None
    call_id: int | None = None

    def __post_init__(self) -> None:
        """Refuse a withheld product with content, or an ``ok`` one without.

        Raises:
            ValueError: The status and the content disagree.
        """
        if (self.status == "ok") != (self.content is not None) or (
            (self.status == "withheld") != (self.withheld_reason is not None)
        ):
            message = "an ok product has content; a withheld one has a reason and no content"
            raise ValueError(message)


@dataclass(frozen=True)
class StoredOutput:
    """A stored product."""

    id: int
    kind: str
    location_name: str | None
    assessment_id: int | None
    snapshot_id: UUID | None
    graphic_sha256: str | None
    model: str
    prompt_version: str
    status: str
    withheld_reason: str | None
    content: dict[str, Any] | None
    call_id: int | None
    created_at: datetime


def _stored(row: AiOutputRow) -> StoredOutput:
    return StoredOutput(
        id=row.id,
        kind=row.kind,
        location_name=row.location_name,
        assessment_id=row.assessment_id,
        snapshot_id=row.snapshot_id,
        graphic_sha256=row.graphic_sha256,
        model=row.model,
        prompt_version=row.prompt_version,
        status=row.status,
        withheld_reason=row.withheld_reason,
        content=row.content,
        call_id=row.call_id,
        created_at=row.created_at,
    )


class OutputRepository:
    """The AI's products: stored as they ended, read back newest first."""

    def __init__(
        self,
        engine: Engine,
        *,
        now: Callable[[], datetime],
        stored: Callable[[StoredOutput], None] | None = None,
    ) -> None:
        """Create the repository.

        Args:
            engine: The AI engine.
            now: The clock, for when a product is stored.
            stored: Hears of each product once it is committed.
        """
        self._engine = engine
        self._now = now
        self._stored = stored

    def add(self, output: NewOutput) -> StoredOutput:
        """Store a product.

        Args:
            output: The product.

        Returns:
            The stored product.
        """
        saved = self._insert(output)
        if self._stored is not None:
            self._stored(saved)
        return saved

    def _insert(self, output: NewOutput) -> StoredOutput:
        reason = output.withheld_reason[:MAX_REASON_LENGTH] if output.withheld_reason else None
        with writing_session(self._engine) as session:
            row = AiOutputRow(
                kind=output.kind,
                location_name=output.location_name,
                assessment_id=output.assessment_id,
                snapshot_id=output.snapshot_id,
                graphic_sha256=output.graphic_sha256,
                model=output.model,
                prompt_version=output.prompt_version,
                status=output.status,
                withheld_reason=reason,
                content=output.content,
                call_id=output.call_id,
                created_at=self._now(),
            )
            session.add(row)
            session.flush()
            return _stored(row)

    def _first(self, *conditions: Any) -> StoredOutput | None:  # noqa: ANN401 - SQL clauses
        with Session(self._engine) as session:
            row = session.scalar(
                select(AiOutputRow)
                .where(*conditions)
                .order_by(AiOutputRow.created_at.desc(), AiOutputRow.id.desc())
                .limit(1)
            )
            return _stored(row) if row is not None else None

    def get(self, output_id: int) -> StoredOutput | None:
        """Read one product.

        Args:
            output_id: Its id.

        Returns:
            The product, or ``None``.
        """
        with Session(self._engine) as session:
            row = session.get(AiOutputRow, output_id)
            return _stored(row) if row is not None else None

    def latest_briefing(self, location: str) -> StoredOutput | None:
        """Read a location's newest briefing, withheld or not.

        Args:
            location: The location's name.

        Returns:
            The briefing, or ``None`` when none is stored.
        """
        return self._first(AiOutputRow.kind == "briefing", AiOutputRow.location_name == location)

    def briefing_for(
        self, assessment_id: int, model: str, prompt_version: str
    ) -> StoredOutput | None:
        """Find the briefing to reuse: an ``ok`` one for the assessment, model, and prompt.

        A withheld briefing is not reused, so asking again sends a new request.

        Args:
            assessment_id: The assessment.
            model: The model.
            prompt_version: The frozen prompt's version.

        Returns:
            The briefing, or ``None``.
        """
        return self._first(
            AiOutputRow.kind == "briefing",
            AiOutputRow.assessment_id == assessment_id,
            AiOutputRow.model == model,
            AiOutputRow.prompt_version == prompt_version,
            AiOutputRow.status == "ok",
        )

    def summaries(self, location: str | None, limit: int) -> tuple[StoredOutput, ...]:
        """Read change summaries, newest first, withheld ones included.

        Args:
            location: The location's name, or ``None`` for every location.
            limit: At most this many.

        Returns:
            The summaries.

        Raises:
            ValueError: The limit is below one.
        """
        if limit < 1:
            message = "a listing holds at least one summary"
            raise ValueError(message)
        conditions = [AiOutputRow.kind == "summary"]
        if location is not None:
            conditions.append(AiOutputRow.location_name == location)
        with Session(self._engine) as session:
            rows: Sequence[AiOutputRow] = session.scalars(
                select(AiOutputRow)
                .where(*conditions)
                .order_by(AiOutputRow.created_at.desc(), AiOutputRow.id.desc())
                .limit(limit)
            ).all()
            return tuple(_stored(row) for row in rows)

    def latest_narration(self, graphic_sha256: str) -> StoredOutput | None:
        """Read the newest narration of an outlook graphic, withheld or not.

        Args:
            graphic_sha256: The graphic's PNG body's SHA-256.

        Returns:
            The narration, or ``None`` when none is stored.
        """
        return self._first(
            AiOutputRow.kind == "narration", AiOutputRow.graphic_sha256 == graphic_sha256
        )

    def narration_for(
        self, graphic_sha256: str, two_sha256: str, model: str, prompt_version: str
    ) -> StoredOutput | None:
        """Find the narration to reuse: an ``ok`` one for the graphic, its TWO, model, and prompt.

        A withheld narration is not reused, so asking again sends a new request.

        Args:
            graphic_sha256: The graphic's PNG body's SHA-256.
            two_sha256: The SHA-256 of the TWO's text the narration was checked against.
            model: The model.
            prompt_version: The narration prompt's version.

        Returns:
            The narration, or ``None``.
        """
        return self._first(
            AiOutputRow.kind == "narration",
            AiOutputRow.graphic_sha256 == graphic_sha256,
            AiOutputRow.model == model,
            AiOutputRow.prompt_version == prompt_version,
            AiOutputRow.status == "ok",
            AiOutputRow.content["two_sha256"].as_string() == two_sha256,
        )

    def summary_for(self, assessment_id: int) -> StoredOutput | None:
        """Find an assessment's change summary, withheld or not; it is never rewritten.

        Args:
            assessment_id: The assessment.

        Returns:
            The summary, or ``None``.
        """
        return self._first(
            AiOutputRow.kind == "summary", AiOutputRow.assessment_id == assessment_id
        )
