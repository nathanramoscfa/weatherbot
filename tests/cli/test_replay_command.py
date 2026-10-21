# tests/cli/test_replay_command.py
"""``weatherbot replay`` prints a storm's ladder over the committed corpus, storing nothing.

The landmarks are added through ``locations add`` against the recorded answers; the
corpus is the committed subset, named by its absolute path, since each test runs in its
own temporary working directory. The goldens' timelines are the operator's approved
reference: Irma's transitions at both landmarks must equal theirs.
"""

import json
import shutil
import time
from pathlib import Path
from typing import cast

import pytest
from cli_support import CORPUS, MIAMI, NASSAU, add_landmark, parse, recorded_services, run, runtime
from fixture_support import REPOSITORY_ROOT
from source_support import NOW
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.cli.documents import ReplayDocument, ReplayStepEntry
from weatherbot.services.config import AppPaths
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.tables import AssessmentRow, SnapshotRow

IRMA = "AL112017"
GOLDENS = REPOSITORY_ROOT / "tests" / "golden" / "replay"
CI_BOUND_SECONDS = 60.0
"""Each storm at each landmark takes under 10 s on the operator's machine; CI is bounded."""
USAGE = 2
LANDMARKS = ((MIAMI, "miami-dade"), (NASSAU, "nassau"))

type Projected = tuple[str, str, int, str, tuple[str, ...], tuple[str, ...]]


@pytest.fixture
def landmarks() -> None:
    with recorded_services():
        for name, key in LANDMARKS:
            assert add_landmark(name, key).exit_code == 0


def _golden(key: str) -> list[dict[str, object]]:
    document = json.loads((GOLDENS / f"{IRMA}-{key}.json").read_text(encoding="utf-8"))
    return cast("list[dict[str, object]]", document["timeline"])


def _projected(entry: dict[str, object]) -> Projected:
    """A golden entry, in the fields a replay step prints."""
    return (
        str(entry["advisory"]),
        str(entry["issued_at"]),
        cast("int", entry["level"]),
        str(entry["rule"]),
        tuple(cast("list[str]", entry["changes"])),
        tuple(cast("list[str]", entry["official_codes"])),
    )


def _step(step: ReplayStepEntry) -> Projected:
    return (
        step.advisory,
        step.issued_at.isoformat().replace("+00:00", "Z"),
        step.level,
        step.rule,
        tuple(change.kind for change in step.changes),
        step.official_codes,
    )


def _transitions(timeline: list[dict[str, object]]) -> list[Projected]:
    kept: list[Projected] = []
    previous: tuple[object, object] | None = None
    for entry in timeline:
        if (entry["level"], entry["rule"]) != previous:
            kept.append(_projected(entry))
        previous = (entry["level"], entry["rule"])
    return kept


def _replay(name: str, *extra: str) -> list[str]:
    return ["replay", IRMA, "--location", name, "--corpus", str(CORPUS), *extra]


@pytest.mark.usefixtures("landmarks")
@pytest.mark.parametrize(("name", "key"), LANDMARKS)
def test_irma_s_transitions_at_each_landmark_equal_the_golden_s(name: str, key: str) -> None:
    started = time.perf_counter()
    ran = run(_replay(name, "--json"))
    elapsed = time.perf_counter() - started
    document = parse(ran, ReplayDocument)
    every = parse(run(_replay(name, "--every", "--json")), ReplayDocument)

    assert ran.exit_code == 0, ran.stderr
    assert elapsed < CI_BOUND_SECONDS
    assert [_step(step) for step in document.data.steps] == _transitions(_golden(key))
    assert [_step(step) for step in every.data.steps] == [_projected(e) for e in _golden(key)]
    storm = document.data.storm
    assert (storm.atcf_id, storm.name, storm.advisories) == (IRMA, "Irma", len(_golden(key)))
    assert not document.data.every
    assert every.data.every


@pytest.mark.usefixtures("landmarks")
def test_replay_prints_the_transitions_and_stores_nothing() -> None:
    result = run(_replay(MIAMI))

    assert result.exit_code == 0, result.stderr
    assert "Irma (AL112017) at Miami-Dade County Hall: 84 advisories" in result.stdout
    assert "Transitions: the 12 advisories where the level or the rule changes" in result.stdout
    assert "36        2017-09-08 03:00 UTC  5 Hurricane Warning" in result.stdout
    assert "level_changed, advisory_issued, official_changed" in result.stdout
    assert "Replayed assessments lack " in result.stdout
    assert "NWS alerts" in result.stdout
    assert "Nothing was stored: a replay is never part of the history." in result.stdout
    assert result.stdout.rstrip().endswith(NOTICE)
    with open_database(AppPaths.resolve()) as database, Session(database.engine) as session:
        for table in (AssessmentRow, SnapshotRow):
            assert session.scalar(select(func.count()).select_from(table)) == 0  # pyright: ignore[reportArgumentType] - a mapped class


@pytest.mark.usefixtures("landmarks")
def test_replay_assesses_with_the_toggle_off_and_says_so() -> None:
    run(["locations", "evacuation", MIAMI, "on"])

    ran = run(_replay(MIAMI, "--json"), runtime(now=NOW))
    document = parse(ran, ReplayDocument)

    assert document.data.location.evacuation_order_stored_on
    assert any("assesses with it off" in note for note in document.data.notes)
    assert [_step(step) for step in document.data.steps] == _transitions(_golden("miami-dade"))
    assert all(step.rule != "evacuation_order" for step in document.data.steps)


def test_replay_names_convert_full_where_the_windows_do_not_cover_the_location() -> None:
    lat, lon = synthetic_coordinates(load_landmarks(), (), seed=6)
    with recorded_services():
        run(["locations", "add", "Elsewhere", "--lat", lat, "--lon", lon])

    document = parse(
        run(["replay", IRMA, "--location", "Elsewhere", "--corpus", str(CORPUS), "--json"]),
        ReplayDocument,
    )

    (note,) = [note for note in document.data.notes if "convert --full" in note]
    assert "windows around the public landmarks" in note
    assert "do not cover 'Elsewhere'" in note


@pytest.mark.usefixtures("landmarks")
def test_replay_refuses_a_directory_without_a_manifest_an_unknown_storm_or_location(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "not-a-corpus"
    empty.mkdir()

    no_manifest = run(["replay", IRMA, "--location", MIAMI, "--corpus", str(empty)])
    missing = run(["replay", IRMA, "--location", MIAMI, "--corpus", str(tmp_path / "absent")])
    storm = run(["replay", "AL012000", "--location", MIAMI, "--corpus", str(CORPUS)])
    place = run(["replay", IRMA, "--location", "Nowhere", "--corpus", str(CORPUS)])

    assert no_manifest.exit_code == USAGE
    assert "is not a replay corpus" in no_manifest.stderr
    assert "holds no manifest" in no_manifest.stderr
    assert missing.exit_code == USAGE
    assert "--corpus must name a directory" in missing.stderr
    assert storm.exit_code == USAGE
    assert "the corpus holds no storm 'AL012000'; it holds AL052019 (Dorian)" in storm.stderr
    assert place.exit_code == USAGE
    assert "no location is named 'Nowhere'" in place.stderr


@pytest.mark.usefixtures("landmarks")
def test_replay_exits_1_when_the_corpus_refuses_a_tampered_file(tmp_path: Path) -> None:
    copy = tmp_path / "corpus"
    shutil.copytree(CORPUS, copy)
    manifest = json.loads((copy / "corpus-manifest.json").read_text(encoding="utf-8"))
    cone = next(item for item in manifest["subset"] if item["product"] == "cone")
    target = copy / cone["file"]
    target.write_bytes(target.read_bytes() + b" ")

    result = run(["replay", IRMA, "--location", MIAMI, "--corpus", str(copy)])

    assert result.exit_code == 1
    assert "the corpus refused a file" in result.stderr
