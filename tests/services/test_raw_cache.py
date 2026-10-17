# tests/services/test_raw_cache.py
"""The raw-response cache: deduplicated bodies, durable validators, and a quiet URL.

The 304 test runs the outlook-graphics client twice, with the database closed and
reopened between the runs, as two separate runs of the application would.
"""

import dataclasses
import hashlib
import logging
from datetime import timedelta

import httpx
import pytest
import respx
from source_support import NOW, Quiet, entry, recorded, recorded_result
from sqlalchemy import select
from sqlalchemy.orm import Session

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.models import OutlookGraphic
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.raw_cache import (
    CorruptBodyError,
    RawResponseCache,
    read_body,
)
from weatherbot.services.persistence.tables import RawResponseRow, ResponseBodyRow
from weatherbot.sources import nhc_outlook_graphics as graphics
from weatherbot.sources import nws
from weatherbot.sources.http import HTTP_NOT_MODIFIED, FetchResult, SourceResult, StoredResponse

pytestmark = pytest.mark.anyio


def _rows(database: Database) -> tuple[list[RawResponseRow], list[ResponseBodyRow]]:
    with Session(database.engine) as session:
        raw = list(session.scalars(select(RawResponseRow).order_by(RawResponseRow.id)))
        bodies = list(session.scalars(select(ResponseBodyRow)))
        session.expunge_all()
        return raw, bodies


def _result(body: bytes, **update: object) -> FetchResult:
    result = FetchResult(
        source_id="nhc-outlook-graphics",
        url="https://www.nhc.noaa.gov/xgtwo/two_atl_2d0.png",
        status=200,
        body=body,
        headers={"content-type": "image/png", "etag": '"one"'},
        fetched_at=NOW,
        sha256=hashlib.sha256(body).hexdigest(),
    )
    return dataclasses.replace(result, **update)  # pyright: ignore[reportArgumentType] - test fields


async def test_a_304_is_served_from_the_persistent_store_across_two_runs() -> None:
    directory = recorded("nhc-outlook-graphics")
    live = recorded_result(directory, entry(directory, "two_atl_7d0.png"))
    etag = live.headers["etag"]
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(HTTP_NOT_MODIFIED, headers={"etag": etag})
        return httpx.Response(
            200, content=live.body, headers={"content-type": "image/png", "etag": etag}
        )

    async def run() -> SourceResult[tuple[OutlookGraphic, ...]]:
        with open_database(AppPaths.resolve()) as database:
            cache = RawResponseCache(database.engine)
            with respx.mock(assert_all_called=False) as router:
                router.route(host="www.nhc.noaa.gov").mock(side_effect=answer)
                async with httpx.AsyncClient() as client:
                    fetcher = dataclasses.replace(Quiet().fetcher(client), validators=cache)
                    result = await graphics.fetch_outlook_graphics(fetcher)
            for response in result.responses:
                cache.save_fetch(response, response.source_id, httpx.URL(response.url).path)
        return result

    first = await run()
    second = await run()

    count = len(first.responses)
    assert all(not r.not_modified for r in first.responses)
    assert all(request.headers.get("if-none-match") is None for request in sent[:count])
    assert all(request.headers.get("if-none-match") == etag for request in sent[count:])
    assert all(r.not_modified and r.status == HTTP_NOT_MODIFIED for r in second.responses)
    assert [r.body for r in second.responses] == [r.body for r in first.responses]
    assert [g.width_px for g in second.records] == [g.width_px for g in first.records]
    with open_database(AppPaths.resolve()) as database:
        raw, bodies = _rows(database)
    assert len(raw) == count
    assert len(bodies) == len({r.sha256 for r in first.responses})
    assert all(row.status == 200 and row.etag == etag for row in raw)  # noqa: PLR2004 - HTTP 200


def test_a_body_is_stored_once_and_compressed() -> None:
    body = b"{" + b'"same": "body", ' * 400 + b"}"
    with open_database(AppPaths.resolve()) as database:
        cache = RawResponseCache(database.engine)
        first = cache.save_fetch(_result(body), "nhc-outlook-graphics", "atl-2d0")
        second = cache.save_fetch(
            _result(body, source_id="nhc-gis-rss"), "nhc-gis-rss", "another-product"
        )
        third = cache.save_fetch(
            _result(body), "nhc-outlook-graphics", "atl-2d0", NOW - timedelta(hours=6)
        )
        raw, bodies = _rows(database)

    assert len({first, second, third}) == len(raw) == 3  # noqa: PLR2004 - three products
    (stored,) = bodies
    assert stored.size == len(body)
    assert len(stored.body) < len(body)
    assert read_body(stored) == body


def test_the_same_answer_again_refreshes_its_row() -> None:
    later = NOW + timedelta(hours=1)
    with open_database(AppPaths.resolve()) as database:
        cache = RawResponseCache(database.engine)
        first = cache.save_fetch(_result(b"body"), "nhc-outlook-graphics", "atl-2d0")
        again = cache.save_fetch(
            _result(b"body", fetched_at=later, headers={"etag": '"two"'}),
            "nhc-outlook-graphics",
            "atl-2d0",
        )
        (row,), _ = _rows(database)

    assert first == again
    assert row.fetched_at == later
    assert row.etag == '"two"'
    assert row.headers == {"content-type": "image/png", "etag": '"two"'}


def test_only_allowlisted_response_headers_are_stored() -> None:
    headers = {
        "content-type": "application/json",
        "etag": '"one"',
        "set-cookie": "session=abc",
        "user-agent": "weatherbot",
        "authorization": "Bearer token",
        "x-request-id": "123",
    }
    with open_database(AppPaths.resolve()) as database:
        RawResponseCache(database.engine).save_fetch(
            _result(b"body", headers=headers), "nhc-outlook-graphics", "atl-2d0"
        )
        (row,), _ = _rows(database)

    assert row.headers == {"content-type": "application/json", "etag": '"one"'}


def test_validators_load_from_the_database_and_this_runs_answers_first() -> None:
    url = _result(b"").url
    with open_database(AppPaths.resolve()) as database:
        RawResponseCache(database.engine).save_fetch(
            _result(b"old"), "nhc-outlook-graphics", "atl-2d0"
        )
        cache = RawResponseCache(database.engine)
        stored = cache.load(url)
        assert stored is not None
        assert (stored.etag, stored.body) == ('"one"', b"old")
        newer = StoredResponse(
            etag='"two"', last_modified=None, body=b"new", sha256="0" * 64, headers={}
        )
        cache.save(url, newer)

        assert cache.load(url) == newer
        assert RawResponseCache(database.engine).load(url) == stored
        assert cache.load("https://www.nhc.noaa.gov/other.png") is None


def test_an_answer_without_validators_is_not_a_validator() -> None:
    with open_database(AppPaths.resolve()) as database:
        cache = RawResponseCache(database.engine)
        cache.save_fetch(
            _result(b"body", headers={"content-type": "image/png"}), "nhc-outlook-graphics", "a"
        )

        assert cache.load(_result(b"").url) is None


def test_save_fetch_refuses_another_sources_id() -> None:
    with open_database(AppPaths.resolve()) as database:
        cache = RawResponseCache(database.engine)
        with pytest.raises(ValueError, match="its own source id"):
            cache.save_fetch(_result(b"body"), "nhc-gis-rss", "atl-2d0")


def test_a_corrupt_body_is_refused() -> None:
    with open_database(AppPaths.resolve()) as database:
        RawResponseCache(database.engine).save_fetch(
            _result(b"body"), "nhc-outlook-graphics", "atl-2d0"
        )
        _, (body,) = _rows(database)

    body.size += 1
    with pytest.raises(CorruptBodyError, match="corrupt"):
        read_body(body)


def test_a_url_with_coordinates_stays_out_of_every_record_above_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    lat_text, lon_text = synthetic_coordinates(load_landmarks(), ())
    url = nws.points_url(float(lat_text), float(lon_text))
    shown = url.split("/points/")[1]
    result = _result(b"{}", source_id="nws-points", url=url, headers={"etag": '"p"'})
    caplog.set_level(logging.DEBUG)

    with open_database(AppPaths.resolve()) as database:
        cache = RawResponseCache(database.engine)
        cache.save_fetch(result, "nws-points", "point")
        stored = cache.load(url)

    assert stored is not None
    loud = [r.getMessage() for r in caplog.records if r.levelno > logging.DEBUG]
    assert all(shown not in message for message in loud)
    assert all(lat_text not in message for message in loud)
