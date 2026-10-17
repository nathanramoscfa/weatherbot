# src/weatherbot/sources/nhc_text_products.py
"""NHC text products from the NWS API (register source ``nhc-text-products``).

The register reads the TCP (public advisory) by storm slot and the TWO (outlook) by
basin from ``api.weather.gov``, not from NHC's HTML pages. A client lists
``/products/types/{TCP,TWO}/locations/{location}``, takes the newest product id, checks it
against ``PRODUCT_ID_PATTERN``, and fetches ``/products/{id}``. Only the English TWO
basins are asked for (``AT``, ``EP``, ``CP``); ``SAT``, ``SEP``, and ``SCP`` are Spanish.

Later storms of a season reuse a slot, so a TCP's header names its storm's ATCF id. A TCP
whose header names another storm than the roster's storm in that slot is not attributed
to the storm: it is logged as Source drift and left out, never raised. The advisory number
in the TCP's text (``ADVISORY NUMBER 22A``) is the product's own and is compared with the
roster's ``publicAdvisory.advNum``; an older product keeps its number. Every request goes
to ``api.weather.gov`` through the run's fetcher, which paces that host 1.2 seconds apart
for this client and the NWS clients alike.
"""

import asyncio
import re
from collections.abc import Sequence
from datetime import datetime
from typing import Final, Literal

from weatherbot.models import AdvisoryNumber, Provenance, SourceId, StormSummary, TextProduct
from weatherbot.sources.drift import warn_drift
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.fields import Fields, as_mapping, as_sequence, model_errors, parse_document
from weatherbot.sources.http import Fetcher, FetchResult, SourceResult

SOURCE: Final[SourceId] = "nhc-text-products"
API_ROOT: Final = "https://api.weather.gov"
TWO_BASINS: Final = ("AT", "EP", "CP")
"""The English TWO locations; the Spanish editions (``SAT``, ``SEP``, ``SCP``) are not read."""

PRODUCT_ID_PATTERN: Final = re.compile(r"[0-9A-Za-z-]{8,64}")
"""A product id the client follows; the fixture recorder imports this pattern."""

FIELDS_READ: Final = frozenset(
    {"id", "issuanceTime", "wmoCollectiveId", "issuingOffice", "productText"}
)
"""The product keys the parser reads: the register's "Fields v2 uses"."""
LIST_FIELDS_READ: Final = frozenset({"id", "issuanceTime"})
"""The keys read from each ``@graph`` item of a list: the register's "List fields v2 uses"."""

MAX_TEXT_BYTES: Final = 2 * 1024 * 1024

type Code = Literal["TCP", "TWO"]

_HEADER_ATCF: Final = re.compile(
    r"^NWS .*Hurricane Center.*?\s(?P<atcf>(?:AL|EP|CP)\d{6})\s*$", re.MULTILINE
)
_ADVISORY: Final = re.compile(r"\bADVISORY NUMBER\s+(?P<number>\d{1,3}[A-Z]?)\b", re.IGNORECASE)
_WMO_LINE: Final = re.compile(r"^[A-Z]{4}\d{2} [A-Z]{4} (?P<stamp>\d{6})\b", re.MULTILINE)


def list_url(code: Code, location: str) -> str:
    """Return the product list URL of a code and location.

    Args:
        code: ``TCP`` or ``TWO``.
        location: A slot (``EP5``) for a TCP, a basin (``AT``) for a TWO.

    Returns:
        The URL.
    """
    return f"{API_ROOT}/products/types/{code}/locations/{location}"


def newest_product_id(body: bytes, source_id: SourceId, what: str) -> str | None:
    """Return the id of the newest product a list names.

    Args:
        body: The list payload.
        source_id: The register id, for errors.
        what: The list, for errors.

    Returns:
        The id of the item with the latest ``issuanceTime``, or ``None`` for an empty list.

    Raises:
        SourceSchemaError: The list lacks ``@graph``, an item lacks a key, or the newest id
            is not ``PRODUCT_ID_PATTERN``.
    """
    document = as_mapping(parse_document(body, source_id, what), source_id, what)
    graph = as_sequence(document.get("@graph"), source_id, f"{what}'s @graph")
    dated: list[tuple[datetime, str]] = []
    for index, item in enumerate(graph):
        fields = Fields(
            as_mapping(item, source_id, f"{what} item {index}"),
            LIST_FIELDS_READ,
            source_id=source_id,
            where=f"{what} item {index}",
        )
        dated.append((_instant(fields, "issuanceTime"), fields.text("id")))
    if not dated:
        return None
    identifier = max(dated)[1]
    if not PRODUCT_ID_PATTERN.fullmatch(identifier):
        raise SourceSchemaError(source_id, f"{what}: the newest product has an unexpected id")
    return identifier


def _instant(fields: Fields, name: str) -> datetime:
    try:
        return datetime.fromisoformat(fields.text(name))
    except ValueError:
        message = f"{fields.where}: {name!r} is not an ISO 8601 instant"
        raise SourceSchemaError(fields.source_id, message) from None


def parse_text_product(
    body: bytes, provenance: Provenance, *, code: Code, location: str
) -> TextProduct:
    """Parse ``/products/{id}`` into a ``TextProduct``.

    A TCP's ATCF id comes from its header line and its advisory from ``ADVISORY NUMBER``;
    a TWO names neither.

    Args:
        body: The product payload.
        provenance: The answer's provenance.
        code: ``TCP`` or ``TWO``.
        location: The slot or basin it was listed under.

    Returns:
        The product.

    Raises:
        SourceSchemaError: A key the register lists is missing, or a TCP names no storm or
            advisory.
    """
    source = provenance.source_id
    what = f"the {code} product for {location}"
    fields = Fields(
        as_mapping(parse_document(body, source, what), source, what),
        FIELDS_READ,
        source_id=source,
        where=what,
    )
    text = fields.text("productText")
    issued_at = _instant(fields, "issuanceTime")
    atcf_id: str | None = None
    advisory: AdvisoryNumber | None = None
    if code == "TCP":
        header, number = _HEADER_ATCF.search(text), _ADVISORY.search(text)
        if header is None or number is None:
            raise SourceSchemaError(source, f"{what} names no ATCF id or advisory number")
        atcf_id = header["atcf"]
        with model_errors(source, what):
            advisory = AdvisoryNumber.parse(number["number"])
    _check_wmo_line(text, issued_at, what)
    with model_errors(source, what):
        return TextProduct(
            product_id=fields.text("id"),
            code=code,
            location=location,
            wmo_collective_id=fields.text("wmoCollectiveId"),
            issuing_office=fields.text("issuingOffice"),
            issued_at=issued_at,
            text=text,
            atcf_id=atcf_id,
            advisory=advisory,
            provenance=provenance,
        )


def _check_wmo_line(text: str, issued_at: datetime, what: str) -> None:
    """Warn when the WMO line's ``DDHHMM`` is not ``issuanceTime`` (the register: they match)."""
    line = _WMO_LINE.search(text)
    if line is not None and line["stamp"] != f"{issued_at:%d%H%M}":
        warn_drift(SOURCE, f"{what}: the WMO line's time is not issuanceTime")


async def _newest(
    fetcher: Fetcher, code: Code, location: str
) -> tuple[TextProduct | None, tuple[FetchResult, ...]]:
    listing = await fetcher.get(list_url(code, location), source_id=SOURCE)
    what = f"the {code} list for {location}"
    identifier = newest_product_id(listing.body, SOURCE, what)
    if identifier is None:
        return None, (listing,)
    result = await fetcher.get(
        f"{API_ROOT}/products/{identifier}", source_id=SOURCE, max_bytes=MAX_TEXT_BYTES
    )
    product = parse_text_product(result.body, result.provenance(), code=code, location=location)
    return product, (listing, result)


def attribute_tcp(product: TextProduct, storm: StormSummary) -> TextProduct | None:
    """Attribute a slot's TCP to the roster's storm in that slot, or decline to.

    Args:
        product: The newest TCP of the storm's slot.
        storm: The roster's storm in that slot.

    Returns:
        The product when its header names the storm; ``None`` for a reused slot's TCP of
        another storm, which is logged as Source drift.
    """
    if product.atcf_id != storm.atcf_id:
        warn_drift(
            SOURCE,
            f"the newest TCP in slot {storm.slot} names {product.atcf_id}, not the roster's "
            f"{storm.atcf_id}; it is not attributed",
        )
        return None
    if product.advisory != storm.public_advisory.advisory:
        warn_drift(
            SOURCE,
            f"{storm.atcf_id}'s newest TCP is advisory {product.advisory}, the roster's "
            f"public advisory {storm.public_advisory.advisory}; the TCP keeps its own number",
        )
    return product


async def fetch_tcps(
    fetcher: Fetcher, storms: Sequence[StormSummary]
) -> SourceResult[tuple[TextProduct, ...]]:
    """Fetch the newest TCP of each roster storm's slot.

    Args:
        fetcher: The run's fetcher.
        storms: The roster's storms; none means no request.

    Returns:
        The TCPs attributed to their storms, in roster order, and every answer.
    """
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(_newest(fetcher, "TCP", storm.slot)) for storm in storms]
    products: list[TextProduct] = []
    responses: list[FetchResult] = []
    for storm, task in zip(storms, tasks, strict=True):
        product, answers = task.result()
        responses.extend(answers)
        attributed = attribute_tcp(product, storm) if product is not None else None
        if attributed is not None:
            products.append(attributed)
    return SourceResult(tuple(products), tuple(responses))


async def fetch_twos(fetcher: Fetcher) -> SourceResult[tuple[TextProduct, ...]]:
    """Fetch the newest English TWO of each basin.

    Args:
        fetcher: The run's fetcher.

    Returns:
        One TWO per basin whose list is not empty, and every answer.
    """
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(_newest(fetcher, "TWO", basin)) for basin in TWO_BASINS]
    products: list[TextProduct] = []
    responses: list[FetchResult] = []
    for task in tasks:
        product, answers = task.result()
        responses.extend(answers)
        if product is not None:
            products.append(product)
    return SourceResult(tuple(products), tuple(responses))
