# tests/sources/test_nws.py
"""Tests of the NWS points, alerts, and zones clients, without network (respx).

Coordinates come from ``scripts/public_landmarks.toml`` through ``load_landmarks()``, or
from ``synthetic_coordinates()`` in the privacy tests, never from a literal. Rounding cases
are computed from a landmark at run time.
"""

import ast
import json
import logging
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import respx
from source_support import Quiet, entry, recorded, recorded_result

from check_personal_data import Landmark, load_landmarks, synthetic_coordinates
from weatherbot.models import LatLon, Location, NwsCoverage
from weatherbot.sources import nhc_text_products as text_products
from weatherbot.sources import nws
from weatherbot.sources.drift import DRIFT_ATTRIBUTE
from weatherbot.sources.errors import DocumentedProblem, SourceError, SourceHttpError
from weatherbot.sources.http import HOST_INTERVALS, open_client

pytestmark = pytest.mark.anyio

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_HOST = "api.weather.gov"
PROBLEM = {"content-type": "application/problem+json"}
GEOJSON = {"content-type": "application/geo+json"}
EMPTY: dict[str, object] = {"type": "FeatureCollection", "features": []}
ALERT_QUERIES = 3
"""The point, the county, and the forecast zone."""
RETRIED_ONCE = 2


def landmark(key: str) -> Landmark:
    return next(item for item in load_landmarks() if item.key == key)


def point_of(key: str) -> tuple[float, float]:
    found = landmark(key)
    return float(found.lat), float(found.lon)


def miami_coverage() -> NwsCoverage:
    directory = recorded("nws-points")
    return nws.parse_point(directory.payload(entry(directory, "points-miami-dade.json")))


def location_at(lat: float, lon: float, coverage: NwsCoverage | None) -> Location:
    return Location(name="Test", point=LatLon(latitude=lat, longitude=lon), nws=coverage)


def recorded_alert_feature() -> dict[str, Any]:
    """The Rip Current Statement recorded on 2026-10-17 (a real alert, as received)."""
    directory = recorded("nws-alerts-zone")
    document = json.loads(directory.payload(entry(directory, "alerts-zone-FLC086.geojson")))
    return document["features"][0]


def collection(*features: dict[str, object]) -> dict[str, object]:
    return {"type": "FeatureCollection", "features": list(features)}


def mock_alerts(
    router: respx.MockRouter,
    location: Location,
    *,
    point: dict[str, object],
    county: dict[str, object],
    forecast: dict[str, object],
) -> list[respx.Route]:
    coverage = location.nws
    assert coverage is not None
    lat, lon = location.point.latitude, location.point.longitude
    answers = [
        (nws.point_alerts_url(lat, lon), point),
        (nws.zone_alerts_url(coverage.county_zone), county),
        (nws.zone_alerts_url(coverage.forecast_zone), forecast),
    ]
    return [
        router.get(url).mock(return_value=httpx.Response(200, json=body, headers=GEOJSON))
        for url, body in answers
    ]


# format_point ------------------------------------------------------------------------------


def test_format_point_writes_four_decimals() -> None:
    found = landmark("miami-dade")
    lat, lon = float(found.lat), float(found.lon)

    assert nws.format_point(lat, lon) == f"{found.lat:.4f},{found.lon:.4f}"
    assert nws.points_url(lat, lon).endswith(f"/points/{found.lat:.4f},{found.lon:.4f}")


def _shifted(value: Decimal, offset: str) -> float:
    return float(value + Decimal(offset))


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        ("0.00004", "0"),
        ("-0.00004", "0"),
        ("0.00006", "0.0001"),
        ("-0.00006", "-0.0001"),
        ("0", "0"),
    ],
)
def test_format_point_rounds_half_to_even(offset: str, expected: str) -> None:
    found = landmark("miami-dade")

    written = nws.format_point(_shifted(found.lat, offset), _shifted(found.lon, offset))

    lat, lon = written.split(",")
    assert lat == f"{found.lat + Decimal(expected):.4f}"
    assert lon == f"{found.lon + Decimal(expected):.4f}"


@pytest.mark.parametrize("half", ["0.00005", "0.00015", "-0.00005"])
def test_format_point_rounds_a_half_to_the_even_neighbour(half: str) -> None:
    base = landmark("miami-dade").lat
    value = base + Decimal(half)
    lower = value.quantize(Decimal("0.0001"), rounding="ROUND_FLOOR")
    upper = lower + Decimal("0.0001")
    even = lower if int(lower.as_tuple().digits[-1]) % 2 == 0 else upper

    lat, _ = nws.format_point(float(value), 0.0).split(",")

    assert lat == f"{even:.4f}"


def test_format_point_writes_no_negative_zero() -> None:
    written = nws.format_point(-1e-5, -0.0)

    assert "-" not in written
    assert [Decimal(part) for part in written.split(",")] == [Decimal(0)] * 2
    assert all(part.endswith(".0000") for part in written.split(","))


@pytest.mark.parametrize(
    ("lat", "lon"),
    [(91.0, 0.0), (0.0, -181.0), (float("nan"), 0.0), (0.0, float("inf"))],
)
def test_format_point_refuses_a_value_out_of_range_without_repeating_it(
    lat: float, lon: float
) -> None:
    with pytest.raises(ValueError, match="not finite or is out of range") as raised:
        nws.format_point(lat, lon)
    assert "91" not in str(raised.value)
    assert "181" not in str(raised.value)


def _writes_a_coordinate(node: ast.JoinedStr) -> bool:
    """Whether an f-string interpolates a value into a coordinate slot of a URL."""
    text = "".join(str(part.value) for part in node.values if isinstance(part, ast.Constant))
    slots = ("/points/", "point=", "lat=", "lon=", "latitude=", "longitude=")
    return any(slot in text for slot in slots) and any(
        isinstance(part, ast.FormattedValue) for part in node.values
    )


def test_format_point_is_the_only_writer_of_a_coordinate_into_a_url() -> None:
    files = [*sorted((REPOSITORY_ROOT / "src" / "weatherbot").rglob("*.py"))]
    files.append(REPOSITORY_ROOT / "scripts" / "record_fixtures.py")
    writers = {
        f"{path.relative_to(REPOSITORY_ROOT).as_posix()}:{function.name}"
        for path in files
        for function in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.JoinedStr) and _writes_a_coordinate(node)
    }
    # The URL builders interpolate format_point's text; format_point writes the digits.
    assert sorted(writers) == [
        "src/weatherbot/sources/nominatim.py:reverse_url",
        "src/weatherbot/sources/nws.py:point_alerts_url",
        "src/weatherbot/sources/nws.py:points_url",
    ]
    nws_source = (REPOSITORY_ROOT / "src/weatherbot/sources/nws.py").read_text(encoding="utf-8")
    nominatim_source = (REPOSITORY_ROOT / "src/weatherbot/sources/nominatim.py").read_text(
        encoding="utf-8"
    )
    assert "{format_point(lat, lon)}" in nws_source
    assert "format_point(lat, lon).partition" in nominatim_source
    # No other code rounds a value to the API's four decimals.
    for path in files:
        assert ".4f}" not in path.read_text(encoding="utf-8"), path.name


# Points ------------------------------------------------------------------------------------


async def test_the_miami_dade_point_resolves_to_its_zones() -> None:
    lat, lon = point_of("miami-dade")
    with respx.mock(assert_all_called=True) as router:
        directory = recorded("nws-points")
        router.get(nws.points_url(lat, lon)).mock(
            return_value=httpx.Response(
                200,
                content=directory.payload(entry(directory, "points-miami-dade.json")),
                headers=GEOJSON,
            )
        )
        async with open_client() as client:
            result = await nws.lookup_point(Quiet().fetcher(client), lat, lon)
    assert result.records == miami_coverage()
    assert len(result.responses) == 1


async def test_another_documented_404_problem_is_an_http_error() -> None:
    lat, lon = point_of("miami-dade")
    problem = {"type": "https://api.weather.gov/problems/NotFound", "title": "Not Found"}
    with respx.mock as router:
        router.get(nws.points_url(lat, lon)).mock(
            return_value=httpx.Response(404, json=problem, headers=PROBLEM)
        )
        async with open_client() as client:
            with pytest.raises(SourceHttpError, match="NotFound"):
                await nws.lookup_point(Quiet().fetcher(client), lat, lon)


# Alerts ------------------------------------------------------------------------------------


async def test_an_alert_both_queries_return_is_kept_once_with_both_queries() -> None:
    feature = recorded_alert_feature()
    location = location_at(*point_of("miami-dade"), miami_coverage())
    with respx.mock(assert_all_called=True) as router:
        mock_alerts(
            router, location, point=collection(feature), county=collection(feature), forecast=EMPTY
        )
        async with open_client() as client:
            result = await nws.fetch_alerts(Quiet().fetcher(client), location)
    (alert,) = result.records
    assert [(q.kind, q.zone_id) for q in alert.found_by] == [("point", None), ("zone", "FLC086")]
    assert [q.provenance.source_id for q in alert.found_by] == [
        "nws-alerts-point",
        "nws-alerts-zone",
    ]
    assert len(result.responses) == ALERT_QUERIES


async def test_the_merge_keeps_the_order_of_first_appearance() -> None:
    first = recorded_alert_feature()
    second = json.loads(json.dumps(first))
    second["properties"]["id"] = f"{first['properties']['id']}.second"
    location = location_at(*point_of("miami-dade"), miami_coverage())
    with respx.mock as router:
        mock_alerts(
            router,
            location,
            point=EMPTY,
            county=collection(second, first),
            forecast=collection(first),
        )
        async with open_client() as client:
            result = await nws.fetch_alerts(Quiet().fetcher(client), location)
    assert [a.id.endswith(".second") for a in result.records] == [True, False]
    assert [q.zone_id for q in result.records[1].found_by] == ["FLC086", "FLZ173"]


async def test_copies_that_disagree_keep_the_first_and_are_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first = recorded_alert_feature()
    edited = json.loads(json.dumps(first))
    edited["properties"]["headline"] = "Edited"
    location = location_at(*point_of("miami-dade"), miami_coverage())
    with respx.mock as router:
        mock_alerts(
            router, location, point=collection(first), county=collection(edited), forecast=EMPTY
        )
        caplog.set_level(logging.WARNING, "weatherbot.sources")
        async with open_client() as client:
            result = await nws.fetch_alerts(Quiet().fetcher(client), location)
    (alert,) = result.records
    assert alert.headline != "Edited"
    assert [q.kind for q in alert.found_by] == ["point", "zone"]
    assert any(hasattr(record, DRIFT_ATTRIBUTE) for record in caplog.records)


async def test_nothing_is_filtered_by_zone() -> None:
    feature = recorded_alert_feature()
    outside = json.loads(json.dumps(feature))
    properties = outside["properties"]
    properties["id"] = f"{properties['id']}.outside"
    properties["affectedZones"] = ["https://api.weather.gov/zones/forecast/FLZ069"]
    properties["geocode"]["UGC"] = ["FLZ069"]
    location = location_at(*point_of("miami-dade"), miami_coverage())
    with respx.mock as router:
        mock_alerts(router, location, point=EMPTY, county=collection(outside), forecast=EMPTY)
        async with open_client() as client:
            result = await nws.fetch_alerts(Quiet().fetcher(client), location)
    (alert,) = result.records
    assert alert.affected_zone_ids == ("FLZ069",)


async def test_a_location_outside_nws_coverage_makes_no_alert_request() -> None:
    location = location_at(*point_of("nassau"), None)
    with respx.mock(assert_all_called=False) as router:
        catch_all = router.route().mock(return_value=httpx.Response(500))
        async with open_client() as client:
            result = await nws.fetch_alerts(Quiet().fetcher(client), location)
    assert result.records == ()
    assert result.responses == ()
    assert catch_all.call_count == 0


async def test_the_out_of_bounds_point_answer_is_a_documented_problem() -> None:
    # A location wrongly marked as covered: the point query's 400 is typed.
    location = location_at(*point_of("nassau"), miami_coverage())
    directory = recorded("nws-alerts-point")
    nassau = directory.payload(entry(directory, "alerts-point-nassau.json"))
    with respx.mock as router:
        router.get(nws.point_alerts_url(location.point.latitude, location.point.longitude)).mock(
            return_value=httpx.Response(400, content=nassau, headers=PROBLEM)
        )
        async with open_client() as client:
            with pytest.raises(DocumentedProblem) as raised:
                await nws.fetch_alerts(Quiet().fetcher(client), location)
    assert raised.value.status == nws.HTTP_BAD_REQUEST
    assert raised.value.problem_type == "https://api.weather.gov/problems/InvalidParameter"


async def test_a_429_with_retry_after_on_the_api_is_waited_for() -> None:
    lat, lon = point_of("miami-dade")
    directory = recorded("nws-points")
    body = directory.payload(entry(directory, "points-miami-dade.json"))
    quiet = Quiet()
    with respx.mock as router:
        route = router.get(nws.points_url(lat, lon)).mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "5"}),
                httpx.Response(200, content=body, headers=GEOJSON),
            ]
        )
        async with open_client() as client:
            result = await nws.lookup_point(quiet.fetcher(client), lat, lon)
    assert route.call_count == RETRIED_ONCE
    assert quiet.backoff.sleeps == [5.0]
    assert isinstance(result.records, NwsCoverage)


async def test_pacing_is_shared_with_the_text_product_client() -> None:
    lat, lon = point_of("miami-dade")
    directory = recorded("nws-points")
    body = directory.payload(entry(directory, "points-miami-dade.json"))
    quiet = Quiet()
    with respx.mock as router:
        router.get(nws.points_url(lat, lon)).mock(
            return_value=httpx.Response(200, content=body, headers=GEOJSON)
        )
        for basin in text_products.TWO_BASINS:
            router.get(text_products.list_url("TWO", basin)).mock(
                return_value=httpx.Response(200, json={"@graph": []})
            )
        async with open_client() as client:
            fetcher = quiet.fetcher(client)
            await nws.lookup_point(fetcher, lat, lon)
            await text_products.fetch_twos(fetcher)
            await nws.lookup_point(fetcher, lat, lon)
    # Five requests to one host through one fetcher: four waits of the API's interval.
    assert quiet.clock.sleeps == pytest.approx([HOST_INTERVALS[API_HOST]] * 4)


# Zones -------------------------------------------------------------------------------------


async def test_a_zone_request_is_conditional_once_its_validators_are_stored() -> None:
    directory = recorded("nws-zones")
    item = entry(directory, "zone-forecast-FLZ173.json")
    recorded_headers = cast("dict[str, str]", item["headers"])
    headers = {**GEOJSON, "last-modified": recorded_headers["last-modified"]}
    with respx.mock as router:
        route = router.get(nws.zone_url("forecast", "FLZ173")).mock(
            side_effect=[
                httpx.Response(200, content=directory.payload(item), headers=headers),
                httpx.Response(304, headers=headers),
            ]
        )
        async with open_client() as client:
            fetcher = Quiet().fetcher(client)
            first = await nws.fetch_zone(fetcher, "forecast", "FLZ173")
            second = await nws.fetch_zone(fetcher, "forecast", "FLZ173")
    assert "if-modified-since" in route.calls.last.request.headers
    assert second.records.provenance.not_modified
    assert second.records.geometry == first.records.geometry


@pytest.mark.parametrize(
    ("kind", "zone_id"),
    [("forecast", "FLZ17"), ("forecast", "../x"), ("county", "flc086"), ("marine", "FLZ173")],
)
def test_a_zone_url_takes_only_a_zone_kind_and_id(kind: str, zone_id: str) -> None:
    with pytest.raises(ValueError, match="NWS zone"):
        nws.zone_url(kind, zone_id)  # pyright: ignore[reportArgumentType] - a wrong kind on purpose


def test_a_zone_answer_for_another_zone_is_refused() -> None:
    directory = recorded("nws-zones")
    item = entry(directory, "zone-forecast-FLZ173.json")
    with pytest.raises(SourceError, match="another zone"):
        nws.parse_zone(
            directory.payload(item),
            recorded_result(directory, item).provenance(),
            zone_id="FLZ174",
        )


# Coordinate hygiene ------------------------------------------------------------------------


@pytest.fixture
def coordinates() -> tuple[str, str]:
    return synthetic_coordinates(load_landmarks(), ())


async def test_no_record_error_or_repr_carries_a_coordinate(
    coordinates: tuple[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    lat_text, lon_text = coordinates
    lat, lon = float(lat_text), float(lon_text)
    coverage = miami_coverage()
    location = location_at(lat, lon, coverage)
    feature = recorded_alert_feature()
    directory = recorded("nws-points")
    points_body = directory.payload(entry(directory, "points-miami-dade.json"))
    title = f"Unable to provide data for requested point {lat_text},{lon_text}"
    caplog.set_level(logging.DEBUG, logger="weatherbot.sources")
    errors: list[Exception] = []
    with respx.mock as router:
        router.get(nws.points_url(lat, lon)).mock(
            side_effect=[
                httpx.Response(200, content=points_body, headers=GEOJSON),
                httpx.Response(
                    404,
                    json={"type": nws.INVALID_POINT, "title": title, "detail": title},
                    headers=PROBLEM,
                ),
                httpx.Response(404, json={"type": "about:blank", "title": title}, headers=PROBLEM),
            ]
        )
        mock_alerts(
            router, location, point=collection(feature), county=collection(feature), forecast=EMPTY
        )
        async with open_client() as client:
            fetcher = Quiet().fetcher(client)
            covered = await nws.lookup_point(fetcher, lat, lon)
            outside = await nws.lookup_point(fetcher, lat, lon)
            try:
                await nws.lookup_point(fetcher, lat, lon)
            except SourceError as error:
                errors.append(error)
            alerts = await nws.fetch_alerts(fetcher, location)
    try:
        nws.format_point(lat + 200, lon)
    except ValueError as error:
        errors.append(error)

    assert [type(error).__name__ for error in errors] == ["SourceHttpError", "ValueError"]
    shown = [
        *(str(error) for error in errors),
        *(repr(error) for error in errors),
        repr(covered),
        repr(outside),
        repr(alerts),
        repr(location),
        *(repr(alert) for alert in alerts.records),
    ]
    shown += [r.getMessage() for r in caplog.records if r.levelno > logging.DEBUG]
    for text in shown:
        assert lat_text not in text
        assert lon_text not in text
    # Only DEBUG records name the full URL.
    assert any(lat_text in r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG)
    assert re.search(re.escape(lat_text), nws.points_url(lat, lon))
