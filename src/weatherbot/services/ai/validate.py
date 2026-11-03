# src/weatherbot/services/ai/validate.py
"""The validators: no AI text reaches a page or a terminal unless it passes them.

Every briefing section, briefing, and change summary is checked against its own context:

- ``level``: an explicit level statement ("level 4", "threat level four", "alert level
  4", "level-4", "levels 3 and 4", "the level is 4") names only the engine's level (a
  change summary: the previous or the new one). The ladder's labels and product names
  ("Hurricane Warning", "Watch / Hurricane Threat") are never read as levels, nor is "a
  level of preparedness", a water level ("water levels of 2 to 4 feet"), or a number
  with a unit after it.
- ``source``: every source key cited (``S1``, ``S2``, ...) is one the context holds, and
  every structured key field holds exactly such a key.
- ``url``: no URL (a scheme, ``www.``, or a bare host with a path). The NOAA texts'
  links were removed before the request, so any URL is the model's own.
- ``coordinate``: no coordinate pair or position (decimal, ``20.3N 106.9W``-style, or
  "latitude 20.3 North, longitude 106.9 West") unless the same position appears in the
  context's NOAA text: a storm's position quoted from its advisory is public. Positions
  are compared as signed decimals, so a change of notation is still a quotation.
- ``empty`` and ``length``: no required section empty, no empty item, and no text past
  its bound (a section 1,500 characters, a timeline 12 items, actions 8, a summary 600).

A ``Violation`` names its rule and the section in fixed text and never quotes the model,
because a withheld product's text is never stored, logged, printed, or shown.

The chat checks each sentence before it is shown: ``sentence_violations`` applies the URL
rule, the coordinate rule against the NOAA texts the tools returned, and the current-level
check (``current_level_asserted``: "is level 4", "the current or official level is 4",
"level 4 now" for another level than the engine's latest). A narration of an outlook
graphic (``validate_narration``) may state no level at all, no URL, and no position, must
carry its caveat, and may state only the chances its TWO states (``chance``): "20%"
matches the TWO's "20 percent".

The module is pure: it imports the models, the standard library, and the AI schemas and
context only.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol

from weatherbot.models import AlertLevel
from weatherbot.services.ai.context import (
    URL_PATTERN,
    BriefingContext,
    ChangeContext,
    NoaaText,
    SourceRef,
)
from weatherbot.services.ai.schemas import (
    BRIEFING_SECTIONS,
    Briefing,
    ChangeSummary,
    OutlookNarration,
    SectionName,
    SourceNote,
    TimelineItem,
)

type ViolationRule = Literal["level", "source", "url", "coordinate", "empty", "length", "chance"]
type SectionValue = str | Sequence[TimelineItem] | Sequence[str] | Sequence[SourceNote]

SECTION_LIMIT: Final = 1_500
TIMELINE_LIMIT: Final = 12
ACTIONS_LIMIT: Final = 8
SUMMARY_LIMIT: Final = 600
REQUIRED_SECTIONS: Final[frozenset[SectionName]] = frozenset(
    {"situation", "what_it_means_here", "actions"}
)
"""The sections a briefing cannot leave empty; a quiet day may have no timeline."""
NUMBER_WORDS: Final[Mapping[str, int]] = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_NUMBER: Final = r"(?:[1-5]|one|two|three|four|five)(?![\w.]*\d)"
_CONNECTOR: Final = (
    r"(?:\s+(?:is|was|are|were|of|at|remains|remained|stays|stayed|stands|now|"
    r"currently|still|rose|rises|fell|falls|moved|moves|went|goes|changed|"
    r"has|had|been|become|became|to|from)\b)*"
)
LEVEL_PATTERN: Final = re.compile(
    rf"\b(?:(?:threat|alert)\s+)?levels?{_CONNECTOR}[\s:=-]*(?P<first>{_NUMBER})\b"
    rf"(?P<rest>(?:\s*(?:,|and|or|to|through|-|\u2013)\s*(?:level\s+)?{_NUMBER}\b)*)",
    re.IGNORECASE,
)
"""An explicit level statement, and any list that follows it ("levels 3 and 4")."""
_LIST_NUMBER: Final = re.compile(rf"\b{_NUMBER}\b", re.IGNORECASE)
_NOT_LADDER_BEFORE: Final = re.compile(
    r"\b(?:water|sea|tide|tidal|ground|surge|river|lake|flood|noise|rainfall)\s*$",
    re.IGNORECASE,
)
_UNIT_AFTER: Final = re.compile(
    r"\s*(?:feet|foot|ft\b|inch|inches|meters?|metres?|cm\b|%|percent|mph|km|kt\b|knots?|"
    r"miles?|mi\b|mb\b|millibars?)",
    re.IGNORECASE,
)
SOURCE_KEY: Final = re.compile(r"\bS\d{1,3}\b")
_DEGREES: Final = r"\s*°?\s*"
_HEMISPHERE_PAIR: Final = re.compile(
    rf"(?P<lat>\d{{1,2}}(?:\.\d+)?){_DEGREES}(?P<ns>[NS])\b[\s,/;]*"
    rf"(?P<lon>\d{{1,3}}(?:\.\d+)?){_DEGREES}(?P<ew>[EW])\b",
    re.IGNORECASE,
)
_WORDED_PAIR: Final = re.compile(
    r"\blat(?:itude)?\.?\s*[:=]?\s*(?P<lat>-?\d{1,2}(?:\.\d+)?)\s*°?\s*(?P<ns>north|south|[NS])?"
    r"\b[\s,;/]*(?:and\s+)?lon(?:gitude)?\.?\s*[:=]?\s*(?P<lon>-?\d{1,3}(?:\.\d+)?)\s*°?\s*"
    r"(?P<ew>east|west|[EW])?\b",
    re.IGNORECASE,
)
_DECIMAL_PAIR: Final = re.compile(
    r"(?<![\w.])(?P<lat>-?\d{1,2}\.\d+)\s*,\s*(?P<lon>-?\d{1,3}\.\d+)(?!\w|\.\d)"
)
_LATITUDE_MAX: Final = 90.0
_LONGITUDE_MAX: Final = 180.0
_FILLER: Final = r"(?:(?!not\b|never\b|no\b|longer\b)\w+\s+){0,2}?"
_ASSERTED_PATTERNS: Final = (
    re.compile(
        rf"\b(?:is|are|remains|stays|stands|sits|now|currently|presently)\s+{_FILLER}"
        rf"(?:at\s+)?(?:(?:threat|alert)\s+)?level[\s:=-]*(?P<number>{_NUMBER})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:current|present|today's|latest|official)\s+(?:(?:threat|alert)\s+)?level"
        rf"(?:\s+(?:is|of|stands at|sits at|remains))?[\s:=-]*(?P<number>{_NUMBER})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\blevel\s+(?:is|remains|stays|stands|sits)\s+(?:at\s+)?(?:now\s+)?"
        rf"(?P<number>{_NUMBER})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\blevel[\s:=-]*(?P<number>{_NUMBER})\s+(?:now|currently|right now|today)\b",
        re.IGNORECASE,
    ),
)
"""Statements that a location's level is something now, for one chat sentence."""
NARRATION_SUMMARY_LIMIT: Final = 800
AREA_LIMIT: Final = 600
"""Twice the 300 characters the narration prompt asks for: ten live narrations on
2026-11-02 wrote 240 to 337, and one in the live eval passed the earlier 400."""
AREAS_LIMIT: Final = 8
PERCENTAGE: Final = re.compile(
    r"(?<!\w)(?<!\d\.)(?P<number>\d{1,3}(?:\.\d+)?)\s*(?:%|percent\b|per\s+cent\b)",
    re.IGNORECASE,
)
"""A percentage: a number followed by "%", "percent", or "per cent". NHC writes a chance
after an ellipsis ("low...20 percent"), so only a decimal's fractional digits are refused
as a start."""


@dataclass(frozen=True)
class Violation:
    """One broken rule: which rule, and fixed text naming the section, never the model's."""

    rule: ViolationRule
    detail: str


class Grounding(Protocol):
    """What a validator checks a text against: the context's sources and NOAA texts."""

    @property
    def sources(self) -> tuple[SourceRef, ...]:
        """The sources the context lists."""
        ...

    @property
    def noaa(self) -> tuple[NoaaText, ...]:
        """The NOAA texts the context carries."""
        ...


def _number(text: str) -> int:
    lowered = text.lower()
    return NUMBER_WORDS.get(lowered) or int(lowered)


def levels_stated(text: str) -> frozenset[int]:
    """Find the levels a text states explicitly.

    Args:
        text: Model text.

    Returns:
        Every level number from 1 to 5 written after "level", "threat level", or "alert
        level" (or "levels", or "level is" and the like), and in a list that follows one.
        A label or a product name is never a level, nor is a water level or a number
        with a unit after it.
    """
    found: set[int] = set()
    for match in LEVEL_PATTERN.finditer(text):
        if _NOT_LADDER_BEFORE.search(text, 0, match.start()):
            continue
        if _UNIT_AFTER.match(text, match.end()):
            continue
        found.add(_number(match["first"]))
        found.update(_number(item) for item in _LIST_NUMBER.findall(match["rest"]))
    return frozenset(found)


def source_keys(text: str) -> frozenset[str]:
    """Find the source keys a text cites.

    Args:
        text: Model text.

    Returns:
        Every ``S`` followed by digits, as a whole word.
    """
    return frozenset(SOURCE_KEY.findall(text))


def has_url(text: str) -> bool:
    """Whether a text carries a URL: a scheme, ``www.``, or a bare host with a path.

    Args:
        text: Model text.

    Returns:
        Whether it does.
    """
    return URL_PATTERN.search(text) is not None


def _signed(value: str, hemisphere: str | None, negative: str) -> str:
    magnitude = value.lstrip("-")
    if "." in magnitude:
        magnitude = magnitude.rstrip("0").rstrip(".")
    magnitude = magnitude.lstrip("0") or "0"
    if magnitude.startswith("."):
        magnitude = f"0{magnitude}"
    sign = value.startswith("-") or (hemisphere is not None and hemisphere[0].upper() == negative)
    return f"-{magnitude}" if sign and magnitude != "0" else magnitude


def positions(text: str) -> frozenset[tuple[str, str]]:
    """Find every coordinate pair or position in a text, normalized to signed decimals.

    Args:
        text: Any text.

    Returns:
        Each pair as signed latitude and longitude text (``("20.3", "-106.9")``), in any
        of the notations: hemisphere letters, "latitude ... longitude ...", or a decimal
        pair. A pair out of range is not a position.
    """
    found: set[tuple[str, str]] = set()
    for pattern in (_HEMISPHERE_PAIR, _WORDED_PAIR, _DECIMAL_PAIR):
        for match in pattern.finditer(text):
            groups = match.groupdict()
            lat = _signed(match["lat"], groups.get("ns"), "S")
            lon = _signed(match["lon"], groups.get("ew"), "W")
            if abs(float(lat)) <= _LATITUDE_MAX and abs(float(lon)) <= _LONGITUDE_MAX:
                found.add((lat, lon))
    return frozenset(found)


def unquoted_positions(text: str, noaa: Sequence[NoaaText]) -> frozenset[tuple[str, str]]:
    """Find the positions in a text that no NOAA text of the context states.

    Args:
        text: Model text.
        noaa: The context's NOAA texts.

    Returns:
        The positions the model wrote that it did not quote.
    """
    quoted: set[tuple[str, str]] = set()
    for item in noaa:
        quoted.update(positions(item.text))
    return positions(text) - quoted


def _text_rules(
    section: str,
    texts: Sequence[str],
    grounding: Grounding,
    levels: frozenset[int],
    keys: Sequence[str] = (),
) -> list[Violation]:
    violations: list[Violation] = []
    joined = "\n".join(texts)
    known = {source.key for source in grounding.sources}
    if not levels_stated(joined) <= levels:
        violations.append(Violation("level", f"{section} states a level the engine did not"))
    if not source_keys(joined) <= known or not set(keys) <= known:
        violations.append(Violation("source", f"{section} cites a source the context lacks"))
    if has_url(joined):
        violations.append(Violation("url", f"{section} carries a URL"))
    if unquoted_positions(joined, grounding.noaa):
        violations.append(
            Violation("coordinate", f"{section} carries a position no NOAA product states")
        )
    return violations


def _parts(name: SectionName, value: SectionValue) -> tuple[list[str], list[str]]:
    """A section's texts, and the structured key fields among them."""
    if isinstance(value, str):
        return [value], []
    texts: list[str] = []
    keys: list[str] = []
    for item in value:
        if isinstance(item, TimelineItem):
            texts.extend((item.when, item.what, *item.sources))
            keys.extend(item.sources)
        elif isinstance(item, SourceNote):
            texts.extend((item.key, item.why))
            keys.append(item.key)
        else:
            texts.append(item)
    del name
    return texts, keys


def _shape_rules(name: SectionName, value: SectionValue, texts: Sequence[str]) -> list[Violation]:
    violations: list[Violation] = []
    empty_item = any(not text.strip() for text in texts)
    if (name in REQUIRED_SECTIONS and not "".join(texts).strip()) or empty_item:
        violations.append(Violation("empty", f"{name} is empty or has an empty item"))
    count = 0 if isinstance(value, str) else len(value)
    if sum(len(text) for text in texts) > SECTION_LIMIT:
        violations.append(Violation("length", f"{name} passes {SECTION_LIMIT} characters"))
    elif name == "timeline" and count > TIMELINE_LIMIT:
        violations.append(Violation("length", f"timeline passes {TIMELINE_LIMIT} items"))
    elif name == "actions" and count > ACTIONS_LIMIT:
        violations.append(Violation("length", f"actions passes {ACTIONS_LIMIT} items"))
    return violations


def validate_section(
    name: SectionName, value: SectionValue, context: BriefingContext
) -> tuple[Violation, ...]:
    """Check one briefing section: every rule that can judge a section alone.

    Args:
        name: The section.
        value: Its value, of its schema's type.
        context: The briefing's context.

    Returns:
        The violations; none when the section may be released.
    """
    texts, keys = _parts(name, value)
    violations = _shape_rules(name, value, texts)
    allowed = frozenset({context.level.number})
    violations.extend(_text_rules(name, texts, context, allowed, keys))
    return tuple(violations)


def validate_briefing(briefing: Briefing, context: BriefingContext) -> tuple[Violation, ...]:
    """Check a whole briefing: each section, allowing only the engine's level.

    Args:
        briefing: The briefing.
        context: Its context.

    Returns:
        The violations, section by section in order.
    """
    return tuple(
        violation
        for name in BRIEFING_SECTIONS
        for violation in validate_section(name, getattr(briefing, name), context)
    )


def validate_summary(summary: ChangeSummary, context: ChangeContext) -> tuple[Violation, ...]:
    """Check a change summary, allowing the previous and the new level.

    Args:
        summary: The summary.
        context: Its context.

    Returns:
        The violations.
    """
    violations: list[Violation] = []
    if not summary.summary.strip() or any(not key.strip() for key in summary.sources):
        violations.append(Violation("empty", "summary is empty or has an empty item"))
    if len(summary.summary) > SUMMARY_LIMIT:
        violations.append(Violation("length", f"summary passes {SUMMARY_LIMIT} characters"))
    allowed = frozenset({context.previous_level.number, context.level.number})
    texts = [summary.summary, *summary.sources]
    violations.extend(_text_rules("summary", texts, context, allowed, summary.sources))
    return tuple(violations)


def current_level_asserted(sentence: str, levels: Mapping[str, AlertLevel]) -> bool:
    """Whether a sentence says a location's current level is other than the engine's.

    Args:
        sentence: One sentence of model text.
        levels: Each location's latest level, by name.

    Returns:
        True when the sentence asserts a current level ("is level 4", "the current level
        is 4", "level 4 now") that is not the engine's latest for the location it names,
        or for any location when it names none. A negated statement ("is not level 5")
        asserts nothing.
    """
    lowered = sentence.lower()
    named = [level for name, level in levels.items() if name.lower() in lowered]
    allowed = {int(level) for level in (named or levels.values())}
    return any(
        _number(match["number"]) not in allowed
        for pattern in _ASSERTED_PATTERNS
        for match in pattern.finditer(sentence)
    )


def sentence_violations(
    sentence: str, context: Grounding, levels: Mapping[str, AlertLevel]
) -> tuple[Violation, ...]:
    """Check one chat sentence: a URL, an unquoted position, or another current level.

    Args:
        sentence: One sentence of model text.
        context: The NOAA texts the conversation quoted from.
        levels: Each location's latest level, by name.

    Returns:
        The violations; any one withholds the rest of the answer.
    """
    violations: list[Violation] = []
    if has_url(sentence):
        violations.append(Violation("url", "the answer carries a URL"))
    if unquoted_positions(sentence, context.noaa):
        violations.append(Violation("coordinate", "the answer carries an unquoted position"))
    if current_level_asserted(sentence, levels):
        violations.append(Violation("level", "the answer states another current level"))
    return tuple(violations)


def percentages(text: str) -> frozenset[float]:
    """Find the percentages a text states, as numbers.

    Args:
        text: Any text.

    Returns:
        Each number written before "%", "percent", or "per cent", so "20%" and "20
        percent" are the same number.
    """
    return frozenset(float(match["number"]) for match in PERCENTAGE.finditer(text))


def _narration_texts(narration: OutlookNarration) -> list[str]:
    texts = [narration.summary]
    for area in narration.areas:
        texts.extend((area.description, area.chance_text))
    texts.append(narration.caveat)
    return texts


def _narration_shape(narration: OutlookNarration) -> list[Violation]:
    violations: list[Violation] = []
    blank_area = any(
        not area.description.strip() or not area.chance_text.strip() for area in narration.areas
    )
    if not narration.summary.strip() or not narration.caveat.strip() or blank_area:
        violations.append(
            Violation("empty", "the narration's summary or caveat is empty, or an area is")
        )
    too_long = len(narration.summary) > NARRATION_SUMMARY_LIMIT or any(
        len(area.description) > AREA_LIMIT for area in narration.areas
    )
    if too_long or len(narration.areas) > AREAS_LIMIT:
        violations.append(Violation("length", "the narration passes its bounds"))
    return violations


def validate_narration(narration: OutlookNarration, two_text: str) -> tuple[Violation, ...]:
    """Check a narration of an outlook graphic against its basin's TWO.

    Args:
        narration: The narration.
        two_text: The TWO's text as the request carried it.

    Returns:
        The violations: a level statement of any kind, a URL, any coordinate or position
        (even one the TWO states), an empty summary, caveat, or area, a text past its
        bound, or a percentage that the TWO's text does not state (compared as numbers).
    """
    violations = _narration_shape(narration)
    joined = "\n".join(_narration_texts(narration))
    if levels_stated(joined):
        violations.append(Violation("level", "the narration states a level"))
    if has_url(joined):
        violations.append(Violation("url", "the narration carries a URL"))
    if positions(joined):
        violations.append(Violation("coordinate", "the narration carries a position"))
    if not percentages(joined) <= percentages(two_text):
        violations.append(Violation("chance", "the narration states a chance the TWO does not"))
    return tuple(violations)


def first_violation(violations: Iterable[Violation]) -> Violation | None:
    """The first violation, which names the product's withheld reason.

    Args:
        violations: A validator's result.

    Returns:
        The first one, or ``None`` when there is none.
    """
    return next(iter(violations), None)
