# tests/sources/test_nws_no_county.py
"""Tests for marine-zone NWS ``/points``, ``/zones``, and ``fetch_alerts`` without a county.

Built in test code from the recorded Miami-Dade answers so no water coordinate is recorded.
"""

import json
from typing import Any, cast

import httpx
import pytest
import respx
from source_support import Quiet, entry, recorded, recorded_result

from check_personal_data import load_landmarks
from weatherbot.models import LatLon, Location, NwsCoverage
from weatherbot.sources import nws
from weatherbot.sources.http import open_client

pytestmark = pytest.mark.anyio

GEOJSON = {"content-type": "application/geo+json"}
EMPTY: dict[str, object] = {"type": "FeatureCollection", "features": []}
EXPECTED_ALERT_RESPONSES = 2


def _miami_point() -> tuple[float, float]:
    found = next(item for item in load_landmarks() if item.key == "miami-dade")
    return float(found.lat), float(found.lon)


def _marine_points_payload(*, cwa: str = "MFL", null_county: bool = False) -> bytes:
    directory = recorded("nws-points")
    doc = cast(
        "dict[str, Any]",
        json.loads(directory.payload(entry(directory, "points-miami-dade.json"))),
    )
    props = cast("dict[str, Any]", doc["properties"])
    if null_county:
        props["county"] = None
    else:
        props.pop("county", None)
    props.pop("fireWeatherZone", None)
    props["forecastZone"] = "https://api.weather.gov/zones/forecast/AMZ630"
    props["cwa"] = cwa
    return json.dumps(doc).encode("utf-8")


def _marine_zone_payload(*, omit_state: bool = False) -> bytes:
    directory = recorded("nws-zones")
    doc = cast(
        "dict[str, Any]",
        json.loads(directory.payload(entry(directory, "zone-forecast-FLZ173.json"))),
    )
    props = cast("dict[str, Any]", doc["properties"])
    props["id"] = "AMZ630"
    props["type"] = "coastal"
    if omit_state:
        props.pop("state", None)
    else:
        props["state"] = None
    return json.dumps(doc).encode("utf-8")


def test_parse_point_accepts_missing_or_null_county_and_alphanumeric_cwa() -> None:
    missing = nws.parse_point(_marine_points_payload(cwa="MFL"))
    assert missing.county_zone is None
    assert missing.forecast_zone == "AMZ630"
    assert missing.cwa == "MFL"

    open_water = nws.parse_point(_marine_points_payload(cwa="NH2", null_county=True))
    assert open_water.county_zone is None
    assert open_water.forecast_zone == "AMZ630"
    assert open_water.cwa == "NH2"


async def test_lookup_point_returns_coverage_without_county() -> None:
    lat, lon = _miami_point()
    with respx.mock(assert_all_called=True) as router:
        router.get(nws.points_url(lat, lon)).mock(
            return_value=httpx.Response(200, content=_marine_points_payload(), headers=GEOJSON)
        )
        async with open_client() as client:
            result = await nws.lookup_point(Quiet().fetcher(client), lat, lon)
    assert isinstance(result.records, NwsCoverage)
    assert result.records.county_zone is None
    assert result.records.forecast_zone == "AMZ630"


def test_parse_zone_accepts_coastal_zone_with_null_or_missing_state() -> None:
    directory = recorded("nws-zones")
    item = entry(directory, "zone-forecast-FLZ173.json")
    provenance = recorded_result(directory, item).provenance()

    null_state = nws.parse_zone(
        _marine_zone_payload(omit_state=False), provenance, zone_id="AMZ630"
    )
    assert null_state.id == "AMZ630"
    assert null_state.type == "coastal"
    assert null_state.state is None

    omitted_state = nws.parse_zone(
        _marine_zone_payload(omit_state=True), provenance, zone_id="AMZ630"
    )
    assert omitted_state.id == "AMZ630"
    assert omitted_state.state is None


async def test_fetch_alerts_queries_only_point_and_forecast_zone_when_county_is_none() -> None:
    lat, lon = _miami_point()
    coverage = nws.parse_point(_marine_points_payload())
    location = Location(name="Marine", point=LatLon(latitude=lat, longitude=lon), nws=coverage)

    with respx.mock(assert_all_called=True) as router:
        point_route = router.get(nws.point_alerts_url(lat, lon)).mock(
            return_value=httpx.Response(200, json=EMPTY, headers=GEOJSON)
        )
        forecast_route = router.get(nws.zone_alerts_url("AMZ630")).mock(
            return_value=httpx.Response(200, json=EMPTY, headers=GEOJSON)
        )
        async with open_client() as client:
            result = await nws.fetch_alerts(Quiet().fetcher(client), location)

    assert point_route.called
    assert forecast_route.called
    assert len(result.responses) == EXPECTED_ALERT_RESPONSES
    assert result.records == ()
