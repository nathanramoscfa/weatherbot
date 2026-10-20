# tests/engine/test_arrivals.py
"""``read_arrival``: the recorded and archived products, honest refusals, and synthetic edges.

The archived Dorian 036 pair is the recorded ``nhc-arrival-times`` capture, read from the
committed replay track's tau-0 center at both public landmarks. The Trudy 015 pair is read
between points derived at run time from its own isochrones. Synthetic isochrones are built
from the Nassau landmark, whole-degree offsets, and the antimeridian.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest
from engine_support import (
    DORIAN,
    IRMA,
    MIAMI_DADE,
    NASSAU,
    SYNTHETIC_AT,
    landmark,
    landmark_xy,
    line,
    offset,
    replay_track,
    synthetic_arrivals,
    synthetic_track,
)
from scenarios import rebuilt, recorded_maps, replay, replay_miami_dade
from source_support import entry, recorded, recorded_result

from weatherbot.engine import assess
from weatherbot.engine.arrivals import (
    CONTRADICTS,
    NO_ISOCHRONE,
    NO_OUTER_CONTOUR,
    NO_TRACK,
    PATH_LEAVES,
    latest_product,
    read_arrival,
    track_fallback,
)
from weatherbot.engine.geodesy import Position, figure_of
from weatherbot.engine.geometry import Approach, place
from weatherbot.engine.threats import threats_for
from weatherbot.models import (
    TRACK_FALLBACK_LABEL,
    WGS84,
    ArrivalReading,
    ArrivalTimeLine,
    ArrivalTimeProduct,
    Geometry,
    Thresholds,
)
from weatherbot.models.arrivals import MAP_LAYER_REASON
from weatherbot.sources import nhc_arrival_times

if TYPE_CHECKING:
    from collections.abc import Sequence

FIGURE = figure_of(WGS84)
DORIAN_PAIR = {
    "earliest_reasonable": "AL052019_036adv_earliest_reasonable_toa_34.kmz",
    "most_likely": "AL052019_036adv_most_likely_toa_34.kmz",
}
TRUDY_PAIR = (
    "EP212026_015adv_earliest_reasonable_toa_34.kmz",
    "EP212026_015adv_most_likely_toa_34.kmz",
)
SIMON_PAIR = (
    "EP202026_038adv_earliest_reasonable_toa_34.kmz",
    "EP202026_038adv_most_likely_toa_34.kmz",
)


def at(day: int, hour: int) -> datetime:
    return datetime(2019, 9, day, hour, tzinfo=UTC)


def capture(name: str) -> ArrivalTimeProduct:
    """A recorded arrival-time KMZ, parsed by the client."""
    directory = recorded("nhc-arrival-times")
    result = recorded_result(directory, entry(directory, name))
    return nhc_arrival_times.parse_arrival_kmz(result.body, result.provenance())


def dorian_center() -> Position:
    """Dorian 036's tau-0 center, from the committed replay track."""
    first = min(replay_track(DORIAN, "036"), key=lambda point: point.valid_at)
    coordinates = cast("Sequence[float]", first.position.coordinates)
    return (coordinates[0], coordinates[1])


def at_landmark(product: ArrivalTimeProduct, key: str, center: Position) -> ArrivalReading:
    return read_arrival(product, center, place(landmark(key), WGS84), FIGURE)


# The archived Dorian 036 pair: the four anchors ------------------------------------------


@pytest.mark.parametrize(
    ("kind", "key", "reading", "start", "end"),
    [
        ("earliest_reasonable", NASSAU, "before", None, at(2, 12)),
        ("most_likely", NASSAU, "between", at(2, 18), at(3, 0)),
        ("earliest_reasonable", MIAMI_DADE, "between", at(2, 12), at(2, 18)),
        ("most_likely", MIAMI_DADE, "between", at(3, 0), at(3, 12)),
    ],
    ids=["nassau-earliest", "nassau-most-likely", "miami-dade-earliest", "miami-dade-most-likely"],
)
def test_the_archived_dorian_036_pair_reads_the_anchors(
    kind: str, key: str, reading: str, start: datetime | None, end: datetime
) -> None:
    product = capture(DORIAN_PAIR[kind])

    found = at_landmark(product, key, dorian_center())

    assert (found.kind, found.origin, found.reading) == (kind, "kmz", reading)
    assert (found.start, found.end) == (start, end)
    assert str(found.advisory) == "36"
    assert found.citation is not None
    assert found.citation.source_id == "nhc-arrival-times"


# The 2026 captures ------------------------------------------------------------------------


def middle(line_: ArrivalTimeLine) -> Position:
    coordinates = cast("Sequence[Sequence[float]]", line_.geometry.coordinates)
    vertex = coordinates[len(coordinates) // 2]
    return (vertex[0], vertex[1])


@pytest.mark.parametrize("name", TRUDY_PAIR)
def test_trudy_015_reads_a_determinate_interval_between_points_its_lines_give(name: str) -> None:
    product = capture(name)
    first, second, third = [line_ for line_ in product.lines if not line_.is_outer_contour][:3]
    a, b, c = middle(first), middle(second), middle(third)
    # A center behind the first isochrone, and a point between the second and the third.
    center = (2 * a[0] - b[0], 2 * a[1] - b[1])
    position = ((b[0] + c[0]) / 2, (b[1] + c[1]) / 2)

    found = read_arrival(product, center, position, FIGURE)

    assert (found.reading, found.start, found.end) == ("between", second.valid_at, third.valid_at)


@pytest.mark.parametrize("name", SIMON_PAIR)
def test_simon_038_has_no_area_to_read(name: str) -> None:
    product = capture(name)
    (outer,) = product.lines

    found = at_landmark(product, NASSAU, landmark_xy(NASSAU))

    assert outer.is_outer_contour
    assert len(cast("tuple[object, ...]", outer.geometry.coordinates)) == 2  # noqa: PLR2004 - two positions
    assert (found.reading, found.reason) == ("unresolved", NO_OUTER_CONTOUR)


# Products that carry no instant -----------------------------------------------------------


def withheld(product: ArrivalTimeProduct, reason: str) -> ArrivalTimeProduct:
    """The product with its instants withheld, as a KMZ that disagrees with the roster."""
    lines = tuple(
        ArrivalTimeLine.resolve(
            item.label,
            item.geometry,
            origin="kmz",
            published_at=product.published_at,
            time_zone=product.time_zone,
            withheld_reason=reason,
        )
        for item in product.lines
    )
    return rebuilt(product, lines=lines, withheld_reason=reason)


def test_a_withheld_product_reads_its_own_reason() -> None:
    reason = "advisoryNum 37 is not the roster's advNum 36"
    product = withheld(capture(DORIAN_PAIR["earliest_reasonable"]), reason)

    found = at_landmark(product, MIAMI_DADE, dorian_center())

    assert (found.reading, found.reason, found.start, found.end) == (
        "unresolved",
        reason,
        None,
        None,
    )


def test_a_map_layer_product_reads_its_own_reason() -> None:
    (simon,) = [storm for storm in recorded_maps().storms if storm.cone is not None]
    product = simon.arrival_times[0]
    first = min(simon.track_points, key=lambda point: point.valid_at)
    coordinates = cast("Sequence[float]", first.position.coordinates)

    found = read_arrival(product, (coordinates[0], coordinates[1]), landmark_xy(MIAMI_DADE), FIGURE)

    assert product.origin == "map_layer"
    assert (found.origin, found.reading, found.reason) == (
        "map_layer",
        "unresolved",
        MAP_LAYER_REASON,
    )


def test_an_unresolved_line_reads_its_reason_and_no_label_is_parsed_here() -> None:
    product = capture(DORIAN_PAIR["earliest_reasonable"])
    lines = list(product.lines)
    lines[2] = ArrivalTimeLine.resolve(
        "Someday 8 am",
        lines[2].geometry,
        origin="kmz",
        published_at=product.published_at,
        time_zone=product.time_zone,
    )
    broken = rebuilt(product, lines=tuple(lines))

    found = at_landmark(broken, MIAMI_DADE, dorian_center())

    assert lines[2].unresolved_reason
    assert (found.reading, found.reason) == ("unresolved", lines[2].unresolved_reason)


# Synthetic isochrones ---------------------------------------------------------------------


def east(degrees: float, north: float = 0.0) -> Position:
    """A position east (negative: west) of the Nassau landmark."""
    return offset(NASSAU, degrees, north)


def ring(west: float, east_: float, half: float) -> Geometry:
    """A closed ring around the Nassau landmark's latitude, as a LineString."""
    south, north = -half, half
    corners = [east(west, south), east(east_, south), east(east_, north), east(west, north)]
    return line(*corners, corners[0])


def meridian(degrees: float, half: float = 2.9) -> Geometry:
    """An open isochrone running north and south, ending short of the outer ring."""
    return line(east(degrees, -half), east(degrees, half))


# The center sits 4 degrees west; isochrones at 3, 1.5, and 0.5 degrees west; the outer
# contour runs from 5 degrees west to 1 degree east.
LADDER: tuple[tuple[str | None, Geometry], ...] = (
    ("Tue 2 pm", meridian(-3.0)),
    ("Tue 8 pm", meridian(-1.5)),
    ("Wed 2 am", meridian(-0.5)),
    (None, ring(-5.0, 1.0, 3.0)),
)
CENTER = east(-4.0)


# The labels' instants: Tue 2 pm, Tue 8 pm, and Wed 2 am EDT.
T1 = datetime(2026, 10, 13, 18, tzinfo=UTC)
T2 = datetime(2026, 10, 14, 0, tzinfo=UTC)
T3 = datetime(2026, 10, 14, 6, tzinfo=UTC)


@pytest.mark.parametrize(
    ("position", "reading", "start", "end"),
    [
        (east(-3.5), "before", None, T1),
        (east(-1.0), "between", T2, T3),
        (landmark_xy(NASSAU), "after", T3, None),
        (east(2.0), "outside", None, None),
    ],
    ids=["before", "between", "after", "outside"],
)
def test_synthetic_isochrones_read_each_interval(
    position: Position, reading: str, start: datetime | None, end: datetime | None
) -> None:
    found = read_arrival(synthetic_arrivals(LADDER), CENTER, position, FIGURE)

    assert (found.reading, found.start, found.end) == (reading, start, end)


def test_the_location_at_the_center_reads_before_the_first_isochrone() -> None:
    found = read_arrival(synthetic_arrivals(LADDER), CENTER, CENTER, FIGURE)

    assert (found.reading, found.end) == ("before", T1)


def test_a_path_that_leaves_the_outer_contour_reads_nothing() -> None:
    # Two closed parts: the center in one, the location in the other.
    outer = Geometry(
        type="MultiLineString",
        coordinates=(
            cast("tuple[Position, ...]", ring(-5.0, -2.0, 3.0).coordinates),
            cast("tuple[Position, ...]", ring(-1.0, 1.0, 3.0).coordinates),
        ),
        crs=WGS84,
    )
    product = synthetic_arrivals([("Tue 2 pm", meridian(-3.0)), (None, outer)])

    found = read_arrival(product, CENTER, landmark_xy(NASSAU), FIGURE)

    assert (found.reading, found.reason) == ("unresolved", PATH_LEAVES)


def test_a_reading_later_than_a_closed_isochrone_that_holds_the_location_is_refused() -> None:
    # A closed Tue 2 pm contour around the location, beyond an open Tue 8 pm line.
    lines = (
        ("Tue 2 pm", ring(-1.2, -0.8, 0.2)),
        ("Tue 8 pm", meridian(-2.0)),
        (None, LADDER[-1][1]),
    )

    found = read_arrival(synthetic_arrivals(lines), CENTER, east(-1.0), FIGURE)

    assert (found.reading, found.reason) == ("unresolved", CONTRADICTS)


def test_a_closed_isochrone_that_holds_the_location_bounds_its_reading() -> None:
    # The first contour closes around both the center and the location.
    lines = (
        ("Tue 2 pm", ring(-4.5, -0.8, 2.0)),
        ("Tue 8 pm", meridian(-0.5)),
        (None, LADDER[-1][1]),
    )

    found = read_arrival(synthetic_arrivals(lines), CENTER, east(-1.0), FIGURE)

    assert (found.reading, found.end) == ("before", T1)


def test_a_product_with_only_its_outer_contour_reads_nothing_inside_it() -> None:
    product = synthetic_arrivals([(None, LADDER[-1][1])])

    inside = read_arrival(product, CENTER, east(-1.0), FIGURE)
    outside = read_arrival(product, CENTER, east(2.0), FIGURE)

    assert (inside.reading, inside.reason) == ("unresolved", NO_ISOCHRONE)
    assert outside.reading == "outside"


def test_the_path_is_safe_across_the_antimeridian() -> None:
    _, latitude = landmark_xy(NASSAU)
    outer_ring = [(178.5, latitude - 1), (-178.5, latitude - 1), (-178.5, latitude + 1)]
    outer_ring += [(178.5, latitude + 1), (178.5, latitude - 1)]
    lines = (
        ("Tue 2 pm", line((179.9, latitude - 0.9), (179.9, latitude + 0.9))),
        ("Tue 8 pm", line((-179.0, latitude - 0.9), (-179.0, latitude + 0.9))),
        (None, line(*outer_ring)),
    )

    found = read_arrival(synthetic_arrivals(lines), (179.5, latitude), (-179.5, latitude), FIGURE)

    assert (found.reading, found.start, found.end) == ("between", T1, T2)


def test_a_foreign_figure_is_refused() -> None:
    native = replay_track(DORIAN, "036")[0].position.crs

    with pytest.raises(ValueError, match="figure of its lines' CRS"):
        read_arrival(synthetic_arrivals(LADDER), CENTER, east(-1.0), figure_of(native))


# Choosing a product, and the fallback -----------------------------------------------------


def test_the_latest_advisory_s_product_is_read_a_kmz_before_a_map_layer() -> None:
    (simon,) = [storm for storm in recorded_maps().storms if storm.cone is not None]
    layer = simon.arrival_times[0]
    kmz = capture("EP202026_038adv_earliest_reasonable_toa_34.kmz")
    same = rebuilt(kmz, advisory=rebuilt(kmz.advisory, number=layer.advisory.number))

    assert latest_product([layer, kmz], "earliest_reasonable") is kmz
    assert latest_product([same, layer], "earliest_reasonable") is same
    assert latest_product([layer], "most_likely") is None


def test_a_storm_without_a_product_reads_the_labelled_closest_approach() -> None:
    track = synthetic_track(SYNTHETIC_AT, [east(-2.0), east(0.0), east(2.0)])
    approach = Approach(distance_km=1.0, instant=T1, lead_h=6.0)

    found = track_fallback("most_likely", approach, track)
    nothing = track_fallback("most_likely", None, ())

    assert (found.origin, found.reading, found.approach_at) == ("track", "track", T1)
    assert found.label == TRACK_FALLBACK_LABEL
    assert found.citation is not None
    assert (nothing.origin, nothing.reading, nothing.reason) == ("track", "unresolved", NO_TRACK)


def test_irma_has_no_product_and_reads_the_fallback() -> None:
    snapshot, location = replay(IRMA, "36"), replay_miami_dade()

    (threat,) = threats_for(snapshot, location, snapshot.completed_at)
    assessment = assess(snapshot, location, Thresholds())

    for reading in (threat.earliest_arrival, threat.most_likely_arrival):
        assert (reading.origin, reading.reading, reading.label) == (
            "track",
            "track",
            TRACK_FALLBACK_LABEL,
        )
        assert reading.approach_at == threat.closest_approach_at
    missing = [item for item in assessment.unavailable if item.kind == "arrival_times"]
    assert [item.atcf_id for item in missing] == [IRMA, IRMA]
