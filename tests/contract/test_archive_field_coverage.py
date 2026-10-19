# tests/contract/test_archive_field_coverage.py
"""The archive's field contract: each converted kind reads exactly the register's fields.

``docs/DATA_SOURCES.md``'s "Converted collections" (under "GIS archive") lists, per kind, the
fields v2 uses; ``weatherbot.sources.nhc_gis_archive.FIELDS_READ`` declares what each
parser reads. The two must be equal, and deleting any read field from a committed
collection (its manifest checksum rewritten to match) must fail the parse with
``SourceSchemaError``.
"""

import gzip
import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from fixture_support import register_section_fields

from weatherbot.sources import nhc_gis_archive as archive
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.nhc_gis_archive import CorpusEntry

REPLAY = Path(__file__).resolve().parents[1] / "fixtures" / "replay"
SECTION = "Converted collections"
type Parser = Callable[[bytes, CorpusEntry], object]

# Each kind: its register bullet, a committed collection of it, and the parsers that read it.
KINDS: dict[str, tuple[str, str, tuple[Parser, ...]]] = {
    "cone": (
        "Cone fields v2 uses",
        "AL112017/036/cone.geojson.gz",
        (archive.parse_cone, archive.parse_archive_storm),
    ),
    "track": ("Track fields v2 uses", "AL112017/036/track.geojson.gz", (archive.parse_track,)),
    "points": (
        "Points fields v2 uses",
        "AL112017/036/points.geojson.gz",
        (archive.parse_track_points,),
    ),
    "watch-warning": (
        "Watch-warning fields v2 uses",
        "AL052019/030/watch-warning.geojson.gz",
        (archive.parse_watch_warnings,),
    ),
    "wsp": (
        "WSP extract fields v2 uses",
        "AL052019/wsp/2019090100/wsp-34kt.geojson.gz",
        (archive.parse_wind_probabilities,),
    ),
}
DELETIONS = [(kind, field) for kind in KINDS for field in sorted(archive.FIELDS_READ[kind])]


def _entry(file: str) -> CorpusEntry:
    manifest = archive.parse_manifest((REPLAY / archive.MANIFEST_NAME).read_bytes())
    return manifest.entry(next(item for item in manifest.subset if item.file == file))


def parse_all(parsers: tuple[Parser, ...], body: bytes, entry: CorpusEntry) -> None:
    """Run every parser of a kind over the same bytes."""
    for parse in parsers:
        parse(body, entry)


def test_the_register_lists_every_converted_kind() -> None:
    assert set(archive.FIELDS_READ) == set(KINDS)


@pytest.mark.parametrize("kind", list(KINDS))
def test_each_kind_reads_exactly_the_registers_fields(kind: str) -> None:
    label, _, _ = KINDS[kind]

    assert register_section_fields(SECTION, label, level=3) == archive.FIELDS_READ[kind]


@pytest.mark.parametrize("kind", list(KINDS))
def test_each_kind_parses_its_committed_collection(kind: str) -> None:
    _, file, parsers = KINDS[kind]
    body = (REPLAY / file).read_bytes()

    parse_all(parsers, body, _entry(file))


@pytest.mark.parametrize(("kind", "field"), DELETIONS, ids=[f"{k}:{f}" for k, f in DELETIONS])
def test_deleting_a_field_read_fails_the_parse(kind: str, field: str) -> None:
    _, file, parsers = KINDS[kind]
    collection = cast(
        "dict[str, object]", json.loads(gzip.decompress((REPLAY / file).read_bytes()))
    )
    first = cast("list[dict[str, dict[str, object]]]", collection["features"])[0]
    del first["properties"][field]
    body = gzip.compress(json.dumps(collection).encode(), mtime=0)
    entry = _entry(file)
    entry = replace(
        entry,
        converted=replace(
            entry.converted, sha256=hashlib.sha256(body).hexdigest(), bytes=len(body)
        ),
    )

    with pytest.raises(SourceSchemaError, match=field):
        parse_all(parsers, body, entry)
