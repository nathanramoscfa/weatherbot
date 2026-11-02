# tests/ai/test_ai_validators.py
"""The validators: each rule, the ladder's own words never read as levels, and chat sentences."""

from datetime import UTC, datetime

import pytest

from weatherbot.models import AlertLevel
from weatherbot.services.ai.context import (
    BriefingContext,
    ChangeContext,
    LevelRef,
    NoaaText,
    SourceRef,
)
from weatherbot.services.ai.schemas import (
    AreaNote,
    Briefing,
    ChangeSummary,
    OutlookNarration,
    SourceNote,
    TimelineItem,
)
from weatherbot.services.ai.validate import (
    ACTIONS_LIMIT,
    AREAS_LIMIT,
    NARRATION_SUMMARY_LIMIT,
    SECTION_LIMIT,
    SUMMARY_LIMIT,
    TIMELINE_LIMIT,
    current_level_asserted,
    first_violation,
    has_url,
    levels_stated,
    percentages,
    positions,
    sentence_violations,
    source_keys,
    unquoted_positions,
    validate_briefing,
    validate_narration,
    validate_section,
    validate_summary,
)

AS_OF = datetime(2026, 10, 12, 18, tzinfo=UTC)
TCP = (
    "...SIMON MOVING NORTHWEST...\n"
    "LOCATION...20.3N 106.9W\n"
    "the center of Hurricane Simon was located near latitude 20.3 North, longitude 106.9 West."
)
SOURCES = (
    SourceRef(key="S1", source_id="nhc-text-products", code="TCP", title="NHC public advisory"),
    SourceRef(key="S2", source_id="nhc-map-tropical-summary", title="NHC wind odds"),
)


def _level(number: int) -> LevelRef:
    level = AlertLevel(number)
    return LevelRef(number=number, label=level.label, actions=level.actions)


def _context(level: int = 3) -> BriefingContext:
    return BriefingContext(
        location="Miami-Dade County Hall",
        as_of=AS_OF,
        level=_level(level),
        rule="hurricane_cone",
        trigger="The location is inside the cone.",
        complete=True,
        unavailable=(),
        evidence=(),
        official=(),
        wind_probabilities=(),
        threats=(),
        changes=(),
        stale_sources=(),
        sources=SOURCES,
        noaa=(NoaaText(key="S1", code="TCP", issued=AS_OF, text=TCP),),
    )


def _change_context(previous: int = 2, level: int = 3) -> ChangeContext:
    return ChangeContext(
        location="Miami-Dade County Hall",
        as_of=AS_OF,
        previous_level=_level(previous),
        level=_level(level),
        rule="hurricane_cone",
        changes=(),
        evidence=(),
        sources=SOURCES,
    )


def _briefing(**changes: object) -> Briefing:
    fields: dict[str, object] = {
        "situation": "Simon is near 20.3N 106.9W [S1].",
        "what_it_means_here": "Weatherbot's level here is level 3, Watch / Hurricane Threat [S1].",
        "timeline": [TimelineItem(when="18Z", what="Closest approach.", sources=["S1"])],
        "actions": ["Stock supplies.", "Follow the instructions of your local officials."],
        "sources": [SourceNote(key="S1", why="the advisory")],
    }
    return Briefing.model_validate(fields | changes)


# Level statements ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "levels"),
    [
        ("Weatherbot's level is level 3.", {3}),
        ("The threat level 4 applies.", {4}),
        ("This is level four.", {4}),
        ("An alert level of 5.", {5}),
        ("A level-4 day.", {4}),
        ("Levels 3 and 4 differ.", {3, 4}),
        ("The level rose from 3 to 4.", {3, 4}),
        ("From level 3 to level 4.", {3, 4}),
        ("The level is 2 now.", {2}),
        ("LEVEL 1 (All Clear).", {1}),
    ],
)
def test_explicit_level_statements_are_found(text: str, levels: set[int]) -> None:
    assert levels_stated(text) == levels


@pytest.mark.parametrize(
    "text",
    [
        "A Hurricane Warning covers the coast.",
        "Watch / Hurricane Threat",
        "Warning / Watch / Evacuation",
        "Tropical Storm Threat",
        "Keep a level of preparedness.",
        "Water levels of 2 to 4 feet above ground level are possible.",
        "Surge could raise water levels 3 feet.",
        "A Category 4 hurricane with 34-kt winds and a 10-20% band.",
        "Level 10 does not exist.",
        "The level is 3.5 on some scale.",
        "Sea level 2 m above normal.",
    ],
)
def test_the_ladders_words_and_other_levels_are_never_read_as_levels(text: str) -> None:
    assert levels_stated(text) == frozenset()


def test_source_keys_urls_and_positions_are_found() -> None:
    assert source_keys("As [S1] and S12 say, not SS1 or S1a.") == {"S1", "S12"}
    assert has_url("see https://example.invalid/x")
    assert has_url("see www.example.invalid")
    assert has_url("see hurricanes.gov/graphics_ep5.shtml")
    assert not has_url("winds of 34 kt/h and a.m./p.m. times, U.S./Mexico")
    assert positions("near 20.3N 106.9W") == {("20.3", "-106.9")}
    assert positions("latitude 20.3 North, longitude 106.9 West") == {("20.3", "-106.9")}
    assert positions("at 25.80, -80.19") == {("25.8", "-80.19")}
    assert positions("lat 12.30 lon -45.6") == {("12.3", "-45.6")}
    assert positions("12.3S 45.6E and 95.0, 10.0") == {("-12.3", "45.6")}
    assert positions("1.5, 200.5 is out of range") == frozenset()


def test_a_position_is_quoted_whatever_its_notation() -> None:
    noaa = (NoaaText(key="S1", code="TCP", text=TCP),)

    assert unquoted_positions("near 20.3 N 106.9 W", noaa) == frozenset()
    assert unquoted_positions("near 20.30N 106.90W", noaa) == frozenset()
    assert unquoted_positions("near 20.4N 106.9W", noaa) == {("20.4", "-106.9")}


# Briefings ----------------------------------------------------------------------------------


def test_a_briefing_that_keeps_to_its_context_passes() -> None:
    assert validate_briefing(_briefing(), _context()) == ()


@pytest.mark.parametrize(
    ("changes", "rule"),
    [
        ({"situation": "It is level 4 now."}, "level"),
        ({"situation": "As the bulletin says [S7]."}, "source"),
        ({"sources": [SourceNote(key="TCP", why="the advisory")]}, "source"),
        ({"situation": "Read hurricanes.gov/graphics_ep5.shtml."}, "url"),
        ({"situation": "The center is near 25.8, -80.2."}, "coordinate"),
        ({"what_it_means_here": "   "}, "empty"),
        ({"actions": []}, "empty"),
        ({"actions": ["Stock supplies.", ""]}, "empty"),
        ({"situation": "x" * (SECTION_LIMIT + 1)}, "length"),
        (
            {"timeline": [TimelineItem(when="t", what="w", sources=[])] * (TIMELINE_LIMIT + 1)},
            "length",
        ),
        ({"actions": ["Act."] * (ACTIONS_LIMIT + 1)}, "length"),
    ],
)
def test_each_rule_rejects_a_briefing(changes: dict[str, object], rule: str) -> None:
    found = first_violation(validate_briefing(_briefing(**changes), _context()))

    assert found is not None
    assert found.rule == rule


def test_a_violation_never_quotes_the_model() -> None:
    hidden = "a sentence the model wrote at level 5"

    found = validate_briefing(_briefing(situation=hidden), _context())

    assert found
    assert all(hidden not in item.detail and "5" not in item.detail for item in found)


def test_a_quiet_briefing_may_have_no_timeline_and_no_sources() -> None:
    assert validate_section("timeline", [], _context()) == ()
    assert validate_section("sources", [], _context()) == ()


def test_a_section_allows_only_the_engines_level() -> None:
    assert validate_section("situation", "At level 1 [S1].", _context(level=1)) == ()
    assert validate_section("situation", "At level 1 [S1].", _context(level=3))


# Summaries ----------------------------------------------------------------------------------


def test_a_summary_allows_the_previous_and_the_new_level() -> None:
    summary = ChangeSummary(summary="The level rose from level 2 to level 3 [S2].", sources=["S2"])

    assert validate_summary(summary, _change_context()) == ()


@pytest.mark.parametrize(
    ("summary", "rule"),
    [
        (ChangeSummary(summary="Now level 4.", sources=[]), "level"),
        (ChangeSummary(summary="Up a level [S2].", sources=["S9"]), "source"),
        (ChangeSummary(summary="See www.example.invalid.", sources=[]), "url"),
        (ChangeSummary(summary="Simon is near 20.3N 106.9W.", sources=[]), "coordinate"),
        (ChangeSummary(summary=" ", sources=[]), "empty"),
        (ChangeSummary(summary="Up.", sources=[""]), "empty"),
        (ChangeSummary(summary="x" * (SUMMARY_LIMIT + 1), sources=[]), "length"),
    ],
)
def test_each_rule_rejects_a_summary(summary: ChangeSummary, rule: str) -> None:
    found = first_violation(validate_summary(summary, _change_context()))

    assert found is not None
    assert found.rule == rule


# Chat sentences ------------------------------------------------------------------------------

LEVELS = {"Miami-Dade County Hall": AlertLevel(3), "Parliament Square": AlertLevel(1)}


@pytest.mark.parametrize(
    ("sentence", "asserted"),
    [
        ("Miami-Dade County Hall is at level 3.", False),
        ("Miami-Dade County Hall is at level 5.", True),
        ("Parliament Square is now level 3.", True),
        ("The current threat level is 4.", True),
        ("The current level is 3.", False),
        ("Level 5 now applies everywhere.", True),
        ("Miami-Dade County Hall is not level 5.", False),
        ("Level 5 means a Hurricane Warning covers the location.", False),
        ("A level of preparedness helps.", False),
        ("The official level is 4.", True),
        ("Its official level was 4 on Monday.", False),
        ("Miami-Dade County Hall is at least level 3, Watch / Hurricane Threat.", False),
    ],
)
def test_a_sentence_asserting_another_current_level_is_found(
    sentence: str, *, asserted: bool
) -> None:
    assert current_level_asserted(sentence, LEVELS) is asserted


def test_a_chat_sentence_is_checked_for_urls_positions_and_levels() -> None:
    context = _context()

    assert sentence_violations("Simon is near 20.3N 106.9W [S1].", context, LEVELS) == ()
    rules = [
        item.rule
        for item in sentence_violations(
            "It is level 5 now; see www.example.invalid near 25.8, -80.2.", context, LEVELS
        )
    ]
    assert rules == ["url", "coordinate", "level"]
    assert first_violation(()) is None


# Narrations --------------------------------------------------------------------------------

TWO = (
    "Eastern Tropical Atlantic:\n"
    "* Formation chance through 48 hours...low...near 0 percent.\n"
    "* Formation chance through 7 days...low...20 percent.\n"
    "Another system has a 2.5 percent chance, which no area carries."
)
NARRATION = OutlookNarration(
    summary="The outlook marks one area in the eastern tropical Atlantic.",
    areas=[AreaNote(description="An area of low pressure.", chance_text="20%")],
    caveat="This is an AI description of the official graphic, which governs.",
)


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("20%", {20.0}),
        ("low...20 percent.", {20.0}),
        ("near 100 percent", {100.0}),
        ("a 2.5% chance", {2.5}),
        ("20 per cent and 30 %", {20.0, 30.0}),
        ("level 2 and 7 days", set[float]()),
    ],
)
def test_percentages_are_read_as_numbers(text: str, found: set[float]) -> None:
    assert percentages(text) == found


def test_a_narration_quoting_its_twos_chances_passes() -> None:
    assert validate_narration(NARRATION, TWO) == ()
    assert validate_narration(NARRATION.model_copy(update={"areas": []}), TWO) == ()


@pytest.mark.parametrize(
    ("changes", "rule"),
    [
        ({"areas": [AreaNote(description="A low.", chance_text="30%")]}, "chance"),
        ({"summary": "It has a 5 percent chance."}, "chance"),
        ({"summary": "Weatherbot's level is level 2 here."}, "level"),
        ({"summary": "See hurricanes.gov/gtwo for the map."}, "url"),
        ({"summary": "A low near 12.3N 45.6W."}, "coordinate"),
        ({"caveat": "  "}, "empty"),
        ({"areas": [AreaNote(description="", chance_text="20%")]}, "empty"),
        ({"summary": "x" * (NARRATION_SUMMARY_LIMIT + 1)}, "length"),
        (
            {"areas": [AreaNote(description="A low.", chance_text="20%")] * (AREAS_LIMIT + 1)},
            "length",
        ),
    ],
)
def test_each_rule_withholds_a_narration(changes: dict[str, object], rule: str) -> None:
    found = validate_narration(NARRATION.model_copy(update=changes), TWO)

    assert rule in [item.rule for item in found]
