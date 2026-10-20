# tests/engine/test_probabilities.py
"""The location's band of each wind-speed-probability product the snapshot holds.

Synthetic bands are squares and rectangles built from the Miami-Dade landmark; the replay
corpus gives the landmark windows, and Ian's advisories without a product.
"""

from collections.abc import Sequence

import pytest
from engine_support import (
    IRMA,
    MIAMI_DADE,
    NASSAU,
    landmark_location,
    landmark_xy,
    square,
    synthetic_snapshot,
    synthetic_storm,
    synthetic_wind,
)
from scenarios import recorded_maps, replay

from weatherbot.engine.probabilities import RULE_THRESHOLDS, read_probabilities
from weatherbot.models import WGS84, Geometry

IAN = "AL092022"


def rectangle(west: float, south: float, east: float, north: float) -> Geometry:
    """A closed rectangle, as a Polygon."""
    ring = ((west, south), (east, south), (east, north), (west, north), (west, south))
    return Geometry(type="Polygon", coordinates=(ring,), crs=WGS84)


def around(east: Sequence[float], north: Sequence[float]) -> Geometry:
    """A rectangle whose sides are offsets in degrees from the Miami-Dade landmark."""
    lon, lat = landmark_xy(MIAMI_DADE)
    return rectangle(lon + east[0], lat + north[0], lon + east[1], lat + north[1])


def test_the_location_reads_the_band_that_covers_it() -> None:
    product = synthetic_wind(
        34,
        [
            ("10-20%", around((-0.5, 0.5), (-0.5, 0.5))),
            ("50-60%", around((1.0, 2.0), (-0.5, 0.5))),
        ],
    )

    (reading,), unavailable = read_probabilities(
        synthetic_snapshot(winds=[product]), landmark_location()
    )

    assert reading.band is not None
    assert (reading.reading.reading, reading.reading.label) == ("band", "10-20%")
    assert (reading.reading.lower_pct, reading.reading.upper_pct) == (10, 20)
    assert reading.reading.synoptic_at == product.synoptic_at
    assert reading.reading.crs == "EPSG:4326"
    assert unavailable == ()


def test_a_point_on_a_shared_boundary_takes_the_higher_band() -> None:
    product = synthetic_wind(
        64,
        [
            ("5-10%", around((-0.5, 0.0), (-0.5, 0.5))),
            ("10-20%", around((0.0, 0.5), (-0.5, 0.5))),
        ],
    )

    (reading,), _ = read_probabilities(synthetic_snapshot(winds=[product]), landmark_location())

    assert reading.reading.label == "10-20%"


def test_a_location_outside_every_band_is_below_every_band() -> None:
    product = synthetic_wind(34, [(">90%", square(landmark_xy(NASSAU), 0.5))])

    (reading,), unavailable = read_probabilities(
        synthetic_snapshot(winds=[product]), landmark_location()
    )

    assert (reading.reading.reading, reading.reading.label, reading.band) == (
        "below_every_band",
        None,
        None,
    )
    assert unavailable == ()


def test_an_extract_says_nothing_outside_its_coverage() -> None:
    window = square(landmark_xy(NASSAU), 1.0)
    product = synthetic_wind(64, [("<5%", square(landmark_xy(NASSAU), 0.5))], coverage=window)

    (reading,), unavailable = read_probabilities(
        synthetic_snapshot(winds=[product]), landmark_location()
    )
    (missing,) = unavailable

    assert (reading.reading.reading, reading.band) == ("outside_coverage", None)
    assert (missing.kind, missing.threshold_kt) == ("wind_probabilities", 64)
    assert "does not cover this location" in missing.reason


def test_an_empty_extract_covering_the_location_reads_below_every_band() -> None:
    product = synthetic_wind(34, [], coverage=square(landmark_xy(MIAMI_DADE), 1.0))

    (reading,), unavailable = read_probabilities(
        synthetic_snapshot(winds=[product]), landmark_location()
    )

    assert reading.reading.reading == "below_every_band"
    assert unavailable == ()


def test_an_invalid_band_is_read_through_its_repair() -> None:
    lon, lat = landmark_xy(MIAMI_DADE)
    # A bow tie whose crossing is a degree east of the landmark.
    bow = (
        (lon - 1.0, lat - 1.0),
        (lon + 3.0, lat + 1.0),
        (lon + 3.0, lat - 1.0),
        (lon - 1.0, lat + 1.0),
        (lon - 1.0, lat - 1.0),
    )
    shape = Geometry(type="Polygon", coordinates=(bow,), crs=WGS84)
    product = synthetic_wind(34, [("20-30%", shape)])

    (reading,), unavailable = read_probabilities(
        synthetic_snapshot(winds=[product]), landmark_location()
    )

    assert not shape.is_valid
    assert reading.reading.label == "20-30%"
    assert unavailable == ()


def test_a_band_left_with_no_area_is_an_unavailable_input() -> None:
    lon, lat = landmark_xy(MIAMI_DADE)
    flat = ((lon, lat), (lon + 1.0, lat), (lon + 2.0, lat), (lon, lat))
    product = synthetic_wind(
        34, [("5-10%", Geometry(type="Polygon", coordinates=(flat,), crs=WGS84))]
    )

    (reading,), unavailable = read_probabilities(
        synthetic_snapshot(winds=[product]), landmark_location()
    )
    (missing,) = unavailable

    assert reading.reading.reading == "below_every_band"
    assert (missing.kind, missing.threshold_kt) == ("wind_probabilities", 34)
    assert missing.reason.startswith("the 5-10% band is unusable")


def test_probabilities_come_from_the_snapshot_never_from_a_storm() -> None:
    storm = synthetic_storm(cone=square(landmark_xy(MIAMI_DADE), 1.0))

    readings, unavailable = read_probabilities(
        synthetic_snapshot(storms=[storm]), landmark_location()
    )

    assert (readings, unavailable) == ((), ())


def test_a_live_snapshot_without_a_product_has_no_band_anywhere() -> None:
    recorded = recorded_maps()

    readings, unavailable = read_probabilities(recorded, landmark_location())

    assert [item.reading.threshold_kt for item in readings] == [34, 50, 64]
    assert {item.reading.reading for item in readings} == {"below_every_band"}
    assert unavailable == ()


def test_the_replay_windows_are_read_inside_their_coverage() -> None:
    readings, unavailable = read_probabilities(replay(IRMA, "36"), landmark_location())

    assert [(item.reading.threshold_kt, item.reading.label) for item in readings] == [
        (34, ">90%"),
        (50, "70-80%"),
        (64, "50-60%"),
    ]
    assert {item.reading.crs for item in readings} == {"native (D_Sphere)"}
    assert unavailable == ()


@pytest.mark.parametrize("advisory", ["36", "37", "38"])
def test_a_replay_advisory_without_a_product_lacks_both_rule_thresholds(advisory: str) -> None:
    snapshot = replay(IAN, advisory)

    readings, unavailable = read_probabilities(snapshot, landmark_location())

    assert snapshot.wind_probabilities == ()
    assert readings == ()
    assert [(item.kind, item.threshold_kt) for item in unavailable] == [
        ("wind_probabilities", threshold) for threshold in RULE_THRESHOLDS
    ]
