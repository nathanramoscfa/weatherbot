# tests/engine/test_tracks.py
"""A forecast track's closest approach: Irma 036 on the archive sphere, and synthetic tracks."""

from datetime import UTC, datetime, timedelta

import pytest
from engine_support import IRMA, landmark, replay_track, synthetic_track

from weatherbot.engine.geodesy import distance_km, figure_of
from weatherbot.engine.geometry import Approach, closest_approach, place
from weatherbot.models import WGS84

START = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)


def test_irma_036_passes_the_miami_dade_landmark_between_its_48_and_72_hour_points() -> None:
    points = replay_track(IRMA, "036")
    by_tau = {point.tau_h: point for point in points}
    crs = points[0].position.crs
    figure = figure_of(crs)

    approach = closest_approach(points, place(landmark("miami-dade"), crs), figure)

    assert figure.is_sphere
    assert approach.distance_km == pytest.approx(38.9, abs=0.5)
    assert by_tau[48].valid_at < approach.instant < by_tau[72].valid_at
    assert 48.0 < approach.lead_h < 72.0  # noqa: PLR2004 - the bracketing points
    assert approach.lead_h == (approach.instant - by_tau[0].valid_at).total_seconds() / 3600


def test_a_straight_pass_is_nearest_midway_and_nearer_than_either_point() -> None:
    point = landmark("nassau")
    lon, lat = point.longitude, point.latitude
    position = place(point, WGS84)
    figure = figure_of(WGS84)
    track = synthetic_track(START, [(lon - 2.0, lat - 1.0), (lon + 2.0, lat - 1.0)])

    approach = closest_approach(track, position, figure)

    assert approach.distance_km < distance_km(position, (lon - 2.0, lat - 1.0), figure)
    assert approach.distance_km < distance_km(position, (lon + 2.0, lat - 1.0), figure)
    assert approach.distance_km == pytest.approx(111.0, abs=2.0)
    # By symmetry the nearest point is the edge's midpoint, six hours in.
    assert abs(approach.instant - (START + timedelta(hours=6))) < timedelta(seconds=1)
    assert approach.lead_h == pytest.approx(6.0, abs=1e-3)


def test_a_stationary_storm_approaches_at_its_first_instant() -> None:
    point = landmark("miami-dade")
    centre = (point.longitude + 1.0, point.latitude + 1.0)
    figure = figure_of(WGS84)
    position = place(point, WGS84)

    approach = closest_approach(synthetic_track(START, [centre] * 4), position, figure)

    assert approach == Approach(
        distance_km=distance_km(position, centre, figure), instant=START, lead_h=0.0
    )


def test_a_track_moving_away_approaches_at_its_first_point() -> None:
    point = landmark("miami-dade")
    lon, lat = point.longitude, point.latitude
    track = synthetic_track(
        START, [(lon + 1.0, lat), (lon + 3.0, lat + 1.0), (lon + 5.0, lat + 3.0)]
    )

    approach = closest_approach(track, place(point, WGS84), figure_of(WGS84))

    assert (approach.instant, approach.lead_h) == (START, 0.0)


def test_one_point_is_its_own_approach_and_no_points_is_an_error() -> None:
    point = landmark("nassau")
    centre = (point.longitude, point.latitude + 2.0)
    figure = figure_of(WGS84)
    position = place(point, WGS84)

    approach = closest_approach(synthetic_track(START, [centre]), position, figure)

    assert approach == Approach(distance_km(position, centre, figure), START, 0.0)
    with pytest.raises(ValueError, match="at least one point"):
        closest_approach([], position, figure)


def test_points_are_taken_in_valid_time_order() -> None:
    point = landmark("nassau")
    lon, lat = point.longitude, point.latitude
    track = synthetic_track(START, [(lon - 3.0, lat + 1.0), (lon, lat + 1.0), (lon + 3.0, lat)])
    figure = figure_of(WGS84)
    position = place(point, WGS84)

    assert closest_approach(track[::-1], position, figure) == closest_approach(
        track, position, figure
    )


def test_a_track_split_at_the_antimeridian_is_measured_continuously() -> None:
    lat = landmark("nassau").latitude
    track = synthetic_track(START, [(179.0, lat), (-179.0, lat)], step=timedelta(hours=6))

    approach = closest_approach(track, (180.0, lat), figure_of(WGS84))

    # The geodesic across 180 degrees bows poleward of the parallel by well under 5 km.
    assert approach.distance_km < 5.0  # noqa: PLR2004 - far below a degree
    assert approach.lead_h == pytest.approx(3.0, abs=1e-3)


def test_a_track_is_measured_only_on_its_own_figure() -> None:
    points = replay_track(IRMA, "036")

    with pytest.raises(ValueError, match="figure of its own CRS"):
        closest_approach(points, place(landmark("miami-dade"), WGS84), figure_of(WGS84))
