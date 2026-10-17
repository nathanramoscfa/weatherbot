# tests/contract/test_register.py
"""Contract tests that keep the register, the recorder, and the recorded catalogs in agreement.

``docs/DATA_SOURCES.md`` names every source and every ArcGIS layer; ``scripts/record_fixtures.py``
records them; ``tests/fixtures/recorded/`` holds what NOAA answered. A layer that moves, a
source that gains a row, or a recorder that drifts from the register fails here, in the pull
request that causes it (the register's "Re-verifying" section).
"""

import json
import re

import pytest
from fixture_support import (
    CATALOG_GEOMETRY,
    CATALOG_KINDS,
    FEATURE_GEOMETRIES,
    CaptureDirectory,
    RegisterLayer,
    as_list,
    as_object,
    capture_directories,
    latest_live,
    register_layers,
    register_rows,
    register_text,
    register_user_agent,
)

import record_fixtures as recorder
from weatherbot import __version__, sources
from weatherbot.sources import arcgis, http

PATH_SEPARATOR = " / "
EN_DASH = chr(0x2013)  # the register writes a range with an en dash
CATEGORIES = re.compile(rf"Categories (\d){EN_DASH}(\d)")
STATUS_OK = 200
SLOTS_PER_BASIN = 5
BASIN_COUNT = 3
SERVICES = list(recorder.MAP_SERVICES.values())
CATALOG_FILES = {"catalog.json", "layers.json", "layers.json.gz"}


def test_the_register_ids_are_the_recorder_sources_plus_the_rows_that_are_not_required() -> None:
    rows = register_rows()
    ids = [row.source_id for row in rows]
    assert len(set(ids)) == len(ids), "a source id appears twice in the register"
    required = {row.source_id for row in rows if row.required}
    others = {row.source_id for row in rows if not row.required}
    assert set(recorder.SOURCES) == required
    assert set(ids) == set(recorder.SOURCES) | others
    for row in rows:
        assert row.required or row.fixture == "replay-corpus" or row.fixture.startswith("none"), (
            f"{row.source_id}: the Fixture cell is {row.fixture!r}"
        )


def test_the_recorder_lists_the_sources_in_register_order() -> None:
    required = [row.source_id for row in register_rows() if row.required]
    assert list(recorder.SOURCES) == required


@pytest.mark.parametrize("source", sorted(recorder.SOURCES))
def test_every_required_source_has_a_capture_with_status_200(source: str) -> None:
    directories = [item for item in capture_directories() if item.source == source]
    assert directories, f"{source} has no capture directory"
    assert any(entry["status"] == STATUS_OK for item in directories for entry in item.entries), (
        f"{source} has no capture with status 200"
    )


def test_the_package_user_agent_is_the_registers() -> None:
    assert register_user_agent() == sources.USER_AGENT
    # The version part follows the package version (the register's "User-Agent").
    expected = f"weatherbot/{__version__} (+https://github.com/nathanramoscfa/weatherbot)"
    assert expected == sources.USER_AGENT


def test_the_recorder_imports_the_packages_register_constants() -> None:
    # One definition each: the recorder uses the package's objects, not copies.
    assert recorder.USER_AGENT is sources.USER_AGENT
    assert recorder.HOST_INTERVALS is http.HOST_INTERVALS
    assert recorder.QUERY_PARAMETERS is arcgis.QUERY_PARAMETERS
    assert recorder.COUNT_PARAMETERS is arcgis.COUNT_PARAMETERS
    assert recorder.HEADER_ALLOWLIST is http.HEADER_ALLOWLIST


def test_the_register_shares_the_recorders_arcgis_query_parameters() -> None:
    text = register_text()
    for name, value in recorder.QUERY_PARAMETERS.items():
        assert re.search(rf"\| `{name}` \| `{re.escape(value)}` \|", text), f"{name}={value}"


def _catalog_layers(directory: CaptureDirectory) -> list[dict[str, object]]:
    entry = next(item for item in directory.entries if item["file"] == "catalog.json")
    catalog = as_object(json.loads(directory.payload(entry)))
    return [as_object(layer) for layer in as_list(catalog["layers"])]


def _paths(layers: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Index the layers by their group path from the service root, joined with ``" / "``."""
    by_id = {int(str(layer["id"])): layer for layer in layers}
    paths: dict[str, dict[str, object]] = {}
    for layer in layers:
        names = [str(layer["name"])]
        parent = int(str(layer["parentLayerId"]))
        while parent != -1:
            names.append(str(by_id[parent]["name"]))
            parent = int(str(by_id[parent]["parentLayerId"]))
        paths[PATH_SEPARATOR.join(reversed(names))] = layer
    return paths


def _geometry(layer: dict[str, object]) -> str:
    kind = str(layer["type"])
    return CATALOG_KINDS.get(kind) or CATALOG_GEOMETRY[str(layer["geometryType"])]


def _expand(layers: list[RegisterLayer], slots: list[str]) -> list[tuple[RegisterLayer, str]]:
    """Expand ``{slot}`` over the slots and ``{n}`` over the categories the region's row lists."""
    categories = {
        layer.name: range(int(found[1]), int(found[2]) + 1)
        for layer in layers
        if (found := CATEGORIES.search(layer.notes))
    }
    expanded: list[tuple[RegisterLayer, str]] = []
    for layer in layers:
        if "{slot}" in layer.name:
            expanded.extend((layer, layer.name.replace("{slot}", slot)) for slot in slots)
        elif "{n}" in layer.name:
            region = layer.name.split(f"{PATH_SEPARATOR}Category {{n}}")[0]
            expanded.extend((layer, layer.name.replace("{n}", str(n))) for n in categories[region])
        else:
            expanded.append((layer, layer.name))
    return expanded


@pytest.mark.parametrize("service", SERVICES, ids=lambda service: service.source_id)
def test_every_register_layer_exists_in_the_recorded_catalog(service: recorder.MapService) -> None:
    directory = latest_live(service.source_id)
    assert directory is not None, f"{service.source_id} has no live capture"
    layers = _catalog_layers(directory)
    registered = register_layers(service.service)
    assert registered, f"the register has no layer table for {service.service}"
    by_path = _paths(layers)
    if any(PATH_SEPARATOR in layer.name for layer in registered):
        # StormSurgeRisk repeats its layer names, so the register names them by group path.
        found = by_path
    else:
        # Every other service names its layers uniquely, which is what resolving by name needs.
        names = [str(layer["name"]) for layer in layers]
        assert len(set(names)) == len(names), f"{service.service} repeats a layer name"
        found = {str(layer["name"]): layer for layer in layers}
    slots = sorted(
        str(layer["name"])
        for layer in layers
        if recorder.SLOT_PATTERN.fullmatch(str(layer["name"]))
    )
    if service.slot_layers or any("{slot}" in layer.name for layer in registered):
        assert len(slots) == SLOTS_PER_BASIN * BASIN_COUNT
    for layer, name in _expand(registered, slots):
        assert name in found, f"{service.service}: the catalog lacks the register's layer {name!r}"
        assert _geometry(found[name]) == layer.geometry, f"{name}: the register states the geometry"


@pytest.mark.parametrize("service", SERVICES, ids=lambda service: service.source_id)
def test_the_recorder_queries_exactly_the_feature_layers_the_register_lists(
    service: recorder.MapService,
) -> None:
    registered = {
        layer.name
        for layer in register_layers(service.service)
        if layer.geometry in FEATURE_GEOMETRIES
    }
    recorded = {layer.name for layer in (*service.layers, *service.slot_layers)}
    if service.source_id == "nhc-map-surge-risk":
        # Only the catalog: v2 draws the hazard rasters and queries none of these layers.
        assert not recorded
        assert registered
    else:
        assert recorded == registered


def _active_slots(roster: CaptureDirectory) -> list[str]:
    document = as_object(json.loads(roster.payload(roster.entries[0])))
    storms = [as_object(storm) for storm in as_list(document["activeStorms"])]
    return sorted({str(storm["binNumber"]) for storm in storms})


@pytest.mark.parametrize("service", SERVICES, ids=lambda service: service.source_id)
def test_the_recorded_service_holds_a_capture_of_every_layer_it_queries(
    service: recorder.MapService,
) -> None:
    directory = latest_live(service.source_id)
    assert directory is not None, f"{service.source_id} has no live capture"
    wanted = {layer.name: layer.count_only for layer in service.layers}
    if service.slot_layers:
        roster = latest_live("nhc-current-storms")
        assert roster is not None
        assert roster.day == directory.day, "the roster and the service differ in date"
        for slot in _active_slots(roster):
            wanted.update(
                {
                    layer.name.replace("{slot}", slot): layer.count_only
                    for layer in service.slot_layers
                }
            )
    expected = {
        f"{'count' if count_only else 'query'}-{recorder.slugify(name)}"
        f".{'json' if count_only else 'geojson'}"
        for name, count_only in wanted.items()
    }
    files = directory.file_names()
    assert files - CATALOG_FILES == expected
    assert "catalog.json" in files
    assert files & {"layers.json", "layers.json.gz"}
