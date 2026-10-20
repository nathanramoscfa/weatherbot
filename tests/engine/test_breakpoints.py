# tests/engine/test_breakpoints.py  # noqa: ERA001 - a file path, not code
"""A location's breakpoint span, and the catalogue names of a segment's ends.

The recorded catalogue of 2026-10-12 gives both landmarks' spans; synthetic catalogues
built from whole-degree offsets of a landmark test the neighbour rules.
"""

from datetime import UTC, datetime
from typing import cast

import pytest
from engine_support import (
    MIAMI_DADE,
    NASSAU,
    landmark_xy,
    line,
    offset,
    synthetic_provenance,
)
from scenarios import recorded_maps

from weatherbot.engine.breakpoints import (
    SPAN_REACH_KM,
    breakpoint_span,
    is_region,
    nearest_breakpoint,
    segment_ends,
)
from weatherbot.engine.geodesy import distance_km, figure_of
from weatherbot.models import WGS84, Breakpoint, BreakpointSpan, Geometry

LOADED = datetime(2026, 4, 30, 18, 42, 35, tzinfo=UTC)  # idp_filedate 1777574555000
CATALOGUE_SIZE = 549


def catalogue() -> tuple[Breakpoint, ...]:
    """The recorded breakpoint catalogue."""
    return recorded_maps().breakpoints


def named(name: str) -> Breakpoint:
    """A recorded catalogue entry by name."""
    return next(item for item in catalogue() if item.name == name)


def entry(
    name: str, position: tuple[float, float], objectid: int, country: str = "Testland"
) -> Breakpoint:
    """A synthetic catalogue entry."""
    return Breakpoint(
        name=name,
        state=None,
        country=country,
        position=Geometry(type="Point", coordinates=position, crs=WGS84),
        objectid=objectid,
        loaded_at=LOADED,
        provenance=synthetic_provenance("nhc-map-breakpoints"),
    )


# The recorded catalogue --------------------------------------------------------------------


def test_the_catalogue_is_read_with_its_order_and_load_date() -> None:
    objectids = [item.objectid for item in catalogue()]

    assert len(objectids) == CATALOGUE_SIZE
    assert objectids == sorted(cast("list[int]", objectids))
    assert {item.loaded_at for item in catalogue()} == {LOADED}


def test_the_miami_dade_landmarks_span_is_ocean_reef_to_the_county_line() -> None:
    span = breakpoint_span(landmark_xy(MIAMI_DADE), catalogue())

    assert span == BreakpointSpan(
        names=("Ocean Reef", "Miami-Dade/Broward County Line"),
        country="United States",
        is_region=False,
        catalog_loaded_at=LOADED,
    )


def test_the_nassau_landmarks_span_is_its_region() -> None:
    span = breakpoint_span(landmark_xy(NASSAU), catalogue())

    assert span is not None
    assert (span.names, span.country, span.is_region) == (("Bahamas (NW)",), "The Bahamas", True)


def test_the_landmarks_nearest_breakpoints_are_the_recorded_ones() -> None:
    figure = figure_of(WGS84)
    miami = named("Miami-Dade/Broward County Line")
    region = named("Bahamas (NW)")

    found = nearest_breakpoint(landmark_xy(MIAMI_DADE), catalogue(), SPAN_REACH_KM)
    position = cast("tuple[float, float]", miami.position.coordinates)

    assert found == miami
    assert distance_km(landmark_xy(MIAMI_DADE), position, figure) == pytest.approx(24.0, abs=0.1)
    assert nearest_breakpoint(landmark_xy(NASSAU), catalogue(), SPAN_REACH_KM) == region


def test_a_position_beyond_the_reach_has_no_span() -> None:
    far = offset(NASSAU, 0.0, 3.0)

    assert nearest_breakpoint(far, catalogue(), SPAN_REACH_KM) is None
    assert breakpoint_span(far, catalogue()) is None


def test_an_empty_catalogue_or_one_stored_without_objectids_gives_no_span() -> None:
    unordered = [item.model_copy(update={"objectid": None}) for item in catalogue()]

    assert breakpoint_span(landmark_xy(MIAMI_DADE), ()) is None
    assert breakpoint_span(landmark_xy(MIAMI_DADE), unordered) is None


@pytest.mark.parametrize(
    ("name", "region"),
    [
        ("Bahamas (NW)", True),
        ("Bahamas (Extreme NW )", True),
        ("Jamaica (all)", True),
        ("Venezuela (Isla de Margarita)", True),
        ("Bay Islands (Honduras)", False),
        ("Isle of Youth (Cuba)", False),
        ("Kiritimati (Christmas) Island", False),
        ("Anse d'Hainault (sw tip Haiti)", False),
        ("Ocean Reef", False),
    ],
)
def test_a_region_is_a_country_and_a_parenthesised_part(name: str, *, region: bool) -> None:
    assert is_region(named(name)) is region


# Synthetic catalogues ----------------------------------------------------------------------


def coast() -> list[Breakpoint]:
    """Three breakpoints a degree apart, south to north through the Miami-Dade landmark."""
    return [
        entry("South", offset(MIAMI_DADE, 0.0, -1.0), 1),
        entry("Middle", landmark_xy(MIAMI_DADE), 2),
        entry("North", offset(MIAMI_DADE, 0.0, 1.0), 3),
    ]


@pytest.mark.parametrize(
    ("north_deg", "names"),
    [(-0.3, ("South", "Middle")), (0.3, ("Middle", "North"))],
    ids=["south-of-middle", "north-of-middle"],
)
def test_the_span_is_the_pair_the_projection_falls_between(
    north_deg: float, names: tuple[str, str]
) -> None:
    span = breakpoint_span(offset(MIAMI_DADE, 0.05, north_deg), coast())

    assert span is not None
    assert (span.names, span.country, span.is_region) == (names, "Testland", False)


def test_the_names_follow_objectid_order_whatever_the_catalogues_order() -> None:
    span = breakpoint_span(offset(MIAMI_DADE, 0.05, -0.3), list(reversed(coast())))

    assert span is not None
    assert span.names == ("South", "Middle")


def test_a_neighbour_in_another_country_or_a_region_is_not_a_bracket() -> None:
    catalogue_ = [
        entry("South", offset(MIAMI_DADE, 0.0, -1.0), 1, country="Otherland"),
        entry("Middle", landmark_xy(MIAMI_DADE), 2),
        entry("Testland (North)", offset(MIAMI_DADE, 0.0, 1.0), 3),
    ]

    span = breakpoint_span(offset(MIAMI_DADE, 0.05, -0.3), catalogue_)

    assert span is not None
    assert span.names == ("Middle",)


def test_a_projection_beyond_both_neighbours_takes_the_earlier_one() -> None:
    corner = [
        entry("West", offset(MIAMI_DADE, -1.0, 0.0), 1),
        entry("Corner", landmark_xy(MIAMI_DADE), 2),
        entry("South", offset(MIAMI_DADE, 0.0, -1.0), 3),
    ]

    span = breakpoint_span(offset(MIAMI_DADE, 0.2, 0.3), corner)

    assert span is not None
    assert span.names == ("West", "Corner")


def test_a_tie_keeps_the_earlier_breakpoint() -> None:
    twins = [
        entry("First", landmark_xy(MIAMI_DADE), 1),
        entry("Second", landmark_xy(MIAMI_DADE), 2),
    ]

    assert nearest_breakpoint(landmark_xy(MIAMI_DADE), twins, 1.0) == twins[0]


# Segment ends ------------------------------------------------------------------------------


def test_a_segments_ends_are_named_by_breakpoints_within_reach() -> None:
    near_south = offset(MIAMI_DADE, 0.02, -1.0)  # about 2 km from South
    far_north = offset(MIAMI_DADE, 0.0, 1.2)  # about 22 km from North

    assert segment_ends(line(near_south, offset(MIAMI_DADE, 0.0, 1.0)), coast()) == (
        "South",
        "North",
    )
    assert segment_ends(line(near_south, far_north), coast()) == ("South",)


def test_a_point_or_split_segment_names_its_ends() -> None:
    point = Geometry(type="Point", coordinates=landmark_xy(MIAMI_DADE), crs=WGS84)
    split = Geometry(
        type="MultiLineString",
        coordinates=(
            (offset(MIAMI_DADE, 0.0, -1.0), offset(MIAMI_DADE, 0.5, -0.5)),
            (offset(MIAMI_DADE, 0.5, 0.5), offset(MIAMI_DADE, 0.0, 1.0)),
        ),
        crs=WGS84,
    )

    assert segment_ends(point, coast()) == ("Middle",)
    assert segment_ends(split, coast()) == ("South", "North")
    assert segment_ends(line(landmark_xy(MIAMI_DADE), offset(MIAMI_DADE, 0.01, 0.0)), coast()) == (
        "Middle",
    )
