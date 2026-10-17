# tests/sources/test_nhc_gis_rss.py
"""Tests of the GIS RSS client over the recorded feeds and edited copies of them."""

from datetime import UTC, datetime

import httpx
import pytest
import respx
from source_support import Quiet, entry, recorded, recorded_result, serve

from weatherbot.models import Provenance
from weatherbot.sources import nhc_gis_rss as rss
from weatherbot.sources.errors import SourceSchemaError

EP_ITEMS = 8


def feed(name: str) -> tuple[bytes, Provenance]:
    directory = recorded("nhc-gis-rss")
    result = recorded_result(directory, entry(directory, name))
    return result.body, result.provenance()


@pytest.mark.parametrize("name", ["gis-at.xml", "gis-cp.xml"])
def test_a_feed_without_a_storm_holds_only_the_placeholder(name: str) -> None:
    body, provenance = feed(name)

    (item,) = rss.parse_gis_feed(body, provenance)

    assert item.is_placeholder
    assert (item.published_at, item.atcf_id, item.slot) == (None, None, None)
    assert item.feed == name[4:6]


def test_the_storm_feed_names_its_storm_and_dates_its_items_in_utc() -> None:
    body, provenance = feed("gis-ep.xml")

    items = rss.parse_gis_feed(body, provenance)

    assert len(items) == EP_ITEMS
    summary = items[0]
    assert (summary.atcf_id, summary.slot) == ("EP202026", "EP5")
    assert summary.guid == "summary-ep202026-202610122333"
    assert summary.published_at == datetime(2026, 10, 12, 23, 33, 58, tzinfo=UTC)
    assert all(item.published_at and item.published_at.tzinfo == UTC for item in items)
    assert all(item.atcf_id is None for item in items[1:]), "only the summary has nhc:Cyclone"
    assert not any(item.is_placeholder for item in items)


def _edited(old: bytes, new: bytes, name: str = "gis-ep.xml") -> tuple[bytes, Provenance]:
    body, provenance = feed(name)
    assert old in body
    return body.replace(old, new, 1), provenance


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (b'<guid isPermaLink="false">summary-ep202026-202610122333</guid>', b"", "guid"),
        (b"<nhc:atcf>EP202026</nhc:atcf>", b"", "nhc:Cyclone.atcf"),
        (b"<nhc:wallet>EP5</nhc:wallet>", b"", "nhc:Cyclone.wallet"),
        (b"Mon, 12 Oct 2026 23:33:58 GMT", b"soon", "RFC 2822"),
        (b'<rss version="2.0"', b'<rss version="0.91"', "not an RSS 2.0 feed"),
        (b"<channel>", b"<channel><!-- -->", None),
    ],
    ids=["missing-guid", "missing-atcf", "missing-wallet", "bad-date", "version", "comment"],
)
def test_items_are_read_strictly(old: bytes, new: bytes, message: str | None) -> None:
    body, provenance = _edited(old, new)
    if message is None:
        assert rss.parse_gis_feed(body, provenance)
        return
    with pytest.raises(SourceSchemaError, match=message):
        rss.parse_gis_feed(body, provenance)


def test_a_feed_with_an_entity_declaration_is_refused() -> None:
    body, provenance = feed("gis-at.xml")
    declared = body.replace(
        b'<rss version="2.0"', b'<!DOCTYPE rss [<!ENTITY a "x">]><rss version="2.0"', 1
    )

    with pytest.raises(SourceSchemaError, match="declares a DTD or an entity"):
        rss.parse_gis_feed(declared, provenance)


def test_the_channel_pub_date_is_not_read() -> None:
    body, provenance = _edited(
        b"<pubDate>Tue, 13 Oct 2026 00:17:17 GMT</pubDate>", b"<pubDate>never</pubDate>"
    )

    assert rss.parse_gis_feed(body, provenance) == rss.parse_gis_feed(*feed("gis-ep.xml"))


@pytest.mark.anyio
async def test_fetch_reads_the_three_feeds() -> None:
    with respx.mock(assert_all_called=False) as router:
        serve(router, recorded("nhc-gis-rss"))
        async with httpx.AsyncClient() as client:
            result = await rss.fetch_gis_feeds(Quiet().fetcher(client))

    assert [r.url for r in result.responses] == [rss.feed_url(f) for f in rss.FEEDS]
    assert [item.feed for item in result.records] == ["at", *["ep"] * EP_ITEMS, "cp"]
