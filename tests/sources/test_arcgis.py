# tests/sources/test_arcgis.py
"""Tests of the ArcGIS client: catalogs, layer resolution, paging, error objects, and counts."""

import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from fixture_support import as_list, as_object
from source_support import NOW, Quiet, entry, recorded, recorded_result

from weatherbot.models import MapCatalog
from weatherbot.sources.arcgis import (
    COUNT_PARAMETERS,
    QUERY_PARAMETERS,
    SURGE_RISK,
    TROPICAL_SUMMARY,
    TROPICAL_WEATHER,
    MapService,
    count,
    fetch_catalog,
    parse_catalog,
    parse_count,
    query,
    resolve,
)
from weatherbot.sources.errors import SourceHttpError, SourceSchemaError
from weatherbot.sources.http import FetchResult

SHIFT = 1000
SERVICE = MapService("nhc-map-tropical-weather", "Synthetic")
MAX_RECORDS = 2000
PAGE = 2
FEATURES = 5
PAGES = 3
TOKEN_ERROR = 498
BAD_REQUEST = 400
FOOTPRINTS = 4
PACIFIC_IMAGE = 5


def _result(document: object, service: MapService = SERVICE) -> FetchResult:
    body = json.dumps(document).encode()
    return FetchResult(
        source_id=service.source_id,
        url=f"{service.url}?f=json",
        status=200,
        body=body,
        headers={},
        fetched_at=NOW,
        sha256="0" * 64,
    )


def _catalog(layers: list[dict[str, object]], limit: int = 2000) -> MapCatalog:
    return parse_catalog(_result({"layers": layers, "maxRecordCount": limit}), SERVICE)


def _layer(
    layer_id: int, name: str, parent: int = -1, kind: str = "Feature Layer"
) -> dict[str, object]:
    return {"id": layer_id, "name": name, "parentLayerId": parent, "type": kind}


def test_the_recorded_catalogs_parse_with_their_group_paths() -> None:
    directory = recorded(TROPICAL_WEATHER.source_id)
    catalog = parse_catalog(
        recorded_result(directory, entry(directory, "catalog.json")), TROPICAL_WEATHER
    )
    assert catalog.service == "tropical/NHC_tropical_weather"
    assert catalog.max_record_count == MAX_RECORDS
    cone = resolve(catalog, "EP5 Forecast Cone")
    assert cone.group_path == ("EP5", "EP5 Forecast Information")
    assert cone.geometry_type == "esriGeometryPolygon"


def test_layers_resolve_by_name_after_their_ids_shift() -> None:
    directory = recorded(TROPICAL_SUMMARY.source_id)
    document = as_object(json.loads(directory.payload(entry(directory, "catalog.json"))))
    original = parse_catalog(_result(document, TROPICAL_SUMMARY), TROPICAL_SUMMARY)
    for layer in (as_object(item) for item in as_list(document["layers"])):
        layer["id"] = int(str(layer["id"])) + SHIFT
        parent = int(str(layer["parentLayerId"]))
        layer["parentLayerId"] = parent + SHIFT if parent != -1 else -1
    shifted = parse_catalog(_result(document, TROPICAL_SUMMARY), TROPICAL_SUMMARY)
    for name in ("Forecast Cone", "Probabilistic Winds 34 kts", "Seven-Day: Development Motion"):
        before, after = resolve(original, name), resolve(shifted, name)
        assert after.id == before.id + SHIFT
        assert after.group_path == before.group_path


def test_repeated_names_resolve_only_by_group_path() -> None:
    catalog = _catalog(
        [
            _layer(0, "Atlantic", kind="Group Layer"),
            _layer(1, "Category 1", 0, "Mosaic Layer"),
            _layer(2, "Image", 1, "Raster Layer"),
            _layer(3, "Pacific", kind="Group Layer"),
            _layer(4, "Category 1", 3, "Mosaic Layer"),
            _layer(5, "Image", 4, "Raster Layer"),
        ]
    )
    with pytest.raises(SourceSchemaError, match="2 layers match 'Image'"):
        resolve(catalog, "Image")
    assert resolve(catalog, "Pacific / Category 1 / Image").id == PACIFIC_IMAGE
    with pytest.raises(SourceSchemaError, match="0 layers match"):
        resolve(catalog, "Atlantic / Image")


def test_the_recorded_surge_risk_catalog_resolves_its_group_paths() -> None:
    directory = recorded(SURGE_RISK.source_id)
    catalog = parse_catalog(
        recorded_result(directory, entry(directory, "catalog.json")), SURGE_RISK
    )
    for category in range(1, 6):
        layer = resolve(catalog, f"Atlantic / US East and Gulf Coast / Category {category} / Image")
        assert layer.name == "Image"


def test_a_missing_layer_names_the_layer() -> None:
    with pytest.raises(SourceSchemaError, match="'Forecast Cone'"):
        resolve(_catalog([_layer(0, "Forecast Points")]), "Forecast Cone")


def test_a_catalog_error_object_is_an_http_error() -> None:
    with pytest.raises(SourceHttpError, match="code 498") as raised:
        parse_catalog(_result({"error": {"code": 498, "message": "Invalid token"}}), SERVICE)
    assert raised.value.status == TOKEN_ERROR


def test_a_catalog_without_layers_breaks_the_schema() -> None:
    with pytest.raises(SourceSchemaError, match="layers"):
        parse_catalog(_result({"currentVersion": 11.3}), SERVICE)


def _features(start: int, stop: int) -> list[dict[str, object]]:
    return [
        {
            "type": "Feature",
            "id": number,
            "geometry": None,
            "properties": {"objectid": number},
        }
        for number in range(start, stop)
    ]


@pytest.mark.anyio
async def test_a_truncated_layer_pages_by_objectid_until_a_page_is_complete() -> None:
    layer = _catalog([_layer(7, "Synthetic Layer")], limit=2).layers[0]
    requests: list[dict[str, list[str]]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        parameters = parse_qs(urlsplit(str(request.url)).query)
        requests.append(parameters)
        if "resultOffset" not in parameters:
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": _features(1, 3),
                    "exceededTransferLimit": True,
                },
            )
        offset = int(parameters["resultOffset"][0])
        page = _features(offset + 1, min(offset + 3, 6))
        collection: dict[str, object] = {"type": "FeatureCollection", "features": page}
        if offset + PAGE < FEATURES:
            collection["exceededTransferLimit"] = True
        return httpx.Response(200, json=collection)

    with respx.mock as router:
        router.get(url__startswith=f"{SERVICE.url}/7/query").mock(side_effect=answer)
        async with httpx.AsyncClient() as client:
            result = await query(Quiet().fetcher(client), SERVICE, layer, page_size=2)

    assert len(result.pages) == PAGES
    assert [feature["id"] for feature in result.features] == [1, 2, 3, 4, 5]
    assert len(result.responses) == PAGES
    first, *pages = requests
    assert {name: values[0] for name, values in first.items()} == dict(QUERY_PARAMETERS)
    for number, parameters in enumerate(pages):
        assert parameters["resultOffset"] == [str(number * 2)]
        assert parameters["resultRecordCount"] == ["2"]
        assert parameters["orderByFields"] == ["objectid"]
        assert parameters["outSR"] == ["4326"]


@pytest.mark.anyio
async def test_an_error_object_in_a_200_query_is_an_http_error() -> None:
    layer = _catalog([_layer(3, "Broken")]).layers[0]
    with respx.mock as router:
        router.get(url__startswith=f"{SERVICE.url}/3/query").mock(
            return_value=httpx.Response(200, json={"error": {"code": 400, "message": "bad"}})
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(SourceHttpError, match="ArcGIS error object") as raised:
                await query(Quiet().fetcher(client), SERVICE, layer)
    assert raised.value.status == BAD_REQUEST


@pytest.mark.anyio
async def test_a_query_that_is_not_a_feature_collection_breaks_the_schema() -> None:
    layer = _catalog([_layer(3, "Odd")]).layers[0]
    with respx.mock as router:
        router.get(url__startswith=f"{SERVICE.url}/3/query").mock(
            return_value=httpx.Response(200, json={"features": []})
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(SourceSchemaError, match="FeatureCollection"):
                await query(Quiet().fetcher(client), SERVICE, layer)


@pytest.mark.anyio
async def test_count_sends_the_count_parameters() -> None:
    layer = _catalog([_layer(9, "Footprint_Inun")]).layers[0]
    with respx.mock as router:
        route = router.get(url__startswith=f"{SERVICE.url}/9/query").mock(
            return_value=httpx.Response(200, json={"count": 4})
        )
        async with httpx.AsyncClient() as client:
            result = await count(Quiet().fetcher(client), SERVICE, layer)
    assert result.records == FOOTPRINTS
    sent = parse_qs(urlsplit(str(route.calls.last.request.url)).query)
    assert {name: values[0] for name, values in sent.items()} == dict(COUNT_PARAMETERS)


def test_the_recorded_counts_parse() -> None:
    directory = recorded(TROPICAL_SUMMARY.source_id)
    for name in ("count-footprint-inun.json", "count-footprint-tmask.json"):
        assert parse_count(recorded_result(directory, entry(directory, name)), name) == 0


@pytest.mark.anyio
async def test_fetch_catalog_reads_the_service_catalog_once() -> None:
    directory = recorded(TROPICAL_SUMMARY.source_id)
    with respx.mock as router:
        route = router.get(f"{TROPICAL_SUMMARY.url}?f=json").mock(
            return_value=httpx.Response(
                200, content=directory.payload(entry(directory, "catalog.json"))
            )
        )
        async with httpx.AsyncClient() as client:
            result = await fetch_catalog(Quiet().fetcher(client), TROPICAL_SUMMARY)
    assert route.call_count == 1
    assert result.records.provenance.source_id == "nhc-map-tropical-summary"
    assert resolve(result.records, "Forecast Cone").name == "Forecast Cone"
