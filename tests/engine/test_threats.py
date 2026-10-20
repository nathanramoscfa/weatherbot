# tests/engine/test_threats.py
"""``threats_for``: one threat per storm, read from each storm's own advisory products.

The replay anchors are Irma 036 and Dorian 030 at both public landmarks, through the
committed corpus; the live cases are the recorded snapshot and synthetic storms built
around the Nassau landmark.
"""

import re
from datetime import timedelta
from typing import TYPE_CHECKING, cast

import pytest
from engine_support import (
    DORIAN,
    IRMA,
    NASSAU,
    SYNTHETIC_AT,
    landmark_location,
    landmark_xy,
    line,
    offset,
    square,
    synthetic_arrivals,
    synthetic_snapshot,
    synthetic_storm,
    synthetic_track,
)
from scenarios import nassau, rebuilt, recorded, replay, replay_miami_dade

from weatherbot.engine import assess
from weatherbot.engine.arrivals import NO_CENTER, NO_TRACK
from weatherbot.engine.geodesy import distance_km, figure_of, initial_bearing_deg
from weatherbot.engine.geometry import place
from weatherbot.engine.threats import threats_for
from weatherbot.models import Location, RuleId, Snapshot, StormThreat, Thresholds
from weatherbot.models.arrivals import MAP_LAYER_REASON

if TYPE_CHECKING:
    from collections.abc import Sequence

LOCATED_FIELDS = (
    "distance_km",
    "bearing_deg",
    "closest_approach_at",
    "closest_approach_km",
    "lead_h",
)


def threat_of(snapshot: Snapshot, location: Location) -> StormThreat:
    (threat,) = threats_for(snapshot, location, snapshot.completed_at)
    return threat


# The replay anchors -----------------------------------------------------------------------


def test_irma_036_is_a_category_5_threat_whose_cone_covers_only_the_miami_dade_landmark() -> None:
    snapshot = replay(IRMA, "36")

    miami = threat_of(snapshot, replay_miami_dade())
    bahamas = threat_of(snapshot, nassau())

    for threat in (miami, bahamas):
        assert (threat.atcf_id, threat.storm_name, str(threat.advisory)) == (IRMA, "Irma", "36")
        assert threat.issued_at == snapshot.completed_at
        assert (threat.category, threat.development) == (5, "Major Hurricane")
        assert threat.crs == "native (D_Sphere)"
        assert threat.hurricane_by_approach is True
    assert (miami.in_cone, bahamas.in_cone) == (True, False)
    assert miami.closest_approach_km == pytest.approx(38.9, abs=0.1)


def test_dorian_030_s_cone_covers_neither_landmark_while_its_warning_sets_nassau_s_level() -> None:
    snapshot = replay(DORIAN, "30")

    miami = threat_of(snapshot, replay_miami_dade())
    bahamas = threat_of(snapshot, nassau())
    level = assess(snapshot, nassau(), Thresholds())

    assert (miami.in_cone, bahamas.in_cone) == (False, False)
    assert (miami.category, bahamas.category) == (4, 4)
    assert level.rule == RuleId.HURRICANE_WARNING
    assert level.threats == (bahamas,)


@pytest.mark.parametrize(("storm", "advisory"), [(IRMA, "36"), (DORIAN, "30")])
@pytest.mark.parametrize("which", ["miami-dade", "nassau"])
def test_distance_and_bearing_are_measured_from_the_tau_0_center(
    storm: str, advisory: str, which: str
) -> None:
    snapshot = replay(storm, advisory)
    location = replay_miami_dade() if which == "miami-dade" else nassau()
    first = min(snapshot.storms[0].track_points, key=lambda point: point.valid_at)
    crs = first.position.crs
    coordinates = cast("Sequence[float]", first.position.coordinates)
    center, here = (coordinates[0], coordinates[1]), place(location.point, crs)

    threat = threat_of(snapshot, location)

    assert first.tau_h == 0
    assert threat.distance_km == distance_km(center, here, figure_of(crs))
    assert threat.bearing_deg == initial_bearing_deg(center, here, figure_of(crs))
    assert threat.lead_h is not None
    assert threat.closest_approach_at is not None
    expected = max(0.0, (threat.closest_approach_at - snapshot.completed_at).total_seconds() / 3600)
    assert threat.lead_h == pytest.approx(expected)


def test_an_approach_already_past_counts_as_now() -> None:
    # Dorian 036 had passed its closest approach to the Nassau landmark at tau 0.
    snapshot = replay(DORIAN, "36")

    threat = threat_of(snapshot, nassau())

    assert threat.lead_h == 0.0
    assert threat.closest_approach_km == pytest.approx(threat.distance_km)


# Live storms ------------------------------------------------------------------------------


def test_the_recorded_snapshot_has_one_threat_per_storm_in_its_order() -> None:
    full = recorded().snapshot
    location = landmark_location()

    threats = threats_for(full, location, full.completed_at)

    assert [threat.atcf_id for threat in threats] == [storm.atcf_id for storm in full.storms]
    simon, stand_in = threats
    summary = full.storms[0].summary
    assert summary is not None
    assert simon.advisory == summary.public_advisory.advisory
    assert (simon.category, simon.development) == (2, "Hurricane")
    assert simon.earliest_arrival.reason == MAP_LAYER_REASON
    # The stand-in carries the archived KMZ pair but no forecast points of its own.
    assert stand_in.distance_km is None
    assert (stand_in.earliest_arrival.reading, stand_in.earliest_arrival.reason) == (
        "unresolved",
        NO_CENTER,
    )


def test_a_storm_without_points_has_its_measured_parts_unresolved() -> None:
    location = landmark_location(NASSAU)
    storm = synthetic_storm(cone=square(landmark_xy(NASSAU), 1.0))
    snapshot = synthetic_snapshot(storms=[storm])

    threat = threat_of(snapshot, location)
    assessment = assess(snapshot, location, Thresholds())

    assert threat.in_cone is True
    assert all(getattr(threat, name) is None for name in LOCATED_FIELDS)
    assert (threat.category, threat.development, threat.hurricane_by_approach) == (None, None, None)
    for reading in (threat.earliest_arrival, threat.most_likely_arrival):
        assert (reading.origin, reading.reading, reading.reason) == (
            "track",
            "unresolved",
            NO_TRACK,
        )
    kinds = [(item.kind, item.atcf_id) for item in assessment.unavailable]
    assert ("forecast_points", storm.atcf_id) in kinds


def test_a_storm_without_a_cone_is_neither_in_nor_out_of_it() -> None:
    track = synthetic_track(SYNTHETIC_AT, [offset(NASSAU, 2.0), offset(NASSAU, -2.0)])
    snapshot = synthetic_snapshot(storms=[synthetic_storm(points=track)])

    threat = threat_of(snapshot, landmark_location(NASSAU))

    assert threat.in_cone is None
    assert threat.distance_km is not None


def test_a_storm_with_a_product_reads_it_from_its_center() -> None:
    center = offset(NASSAU, -4.0)
    track = synthetic_track(SYNTHETIC_AT, [center, offset(NASSAU, 2.0)], winds_kt=[70, 70])
    corners = [
        offset(NASSAU, -5, -3),
        offset(NASSAU, 1, -3),
        offset(NASSAU, 1, 3),
        offset(NASSAU, -5, 3),
    ]
    product = synthetic_arrivals(
        [
            ("Tue 2 pm", line(offset(NASSAU, -3.0, -2.9), offset(NASSAU, -3.0, 2.9))),
            (None, line(*corners, corners[0])),
        ]
    )
    storm = synthetic_storm(points=track, arrivals=[product])
    snapshot = synthetic_snapshot(storms=[storm])

    threat = threat_of(snapshot, landmark_location(NASSAU))
    assessment = assess(snapshot, landmark_location(NASSAU), Thresholds())

    assert (threat.earliest_arrival.origin, threat.earliest_arrival.reading) == ("kmz", "after")
    assert threat.most_likely_arrival.origin == "track"
    missing = [item for item in assessment.unavailable if item.kind == "arrival_times"]
    assert len(missing) == 1
    assert "most-likely" in missing[0].reason


# What a threat never holds ----------------------------------------------------------------


def test_no_threat_field_holds_a_wind_speed_probability() -> None:
    names = set(StormThreat.model_fields)

    assert not {name for name in names if re.search(r"prob|pct|percent|band", name)}


def test_a_threat_s_located_values_stay_out_of_its_repr() -> None:
    threat = threat_of(replay(IRMA, "36"), replay_miami_dade())
    text = repr(threat)

    assert not [name for name in LOCATED_FIELDS if f"{name}=" in text]
    assert f"{threat.distance_km}" not in text
    for reading in (threat.earliest_arrival, threat.most_likely_arrival):
        assert "approach_at=" not in repr(reading)


def test_the_assessment_carries_the_threats_and_they_never_change_the_level() -> None:
    snapshot, location = replay(IRMA, "22"), replay_miami_dade()

    assessment = assess(snapshot, location, Thresholds())

    assert assessment.threats == threats_for(snapshot, location, snapshot.completed_at)
    assert assessment.rule == RuleId.HURRICANE_CONE
    assert assessment.threats[0].lead_h == assessment.evidence[0].lead_h
    assert assessment.threats[0].closest_approach_at == assessment.evidence[0].closest_approach_at
    approach_at, lead_h = assessment.threats[0].closest_approach_at, assessment.threats[0].lead_h
    assert approach_at is not None
    assert lead_h is not None
    assert approach_at - assessment.as_of == timedelta(hours=lead_h)


@pytest.mark.parametrize(
    ("outcome", "why"),
    [
        ("failed", "nhc-arrival-times failed (SourceHttpError)"),
        (None, "nhc-arrival-times was not asked"),
    ],
    ids=["failed", "not-asked"],
)
def test_a_missing_product_names_what_the_arrival_source_answered(
    outcome: str | None, why: str
) -> None:
    track = synthetic_track(SYNTHETIC_AT, [offset(NASSAU, 2.0), offset(NASSAU, -2.0)])
    snapshot = synthetic_snapshot(
        storms=[synthetic_storm(points=track)],
        failed=("nhc-arrival-times",) if outcome == "failed" else (),
    )
    if outcome is None:
        kept = tuple(o for o in snapshot.source_outcomes if o.source_id != "nhc-arrival-times")
        snapshot = rebuilt(snapshot, source_outcomes=kept)

    assessment = assess(snapshot, landmark_location(NASSAU), Thresholds())

    reasons = [item.reason for item in assessment.unavailable if item.kind == "arrival_times"]
    assert len(reasons) == 2  # noqa: PLR2004 - both kinds
    assert all(f"({why})" in reason for reason in reasons)
