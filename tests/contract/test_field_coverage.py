# tests/contract/test_field_coverage.py
"""The field-coverage contract: each parser reads exactly the register's "Fields v2 uses".

``docs/DATA_SOURCES.md`` lists, per layer, the fields v2 uses; each parser declares the
fields it reads (``FIELDS_READ``). For a typed layer the two must be equal, and deleting
any field read from a recorded feature must fail the parse with ``SourceSchemaError``. A
display layer is kept as received, so every field the register lists for it must be in
every recorded feature, because the map will read it. An empty recorded layer is checked
against its catalog schema instead. The roster gets the same two checks.
"""

import copy
import json
from collections.abc import Iterator, Mapping
from datetime import datetime
from functools import cache
from typing import NamedTuple

import pytest
from fixture_support import (
    FEATURE_GEOMETRIES,
    CaptureDirectory,
    as_list,
    as_object,
    latest_live,
    layer_fields,
    register_layers,
    register_roster_fields,
)

from weatherbot.models import Provenance, SourceId, StormSummary
from weatherbot.sources import nhc_current_storms, nhc_map
from weatherbot.sources.errors import SourceSchemaError

SERVICES: Mapping[SourceId, str] = {
    "nhc-map-tropical-weather": "NHC_tropical_weather",
    "nhc-map-tropical-summary": "NHC_tropical_weather_summary",
    "nhc-map-breakpoints": "NHC_Breakpoints",
    "nhc-map-peak-surge": "NHC_PeakStormSurge",
}
SLOT_PREFIX = "{slot} "
LAYER_NOTE_PREFIX = "layer '"


def _directory(source: str) -> CaptureDirectory:
    directory = latest_live(source)
    assert directory is not None, f"{source} has no live capture"
    return directory


def _provenance(directory: CaptureDirectory, item: Mapping[str, object]) -> Provenance:
    return Provenance(
        source_id=directory.source,  # pyright: ignore[reportArgumentType] - a register id
        url=str(item["url"]),
        status=int(str(item["status"])),
        fetched_at=datetime.fromisoformat(str(item["fetched_at"])),
        sha256=str(item["sha256"]),
    )


@cache
def _roster() -> dict[str, object]:
    directory = _directory("nhc-current-storms")
    (item,) = directory.entries
    return as_object(json.loads(directory.payload(item)))


def _storms() -> tuple[StormSummary, ...]:
    directory = _directory("nhc-current-storms")
    (item,) = directory.entries
    return nhc_current_storms.parse_current_storms(
        json.dumps(_roster()).encode(), _provenance(directory, item)
    )


class Capture(NamedTuple):
    """One recorded layer query."""

    source: SourceId
    layer: str
    file: str

    @property
    def base(self) -> str:
        """The layer's name without its slot."""
        return nhc_map.base_layer_name(self.layer)

    def __str__(self) -> str:
        """The test id."""
        return f"{self.source}:{self.layer}"


def _layer_of(item: Mapping[str, object]) -> str | None:
    note = str(item.get("notes", ""))
    if not note.startswith(LAYER_NOTE_PREFIX) or not str(item["file"]).startswith("query-"):
        return None
    return note[len(LAYER_NOTE_PREFIX) :].rsplit("', id ", 1)[0]


def _captures() -> Iterator[Capture]:
    for source in SERVICES:
        for item in _directory(source).entries:
            layer = _layer_of(item)
            if layer is not None:
                yield Capture(source, layer, str(item["file"]))


@cache
def _document(capture: Capture) -> dict[str, object]:
    directory = _directory(capture.source)
    item = next(entry for entry in directory.entries if entry["file"] == capture.file)
    return as_object(json.loads(directory.payload(item)))


def _features(capture: Capture) -> list[object]:
    return as_list(_document(capture)["features"])


def _parse(capture: Capture, collection: Mapping[str, object]) -> object:
    directory = _directory(capture.source)
    item = next(entry for entry in directory.entries if entry["file"] == capture.file)
    return nhc_map.parse_layer(capture.layer, collection, _provenance(directory, item), _storms())


CAPTURES = list(_captures())
TYPED = [c for c in CAPTURES if c.base in nhc_map.FIELDS_READ]
DISPLAY = [c for c in CAPTURES if c.base in nhc_map.DISPLAY_LAYERS]
DELETIONS = [
    (capture, field)
    for capture in TYPED
    if _features(capture)
    for field in sorted(nhc_map.FIELDS_READ[capture.base])
]
REGISTER_ROWS = [
    (source, name, fields)
    for source, service in SERVICES.items()
    for name, fields in layer_fields(service).items()
]
FEATURE_ROWS = {
    (source, layer.name)
    for source, service in SERVICES.items()
    for layer in register_layers(service)
    if layer.geometry in FEATURE_GEOMETRIES
}


@pytest.mark.parametrize(
    ("source", "name", "fields"),
    [row for row in REGISTER_ROWS if (row[0], row[1]) in FEATURE_ROWS],
    ids=[f"{s}:{n}" for s, n, _ in REGISTER_ROWS if (s, n) in FEATURE_ROWS],
)
def test_each_typed_parser_reads_exactly_the_registers_fields(
    source: str, name: str, fields: Mapping[str, frozenset[str]]
) -> None:
    base = name.removeprefix(SLOT_PREFIX)
    assert fields["used"] <= fields["present"], f"{source}: {name} uses a field it lacks"
    if base in nhc_map.FIELDS_READ:
        assert nhc_map.FIELDS_READ[base] == fields["used"], f"{source}: {name}"
    elif base not in nhc_map.DISPLAY_LAYERS:
        # Not used in 2.0, counted, or read by doctor only: the register lists no field.
        assert fields["used"] == frozenset(), f"{source}: {name} has fields but no parser"


def test_every_parsed_layer_is_a_register_layer() -> None:
    registered = {name.removeprefix(SLOT_PREFIX) for _, name in FEATURE_ROWS}
    assert set(nhc_map.FIELDS_READ) <= registered
    assert registered >= nhc_map.DISPLAY_LAYERS
    assert nhc_map.FIELDS_READ[nhc_map.FORECAST_CONE] >= nhc_map.CONE_ADVISORIES_READ


@pytest.mark.parametrize(("capture", "field"), DELETIONS, ids=[f"{c}:{f}" for c, f in DELETIONS])
def test_deleting_a_field_read_fails_the_parse(capture: Capture, field: str) -> None:
    collection = copy.deepcopy(_document(capture))
    first = as_object(as_list(collection["features"])[0])
    del as_object(first["properties"])[field]
    with pytest.raises(SourceSchemaError, match=field):
        _parse(capture, collection)


@pytest.mark.parametrize("capture", TYPED, ids=str)
def test_every_typed_capture_parses(capture: Capture) -> None:
    _parse(capture, _document(capture))


def _register_fields(capture: Capture) -> frozenset[str]:
    rows = layer_fields(SERVICES[capture.source])
    name = next((n for n in rows if n.removeprefix(SLOT_PREFIX) == capture.base), capture.layer)
    return rows[name]["used"]


@pytest.mark.parametrize("capture", [c for c in DISPLAY if _features(c)], ids=str)
def test_display_layers_carry_every_register_field(capture: Capture) -> None:
    wanted = _register_fields(capture)
    assert wanted, f"{capture}: the register lists no field for a populated display layer"
    for feature in _features(capture):
        properties = as_object(as_object(feature)["properties"])
        assert wanted <= set(properties), f"{capture}: a feature lacks {wanted - set(properties)}"


def _schema_fields(capture: Capture) -> set[str]:
    directory = _directory(capture.source)
    item = next(e for e in directory.entries if str(e["file"]).startswith("layers.json"))
    layers = as_list(as_object(json.loads(directory.payload(item)))["layers"])
    layer = next(as_object(row) for row in layers if as_object(row)["name"] == capture.layer)
    return {str(as_object(field)["name"]) for field in as_list(layer["fields"])}


@pytest.mark.parametrize("capture", [c for c in (*TYPED, *DISPLAY) if not _features(c)], ids=str)
def test_empty_layers_carry_their_fields_in_the_catalog_schema(capture: Capture) -> None:
    wanted = nhc_map.FIELDS_READ.get(capture.base, _register_fields(capture))
    assert wanted <= _schema_fields(capture), f"{capture}: the schema lacks a field v2 reads"


def test_the_roster_parser_reads_exactly_the_registers_fields() -> None:
    assert register_roster_fields() == nhc_current_storms.FIELDS_READ


@pytest.mark.parametrize("field", sorted(nhc_current_storms.FIELDS_READ))
def test_deleting_a_roster_field_read_fails_the_parse(field: str) -> None:
    document = copy.deepcopy(_roster())
    storm = as_object(as_list(document["activeStorms"])[0])
    *parents, name = field.split(".")
    for parent in parents:
        storm = as_object(storm[parent])
    del storm[name]
    directory = _directory("nhc-current-storms")
    (item,) = directory.entries
    with pytest.raises(SourceSchemaError, match=name):
        nhc_current_storms.parse_current_storms(
            json.dumps(document).encode(), _provenance(directory, item)
        )
