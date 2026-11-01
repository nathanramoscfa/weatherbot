# src/weatherbot/services/ai/schemas.py
"""The shapes Claude writes: a briefing and a change summary, neither with a level.

Each is a Pydantic model whose JSON Schema ``AiCaller`` sends as ``output_config.format``,
so the answer's text is JSON of exactly these fields, in this order. No field is named
``level`` or carries one: the level always comes from the engine, and the validators
(``validate.py``) withhold any text that states another. Length limits live in the
validators too, because structured outputs accept only a subset of JSON Schema.

The briefing's sections stream in field order, and ``BRIEFING_SECTIONS`` names them in
that order. This module imports pydantic and the standard library only.
"""

from typing import Final, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

type SectionName = Literal["situation", "what_it_means_here", "timeline", "actions", "sources"]
BRIEFING_SECTIONS: Final[tuple[SectionName, ...]] = get_args(SectionName.__value__)
"""The briefing's sections, in the order the model writes and the page shows them."""


class _Output(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class TimelineItem(_Output):
    """One expected development, with the products that state it."""

    when: str = Field(description="When, as the context states it: a UTC time, or a window.")
    what: str = Field(description="What happens then, in plain language.")
    sources: list[str] = Field(description="The source keys that state it, such as S2.")


class SourceNote(_Output):
    """A source the briefing used, and what it was used for."""

    key: str = Field(description="A source key from the context, such as S2.")
    why: str = Field(description="What the briefing took from it, in a few words.")


class Briefing(_Output):
    """A plain-language briefing for one location's latest assessment."""

    situation: str = Field(
        description="A paragraph per threatening storm, or one paragraph on the quiet tropics."
    )
    what_it_means_here: str = Field(
        description="What the engine's level means for this location, and why it was set."
    )
    timeline: list[TimelineItem] = Field(description="Expected developments, earliest first.")
    actions: list[str] = Field(
        description="The ladder's actions for the level, and following local officials."
    )
    sources: list[SourceNote] = Field(description="Every source key the briefing cites.")


class ChangeSummary(_Output):
    """A short summary of what changed between two assessments of one location."""

    summary: str = Field(description="What changed and what it means, in two to four sentences.")
    sources: list[str] = Field(description="The source keys the summary cites, such as S2.")
