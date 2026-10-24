# tests/sources/test_cone_advisories.py
"""The summary service's attribute-only cone-layer query (``fetch_cone_advisories``)."""

import asyncio
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from source_support import Quiet, entry, layer_name, recorded

from weatherbot.models import AdvisoryNumber
from weatherbot.sources import arcgis, nhc_map
from weatherbot.sources.errors import SourceHttpError, SourceSchemaError
from weatherbot.sources.http import open_client


def _cone_capture() -> tuple[bytes, int]:
    capture = recorded("nhc-map-tropical-summary")
    for item in capture.entries:
        if str(item["file"]).startswith("query-") and layer_name(item) == nhc_map.FORECAST_CONE:
            layer_id = int(str(item["notes"]).rsplit("id ", 1)[1])
            return capture.payload(item), layer_id
    message = "recorded summary service capture lacks Forecast Cone"
    raise AssertionError(message)


def test_fetch_cone_advisories_sends_attribute_parameters_and_parses_recorded_cone() -> None:
    capture = recorded("nhc-map-tropical-summary")
    catalog_body = capture.payload(entry(capture, "catalog.json"))
    cone_body, layer_id = _cone_capture()
    expected_url = (
        f"{arcgis.TROPICAL_SUMMARY.url}/{layer_id}/query"
        "?where=1%3D1&outFields=binnumber,advisnum&returnGeometry=false&f=json"
    )

    async def _run() -> dict[str, AdvisoryNumber]:
        with respx.mock(assert_all_called=True) as router:
            router.get(f"{arcgis.TROPICAL_SUMMARY.url}?f=json").mock(
                return_value=httpx.Response(200, content=catalog_body)
            )
            route = router.get(expected_url).mock(
                return_value=httpx.Response(200, content=cone_body)
            )
            async with open_client() as client:
                fetcher = Quiet().fetcher(client)
                catalog = (await arcgis.fetch_catalog(fetcher, arcgis.TROPICAL_SUMMARY)).records
                result = await nhc_map.fetch_cone_advisories(fetcher, catalog)
            called_url = str(route.calls.last.request.url)
            params = parse_qs(urlsplit(called_url).query)
            assert params == {
                "where": ["1=1"],
                "outFields": ["binnumber,advisnum"],
                "returnGeometry": ["false"],
                "f": ["json"],
            }
            return {str(k): v for k, v in result.records.items()}

    advisories = asyncio.run(_run())
    assert advisories == {"EP5": AdvisoryNumber.parse("022A")}


def test_fetch_cone_advisories_parses_arcgis_json_attributes_and_rejects_bad_rows() -> None:
    rows = (
        {"binnumber": "AT1", "advisnum": "004A"},
        {"binnumber": "EP2", "advisnum": "12"},
    )
    parsed = nhc_map.parse_cone_advisories(rows)
    assert dict(parsed) == {
        "AT1": AdvisoryNumber.parse("004A"),
        "EP2": AdvisoryNumber.parse("12"),
    }

    with pytest.raises(SourceSchemaError, match="not a storm slot"):
        nhc_map.parse_cone_advisories(({"binnumber": "XX9", "advisnum": "1"},))

    with pytest.raises(SourceSchemaError, match="more than one advisory"):
        nhc_map.parse_cone_advisories(
            (
                {"binnumber": "AT1", "advisnum": "1"},
                {"binnumber": "AT1", "advisnum": "2"},
            )
        )


def test_arcgis_attributes_parses_f_json_attributes_and_refuses_error_object() -> None:
    capture = recorded("nhc-map-tropical-summary")
    catalog_body = capture.payload(entry(capture, "catalog.json"))
    _, layer_id = _cone_capture()
    query_url = (
        f"{arcgis.TROPICAL_SUMMARY.url}/{layer_id}/query"
        "?where=1%3D1&outFields=binnumber,advisnum&returnGeometry=false&f=json"
    )

    async def _run_ok() -> dict[str, AdvisoryNumber]:
        body = b'{"features": [{"attributes": {"binnumber": "AT2", "advisnum": "007"}}]}'
        with respx.mock(assert_all_called=True) as router:
            router.get(f"{arcgis.TROPICAL_SUMMARY.url}?f=json").mock(
                return_value=httpx.Response(200, content=catalog_body)
            )
            router.get(query_url).mock(return_value=httpx.Response(200, content=body))
            async with open_client() as client:
                fetcher = Quiet().fetcher(client)
                catalog = (await arcgis.fetch_catalog(fetcher, arcgis.TROPICAL_SUMMARY)).records
                result = await nhc_map.fetch_cone_advisories(fetcher, catalog)
                return {str(k): v for k, v in result.records.items()}

    assert asyncio.run(_run_ok()) == {"AT2": AdvisoryNumber.parse("007")}

    async def _run_err() -> None:
        body = b'{"error": {"code": 500, "message": "failed"}}'
        with respx.mock(assert_all_called=True) as router:
            router.get(f"{arcgis.TROPICAL_SUMMARY.url}?f=json").mock(
                return_value=httpx.Response(200, content=catalog_body)
            )
            router.get(query_url).mock(return_value=httpx.Response(200, content=body))
            async with open_client() as client:
                fetcher = Quiet().fetcher(client)
                catalog = (await arcgis.fetch_catalog(fetcher, arcgis.TROPICAL_SUMMARY)).records
                await nhc_map.fetch_cone_advisories(fetcher, catalog)

    with pytest.raises(SourceHttpError, match="ArcGIS error object"):
        asyncio.run(_run_err())
