# tests/engine/test_cached_arrivals.py
"""Every cached arrival-time product, read at both public landmarks.

It needs the pinned cache, so it runs with ``pytest -m corpus`` (``replay-corpus.yml``).
A complete local conversion (``convert --full``) goes to a temporary directory outside the
checkout, and the products are read back through ``ReplayCorpus``, the verifying reader
replay snapshots use. Each full advisory's pair is read from that advisory's own tau-0
center. The contradiction check here is independent of the engine's guard: it builds each
closed labelled contour with Shapely and tests the landmark itself.
"""

from collections import Counter
from datetime import datetime
from typing import TYPE_CHECKING, cast

import pytest
from engine_support import landmark
from shapely.geometry import Point, Polygon

from weatherbot.engine.arrivals import PATH_LEAVES, read_arrival
from weatherbot.engine.geodesy import Position, figure_of
from weatherbot.engine.geometry import place
from weatherbot.models import WGS84, ArrivalReading, ArrivalTimeProduct
from weatherbot.services.replay import ReplayCorpus

if TYPE_CHECKING:
    from collections.abc import Sequence

LANDMARKS = ("miami-dade", "nassau")
PRODUCTS = 244
# The readings measured on 2026-10-19 over the 244 products at both landmarks: 186 lie
# outside the 5 percent contour, and 22 long paths from Ian's first advisories leave the
# contour and come back, so they read nothing; three of those would otherwise have read
# "before" the first isochrone, days too early.
READINGS = Counter({"outside": 186, "between": 228, "before": 43, "after": 9, "unresolved": 22})


def contours_holding(product: ArrivalTimeProduct, position: Position) -> list[datetime]:
    """The instants of the closed labelled contours that hold a position, built here."""
    instants: list[datetime] = []
    for line in product.lines:
        coordinates = cast("Sequence[Sequence[float]]", line.geometry.coordinates)
        if line.is_outer_contour or line.geometry.type != "LineString":
            continue
        closed = tuple(coordinates[0]) == tuple(coordinates[-1])
        if closed and line.valid_at and Polygon(coordinates).covers(Point(position)):
            instants.append(line.valid_at)
    return instants


def check(reading: ArrivalReading, product: ArrivalTimeProduct, position: Position) -> None:
    """A reading's interval starts before it ends and never passes a contour holding it."""
    if reading.start is not None and reading.end is not None:
        assert reading.start < reading.end
    for instant in contours_holding(product, position):
        assert reading.reading in {"before", "between", "unresolved"}
        if reading.end is not None:
            assert reading.end <= instant


@pytest.mark.corpus
def test_every_cached_arrival_product_reads_at_both_landmarks(
    full_replay_corpus: ReplayCorpus,
) -> None:
    figure = figure_of(WGS84)

    pairs: dict[tuple[str, str, str], tuple[ArrivalTimeProduct, Position]] = {}
    for snapshot in (
        snapshot
        for storm in full_replay_corpus.manifest.storms
        for snapshot in full_replay_corpus.snapshots(storm)
    ):
        storm = snapshot.storms[0].atcf_id
        (products,) = snapshot.storms
        first = min(products.track_points, key=lambda point: point.valid_at)
        coordinates = cast("Sequence[float]", first.position.coordinates)
        for product in products.arrival_times:
            # A full advisory's own snapshot comes first and holds its own pair.
            key = (storm, str(product.advisory.number), product.kind)
            pairs.setdefault(key, (product, (coordinates[0], coordinates[1])))
    readings: Counter[str] = Counter()
    for product, center in pairs.values():
        for key in LANDMARKS:
            position = place(landmark(key), WGS84)
            reading = read_arrival(product, center, position, figure)
            check(reading, product, position)
            readings[reading.reading] += 1
            if reading.reading == "unresolved":
                assert reading.reason == PATH_LEAVES

    assert len(pairs) == PRODUCTS
    assert readings == READINGS
