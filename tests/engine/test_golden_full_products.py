# tests/engine/test_golden_full_products.py
"""A cached full conversion must produce the same levels and rules as the landmark windows."""

from typing import cast

import pytest

from build_goldens import read_document
from ladder_data import GOLDENS, public_landmarks
from weatherbot.engine import assess
from weatherbot.models import Thresholds
from weatherbot.services.replay import ReplayCorpus


@pytest.mark.corpus
def test_full_probability_products_equal_every_golden_level_and_rule(
    full_replay_corpus: ReplayCorpus,
) -> None:
    landmarks = public_landmarks()
    expected: dict[tuple[str, str, str], tuple[object, object]] = {}
    for path in GOLDENS.glob("*.json"):
        document = read_document(path)
        for row in cast("list[dict[str, object]]", document["timeline"]):
            expected[str(document["atcf_id"]), str(document["landmark"]), str(row["advisory"])] = (
                row["level"],
                row["rule"],
            )
    seen: set[tuple[str, str, str]] = set()
    for snapshot in (
        snapshot
        for storm in full_replay_corpus.manifest.storms
        for snapshot in full_replay_corpus.snapshots(storm)
    ):
        storm = snapshot.storms[0]
        assert storm.cone is not None
        assert all(product.coverage is None for product in snapshot.wind_probabilities)
        for landmark, location in landmarks.items():
            assessment = assess(snapshot, location, Thresholds())
            key = (storm.atcf_id, landmark, str(storm.cone.advisory.number))
            assert (int(assessment.level), str(assessment.rule)) == expected[key], key
            seen.add(key)
    assert seen == set(expected)
