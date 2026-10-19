# tests/replay/test_corpus_subset.py
"""Replay geometry, advisory order, landmark windows, and full-cache reproducibility checks."""

import gzip
import json
import os
from pathlib import Path
from typing import cast

import pytest
from shapely.geometry import MultiPolygon, box, shape

import fetch_replay_corpus as corpus
from check_personal_data import load_landmarks
from record_fixtures import as_list, as_object
from weatherbot.models import WIND_PROBABILITY_BANDS

FORECAST_PRODUCTS = ("cone", "track", "points", "watch-warning")
WINDOW_PRODUCTS = ("wsp-34kt", "wsp-50kt", "wsp-64kt")
MAX_WINDOW_BYTES = 1024 * 1024


@pytest.mark.parametrize("storm", corpus.STORMS)
def test_advisories_and_geometry_are_complete_and_valid(storm: str) -> None:
    manifest = corpus.load_manifest()
    info = manifest.storms[storm]
    outputs = [
        output
        for output in manifest.subset
        if output.file.startswith(storm + "/") and output.product in FORECAST_PRODUCTS
    ]
    included = sorted({output.file.split("/")[1] for output in outputs}, key=corpus.advisory_key)
    assert included
    assert included[0] == info.advisories[0]
    assert included[-1] == info.advisories[-1]
    assert set(included).isdisjoint(info.omitted_advisories)
    assert set(included) | set(info.omitted_advisories) == set(info.advisories)
    if manifest.subset_rule == corpus.subset_rule(corpus.ALL_ADVISORIES):
        assert not info.omitted_advisories
    else:
        assert manifest.subset_rule == corpus.subset_rule(corpus.REGION_RULE)
    for adv in included:
        assert {output.product for output in outputs if output.file.split("/")[1] == adv} >= {
            "cone",
            "track",
            "points",
        }
    for output in outputs:
        collection = as_object(
            json.loads(gzip.decompress((corpus.DEFAULT_ROOT / output.file).read_bytes())),
            output.file,
        )
        features = as_list(collection["features"], "features")
        assert features
        for item in features:
            feature = as_object(item, "feature")
            properties = as_object(feature["properties"], "properties")
            advisory = str(properties["ADVISNUM"]).upper().lstrip("0")
            assert advisory == output.file.split("/")[1].lstrip("0")
            geometry = shape(as_object(feature["geometry"], "geometry"))
            assert not geometry.is_empty
            if output.product == "cone":
                assert geometry.geom_type in {"Polygon", "MultiPolygon"}
                assert geometry.is_valid, output.file


def test_every_synoptic_time_has_a_windowed_product_per_threshold() -> None:
    manifest = corpus.load_manifest()
    windows = [output for output in manifest.subset if output.product in WINDOW_PRODUCTS]
    for storm, info in manifest.storms.items():
        expected = {
            f"{storm}/wsp/{moment}/{product}.geojson.gz"
            for moment in info.synoptic_times
            for product in WINDOW_PRODUCTS
        }
        assert {output.file for output in windows if output.file.startswith(storm + "/")} == (
            expected
        )
    assert sum(output.bytes for output in windows) < MAX_WINDOW_BYTES
    assert sum(output.bytes for output in manifest.subset) < corpus.MAX_SUBSET_BYTES


@pytest.mark.parametrize("storm", corpus.STORMS)
def test_each_window_covers_the_landmark_boxes_and_holds_only_known_bands(storm: str) -> None:
    manifest = corpus.load_manifest()
    archives = {entry.file: entry for entry in manifest.files}
    landmarks = load_landmarks()
    boxes = MultiPolygon([box(*bounds) for bounds in corpus.window_boxes(landmarks)])
    for output in manifest.subset:
        if output.product not in WINDOW_PRODUCTS or not output.file.startswith(storm + "/"):
            continue
        collection = as_object(
            json.loads(gzip.decompress((corpus.DEFAULT_ROOT / output.file).read_bytes())),
            output.file,
        )
        source = archives[output.source]
        assert source.product == corpus.WSP_ARCHIVE
        assert collection["synoptic_time"] == source.synoptic_time
        assert (
            output.member
            == f"{source.synoptic_time}_wsp{collection['threshold_kt']}knt120hr_5km.shp"
        )
        assert output.product == f"wsp-{collection['threshold_kt']}kt"
        window = as_object(collection["window"], "window")
        assert window["landmarks"] == [landmark.key for landmark in landmarks]
        assert window["half_width_deg"] == corpus.WINDOW_HALF_WIDTH_DEG
        covered = shape(as_object(window["geometry"], "window geometry"))
        assert covered.equals(boxes)
        for item in as_list(collection["features"], "features"):
            feature = as_object(item, "feature")
            assert as_object(feature["properties"], "properties")["PERCENTAGE"] in (
                WIND_PROBABILITY_BANDS
            )
            band = shape(as_object(feature["geometry"], "geometry"))
            assert band.is_valid, output.file
            assert not band.is_empty
            assert covered.covers(band), output.file
            note = feature.get("geometry_note")
            assert note is None or str(note).startswith("Source band invalid")


@pytest.mark.corpus
def test_full_cache_verifies_every_file_and_reconverts_byte_for_byte(tmp_path: Path) -> None:
    cache = Path(os.environ.get("WEATHERBOT_CORPUS_CACHE", corpus.DEFAULT_CACHE))
    if not cache.is_dir():
        pytest.skip("replay cache absent; run fetch explicitly")
    manifest = corpus.load_manifest()
    corpus.verify(manifest, cache)
    for entry in manifest.files:
        original_prj = dict(entry.prj)
        original_time = entry.synoptic_time
        corpus.inspect_archive(entry, cache)
        assert entry.prj == original_prj
        assert entry.synoptic_time == original_time
    corpus.convert(manifest, cache, tmp_path)
    for output in manifest.subset:
        assert (tmp_path / output.file).read_bytes() == (
            corpus.DEFAULT_ROOT / output.file
        ).read_bytes()


@pytest.mark.corpus
def test_region_fallback_explains_every_omitted_advisory() -> None:
    cache = Path(os.environ.get("WEATHERBOT_CORPUS_CACHE", corpus.DEFAULT_CACHE))
    if not cache.is_dir():
        pytest.skip("replay cache absent")
    manifest = corpus.load_manifest()
    if manifest.subset_rule == corpus.subset_rule(corpus.ALL_ADVISORIES):
        assert all(not info.omitted_advisories for info in manifest.storms.values())
        return
    region = box(-88, 20, -72, 31)
    for entry in manifest.files:
        if entry.product != "5day":
            continue
        collections = corpus.forecast_collections(entry, cache)
        intersects = any(
            shape(as_object(as_object(feature, "feature")["geometry"], "geometry")).intersects(
                region
            )
            for _, product, collection in collections
            if product in {"cone", "watch-warning"}
            for feature in cast("list[object]", collection["features"])
        )
        info = manifest.storms[entry.storm]
        expected = intersects or entry.advisories[0] in {info.advisories[0], info.advisories[-1]}
        assert (entry.advisories[0] not in info.omitted_advisories) == expected
