# src/weatherbot/sources/nominatim.py
"""Nominatim reverse and forward geocoding (register source ``geocode-nominatim``).

``reverse_geocode`` asks OpenStreetMap's Nominatim for the place at a location's point and
returns its display name, country, and the licence text the display shows as attribution
(© OpenStreetMap contributors, ODbL 1.0). ``search`` asks Nominatim's ``/search`` endpoint
for up to five candidate places matching an operator's query on explicit user action
(``weatherbot locations add --place`` or the ``Search`` button on ``/settings``). The
usage policy allows at most one request per second, forbids autocomplete, requires results
to be cached, and treats periodic requests as bulk geocoding, so neither function ever runs
in a monitor cycle. The run's fetcher paces the host 1.5 seconds apart. Coordinates in
``reverse_url`` are written by ``nws.format_point``, and ``q`` in ``search_url`` is
redacted in logs above ``DEBUG``.
"""

import math
from typing import Final, cast
from urllib.parse import quote, urlencode

from weatherbot.models import GeocodeCandidate, GeocodeResult, OsmType, Provenance, SourceId
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.fields import (
    Fields,
    as_mapping,
    as_sequence,
    model_errors,
    parse_document,
)
from weatherbot.sources.http import Fetcher, SourceResult
from weatherbot.sources.nws import format_point

SOURCE: Final[SourceId] = "geocode-nominatim"
REVERSE_URL: Final = "https://nominatim.openstreetmap.org/reverse"
SEARCH_URL: Final = "https://nominatim.openstreetmap.org/search"
SEARCH_LIMIT: Final = 5
MAX_BYTES: Final = 256 * 1024

_ADDRESS_FIELDS: Final = frozenset({"country_code", "country"})
_TOP_FIELDS: Final = frozenset({"display_name", "name", "licence", "osm_type", "osm_id"})
FIELDS_READ: Final = _TOP_FIELDS | {f"address.{name}" for name in _ADDRESS_FIELDS}
"""The reverse-geocoding fields the parser reads, nested members as ``object.member``."""

_SEARCH_ADDRESS_FIELDS: Final = frozenset({"country_code"})
_SEARCH_TOP_FIELDS: Final = frozenset(
    {"lat", "lon", "display_name", "name", "category", "type", "osm_type", "osm_id", "licence"}
)
SEARCH_FIELDS_READ: Final = _SEARCH_TOP_FIELDS | {
    f"address.{name}" for name in _SEARCH_ADDRESS_FIELDS
}
"""The forward-search fields the parser reads, nested members as ``object.member``."""


def reverse_url(lat: float, lon: float) -> str:
    """Return the ``reverse?format=jsonv2`` URL of a point.

    Args:
        lat: Degrees north.
        lon: Degrees east.

    Returns:
        The URL, with both values written by ``format_point``.
    """
    lat_text, _, lon_text = format_point(lat, lon).partition(",")
    return f"{REVERSE_URL}?format=jsonv2&lat={lat_text}&lon={lon_text}"


def search_url(query: str) -> str:
    """Return the ``search?q=...&format=jsonv2&addressdetails=1&limit=5`` URL for ``query``.

    Args:
        query: Place search text.

    Returns:
        The URL with ``q`` percent-encoded.
    """
    encoded = urlencode(
        {
            "q": query,
            "format": "jsonv2",
            "addressdetails": "1",
            "limit": str(SEARCH_LIMIT),
        },
        quote_via=quote,
    )
    return f"{SEARCH_URL}?{encoded}"


def _coordinate(fields: Fields, name: str, minimum: float, maximum: float) -> float:
    raw = fields.text(name)
    try:
        value = float(raw)
    except ValueError:
        raise SourceSchemaError(
            fields.source_id, f"{fields.where}: {name!r} is not a number"
        ) from None
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise SourceSchemaError(fields.source_id, f"{fields.where}: {name!r} is out of range")
    return value


def parse_reverse(body: bytes, provenance: Provenance) -> GeocodeResult | None:
    """Parse a reverse-geocoding answer.

    Args:
        body: The payload.
        provenance: The answer's provenance.

    Returns:
        The result, or ``None`` when Nominatim found no place at the point (its answer is
        an object with only ``error``, as for a point at sea).

    Raises:
        SourceSchemaError: A field the register lists is missing or malformed.
    """
    source = provenance.source_id
    what = "the reverse-geocoding answer"
    document = as_mapping(parse_document(body, source, what), source, what)
    if "error" in document and "display_name" not in document:
        return None
    fields = Fields(document, _TOP_FIELDS | {"address"}, source_id=source, where=what)
    address = fields.child("address", _ADDRESS_FIELDS)
    if address is None:
        raise SourceSchemaError(source, f"{what}: 'address' is missing")
    with model_errors(source, what):
        return GeocodeResult(
            display_name=fields.text("display_name"),
            name=fields.optional_text("name"),
            country_code=address.optional_text("country_code"),
            country=address.optional_text("country"),
            licence=fields.text("licence"),
            osm_type=fields.text("osm_type"),
            osm_id=fields.integer("osm_id"),
            provenance=provenance,
        )


def parse_search(body: bytes, provenance: Provenance) -> tuple[GeocodeCandidate, ...]:
    """Parse a Nominatim ``jsonv2`` forward-search response list.

    Args:
        body: The payload.
        provenance: The answer's provenance.

    Returns:
        Up to five ``GeocodeCandidate`` records; ``()`` for an empty ``[]`` answer.

    Raises:
        SourceSchemaError: The payload is not a JSON array or a candidate is malformed.
    """
    source = provenance.source_id
    what = "the search answer"
    items = as_sequence(parse_document(body, source, what), source, what)
    candidates: list[GeocodeCandidate] = []
    for index, item in enumerate(items):
        entry_what = f"{what}[{index}]"
        mapping = as_mapping(item, source, entry_what)
        fields = Fields(
            mapping, _SEARCH_TOP_FIELDS | {"address"}, source_id=source, where=entry_what
        )
        address = fields.child("address", _SEARCH_ADDRESS_FIELDS)
        if address is None:
            raise SourceSchemaError(source, f"{entry_what}: 'address' is missing")
        raw_name = fields.optional_text("name")
        raw_cc = address.optional_text("country_code")
        lat = _coordinate(fields, "lat", -90.0, 90.0)
        lon = _coordinate(fields, "lon", -180.0, 180.0)
        with model_errors(source, entry_what):
            candidates.append(
                GeocodeCandidate(
                    display_name=fields.text("display_name"),
                    name=raw_name or None,
                    latitude=lat,
                    longitude=lon,
                    country_code=raw_cc.lower() if raw_cc else None,
                    category=fields.text("category"),
                    kind=fields.text("type"),
                    osm_type=cast("OsmType", fields.text("osm_type")),
                    osm_id=fields.integer("osm_id"),
                    licence=fields.text("licence"),
                    provenance=provenance,
                )
            )
    return tuple(candidates)


async def reverse_geocode(
    fetcher: Fetcher, lat: float, lon: float
) -> SourceResult[GeocodeResult | None]:
    """Reverse-geocode a location's point: one request per location, at setup, never per fetch.

    Nominatim's usage policy asks for at most one request per second and for results to be
    cached; Step 6's locations service calls this once when a location is added and keeps
    the result.

    Args:
        fetcher: The run's fetcher (it paces the host 1.5 seconds apart).
        lat: Degrees north.
        lon: Degrees east.

    Returns:
        The result (``None`` when no place is found) and the answer.
    """
    result = await fetcher.get(reverse_url(lat, lon), source_id=SOURCE, max_bytes=MAX_BYTES)
    return SourceResult(parse_reverse(result.body, result.provenance()), (result,))


async def search(fetcher: Fetcher, query: str) -> SourceResult[tuple[GeocodeCandidate, ...]]:
    """Forward-search Nominatim once for ``query`` on explicit user action.

    Args:
        fetcher: The run's fetcher (it paces the host 1.5 seconds apart).
        query: Place search text.

    Returns:
        The candidates and the answer.
    """
    result = await fetcher.get(search_url(query), source_id=SOURCE, max_bytes=MAX_BYTES)
    return SourceResult(parse_search(result.body, result.provenance()), (result,))
