# tests/sources/test_nominatim_search.py
"""Tests of the Nominatim forward-search client, without network (respx)."""

import logging

import httpx
import pytest
import respx
from source_support import Quiet, entry, recorded, recorded_result

from weatherbot.models import Provenance
from weatherbot.sources import nominatim
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.http import open_client

pytestmark = pytest.mark.anyio

HOST = "nominatim.openstreetmap.org"
JSON = {"content-type": "application/json; charset=utf-8"}


def _search_body(name: str) -> bytes:
    directory = recorded("geocode-nominatim")
    return directory.payload(entry(directory, name))


def _provenance() -> Provenance:
    directory = recorded("geocode-nominatim")
    return recorded_result(directory, entry(directory, "search-nassau.json")).provenance()


def test_search_url_percent_encodes_query_and_sets_parameters() -> None:
    url = nominatim.search_url("Nassau, Bahamas")
    assert url == (
        f"https://{HOST}/search?q=Nassau%2C%20Bahamas&format=jsonv2&addressdetails=1&limit=5"
    )


def test_parse_search_returns_candidates_with_repr_false_on_place_and_point_fields() -> None:
    candidates = nominatim.parse_search(_search_body("search-nassau.json"), _provenance())
    assert len(candidates) >= 1
    first = candidates[0]
    assert first.country_code == "bs"
    assert first.osm_type in ("node", "way", "relation")
    assert first.osm_id >= 1
    assert first.licence.startswith("Data © OpenStreetMap contributors")

    rendered = repr(first)
    assert first.display_name not in rendered
    assert first.name is not None
    assert first.name not in rendered
    assert f"{first.latitude:.3f}" not in rendered
    assert f"{first.longitude:.3f}" not in rendered


def test_parse_search_returns_empty_tuple_on_empty_array_and_rejects_bad_shapes() -> None:
    assert nominatim.parse_search(_search_body("search-none.json"), _provenance()) == ()
    assert nominatim.parse_search(b"[]", _provenance()) == ()

    with pytest.raises(SourceSchemaError, match="is not a JSON array"):
        nominatim.parse_search(b'{"error": "bad"}', _provenance())

    with pytest.raises(SourceSchemaError, match="is not a JSON object"):
        nominatim.parse_search(b"[1]", _provenance())


async def test_search_fetches_candidates_and_redacts_query_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    place_query = "Secret Place Name 99"
    caplog.set_level(logging.INFO, logger="weatherbot.sources")
    with respx.mock(assert_all_called=True) as router:
        router.get(nominatim.search_url(place_query)).mock(
            return_value=httpx.Response(
                200, content=_search_body("search-miami.json"), headers=JSON
            )
        )
        async with open_client() as client:
            result = await nominatim.search(Quiet().fetcher(client), place_query)

    assert len(result.records) >= 1
    assert result.records[0].country_code == "us"
    for record in caplog.records:
        assert place_query not in record.getMessage()
        assert "Secret%20Place" not in record.getMessage()
