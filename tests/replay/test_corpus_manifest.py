# tests/replay/test_corpus_manifest.py
"""Every committed replay file has pinned archive and native CRS provenance."""

import gzip
import hashlib
import json
from typing import cast

import fetch_replay_corpus as corpus
from record_fixtures import as_list, as_object

ROOT = corpus.DEFAULT_ROOT


def test_manifest_covers_the_four_storms_and_all_archive_products() -> None:
    manifest = corpus.load_manifest()
    assert manifest.schema == 1
    assert manifest.coordinate_policy == corpus.COORDINATE_POLICY
    assert manifest.files
    assert manifest.subset
    for storm, info in manifest.storms.items():
        entries = [entry for entry in manifest.files if entry.storm == storm]
        assert info.advisories == sorted(set(info.advisories), key=corpus.advisory_key)
        assert {entry.advisories[0] for entry in entries if entry.product == "5day"} == set(
            info.advisories
        )
        assert {entry.advisories[0] for entry in entries if entry.product == "fcst"} | set(
            info.missing_fcst
        ) == set(info.advisories)
        assert {entry.synoptic_time for entry in entries if entry.product == "fcst"} == set(
            info.synoptic_times
        )
        for moment in info.synoptic_times:
            wsp = [
                entry
                for entry in entries
                if entry.synoptic_time == moment and entry.product.startswith("wsp_")
            ]
            assert {entry.product for entry in wsp} == {"wsp_120hr5km", "wsp_120hrhalfDeg"}
            fcst = [
                entry
                for entry in entries
                if entry.product == "fcst" and entry.synoptic_time == moment
            ]
            assert all(
                set(entry.advisories) == {item.advisories[0] for item in fcst} for entry in wsp
            )
        for adv in info.advisories:
            arrivals = {
                entry.product
                for entry in entries
                if entry.advisories == [adv] and entry.product.startswith("toa_")
            }
            assert arrivals == (
                set()
                if adv in info.missing_arrival
                else {"toa_earliest_reasonable", "toa_most_likely"}
            )
    assert manifest.storms["AL112017"].missing_arrival == manifest.storms["AL112017"].advisories
    assert manifest.storms["AL092022"].missing_fcst


def test_every_subset_file_matches_its_manifest_and_original_archive_member() -> None:
    manifest = corpus.load_manifest()
    archives = {entry.file: entry for entry in manifest.files}
    actual = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*.geojson.gz")}
    assert actual == {output.file for output in manifest.subset}
    assert len(actual) == len(manifest.subset)
    for output in manifest.subset:
        path = corpus.safe_path(ROOT, output.file)
        body = path.read_bytes()
        assert len(body) == output.bytes
        assert hashlib.sha256(body).hexdigest() == output.sha256
        assert body[4:8] == bytes(4), "gzip mtime must be zero"
        collection = as_object(json.loads(gzip.decompress(body)), output.file)
        source = archives[output.source]
        assert source.product == "5day"
        assert collection["source"] == source.file
        assert collection["storm"] == source.storm
        assert collection["advisory"] == source.advisories[0]
        crs = as_object(collection["source_crs"], "source CRS")
        original = source.prj[output.member.removesuffix(".shp") + ".prj"]
        assert crs == {"datum": original.datum, "wkt": original.wkt}
        assert corpus.geographic_crs(cast("str", crs["wkt"])) == original
        assert collection["type"] == "FeatureCollection"
        for feature in as_list(collection["features"], "features"):
            assert as_object(feature, "feature")["type"] == "Feature"


def test_every_file_under_replay_is_accounted_for() -> None:
    manifest = corpus.load_manifest()
    actual = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*") if path.is_file()}
    assert actual == {output.file for output in manifest.subset} | {
        "corpus-manifest.json",
        "NOTICE.md",
    }
