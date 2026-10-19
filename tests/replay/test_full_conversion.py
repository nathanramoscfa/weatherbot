# tests/replay/test_full_conversion.py
"""A complete local conversion (``convert --full``) replays every advisory of every storm.

It needs the pinned cache, so it runs with ``pytest -m corpus`` (``replay-corpus.yml``).
The conversion goes to a temporary directory outside the checkout; nothing is committed.
"""

import os
from pathlib import Path

import pytest

import fetch_replay_corpus as corpus
from weatherbot.services.replay import NO_ARRIVAL_PRODUCTS, ReplayCorpus
from weatherbot.sources.nhc_gis_archive import ARRIVAL_KINDS

SNAPSHOTS = {"AL112017": 84, "AL052019": 117, "AL092022": 68, "AL142024": 41}
# Every advisory whose latest full advisory has a KMZ pair: all but Irma's (the archive
# begins in 2018) and Ian's last three full advisories (036 to 038 have none).
WITH_ARRIVALS = {"AL112017": 0, "AL052019": 117, "AL092022": 65, "AL142024": 41}


@pytest.mark.corpus
def test_a_full_conversion_replays_every_storm_with_its_arrival_products(tmp_path: Path) -> None:
    cache = Path(os.environ.get("WEATHERBOT_CORPUS_CACHE", corpus.DEFAULT_CACHE))
    if not cache.is_dir():
        pytest.skip("replay cache absent; run fetch explicitly")
    out = tmp_path / "full"
    corpus.convert_full(corpus.load_manifest(), cache, out)
    replayed = ReplayCorpus.open(out)

    counts: dict[str, int] = {}
    arrivals: dict[str, int] = {}
    for storm in corpus.STORMS:
        snapshots = list(replayed.snapshots(storm))
        counts[storm] = len(snapshots)
        arrivals[storm] = 0
        for snapshot in snapshots:
            outcome = snapshot.source_outcomes[1]
            products = snapshot.storms[0].arrival_times
            if outcome.status == "ok":
                arrivals[storm] += 1
                assert len(products) == len(ARRIVAL_KINDS)
                assert all(product.withheld_reason is None for product in products)
            else:
                assert products == ()
                assert str(outcome.reason).startswith(f"{NO_ARRIVAL_PRODUCTS} for {storm}")
            assert all(product.coverage is None for product in snapshot.wind_probabilities)

    assert counts == SNAPSHOTS
    assert arrivals == WITH_ARRIVALS
