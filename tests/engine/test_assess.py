# tests/engine/test_assess.py
"""``assess``: every scenario's level, the first match, the evidence, and honest floors.

The scenarios come from ``scenarios.py``; the rest are synthetic live snapshots built
around the Miami-Dade landmark, or around a ``synthetic_coordinates()`` point for the
privacy test, at run time.
"""

import logging
import re
from datetime import timedelta

import pytest
from engine_support import (
    IRMA,
    MIAMI_DADE,
    MIAMI_DADE_ZONES,
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
from scenarios import SCENARIOS, Scenario, rebuilt, recorded_maps, replay, replay_miami_dade

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.engine import RULES, assess
from weatherbot.engine.assess import read
from weatherbot.models import (
    RULE_LEVELS,
    WGS84,
    AlertQuery,
    Assessment,
    BreakpointSpan,
    Geometry,
    LatLon,
    Location,
    NwsAlert,
    Provenance,
    RuleId,
    Snapshot,
    SourceOutcome,
    Thresholds,
)

DECIMAL_COORDINATE = re.compile(r"\d+\.\d{3,}")


def _ids(scenario: Scenario) -> str:
    return scenario.name


# Scenarios ---------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_ids)
def test_every_scenario_gives_its_level_rule_and_completeness(scenario: Scenario) -> None:
    snapshot, location = scenario.inputs()

    assessment = assess(snapshot, location, Thresholds())

    assert (assessment.level, assessment.rule, assessment.complete) == (
        scenario.level,
        scenario.rule,
        scenario.complete,
    )
    assert scenario.level == RULE_LEVELS[scenario.rule]
    assert all(item.rule == scenario.rule for item in assessment.evidence)


def test_the_scenarios_are_named_once() -> None:
    names = [scenario.name for scenario in SCENARIOS]

    assert len(names) == len(set(names))


def test_the_partial_scenario_lists_nws_alerts_as_unavailable() -> None:
    snapshot, location = next(s for s in SCENARIOS if s.name == "partial-alerts-failed").inputs()

    assessment = assess(snapshot, location, Thresholds())
    (missing,) = assessment.unavailable

    assert missing.kind == "nws_alerts"
    assert missing.reason == (
        "NWS alerts were not checked: nws-alerts-point failed (SourceHttpError); "
        "nws-alerts-zone failed (SourceHttpError)"
    )
    assert not assessment.complete


# What an assessment records ----------------------------------------------------------------


def test_a_live_assessment_records_its_snapshot_instant_and_thresholds() -> None:
    snapshot = recorded_maps()
    thresholds = Thresholds(coastal_reach_km=30.0)
    location = landmark_location()

    assessment = assess(snapshot, location, thresholds)

    assert (assessment.snapshot_id, assessment.origin) == (snapshot.snapshot_id, "live")
    assert assessment.as_of == snapshot.completed_at
    assert assessment.location_name == location.name
    assert assessment.thresholds == thresholds
    assert assessment.ruleset == thresholds.fingerprint()
    assert Assessment.model_validate_json(assessment.model_dump_json()) == assessment


def test_a_replay_assessment_is_as_of_its_advisorys_issuance() -> None:
    snapshot = replay(IRMA, "36")
    cone = snapshot.storms[0].cone

    assessment = assess(snapshot, replay_miami_dade(), Thresholds())

    assert cone is not None
    assert (assessment.origin, assessment.as_of) == ("replay", cone.advisory.issued_at)


def test_the_first_matching_rule_decides_and_its_matches_are_the_evidence() -> None:
    snapshot, location = replay(IRMA, "36"), replay_miami_dade()
    readings, _ = read(snapshot, location, Thresholds())
    matched = [rule.id for rule in RULES if rule.evaluate(readings)]

    assessment = assess(snapshot, location, Thresholds())

    assert matched[:2] == [RuleId.HURRICANE_WARNING, RuleId.HURRICANE_CONE]
    assert RuleId.HURRICANE_WIND_PROBABILITY in matched
    assert assessment.rule == matched[0]
    assert assessment.evidence == RULES[0].evaluate(readings)


def test_two_matching_rules_the_earlier_decides_in_whatever_order_the_rules_run() -> None:
    location = landmark_location(evacuation=True)
    alert = synthetic_alert("Hurricane Warning")
    snapshot = synthetic_snapshot(alerts={location.name: (alert,)})
    toggle_first = (RULES[3], *RULES[:3], *RULES[4:])

    ladder = assess(snapshot, location, Thresholds())
    reordered = assess(snapshot, location, Thresholds(), rules=toggle_first)
    without = assess(snapshot, location, Thresholds(), rules=RULES[1:])

    assert (ladder.rule, reordered.rule, without.rule) == (
        RuleId.HURRICANE_WARNING,
        RuleId.EVACUATION_ORDER,
        RuleId.EVACUATION_ORDER,
    )
    assert reordered.ruleset == Thresholds().fingerprint(rule.id for rule in toggle_first)
    assert ladder.ruleset not in {reordered.ruleset, without.ruleset}
    assert reordered.ruleset != without.ruleset


def test_all_clear_has_no_evidence_and_lists_what_it_considered() -> None:
    assessment = assess(recorded_maps(), landmark_location(), Thresholds())

    assert (assessment.rule, assessment.evidence) == (RuleId.ALL_CLEAR, ())
    assert [item.threshold_kt for item in assessment.wind_probabilities] == [34, 50, 64]
    assert assessment.breakpoint_span is not None


def test_official_lists_every_alert_and_every_covering_segment() -> None:
    location = landmark_location()
    alerts = (
        synthetic_alert("Rip Current Statement"),
        synthetic_alert("Hurricane Watch", queries=("FLC086",), zones=("FLZ069",)),
    )
    segments = [
        synthetic_segment("TWR", line(offset(MIAMI_DADE, 0.1, -1), offset(MIAMI_DADE, 0.1, 1))),
        synthetic_segment("HWR", line(offset(MIAMI_DADE, 3.0, -1), offset(MIAMI_DADE, 3.0, 1))),
    ]
    snapshot = synthetic_snapshot(
        storms=[synthetic_storm(segments=segments)], alerts={location.name: alerts}
    )

    assessment = assess(snapshot, location, Thresholds())

    assert [(item.code, item.covers, item.rule) for item in assessment.official] == [
        ("Rip Current Statement", True, None),
        ("Hurricane Watch", False, None),
        ("TWR", True, RuleId.TROPICAL_STORM_WARNING),
    ]
    assert assessment.rule == RuleId.TROPICAL_STORM_WARNING


# Honest floors -----------------------------------------------------------------------------


def _alerted(location: Location) -> dict[str, tuple[NwsAlert, ...]]:
    return {location.name: ()}


@pytest.mark.parametrize("source", ["nhc-current-storms", "nhc-map-tropical-summary"])
def test_a_failed_roster_or_map_source_is_unavailable(source: str) -> None:
    location = landmark_location()
    storm = synthetic_storm()  # the map source drew nothing for it
    snapshot = synthetic_snapshot(
        storms=[storm] if source != "nhc-current-storms" else [],
        alerts=_alerted(location),
        failed=[source],  # pyright: ignore[reportArgumentType] - a source id
    )

    assessment = assess(snapshot, location, Thresholds())
    (missing,) = [item for item in assessment.unavailable if item.kind == "source"]
    others = {item.kind for item in assessment.unavailable} - {"source"}

    assert (missing.kind, missing.source_id) == ("source", source)
    assert missing.reason.startswith(f"{source} failed (SourceHttpError), so ")
    assert (assessment.rule, assessment.complete) == (RuleId.ALL_CLEAR, False)
    # A storm the failed map source drew nothing for lacks its arrival products, but its
    # forecast points are not listed again.
    assert others == ({"arrival_times"} if source == "nhc-map-tropical-summary" else set())


def test_a_failed_breakpoint_catalogue_leaves_the_level_complete() -> None:
    location = landmark_location()
    snapshot = synthetic_snapshot(alerts=_alerted(location), failed=["nhc-map-breakpoints"])

    assessment = assess(snapshot, location, Thresholds())

    assert (assessment.complete, assessment.breakpoint_span) == (True, None)


THREAT_INPUTS = ["forecast_points", "arrival_times", "arrival_times"]
"""What a storm with no forecast points and no arrival products also lacks."""


def test_a_storm_without_a_cone_is_unavailable() -> None:
    location = landmark_location()
    snapshot = synthetic_snapshot(storms=[synthetic_storm()], alerts=_alerted(location))

    missing, *rest = assess(snapshot, location, Thresholds()).unavailable

    assert (missing.kind, missing.atcf_id, missing.storm_name) == ("cone", "CP012026", "Synthetic")
    assert [item.kind for item in rest] == THREAT_INPUTS


def test_a_cone_left_with_no_area_is_unavailable() -> None:
    location = landmark_location()
    lon, lat = landmark_xy(MIAMI_DADE)
    flat = Geometry(
        type="Polygon",
        coordinates=(((lon, lat), (lon + 1.0, lat), (lon + 2.0, lat), (lon, lat)),),
        crs=WGS84,
    )
    snapshot = synthetic_snapshot(storms=[synthetic_storm(cone=flat)], alerts=_alerted(location))

    missing, *rest = assess(snapshot, location, Thresholds()).unavailable

    assert missing.kind == "cone"
    assert "is unusable: repaired by shapely.make_valid" in missing.reason
    assert [item.kind for item in rest] == THREAT_INPUTS


@pytest.mark.parametrize(
    ("outcomes", "reason"),
    [
        ({}, "the snapshot holds no alert list for this location"),
        (
            {"nws-alerts-zone": ("skipped", "no location inside NWS coverage")},
            "nws-alerts-zone was skipped (no location inside NWS coverage)",
        ),
    ],
    ids=["not-asked", "skipped"],
)
def test_nws_alerts_for_a_covered_location_without_a_list_are_unavailable(
    outcomes: dict[str, tuple[str, str]], reason: str
) -> None:
    snapshot = synthetic_snapshot()
    replaced = tuple(
        SourceOutcome(
            source_id=item.source_id, status="skipped", reason=outcomes[item.source_id][1]
        )
        if item.source_id in outcomes
        else item
        for item in snapshot.source_outcomes
    )
    snapshot = rebuilt(snapshot, source_outcomes=replaced)

    (missing,) = assess(snapshot, landmark_location(), Thresholds()).unavailable

    assert (missing.kind, missing.reason) == (
        "nws_alerts",
        f"NWS alerts were not checked: {reason}",
    )


def test_a_location_outside_nws_coverage_needs_no_alerts() -> None:
    nassau = Location(name="Nassau landmark", point=landmark_location("nassau").point)

    assessment = assess(synthetic_snapshot(), nassau, Thresholds())

    assert (assessment.unavailable, assessment.complete) == ((), True)


def test_a_replay_assessment_names_the_alerts_outlook_and_arrivals_it_could_not_check() -> None:
    snapshot = replay(IRMA, "36")
    name = snapshot.storms[0].name
    assessment = assess(snapshot, replay_miami_dade(), Thresholds())
    track = "so that arrival reads the forecast track's closest approach"

    assert [(item.kind, item.reason) for item in assessment.unavailable] == [
        ("nws_alerts", "NWS alerts were not checked: a replay snapshot holds no NWS alerts"),
        ("outlook_areas", "a replay snapshot holds no tropical weather outlook"),
        *(
            (
                "arrival_times",
                (
                    f"the snapshot holds no {kind} arrival-time product for {name} "
                    f"(the corpus holds no arrival-time products), {track}"
                ),
            )
            for kind in ("earliest-reasonable", "most-likely")
        ),
    ]


# The breakpoint span -----------------------------------------------------------------------


def test_the_span_comes_from_the_snapshots_catalogue_else_from_the_location() -> None:
    stored = BreakpointSpan(names=("Stored",), country="Testland", is_region=True)
    location = rebuilt(replay_miami_dade(), breakpoint_span=stored)

    live = assess(recorded_maps(), location, Thresholds())
    replayed = assess(replay(IRMA, "36"), location, Thresholds())
    bare = assess(replay(IRMA, "36"), replay_miami_dade(), Thresholds())

    assert live.breakpoint_span is not None
    assert live.breakpoint_span.names == ("Ocean Reef", "Miami-Dade/Broward County Line")
    assert replayed.breakpoint_span == stored
    assert bare.breakpoint_span is None


# Privacy and purity ------------------------------------------------------------------------


@pytest.fixture
def coordinates() -> tuple[str, str]:
    """A synthetic latitude and longitude, far from every landmark."""
    return synthetic_coordinates(load_landmarks(), ())


def _located_alert(coordinates: tuple[str, str]) -> NwsAlert:
    """A Hurricane Warning the point query returned, its URL carrying the coordinates."""
    lat, lon = coordinates
    alert = synthetic_alert("Hurricane Warning")
    query = AlertQuery(
        kind="point",
        provenance=Provenance(
            source_id="nws-alerts-point",
            url=f"https://api.weather.gov/alerts/active?point={lat},{lon}",
            status=200,
            fetched_at=SYNTHETIC_AT,
            sha256="1" * 64,
        ),
    )
    return rebuilt(alert, found_by=(query,))


def _surrounded(coordinates: tuple[str, str]) -> tuple[Snapshot, Location]:
    """Every product kind covering a synthetic location, and the location itself."""
    lat, lon = (float(value) for value in coordinates)
    centre = (lon, lat)
    location = Location(
        name="Synthetic place",
        point=LatLon(latitude=lat, longitude=lon),
        nws=MIAMI_DADE_ZONES,
        evacuation_order_in_effect=True,
    )
    track = synthetic_track(
        SYNTHETIC_AT,
        [(lon + 2.0, lat - 2.0), (lon + 0.05, lat), (lon - 2.0, lat + 2.0)],
        winds_kt=[100, 100, 90],
    )
    alongside = line((lon + 0.1, lat - 1.0), (lon + 0.1, lat + 1.0))
    segments = [synthetic_segment(code, alongside) for code in ("HWR", "TWR", "HWA", "TWA")]
    storm = synthetic_storm(cone=square(centre, 1.0), points=track, segments=segments)
    winds = [
        synthetic_wind(34, [(">90%", square(centre, 0.5))]),
        synthetic_wind(64, [("50-60%", square(centre, 0.5))]),
    ]
    snapshot = synthetic_snapshot(
        storms=[storm],
        winds=winds,
        outlook=[synthetic_region(square(centre, 1.0), 40)],
        alerts={location.name: (_located_alert(coordinates),)},
    )
    return snapshot, location


def _leaks(text: str, coordinates: tuple[str, str]) -> list[str]:
    lat, lon = coordinates
    renderings = {lat, lon, str(float(lat)), str(float(lon)), lat.lstrip("-"), lon.lstrip("-")}
    return sorted(value for value in renderings if value in text)


def test_no_evidence_field_or_detail_carries_the_locations_coordinates(
    coordinates: tuple[str, str],
) -> None:
    snapshot, location = _surrounded(coordinates)
    readings, _ = read(snapshot, location, Thresholds())
    evidence = [item for rule in RULES for item in rule.evaluate(readings)]
    assessment = assess(snapshot, location, Thresholds())

    rendered = [item.model_dump_json() for item in evidence] + [assessment.model_dump_json()]

    assert {item.rule for item in evidence} == set(RuleId) - {RuleId.ALL_CLEAR}
    assert not [text for text in rendered if _leaks(text, coordinates)]
    assert not [item.detail for item in evidence if DECIMAL_COORDINATE.search(item.detail)]
    assert assessment.official[0].citation.url is None
    # The coordinates are in the snapshot, so the check would catch them.
    assert _leaks(snapshot.model_dump_json(), coordinates)


def test_the_engine_logs_nothing(
    caplog: pytest.LogCaptureFixture, coordinates: tuple[str, str]
) -> None:
    inputs = [
        _surrounded(coordinates),
        (recorded_maps(), landmark_location()),
        (replay(IRMA, "36"), replay_miami_dade()),
    ]

    with caplog.at_level(logging.DEBUG):
        for snapshot, location in inputs:
            assess(snapshot, location, Thresholds())

    assert caplog.records == []


def test_assessing_twice_gives_the_same_assessment() -> None:
    snapshot, location = replay(IRMA, "22"), replay_miami_dade()

    first = assess(snapshot, location, Thresholds())

    assert assess(snapshot, location, Thresholds()) == first
    assert first.evidence[0].lead_h is not None
    assert first.evidence[0].closest_approach_at == first.as_of + timedelta(
        hours=first.evidence[0].lead_h
    )
