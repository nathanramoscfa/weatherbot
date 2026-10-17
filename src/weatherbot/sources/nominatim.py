# src/weatherbot/sources/nominatim.py
"""Nominatim reverse geocoding (register source ``geocode-nominatim``).

``reverse_geocode`` asks OpenStreetMap's Nominatim for the place at a location's point and
returns its display name, country, and the licence text the display shows as attribution
(© OpenStreetMap contributors, ODbL 1.0). The usage policy allows at most one request per
second, requires the results to be cached, and treats periodic requests as bulk geocoding,
so the rule Step 6 enforces is one request per location, at setup, never per fetch; the
result is kept with the location for good. The run's fetcher paces the host 1.5 seconds
apart. The point is written into the URL by ``nws.format_point``, the only writer of a
coordinate into a URL, and the result's provenance keeps that URL out of ``repr``.
"""

from typing import Final

from weatherbot.models import GeocodeResult, Provenance, SourceId
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.fields import Fields, as_mapping, model_errors, parse_document
from weatherbot.sources.http import Fetcher, SourceResult
from weatherbot.sources.nws import format_point

SOURCE: Final[SourceId] = "geocode-nominatim"
REVERSE_URL: Final = "https://nominatim.openstreetmap.org/reverse"
MAX_BYTES: Final = 256 * 1024

_ADDRESS_FIELDS: Final = frozenset({"country_code", "country"})
_TOP_FIELDS: Final = frozenset({"display_name", "name", "licence", "osm_type", "osm_id"})
FIELDS_READ: Final = _TOP_FIELDS | {f"address.{name}" for name in _ADDRESS_FIELDS}
"""The fields the parser reads, nested members as ``object.member``: the register's list."""


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


async def reverse_geocode(
    fetcher: Fetcher, lat: float, lon: float
) -> SourceResult[GeocodeResult | None]:
    """Reverse-geocode a location's point: one request per location, at setup, never per fetch.

    Nominatim's usage policy asks for at most one request per second and for results to be
    cached; Step 6's locations service calls this once when a location is added and keeps
    the result. Nothing else in Weatherbot calls Nominatim.

    Args:
        fetcher: The run's fetcher (it paces the host 1.5 seconds apart).
        lat: Degrees north.
        lon: Degrees east.

    Returns:
        The result (``None`` when no place is found) and the answer.
    """
    result = await fetcher.get(reverse_url(lat, lon), source_id=SOURCE, max_bytes=MAX_BYTES)
    return SourceResult(parse_reverse(result.body, result.provenance()), (result,))
