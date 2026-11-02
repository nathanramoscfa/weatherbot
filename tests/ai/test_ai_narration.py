# tests/ai/test_ai_narration.py
"""``NarrationService``: off by default, the stored PNG and its TWO sent, checked, stored, reused.

The database holds the Miami-Dade landmark and the recorded snapshot with every recorded
answer, the outlook graphics' PNG bodies among them. The recorded narrations
(``tests/fixtures/ai/narration-*.sse``) replay through the real SDK; the failures are
hand-written streams.
"""

import base64
import hashlib
import json
from collections.abc import Iterator, Sequence
from typing import Any, cast

import pytest
from ai_support import (
    FIXTURES,
    RecordedAnswer,
    chunked_stream,
    ledger_rows,
    load_answer,
    output_rows,
    replayed_service,
    shared_recorded_snapshot,
    stored_recorded,
)
from sqlalchemy import update

from weatherbot.models import Snapshot
from weatherbot.services.ai.caller import estimate_prompt_tokens, image_tokens, request_kwargs
from weatherbot.services.ai.narration import (
    NARRATION_EFFORT,
    NARRATION_LABEL,
    NARRATION_MAX_TOKENS,
    Done,
    NarrationEvent,
    NarrationService,
    Started,
    Unavailable,
    Withheld,
    stored_narration,
    two_sha256,
)
from weatherbot.services.ai.prompts import narration_prompt_version, narration_system_blocks
from weatherbot.services.ai.schemas import OutlookNarration
from weatherbot.services.ai.service import AiService
from weatherbot.services.config import AiSettings, AppPaths
from weatherbot.services.persistence.database import Database, open_database, writing_session
from weatherbot.services.persistence.repositories import SnapshotRepository
from weatherbot.services.persistence.tables import ResponseBodyRow

pytestmark = pytest.mark.anyio

ON = AiSettings(outlook_narration=True)
VALID: dict[str, Any] = {
    "summary": "The outlook marks one area in the eastern tropical Atlantic, with a low chance.",
    "areas": [
        {"description": "An area of low pressure west of the islands.", "chance_text": "20%"}
    ],
    "caveat": "This is an AI description of the official graphic, which governs.",
}


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


def _stream(**changes: object) -> RecordedAnswer:
    return RecordedAnswer.events(chunked_stream(json.dumps(VALID | changes), thinking=False))


async def _events(
    service: AiService, basin: str = "atl", horizon: str = "7d0", *, new: bool = False
) -> list[NarrationEvent]:
    narrations = NarrationService(service)
    return [event async for event in narrations.stream(basin, horizon, new=new)]  # pyright: ignore[reportArgumentType] - a basin and a horizon


def _graphic(snapshot: Snapshot, basin: str, horizon: str) -> str:
    return next(
        item.provenance.sha256
        for item in snapshot.outlook_graphics
        if item.basin == basin and item.horizon == horizon
    )


def _manifest(case: str) -> dict[str, Any]:
    entries: Sequence[dict[str, Any]] = json.loads(
        (FIXTURES / "manifest.json").read_text(encoding="utf-8")
    )
    return next(entry for entry in entries if entry["case"] == case)


# Off by default ----------------------------------------------------------------------------


async def test_narration_is_off_by_default_and_sends_nothing(database: Database) -> None:
    await stored_recorded(database)
    service, replay = replayed_service(database, [load_answer("narration-atl-7d0")])

    assert AiSettings().outlook_narration is False
    assert await _events(service) == [Unavailable("disabled")]
    assert replay.requests == []
    await service.close()


async def test_ai_turned_off_is_unavailable_even_with_narration_on(database: Database) -> None:
    await stored_recorded(database)
    settings = AiSettings(enabled=False, outlook_narration=True)
    service, replay = replayed_service(database, [], settings=settings)

    assert await _events(service) == [Unavailable("disabled")]
    assert replay.requests == []
    await service.close()


# The request -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "basin", "horizon"),
    [("narration-atl-7d0", "atl", "7d0"), ("narration-pac-2d0", "pac", "2d0")],
)
async def test_the_stored_png_and_its_two_are_sent_as_recorded(
    database: Database, case: str, basin: str, horizon: str
) -> None:
    recorded, _ = await stored_recorded(database)
    service, replay = replayed_service(database, [load_answer(case)], settings=ON)

    events = await _events(service, basin, horizon)

    started, done = events
    assert isinstance(started, Started)
    assert started.graphic_sha256 == _graphic(recorded.snapshot, basin, horizon)
    assert started.prompt_version == narration_prompt_version()
    assert isinstance(done, Done)
    assert not done.reused
    request = replay.requests[0]
    assert hashlib.sha256(request.content).hexdigest() == _manifest(case)["request_sha256"]
    body = cast("dict[str, Any]", request.body)
    [user] = body["messages"]
    image, text = user["content"]
    assert image["type"] == "image"
    assert image["source"]["media_type"] == "image/png"
    png = base64.b64decode(image["source"]["data"])
    assert hashlib.sha256(png).hexdigest() == started.graphic_sha256
    assert '<noaa_product key="S1" code="TWO"' in text["text"]
    assert text["text"].endswith(" outlook over seven days." if horizon == "7d0" else " two days.")
    assert body["system"] == narration_system_blocks()
    assert body["max_tokens"] == NARRATION_MAX_TOKENS
    assert body["output_config"]["effort"] == NARRATION_EFFORT
    assert body["output_config"]["format"]["type"] == "json_schema"
    await service.close()


async def test_the_ceiling_counts_the_image_at_its_visual_tokens(database: Database) -> None:
    recorded, _ = await stored_recorded(database)
    service, replay = replayed_service(database, [load_answer("narration-atl-7d0")], settings=ON)

    await _events(service)

    body = cast("dict[str, Any]", dict(replay.requests[0].body))
    del body["model"]
    del body["stream"]
    graphic = next(item for item in recorded.snapshot.outlook_graphics if item.basin == "atl")
    tokens = estimate_prompt_tokens("claude-sonnet-5-5", body)
    data: str = body["messages"][0]["content"][0]["source"]["data"]
    assert image_tokens(graphic.width_px, graphic.height_px) == 825  # noqa: PLR2004 - 900 by 679
    assert tokens < len(data) / 2.5  # the image never counts at its base64 text
    assert request_kwargs(body)["max_tokens"] == NARRATION_MAX_TOKENS
    [row] = ledger_rows(database.engine)
    assert (row.kind, row.status) == ("narration", "ok")
    await service.close()


# Checked -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"areas": [{"description": "A low.", "chance_text": "35%"}]}, "chance"),
        ({"summary": "A low with a 40 percent chance of forming."}, "chance"),
        ({"summary": "Weatherbot's level is level 3 here."}, "level"),
        ({"summary": "See www.example.invalid/outlook for more."}, "url"),
        ({"summary": "A low near 12.3N 45.6W."}, "coordinate"),
        ({"caveat": " "}, "empty"),
    ],
)
async def test_a_narration_that_breaks_a_rule_is_withheld_and_stored_without_text(
    database: Database, changes: dict[str, object], reason: str
) -> None:
    await stored_recorded(database)
    service, _ = replayed_service(database, [_stream(**changes)], settings=ON)

    events = await _events(service)

    withheld = events[-1]
    assert isinstance(withheld, Withheld)
    assert withheld.reason == reason
    [row] = output_rows(database.engine)
    assert (row.kind, row.status, row.withheld_reason, row.content) == (
        "narration",
        "withheld",
        reason,
        None,
    )
    assert withheld.output_id == row.id
    await service.close()


async def test_text_that_misses_the_schema_is_withheld(database: Database) -> None:
    await stored_recorded(database)
    answer = RecordedAnswer.events(chunked_stream('{"summary": "Only this."}', thinking=False))
    service, _ = replayed_service(database, [answer], settings=ON)

    events = await _events(service)

    assert isinstance(events[-1], Withheld)
    assert events[-1].reason == "invalid_output"
    await service.close()


async def test_a_refusal_is_unavailable_and_stores_nothing(database: Database) -> None:
    await stored_recorded(database)
    refusal = RecordedAnswer.events(chunked_stream("", stop_reason="refusal", thinking=False))
    service, _ = replayed_service(database, [refusal], settings=ON)

    events = await _events(service)

    assert events[-1] == Unavailable("declined")
    assert output_rows(database.engine) == []
    await service.close()


# Stored and reused -------------------------------------------------------------------------


async def test_a_narration_is_stored_and_reused_per_graphic(database: Database) -> None:
    recorded, _ = await stored_recorded(database)
    service, replay = replayed_service(database, [_stream(), _stream()], settings=ON)

    first = await _events(service)
    again = await _events(service)

    done = first[-1]
    reused = again[-1]
    assert isinstance(done, Done)
    assert isinstance(reused, Done)
    assert (done.reused, reused.reused) == (False, True)
    assert reused.output_id == done.output_id
    assert reused.narration == OutlookNarration.model_validate(VALID)
    assert len(replay.requests) == 1
    [row] = output_rows(database.engine)
    assert row.graphic_sha256 == _graphic(recorded.snapshot, "atl", "7d0")
    assert row.content is not None
    two = next(item for item in recorded.snapshot.text_products if item.location == "AT")
    assert row.content["two_sha256"] == two_sha256(two)
    narration, source = stored_narration(NarrationService(service).output(row.id))  # pyright: ignore[reportArgumentType] - a stored row
    assert narration == done.narration
    assert source.code == "TWO"

    renewed = await _events(service, new=True)

    assert isinstance(renewed[-1], Done)
    assert not renewed[-1].reused
    assert len(replay.requests) == 2  # noqa: PLR2004 - the first and the new narration
    await service.close()


async def test_a_new_two_text_is_not_reused(database: Database) -> None:
    recorded, _ = await stored_recorded(database)
    service, replay = replayed_service(database, [_stream(), _stream()], settings=ON)
    await _events(service)
    snapshot = recorded.snapshot
    later = snapshot.model_copy(
        update={
            "snapshot_id": snapshot.snapshot_id.__class__(int=7),
            "completed_at": snapshot.completed_at.replace(hour=3),
            "text_products": tuple(
                product.model_copy(
                    update={
                        "product_id": f"{product.product_id}-later",
                        "text": f"{product.text}\nUpdated 20 percent.",
                    }
                )
                if product.code == "TWO"
                else product
                for product in snapshot.text_products
            ),
        }
    )
    SnapshotRepository(database.engine).save(later)

    events = await _events(service)

    assert isinstance(events[-1], Done)
    assert not events[-1].reused
    assert len(replay.requests) == 2  # noqa: PLR2004 - the graphic's TWO changed
    await service.close()


async def test_a_withheld_narration_is_not_reused(database: Database) -> None:
    await stored_recorded(database)
    bad = _stream(summary="A 99% chance.")
    service, replay = replayed_service(database, [bad, _stream()], settings=ON)
    await _events(service)

    events = await _events(service)

    assert isinstance(events[-1], Done)
    assert len(replay.requests) == 2  # noqa: PLR2004 - the withheld and the new narration
    await service.close()


# Unavailable -------------------------------------------------------------------------------


async def test_no_snapshot_means_no_graphic(database: Database) -> None:
    service, replay = replayed_service(database, [], settings=ON)

    assert await _events(service) == [Unavailable("no_graphic")]
    assert replay.requests == []
    await service.close()


async def test_a_missing_or_altered_png_body_means_no_graphic(database: Database) -> None:
    recorded, _ = await stored_recorded(database)
    sha = _graphic(recorded.snapshot, "atl", "7d0")
    with writing_session(database.engine) as session:
        session.execute(update(ResponseBodyRow).where(ResponseBodyRow.sha256 == sha).values(size=1))
    service, replay = replayed_service(database, [], settings=ON)

    assert await _events(service) == [Unavailable("no_graphic")]
    assert replay.requests == []
    await service.close()


async def test_a_basin_without_its_two_is_no_outlook(database: Database) -> None:
    recorded = await shared_recorded_snapshot()
    snapshot = recorded.snapshot.model_copy(
        update={
            "alerts": {},
            "text_products": tuple(
                product for product in recorded.snapshot.text_products if product.location != "AT"
            ),
        }
    )
    SnapshotRepository(database.engine).save(snapshot, recorded.responses)
    service, replay = replayed_service(database, [], settings=ON)

    assert await _events(service) == [Unavailable("no_outlook")]
    assert replay.requests == []
    await service.close()


def test_the_label_names_an_ai_interpretation_of_the_official_graphic() -> None:
    assert NARRATION_LABEL == "AI interpretation of the official graphic"
