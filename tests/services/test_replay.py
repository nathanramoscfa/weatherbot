# tests/services/test_replay.py
"""Replay: the committed corpus read back as snapshots, and every file checked before parsing.

The counts, order, and associations come from the committed subset under
``tests/fixtures/replay/``. The refusals copy a few advisories into a temporary corpus
and break one rule there. The arrival pair is the recorded Dorian 036 KMZ pair, whose
bytes the corpus manifest pins.
"""

import json
import shutil
from functools import cache
from pathlib import Path
from typing import cast

import pytest

from weatherbot.models import Snapshot, parse_synoptic_time
from weatherbot.services import replay
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import SnapshotRepository, SnapshotStoreError
from weatherbot.services.replay import NO_ARRIVAL_PRODUCTS, ReplayCorpus, ReplayError
from weatherbot.sources import nhc_gis_archive

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REPLAY = FIXTURES / "replay"
RECORDED_KMZ = FIXTURES / "recorded" / "nhc-arrival-times" / "2026-10-17"
SNAPSHOTS = {"AL112017": 84, "AL052019": 117, "AL092022": 68, "AL142024": 41}
NAMES = {"AL112017": "Irma", "AL052019": "Dorian", "AL092022": "Ian", "AL142024": "Milton"}
THRESHOLDS = (34, 50, 64)
DORIAN: tuple[str, ...] = ("035", "035A", "036", "036A", "037")
type Json = dict[str, object]


@cache
def committed() -> ReplayCorpus:
    """The committed subset, opened once."""
    return ReplayCorpus.open(REPLAY)


@cache
def snapshots(storm: str) -> tuple[Snapshot, ...]:
    """Every replay snapshot of a storm, from the committed subset."""
    return tuple(committed().snapshots(storm))


def raw_manifest() -> Json:
    """The committed manifest as JSON."""
    return cast("Json", json.loads((REPLAY / nhc_gis_archive.MANIFEST_NAME).read_bytes()))


def associations(storm: str) -> dict[str, str]:
    """Each advisory's synoptic time, as the manifest associates them."""
    files = cast("list[Json]", raw_manifest()["files"])
    return {
        advisory: cast("str", entry["synoptic_time"])
        for entry in files
        if entry["storm"] == storm and entry["product"] == nhc_gis_archive.WSP_ARCHIVE
        for advisory in cast("list[str]", entry["advisories"])
    }


# The committed corpus


def test_the_corpus_lists_its_four_storms() -> None:
    storms = committed().storms()

    assert {storm.atcf_id: storm.advisories for storm in storms} == SNAPSHOTS
    assert {storm.atcf_id: storm.name for storm in storms} == NAMES
    assert all(storm.first_issued_at < storm.last_issued_at for storm in storms)


@pytest.mark.parametrize(("storm", "count"), SNAPSHOTS.items())
def test_each_storm_replays_one_snapshot_per_advisory_in_order(storm: str, count: int) -> None:
    found = snapshots(storm)
    advisories = raw_manifest()["storms"]
    order = cast("dict[str, Json]", advisories)[storm]["advisories"]

    assert len(found) == count
    issued = [snapshot.started_at for snapshot in found]
    assert issued == sorted(issued)
    for snapshot, advisory in zip(found, cast("list[str]", order), strict=True):
        (products,) = snapshot.storms
        assert snapshot.origin == "replay"
        assert snapshot.snapshot_id == replay.snapshot_id(storm, advisory)
        assert snapshot.started_at == snapshot.completed_at
        assert products.cone is not None
        assert snapshot.started_at == products.cone.advisory.issued_at
        assert products.archived is not None
        assert products.atcf_id == storm
        assert products.track is not None
        assert products.track_points
    assert len({snapshot.snapshot_id for snapshot in found}) == count


@pytest.mark.parametrize("storm", SNAPSHOTS)
def test_each_snapshot_holds_the_probabilities_the_manifest_associates(storm: str) -> None:
    associated = associations(storm)
    order = cast(
        "list[str]", cast("dict[str, Json]", raw_manifest()["storms"])[storm]["advisories"]
    )

    for snapshot, advisory in zip(snapshots(storm), order, strict=True):
        products = snapshot.wind_probabilities
        if advisory not in associated:
            assert products == ()
            continue
        assert tuple(product.threshold_kt for product in products) == THRESHOLDS
        assert {product.synoptic_at for product in products} == {
            parse_synoptic_time(associated[advisory])
        }
        assert all(product.coverage is not None for product in products)


def test_ian_s_last_three_advisories_have_no_probabilities() -> None:
    assert [bool(snapshot.wind_probabilities) for snapshot in snapshots("AL092022")[-3:]] == [
        False,
        False,
        False,
    ]


def test_the_committed_subset_s_arrival_outcome_is_skipped_with_its_reason() -> None:
    for storm in SNAPSHOTS:
        for snapshot in snapshots(storm):
            archive, arrivals = snapshot.source_outcomes
            assert (archive.source_id, archive.status) == ("nhc-gis-archive", "ok")
            assert (arrivals.source_id, arrivals.status) == ("nhc-arrival-times", "skipped")
            assert arrivals.reason == NO_ARRIVAL_PRODUCTS
            assert snapshot.storms[0].arrival_times == ()


def test_replay_is_deterministic() -> None:
    again = next(ReplayCorpus.open(REPLAY).snapshots("AL112017"))

    assert again == snapshots("AL112017")[0]


def test_an_unknown_storm_is_refused() -> None:
    with pytest.raises(ReplayError, match="lists no storm 'AL012017'") as error:
        next(committed().snapshots("AL012017"))
    assert error.value.file == nhc_gis_archive.MANIFEST_NAME


def test_the_repository_refuses_a_replay_snapshot() -> None:
    with open_database(AppPaths.resolve()) as database:
        repository = SnapshotRepository(database.engine)

        with pytest.raises(SnapshotStoreError, match="history is live only"):
            repository.save(snapshots("AL112017")[0])
        assert repository.latest() is None


# A small copied corpus, broken one rule at a time


def small_corpus(directory: Path, storm: str, advisories: tuple[str, ...]) -> Path:
    """Copy a few advisories of one storm (forecast products and windows) into ``directory``."""
    raw = raw_manifest()
    files = [entry for entry in cast("list[Json]", raw["files"]) if entry["storm"] == storm]
    sources = {
        cast("str", entry["file"])
        for entry in files
        if set(cast("list[str]", entry["advisories"])) & set(advisories)
    }
    subset = [entry for entry in cast("list[Json]", raw["subset"]) if entry["source"] in sources]
    storm_entry = cast("dict[str, Json]", raw["storms"])[storm]
    raw = {
        **raw,
        "files": files,
        "subset": subset,
        "storms": {storm: {**storm_entry, "advisories": list(advisories)}},
    }
    for entry in subset:
        target = directory / cast("str", entry["file"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPLAY / cast("str", entry["file"]), target)
    write(directory, raw)
    return directory


def write(directory: Path, raw: Json) -> None:
    """Write a corpus manifest."""
    (directory / nhc_gis_archive.MANIFEST_NAME).write_bytes(json.dumps(raw).encode())


def manifest_of(directory: Path) -> Json:
    """Read a corpus manifest back."""
    return cast("Json", json.loads((directory / nhc_gis_archive.MANIFEST_NAME).read_bytes()))


@pytest.fixture
def small(tmp_path: Path) -> Path:
    """Irma 001 and 002, copied."""
    return small_corpus(tmp_path / "corpus", "AL112017", ("001", "002"))


@pytest.fixture
def parsed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every cone the archive parser is handed."""
    seen: list[str] = []
    original = nhc_gis_archive.parse_cone

    def recording(body: bytes, entry: nhc_gis_archive.CorpusEntry) -> object:
        seen.append(entry.converted.file)
        return original(body, entry)

    monkeypatch.setattr(nhc_gis_archive, "parse_cone", recording)
    return seen


def test_a_small_copy_replays_like_the_committed_subset(small: Path) -> None:
    copied = tuple(ReplayCorpus.open(small).snapshots("AL112017"))

    assert copied == snapshots("AL112017")[:2]


def test_a_flipped_byte_is_refused_before_parsing(small: Path, parsed: list[str]) -> None:
    cone = small / "AL112017" / "002" / "cone.geojson.gz"
    body = cone.read_bytes()
    cone.write_bytes(bytes([body[0], body[1], body[2] ^ 1]) + body[3:])
    found = ReplayCorpus.open(small).snapshots("AL112017")

    assert next(found).snapshot_id == replay.snapshot_id("AL112017", "001")
    with pytest.raises(ReplayError, match="SHA-256 differs") as error:
        next(found)
    assert error.value.file == "AL112017/002/cone.geojson.gz"
    assert "AL112017/002/cone.geojson.gz" not in parsed


def test_a_file_of_another_size_is_refused(small: Path) -> None:
    track = small / "AL112017" / "001" / "track.geojson.gz"
    track.write_bytes(track.read_bytes() + b"\0")

    with pytest.raises(ReplayError, match="size differs"):
        next(ReplayCorpus.open(small).snapshots("AL112017"))


def test_a_missing_file_is_refused(small: Path, parsed: list[str]) -> None:
    (small / "AL112017" / "001" / "cone.geojson.gz").unlink()

    with pytest.raises(ReplayError, match="the file is missing") as error:
        next(ReplayCorpus.open(small).snapshots("AL112017"))
    assert error.value.rule == "the file is missing"
    assert parsed == []


@pytest.mark.parametrize(
    "name", ["../outside/cone.geojson.gz", "/absolute/cone.geojson.gz", "a\\b.gz", "a//b.gz"]
)
def test_a_path_that_leaves_the_corpus_is_refused_on_open(small: Path, name: str) -> None:
    raw = manifest_of(small)
    subset = cast("list[Json]", raw["subset"])
    subset[0] = {**subset[0], "file": name}
    write(small, raw)

    with pytest.raises(ReplayError, match="not a plain relative path") as error:
        ReplayCorpus.open(small)
    assert error.value.file == name


def test_a_link_out_of_the_corpus_is_refused(small: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.geojson.gz"
    cone = small / "AL112017" / "001" / "cone.geojson.gz"
    shutil.copyfile(cone, outside)
    cone.unlink()
    try:
        cone.symlink_to(outside)
    except OSError:
        pytest.skip("this account cannot create symbolic links")

    with pytest.raises(ReplayError, match="leaves the corpus directory"):
        ReplayCorpus.open(small)


def test_a_file_listed_over_the_bound_is_refused(
    small: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(replay, "MAX_FILE_BYTES", 10)

    with pytest.raises(ReplayError, match="over 10 bytes"):
        ReplayCorpus.open(small)


def test_a_directory_without_a_readable_manifest_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ReplayError, match="holds no manifest"):
        ReplayCorpus.open(tmp_path)
    write(tmp_path, {"schema": 2})
    with pytest.raises(ReplayError, match="does not parse"):
        ReplayCorpus.open(tmp_path)


def test_a_verified_file_that_does_not_parse_names_itself(small: Path) -> None:
    raw = manifest_of(small)
    subset = cast("list[Json]", raw["subset"])
    track = next(entry for entry in subset if entry["file"] == "AL112017/001/track.geojson.gz")
    cone = next(entry for entry in subset if entry["file"] == "AL112017/001/cone.geojson.gz")
    track["file"], track["sha256"], track["bytes"] = cone["file"], cone["sha256"], cone["bytes"]
    write(small, raw)

    with pytest.raises(ReplayError, match="does not parse") as error:
        next(ReplayCorpus.open(small).snapshots("AL112017"))
    assert error.value.file == "AL112017/001/cone.geojson.gz"


# Arrival-time products


@pytest.fixture
def with_kmz(tmp_path: Path) -> Path:
    """Dorian 035 to 037 copied, with the recorded 036 pair in place of the archive's."""
    directory = small_corpus(tmp_path / "corpus", "AL052019", DORIAN)
    raw = manifest_of(directory)
    files = {cast("str", entry["file"]): entry for entry in cast("list[Json]", raw["files"])}
    for kind in nhc_gis_archive.ARRIVAL_KINDS:
        name = f"AL052019_036adv_{kind.removeprefix('toa_')}_toa_34.kmz"
        source = files[f"AL052019/{name}"]
        target = directory / "AL052019" / "toa" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RECORDED_KMZ / name, target)
        cast("list[Json]", raw["subset"]).append(
            {
                "file": f"AL052019/toa/{name}",
                "source": source["file"],
                "member": name,
                "product": kind,
                "sha256": source["sha256"],
                "bytes": source["bytes"],
            }
        )
    write(directory, raw)
    return directory


def test_each_advisory_gets_the_pair_of_the_latest_full_advisory(with_kmz: Path) -> None:
    replayed = list(ReplayCorpus.open(with_kmz).snapshots("AL052019"))
    by_advisory = dict(zip(DORIAN, replayed, strict=True))

    for advisory in ("036", "036A"):
        snapshot = by_advisory[advisory]
        products = snapshot.storms[0].arrival_times
        assert [product.kind for product in products] == ["earliest_reasonable", "most_likely"]
        assert all(str(product.advisory.number) == "36" for product in products)
        assert all(product.withheld_reason is None for product in products)
        assert all(product.provenance.source_id == "nhc-arrival-times" for product in products)
        assert snapshot.source_outcomes[1].status == "ok"
    for advisory, full in (("035", "035"), ("035A", "035"), ("037", "037")):
        outcome = by_advisory[advisory].source_outcomes[1]
        assert outcome.status == "skipped"
        assert outcome.reason == f"{NO_ARRIVAL_PRODUCTS} for AL052019 advisory {full}"


def test_an_intermediate_with_no_full_advisory_before_it_has_no_pair(with_kmz: Path) -> None:
    raw = manifest_of(with_kmz)
    storms = cast("dict[str, Json]", raw["storms"])
    storms["AL052019"] = {**storms["AL052019"], "advisories": ["035A", "036"]}
    write(with_kmz, raw)

    first, second = ReplayCorpus.open(with_kmz).snapshots("AL052019")

    assert first.source_outcomes[1].reason == f"{NO_ARRIVAL_PRODUCTS} for AL052019 advisory 035A"
    assert second.source_outcomes[1].status == "ok"
