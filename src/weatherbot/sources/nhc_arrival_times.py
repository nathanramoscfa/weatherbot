# src/weatherbot/sources/nhc_arrival_times.py
"""Arrival times of tropical-storm-force winds from the KMZ the roster links (issue #11).

Register source ``nhc-arrival-times``. The roster's ``earliestArrivalTimeTSWindsGIS`` and
``mostLikelyTimeTSWindsGIS`` objects link one KMZ each per full advisory. Its KML states
the product's ``timezone``, ``advisoryNum``, ``atcfid``, and ``pubAdvTime`` in the
Document's ``ExtendedData``, which the map layers lack, so each labelled line resolves to
an instant by ``resolve_arrival_label``; the map-layer lines stay the label-only fallback.

The archive arrives from the network, so it is opened in memory under limits: at most 64
members, none absolute or containing ``..``, at most 8 MiB uncompressed in all, and no
member compressed more than 100 to 1. Exactly one ``.kml`` member is read, with
``defusedxml``; the label images are ignored. A URL is followed only when it matches the
arrival-time pattern on ``www.nhc.noaa.gov`` over HTTPS and names the storm and the kind of
the roster object that links it; anything else is a ``SourceSchemaError`` and is never
fetched.

When the KMZ disagrees with its own URL or with the roster (advisory, ATCF id, or an
issuance more than an hour from ``pubAdvTime``), or when ``timezone`` disagrees with the
zone ``pubAdvTime`` names, the product keeps its lines with no instant and the reason, and
the client logs a Source-drift warning. A product's storm and advisory come from its URL,
which is the roster's; its times come from the KML.
"""

import asyncio
import io
import re
import zipfile
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Final, Literal

from weatherbot.models import (
    WGS84,
    Advisory,
    AdvisoryNumber,
    ArrivalTimeLine,
    ArrivalTimeProduct,
    Geometry,
    Provenance,
    RosterProduct,
    SourceId,
    StormSummary,
    parse_nhc_local_time,
)
from weatherbot.sources.drift import warn_drift
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.fields import Fields, model_errors
from weatherbot.sources.http import Fetcher, FetchResult, SourceResult
from weatherbot.sources.markup import XmlElement, children, local_name, parse_xml, text_of

SOURCE: Final[SourceId] = "nhc-arrival-times"

ARRIVAL_KMZ_URL: Final = re.compile(
    r"^https://www\.nhc\.noaa\.gov/storm_graphics/api/"
    r"(?P<atcf>(?:AL|EP|CP)\d{6})_(?P<advisory>\d{3})adv_"
    r"(?P<kind>earliest_reasonable|most_likely)_toa_34\.kmz$"
)
"""The only URLs the client and the recorder follow: the register's arrival-time KMZ."""

type Kind = Literal["earliest_reasonable", "most_likely"]
KINDS: Final[tuple[Kind, ...]] = ("earliest_reasonable", "most_likely")

KML_NAMESPACES: Final = ("http://earth.google.com/kml/2.2", "http://www.opengis.net/kml/2.2")

# The archive limits; scripts/check_personal_data.py bounds a zip the same way, and a test
# keeps the two equal.
MAX_MEMBERS: Final = 64
MAX_UNCOMPRESSED_BYTES: Final = 8 * 1024 * 1024
MAX_COMPRESSION_RATIO: Final = 100
MAX_KMZ_BYTES: Final = 2 * 1024 * 1024
"""The download cap: the products are tens of kilobytes."""

FIELDS_READ: Final = frozenset({"timezone", "advisoryNum", "atcfid", "pubAdvTime"})
"""The ``ExtendedData`` keys the parser reads: the register's "Fields v2 uses"."""

OUTER_CONTOUR_LABEL: Final = "Wind Speed Probability 5% contour"
ISSUANCE_TOLERANCE: Final = timedelta(hours=1)
_LINE_GEOMETRIES: Final = ("LineString", "MultiGeometry")
_ZONE_OF_TEXT: Final = re.compile(r"\b(?:AM|PM)\s+(?P<zone>[A-Za-z]{2,5})\s", re.IGNORECASE)


def check_url(url: str, *, atcf_id: str | None = None, kind: Kind | None = None) -> re.Match[str]:
    """Check an arrival-time URL before anything fetches it.

    Args:
        url: The URL, as a roster object links it.
        atcf_id: The storm the roster lists the link under, when known.
        kind: The roster object the link came from, when known.

    Returns:
        The match: ``atcf``, ``advisory``, and ``kind``.

    Raises:
        SourceSchemaError: The URL is not the register's arrival-time KMZ over HTTPS on
            ``www.nhc.noaa.gov``, or names another storm or kind than its roster object.
    """
    match = ARRIVAL_KMZ_URL.fullmatch(url)
    if match is None:
        message = "a roster arrival-time link is not the register's KMZ pattern; not fetched"
        raise SourceSchemaError(SOURCE, message)
    if (atcf_id is not None and match["atcf"] != atcf_id) or (
        kind is not None and match["kind"] != kind
    ):
        message = (
            f"the roster's {kind or 'arrival-time'} link for {atcf_id or 'a storm'} names "
            f"{match['atcf']} {match['kind']}; not fetched"
        )
        raise SourceSchemaError(SOURCE, message)
    return match


def read_kml(body: bytes, source_id: SourceId = SOURCE) -> bytes:
    """Open a KMZ in memory under the limits and return its one KML member's bytes.

    Args:
        body: The KMZ bytes.
        source_id: The register id, for errors.

    Returns:
        The KML member, decompressed.

    Raises:
        SourceSchemaError: The archive is unreadable, breaks a limit, or does not hold
            exactly one ``.kml`` member.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
    except (zipfile.BadZipFile, OSError, ValueError):
        raise SourceSchemaError(source_id, "the KMZ is not a readable zip archive") from None
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            message = f"the KMZ holds {len(infos)} members, over the limit of {MAX_MEMBERS}"
            raise SourceSchemaError(source_id, message)
        total = 0
        for info in infos:
            _check_member(info, source_id)
            total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            message = f"the KMZ expands to {total} bytes, over {MAX_UNCOMPRESSED_BYTES}"
            raise SourceSchemaError(source_id, message)
        kml = [info for info in infos if info.filename.lower().endswith(".kml")]
        if len(kml) != 1:
            message = f"the KMZ holds {len(kml)} KML members, not one"
            raise SourceSchemaError(source_id, message)
        try:
            data = archive.read(kml[0])
        except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError):
            raise SourceSchemaError(source_id, "the KMZ's KML member is unreadable") from None
    if len(data) != kml[0].file_size:
        raise SourceSchemaError(source_id, "the KMZ's KML member is not the size it states")
    return data


def _check_member(info: zipfile.ZipInfo, source_id: SourceId) -> None:
    name = info.filename
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in name:
        message = "the KMZ holds a member with an absolute or parent-relative name"
        raise SourceSchemaError(source_id, message)
    if info.flag_bits & 1:
        raise SourceSchemaError(source_id, "the KMZ holds an encrypted member")
    if info.file_size > MAX_COMPRESSION_RATIO * max(info.compress_size, 1):
        message = f"a KMZ member is compressed more than {MAX_COMPRESSION_RATIO} to 1"
        raise SourceSchemaError(source_id, message)


class _CellText(HTMLParser):
    """Collects the text of each table cell of a Placemark's description."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: list[str] = []
        self._open = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002 - HTMLParser's signature
        if tag in {"td", "th"}:
            self.cells.append("")
            self._open = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"}:
            self._open = False

    def handle_data(self, data: str) -> None:
        if self._open:
            self.cells[-1] += data


def description_label(description: str, where: str) -> str:
    """Return the text of the single table cell of a Placemark's ``description``.

    Args:
        description: The description's text (HTML inside CDATA).
        where: The Placemark, for errors.

    Returns:
        The cell's text, with its whitespace collapsed.

    Raises:
        SourceSchemaError: The description holds no table cell, or more than one.
    """
    parser = _CellText()
    parser.feed(description)
    parser.close()
    if len(parser.cells) != 1:
        message = f"{where}'s description holds {len(parser.cells)} table cells, not one"
        raise SourceSchemaError(SOURCE, message)
    return " ".join(parser.cells[0].split())


def _positions(text: str, where: str) -> tuple[tuple[float, float], ...]:
    positions: list[tuple[float, float]] = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) not in {2, 3}:
            message = f"{where} has a coordinate that is not lon,lat[,alt]"
            raise SourceSchemaError(SOURCE, message)
        try:
            positions.append((float(parts[0]), float(parts[1])))
        except ValueError:
            message = f"{where} has a coordinate that is not a number"
            raise SourceSchemaError(SOURCE, message) from None
    return tuple(positions)


def _geometry(placemark: XmlElement, namespace: str, where: str) -> Geometry:
    """A Placemark's LineString, or its MultiGeometry's LineStrings; ``lon,lat[,alt]``."""
    multi = children(placemark, "MultiGeometry", namespace)
    lines: list[tuple[tuple[float, float], ...]] = []
    for line in placemark.iter(f"{{{namespace}}}LineString"):
        coordinates = children(line, "coordinates", namespace)
        if len(coordinates) != 1:
            message = f"{where} has a LineString without one coordinates element"
            raise SourceSchemaError(SOURCE, message)
        lines.append(_positions(text_of(coordinates[0]), where))
    if not lines or (not multi and len(lines) != 1):
        raise SourceSchemaError(SOURCE, f"{where} has no single LineString or MultiGeometry")
    with model_errors(SOURCE, f"{where}'s geometry"):
        if multi:
            return Geometry(type="MultiLineString", coordinates=tuple(lines), crs=WGS84)
        return Geometry(type="LineString", coordinates=lines[0], crs=WGS84)


def _extended_data(document: XmlElement, namespace: str) -> Fields:
    values: dict[str, object] = {}
    for extended in children(document, "ExtendedData", namespace):
        for data in children(extended, "Data", namespace):
            name = data.get("name")
            value = children(data, "value", namespace)
            if name is not None and len(value) == 1:
                values[name] = text_of(value[0])
    return Fields(values, FIELDS_READ, source_id=SOURCE, where="the KML's ExtendedData")


def _document(body: bytes) -> tuple[XmlElement, str]:
    root = parse_xml(read_kml(body), SOURCE, "the KMZ's KML")
    namespace = root.tag[1:].partition("}")[0] if root.tag.startswith("{") else ""
    if local_name(root) != "kml" or namespace not in KML_NAMESPACES:
        message = "the KMZ's KML root is not <kml> in a KML 2.2 namespace"
        raise SourceSchemaError(SOURCE, message)
    documents = children(root, "Document", namespace)
    if len(documents) != 1:
        raise SourceSchemaError(SOURCE, "the KML holds no single Document")
    return documents[0], namespace


def _disagreements(  # noqa: PLR0913 - the product's identity and its four statements
    *,
    url: re.Match[str],
    number: AdvisoryNumber,
    atcf_text: str,
    zone: str,
    published_text: str,
    published_at: datetime | None,
    storm: StormSummary | None,
) -> list[str]:
    """Name every way the KML disagrees with its URL, its roster object, or itself."""
    found: list[str] = []
    url_number = AdvisoryNumber.parse(url["advisory"])
    if number != url_number:
        found.append(f"advisoryNum {number} is not the URL's advisory {url_number}")
    if atcf_text.upper() != url["atcf"]:
        found.append(f"atcfid {atcf_text!r} is not the URL's storm {url['atcf']}")
    named = _ZONE_OF_TEXT.search(published_text)
    if named is not None and named["zone"].upper() != zone.upper():
        found.append(f"timezone {zone!r} is not the zone pubAdvTime names ({named['zone']})")
    if published_at is None:
        found.append(f"pubAdvTime {published_text!r} names a zone outside the table")
    if storm is None:
        return found
    if atcf_text.upper() != storm.atcf_id:
        found.append(f"atcfid {atcf_text!r} is not the roster storm {storm.atcf_id}")
    anchor = _roster_product(storm, url["kind"])
    if anchor is None:
        return found
    if anchor.advisory is not None and anchor.advisory != number:
        found.append(f"advisoryNum {number} is not the roster's advNum {anchor.advisory}")
    if published_at is not None and abs(published_at - anchor.issued_at) > ISSUANCE_TOLERANCE:
        found.append(
            f"pubAdvTime is more than an hour from the roster's issuance "
            f"{anchor.issued_at:%Y-%m-%dT%H:%MZ}"
        )
    return found


def _kind(url: re.Match[str]) -> Kind:
    return "earliest_reasonable" if url["kind"] == "earliest_reasonable" else "most_likely"


def _roster_product(storm: StormSummary, kind: str) -> RosterProduct | None:
    return (
        storm.earliest_arrival_kmz
        if kind == "earliest_reasonable"
        else storm.most_likely_arrival_kmz
    )


def _lines(
    document: XmlElement,
    namespace: str,
    *,
    published_at: datetime | None,
    zone: str,
    withheld: str | None,
) -> tuple[ArrivalTimeLine, ...]:
    lines: list[ArrivalTimeLine] = []
    for index, placemark in enumerate(document.iter(f"{{{namespace}}}Placemark")):
        where = f"Placemark {index}"
        if not any(children(placemark, name, namespace) for name in _LINE_GEOMETRIES):
            continue  # a label icon: a Point with no description
        descriptions = children(placemark, "description", namespace)
        if len(descriptions) != 1:
            raise SourceSchemaError(SOURCE, f"{where} has no single description")
        label = description_label(descriptions[0].text or "", where)
        is_outer = " ".join(label.split()).lower() == OUTER_CONTOUR_LABEL.lower()
        geometry = _geometry(placemark, namespace, where)
        with model_errors(SOURCE, where):
            lines.append(
                ArrivalTimeLine.resolve(
                    None if is_outer else label,
                    geometry,
                    origin="kmz",
                    published_at=published_at,
                    time_zone=zone,
                    withheld_reason=withheld,
                )
            )
    if not lines:
        raise SourceSchemaError(SOURCE, "the KML holds no arrival-time line")
    return tuple(lines)


def parse_arrival_kmz(
    body: bytes, provenance: Provenance, storm: StormSummary | None = None
) -> ArrivalTimeProduct:
    """Parse an arrival-time KMZ into a product whose labelled lines carry instants.

    Args:
        body: The KMZ bytes.
        provenance: The answer's provenance; its URL names the storm, advisory, and kind.
        storm: The roster storm that links the KMZ; ``None`` for an archived product,
            which is checked against its URL only.

    Returns:
        The product: each labelled line resolved, or every line unresolved with the reason
        the KML disagrees with its URL, its roster object, or itself.

    Raises:
        SourceSchemaError: The URL is not the pattern, the archive breaks a limit, or the
            KML lacks a key the register lists or a line's label or geometry.
    """
    url = check_url(provenance.url)
    document, namespace = _document(body)
    fields = _extended_data(document, namespace)
    zone, atcf_text = fields.text("timezone"), fields.text("atcfid")
    number_text, published_text = fields.code("advisoryNum"), fields.text("pubAdvTime")
    with model_errors(SOURCE, "the KML's ExtendedData"):
        number = AdvisoryNumber.parse(number_text)
        published_at = parse_nhc_local_time(published_text)
    found = _disagreements(
        url=url,
        number=number,
        atcf_text=atcf_text,
        zone=zone,
        published_text=published_text,
        published_at=published_at,
        storm=storm,
    )
    withheld = "; ".join(found) if found else None
    if withheld is not None:
        warn_drift(SOURCE, f"{url['atcf']} {url['kind']} advisory {url['advisory']}: {withheld}")
    lines = _lines(document, namespace, published_at=published_at, zone=zone, withheld=withheld)
    with model_errors(SOURCE, f"the {url['kind']} product of {url['atcf']}"):
        return ArrivalTimeProduct(
            atcf_id=url["atcf"],
            advisory=Advisory(
                atcf_id=url["atcf"],
                number=AdvisoryNumber.parse(url["advisory"]),
                issued_at=published_at,
                local_text=published_text,
            ),
            provenance=provenance,
            kind=_kind(url),
            time_zone=zone,
            published_at=published_at,
            published_local_text=published_text,
            origin="kmz",
            lines=lines,
            withheld_reason=withheld,
        )


def arrival_links(storm: StormSummary) -> list[tuple[Kind, str]]:
    """List a roster storm's arrival-time links, each checked before anything fetches it.

    Args:
        storm: The roster storm.

    Returns:
        ``(kind, url)`` for each arrival-time object the roster lists with a link.

    Raises:
        SourceSchemaError: A link is outside the pattern or names another storm or kind.
    """
    links: list[tuple[Kind, str]] = []
    for kind in KINDS:
        product = _roster_product(storm, kind)
        if product is not None and product.url is not None:
            check_url(product.url, atcf_id=storm.atcf_id, kind=kind)
            links.append((kind, product.url))
    return links


async def fetch_arrival_times(
    fetcher: Fetcher, storms: Sequence[StormSummary]
) -> SourceResult[tuple[ArrivalTimeProduct, ...]]:
    """Fetch and parse every roster storm's two arrival-time KMZ files.

    Every link is checked before the first request, so one bad link fetches nothing.

    Args:
        fetcher: The run's fetcher.
        storms: The roster's storms; none means no request.

    Returns:
        The products, in roster order (earliest reasonable, then most likely), and the
        answers.
    """
    wanted = [(storm, url) for storm in storms for _, url in arrival_links(storm)]
    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(fetcher.get(url, source_id=SOURCE, max_bytes=MAX_KMZ_BYTES))
            for _, url in wanted
        ]
    results: list[FetchResult] = [task.result() for task in tasks]
    products = tuple(
        parse_arrival_kmz(result.body, result.provenance(), storm)
        for (storm, _), result in zip(wanted, results, strict=True)
    )
    return SourceResult(products, tuple(results))


def prefer_kmz(products: Iterable[ArrivalTimeProduct]) -> tuple[ArrivalTimeProduct, ...]:
    """Apply the snapshot rule: a ``kmz`` product supersedes the ``map_layer`` product.

    A map-layer product is dropped when a KMZ product of the same storm, advisory, and
    kind is present; every other product is kept, in order. Step 6's snapshot service
    applies this rule.

    Args:
        products: Arrival-time products of both origins.

    Returns:
        The products the snapshot keeps.
    """
    products = tuple(products)
    from_kmz = {
        (product.atcf_id, product.advisory.number, product.kind)
        for product in products
        if product.origin == "kmz"
    }
    return tuple(
        product
        for product in products
        if product.origin == "kmz"
        or (product.atcf_id, product.advisory.number, product.kind) not in from_kmz
    )
