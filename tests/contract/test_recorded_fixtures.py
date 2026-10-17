# tests/contract/test_recorded_fixtures.py
"""Contract tests over every recorded capture under ``tests/fixtures/recorded/``.

Each capture directory holds one ``manifest.json`` (schema in the module docstring of
``scripts/record_fixtures.py``). These tests verify what the manifest claims against the
bytes on disk, and that no stored header, file, or request coordinate falls outside what the
recorder promises.
"""

import hashlib
import json
import re
from decimal import Decimal

import pytest
from fixture_support import (
    DATE_NAME,
    MANIFEST_NAME,
    RECORDED_ROOT,
    CaptureDirectory,
    as_object,
    capture_directories,
    register_rows,
    register_user_agent,
)

import check_personal_data as checker
import record_fixtures as recorder
from weatherbot.sources.markup import parse_xml
from weatherbot.sources.nhc_arrival_times import read_kml

DIRECTORIES = capture_directories()
EVERY_DIRECTORY = pytest.mark.parametrize(
    "directory", DIRECTORIES, ids=[item.label for item in DIRECTORIES]
)

MANIFEST_KEYS = ["schema", "source", "recorded_at", "recorder", "user_agent", "captures"]
ENTRY_KEYS = [
    "file",
    "url",
    "status",
    "fetched_at",
    "sha256",
    "bytes",
    "stored_as",
    "headers",
    "origin",
    "notes",
]
ORIGINS = {recorder.ORIGIN_LIVE, recorder.ORIGIN_REPORT, recorder.ORIGIN_CACHE}
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
DIGEST = re.compile(r"[0-9a-f]{64}")
PNG_NOTE = re.compile(r"PNG (\d+)x(\d+)")
HTTP_STATUSES = range(100, 600)
HARVESTED_OUTLOOK_DATES = (
    "2025-09-30",
    "2025-10-03",
    "2025-10-04",
    "2025-10-06",
    "2025-10-22",
    "2025-10-23",
)
HARVESTED_FROM = re.compile(r"reports/hurricane_threat_analysis_(\d{4})(\d{2})(\d{2})_\d{6}\.html")


def test_the_recorded_tree_holds_only_capture_directories_and_the_notice() -> None:
    assert DIRECTORIES, "no capture directory under tests/fixtures/recorded/"
    root_entries = sorted(path.name for path in RECORDED_ROOT.iterdir())
    sources = sorted({item.source for item in DIRECTORIES})
    assert root_entries == sorted([*sources, "NOTICE.md"])
    for source in sources:
        for path in (RECORDED_ROOT / source).iterdir():
            assert path.is_dir(), f"{path.name} is a loose file in {source}/"
            assert DATE_NAME.fullmatch(path.name), f"{source}/{path.name} is not a date directory"
            assert (path / MANIFEST_NAME).is_file(), f"{source}/{path.name} has no manifest"


@EVERY_DIRECTORY
def test_the_manifest_matches_the_schema(directory: CaptureDirectory) -> None:
    manifest = directory.manifest
    assert list(manifest) == MANIFEST_KEYS
    assert manifest["schema"] == recorder.SCHEMA_VERSION
    assert manifest["source"] == directory.source
    assert manifest["source"] in {row.source_id for row in register_rows()}
    assert TIMESTAMP.fullmatch(str(manifest["recorded_at"]))
    assert manifest["recorder"] == recorder.RECORDER_PATH
    assert manifest["user_agent"] == recorder.USER_AGENT == register_user_agent()
    assert directory.entries, "a capture directory records at least one file"
    for entry in directory.entries:
        harvested = str(entry["origin"]).startswith("harvest:")
        assert list(entry) == [*ENTRY_KEYS, *(["harvested_from"] if harvested else [])]
        assert entry["origin"] in ORIGINS
        assert "/" not in str(entry["file"]), "a file is named, not addressed by path"
        assert str(entry["url"]).startswith("https://")
        assert isinstance(entry["status"], int)
        assert entry["status"] in HTTP_STATUSES
        assert TIMESTAMP.fullmatch(str(entry["fetched_at"]))
        assert DIGEST.fullmatch(str(entry["sha256"]))
        assert isinstance(entry["bytes"], int)
        assert entry["stored_as"] in {"raw", "gzip"}
        assert str(entry["file"]).endswith(".gz") == (entry["stored_as"] == "gzip")
        assert isinstance(entry["notes"], str)
        headers = as_object(entry["headers"])
        assert all(isinstance(value, str) for value in headers.values())


@EVERY_DIRECTORY
def test_every_listed_file_exists_with_the_recorded_checksum_and_size(
    directory: CaptureDirectory,
) -> None:
    for entry in directory.entries:
        stored = directory.path / str(entry["file"])
        assert stored.is_file(), f"{directory.label}/{entry['file']} is listed but missing"
        payload = directory.payload(entry)
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"], entry["file"]
        assert len(payload) == entry["bytes"], entry["file"]
        if entry["stored_as"] == "gzip":
            assert stored.stat().st_size < len(payload)
            # mtime=0 in the gzip header: recording the same bytes gives the same file.
            assert stored.read_bytes()[4:8] == bytes(4), f"{entry['file']} carries a gzip mtime"
            assert len(payload) > recorder.GZIP_THRESHOLD_BYTES, f"{entry['file']} need not be gzip"
        else:
            assert len(payload) <= recorder.GZIP_THRESHOLD_BYTES, f"{entry['file']} should be gzip"


@EVERY_DIRECTORY
def test_every_file_in_the_directory_is_listed(directory: CaptureDirectory) -> None:
    on_disk = {path.name for path in directory.path.iterdir()}
    assert on_disk - {MANIFEST_NAME} == directory.file_names()
    assert MANIFEST_NAME in on_disk


@EVERY_DIRECTORY
def test_every_payload_parses_by_its_format(directory: CaptureDirectory) -> None:
    for entry in directory.entries:
        name = str(entry["file"]).removesuffix(".gz")
        payload = directory.payload(entry)
        where = f"{directory.label}/{name}"
        if name.endswith(".geojson"):
            document = as_object(json.loads(payload))
            assert document.get("type") == "FeatureCollection", where
            assert isinstance(document.get("features"), list), where
        elif name.endswith(".json"):
            json.loads(payload)
        elif name.endswith(".png"):
            assert payload.startswith(recorder.PNG_SIGNATURE), where
            note = PNG_NOTE.fullmatch(str(entry["notes"]).split(".")[0])
            assert note is not None, f"{where} does not record its size in notes"
            assert recorder.png_dimensions(payload) == (int(note[1]), int(note[2])), where
        elif name.endswith(".xml"):
            parse_xml(payload, "nhc-gis-rss", where)
        elif name.endswith(".kmz"):
            # A zip under the client's limits whose single KML member parses with defusedxml.
            parse_xml(read_kml(payload), "nhc-arrival-times", where)
        else:
            pytest.fail(f"{where} has no parser for its extension")


@EVERY_DIRECTORY
def test_no_stored_header_is_outside_the_allowlist(directory: CaptureDirectory) -> None:
    for entry in directory.entries:
        headers = as_object(entry["headers"])
        assert set(headers) <= recorder.HEADER_ALLOWLIST, entry["file"]
        assert list(headers) == sorted(headers), "headers are stored sorted by name"


@EVERY_DIRECTORY
def test_every_request_coordinate_is_an_allowlisted_landmark(directory: CaptureDirectory) -> None:
    allowlist = checker.Allowlist.from_landmarks(checker.load_landmarks())
    for entry in directory.entries:
        for lat, lon in checker.request_coordinates(str(entry["url"])):
            assert allowlist.allows_pair(Decimal(lat), Decimal(lon)), entry["file"]


@EVERY_DIRECTORY
def test_a_documented_error_is_recorded_with_its_body(directory: CaptureDirectory) -> None:
    for entry in directory.entries:
        if entry["status"] != recorder.HTTP_OK:
            headers = as_object(entry["headers"])
            assert str(headers["content-type"]).startswith(recorder.PROBLEM_JSON)
            assert "title" in as_object(json.loads(directory.payload(entry)))


@EVERY_DIRECTORY
def test_harvested_captures_name_their_source_file(directory: CaptureDirectory) -> None:
    for entry in directory.entries:
        harvested = str(entry["origin"]).startswith("harvest:")
        assert ("harvested_from" in entry) == harvested
        if harvested:
            origin_path = str(entry["harvested_from"])
            assert origin_path.startswith(("reports/", "cache/"))
            assert ".." not in origin_path
            assert "fetched_at" in entry
            assert "converted" in str(entry["notes"]) or "timestamp" in str(entry["notes"])


def test_the_six_harvested_outlook_maps_have_their_provenance() -> None:
    harvested = {
        item.day: item
        for item in DIRECTORIES
        if item.source == recorder.OUTLOOK_SOURCE and not item.is_live()
    }
    assert sorted(harvested) == list(HARVESTED_OUTLOOK_DATES)
    for day, directory in harvested.items():
        (entry,) = directory.entries
        assert entry["file"] == "two_atl_7d0.png"
        assert entry["origin"] == recorder.ORIGIN_REPORT
        assert entry["url"] == recorder.OUTLOOK_URL
        match = HARVESTED_FROM.fullmatch(str(entry["harvested_from"]))
        assert match is not None
        # The folder is the report's local date, which can differ from fetched_at's UTC date.
        assert f"{match[1]}-{match[2]}-{match[3]}" == day


def test_a_live_capture_of_every_outlook_map_exists() -> None:
    live = [
        item for item in DIRECTORIES if item.source == recorder.OUTLOOK_SOURCE and item.is_live()
    ]
    assert live, "no live outlook capture"
    assert live[-1].file_names() == set(recorder.OUTLOOK_FILES)
