# tests/ai/test_ai_tools.py
"""The chat's nine tools: strict, allowlisted, bounded, read-only, and privacy-reduced.

The database holds both public landmarks assessed over the recorded 2026-10-12 snapshot,
as the recorded chat cases do. Every tool runs through the AI engine.
"""

import json
import re
import sqlite3
from collections.abc import AsyncIterator, Iterator
from typing import cast

import pytest
from ai_support import replayed_service, shared_recorded_snapshot, stored_later
from eval.chat_cases import store_case_data
from source_support import NOW
from sqlalchemy import exc, text

from check_personal_data import load_landmarks
from weatherbot.services.ai.context import CUT_MARK, URL_PATTERN, NoaaText
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.prompts import ladder_text
from weatherbot.services.ai.tools import (
    RESULT_CUT,
    RESULT_LIMIT,
    TOOL_DEFINITIONS,
    TOOL_NAMES,
    Toolbox,
    ToolResult,
    bounded,
    tool_params,
)
from weatherbot.services.ai.validate import positions
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import AssessmentRepository, SnapshotRepository

pytestmark = pytest.mark.anyio

MIAMI = "Miami-Dade County Hall"
NASSAU = "Parliament Square"
EVERY_CALL: list[tuple[str, dict[str, object]]] = [
    ("list_locations", {}),
    ("get_assessment", {"location": MIAMI}),
    ("get_evidence", {"location": MIAMI}),
    ("get_alerts", {"location": MIAMI}),
    ("get_storms", {}),
    ("get_storm", {"atcf_id": "EP202026"}),
    ("get_outlook", {"basin": "atl"}),
    ("get_ladder", {}),
    ("get_history", {"location": NASSAU, "limit": 5}),
]
"""One good call of each tool, in ``TOOL_NAMES`` order."""
DRIVE_PATH = re.compile(r"\b[A-Za-z]:[\\/]")
"""A Windows path: a drive letter, a colon, and a separator."""


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


@pytest.fixture
async def toolbox(database: Database) -> AsyncIterator[Toolbox]:
    await store_case_data(database)
    engine = ai_engine(database.path)
    yield Toolbox(engine, now=lambda: NOW)
    engine.dispose()


def _document(result: ToolResult) -> dict[str, object]:
    head = result.content.split("\n\n<noaa_product", 1)[0]
    found: object = json.loads(head)
    assert isinstance(found, dict)
    return found  # pyright: ignore[reportUnknownVariableType] - a JSON object


# The definitions ---------------------------------------------------------------------------


def test_the_nine_tools_are_the_allowlist_in_definition_order() -> None:
    assert len(TOOL_NAMES) == 9  # noqa: PLR2004 - the roadmap's nine
    assert tuple(definition["name"] for definition in TOOL_DEFINITIONS) == TOOL_NAMES
    assert [name for name, _ in EVERY_CALL] == list(TOOL_NAMES)


@pytest.mark.parametrize("definition", TOOL_DEFINITIONS, ids=TOOL_NAMES)
def test_every_schema_is_strict_closed_and_requires_every_property(
    definition: dict[str, object],
) -> None:
    schema = definition["input_schema"]
    assert isinstance(schema, dict)
    properties = cast("dict[str, dict[str, object]]", schema["properties"])

    assert definition["strict"] is True
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(cast("list[str]", schema["required"])) == set(properties)
    assert not {"url", "path", "query", "sql", "file"} & set(properties)
    assert {spec["type"] for spec in properties.values()} <= {"string", "integer"}


def test_the_request_marks_only_the_last_tool_for_the_cache_and_leaves_the_definitions() -> None:
    tools = tool_params()

    assert tools[-1]["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in tool for tool in tools[:-1])
    assert all("cache_control" not in definition for definition in TOOL_DEFINITIONS)
    assert all("eager_input_streaming" not in tool for tool in tools)
    assert tool_params() == tools


# What the tools return ---------------------------------------------------------------------


async def test_every_tool_answers_from_the_stored_data(
    database: Database, toolbox: Toolbox
) -> None:
    results = toolbox.run(EVERY_CALL)

    assert [result.is_error for result in results] == [False] * len(EVERY_CALL)
    listed = _document(results[0])["locations"]
    assert [entry["name"] for entry in listed] == [MIAMI, NASSAU]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType, reportGeneralTypeIssues] - a JSON list
    assert _document(results[1])["location"] == MIAMI
    assert "noaa" not in _document(results[1])
    assert [text.code for text in results[3].noaa] == ["Rip Current Statement"]
    storms = _document(results[4])["storms"]
    assert [storm["atcf_id"] for storm in storms] == ["EP202026", "AL052019"]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType, reportGeneralTypeIssues] - a JSON list
    storm = _document(results[5])
    assert [text.code for text in results[5].noaa] == ["TCP"]
    assert storm["public_advisory"] == results[5].noaa[0].key
    assert {entry["location"] for entry in storm["threats"]} == {MIAMI, NASSAU}  # pyright: ignore[reportIndexIssue, reportUnknownVariableType, reportGeneralTypeIssues] - a JSON list
    assert [text.code for text in results[6].noaa] == ["TWO"]
    assert _document(results[7])["ladder"] == ladder_text(
        AssessmentRepository(database.engine).latest_heads()[MIAMI].thresholds
    )


async def test_no_result_carries_a_location_coordinate_a_url_or_a_path(
    database: Database, toolbox: Toolbox
) -> None:
    landmarks = [value for item in load_landmarks() for value in (str(item.lat), str(item.lon))]

    for result in toolbox.run(EVERY_CALL):
        quoted = {position for text in result.noaa for position in positions(text.text)}
        assert positions(json.dumps(_document(result))) == set()
        assert positions(result.content) <= quoted  # only a storm position a product states
        assert URL_PATTERN.search(result.content) is None
        assert [value for value in landmarks if value in result.content] == []
        assert "/points/" not in result.content
        assert DRIVE_PATH.search(result.content) is None
        assert str(database.path.parent) not in result.content


async def test_the_outlook_reads_each_basins_two_and_areas(toolbox: Toolbox) -> None:
    atlantic, pacific, central = toolbox.run(
        [("get_outlook", {"basin": basin}) for basin in ("atl", "pac", "cpac")]
    )

    assert {area["chance_7day_pct"] for area in _document(atlantic)["areas"]} == {20}  # pyright: ignore[reportIndexIssue, reportUnknownVariableType, reportGeneralTypeIssues] - a JSON list
    assert {area["chance_2day_pct"] for area in _document(pacific)["areas"]} == {100}  # pyright: ignore[reportIndexIssue, reportUnknownVariableType, reportGeneralTypeIssues] - a JSON list
    assert _document(central)["areas"] == []
    assert [text.code for text in central.noaa] == ["TWO"]


async def test_history_holds_at_most_the_limit_newest_first(
    database: Database, toolbox: Toolbox
) -> None:
    recorded = await shared_recorded_snapshot()
    first = AssessmentRepository(database.engine).latest(MIAMI)
    assert first is not None
    stored_later(database, recorded, first.assessment, 1, alerts={})

    [one, both] = toolbox.run(
        [
            ("get_history", {"location": MIAMI, "limit": 1}),
            ("get_history", {"location": MIAMI, "limit": 10}),
        ]
    )

    history = _document(both)["history"]
    assert len(_document(one)["history"]) == 1  # pyright: ignore[reportArgumentType] - a JSON list
    assert len(history) == 2  # noqa: PLR2004 - both assessments  # pyright: ignore[reportArgumentType] - a JSON list
    assert history[0]["as_of"] > history[1]["as_of"]  # pyright: ignore[reportIndexIssue, reportOptionalSubscript] - a JSON list


async def test_a_location_name_matches_ignoring_case_when_unique(toolbox: Toolbox) -> None:
    [result] = toolbox.run([("get_evidence", {"location": MIAMI.upper()})])

    assert not result.is_error
    assert _document(result)["location"] == MIAMI


# Bounded -----------------------------------------------------------------------------------


def test_a_result_past_its_limit_is_cut_and_marked() -> None:
    document = {"items": ["x" * 100] * 200}

    content, kept = bounded(document)

    assert len(content) == RESULT_LIMIT
    assert content.endswith(RESULT_CUT)
    assert kept == ()


def test_a_noaa_text_that_does_not_fit_is_cut_inside_its_block_and_marked() -> None:
    text = NoaaText(key="S1", code="TCP", text="word " * 3_000)

    content, [kept] = bounded({"public_advisory": "S1"}, [text])

    assert len(content) <= RESULT_LIMIT
    assert content.endswith(f"</noaa_product>{RESULT_CUT}")
    assert kept.text.endswith(CUT_MARK)


async def test_every_result_is_bounded(toolbox: Toolbox, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("weatherbot.services.ai.tools.RESULT_LIMIT", 1_500)

    results = toolbox.run(EVERY_CALL)

    assert max(len(result.content) for result in results) <= 1_500  # noqa: PLR2004 - the patched limit
    assert results[5].content.endswith(RESULT_CUT)


# Refused -----------------------------------------------------------------------------------


def _no_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> None:
        message = "a refused call read data"
        raise AssertionError(message)

    monkeypatch.setattr(SnapshotRepository, "load", refuse)
    monkeypatch.setattr(AssessmentRepository, "latest", refuse)
    monkeypatch.setattr(AssessmentRepository, "history", refuse)


@pytest.mark.parametrize(
    ("name", "arguments", "error", "allowed"),
    [
        ("fetch_url", {"url": "https://example.invalid/collect"}, "unknown_tool", list(TOOL_NAMES)),
        ("get_assessment", {"location": "Nowhere"}, "unknown_location", [MIAMI, NASSAU]),
        ("get_assessment", {"location": 7}, "bad_arguments", {"location": [MIAMI, NASSAU]}),
        (
            "get_alerts",
            {"location": MIAMI, "extra": 1},
            "bad_arguments",
            {"location": [MIAMI, NASSAU]},
        ),
        ("get_evidence", "not an object", "bad_arguments", {"location": [MIAMI, NASSAU]}),
        (
            "get_history",
            {"location": MIAMI, "limit": 11},
            "bad_arguments",
            {"location": [MIAMI, NASSAU], "limit": "an integer from 1 to 10"},
        ),
        ("get_history", {"location": MIAMI, "limit": True}, "bad_arguments", None),
        ("get_outlook", {"basin": "wpac"}, "bad_arguments", {"basin": ["atl", "pac", "cpac"]}),
        ("list_locations", {"location": MIAMI}, "bad_arguments", {}),
    ],
)
async def test_bad_input_is_an_error_listing_the_allowed_values_and_reads_nothing(  # noqa: PLR0913 - the case's fields
    toolbox: Toolbox,
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str,
    arguments: object,
    error: str,
    allowed: object,
) -> None:
    _no_reads(monkeypatch)

    [result] = toolbox.run([(name, arguments)])

    assert result.is_error
    assert result.noaa == ()
    document = json.loads(result.content)
    assert document["error"] == error
    if allowed is not None:
        assert document["allowed"] == allowed
    assert "example.invalid" not in result.content


async def test_an_unknown_storm_is_an_error_listing_the_active_storms(toolbox: Toolbox) -> None:
    [unknown, malformed] = toolbox.run(
        [("get_storm", {"atcf_id": "AL992026"}), ("get_storm", {"atcf_id": "simon"})]
    )

    for result in (unknown, malformed):
        assert result.is_error
    assert json.loads(unknown.content)["allowed"] == ["EP202026", "AL052019"]
    assert json.loads(malformed.content)["allowed"] == {"atcf_id": ["EP202026", "AL052019"]}


# Read-only ---------------------------------------------------------------------------------


def _row_counts(database: Database) -> dict[str, int]:
    with database.engine.connect() as connection:
        tables = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
        ).scalars()
        return {
            table: connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()  # noqa: S608 - names from sqlite_master
            for table in list(tables)
        }


async def test_every_tool_reads_through_the_ai_engine_whose_writes_are_refused(
    database: Database,
) -> None:
    await store_case_data(database)
    service, _ = replayed_service(database, [])
    toolbox = Toolbox(service.engine, now=service.clock)
    before = _row_counts(database)

    toolbox.run(EVERY_CALL)

    assert toolbox.engine is service.engine
    assert _row_counts(database) == before
    with pytest.raises(exc.DatabaseError) as refused, toolbox.engine.begin() as connection:
        connection.execute(text("DELETE FROM assessments"))
    assert isinstance(refused.value.orig, sqlite3.DatabaseError)
    assert _row_counts(database) == before
    await service.close()
