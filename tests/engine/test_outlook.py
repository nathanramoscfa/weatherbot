# tests/engine/test_outlook.py
"""The seven-day development regions at a location: covering or not, and their chance."""

from engine_support import (
    IRMA,
    MIAMI_DADE,
    NASSAU,
    SYNTHETIC_AT,
    landmark_location,
    landmark_xy,
    square,
    synthetic_provenance,
    synthetic_region,
    synthetic_snapshot,
)
from scenarios import development_region_location, recorded_maps, replay

from weatherbot.engine.outlook import read_regions
from weatherbot.models import WGS84, Geometry, OutlookArea


def test_a_region_covering_the_location_is_read_with_its_chance() -> None:
    region = synthetic_region(square(landmark_xy(MIAMI_DADE), 1.0), 30)

    (reading,), unavailable = read_regions(
        synthetic_snapshot(outlook=[region]), landmark_location()
    )

    assert (reading.covers, reading.chance_7day_pct, reading.area) == (True, 30, region)
    assert unavailable == ()


def test_a_region_elsewhere_is_read_as_not_covering() -> None:
    region = synthetic_region(square(landmark_xy(NASSAU), 1.0), 30)

    (reading,), _ = read_regions(synthetic_snapshot(outlook=[region]), landmark_location())

    assert not reading.covers


def test_only_development_regions_are_read() -> None:
    marker = OutlookArea(
        kind="seven_day_location",
        basin="Atlantic",
        chance_2day_pct=10,
        chance_7day_pct=30,
        risk_2day=None,
        risk_7day=None,
        outlook_stamp="gtwo_areas_synthetic",
        issued_at=SYNTHETIC_AT,
        geometry=Geometry(type="Point", coordinates=landmark_xy(MIAMI_DADE), crs=WGS84),
        provenance=synthetic_provenance(),
    )

    readings, unavailable = read_regions(synthetic_snapshot(outlook=[marker]), landmark_location())

    assert (readings, unavailable) == ((), ())


def test_a_region_left_with_no_area_is_an_unavailable_input() -> None:
    lon, lat = landmark_xy(MIAMI_DADE)
    flat = ((lon, lat), (lon + 1.0, lat), (lon + 2.0, lat), (lon, lat))
    region = synthetic_region(Geometry(type="Polygon", coordinates=(flat,), crs=WGS84), 20)

    readings, unavailable = read_regions(synthetic_snapshot(outlook=[region]), landmark_location())
    (missing,) = unavailable

    assert readings == ()
    assert missing.kind == "outlook_areas"
    assert missing.reason.startswith("the Atlantic development region is unusable")


def test_a_replay_snapshot_holds_no_outlook() -> None:
    readings, unavailable = read_regions(replay(IRMA, "36"), landmark_location())
    (missing,) = unavailable

    assert readings == ()
    assert missing.kind == "outlook_areas"
    assert missing.reason == "a replay snapshot holds no tropical weather outlook"


def test_the_recorded_atlantic_region_covers_its_representative_point_only() -> None:
    at_region, _ = read_regions(recorded_maps(), development_region_location())
    at_landmark, _ = read_regions(recorded_maps(), landmark_location())

    assert [(item.area.basin, item.covers, item.chance_7day_pct) for item in at_region] == [
        ("Atlantic", True, 20),
        ("Pacific", False, 100),
    ]
    assert not any(item.covers for item in at_landmark)
