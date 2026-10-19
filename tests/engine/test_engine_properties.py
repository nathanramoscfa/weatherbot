# tests/engine/test_engine_properties.py
"""Property tests of the engine's geodesy and geometry, under the suite's Hypothesis profile.

``tests/conftest.py`` registers the profile: derandomized, with no example database and no
deadline, so every run tries the same examples and writes nothing. Positions are generated
in whole microdegrees, so two positions that differ are at least that far apart; points
near a landmark are generated as offsets from it.
"""

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

import shapely
from engine_support import corpus_wkts, landmark, synthetic_track, wrap, wrapped_polygon
from hypothesis import assume, given
from hypothesis import strategies as st
from shapely.geometry import Point, Polygon

from weatherbot.engine.geodesy import Figure, Position, distance_km, figure_of
from weatherbot.engine.geometry import closest_approach, covers, nearest_on_line, repair
from weatherbot.models import WGS84, Crs, Geometry

MICRODEGREES: Final = 1_000_000
# Rounding in the last digits of a geodesic distance, and a metre, in kilometres.
ROUNDING_KM: Final = 1e-9
METRE_KM: Final = 1e-3
START: Final = datetime(2026, 9, 1, tzinfo=UTC)
SPHERE: Final = Crs.native({"wkt": next(iter(corpus_wkts())), "datum": "D_Sphere"})
FIGURES: Final = (figure_of(WGS84), figure_of(SPHERE))


def degrees(low: float, high: float) -> st.SearchStrategy[float]:
    """Whole microdegrees from ``low`` up to, not including, ``high``."""
    return st.integers(round(low * MICRODEGREES), round(high * MICRODEGREES) - 1).map(
        lambda value: value / MICRODEGREES
    )


positions = st.tuples(degrees(-180.0, 180.0), degrees(-89.0, 89.0))
figures = st.sampled_from(FIGURES)


def near(key: str, spread: float) -> st.SearchStrategy[Position]:
    """Positions within ``spread`` degrees of a landmark."""
    point = landmark(key)
    return st.tuples(
        degrees(-spread, spread).map(lambda offset: point.longitude + offset),
        degrees(-spread, spread).map(lambda offset: point.latitude + offset),
    )


@given(a=positions, b=positions, figure=figures)
def test_distance_is_symmetric_and_zero_only_for_equal_positions(
    a: Position, b: Position, figure: Figure
) -> None:
    there, back = distance_km(a, b, figure), distance_km(b, a, figure)

    assert abs(there - back) <= ROUNDING_KM
    assert (there == 0.0) == (a == b)


@given(a=positions, b=positions, c=positions, figure=figures)
def test_distance_keeps_the_triangle_inequality_within_a_metre(
    a: Position, b: Position, c: Position, figure: Figure
) -> None:
    assert (
        distance_km(a, c, figure)
        <= distance_km(a, b, figure) + distance_km(b, c, figure) + METRE_KM
    )


@st.composite
def antimeridian_rings(draw: st.DrawFn) -> list[Position]:
    """A star-shaped ring around a centre near 180 degrees, in one continuous range."""
    centre_lon = draw(degrees(176.0, 184.0))
    centre_lat = draw(degrees(-60.0, 60.0))
    count = draw(st.integers(3, 9))
    radii = draw(st.lists(degrees(0.5, 6.0), min_size=count, max_size=count))
    ring: list[Position] = []
    for index, radius in enumerate(radii):
        angle = 2.0 * math.pi * index / count
        ring.append(
            (centre_lon + radius * math.cos(angle), centre_lat + radius * math.sin(angle) / 2)
        )
    # Every ring generated here crosses 180 degrees.
    assume(min(lon for lon, _ in ring) < 180.0 < max(lon for lon, _ in ring))  # noqa: PLR2004 - the antimeridian
    return [*ring, ring[0]]


@given(ring=antimeridian_rings(), probe=st.tuples(degrees(-8.0, 8.0), degrees(-8.0, 8.0)))
def test_covers_is_unchanged_when_a_ring_crossing_180_is_shifted_by_360(
    ring: list[Position], probe: tuple[float, float]
) -> None:
    centre_lon = sum(lon for lon, _ in ring[:-1]) / (len(ring) - 1)
    centre_lat = sum(lat for _, lat in ring[:-1]) / (len(ring) - 1)
    unwrapped = (centre_lon + probe[0], centre_lat + probe[1])
    oracle = Polygon(ring)
    assume(oracle.boundary.distance(Point(unwrapped)) > 1e-6)  # noqa: PLR2004 - off the boundary
    expected = bool(oracle.covers(Point(unwrapped)))
    # The same ring, started from a vertex on the other side of 180 degrees: unwrapped
    # from there, its longitudes are the first ring's shifted by 360 degrees.
    first_east = next(index for index, (lon, _) in enumerate(ring) if lon > 180.0)  # noqa: PLR2004 - the antimeridian
    rotated = [*ring[first_east:-1], *ring[:first_east], ring[first_east]]
    position = (wrap(unwrapped[0]), unwrapped[1])

    for shape in (wrapped_polygon(ring), wrapped_polygon(rotated)):
        assert covers(shape, position) == expected
        assert covers(shape, (position[0] + 360.0, position[1])) == expected
        assert covers(shape, (position[0] - 360.0, position[1])) == expected


@given(
    vertices=st.lists(near("miami-dade", 2.0), min_size=3, max_size=6),
    crs=st.sampled_from((WGS84, SPHERE)),
)
def test_repair_is_idempotent_and_the_identity_on_valid_input(
    vertices: list[Position], crs: Crs
) -> None:
    shape = Geometry(type="Polygon", coordinates=((*vertices, vertices[0]),), crs=crs)

    repaired = repair(shape)

    if shapely.is_valid(Polygon(vertices)):
        assert repaired.shape is shape
        assert repaired.note is None
    else:
        assert repaired.note is not None
        assert "[" not in repaired.note
    if repaired.shape is not None:
        again = repair(repaired.shape)
        assert again.shape is repaired.shape
        assert again.note is None


@given(
    vertices=st.lists(near("nassau", 3.0), min_size=1, max_size=6),
    position=near("nassau", 4.0),
    figure=figures,
)
def test_the_nearest_point_of_a_line_is_no_farther_than_any_vertex(
    vertices: list[Position], position: Position, figure: Figure
) -> None:
    crs = WGS84 if figure == FIGURES[0] else SPHERE
    line = (
        Geometry(type="Point", coordinates=vertices[0], crs=crs)
        if len(vertices) == 1
        else Geometry(type="LineString", coordinates=tuple(vertices), crs=crs)
    )

    found = nearest_on_line(position, line, figure)

    assert found.distance_km <= min(distance_km(position, v, figure) for v in vertices)
    assert 0.0 <= found.fraction <= 1.0


@given(
    centres=st.lists(near("miami-dade", 5.0), min_size=1, max_size=8),
    position=near("miami-dade", 6.0),
)
def test_the_closest_approach_is_no_farther_than_any_forecast_point(
    centres: Sequence[Position], position: Position
) -> None:
    figure = figure_of(WGS84)

    approach = closest_approach(synthetic_track(START, centres), position, figure)

    assert approach.distance_km <= min(distance_km(position, c, figure) for c in centres)
    assert 0.0 <= approach.lead_h <= 12.0 * (len(centres) - 1)
