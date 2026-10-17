# tests/contract/test_product_captures.py
"""Contract tests: every recorded capture of the NHC product and display sources parses.

The sources are ``nhc-arrival-times``, ``nhc-text-products``, ``nhc-outlook-graphics``,
``nhc-gis-rss``, ``nhc-map-surge-risk``, ``overlay-radar``, and ``overlay-satellite``.
Where the register lists the fields v2 uses (text-product keys, RSS item fields, and the
arrival-time KML's ``ExtendedData`` keys), the parser's ``FIELDS_READ`` must equal the list,
and deleting any one of them from a recorded capture must fail the parse with a
``SourceSchemaError`` that names it (the field-coverage rule of
``test_field_coverage.py``). The archived arrival-time pair must be the replay corpus's
bytes, and each roster-linked pair must agree with the roster the recorder read.
"""

import copy
import io
import json
import re
import zipfile
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import cast

import pytest
from fixture_support import (
    REPOSITORY_ROOT,
    CaptureDirectory,
    as_list,
    as_object,
    capture_directories,
    latest_live,
    register_section_fields,
)

import record_fixtures as recorder
from weatherbot.models import AdvisoryNumber, Provenance, SourceId
from weatherbot.sources import catalogs, nhc_arrival_times, nhc_gis_rss, nhc_outlook_graphics
from weatherbot.sources import nhc_text_products as text_products
from weatherbot.sources.arcgis import SURGE_RISK, parse_catalog
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.http import FetchResult

CORPUS_MANIFEST = REPOSITORY_ROOT / "tests" / "fixtures" / "replay" / "corpus-manifest.json"
ROSTER_NOTE = re.compile(r"roster: (?P<atcf>\S+) \S+ advNum (?P<adv>\S+), issuance (?P<at>\S+)")
SOURCES: tuple[SourceId, ...] = (
    "nhc-arrival-times",
    "nhc-text-products",
    "nhc-outlook-graphics",
    "nhc-gis-rss",
    "nhc-map-surge-risk",
    "overlay-radar",
    "overlay-satellite",
)
OVERLAYS = {service.source_id: service for service in catalogs.OVERLAYS}
TEXT_FILE = re.compile(r"(?P<code>tcp|two)-(?P<location>[a-z0-9]+)-(?P<kind>list|product)\.json")


def _captures(source: str) -> list[tuple[CaptureDirectory, dict[str, object]]]:
    return [
        (directory, item)
        for directory in capture_directories()
        if directory.source == source
        for item in directory.entries
    ]


CAPTURES = [capture for source in SOURCES for capture in _captures(source)]


def _label(capture: tuple[CaptureDirectory, dict[str, object]]) -> str:
    return f"{capture[0].label}/{capture[1]['file']}"


def _provenance(directory: CaptureDirectory, item: Mapping[str, object]) -> Provenance:
    return Provenance(
        source_id=cast("SourceId", directory.source),
        url=str(item["url"]),
        status=int(str(item["status"])),
        fetched_at=datetime.fromisoformat(str(item["fetched_at"])),
        sha256=str(item["sha256"]),
    )


def _text(provenance: Provenance, name: str, body: bytes) -> object:
    found = TEXT_FILE.fullmatch(name)
    assert found is not None, name
    if found["kind"] == "list":
        return text_products.newest_product_id(body, provenance.source_id, name)
    code = "TCP" if found["code"] == "tcp" else "TWO"
    return text_products.parse_text_product(
        body, provenance, code=code, location=found["location"].upper()
    )


def _surge_risk(provenance: Provenance, name: str, body: bytes) -> object:
    if name != "catalog.json":
        return None  # the layer schemas are read by doctor and the register tests
    result = FetchResult(
        source_id=provenance.source_id,
        url=provenance.url,
        status=provenance.status,
        body=body,
        headers={},
        fetched_at=provenance.fetched_at,
        sha256=provenance.sha256,
    )
    return catalogs.surge_risk_images(parse_catalog(result, SURGE_RISK))


def _overlay(provenance: Provenance, _name: str, body: bytes) -> object:
    return catalogs.parse_capabilities(body, provenance, OVERLAYS[provenance.source_id])


PARSERS: Mapping[str, Callable[[Provenance, str, bytes], object]] = {
    "nhc-arrival-times": lambda p, _, body: nhc_arrival_times.parse_arrival_kmz(body, p),
    "nhc-text-products": _text,
    "nhc-outlook-graphics": lambda p, _, body: nhc_outlook_graphics.parse_outlook_graphic(body, p),
    "nhc-gis-rss": lambda p, _, body: nhc_gis_rss.parse_gis_feed(body, p),
    "nhc-map-surge-risk": _surge_risk,
    "overlay-radar": _overlay,
    "overlay-satellite": _overlay,
}


def _parse(directory: CaptureDirectory, item: dict[str, object], body: bytes) -> object:
    """Parse one capture with its source's client; a list or a layer schema is skipped."""
    name = str(item["file"]).removesuffix(".gz")
    return PARSERS[directory.source](_provenance(directory, item), name, body)


@pytest.mark.parametrize("source", SOURCES)
def test_every_source_has_a_recorded_capture(source: str) -> None:
    assert _captures(source), f"{source} has no recorded capture"


@pytest.mark.parametrize("capture", CAPTURES, ids=[_label(c) for c in CAPTURES])
def test_every_recorded_capture_parses(capture: tuple[CaptureDirectory, dict[str, object]]) -> None:
    directory, item = capture
    _parse(directory, item, directory.payload(item))


# The field-coverage rule ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "label", "declared"),
    [
        ("Text products", "Fields v2 uses", text_products.FIELDS_READ),
        ("Text products", "List fields v2 uses", text_products.LIST_FIELDS_READ),
        ("GIS RSS feeds", "Fields v2 uses", nhc_gis_rss.FIELDS_READ),
        ("Arrival-time KMZ", "Fields v2 uses", nhc_arrival_times.FIELDS_READ),
    ],
    ids=["text-product", "text-list", "gis-rss", "arrival-extended-data"],
)
def test_each_parser_reads_exactly_the_registers_fields(
    heading: str, label: str, declared: frozenset[str]
) -> None:
    assert register_section_fields(heading, label) == declared


def _text_captures(kind: str) -> list[tuple[CaptureDirectory, dict[str, object]]]:
    return [
        (directory, item)
        for directory, item in _captures("nhc-text-products")
        if (found := TEXT_FILE.fullmatch(str(item["file"]))) and found["kind"] == kind
    ]


TEXT_DELETIONS = [
    (capture, field)
    for capture in _text_captures("product")
    for field in sorted(text_products.FIELDS_READ)
]
LIST_DELETIONS = [
    (capture, field)
    for capture in _text_captures("list")
    if as_list(as_object(json.loads(capture[0].payload(capture[1])))["@graph"])
    for field in sorted(text_products.LIST_FIELDS_READ)
]


@pytest.mark.parametrize(
    ("capture", "field"), TEXT_DELETIONS, ids=[f"{_label(c)}:{f}" for c, f in TEXT_DELETIONS]
)
def test_deleting_a_text_product_key_fails_the_parse(
    capture: tuple[CaptureDirectory, dict[str, object]], field: str
) -> None:
    directory, item = capture
    document = as_object(json.loads(directory.payload(item)))
    del document[field]
    with pytest.raises(SourceSchemaError, match=field):
        _parse(directory, item, json.dumps(document).encode())


@pytest.mark.parametrize(
    ("capture", "field"), LIST_DELETIONS, ids=[f"{_label(c)}:{f}" for c, f in LIST_DELETIONS]
)
def test_deleting_a_list_key_fails_the_parse(
    capture: tuple[CaptureDirectory, dict[str, object]], field: str
) -> None:
    directory, item = capture
    document = copy.deepcopy(as_object(json.loads(directory.payload(item))))
    del as_object(as_list(document["@graph"])[0])[field]
    with pytest.raises(SourceSchemaError, match=field):
        _parse(directory, item, json.dumps(document).encode())


def _rss_storm_item() -> tuple[CaptureDirectory, dict[str, object]]:
    """The newest recorded feed item that carries ``nhc:Cyclone``."""
    found = [
        (directory, item)
        for directory, item in _captures("nhc-gis-rss")
        if b"<nhc:Cyclone>" in directory.payload(item)
    ]
    assert found, "no recorded feed has a storm's nhc:Cyclone"
    return found[-1]


def _without_element(body: bytes, field: str) -> bytes:
    """Remove the first item's element for a field (``nhc:Cyclone.atcf`` → ``nhc:atcf``)."""
    tag = f"nhc:{field.rpartition('.')[2]}" if field.startswith("nhc:") else field
    start = body.index(b"<item>")
    found = re.compile(rf"<{tag}[\s>].*?</{tag}>".encode(), re.DOTALL).search(body, start)
    assert found is not None, field
    return body[: found.start()] + body[found.end() :]


@pytest.mark.parametrize("field", sorted(nhc_gis_rss.FIELDS_READ))
def test_deleting_a_feed_field_fails_the_parse(field: str) -> None:
    directory, item = _rss_storm_item()
    body = _without_element(directory.payload(item), field)
    with pytest.raises(SourceSchemaError, match=re.escape(field)):
        _parse(directory, item, body)


def _without_data(body: bytes, field: str) -> bytes:
    """Rebuild a KMZ whose KML lacks one ``ExtendedData`` key."""
    source = zipfile.ZipFile(io.BytesIO(body))
    output = io.BytesIO()
    with source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info)
            if info.filename.endswith(".kml"):
                data = re.sub(
                    rf'<Data name="{field}">.*?</Data>'.encode(),
                    b"",
                    data,
                    count=1,
                    flags=re.DOTALL,
                )
            target.writestr(info.filename, data)
    return output.getvalue()


ARRIVAL_DELETIONS = [
    (capture, field)
    for capture in _captures("nhc-arrival-times")
    for field in sorted(nhc_arrival_times.FIELDS_READ)
]


@pytest.mark.parametrize(
    ("capture", "field"),
    ARRIVAL_DELETIONS,
    ids=[f"{_label(c)}:{f}" for c, f in ARRIVAL_DELETIONS],
)
def test_deleting_an_extended_data_key_fails_the_parse(
    capture: tuple[CaptureDirectory, dict[str, object]], field: str
) -> None:
    directory, item = capture
    body = _without_data(directory.payload(item), field)
    with pytest.raises(SourceSchemaError, match=field):
        _parse(directory, item, body)


# The arrival-time captures ----------------------------------------------------------------


def test_the_archived_pair_is_the_replay_corpus_pinned_bytes() -> None:
    directory = latest_live("nhc-arrival-times")
    assert directory is not None
    pinned = {
        str(entry["url"]): str(entry["sha256"])
        for entry in (
            as_object(e) for e in as_list(json.loads(CORPUS_MANIFEST.read_bytes())["files"])
        )
    }
    recorded = {str(item["url"]): str(item["sha256"]) for item in directory.entries}
    assert set(recorder.ARCHIVED_ARRIVAL_PAIR) <= set(recorded)
    for url in recorder.ARCHIVED_ARRIVAL_PAIR:
        assert recorded[url] == pinned[url], url


@pytest.mark.parametrize(
    "capture",
    _captures("nhc-arrival-times"),
    ids=[_label(c) for c in _captures("nhc-arrival-times")],
)
def test_every_recorded_arrival_product_resolves_and_agrees_with_its_roster(
    capture: tuple[CaptureDirectory, dict[str, object]],
) -> None:
    directory, item = capture
    product = nhc_arrival_times.parse_arrival_kmz(
        directory.payload(item), _provenance(directory, item)
    )
    assert product.withheld_reason is None
    assert product.published_at is not None
    assert all(line.valid_at for line in product.lines if not line.is_outer_contour)
    assert sum(line.is_outer_contour for line in product.lines) == 1
    note = ROSTER_NOTE.fullmatch(str(item["notes"]))
    if item["url"] in recorder.ARCHIVED_ARRIVAL_PAIR:
        assert note is None
        return
    assert note is not None, "a roster-linked capture names the roster's advNum and issuance"
    assert note["atcf"] == product.atcf_id
    assert AdvisoryNumber.parse(note["adv"]) == product.advisory.number
    issued = datetime.fromisoformat(note["at"])
    assert abs(product.published_at - issued) <= timedelta(hours=1)
