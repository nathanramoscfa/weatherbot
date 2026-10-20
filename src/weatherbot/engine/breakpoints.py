# src/weatherbot/engine/breakpoints.py  # noqa: ERA001 - a file path, not code
"""A location's breakpoint span, and the catalogue names of a watch-warning segment's ends.

NHC's breakpoint catalogue follows the coast in ``objectid`` order, and names some coasts
as ``country (region)`` entries. The span names the coast a location sits on; it never
decides whether a watch or warning covers the location, which the segment's own geometry
does. Distances are geodesics on the figure of the catalogue's CRS.
"""

import math
import re
from collections.abc import Sequence
from typing import Final, cast

from weatherbot.engine.geodesy import Position, distance_km, figure_of
from weatherbot.engine.geometry import nearest_on_line
from weatherbot.models import Breakpoint, BreakpointSpan, Geometry

SPAN_REACH_KM: Final = 100.0
"""How far a location's nearest catalogue breakpoint may be for the location to have a span."""

END_NAME_REACH_KM: Final = 10.0
"""How far a segment's end may be from the catalogue breakpoint that names it."""

_REGION: Final = re.compile(r"(?P<country>[^()]+?)\s*\((?P<region>[^()]*)\)\s*")
_ARTICLE: Final = "the "


def is_region(entry: Breakpoint) -> bool:
    """Return whether a catalogue entry is a ``country (region)`` entry.

    The text before the parentheses must be the entry's own country, less a leading
    "The"; a name that only mentions a country in parentheses is a breakpoint.

    Args:
        entry: A catalogue entry.

    Returns:
        Whether it names a region of its country rather than a point on the coast.
    """
    match = _REGION.fullmatch(entry.name)
    if match is None:
        return False
    country = entry.country.strip().casefold()
    country = country.removeprefix(_ARTICLE).strip()
    return bool(country) and match["country"].strip().casefold() == country


def _position(entry: Breakpoint) -> Position:
    longitude, latitude = cast("Sequence[float]", entry.position.coordinates)[:2]
    return (longitude, latitude)


def nearest_breakpoint(
    position: Position, breakpoints: Sequence[Breakpoint], within_km: float
) -> Breakpoint | None:
    """Return the catalogue breakpoint nearest a position, if one is within a distance.

    The position is in the catalogue's coordinates (see ``geometry.place``). A tie keeps
    the earlier entry in the order given.

    Args:
        position: ``(longitude, latitude)``.
        breakpoints: The catalogue.
        within_km: The farthest a breakpoint may be.

    Returns:
        The nearest breakpoint, or ``None`` when none is within ``within_km``.
    """
    best: Breakpoint | None = None
    best_km = math.inf
    for entry in breakpoints:
        figure = figure_of(entry.position.crs)
        measured = distance_km(position, _position(entry), figure)
        if measured <= within_km and measured < best_km:
            best, best_km = entry, measured
    return best


def _ordered(breakpoints: Sequence[Breakpoint]) -> list[Breakpoint] | None:
    """The catalogue in ``objectid`` order, or ``None`` when an entry has no ``objectid``."""
    if any(entry.objectid is None for entry in breakpoints):
        return None
    return sorted(breakpoints, key=lambda entry: cast("int", entry.objectid))


def breakpoint_span(position: Position, breakpoints: Sequence[Breakpoint]) -> BreakpointSpan | None:
    """Return the stretch of coast a position sits on, named from the catalogue.

    The nearest catalogue breakpoint within ``SPAN_REACH_KM`` anchors the span. When it
    is a ``country (region)`` entry, the span is that region. Otherwise the span is that
    breakpoint and its ``objectid`` neighbour in the same country between which the
    position's projection onto the coast falls (the nearer pair when it falls between
    both); when it falls between neither, both stretches come nearest at the breakpoint
    itself, and the earlier neighbour is taken; with no neighbour, the breakpoint stands
    alone. The names are in ``objectid`` order.

    Args:
        position: ``(longitude, latitude)`` in the catalogue's coordinates.
        breakpoints: The snapshot's catalogue.

    Returns:
        The span, or ``None`` beyond ``SPAN_REACH_KM``, for an empty catalogue, or for a
        catalogue stored before its ``objectid`` was read.
    """
    ordered = _ordered(breakpoints)
    if not ordered:
        return None
    nearest = nearest_breakpoint(position, ordered, SPAN_REACH_KM)
    if nearest is None:
        return None
    if is_region(nearest):
        return BreakpointSpan(
            names=(nearest.name,),
            country=nearest.country,
            is_region=True,
            catalog_loaded_at=nearest.loaded_at,
        )
    index = ordered.index(nearest)
    neighbours = [
        ordered[other]
        for other in (index - 1, index + 1)
        if 0 <= other < len(ordered)
        and ordered[other].country == nearest.country
        and not is_region(ordered[other])
    ]
    pair = _bracketing(position, nearest, neighbours)
    names = (nearest.name,) if pair is None else tuple(item.name for item in pair)
    return BreakpointSpan(
        names=names,
        country=nearest.country,
        is_region=False,
        catalog_loaded_at=nearest.loaded_at,
    )


def _bracketing(
    position: Position, nearest: Breakpoint, neighbours: Sequence[Breakpoint]
) -> tuple[Breakpoint, Breakpoint] | None:
    """The neighbour pair the position's projection falls between, in ``objectid`` order."""
    best: tuple[bool, float, Breakpoint] | None = None
    for neighbour in neighbours:
        crs = nearest.position.crs
        line = Geometry(
            type="LineString",
            coordinates=(_position(nearest), _position(neighbour)),
            crs=crs,
        )
        found = nearest_on_line(position, line, figure_of(crs))
        # Falling between the two (not at an end) beats falling beyond them, then the
        # nearer stretch; a tie keeps the earlier neighbour.
        candidate = (found.at_end, found.distance_km, neighbour)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    if best is None:
        return None
    neighbour = best[2]
    first, second = sorted((nearest, neighbour), key=lambda item: cast("int", item.objectid))
    return (first, second)


def segment_ends(segment: Geometry, breakpoints: Sequence[Breakpoint]) -> tuple[str, ...]:
    """Name a watch-warning segment's ends by their nearest catalogue breakpoints.

    The ends are the segment's first and last vertices (a Point segment has one). An end
    with no catalogue breakpoint within ``END_NAME_REACH_KM`` is left unnamed, and an
    end named like the other is named once.

    Args:
        segment: The segment's geometry.
        breakpoints: The snapshot's catalogue.

    Returns:
        The names, in the segment's order.
    """
    coordinates = cast("Sequence[object]", segment.coordinates)
    match segment.type:
        case "Point":
            ends = [cast("Sequence[float]", coordinates)]
        case "LineString":
            ends = [
                cast("Sequence[float]", coordinates[0]),
                cast("Sequence[float]", coordinates[-1]),
            ]
        case _:
            parts = cast("Sequence[Sequence[Sequence[float]]]", coordinates)
            ends = [parts[0][0], parts[-1][-1]]
    names: list[str] = []
    for end in ends:
        found = nearest_breakpoint((end[0], end[1]), breakpoints, END_NAME_REACH_KM)
        if found is not None and found.name not in names:
            names.append(found.name)
    return tuple(names)
