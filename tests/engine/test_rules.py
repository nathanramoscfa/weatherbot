# tests/engine/test_rules.py
"""The ladder: its levels, its eleven rules in order, its thresholds, and each rule's test.

Every rule is shown matching and not matching on synthetic live products built around
the Miami-Dade landmark at run time; the thresholds are the provisional defaults.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Literal, get_args

import pytest
from engine_support import (
    MIAMI_DADE,
    NASSAU,
    SYNTHETIC_AT,
    landmark_location,
    landmark_xy,
    line,
    offset,
    square,
    synthetic_alert,
    synthetic_region,
    synthetic_segment,
    synthetic_snapshot,
    synthetic_storm,
    synthetic_track,
    synthetic_wind,
)
from pydantic import ValidationError

from weatherbot.engine import RULES, Rule
from weatherbot.engine.assess import read
from weatherbot.models import (
    BAND_FLOORS,
    RULE_LEVELS,
    RULE_ORDER,
    WIND_PROBABILITY_BANDS,
    AlertLevel,
    BandFloor,
    Location,
    RuleId,
    Snapshot,
    Thresholds,
)

type Inputs = Callable[[], tuple[Snapshot, Location]]

ORDER = (
    "hurricane_warning",
    "tropical_storm_warning",
    "hurricane_watch",
    "evacuation_order",
    "tropical_storm_watch",
    "hurricane_cone",
    "hurricane_wind_probability",
    "storm_cone",
    "development_region",
    "tropical_storm_wind_probability",
    "all_clear",
)


# The ladder --------------------------------------------------------------------------------


def test_the_rule_ids_are_the_eleven_in_the_documented_order() -> None:
    assert tuple(str(rule) for rule in RuleId) == ORDER
    assert tuple(RuleId) == RULE_ORDER


def test_rules_hold_the_eleven_rules_in_the_ladder_order() -> None:
    assert tuple(rule.id for rule in RULES) == RULE_ORDER
    assert all(isinstance(rule, Rule) and rule.trigger for rule in RULES)


@pytest.mark.parametrize(
    ("rule", "level"),
    [
        ("hurricane_warning", 5),
        ("tropical_storm_warning", 4),
        ("hurricane_watch", 4),
        ("evacuation_order", 4),
        ("tropical_storm_watch", 3),
        ("hurricane_cone", 3),
        ("hurricane_wind_probability", 3),
        ("storm_cone", 2),
        ("development_region", 2),
        ("tropical_storm_wind_probability", 2),
        ("all_clear", 1),
    ],
)
def test_each_rule_sets_its_documented_level(rule: str, level: int) -> None:
    assert RULE_LEVELS[RuleId(rule)] == level
    assert next(item for item in RULES if item.id == rule).level == level


def test_the_levels_carry_the_briefs_names_and_actions() -> None:
    assert [(level.value, level.label, level.actions) for level in AlertLevel] == [
        (1, "All Clear", "Normal activities"),
        (2, "Tropical Storm Threat", "Monitor daily; review plans"),
        (3, "Watch / Hurricane Threat", "Stock supplies; pack; set an exit plan"),
        (
            4,
            "Warning / Watch / Evacuation",
            "Evacuate vulnerable areas; secure transport; assume routes close",
        ),
        (5, "Hurricane Warning", "Shelter if not evacuated; expect outages; follow local orders"),
    ]


def test_the_band_floors_are_the_band_lower_bounds() -> None:
    lowers = tuple(lower for lower, _ in WIND_PROBABILITY_BANDS.values())

    assert lowers == BAND_FLOORS
    assert get_args(BandFloor.__value__) == lowers


# Thresholds --------------------------------------------------------------------------------


def test_the_thresholds_default_to_the_provisional_values() -> None:
    assert Thresholds().model_dump() == {
        "coastal_reach_km": 25.0,
        "segment_end_tolerance_km": 5.0,
        "cone_horizon_h": 120,
        "hurricane_wind_floor_pct": 10,
        "tropical_storm_wind_floor_pct": 5,
        "development_chance_floor_pct": 0,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("coastal_reach_km", 0.0),
        ("coastal_reach_km", 200.0),
        ("segment_end_tolerance_km", 0.0),
        ("segment_end_tolerance_km", 50.0),
        ("cone_horizon_h", 1),
        ("cone_horizon_h", 120),
        *(("hurricane_wind_floor_pct", floor) for floor in BAND_FLOORS),
        ("tropical_storm_wind_floor_pct", 90),
        ("development_chance_floor_pct", 50),
    ],
)
def test_a_threshold_at_its_range_is_accepted(field: str, value: float) -> None:
    assert getattr(Thresholds.model_validate({field: value}), field) == value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("coastal_reach_km", -0.5),
        ("coastal_reach_km", 200.5),
        ("segment_end_tolerance_km", -1.0),
        ("segment_end_tolerance_km", 50.5),
        ("cone_horizon_h", 0),
        ("cone_horizon_h", 121),
        ("hurricane_wind_floor_pct", 15),
        ("tropical_storm_wind_floor_pct", 100),
        ("development_chance_floor_pct", -5),
    ],
)
def test_a_threshold_outside_its_range_is_refused(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Thresholds.model_validate({field: value})


def test_the_fingerprint_is_the_sha256_of_the_canonical_thresholds_and_rule_order() -> None:
    thresholds = Thresholds()
    document = {"rules": list(ORDER), "thresholds": thresholds.model_dump()}
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))

    assert thresholds.fingerprint() == hashlib.sha256(canonical.encode()).hexdigest()
    assert thresholds.fingerprint() == Thresholds().fingerprint()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("coastal_reach_km", 26.0),
        ("segment_end_tolerance_km", 4.0),
        ("cone_horizon_h", 96),
        ("hurricane_wind_floor_pct", 20),
        ("tropical_storm_wind_floor_pct", 10),
        ("development_chance_floor_pct", 10),
    ],
)
def test_the_fingerprint_changes_with_any_threshold(field: str, value: float) -> None:
    moved = Thresholds.model_validate({field: value})

    assert moved.fingerprint() != Thresholds().fingerprint()


def test_the_fingerprint_changes_with_the_rule_order() -> None:
    swapped = (RULE_ORDER[1], RULE_ORDER[0], *RULE_ORDER[2:])

    assert Thresholds().fingerprint(swapped) != Thresholds().fingerprint()


# Each rule, matching and not ---------------------------------------------------------------


def _miami(*, evacuation: bool = False) -> Location:
    return landmark_location(MIAMI_DADE, evacuation=evacuation)


def _alerted(event: str) -> Inputs:
    location = _miami()
    alert = synthetic_alert(event, queries=("FLZ173",), zones=("FLZ173",))
    return lambda: (synthetic_snapshot(alerts={location.name: (alert,)}), location)


def _segment(code: str, east_deg: float = 0.1) -> Inputs:
    # A north-south segment ``east_deg`` east of the landmark, running past it both ways.
    shape = line(offset(MIAMI_DADE, east_deg, -1.0), offset(MIAMI_DADE, east_deg, 1.0))
    storm = synthetic_storm(segments=[synthetic_segment(code, shape)])
    return lambda: (synthetic_snapshot(storms=[storm]), _miami())


def _cone(centre: str, winds: list[int | None], hours: int = 12) -> Inputs:
    # A forecast track over the landmark, ``hours`` after the snapshot.
    track = synthetic_track(
        SYNTHETIC_AT,
        [offset(MIAMI_DADE, 2.0, -2.0), landmark_xy(MIAMI_DADE), offset(MIAMI_DADE, -2.0, 2.0)],
        step=timedelta(hours=hours),
        winds_kt=winds,
    )
    storm = synthetic_storm(cone=square(landmark_xy(centre), 1.0), points=track)
    return lambda: (synthetic_snapshot(storms=[storm]), _miami())


def _band(threshold: Literal[34, 64], label: str, centre: str = MIAMI_DADE) -> Inputs:
    product = synthetic_wind(threshold, [(label, square(landmark_xy(centre), 0.5))])
    return lambda: (synthetic_snapshot(winds=[product]), _miami())


def _region(chance: int | None, centre: str = MIAMI_DADE) -> Inputs:
    region = synthetic_region(square(landmark_xy(centre), 1.0), chance)
    return lambda: (synthetic_snapshot(outlook=[region]), _miami())


MATCHING: dict[RuleId, tuple[Inputs, ...]] = {
    RuleId.HURRICANE_WARNING: (_alerted("Hurricane Warning"), _segment("HWR")),
    RuleId.TROPICAL_STORM_WARNING: (_alerted("Tropical Storm Warning"), _segment("TWR")),
    RuleId.HURRICANE_WATCH: (_alerted("Hurricane Watch"), _segment("HWA")),
    RuleId.EVACUATION_ORDER: (lambda: (synthetic_snapshot(), _miami(evacuation=True)),),
    RuleId.TROPICAL_STORM_WATCH: (_alerted("Tropical Storm Watch"), _segment("TWA")),
    RuleId.HURRICANE_CONE: (_cone(MIAMI_DADE, [100, 100, 90]), _cone(MIAMI_DADE, [64, 50, 40])),
    RuleId.HURRICANE_WIND_PROBABILITY: (_band(64, "10-20%"), _band(64, ">90%")),
    RuleId.STORM_CONE: (_cone(MIAMI_DADE, [40, 40, 40]), _cone(MIAMI_DADE, [100, 100, 100], 130)),
    RuleId.DEVELOPMENT_REGION: (_region(20), _region(0), _region(None)),
    RuleId.TROPICAL_STORM_WIND_PROBABILITY: (_band(34, "5-10%"), _band(34, "20-30%")),
}
NOT_MATCHING: dict[RuleId, tuple[Inputs, ...]] = {
    RuleId.HURRICANE_WARNING: (
        _alerted("Hurricane Watch"),
        _alerted("Storm Surge Warning"),
        _segment("HWR", east_deg=0.5),
    ),
    RuleId.TROPICAL_STORM_WARNING: (_alerted("Hurricane Warning"), _segment("TWA")),
    RuleId.HURRICANE_WATCH: (_alerted("Tropical Storm Watch"), _segment("HWR")),
    RuleId.EVACUATION_ORDER: (lambda: (synthetic_snapshot(), _miami()),),
    RuleId.TROPICAL_STORM_WATCH: (_alerted("Tropical Storm Warning"), _segment("XYZ")),
    RuleId.HURRICANE_CONE: (
        _cone(MIAMI_DADE, [63, 50, 40]),
        _cone(MIAMI_DADE, [100, 100, 100], 130),
        _cone(NASSAU, [100, 100, 100]),
    ),
    RuleId.HURRICANE_WIND_PROBABILITY: (
        _band(64, "5-10%"),
        _band(34, ">90%"),
        _band(64, ">90%", NASSAU),
    ),
    RuleId.STORM_CONE: (_cone(NASSAU, [40, 40, 40]), lambda: (synthetic_snapshot(), _miami())),
    RuleId.DEVELOPMENT_REGION: (_region(20, NASSAU),),
    RuleId.TROPICAL_STORM_WIND_PROBABILITY: (
        _band(34, "<5%"),
        _band(64, ">90%"),
        _band(34, ">90%", NASSAU),
    ),
}


def _rule(rule_id: RuleId) -> Rule:
    return next(rule for rule in RULES if rule.id == rule_id)


def _cases(table: dict[RuleId, tuple[Inputs, ...]]) -> list[tuple[RuleId, Inputs]]:
    return [(rule, inputs) for rule, items in table.items() for inputs in items]


def _label(case: object) -> str | None:
    return str(case) if isinstance(case, RuleId) else None


@pytest.mark.parametrize(("rule_id", "inputs"), _cases(MATCHING), ids=_label)
def test_each_rule_matches_its_trigger(rule_id: RuleId, inputs: Inputs) -> None:
    snapshot, location = inputs()
    readings, _ = read(snapshot, location, Thresholds())

    matches = _rule(rule_id).evaluate(readings)

    assert matches
    assert {item.rule for item in matches} == {rule_id}


@pytest.mark.parametrize(("rule_id", "inputs"), _cases(NOT_MATCHING), ids=_label)
def test_each_rule_does_not_match_without_its_trigger(rule_id: RuleId, inputs: Inputs) -> None:
    snapshot, location = inputs()
    readings, _ = read(snapshot, location, Thresholds())

    assert _rule(rule_id).evaluate(readings) == ()


def test_every_rule_but_all_clear_has_matching_and_non_matching_cases() -> None:
    expected = set(RuleId) - {RuleId.ALL_CLEAR}

    assert set(MATCHING) == expected
    assert set(NOT_MATCHING) == expected


def test_all_clear_never_matches() -> None:
    for inputs in (*MATCHING[RuleId.HURRICANE_WARNING], *MATCHING[RuleId.STORM_CONE]):
        snapshot, location = inputs()
        readings, _ = read(snapshot, location, Thresholds())

        assert _rule(RuleId.ALL_CLEAR).evaluate(readings) == ()


def test_the_cone_horizon_and_the_floors_follow_the_thresholds() -> None:
    late = _cone(MIAMI_DADE, [100, 100, 100], 72)  # the approach comes 72 h after the snapshot
    snapshot, location = late()
    wide, _ = read(snapshot, location, Thresholds(cone_horizon_h=72))
    narrow, _ = read(snapshot, location, Thresholds(cone_horizon_h=71))

    assert _rule(RuleId.HURRICANE_CONE).evaluate(wide)
    assert not _rule(RuleId.HURRICANE_CONE).evaluate(narrow)

    snapshot, location = _band(64, "5-10%")()
    low, _ = read(snapshot, location, Thresholds(hurricane_wind_floor_pct=5))
    assert _rule(RuleId.HURRICANE_WIND_PROBABILITY).evaluate(low)

    snapshot, location = _region(20)()
    high, _ = read(snapshot, location, Thresholds(development_chance_floor_pct=30))
    assert not _rule(RuleId.DEVELOPMENT_REGION).evaluate(high)

    snapshot, location = _region(None)()
    unstated, _ = read(snapshot, location, Thresholds(development_chance_floor_pct=10))
    assert not _rule(RuleId.DEVELOPMENT_REGION).evaluate(unstated)


def test_a_cone_without_forecast_points_matches_only_the_storm_cone() -> None:
    storm = synthetic_storm(cone=square(landmark_xy(MIAMI_DADE), 1.0))
    location = _miami()
    snapshot = synthetic_snapshot(storms=[storm], alerts={location.name: ()})
    readings, unavailable = read(snapshot, location, Thresholds())

    assert not _rule(RuleId.HURRICANE_CONE).evaluate(readings)
    (match,) = _rule(RuleId.STORM_CONE).evaluate(readings)
    assert match.closest_approach_at is None
    assert [item.kind for item in unavailable] == [
        "forecast_points",
        "arrival_times",
        "arrival_times",
    ]


def test_an_approach_already_past_counts_as_now() -> None:
    # The track passed over the landmark 36 h before the snapshot.
    track = synthetic_track(
        SYNTHETIC_AT - timedelta(hours=48),
        [offset(MIAMI_DADE, 2.0, -2.0), landmark_xy(MIAMI_DADE), offset(MIAMI_DADE, -2.0, 2.0)],
        winds_kt=[100, 100, 100],
    )
    storm = synthetic_storm(cone=square(landmark_xy(MIAMI_DADE), 1.0), points=track)
    readings, _ = read(synthetic_snapshot(storms=[storm]), _miami(), Thresholds(cone_horizon_h=1))

    (match,) = _rule(RuleId.HURRICANE_CONE).evaluate(readings)
    assert match.lead_h == 0.0
    assert match.closest_approach_at == SYNTHETIC_AT - timedelta(hours=36)
