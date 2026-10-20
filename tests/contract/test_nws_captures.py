# tests/contract/test_nws_captures.py
"""Contract tests: every recorded capture of the NWS and geocoding sources parses.

The sources are ``nws-points``, ``nws-alerts-point``, ``nws-alerts-zone``, ``nws-zones``,
and ``geocode-nominatim``. Each parser's ``FIELDS_READ`` must equal the register's "Fields
v2 uses", and deleting any one field from a recorded capture must fail the parse with a
``SourceSchemaError`` that names it (the field-coverage rule of ``test_field_coverage.py``).
The merge is proved twice: on the alert recorded on 2026-10-17, which all three queries
returned, and on an alert built here from the register's ``FLC086`` description of
2026-10-12, added to that day's empty county answer. No alert fixture is fabricated.
"""

import copy
import json
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, cast

import httpx
import pytest
import respx
from fixture_support import (
    REGISTER_AFFECTED,
    REGISTER_SAME,
    CaptureDirectory,
    as_list,
    as_object,
    capture_directories,
    register_alert,
    register_section_fields,
)

from check_personal_data import load_landmarks
from weatherbot.models import AlertQuery, LatLon, Location, NwsCoverage, Provenance, SourceId
from weatherbot.sources import nominatim, nws
from weatherbot.sources.errors import DocumentedProblem, SourceSchemaError
from weatherbot.sources.http import HTTP_OK, Fetcher, HostPacer, open_client

pytestmark = pytest.mark.anyio

SOURCES: tuple[SourceId, ...] = (
    "nws-points",
    "nws-alerts-point",
    "nws-alerts-zone",
    "nws-zones",
    "geocode-nominatim",
)
FIRST_DAY = "2026-10-12"
FIRST_ALERT_DAY = "2026-10-17"
COUNTY = "FLC086"
FORECAST_ZONE = "FLZ173"

type Capture = tuple[CaptureDirectory, dict[str, object]]


def _captures(source: str, day: str | None = None) -> list[Capture]:
    return [
        (directory, item)
        for directory in capture_directories()
        if directory.source == source and (day is None or directory.day == day)
        for item in directory.entries
    ]


def _capture(source: str, day: str, name: str) -> Capture:
    return next(c for c in _captures(source, day) if c[1]["file"] == name)


def _label(capture: Capture) -> str:
    return f"{capture[0].label}/{capture[1]['file']}"


def _status(capture: Capture) -> int:
    return int(str(capture[1]["status"]))


def _provenance(capture: Capture) -> Provenance:
    directory, item = capture
    return Provenance(
        source_id=cast("SourceId", directory.source),
        url=str(item["url"]),
        status=_status(capture),
        fetched_at=datetime.fromisoformat(str(item["fetched_at"])),
        sha256=str(item["sha256"]),
    )


def _body(capture: Capture) -> bytes:
    return capture[0].payload(capture[1])


def _document(capture: Capture) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(_body(capture)))


def _landmark_point(key: str) -> tuple[float, float]:
    found = next(item for item in load_landmarks() if item.key == key)
    return float(found.lat), float(found.lon)


def _key(capture: Capture, prefix: str) -> str:
    return str(capture[1]["file"]).removeprefix(prefix).rsplit(".", 1)[0]


def _query(capture: Capture) -> AlertQuery:
    name = str(capture[1]["file"])
    zone_id = name.removeprefix("alerts-zone-").removesuffix(".geojson")
    if capture[0].source == "nws-alerts-point":
        return AlertQuery(kind="point", provenance=_provenance(capture))
    return AlertQuery(kind="zone", zone_id=zone_id, provenance=_provenance(capture))


def _zone_args(capture: Capture) -> tuple[nws.ZoneKind, str]:
    _, kind, zone_id = _key(capture, "").split("-")
    return cast("nws.ZoneKind", kind), zone_id


def _fetcher(client: httpx.AsyncClient) -> Fetcher:
    async def no_wait(_seconds: float) -> None:
        return None

    return Fetcher(client, pacer=HostPacer(sleep=no_wait), sleep=no_wait)


def _respond(router: respx.MockRouter, capture: Capture, body: bytes | None = None) -> respx.Route:
    headers = {
        str(k): str(v)
        for k, v in as_object(capture[1]["headers"]).items()
        if k not in {"content-length", "content-encoding"}
    }
    return router.get(str(capture[1]["url"])).mock(
        return_value=httpx.Response(
            _status(capture), content=body or _body(capture), headers=headers
        )
    )


def _miami_coverage() -> NwsCoverage:
    return nws.parse_point(_body(_capture("nws-points", FIRST_DAY, "points-miami-dade.json")))


def _miami_location() -> Location:
    lat, lon = _landmark_point("miami-dade")
    return Location(
        name="Miami-Dade landmark",
        point=LatLon(latitude=lat, longitude=lon),
        nws=_miami_coverage(),
    )


# Every capture parses ----------------------------------------------------------------------


@pytest.mark.parametrize("source", SOURCES)
def test_every_source_has_a_recorded_capture(source: str) -> None:
    assert _captures(source), f"{source} has no recorded capture"


POINT_CAPTURES = _captures("nws-points")


@pytest.mark.parametrize("capture", POINT_CAPTURES, ids=[_label(c) for c in POINT_CAPTURES])
async def test_every_points_capture_parses_or_is_outside_coverage(capture: Capture) -> None:
    lat, lon = _landmark_point(_key(capture, "points-"))
    assert nws.points_url(lat, lon) == capture[1]["url"]
    with respx.mock(assert_all_called=True) as router:
        _respond(router, capture)
        async with open_client() as client:
            result = await nws.lookup_point(_fetcher(client), lat, lon)
    if _status(capture) == nws.HTTP_NOT_FOUND:
        assert result.records == nws.OutsideNwsCoverage(
            nws.HTTP_NOT_FOUND, nws.INVALID_POINT, "Data Unavailable For Requested Point"
        )
        assert result.responses == ()
    else:
        assert result.records == NwsCoverage(
            forecast_zone=FORECAST_ZONE,
            county_zone=COUNTY,
            cwa="MFL",
            time_zone="America/New_York",
            city="Miami",
            state="FL",
        )


async def test_the_nassau_landmark_is_outside_coverage_and_asks_for_no_alert() -> None:
    lat, lon = _landmark_point("nassau")
    with respx.mock(assert_all_called=False) as router:
        _respond(router, _capture("nws-points", FIRST_DAY, "points-nassau.json"))
        other = router.route().mock(return_value=httpx.Response(500))
        async with open_client() as client:
            fetcher = _fetcher(client)
            coverage = (await nws.lookup_point(fetcher, lat, lon)).records
            assert isinstance(coverage, nws.OutsideNwsCoverage)
            location = Location(name="Nassau landmark", point=LatLon(latitude=lat, longitude=lon))
            alerts = await nws.fetch_alerts(fetcher, location)
    assert alerts.records == ()
    assert other.call_count == 0


ALERT_CAPTURES = [
    c
    for s in ("nws-alerts-point", "nws-alerts-zone")
    for c in _captures(s)
    if _status(c) == HTTP_OK
]


@pytest.mark.parametrize("capture", ALERT_CAPTURES, ids=[_label(c) for c in ALERT_CAPTURES])
def test_every_alerts_capture_parses(capture: Capture) -> None:
    alerts = nws.parse_alerts(_body(capture), _query(capture))
    assert len(alerts) == len(as_list(_document(capture)["features"]))
    if capture[0].day == FIRST_DAY:
        assert alerts == ()  # the FLC086 statement had expired by the recording


@pytest.mark.parametrize(
    "capture",
    [c for c in _captures("nws-alerts-point") if _status(c) == nws.HTTP_BAD_REQUEST],
    ids=_label,
)
async def test_the_nassau_point_alerts_answer_is_a_documented_problem(capture: Capture) -> None:
    lat, lon = _landmark_point("nassau")
    assert nws.point_alerts_url(lat, lon) == capture[1]["url"]
    covered = Location(
        name="Nassau, wrongly covered",
        point=LatLon(latitude=lat, longitude=lon),
        nws=_miami_coverage(),
    )
    with respx.mock as router:
        _respond(router, capture)
        async with open_client() as client:
            with pytest.raises(DocumentedProblem) as raised:
                await nws.fetch_alerts(_fetcher(client), covered)
    assert raised.value.problem_type == "https://api.weather.gov/problems/InvalidParameter"


ZONE_CAPTURES = _captures("nws-zones")


@pytest.mark.parametrize("capture", ZONE_CAPTURES, ids=[_label(c) for c in ZONE_CAPTURES])
async def test_every_zone_capture_parses(capture: Capture) -> None:
    kind, zone_id = _zone_args(capture)
    assert nws.zone_url(kind, zone_id) == capture[1]["url"]
    with respx.mock as router:
        _respond(router, capture)
        async with open_client() as client:
            zone = (await nws.fetch_zone(_fetcher(client), kind, zone_id)).records
    assert zone.id == zone_id
    assert zone.geometry.type == "MultiPolygon"
    assert zone.geometry.crs.name == "EPSG:4326"
    assert (zone.cwa, zone.time_zone, zone.state) == (("MFL",), ("America/New_York",), "FL")


GEOCODE_CAPTURES = _captures("geocode-nominatim")


@pytest.mark.parametrize("capture", GEOCODE_CAPTURES, ids=[_label(c) for c in GEOCODE_CAPTURES])
def test_every_reverse_lookup_parses(capture: Capture) -> None:
    lat, lon = _landmark_point(_key(capture, "reverse-"))
    assert nominatim.reverse_url(lat, lon) == capture[1]["url"]
    place = nominatim.parse_reverse(_body(capture), _provenance(capture))
    assert place is not None
    assert place.country_code in {"us", "bs"}
    assert "OpenStreetMap" in place.licence


# The merge ---------------------------------------------------------------------------------


async def test_the_recorded_alert_merges_into_one_alert_found_by_all_three_queries() -> None:
    location = _miami_location()
    with respx.mock(assert_all_called=True) as router:
        _respond(
            router, _capture("nws-alerts-point", FIRST_ALERT_DAY, "alerts-point-miami-dade.geojson")
        )
        for zone in (COUNTY, FORECAST_ZONE):
            _respond(
                router, _capture("nws-alerts-zone", FIRST_ALERT_DAY, f"alerts-zone-{zone}.geojson")
            )
        async with open_client() as client:
            result = await nws.fetch_alerts(_fetcher(client), location)
    (alert,) = result.records
    assert [(q.kind, q.zone_id) for q in alert.found_by] == [
        ("point", None),
        ("zone", COUNTY),
        ("zone", FORECAST_ZONE),
    ]
    assert FORECAST_ZONE in alert.affected_zone_ids
    assert REGISTER_SAME in alert.geocode_same
    assert alert.vtec
    assert alert.geometry is None


async def test_the_registers_flc086_alert_merges_into_one_alert_found_by_the_county() -> None:
    location = _miami_location()
    county = _capture("nws-alerts-zone", FIRST_DAY, f"alerts-zone-{COUNTY}.geojson")
    document = _document(county)
    sent = datetime.fromisoformat(str(county[1]["fetched_at"])) - timedelta(hours=6)
    document["features"] = [register_alert(sent)]
    with respx.mock(assert_all_called=True) as router:
        _respond(router, _capture("nws-alerts-point", FIRST_DAY, "alerts-point-miami-dade.geojson"))
        _respond(router, county, json.dumps(document).encode())
        _respond(
            router, _capture("nws-alerts-zone", FIRST_DAY, f"alerts-zone-{FORECAST_ZONE}.geojson")
        )
        async with open_client() as client:
            result = await nws.fetch_alerts(_fetcher(client), location)
    (alert,) = result.records
    assert [(q.kind, q.zone_id) for q in alert.found_by] == [("zone", COUNTY)]
    assert alert.affected_zone_ids == REGISTER_AFFECTED
    assert REGISTER_SAME in alert.geocode_same
    assert (alert.vtec, alert.nws_headline) == ((), ())
    # Not filtered: the location's forecast zone is not among the affected zones.
    assert FORECAST_ZONE not in alert.affected_zone_ids


# The field-coverage rule -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "level", "declared"),
    [
        ("Points", 3, nws.POINT_FIELDS_READ),
        ("Alerts for a zone", 3, nws.ALERT_FIELDS_READ),
        ("Zones", 3, nws.ZONE_FIELDS_READ),
        ("OpenStreetMap: basemap and geocoding", 2, nominatim.FIELDS_READ),
    ],
    ids=["points", "alerts", "zones", "nominatim"],
)
def test_each_parser_reads_exactly_the_registers_fields(
    heading: str, level: int, declared: frozenset[str]
) -> None:
    assert register_section_fields(heading, level=level) == declared


def _delete(container: dict[str, Any], field: str) -> str:
    """Delete a dotted field from a JSON object; return the member's own name."""
    *parents, name = field.split(".")
    for parent in parents:
        container = container[parent]
    del container[name]
    return name


def _alert_features() -> list[tuple[str, dict[str, Any]]]:
    recorded = [
        (_label(capture), feature)
        for capture in ALERT_CAPTURES
        for feature in cast("list[dict[str, Any]]", _document(capture)["features"])
    ]
    built = register_alert(datetime.fromisoformat("2026-10-12T19:39:00+00:00"))
    return [*recorded, ("register-FLC086", cast("dict[str, Any]", built))]


def _parse_points(document: dict[str, Any], _: Capture) -> object:
    return nws.parse_point(json.dumps(document).encode())


def _parse_zone(document: dict[str, Any], capture: Capture) -> object:
    _, zone_id = _zone_args(capture)
    return nws.parse_zone(json.dumps(document).encode(), _provenance(capture), zone_id=zone_id)


def _parse_reverse(document: dict[str, Any], capture: Capture) -> object:
    return nominatim.parse_reverse(json.dumps(document).encode(), _provenance(capture))


DOCUMENT_RULES: Mapping[
    str, tuple[frozenset[str], str, Callable[[dict[str, Any], Capture], object]]
] = {
    "nws-points": (nws.POINT_FIELDS_READ, "properties", _parse_points),
    "nws-zones": (nws.ZONE_FIELDS_READ, "properties", _parse_zone),
    "geocode-nominatim": (nominatim.FIELDS_READ, "", _parse_reverse),
}
DOCUMENT_DELETIONS = [
    (capture, field)
    for source, (fields, _, _) in DOCUMENT_RULES.items()
    for capture in _captures(source)
    if _status(capture) == HTTP_OK
    for field in sorted(fields)
]


@pytest.mark.parametrize(
    ("capture", "field"),
    DOCUMENT_DELETIONS,
    ids=[f"{_label(c)}:{f}" for c, f in DOCUMENT_DELETIONS],
)
def test_deleting_a_field_read_fails_the_parse(capture: Capture, field: str) -> None:
    _, root, parse = DOCUMENT_RULES[capture[0].source]
    document = _document(capture)
    name = _delete(document[root] if root else document, field)
    with pytest.raises(SourceSchemaError, match=name):
        parse(document, capture)


ALERT_FEATURES = _alert_features()
ALERT_DELETIONS = [
    (label, feature, field)
    for label, feature in ALERT_FEATURES
    for field in sorted(nws.ALERT_FIELDS_READ)
    if field in nws.OPTIONAL_ALERT_FIELDS or field.rsplit(".", 1)[0] in feature["properties"]
]


@pytest.mark.parametrize(
    ("label", "feature", "field"),
    ALERT_DELETIONS,
    ids=[f"{label}:{field}" for label, _, field in ALERT_DELETIONS],
)
def test_deleting_an_alert_field_fails_the_parse_unless_the_register_marks_it_optional(
    label: str, feature: dict[str, Any], field: str
) -> None:
    edited = copy.deepcopy(feature)
    query = AlertQuery(kind="zone", zone_id=COUNTY, provenance=_provenance(ALERT_CAPTURES[0]))
    properties = edited["properties"]
    if field in nws.OPTIONAL_ALERT_FIELDS:
        properties["parameters"].pop(field.split(".")[1], None)
        alert = nws.parse_alert(edited, query)
        assert getattr(alert, "vtec" if field.endswith("VTEC") else "nws_headline") == (), label
        return
    name = _delete(properties, field)
    with pytest.raises(SourceSchemaError, match=name):
        nws.parse_alert(edited, query)
