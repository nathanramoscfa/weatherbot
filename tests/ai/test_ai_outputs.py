# tests/ai/test_ai_outputs.py
"""``OutputRepository``: products stored as they ended, on the AI engine, read newest first."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from ai_support import stored_recorded

from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.outputs import NewOutput, OutputRepository
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import LocationRepository

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 1, 15, tzinfo=UTC)
LOCATION = "Miami-Dade County Hall"


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


def _briefing(assessment_id: int, **changes: object) -> NewOutput:
    fields: dict[str, object] = {
        "kind": "briefing",
        "model": "claude-sonnet-5-5",
        "prompt_version": "0" * 64,
        "status": "ok",
        "content": {"briefing": {}, "sources": []},
        "location_name": LOCATION,
        "assessment_id": assessment_id,
    }
    return NewOutput(**(fields | changes))  # pyright: ignore[reportArgumentType] - the fields above


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "ok", "content": None},
        {"status": "withheld", "withheld_reason": "level"},
        {"status": "withheld", "content": None},
    ],
)
def test_the_status_content_and_reason_agree(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="an ok product has content"):
        _briefing(1, **changes)


async def test_products_are_stored_and_found_newest_first(database: Database) -> None:
    _, stored = await stored_recorded(database)
    engine = ai_engine(database.path)
    clock = iter(NOW + timedelta(minutes=minute) for minute in range(10))
    outputs = OutputRepository(engine, now=lambda: next(clock))
    first = outputs.add(_briefing(stored.id))
    withheld = outputs.add(
        _briefing(stored.id, status="withheld", content=None, withheld_reason="x" * 40)
    )

    assert outputs.get(first.id) == first
    assert outputs.get(999) is None
    assert outputs.latest_briefing(LOCATION) == withheld
    assert withheld.withheld_reason == "x" * 32
    assert outputs.briefing_for(stored.id, "claude-sonnet-5-5", "0" * 64) == first
    assert outputs.briefing_for(stored.id, "claude-opus-5-5", "0" * 64) is None
    assert outputs.latest_briefing("Elsewhere") is None
    with pytest.raises(ValueError, match="at least one"):
        outputs.summaries(LOCATION, 0)
    engine.dispose()


async def test_removing_the_location_removes_its_products(database: Database) -> None:
    _, stored = await stored_recorded(database)
    engine = ai_engine(database.path)
    outputs = OutputRepository(engine, now=lambda: NOW)
    added = outputs.add(_briefing(stored.id))

    LocationRepository(database.engine).remove(LOCATION)

    assert outputs.get(added.id) is None
    engine.dispose()
