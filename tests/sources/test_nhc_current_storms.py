# tests/sources/test_nhc_current_storms.py
"""Tests of the roster client over the recorded ``CurrentStorms.json`` and edited copies."""

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx
from fixture_support import as_list, as_object
from source_support import NOW, Quiet, entry, recorded, recorded_roster_document

from weatherbot.models import AdvisoryNumber, Provenance
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.nhc_current_storms import (
    ROSTER_URL,
    fetch_current_storms,
    parse_current_storms,
)

MOVEMENT_MPH = 3.0
PROVENANCE = Provenance(
    source_id="nhc-current-storms",
    url=ROSTER_URL,
    status=200,
    fetched_at=NOW,
    sha256="0" * 64,
)


def _parse(document: object) -> object:
    return parse_current_storms(json.dumps(document).encode(), PROVENANCE)


def test_the_recorded_roster_parses_into_storm_summaries() -> None:
    (storm,) = parse_current_storms(json.dumps(recorded_roster_document()).encode(), PROVENANCE)
    assert storm.atcf_id == "EP202026"
    assert storm.slot == "EP5"
    assert storm.classification.raw == "HU"
    assert (storm.intensity_kt, storm.pressure_mb) == (85, 969)
    assert storm.movement_speed_mph == MOVEMENT_MPH
    assert storm.public_advisory.advisory == AdvisoryNumber.parse("22A")
    assert storm.track_cone is not None
    assert storm.track_cone.advisory == AdvisoryNumber.parse("22A")
    assert storm.track_cone.issued_at == datetime(2026, 10, 13, tzinfo=UTC)
    assert storm.earliest_arrival_kmz is not None
    assert storm.earliest_arrival_kmz.advisory == AdvisoryNumber.parse("22")
    assert storm.earliest_arrival_kmz.issued_at == datetime(2026, 10, 12, 21, tzinfo=UTC)
    assert str(storm.earliest_arrival_kmz.url).endswith("_earliest_reasonable_toa_34.kmz")
    assert storm.most_likely_arrival_kmz is not None
    assert str(storm.most_likely_arrival_kmz.url).endswith("_most_likely_toa_34.kmz")
    assert storm.wind_speed_probabilities_issued_at == datetime(2026, 10, 12, 18, tzinfo=UTC)
    assert not storm.has_storm_surge_watch_warning
    assert not storm.has_potential_storm_surge_flooding
    assert not storm.has_peak_surge


def test_an_off_season_roster_has_no_storms() -> None:
    assert _parse({"activeStorms": []}) == ()


def test_absent_or_null_product_objects_leave_their_products_unlisted() -> None:
    document = recorded_roster_document()
    storm = as_object(as_list(document["activeStorms"])[0])
    del storm["trackCone"]
    storm["windSpeedProbabilitiesGIS"] = None
    (summary,) = parse_current_storms(json.dumps(document).encode(), PROVENANCE)
    assert summary.track_cone is None
    assert summary.wind_speed_probabilities_issued_at is None


@pytest.mark.parametrize(
    "document",
    [{"storms": []}, {"activeStorms": {}}, {"activeStorms": [1]}, []],
    ids=["no-active-storms", "not-a-list", "not-an-object", "not-an-object-at-all"],
)
def test_a_roster_of_the_wrong_shape_breaks_the_schema(document: object) -> None:
    with pytest.raises(SourceSchemaError):
        _parse(document)


@pytest.mark.parametrize(
    ("product", "member", "value"),
    [
        ("trackCone", "advNum", "twenty-two"),
        ("trackCone", "issuance", "Monday"),
        ("earliestArrivalTimeTSWindsGIS", "kmzFile", "http://insecure.example/a.kmz"),
    ],
)
def test_a_malformed_product_member_breaks_the_schema(
    product: str, member: str, value: str
) -> None:
    document = recorded_roster_document()
    storm = as_object(as_list(document["activeStorms"])[0])
    as_object(storm[product])[member] = value
    with pytest.raises(SourceSchemaError, match=product):
        _parse(document)


def test_a_roster_that_is_not_json_breaks_the_schema() -> None:
    with pytest.raises(SourceSchemaError, match="not valid JSON"):
        parse_current_storms(b"<html>", PROVENANCE)


def test_a_slot_outside_the_storms_basin_breaks_the_model() -> None:
    document = recorded_roster_document()
    as_object(as_list(document["activeStorms"])[0])["binNumber"] = "AT1"
    with pytest.raises(SourceSchemaError, match="slot"):
        _parse(document)


@pytest.mark.anyio
async def test_fetch_reuses_the_roster_on_a_304() -> None:
    directory = recorded("nhc-current-storms")
    item = entry(directory, "CurrentStorms.json")
    headers = {
        str(k): str(v) for k, v in as_object(item["headers"]).items() if k != "content-length"
    }

    def answer(request: httpx.Request) -> httpx.Response:
        if request.headers.get("if-none-match") == headers["etag"]:
            return httpx.Response(304, headers={"etag": headers["etag"]})
        return httpx.Response(200, content=directory.payload(item), headers=headers)

    with respx.mock as router:
        router.get(ROSTER_URL).mock(side_effect=answer)
        async with httpx.AsyncClient() as client:
            fetcher = Quiet().fetcher(client)
            first = await fetch_current_storms(fetcher)
            second = await fetch_current_storms(fetcher)
    assert first.records == second.records
    assert [storm.atcf_id for storm in second.records] == ["EP202026"]
    assert second.responses[0].not_modified
