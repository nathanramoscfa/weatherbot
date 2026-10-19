# tests/sources/test_nhc_gis_archive.py
"""The archive parsers, on the committed replay corpus: every kind, its provenance, and its rules.

Every test reads the committed subset under ``tests/fixtures/replay/`` through its manifest;
a rule is broken by rewriting a committed collection (and its manifest entry's checksum),
never by a coordinate literal.
"""

import gzip
import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import cast

import pytest

from weatherbot.models import AdvisoryNumber, WindProbabilityProduct
from weatherbot.sources import nhc_gis_archive as archive
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.fields import MISSING_VALUE
from weatherbot.sources.nhc_gis_archive import ConvertedFile, CorpusEntry, CorpusManifest

REPLAY = Path(__file__).resolve().parents[1] / "fixtures" / "replay"
RECORDED_ON = date(2026, 10, 15)
STORMS = ("AL052019", "AL092022", "AL112017", "AL142024")
SUBSET_FILES = 1708
WINDOWED_FILES = 507
SINGLETON_POINTS = 36
SINGLETON_ADVISORIES = 12
IRMA_036_POINTS = 8


@cache
def manifest() -> CorpusManifest:
    """The committed manifest, parsed by the module under test."""
    return archive.parse_manifest((REPLAY / archive.MANIFEST_NAME).read_bytes())


def converted(file: str) -> ConvertedFile:
    """A committed file's manifest entry."""
    return next(item for item in manifest().subset if item.file == file)


def read(file: str) -> tuple[bytes, CorpusEntry]:
    """A committed file's bytes and its parser input."""
    return (REPLAY / file).read_bytes(), manifest().entry(converted(file))


def document(file: str) -> dict[str, object]:
    """A committed collection, decompressed."""
    return cast("dict[str, object]", json.loads(gzip.decompress((REPLAY / file).read_bytes())))


def rewritten(file: str, collection: dict[str, object]) -> tuple[bytes, CorpusEntry]:
    """A collection rewritten, with its manifest entry's size and checksum to match."""
    body = gzip.compress(json.dumps(collection).encode(), mtime=0)
    entry = manifest().entry(converted(file))
    checked = replace(entry.converted, sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
    return body, replace(entry, converted=checked)


def features(collection: dict[str, object]) -> list[dict[str, object]]:
    """A collection's features."""
    return cast("list[dict[str, object]]", collection["features"])


# The manifest


def test_the_committed_manifest_parses_with_its_recording_day() -> None:
    parsed = manifest()

    assert parsed.recorded_on == RECORDED_ON
    assert tuple(parsed.storms) == STORMS
    assert len(parsed.subset) == SUBSET_FILES
    assert sum(item.product in archive.WSP_KINDS for item in parsed.subset) == WINDOWED_FILES
    assert all(item.source in parsed.files for item in parsed.subset)
    assert "landmark" in parsed.subset_rule


def manifest_with(**changes: object) -> bytes:
    """The committed manifest with top-level members replaced."""
    raw = cast("dict[str, object]", json.loads((REPLAY / archive.MANIFEST_NAME).read_bytes()))
    return json.dumps({**raw, **changes}).encode()


def first_subset(**changes: object) -> list[object]:
    """The committed subset with its first entry changed."""
    raw = cast("dict[str, object]", json.loads((REPLAY / archive.MANIFEST_NAME).read_bytes()))
    subset = cast("list[dict[str, object]]", raw["subset"])
    return [{**subset[0], **changes}, *subset[1:]]


@pytest.mark.parametrize(
    ("body", "rule"),
    [
        (b"not json", "not valid JSON"),
        (manifest_with(schema=2), "schema is not 1"),
        (manifest_with(recorded_on="15 October"), "not a YYYY-MM-DD date"),
        (manifest_with(storms={"Irma": {}}), "keyed by ATCF id"),
        (manifest_with(subset=first_subset(source="elsewhere.zip")), "does not pin"),
        (manifest_with(subset=first_subset(sha256="0")), "not a SHA-256"),
        (manifest_with(subset=first_subset(bytes=-1)), "negative"),
        (manifest_with(storms={}), "names no storm"),
    ],
    ids=["json", "schema", "day", "storm-key", "source", "sha256", "bytes", "storm"],
)
def test_a_manifest_that_breaks_a_rule_is_refused(body: bytes, rule: str) -> None:
    with pytest.raises(SourceSchemaError, match=rule):
        archive.parse_manifest(body)


def test_a_manifest_over_its_bound_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archive, "MAX_MANIFEST_BYTES", 10)

    with pytest.raises(SourceSchemaError, match="over 10 bytes"):
        archive.parse_manifest(b"{}" * 10)


# Forecast products


def test_a_cone_parses_with_the_archive_s_provenance_and_native_crs() -> None:
    body, entry = read("AL112017/036/cone.geojson.gz")

    cone = archive.parse_cone(body, entry)

    assert cone.atcf_id == "AL112017"
    assert cone.advisory.number == AdvisoryNumber.parse("36")
    assert cone.advisory.issued_at == datetime(2017, 9, 8, 3, tzinfo=UTC)
    assert cone.advisory.issued_at_source == "local_text"
    assert cone.geometry.type == "Polygon"
    assert cone.geometry.crs.name == "native"
    assert cone.geometry.crs.datum == "D_Sphere"
    assert cone.forecast_period_h == 120  # noqa: PLR2004 - FCSTPRD
    provenance = cone.provenance
    assert provenance.source_id == "nhc-gis-archive"
    assert provenance.url == entry.archive.url
    assert provenance.sha256 == entry.archive.sha256
    assert provenance.fetched_at == datetime(2026, 10, 15, tzinfo=UTC)
    assert provenance.issued_at == cone.advisory.issued_at
    assert provenance.advisory == cone.advisory.number


@pytest.mark.parametrize(
    ("storm", "name", "storm_type"),
    [
        ("AL052019", "Five", "TD"),
        ("AL092022", "Nine", "TD"),
        ("AL142024", "Fourteen", "TD"),
    ],
)
def test_an_archive_storm_is_named_and_typed_as_the_archive_spells_it(
    storm: str, name: str, storm_type: str
) -> None:
    body, entry = read(f"{storm}/001/cone.geojson.gz")

    found = archive.parse_archive_storm(body, entry)

    assert (found.atcf_id, found.name, found.storm_type) == (storm, name, storm_type)
    assert found.provenance == archive.parse_cone(body, entry).provenance


def test_a_track_is_a_line_on_the_archive_sphere() -> None:
    body, entry = read("AL112017/036/track.geojson.gz")

    track = archive.parse_track(body, entry)

    assert track.geometry.type in {"LineString", "MultiLineString"}
    assert track.geometry.crs.datum == "D_Sphere"


def test_forecast_points_are_timed_and_read_9999_as_none() -> None:
    body, entry = read("AL112017/036/points.geojson.gz")
    raw = [
        cast("dict[str, object]", f["properties"]) for f in features(document(entry.converted.file))
    ]

    points = archive.parse_track_points(body, entry)

    assert len(points) == IRMA_036_POINTS
    assert [point.tau_h for point in points] == sorted(point.tau_h for point in points)
    assert points[0].valid_at < points[-1].valid_at
    for point, properties in zip(points, raw, strict=True):
        assert (point.mslp_mb is None) == (properties["MSLP"] == MISSING_VALUE)
        assert (point.direction_deg is None) == (properties["TCDIR"] == MISSING_VALUE)
        assert (point.speed_kt is None) == (properties["TCSPD"] == MISSING_VALUE)
    assert points[0].mslp_mb is not None
    assert all(point.mslp_mb is None for point in points[1:])


def test_dorian_s_one_vertex_warnings_stay_noted_points() -> None:
    advisories: set[str] = set()
    found = 0
    for item in manifest().subset:
        if item.product != "watch-warning" or not item.file.startswith("AL052019/"):
            continue
        body, entry = read(item.file)
        for segment in archive.parse_watch_warnings(body, entry):
            if segment.geometry.type == "Point":
                assert segment.geometry_note is not None
                assert "no segment invented" in segment.geometry_note
                advisories.add(item.file.split("/")[1])
                found += 1

    assert found == SINGLETON_POINTS
    assert len(advisories) == SINGLETON_ADVISORIES
    assert min(advisories) == "056"
    assert max(advisories) == "062A"


def test_watch_warning_codes_are_coded_and_kept() -> None:
    body, entry = read("AL052019/030/watch-warning.geojson.gz")

    segments = archive.parse_watch_warnings(body, entry)

    assert segments
    assert {segment.tcww.raw for segment in segments} <= {"HWA", "HWR", "TWA", "TWR"}
    assert all(segment.tcww.recognized for segment in segments)


# Wind-speed-probability extracts


def extract(file: str) -> WindProbabilityProduct:
    """Parse a committed window extract."""
    return archive.parse_wind_probabilities(*read(file))


def test_a_window_extract_reads_its_bands_and_coverage() -> None:
    product = extract("AL052019/wsp/2019090100/wsp-34kt.geojson.gz")

    assert product.threshold_kt == 34  # noqa: PLR2004 - the file's threshold
    assert product.synoptic_at == datetime(2019, 9, 1, tzinfo=UTC)
    assert [band.label for band in product.bands] == [
        "20-30%", "30-40%", "40-50%", "50-60%", "60-70%", "70-80%", "80-90%", ">90%"
    ]  # fmt: skip
    coverage = product.coverage
    assert coverage is not None
    assert coverage.type == "MultiPolygon"
    assert len(cast("tuple[object, ...]", coverage.coordinates)) == 2  # noqa: PLR2004 - two landmarks
    assert all(band.geometry.crs == coverage.crs for band in product.bands)
    assert all(band.geometry.is_valid for band in product.bands)
    assert product.provenance.url.endswith("/2019090100_wsp_120hr5km.zip")
    assert product.provenance.issued_at is None
    assert product.provenance.advisory is None


def test_an_extract_with_no_band_in_its_windows_still_covers_them() -> None:
    product = extract("AL052019/wsp/2019082412/wsp-64kt.geojson.gz")

    assert product.bands == ()
    assert product.coverage is not None


def test_a_band_made_valid_before_clipping_says_so() -> None:
    notes = {
        band.geometry_note
        for item in manifest().subset
        if item.file.startswith("AL052019/wsp/20190902")
        for band in extract(item.file).bands
        if band.geometry_note
    }

    assert notes
    assert all(note.startswith("Source band invalid (Ring Self-intersection)") for note in notes)


# Refusals


def test_bytes_that_differ_from_the_manifest_are_never_parsed() -> None:
    body, entry = read("AL112017/036/cone.geojson.gz")
    flipped = bytes([body[0] ^ 1]) + body[1:]

    with pytest.raises(SourceSchemaError, match="does not match the manifest"):
        archive.parse_cone(flipped, entry)


def test_a_parser_reads_only_its_own_kind() -> None:
    with pytest.raises(SourceSchemaError, match="is a track file, not cone"):
        archive.parse_cone(*read("AL112017/036/track.geojson.gz"))
    with pytest.raises(SourceSchemaError, match="not wsp-34kt"):
        archive.parse_wind_probabilities(*read("AL112017/036/cone.geojson.gz"))


def test_a_collection_naming_another_storm_or_original_is_refused() -> None:
    file = "AL112017/036/cone.geojson.gz"

    with pytest.raises(SourceSchemaError, match="another storm or original"):
        archive.parse_cone(*rewritten(file, {**document(file), "storm": "AL052019"}))
    with pytest.raises(SourceSchemaError, match="not a FeatureCollection"):
        archive.parse_cone(*rewritten(file, {**document(file), "type": "Feature"}))


def edited(file: str, **properties: object) -> tuple[bytes, CorpusEntry]:
    """A collection whose first feature's attributes are changed."""
    collection = document(file)
    first = features(collection)[0]
    first["properties"] = {**cast("dict[str, object]", first["properties"]), **properties}
    return rewritten(file, collection)


def test_a_feature_of_another_storm_or_advisory_is_refused() -> None:
    file = "AL112017/036/cone.geojson.gz"

    with pytest.raises(SourceSchemaError, match="name another storm"):
        archive.parse_cone(*edited(file, STORMNUM=12))
    with pytest.raises(SourceSchemaError, match="not the manifest's advisory"):
        archive.parse_cone(*edited(file, ADVISNUM="37"))


def test_a_cone_or_track_holds_one_feature() -> None:
    file = "AL112017/036/cone.geojson.gz"
    collection = document(file)
    collection["features"] = features(collection) * 2

    with pytest.raises(SourceSchemaError, match="holds 2 features, not one"):
        archive.parse_cone(*rewritten(file, collection))


def test_a_point_needs_an_instant_to_be_timed_against() -> None:
    file = "AL112017/036/points.geojson.gz"

    with pytest.raises(SourceSchemaError, match="no instant to time the point"):
        archive.parse_track_points(*edited(file, ADVDATE="1100 PM XYZ Thu Sep 07 2017"))


def test_a_feature_without_geometry_or_with_a_bad_note_is_refused() -> None:
    file = "AL052019/030/watch-warning.geojson.gz"
    collection = document(file)
    features(collection)[0]["geometry"] = None
    with pytest.raises(SourceSchemaError, match="has no geometry"):
        archive.parse_watch_warnings(*rewritten(file, collection))
    collection = document(file)
    features(collection)[0]["geometry_note"] = 7
    with pytest.raises(SourceSchemaError, match="geometry_note is not text"):
        archive.parse_watch_warnings(*rewritten(file, collection))


def test_an_extract_must_agree_with_its_member_s_name() -> None:
    file = "AL052019/wsp/2019090100/wsp-34kt.geojson.gz"
    body, entry = read(file)

    with pytest.raises(SourceSchemaError, match="disagrees with its member"):
        archive.parse_wind_probabilities(*rewritten(file, {**document(file), "threshold_kt": 50}))
    renamed = replace(entry, converted=replace(entry.converted, member="2019090100_wsp.shp"))
    with pytest.raises(SourceSchemaError, match="not a 5 km wind-speed-probability"):
        archive.parse_wind_probabilities(body, renamed)


def test_a_body_that_is_not_one_bounded_gzip_member_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file = "AL112017/036/cone.geojson.gz"
    body, entry = read(file)

    def checked(data: bytes) -> tuple[bytes, CorpusEntry]:
        digest = hashlib.sha256(data).hexdigest()
        return data, replace(
            entry, converted=replace(entry.converted, sha256=digest, bytes=len(data))
        )

    with pytest.raises(SourceSchemaError, match="not gzip-compressed"):
        archive.parse_cone(*checked(b"plain bytes"))
    with pytest.raises(SourceSchemaError, match="not one complete gzip member"):
        archive.parse_cone(*checked(body[:-8]))
    with pytest.raises(SourceSchemaError, match="not one complete gzip member"):
        archive.parse_cone(*checked(body + body))
    monkeypatch.setattr(archive, "MAX_COLLECTION_BYTES", 100)
    with pytest.raises(SourceSchemaError, match="expands to more than 100 bytes"):
        archive.parse_cone(body, entry)
