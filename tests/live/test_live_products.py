# tests/live/test_live_products.py
"""Live smoke tests of the NHC product and display clients.

Marked ``live`` and ``enable_socket``: they run only with ``pytest -m live``
(``.github/workflows/live-smoke.yml`` on dispatch). No request carries a coordinate. Tests
that need an active storm skip, with the reason, when the roster lists none.
"""

import pytest

import record_fixtures as recorder
from weatherbot.models import StormSummary
from weatherbot.sources import catalogs, nhc_arrival_times, nhc_gis_rss, nhc_outlook_graphics
from weatherbot.sources import nhc_text_products as text_products
from weatherbot.sources.http import HTTP_NOT_MODIFIED, HTTP_OK, Fetcher, open_client
from weatherbot.sources.nhc_current_storms import fetch_current_storms

pytestmark = [pytest.mark.live, pytest.mark.enable_socket, pytest.mark.anyio]

NO_STORM = "no storm is active, so the roster links no arrival-time KMZ and no TCP slot"


async def _storms(fetcher: Fetcher) -> tuple[StormSummary, ...]:
    return (await fetch_current_storms(fetcher)).records


async def test_each_active_storms_arrival_time_pair_parses() -> None:
    async with open_client() as client:
        fetcher = Fetcher(client)
        storms = [s for s in await _storms(fetcher) if nhc_arrival_times.arrival_links(s)]
        if not storms:
            pytest.skip(NO_STORM)
        result = await nhc_arrival_times.fetch_arrival_times(fetcher, storms)
    assert all(response.status == HTTP_OK for response in result.responses)
    for product in result.records:
        assert product.origin == "kmz"
        assert product.withheld_reason is None, product.withheld_reason
        assert product.published_at is not None


async def test_the_archived_pair_parses_with_resolved_instants() -> None:
    async with open_client() as client:
        fetcher = Fetcher(client)
        for url in recorder.ARCHIVED_ARRIVAL_PAIR:
            result = await fetcher.get(url, source_id=nhc_arrival_times.SOURCE)
            product = nhc_arrival_times.parse_arrival_kmz(result.body, result.provenance())
            assert product.withheld_reason is None
            assert all(line.valid_at for line in product.lines if not line.is_outer_contour)


async def test_one_active_slots_tcp_list_reads() -> None:
    async with open_client() as client:
        fetcher = Fetcher(client)
        storms = await _storms(fetcher)
        if not storms:
            pytest.skip(NO_STORM)
        result = await text_products.fetch_tcps(fetcher, storms[:1])
    assert result.responses[0].url == text_products.list_url("TCP", storms[0].slot)
    assert all(product.atcf_id == storms[0].atcf_id for product in result.records)


async def test_the_three_two_lists_read() -> None:
    async with open_client() as client:
        result = await text_products.fetch_twos(Fetcher(client))
    listed = [r.url for r in result.responses if "/types/TWO/" in r.url]
    assert listed == [text_products.list_url("TWO", basin) for basin in text_products.TWO_BASINS]
    assert all(product.code == "TWO" for product in result.records)


async def test_one_graphic_answers_a_conditional_request() -> None:
    url = nhc_outlook_graphics.GRAPHIC_URLS[1]
    async with open_client() as client:
        fetcher = Fetcher(client)
        first = await fetcher.get(url, source_id=nhc_outlook_graphics.SOURCE)
        second = await fetcher.get(url, source_id=nhc_outlook_graphics.SOURCE)
    graphic = nhc_outlook_graphics.parse_outlook_graphic(second.body, second.provenance())
    assert first.status == HTTP_OK
    assert first.headers.get("etag") or first.headers.get("last-modified")
    # NHC honors the validators; a map redrawn between the two requests answers 200.
    assert second.status in {HTTP_OK, HTTP_NOT_MODIFIED}
    assert second.not_modified == (second.status == HTTP_NOT_MODIFIED)
    assert graphic.width_px > 0


async def test_the_three_feeds_parse() -> None:
    async with open_client() as client:
        result = await nhc_gis_rss.fetch_gis_feeds(Fetcher(client))
    assert {item.feed for item in result.records} == set(nhc_gis_rss.FEEDS)


async def test_both_overlay_capabilities_and_the_surge_risk_catalog_parse() -> None:
    async with open_client() as client:
        fetcher = Fetcher(client)
        overlays = await catalogs.fetch_overlay_catalogs(fetcher)
        surge = await catalogs.fetch_surge_risk_catalog(fetcher)
    assert len(overlays.records) == len(catalogs.OVERLAYS)
    assert len(catalogs.surge_risk_images(surge.records)) == len(catalogs.SURGE_RISK_CATEGORIES)
