# src/weatherbot/engine/arrivals.py
"""When tropical-storm-force winds reach a location, read from an arrival-time product.

A product's isochrones are lines labelled with the instant the winds reach them, inside
an unlabelled outer contour, the 5 percent wind-speed probability contour. Most
isochrones are open lines whose ends stop just short of the outer contour (within 0.05
degrees in all 244 cached products, measured 2026-10-19), so they do not partition its
interior. The reading takes the path from the storm's current center to the location,
a straight line in the lines' own longitude and latitude, as the isochrones are drawn
and as ``weatherbot.engine.geometry`` tests containment: the latest instant among the
labelled lines the path crosses starts the interval, and the next later instant ends
it. Measured on every cached product at both public landmarks, that reading never
contradicts a closed contour. A geodesic path differs once: it slips past the open end
of an isochrone that the straight path crosses, and reads an arrival days too early.

Two guards keep a reading honest. A path that leaves the outer contour and comes back
can pass an isochrone's open end without crossing it, so it reads nothing. A location
inside a closed labelled contour of instant T never reads later than T; a reading that
would is unresolved.

Only instants the product already carries are read (issue #11): no label is parsed
here and no instant guessed. A product of the map layer, one whose instants were
withheld, or one with an unresolved line reads ``unresolved`` with the product's own
reason. When a storm has no product of a kind, its reading is the forecast track's
closest approach, labelled as such, because a closest approach is not a wind arrival.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Final, Literal, cast

from weatherbot.engine.geodesy import Figure, Position, figure_of
from weatherbot.engine.geometry import Approach, covers, intersects, repair, stretches_inside
from weatherbot.models import (
    TRACK_FALLBACK_LABEL,
    ArrivalReading,
    ArrivalTimeLine,
    ArrivalTimeProduct,
    Citation,
    Crs,
    Geometry,
    TrackPoint,
)
from weatherbot.models.arrivals import MAP_LAYER_REASON
from weatherbot.models.assessment import ArrivalKind

NO_OUTER_CONTOUR: Final = "the product has no closed 5 percent contour"
NO_ISOCHRONE: Final = "the product labels no isochrone"
NO_CENTER: Final = "the snapshot holds no forecast points, so the storm's center is unknown"
NO_TRACK: Final = "the snapshot holds neither an arrival-time product nor forecast points"
PATH_LEAVES: Final = (
    "the path from the storm's center leaves the 5 percent contour and comes back, so it "
    "can pass an isochrone's open end without crossing it"
)
CONTRADICTS: Final = "the path reads later than a closed isochrone that holds the location"
_MIN_RING_POSITIONS: Final = 4


def _parts(line: ArrivalTimeLine) -> list[tuple[tuple[float, float], ...]]:
    coordinates = cast("tuple[object, ...]", line.geometry.coordinates)
    parts = coordinates if line.geometry.type == "MultiLineString" else (coordinates,)
    return [
        tuple((float(x[0]), float(x[1])) for x in cast("Sequence[Sequence[float]]", part))
        for part in parts
    ]


def _closed_areas(line: ArrivalTimeLine) -> list[Geometry]:
    """The repaired areas a line's closed parts enclose; an open part encloses none."""
    areas: list[Geometry] = []
    for part in _parts(line):
        if part[0] != part[-1] or len(part) < _MIN_RING_POSITIONS:
            continue
        repaired = repair(Geometry(type="Polygon", coordinates=(part,), crs=line.geometry.crs))
        if repaired.shape is not None:
            areas.append(repaired.shape)
    return areas


def _unresolved_reason(product: ArrivalTimeProduct) -> str | None:
    """The product's own reason it carries no instant to read, if it has one."""
    if product.withheld_reason is not None:
        return product.withheld_reason
    if product.origin == "map_layer":
        return MAP_LAYER_REASON
    return next((line.unresolved_reason for line in product.lines if line.unresolved_reason), None)


def unresolved(product: ArrivalTimeProduct, reason: str) -> ArrivalReading:
    """Return a product's reading that states no instant, with the reason.

    Args:
        product: The arrival-time product.
        reason: Why it reads nothing at the location.

    Returns:
        The ``unresolved`` reading, citing the product.
    """
    return ArrivalReading(
        kind=product.kind,
        origin=product.origin,
        reading="unresolved",
        advisory=product.advisory.number,
        citation=Citation.of(product.provenance),
        reason=reason,
    )


def _path(center: Position, position: Position, crs: Crs) -> Geometry:
    if center == position:
        return Geometry(type="Point", coordinates=center, crs=crs)
    return Geometry(type="LineString", coordinates=(center, position), crs=crs)


def read_arrival(
    product: ArrivalTimeProduct, center: Position, position: Position, figure: Figure
) -> ArrivalReading:
    """Read an arrival-time product at a position, from the storm's current center.

    Args:
        product: The product.
        center: The storm's tau-0 center, in the lines' coordinates. Both geographic
            CRSs the engine measures compare as they are (``weatherbot.engine.geometry.
            place``).
        position: The location, in the lines' coordinates.
        figure: The figure of the lines' CRS; the path is straight in their longitude
            and latitude, so the figure only refuses a foreign one.

    Returns:
        ``before``, ``between``, or ``after`` the labelled instants the path crosses,
        ``outside`` the 5 percent contour, or ``unresolved`` with the reason.

    Raises:
        ValueError: A line's CRS has another figure.
    """
    if any(figure_of(line.geometry.crs) != figure for line in product.lines):
        message = "an arrival product must be read on the figure of its lines' CRS"
        raise ValueError(message)
    reason = _unresolved_reason(product)
    outer = [
        area for line in product.lines if line.is_outer_contour for area in _closed_areas(line)
    ]
    if reason is None and not outer:
        reason = NO_OUTER_CONTOUR
    if reason is not None:
        return unresolved(product, reason)
    if not any(covers(area, position) for area in outer):
        return _reading(product, "outside")
    return _interval(product, center, position, outer)


def _interval(
    product: ArrivalTimeProduct, center: Position, position: Position, outer: Sequence[Geometry]
) -> ArrivalReading:
    """Read the labelled lines the path crosses, for a position inside the outer contour."""
    labelled = [line for line in product.lines if not line.is_outer_contour]
    path = _path(center, position, outer[0].crs)
    if not labelled:
        return unresolved(product, NO_ISOCHRONE)
    if path.type == "LineString" and stretches_inside(path, outer) > 1:
        return unresolved(product, PATH_LEAVES)
    instants = sorted({_instant(line) for line in labelled})
    crossed = [_instant(line) for line in labelled if intersects(path, line.geometry)]
    start = max(crossed, default=None)
    end = next((instant for instant in instants if start is None or instant > start), None)
    if _contradicts(labelled, position, end):
        return unresolved(product, CONTRADICTS)
    if start is None:
        return _reading(product, "before", end=end)
    if end is None:
        return _reading(product, "after", start=start)
    return _reading(product, "between", start=start, end=end)


def _reading(
    product: ArrivalTimeProduct,
    reading: Literal["before", "between", "after", "outside"],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> ArrivalReading:
    return ArrivalReading(
        kind=product.kind,
        origin=product.origin,
        reading=reading,
        advisory=product.advisory.number,
        citation=Citation.of(product.provenance),
        start=start,
        end=end,
    )


def _instant(line: ArrivalTimeLine) -> datetime:
    # Every labelled line of a product read past _unresolved_reason has its instant.
    return cast("datetime", line.valid_at)


def _contradicts(
    labelled: Iterable[ArrivalTimeLine], position: Position, end: datetime | None
) -> bool:
    """Whether a reading's end falls later than a closed contour that holds the position.

    ``end`` is ``None`` for an ``after`` reading, which has no end.
    """
    return any(
        end is None or end > _instant(line)
        for line in labelled
        for area in _closed_areas(line)
        if covers(area, position)
    )


def latest_product(
    products: Iterable[ArrivalTimeProduct], kind: ArrivalKind
) -> ArrivalTimeProduct | None:
    """Return a storm's product of a kind: the latest advisory's, a KMZ before a map layer.

    Args:
        products: The storm's arrival-time products.
        kind: The kind wanted.

    Returns:
        The product, or ``None`` when the storm has none of that kind.
    """
    return max(
        (product for product in products if product.kind == kind),
        key=lambda product: (product.advisory.number, product.origin == "kmz"),
        default=None,
    )


def track_fallback(
    kind: ArrivalKind, approach: Approach | None, points: Sequence[TrackPoint]
) -> ArrivalReading:
    """Return the reading of a storm with no product of a kind: its closest approach.

    Args:
        kind: The product kind the storm lacks.
        approach: The forecast track's closest approach, or ``None`` without points.
        points: The storm's forecast points, which the fallback cites.

    Returns:
        The ``track`` reading, labelled ``TRACK_FALLBACK_LABEL``, or ``unresolved`` when
        the storm has no forecast points either.
    """
    if approach is None or not points:
        return ArrivalReading(kind=kind, origin="track", reading="unresolved", reason=NO_TRACK)
    first = min(points, key=lambda point: point.valid_at)
    return ArrivalReading(
        kind=kind,
        origin="track",
        reading="track",
        advisory=first.advisory.number,
        citation=Citation.of(first.provenance),
        approach_at=approach.instant,
        label=TRACK_FALLBACK_LABEL,
    )
