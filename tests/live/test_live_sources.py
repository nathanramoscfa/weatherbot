# tests/live/test_live_sources.py
"""Live smoke tests of the source clients against the real NHC services.

Each test is marked ``live`` and ``enable_socket`` and runs only with ``pytest -m live``
(``.github/workflows/live-smoke.yml`` runs them on dispatch). No request carries a
coordinate: the roster, two service catalogs, and one outlook layer are location-free.
"""

import pytest
from fixture_support import register_layers

from weatherbot.models import OutlookArea
from weatherbot.sources.arcgis import (
    TROPICAL_SUMMARY,
    TROPICAL_WEATHER,
    fetch_catalog,
    query,
    resolve,
)
from weatherbot.sources.http import HTTP_OK, Fetcher, open_client
from weatherbot.sources.nhc_current_storms import fetch_current_storms
from weatherbot.sources.nhc_map import parse_outlook

pytestmark = [pytest.mark.live, pytest.mark.enable_socket, pytest.mark.anyio]

SLOTS = tuple(f"{basin}{number}" for basin in ("AT", "EP", "CP") for number in range(1, 6))
OUTLOOK_LAYER = "Seven-Day: Potential Development Region"


def _expanded(service: str) -> list[str]:
    names: list[str] = []
    for layer in register_layers(service):
        if "{slot}" in layer.name:
            names.extend(layer.name.replace("{slot}", slot) for slot in SLOTS)
        else:
            names.append(layer.name)
    return names


async def test_the_roster_fetches_and_parses() -> None:
    async with open_client() as client:
        result = await fetch_current_storms(Fetcher(client))
    (response,) = result.responses
    assert response.status == HTTP_OK
    assert all(storm.atcf_id[:2] in {"AL", "EP", "CP"} for storm in result.records)


async def test_every_summary_register_layer_resolves() -> None:
    async with open_client() as client:
        catalog = (await fetch_catalog(Fetcher(client), TROPICAL_SUMMARY)).records
    for name in _expanded(TROPICAL_SUMMARY.name):
        assert resolve(catalog, name).name == name


async def test_every_slot_layer_resolves_for_all_fifteen_slots() -> None:
    async with open_client() as client:
        catalog = (await fetch_catalog(Fetcher(client), TROPICAL_WEATHER)).records
    names = _expanded(TROPICAL_WEATHER.name)
    assert sum(name.endswith(" Forecast Cone") for name in names) == len(SLOTS)
    for name in names:
        assert resolve(catalog, name).name == name


async def test_one_outlook_layer_queries_and_parses() -> None:
    async with open_client() as client:
        fetcher = Fetcher(client)
        catalog = (await fetch_catalog(fetcher, TROPICAL_SUMMARY)).records
        result = await query(
            fetcher,
            TROPICAL_SUMMARY,
            resolve(catalog, OUTLOOK_LAYER),
            page_size=catalog.max_record_count,
        )
    areas = [
        area
        for page in result.pages
        for area in parse_outlook(OUTLOOK_LAYER, page.collection, page.result.provenance())
    ]
    assert all(isinstance(area, OutlookArea) for area in areas)
    assert all(area.kind == "development_region" for area in areas)
