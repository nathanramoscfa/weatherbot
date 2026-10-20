# tests/engine/test_golden_replays.py
"""The eight operator-approved timelines bind the engine, its inputs, and its ruleset."""

from copy import deepcopy
from datetime import date
from functools import cache

import pytest

import build_goldens
from ladder_data import CORPUS, GOLDENS, public_landmarks
from weatherbot.models import Thresholds
from weatherbot.services.replay import ReplayCorpus

NAMES = tuple(
    f"{storm}-{landmark}.json"
    for storm in ReplayCorpus.open(CORPUS).manifest.storms
    for landmark in public_landmarks()
)


@cache
def current_goldens() -> dict[str, dict[str, object]]:
    """Run all eight production timelines once for the frozen-reference checks."""
    return build_goldens.candidates()


@pytest.mark.parametrize("name", NAMES)
def test_every_engine_timeline_equals_its_golden(name: str) -> None:
    expected = build_goldens.read_document(GOLDENS / name)
    actual = current_goldens()[name]
    assert {k: v for k, v in expected.items() if k != "approval"} == {
        k: v for k, v in actual.items() if k != "approval"
    }, name
    assert expected["ruleset"] == Thresholds().fingerprint(), name


@pytest.mark.parametrize("name", NAMES)
def test_every_golden_has_an_operator_approval_of_its_exact_timeline(name: str) -> None:
    assert build_goldens.approved(build_goldens.read_document(GOLDENS / name)), name


def test_golden_check_is_read_only_and_requires_all_approvals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_goldens, "candidates", current_goldens)
    assert build_goldens.main(["--check"]) == 0


def test_an_edited_timeline_or_metadata_cannot_retain_its_approval() -> None:
    # Synthetic approval exercises the pure guard; no golden is written or approved here.
    candidate: dict[str, object] = {
        "timeline": [{"level": 2}],
        "ruleset": "before",
        "approval": None,
    }
    frozen = build_goldens.retain_approval(candidate, None, date(2000, 1, 1))
    assert build_goldens.approved(frozen)
    assert build_goldens.retain_approval(candidate, frozen, None) == frozen
    for key, value in (("timeline", [{"level": 3}]), ("ruleset", "after")):
        edited = deepcopy(candidate) | {key: value}
        with pytest.raises(ValueError, match="new operator approval"):
            build_goldens.retain_approval(edited, frozen, None)
    assert not build_goldens.approved(frozen | {"timeline": [{"level": 3}]})


def test_review_digest_binds_metadata_and_each_candidate() -> None:
    before: dict[str, dict[str, object]] = {
        "a.json": {"timeline": [1], "ruleset": "one", "approval": None}
    }
    digest = build_goldens.review_digest(before)
    assert (
        build_goldens.review_digest({"a.json": before["a.json"] | {"approval": "ignored"}})
        == digest
    )
    assert build_goldens.review_digest({"a.json": before["a.json"] | {"ruleset": "two"}}) != digest
    assert build_goldens.review_digest(before | {"b.json": before["a.json"]}) != digest
