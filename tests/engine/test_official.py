# tests/engine/test_official.py
"""Which official products cover a location: issue #10's rule and the segment coverage rule.

NWS alerts are synthetic, or the two recorded cases of issue #10 (the 2026-10-17 Rip
Current Statement and the register's FLC086 Coastal Flood Statement) and their
Hurricane Warning copies. Segments are synthetic lines placed whole degrees, or tenths of
one, from the Miami-Dade landmark, or the replay corpus's own.
"""

from datetime import timedelta

import pytest
from engine_support import (
    DORIAN,
    IRMA,
    MIAMI_DADE,
    NASSAU,
    SYNTHETIC_AT,
    landmark,
    landmark_location,
    line,
    offset,
    synthetic_alert,
    synthetic_segment,
    synthetic_storm,
)
from fixture_support import REGISTER_AFFECTED
from scenarios import (
    as_hurricane_warning,
    county_statement,
    miami_dade,
    recorded_maps,
    replay,
    rip_current,
)

from weatherbot.engine.geodesy import figure_of
from weatherbot.engine.geometry import nearest_on_line, place
from weatherbot.engine.official import (
    OUTSIDE_ZONES,
    alert_product,
    alert_products,
    segment_product,
    segment_products,
)
from weatherbot.models import WGS84, Geometry, OfficialProduct, RuleId, Thresholds

AS_OF = SYNTHETIC_AT


# NWS alerts (issue #10) --------------------------------------------------------------------


def test_an_alert_the_point_query_returned_covers_the_location() -> None:
    product = alert_product(synthetic_alert("Hurricane Warning"), landmark_location(), AS_OF)

    assert (product.covers, product.rule) == (True, RuleId.HURRICANE_WARNING)
    assert product.reason == "the point query returned it"
    assert product.found_by == ("point",)


@pytest.mark.parametrize("zone", ["FLZ173", "FLC086"], ids=["forecast-zone", "county-zone"])
def test_an_alert_whose_ugc_list_names_the_locations_zone_covers_it(zone: str) -> None:
    alert = synthetic_alert("Hurricane Warning", queries=("FLC086",), zones=("FLZ999", zone))

    product = alert_product(alert, landmark_location(), AS_OF)

    assert (product.covers, product.rule) == (True, RuleId.HURRICANE_WARNING)
    assert product.reason == f"its zone list names this location's zone {zone}"


def test_a_county_alert_outside_the_locations_zones_is_context_and_sets_no_level() -> None:
    alert = synthetic_alert("Hurricane Warning", queries=("FLC086",), zones=REGISTER_AFFECTED)

    product = alert_product(alert, landmark_location(), AS_OF)

    assert (product.covers, product.rule, product.reason) == (False, None, OUTSIDE_ZONES)
    assert product.zones == REGISTER_AFFECTED
    assert product.found_by == ("zone FLC086",)


def test_a_location_outside_nws_coverage_is_covered_only_by_the_point_query() -> None:
    nassau = landmark_location(NASSAU)
    zoned = synthetic_alert("Hurricane Warning", queries=("FLZ173",), zones=("FLZ173",))

    assert not alert_product(zoned, nassau, AS_OF).covers
    assert alert_product(synthetic_alert("Hurricane Warning"), nassau, AS_OF).covers


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"status": "Test"}, "its status is Test, not Actual"),
        ({"status": "Exercise"}, "its status is Exercise, not Actual"),
        ({"message_type": "Cancel"}, "it is a Cancel message"),
        ({"expires": AS_OF}, "it expired before the snapshot's instant"),
        ({"expires": AS_OF - timedelta(minutes=1)}, "it expired before the snapshot's instant"),
    ],
    ids=["test", "exercise", "cancel", "expires-now", "expired"],
)
def test_only_an_actual_unexpired_non_cancel_alert_counts(
    changes: dict[str, object], reason: str
) -> None:
    alert = synthetic_alert("Hurricane Warning", **changes)  # pyright: ignore[reportArgumentType] - keyword fields

    product = alert_product(alert, landmark_location(), AS_OF)

    assert (product.covers, product.rule, product.reason) == (False, None, reason)


@pytest.mark.parametrize("message_type", ["Alert", "Update"])
def test_an_alert_or_an_update_counts(message_type: str) -> None:
    alert = synthetic_alert("Hurricane Warning", message_type=message_type)

    assert alert_product(alert, landmark_location(), AS_OF).covers


@pytest.mark.parametrize(
    ("event", "rule"),
    [
        ("Hurricane Warning", RuleId.HURRICANE_WARNING),
        ("Tropical Storm Warning", RuleId.TROPICAL_STORM_WARNING),
        ("Hurricane Watch", RuleId.HURRICANE_WATCH),
        ("Tropical Storm Watch", RuleId.TROPICAL_STORM_WATCH),
    ],
)
def test_the_four_ladder_events_trigger_their_rules(event: str, rule: RuleId) -> None:
    assert alert_product(synthetic_alert(event), landmark_location(), AS_OF).rule == rule


@pytest.mark.parametrize(
    "event",
    [
        "Storm Surge Warning",
        "Storm Surge Watch",
        "Extreme Wind Warning",
        "Rip Current Statement",
        "hurricane warning",
        "Hurricane Warnings",
    ],
)
def test_any_other_covering_event_is_listed_and_sets_no_level(event: str) -> None:
    product = alert_product(synthetic_alert(event), landmark_location(), AS_OF)

    assert (product.covers, product.rule) == (True, None)
    assert product.reason.endswith("so it sets no level")


def test_an_alert_cites_a_zone_query_and_never_a_point_querys_url() -> None:
    both = synthetic_alert("Hurricane Warning", queries=("point", "FLZ173"), zones=("FLZ173",))
    point = synthetic_alert("Hurricane Warning")

    cited = alert_product(both, landmark_location(), AS_OF).citation
    uncited = alert_product(point, landmark_location(), AS_OF).citation

    assert (cited.source_id, cited.url is not None) == ("nws-alerts-zone", True)
    assert (uncited.source_id, uncited.url) == ("nws-alerts-point", None)


def test_every_alert_is_listed_in_the_snapshots_order() -> None:
    alerts = [
        synthetic_alert("Rip Current Statement"),
        synthetic_alert("Hurricane Warning", queries=("FLC086",), zones=REGISTER_AFFECTED),
    ]

    products = alert_products(alerts, landmark_location(), AS_OF)

    assert [(item.code, item.covers) for item in products] == [
        ("Rip Current Statement", True),
        ("Hurricane Warning", False),
    ]


# The two recorded cases --------------------------------------------------------------------


def test_the_recorded_rip_current_statement_covers_the_landmark_and_sets_no_level() -> None:
    as_of = recorded_maps().completed_at

    product = alert_product(rip_current(), miami_dade(), as_of)

    assert (product.covers, product.rule) == (True, None)
    assert product.found_by == ("point", "zone FLC086", "zone FLZ173")
    assert "FLZ173" in product.zones


def test_the_registers_county_statement_is_context_with_the_zones_it_covers() -> None:
    as_of = recorded_maps().completed_at

    product = alert_product(county_statement(), miami_dade(), as_of)

    assert (product.covers, product.rule, product.reason) == (False, None, OUTSIDE_ZONES)
    assert product.zones == REGISTER_AFFECTED
    assert product.found_by == ("zone FLC086",)


def test_their_hurricane_warning_copies_follow_the_same_rule() -> None:
    as_of = recorded_maps().completed_at
    location = miami_dade()

    covering = alert_product(as_hurricane_warning(rip_current()), location, as_of)
    outside = alert_product(as_hurricane_warning(county_statement()), location, as_of)

    assert (covering.covers, covering.rule) == (True, RuleId.HURRICANE_WARNING)
    assert (outside.covers, outside.rule, outside.reason) == (False, None, OUTSIDE_ZONES)


# NHC segments ------------------------------------------------------------------------------


def _segment(code: str, shape: Geometry) -> OfficialProduct | None:
    storm = synthetic_storm(segments=[synthetic_segment(code, shape)])
    return segment_product(storm, storm.watch_warnings[0], landmark_location(), Thresholds(), ())


def test_a_segment_alongside_the_location_within_the_reach_covers_it() -> None:
    # A tenth of a degree east of the landmark is about 10 km.
    product = _segment("HWR", line(offset(MIAMI_DADE, 0.1, -1.0), offset(MIAMI_DADE, 0.1, 1.0)))

    assert product is not None
    assert (product.covers, product.rule, product.at_end) == (True, RuleId.HURRICANE_WARNING, False)
    assert product.distance_km == pytest.approx(10.0, abs=0.5)
    assert product.crs == "EPSG:4326"
    assert "inside the segment" in product.reason


def test_a_segment_beyond_the_reach_does_not_cover() -> None:
    assert (
        _segment("HWR", line(offset(MIAMI_DADE, 0.3, -1.0), offset(MIAMI_DADE, 0.3, 1.0))) is None
    )


def test_a_segment_that_ends_short_of_the_location_covers_only_within_the_end_tolerance() -> None:
    # Ends about 3.3 km north (0.03 degrees), then about 11 km north (0.1 degrees).
    near = _segment("TWA", line(offset(MIAMI_DADE, 0.0, 1.0), offset(MIAMI_DADE, 0.0, 0.03)))
    short = _segment("TWA", line(offset(MIAMI_DADE, 0.0, 1.0), offset(MIAMI_DADE, 0.0, 0.1)))

    assert near is not None
    assert (near.at_end, near.rule) == (True, RuleId.TROPICAL_STORM_WATCH)
    assert "at its end" in near.reason
    assert short is None


def test_a_point_segment_covers_within_the_reach() -> None:
    point = Geometry(type="Point", coordinates=offset(MIAMI_DADE, 0.0, 0.1), crs=WGS84)

    product = _segment("HWA", point)

    assert product is not None
    assert (product.at_end, product.rule) == (False, RuleId.HURRICANE_WATCH)


def test_a_covering_segment_with_an_unknown_code_is_listed_and_sets_no_level() -> None:
    product = _segment("XYZ", line(offset(MIAMI_DADE, 0.1, -1.0), offset(MIAMI_DADE, 0.1, 1.0)))

    assert product is not None
    assert (product.covers, product.rule, product.code) == (True, None, "XYZ")
    assert product.reason.endswith("the code XYZ is unknown, so it sets no level")


def test_the_reach_and_the_end_tolerance_are_the_thresholds() -> None:
    storm = synthetic_storm(
        segments=[
            synthetic_segment(
                "HWR", line(offset(MIAMI_DADE, 0.0, 1.0), offset(MIAMI_DADE, 0.0, 0.1))
            )
        ]
    )
    segment = storm.watch_warnings[0]
    wide = Thresholds(segment_end_tolerance_km=12.0)

    assert segment_product(storm, segment, landmark_location(), Thresholds(), ()) is None
    assert segment_product(storm, segment, landmark_location(), wide, ()) is not None


def test_only_covering_segments_are_listed() -> None:
    storm = synthetic_storm(
        segments=[
            synthetic_segment("HWR", line(offset(MIAMI_DADE, 0.1, -1), offset(MIAMI_DADE, 0.1, 1))),
            synthetic_segment("TWR", line(offset(MIAMI_DADE, 2.0, -1), offset(MIAMI_DADE, 2.0, 1))),
        ]
    )

    products = segment_products([storm], landmark_location(), Thresholds(), ())

    assert [item.code for item in products] == ["HWR"]


def test_a_covering_segments_ends_are_named_from_the_catalogue() -> None:
    catalogue = recorded_maps().breakpoints
    ocean_reef, county_line = (
        next(item for item in catalogue if item.name == name)
        for name in ("Ocean Reef", "Miami-Dade/Broward County Line")
    )
    ends = [ocean_reef.position.coordinates, county_line.position.coordinates]
    shape = line(*(tuple(end[:2]) for end in ends))  # pyright: ignore[reportArgumentType] - points
    storm = synthetic_storm(segments=[synthetic_segment("HWR", shape)])

    product = segment_product(
        storm, storm.watch_warnings[0], landmark_location(), Thresholds(), catalogue
    )

    assert product is not None
    assert product.breakpoints == ("Ocean Reef", "Miami-Dade/Broward County Line")


# The replay corpus -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("storm", "advisory", "key", "code", "distance"),
    [
        (IRMA, "36", MIAMI_DADE, "HWR", 1.1),
        (IRMA, "34", MIAMI_DADE, "HWA", 1.1),
        (DORIAN, "30", NASSAU, "HWR", 3.8),
    ],
)
def test_the_replay_segments_cover_the_landmarks_on_the_archive_sphere(
    storm: str, advisory: str, key: str, code: str, distance: float
) -> None:
    snapshot = replay(storm, advisory)
    products = segment_products(snapshot.storms, landmark_location(key), Thresholds(), ())

    covering = [item for item in products if item.code == code]
    assert covering
    assert min(item.distance_km or 0.0 for item in covering) == pytest.approx(distance, abs=0.05)
    assert {item.crs for item in covering} == {"native (D_Sphere)"}
    assert all(not item.at_end for item in covering)


def test_the_dorian_032_tropical_storm_watch_ends_short_of_miami_dade() -> None:
    snapshot = replay(DORIAN, "32")
    point = landmark(MIAMI_DADE)
    watches = [s for s in snapshot.storms[0].watch_warnings if s.tcww.raw == "TWA"]
    measured = [
        nearest_on_line(place(point, s.geometry.crs), s.geometry, figure_of(s.geometry.crs))
        for s in watches
    ]
    nearest = min(measured, key=lambda found: found.distance_km)

    products = segment_products(snapshot.storms, landmark_location(MIAMI_DADE), Thresholds(), ())

    assert (nearest.at_end, round(nearest.distance_km, 1)) == (True, 22.6)
    assert [item for item in products if item.code == "TWA"] == []
