# tests/sources/test_nominatim.py
"""Tests of the Nominatim reverse-geocoding client, without network (respx).

Coordinates come from the landmarks through ``load_landmarks()``, or from
``synthetic_coordinates()`` in the privacy test, never from a literal.
"""

import logging
from pathlib import Path

import httpx
import pytest
import respx
from source_support import Quiet, entry, recorded

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.sources import nominatim
from weatherbot.sources.errors import SourceHttpError
from weatherbot.sources.http import HOST_INTERVALS, open_client
from weatherbot.sources.nws import format_point

pytestmark = pytest.mark.anyio

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOST = "nominatim.openstreetmap.org"
JSON = {"content-type": "application/json; charset=utf-8"}


def point_of(key: str) -> tuple[float, float]:
    found = next(item for item in load_landmarks() if item.key == key)
    return float(found.lat), float(found.lon)


def recorded_body(key: str) -> bytes:
    directory = recorded("geocode-nominatim")
    return directory.payload(entry(directory, f"reverse-{key}.json"))


def test_the_url_writes_the_point_with_format_point() -> None:
    lat, lon = point_of("nassau")
    lat_text, lon_text = format_point(lat, lon).split(",")

    assert nominatim.reverse_url(lat, lon) == (
        f"https://{HOST}/reverse?format=jsonv2&lat={lat_text}&lon={lon_text}"
    )


async def test_a_reverse_lookup_returns_the_place_and_its_licence() -> None:
    lat, lon = point_of("nassau")
    with respx.mock(assert_all_called=True) as router:
        router.get(nominatim.reverse_url(lat, lon)).mock(
            return_value=httpx.Response(200, content=recorded_body("nassau"), headers=JSON)
        )
        async with open_client() as client:
            result = await nominatim.reverse_geocode(Quiet().fetcher(client), lat, lon)
    place = result.records
    assert place is not None
    assert (place.name, place.country_code, place.country) == (
        "Parliament Square",
        "bs",
        "The Bahamas",
    )
    assert place.licence.startswith("Data © OpenStreetMap contributors, ODbL 1.0")
    assert place.provenance.source_id == "geocode-nominatim"


async def test_an_answer_with_no_place_returns_none() -> None:
    lat, lon = point_of("miami-dade")
    with respx.mock as router:
        router.get(nominatim.reverse_url(lat, lon)).mock(
            return_value=httpx.Response(200, json={"error": "Unable to geocode"}, headers=JSON)
        )
        async with open_client() as client:
            result = await nominatim.reverse_geocode(Quiet().fetcher(client), lat, lon)
    assert result.records is None
    assert len(result.responses) == 1


async def test_requests_are_paced_one_and_a_half_seconds_apart() -> None:
    quiet = Quiet()
    with respx.mock as router:
        for key in ("miami-dade", "nassau"):
            router.get(nominatim.reverse_url(*point_of(key))).mock(
                return_value=httpx.Response(200, content=recorded_body(key), headers=JSON)
            )
        async with open_client() as client:
            fetcher = quiet.fetcher(client)
            for key in ("miami-dade", "nassau"):
                await nominatim.reverse_geocode(fetcher, *point_of(key))
    assert HOST_INTERVALS[HOST] == pytest.approx(1.5)
    assert quiet.clock.sleeps == pytest.approx([1.5])


def test_only_the_nominatim_client_names_the_host() -> None:
    naming = sorted(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in (REPOSITORY_ROOT / "src").rglob("*.py")
        if HOST in path.read_text(encoding="utf-8")
    )
    # http.py names the host only in its pacing table.
    assert naming == ["src/weatherbot/sources/http.py", "src/weatherbot/sources/nominatim.py"]
    http_source = (REPOSITORY_ROOT / "src/weatherbot/sources/http.py").read_text(encoding="utf-8")
    assert http_source.count(HOST) == 1
    assert "def reverse_geocode" in (
        REPOSITORY_ROOT / "src/weatherbot/sources/nominatim.py"
    ).read_text(encoding="utf-8")


async def test_no_record_error_or_repr_carries_a_coordinate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    lat_text, lon_text = synthetic_coordinates(load_landmarks(), ())
    lat, lon = float(lat_text), float(lon_text)
    caplog.set_level(logging.DEBUG, logger="weatherbot.sources")
    with respx.mock as router:
        router.get(nominatim.reverse_url(lat, lon)).mock(
            side_effect=[
                httpx.Response(200, content=recorded_body("miami-dade"), headers=JSON),
                httpx.Response(418),
            ]
        )
        async with open_client() as client:
            fetcher = Quiet().fetcher(client)
            result = await nominatim.reverse_geocode(fetcher, lat, lon)
            with pytest.raises(SourceHttpError) as raised:
                await nominatim.reverse_geocode(fetcher, lat, lon)
    shown = [repr(result), repr(result.records), str(raised.value), repr(raised.value)]
    shown += [r.getMessage() for r in caplog.records if r.levelno > logging.DEBUG]
    for text in shown:
        assert lat_text not in text
        assert lon_text not in text
