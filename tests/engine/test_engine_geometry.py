# tests/engine/test_engine_geometry.py
"""Containment, intersection, repair, and nearest points, on replay and synthetic geometry.

The replay anchors read the corpus through the archive parser replay snapshots use
(``weatherbot.sources.nhc_gis_archive``) and test the public landmarks; the synthetic
shapes are built from the landmarks, the antimeridian, and whole-degree offsets.
"""

from itertools import pairwise
from typing import cast

import pytest
from engine_support import (
    DORIAN,
    IRMA,
    advisories,
    cone,
    landmark,
    segments,
    square,
    wrap,
    wrapped_polygon,
)
from shapely.geometry import Point, Polygon

from weatherbot.engine.geodesy import Figure, Position, distance_km, figure_of
from weatherbot.engine.geometry import (
    Repaired,
    covers,
    intersects,
    nearest_on_line,
    place,
    repair,
)
from weatherbot.models import WGS84, Crs, Geometry, LatLon
from weatherbot.models.geometry import VALID_REASON

DENSE_SAMPLES = 2000
DENSE_TOLERANCE_KM = 0.05
# Rounding in the last digits of a geodesic distance, in kilometres.
ROUNDING_KM = 1e-9


def cone_shape(storm: str, advisory: str) -> Geometry | None:
    found = cone(storm, advisory)
    return found.geometry if found is not None else None


def covered_advisories(storm: str, point: LatLon) -> list[str]:
    covered: list[str] = []
    for advisory in advisories(storm):
        shape = cone_shape(storm, advisory)
        if shape is not None and covers(shape, place(point, shape.crs)):
            covered.append(advisory)
    return covered


def test_every_replay_cone_of_irma_is_valid_on_the_archive_sphere() -> None:
    shapes = [shape for a in advisories(IRMA) if (shape := cone_shape(IRMA, a)) is not None]

    assert shapes
    assert all(repair(shape).note is None for shape in shapes)
    assert {figure_of(shape.crs).semi_major_m for shape in shapes} == {6371200.0}


def test_the_miami_dade_landmark_is_inside_every_irma_cone_from_022_to_039a() -> None:
    order = advisories(IRMA)
    expected = order[order.index("022") : order.index("039A") + 1]

    covered = covered_advisories(IRMA, landmark("miami-dade"))

    assert covered == expected
    assert len(covered) == 34  # noqa: PLR2004 - the measured run
    assert {"021A", "040"}.isdisjoint(covered)
    assert order[order.index("022") - 1] == "021A"
    assert order[order.index("039A") + 1] == "040"


def test_the_nassau_landmark_is_inside_exactly_20_irma_cones_not_in_a_row() -> None:
    order = advisories(IRMA)

    covered = covered_advisories(IRMA, landmark("nassau"))

    assert len(covered) == 20  # noqa: PLR2004 - the measured count
    assert (covered[0], covered[-1]) == ("019", "031A")
    assert covered != order[order.index("019") : order.index("031A") + 1]


def coded(storm: str, advisory: str, code: str) -> list[Geometry]:
    return [segment.geometry for segment in segments(storm, advisory) if segment.tcww.raw == code]


def nearest_segment(storm: str, advisory: str, code: str, key: str) -> tuple[Geometry, float, bool]:
    point = landmark(key)
    measured: list[tuple[float, bool, Geometry]] = []
    for shape in coded(storm, advisory, code):
        found = nearest_on_line(place(point, shape.crs), shape, figure_of(shape.crs))
        measured.append((found.distance_km, found.at_end, shape))
    distance, at_end, shape = min(measured, key=lambda item: item[0])
    return shape, distance, at_end


def test_dorian_030_s_hurricane_warning_runs_past_the_nassau_landmark() -> None:
    shape, distance, at_end = nearest_segment(DORIAN, "030", "HWR", "nassau")

    assert shape.type == "LineString"
    assert len(cast("tuple[Position, ...]", shape.coordinates)) == 2  # noqa: PLR2004 - two vertices
    assert distance == pytest.approx(3.8, abs=0.1)
    assert not at_end


def test_dorian_032_s_tropical_storm_watch_ends_short_of_the_miami_dade_landmark() -> None:
    _, distance, at_end = nearest_segment(DORIAN, "032", "TWA", "miami-dade")

    assert distance == pytest.approx(22.6, abs=0.1)
    assert at_end


def dense_minimum_km(position: Position, line: Geometry, figure: Figure) -> float:
    """Brute force: sample every edge of every part densely and keep the nearest sample."""
    parts = (
        [cast("tuple[Position, ...]", line.coordinates)]
        if line.type == "LineString"
        else cast("tuple[tuple[Position, ...], ...]", line.coordinates)
    )
    best = float("inf")
    for part in parts:
        for start, end in pairwise(part):
            along = figure.geod.inv_intermediate(
                start[0],
                start[1],
                end[0],
                end[1],
                npts=DENSE_SAMPLES,
                initial_idx=0,
                terminus_idx=0,
                return_back_azimuth=True,
            )
            for lon, lat in zip(along.lons, along.lats, strict=True):
                best = min(best, distance_km((lon, lat), position, figure))
    return best


@pytest.mark.parametrize(("advisory", "key"), [("030", "nassau"), ("032", "miami-dade")])
def test_every_replay_segment_agrees_with_dense_sampling_within_50_m(
    advisory: str, key: str
) -> None:
    point = landmark(key)
    shapes = [segment.geometry for segment in segments(DORIAN, advisory)]
    assert shapes

    for shape in shapes:
        figure = figure_of(shape.crs)
        position = place(point, shape.crs)
        found = nearest_on_line(position, shape, figure).distance_km
        brute = dense_minimum_km(position, shape, figure)
        assert found <= brute + ROUNDING_KM
        assert brute - found <= DENSE_TOLERANCE_KM


def test_a_long_synthetic_edge_agrees_with_dense_sampling_within_50_m() -> None:
    miami, nassau = landmark("miami-dade"), landmark("nassau")
    line = Geometry(
        type="LineString",
        coordinates=(
            (miami.longitude - 9.0, miami.latitude - 6.0),
            (nassau.longitude + 9.0, nassau.latitude + 6.0),
        ),
        crs=WGS84,
    )
    figure = figure_of(WGS84)
    for point in (miami, nassau):
        position = place(point, WGS84)
        found = nearest_on_line(position, line, figure)
        brute = dense_minimum_km(position, line, figure)
        assert not found.at_end
        assert 0.0 < found.fraction < 1.0
        assert -ROUNDING_KM <= brute - found.distance_km <= DENSE_TOLERANCE_KM


def central_pacific_cone(crs: Crs = WGS84) -> Geometry:
    """A cone crossing 180 degrees at the Miami-Dade landmark's latitude, as NHC writes it."""
    lat = landmark("miami-dade").latitude
    ring = [(177.0, lat - 2.0), (183.0, lat - 2.0), (183.0, lat + 2.0), (177.0, lat + 2.0)]
    return wrapped_polygon([*ring, ring[0]], crs)


def test_a_central_pacific_cone_covers_both_sides_of_the_antimeridian_only() -> None:
    shape = central_pacific_cone()
    lat = landmark("miami-dade").latitude
    raw = Polygon(cast("tuple[tuple[Position, ...], ...]", shape.coordinates)[0])

    assert covers(shape, (179.5, lat))
    assert covers(shape, (-179.5, lat))
    assert not covers(shape, (0.5, lat))
    assert not covers(shape, (-0.5, lat))
    # Read as plain coordinates, the same ring would wrongly span the globe the other way.
    assert raw.covers(Point(0.5, lat))
    assert not raw.covers(Point(179.5, lat))


def test_a_position_on_the_boundary_counts_as_covered() -> None:
    shape = central_pacific_cone()
    lat = landmark("miami-dade").latitude

    assert covers(shape, (180.0, lat + 2.0))
    assert covers(shape, (-177.0, lat))


def test_parts_already_split_at_the_antimeridian_test_as_they_are() -> None:
    lat = landmark("nassau").latitude
    west = ((177.0, lat - 2.0), (180.0, lat - 2.0), (180.0, lat + 2.0), (177.0, lat + 2.0))
    east = ((-180.0, lat - 2.0), (-177.0, lat - 2.0), (-177.0, lat + 2.0), (-180.0, lat + 2.0))
    shape = Geometry(
        type="MultiPolygon",
        coordinates=(((*west, west[0]),), ((*east, east[0]),)),
        crs=WGS84,
    )

    assert covers(shape, (179.5, lat))
    assert covers(shape, (-179.5, lat))
    assert covers(shape, (180.0, lat))
    assert not covers(shape, (0.0, lat))


def test_a_hole_in_a_cone_crossing_the_antimeridian_stays_a_hole() -> None:
    lat = landmark("nassau").latitude
    outer = [(176.0, lat - 3.0), (184.0, lat - 3.0), (184.0, lat + 3.0), (176.0, lat + 3.0)]
    # The hole lies wholly east of 180 degrees, so it is written in negative longitudes.
    hole = [(-178.0, lat - 1.0), (-178.0, lat + 1.0), (-177.0, lat + 1.0), (-177.0, lat - 1.0)]
    shape = Geometry(
        type="Polygon",
        coordinates=(
            tuple((wrap(lon), y) for lon, y in [*outer, outer[0]]),
            (*hole, hole[0]),
        ),
        crs=WGS84,
    )

    assert covers(shape, (179.0, lat))
    assert not covers(shape, (-177.5, lat))
    assert covers(shape, (-176.5, lat))


def test_a_ring_that_encircles_a_pole_is_refused() -> None:
    ring = ((-120.0, 80.0), (0.0, 80.0), (120.0, 80.0), (-120.0, 80.0))
    shape = Geometry(type="Polygon", coordinates=(ring,), crs=WGS84)

    with pytest.raises(ValueError, match="encircles a pole"):
        covers(shape, (0.0, 85.0))


def test_a_projected_geometry_is_refused() -> None:
    from pyproj import CRS  # noqa: PLC0415 - only this test needs a projected WKT

    shape = square((0.0, 0.0), 1.0, Crs.native({"wkt": CRS("EPSG:3857").to_wkt("WKT1_GDAL")}))

    with pytest.raises(ValueError, match="projected CRS"):
        covers(shape, (0.0, 0.0))


def test_intersection_is_antimeridian_safe_for_every_geometry_type() -> None:
    shape = central_pacific_cone()
    lat = landmark("miami-dade").latitude
    straddling = wrapped_polygon(
        [(179.0, lat), (181.0, lat), (181.0, lat + 1.0), (179.0, lat + 1.0), (179.0, lat)]
    )
    track = Geometry(type="LineString", coordinates=((179.0, lat), (-179.0, lat)), crs=WGS84)
    split = Geometry(
        type="MultiLineString",
        coordinates=(((178.0, lat), (180.0, lat)), ((-180.0, lat), (-178.0, lat))),
        crs=WGS84,
    )
    centres = Geometry(type="MultiPoint", coordinates=((-178.5, lat), (0.0, lat)), crs=WGS84)
    far = square((0.0, lat), 1.0)

    assert intersects(shape, straddling)
    assert intersects(straddling, shape)
    assert intersects(shape, track)
    assert intersects(split, shape)
    assert intersects(shape, centres)
    assert intersects(shape, Geometry(type="Point", coordinates=(-178.5, lat), crs=WGS84))
    assert not intersects(shape, far)


def bow_tie(crs: Crs = WGS84) -> Geometry:
    """An invalid cone: a ring whose edges cross, centred on the Miami-Dade landmark."""
    point = landmark("miami-dade")
    lon, lat = point.longitude, point.latitude
    ring = ((lon - 1.0, lat - 1.0), (lon + 1.0, lat + 1.0), (lon + 1.0, lat - 1.0),
            (lon - 1.0, lat + 1.0), (lon - 1.0, lat - 1.0))  # fmt: skip
    return Geometry(type="Polygon", coordinates=(ring,), crs=crs)


def test_a_valid_geometry_comes_back_unchanged_with_no_note() -> None:
    shape = square((landmark("nassau").longitude, landmark("nassau").latitude), 1.0)

    repaired = repair(shape)

    assert repaired.shape is shape
    assert repaired.note is None


def test_an_invalid_bow_tie_cone_is_repaired_with_its_reason_and_no_coordinate() -> None:
    shape = bow_tie()
    assert not shape.is_valid

    repaired = repair(shape)

    assert repaired.shape is not None
    assert repaired.shape.is_valid
    assert repaired.shape.validity_reason == VALID_REASON
    assert repaired.shape.crs == shape.crs
    assert repaired.note == "repaired by shapely.make_valid: Self-intersection"
    assert repaired.shape.to_shapely().area == pytest.approx(2.0)
    assert covers(repaired.shape, place(landmark("miami-dade"), WGS84))
    assert repair(repaired.shape) == Repaired(shape=repaired.shape, note=None)


def test_a_repair_that_leaves_no_area_returns_no_shape() -> None:
    point = landmark("nassau")
    lon, lat = point.longitude, point.latitude
    ring = ((lon, lat), (lon + 1.0, lat + 1.0), (lon + 2.0, lat + 2.0), (lon, lat))
    shape = Geometry(type="Polygon", coordinates=(ring,), crs=WGS84)
    assert not shape.is_valid

    repaired = repair(shape)

    assert repaired.shape is None
    assert repaired.note is not None
    assert repaired.note.endswith("; no area remained")


def test_an_invalid_line_is_not_repaired() -> None:
    point = landmark("nassau")
    position = (point.longitude, point.latitude)
    shape = Geometry(type="LineString", coordinates=(position, position), crs=WGS84)
    assert not shape.is_valid

    with pytest.raises(ValueError, match="only an areal geometry"):
        repair(shape)


def test_a_bow_tie_across_the_antimeridian_is_repaired_into_range() -> None:
    lat = landmark("nassau").latitude
    ring = [(178.0, lat - 1.0), (182.0, lat + 1.0), (182.0, lat - 1.0), (178.0, lat + 1.0)]
    shape = wrapped_polygon([*ring, ring[0]])

    repaired = repair(shape)

    assert repaired.shape is not None
    assert repaired.note == "repaired by shapely.make_valid: Self-intersection"
    assert covers(repaired.shape, (179.0, lat))
    assert covers(repaired.shape, (-179.0, lat))
    assert repair(repaired.shape) == Repaired(shape=repaired.shape, note=None)


def test_a_point_segment_is_measured_to_its_one_vertex() -> None:
    miami, nassau = landmark("miami-dade"), landmark("nassau")
    figure = figure_of(WGS84)
    segment = Geometry(type="Point", coordinates=(nassau.longitude, nassau.latitude), crs=WGS84)
    position = place(miami, WGS84)

    found = nearest_on_line(position, segment, figure)

    assert found.distance_km == pytest.approx(
        distance_km(position, (nassau.longitude, nassau.latitude), figure)
    )
    assert (found.part, found.fraction, found.at_end) == (0, 0.0, False)


def test_a_track_split_at_the_antimeridian_has_no_end_where_its_parts_meet() -> None:
    lat = landmark("nassau").latitude
    split = Geometry(
        type="MultiLineString",
        coordinates=(((178.0, lat), (180.0, lat)), ((-180.0, lat), (-178.0, lat))),
        crs=WGS84,
    )
    figure = figure_of(WGS84)

    at_meeting = nearest_on_line((180.0, lat + 1.0), split, figure)
    past_the_end = nearest_on_line((-176.0, lat), split, figure)

    assert not at_meeting.at_end
    assert at_meeting.distance_km < 112.0  # noqa: PLR2004 - under a degree of latitude
    assert past_the_end.at_end
    assert (past_the_end.part, past_the_end.fraction) == (1, 1.0)


def test_a_closed_line_has_no_end() -> None:
    point = landmark("miami-dade")
    shape = square((point.longitude, point.latitude), 1.0)
    ring = cast("tuple[tuple[Position, ...], ...]", shape.coordinates)[0]
    line = Geometry(type="LineString", coordinates=ring, crs=WGS84)

    found = nearest_on_line((point.longitude - 2.0, point.latitude - 2.0), line, figure_of(WGS84))

    assert (found.fraction, found.at_end) == (0.0, False)


def test_a_line_is_measured_only_on_its_own_figure_and_type() -> None:
    point = landmark("nassau")
    line = Geometry(
        type="LineString",
        coordinates=((point.longitude, point.latitude), (point.longitude + 1.0, point.latitude)),
        crs=WGS84,
    )
    sphere_crs = segments(DORIAN, "030")[0].geometry.crs

    with pytest.raises(ValueError, match="figure of its own CRS"):
        nearest_on_line(place(point, WGS84), line, figure_of(sphere_crs))
    with pytest.raises(ValueError, match="must be one of"):
        nearest_on_line(place(point, WGS84), square((0.0, 0.0), 1.0), figure_of(WGS84))
