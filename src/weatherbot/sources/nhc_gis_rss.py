# src/weatherbot/sources/nhc_gis_rss.py
"""NHC's GIS RSS feeds, ``gis-{at,ep,cp}.xml`` (register source ``nhc-gis-rss``).

Each feed is RSS 2.0 with the ``nhc`` namespace, parsed with ``defusedxml``. An item gives
its ``guid``, ``title``, ``link``, and ``pubDate`` (RFC 2822, converted to UTC); a storm's
summary item also carries ``nhc:Cyclone``, whose ``atcf`` and ``wallet`` name the storm and
its slot. With no storm in a basin the feed holds one placeholder item, "There are no
tropical cyclones at this time.", whose ``pubDate`` lies in the future and is not a time,
so it has none. The channel's ``pubDate`` is not read: NHC rewrites it without changing an
item, and change detection compares each item's ``guid``.
"""

import asyncio
import re
from collections.abc import Mapping
from datetime import datetime
from email.utils import parsedate_to_datetime
from types import MappingProxyType
from typing import Final, Literal

from weatherbot.models import NO_STORMS_TITLE, GisFeedItem, Provenance, SourceId
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.fields import Fields, model_errors
from weatherbot.sources.http import Fetcher, SourceResult
from weatherbot.sources.markup import (
    XmlElement,
    children,
    local_name,
    namespace_of,
    parse_xml,
    text_of,
)

SOURCE: Final[SourceId] = "nhc-gis-rss"
NHC_NAMESPACE: Final = "https://www.nhc.noaa.gov"

type Feed = Literal["at", "ep", "cp"]
FEEDS: Final[tuple[Feed, ...]] = ("at", "ep", "cp")

_ITEM_FIELDS: Final = frozenset({"guid", "title", "link", "pubDate"})
CYCLONE: Final = "nhc:Cyclone"
_CYCLONE_FIELDS: Final = frozenset({"atcf", "wallet"})
FIELDS_READ: Final = frozenset(_ITEM_FIELDS | {f"{CYCLONE}.{member}" for member in _CYCLONE_FIELDS})
"""The item fields the parser reads, ``nhc:Cyclone`` members as ``nhc:Cyclone.member``."""

MAX_FEED_BYTES: Final = 2 * 1024 * 1024
_FEED_URL: Final = re.compile(r"/gis-(?P<feed>at|ep|cp)\.xml$")
_FEED_NAMES: Final[Mapping[str, Feed]] = MappingProxyType({feed: feed for feed in FEEDS})


def feed_url(feed: Feed) -> str:
    """Return a feed's URL.

    Args:
        feed: ``at``, ``ep``, or ``cp``.

    Returns:
        The URL.
    """
    return f"https://www.nhc.noaa.gov/gis-{feed}.xml"


def _item_values(item: XmlElement) -> tuple[dict[str, object], bool]:
    """An item's plain children by local name, ``nhc:Cyclone``'s as ``nhc:Cyclone.member``."""
    values: dict[str, object] = {
        local_name(child): text_of(child) for child in item if namespace_of(child) is None
    }
    cyclones = children(item, "Cyclone", NHC_NAMESPACE)
    for child in cyclones[0] if cyclones else ():
        if namespace_of(child) == NHC_NAMESPACE:
            values[f"{CYCLONE}.{local_name(child)}"] = text_of(child)
    return values, bool(cyclones)


def _published_at(fields: Fields, *, placeholder: bool) -> datetime | None:
    text = fields.text("pubDate")
    if placeholder:
        return None
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        when = None
    if when is None or when.tzinfo is None:
        message = f"{fields.where}: 'pubDate' is not an RFC 2822 time with a zone"
        raise SourceSchemaError(fields.source_id, message)
    return when


def parse_gis_feed(body: bytes, provenance: Provenance) -> tuple[GisFeedItem, ...]:
    """Parse one GIS RSS feed into its items; the feed comes from the URL.

    Args:
        body: The feed.
        provenance: The answer's provenance.

    Returns:
        Every item, in feed order, the placeholder included.

    Raises:
        SourceSchemaError: The URL is not a GIS feed, the XML declares a DTD or is not RSS
            2.0, or an item lacks a field the register lists.
    """
    source = provenance.source_id
    named = _FEED_URL.search(provenance.url)
    if named is None:
        raise SourceSchemaError(source, "the URL is not one of the three GIS feeds")
    feed = _FEED_NAMES[named["feed"]]
    root = parse_xml(body, source, f"gis-{feed}.xml")
    channels = children(root, "channel")
    if local_name(root) != "rss" or root.get("version") != "2.0" or len(channels) != 1:
        raise SourceSchemaError(source, f"gis-{feed}.xml is not an RSS 2.0 feed")
    items: list[GisFeedItem] = []
    for index, item in enumerate(children(channels[0], "item")):
        where = f"gis-{feed}.xml item {index}"
        values, has_cyclone = _item_values(item)
        fields = Fields(values, FIELDS_READ, source_id=source, where=where)
        title = fields.text("title")
        placeholder = title == NO_STORMS_TITLE
        atcf_id = slot = None
        if has_cyclone:
            atcf_id = fields.text(f"{CYCLONE}.atcf").upper()
            slot = fields.text(f"{CYCLONE}.wallet").upper()
        with model_errors(source, where):
            items.append(
                GisFeedItem.model_validate(
                    {
                        "feed": feed,
                        "guid": fields.text("guid"),
                        "title": title,
                        "link": fields.text("link"),
                        "published_at": _published_at(fields, placeholder=placeholder),
                        "is_placeholder": placeholder,
                        "atcf_id": atcf_id,
                        "slot": slot,
                        "provenance": provenance,
                    }
                )
            )
    return tuple(items)


async def fetch_gis_feeds(fetcher: Fetcher) -> SourceResult[tuple[GisFeedItem, ...]]:
    """Fetch and parse the three feeds, conditionally when the store holds validators.

    Args:
        fetcher: The run's fetcher.

    Returns:
        Every item of the three feeds, Atlantic first, and the answers.
    """
    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(
                fetcher.get(feed_url(feed), source_id=SOURCE, max_bytes=MAX_FEED_BYTES)
            )
            for feed in FEEDS
        ]
    results = tuple(task.result() for task in tasks)
    items = tuple(item for r in results for item in parse_gis_feed(r.body, r.provenance()))
    return SourceResult(items, results)
