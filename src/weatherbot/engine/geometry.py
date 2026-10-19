# src/weatherbot/engine/geometry.py
"""Where a location sits in a geometry, what a geometry covers, and how near a line comes.

Containment and intersection are planar tests on longitude and latitude in the
geometry's own coordinates, made safe at the antimeridian; distances are geodesics on
the figure of the geometry's CRS (``weatherbot.engine.geodesy``). Every function is pure:
nothing here logs, reads the clock, or opens a file.
"""

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, cast

import shapely
from shapely.affinity import translate
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    mapping,
)
from shapely.geometry.base import BaseGeometry

from weatherbot.engine.geodesy import Figure, Position, figure_of
from weatherbot.models import Crs, Geometry, LatLon, TrackPoint
from weatherbot.models.geometry import require_geometry

_HALF_TURN_DEG: Final = 180.0
_FULL_TURN_DEG: Final = 360.0
# The longitude shifts a position or a shape is tested at, so that a shape unwrapped
# past 180 degrees meets a position given in [-180, 180].
_SHIFTS: Final = (0.0, -_FULL_TURN_DEG, _FULL_TURN_DEG)
_METRES_PER_KM: Final = 1000.0
_SECONDS_PER_HOUR: Final = 3600.0
# The along-edge interval at which the search for an edge's nearest point stops.
_FOOT_TOLERANCE_M: Final = 0.01

type _Ring = list[Position]


@dataclass(frozen=True, slots=True)
class Repaired:
    """A repair's outcome: the usable shape, or none, and what was done to it.

    ``shape`` is the geometry itself when it was valid, its polygonal repair when it was
    not, and ``None`` when no area remained (the product is then unusable). ``note`` is
    ``None`` for a valid geometry and otherwise names the original validity reason.
    """

    shape: Geometry | None
    note: str | None


@dataclass(frozen=True, slots=True)
class Nearest:
    """The point of a line nearest a position.

    ``part`` indexes the line's parts (0 for a LineString or a Point); ``fraction`` is the
    point's geodesic distance along its part over the part's length (0 for a part with no
    length); ``at_end`` is true only when the point is the first or last vertex of an open
    part, that is, one whose first vertex differs from its last.
    """

    distance_km: float
    part: int
    fraction: float
    at_end: bool


@dataclass(frozen=True, slots=True)
class Approach:
    """A forecast track's closest approach to a position.

    ``instant`` is when the interpolated center is nearest (UTC), and ``lead_h`` the hours
    from the track's first point to that instant.
    """

    distance_km: float
    instant: datetime
    lead_h: float


@dataclass(frozen=True, slots=True)
class _Foot:
    """The nearest point of one part: on vertex ``edge``, or ``offset_m`` along that edge."""

    distance_m: float
    edge: int
    offset_m: float
    on_vertex: bool


def _require_figure(crs: Crs, figure: Figure) -> None:
    if figure_of(crs) != figure:
        message = "a geometry must be measured on the figure of its own CRS"
        raise ValueError(message)


def _xy(position: Sequence[float]) -> Position:
    return (position[0], position[1])


def _positions(sequence: object) -> list[Position]:
    return [_xy(position) for position in cast("Sequence[Sequence[float]]", sequence)]


def _unwrap(positions: Sequence[Position]) -> list[Position]:
    """Make longitudes continuous: a step of more than 180 degrees crosses the antimeridian.

    Each longitude moves by a whole number of turns, so a closed ring that does not
    encircle a pole stays exactly closed.
    """
    unwrapped: list[Position] = []
    turns = 0
    previous: float | None = None
    for longitude, latitude in positions:
        if previous is not None:
            if longitude - previous > _HALF_TURN_DEG:
                turns -= 1
            elif longitude - previous < -_HALF_TURN_DEG:
                turns += 1
        unwrapped.append((longitude + _FULL_TURN_DEG * turns, latitude))
        previous = longitude
    return unwrapped


def _unwrapped_ring(ring: Sequence[Position]) -> _Ring:
    unwrapped = _unwrap(ring)
    if unwrapped[-1] != unwrapped[0]:
        message = "a ring that encircles a pole is refused"
        raise ValueError(message)
    return unwrapped


def _unwrapped_polygon(rings: object) -> Polygon:
    """Unwrap a polygon's rings, moving each hole by whole turns onto its exterior."""
    parts = [_positions(ring) for ring in cast("Sequence[object]", rings)]
    exterior = _unwrapped_ring(parts[0])
    longitudes = [longitude for longitude, _ in exterior]
    centre = (min(longitudes) + max(longitudes)) / 2.0
    holes: list[_Ring] = []
    for ring in parts[1:]:
        hole = _unwrapped_ring(ring)
        turns = round((centre - hole[0][0]) / _FULL_TURN_DEG)
        holes.append([(longitude + _FULL_TURN_DEG * turns, lat) for longitude, lat in hole])
    return Polygon(exterior, holes)


def _unwrapped(geometry: Geometry) -> BaseGeometry:
    """Build a geometry's Shapely shape with every line and ring unwrapped at 180 degrees.

    Parts already split at 180 degrees have no such step, so they are built as they are.
    """
    figure_of(geometry.crs)  # refuses a CRS the engine cannot measure
    coordinates = cast("Sequence[object]", geometry.coordinates)
    match geometry.type:
        case "Point":
            return Point(_xy(cast("Sequence[float]", coordinates)))
        case "MultiPoint":
            return MultiPoint(_positions(coordinates))
        case "LineString":
            return LineString(_unwrap(_positions(coordinates)))
        case "MultiLineString":
            return MultiLineString([_unwrap(_positions(line)) for line in coordinates])
        case "Polygon":
            return _unwrapped_polygon(coordinates)
        case "MultiPolygon":
            return MultiPolygon([_unwrapped_polygon(polygon) for polygon in coordinates])


def place(point: LatLon, crs: Crs) -> Position:
    """Return a location's position in the coordinates of a geometry's CRS.

    For both geographic CRSs the engine measures, ``EPSG:4326`` and the replay archive's
    native ``D_Sphere``, the position is the location's own WGS 84 longitude and latitude,
    unchanged. That is all PROJ itself offers: checked on 2026-10-18 with pyproj 3.8.0
    and PROJ 9.8.1, the only transformation from ``EPSG:4326`` to the archive's WKT is a
    "Ballpark geographic offset from WGS 84 to Unknown datum based upon the Authalic
    Sphere", of unknown accuracy (-1), and it returns both public landmarks unchanged.
    Every caller's evidence names the CRS of the geometry it tested.

    Args:
        point: The location's WGS 84 point.
        crs: The CRS of the geometry the location is tested against.

    Returns:
        ``(longitude, latitude)`` in that CRS's coordinates.

    Raises:
        ValueError: The CRS is projected or its WKT is refused.
    """
    figure_of(crs)
    return (point.longitude, point.latitude)


def covers(geometry: Geometry, position: Position) -> bool:
    """Return whether a geometry covers a position; a position on the boundary is inside.

    A ring whose consecutive vertices are more than 180 degrees of longitude apart crosses
    the antimeridian; it is unwrapped into one continuous longitude range first, and the
    position, its longitude brought into [-180, 180), is tested at that longitude and at
    plus and minus 360 degrees.

    Args:
        geometry: The geometry, usually a cone or a band, in a geographic CRS.
        position: ``(longitude, latitude)`` in the geometry's coordinates (see ``place``).

    Returns:
        Whether the position is inside the geometry or on its boundary.
    """
    shape = _unwrapped(geometry)
    longitude = (position[0] + _HALF_TURN_DEG) % _FULL_TURN_DEG - _HALF_TURN_DEG
    return any(shape.covers(Point(longitude + shift, position[1])) for shift in _SHIFTS)


def intersects(a: Geometry, b: Geometry) -> bool:
    """Return whether two geographic geometries share any point, safely at the antimeridian.

    Both are unwrapped as ``covers`` unwraps a ring, and ``b`` is tested at its longitudes
    and at plus and minus 360 degrees. Coordinates of the two geographic CRSs compare as
    they are, as ``place`` explains.

    Args:
        a: A geometry.
        b: Another.

    Returns:
        Whether they intersect.
    """
    first, second = _unwrapped(a), _unwrapped(b)
    return any(first.intersects(translate(second, xoff=shift)) for shift in _SHIFTS)


def _polygons(shape: BaseGeometry) -> Iterator[Polygon]:
    if isinstance(shape, Polygon):
        if not shape.is_empty:
            yield shape
    elif isinstance(shape, MultiPolygon | GeometryCollection):
        for part in cast("MultiPolygon | GeometryCollection[BaseGeometry]", shape).geoms:
            yield from _polygons(part)


def _wrapped(value: object) -> object:
    """Bring each longitude a repair unwrapped past 180 degrees back into [-180, 180]."""
    sequence = cast("Sequence[object]", value)
    if sequence and isinstance(longitude := sequence[0], float):
        if longitude > _HALF_TURN_DEG:
            longitude -= _FULL_TURN_DEG
        elif longitude < -_HALF_TURN_DEG:
            longitude += _FULL_TURN_DEG
        return (longitude, *sequence[1:])
    return tuple(_wrapped(item) for item in sequence)


def repair(geometry: Geometry) -> Repaired:
    """Repair an invalid areal geometry, keeping its polygonal parts and saying why.

    Validity is judged on the shape unwrapped at the antimeridian, as ``covers`` tests it.
    A valid geometry comes back unchanged with no note. An invalid Polygon or MultiPolygon
    goes through ``shapely.make_valid``; its polygonal parts are kept, and the note names
    the original validity reason without its location. A repair that leaves no area
    returns no shape with its note. Repair is idempotent.

    Args:
        geometry: The geometry, usually a cone.

    Returns:
        The usable shape, or none, and the note.

    Raises:
        ValueError: The geometry is invalid and not areal.
    """
    shape = _unwrapped(geometry)
    if shapely.is_valid(shape):
        return Repaired(shape=geometry, note=None)
    if geometry.type not in {"Polygon", "MultiPolygon"}:
        message = "only an areal geometry is repaired"
        raise ValueError(message)
    # The reason's bracketed location is a coordinate; the note names the reason alone.
    reason = str(shapely.is_valid_reason(shape)).split("[", 1)[0]
    note = f"repaired by shapely.make_valid: {reason}"
    kept = list(_polygons(shapely.make_valid(shape)))
    merged = shapely.union_all(kept) if kept else None
    if merged is None or merged.is_empty or merged.area == 0.0:
        return Repaired(shape=None, note=f"{note}; no area remained")
    geojson = cast("dict[str, object]", mapping(merged))
    repaired = {"type": geojson["type"], "coordinates": _wrapped(geojson["coordinates"])}
    return Repaired(shape=Geometry.from_geojson(repaired, geometry.crs), note=note)


def _nearest_on_part(
    part: Sequence[Position], position: Position, figure: Figure
) -> tuple[_Foot, list[float]]:
    """Find a part's point nearest a position, each edge a geodesic.

    Every vertex is a candidate. An edge holds a nearer interior point only when the
    distance still falls on leaving its first vertex and rises on reaching its last; that
    point is where the geodesic to the position meets the edge at a right angle, found by
    bisection on which side of it the position lies. Edges whose triangle bound cannot
    beat the best so far are skipped. A tie keeps the earliest vertex. The part's edge
    lengths, in metres, come back with the point.
    """
    geod = figure.geod
    count = len(part)
    longitudes = [longitude for longitude, _ in part]
    latitudes = [latitude for _, latitude in part]
    toward, _, distances = geod.inv(
        longitudes, latitudes, [position[0]] * count, [position[1]] * count
    )
    toward = cast("list[float]", toward)
    distances = cast("list[float]", distances)
    best_vertex = min(range(count), key=lambda index: (distances[index], index))
    best = _Foot(distances[best_vertex], best_vertex, 0.0, on_vertex=True)
    if count == 1:
        return best, []
    forward, backward, lengths = geod.inv(
        longitudes[:-1], latitudes[:-1], longitudes[1:], latitudes[1:]
    )
    forward = cast("list[float]", forward)
    backward = cast("list[float]", backward)
    lengths = cast("list[float]", lengths)
    for edge in range(count - 1):
        length = lengths[edge]
        if (
            length == 0.0
            or (distances[edge] + distances[edge + 1] - length) / 2.0 >= best.distance_m
        ):
            continue
        leaves_closer = _ahead(toward[edge], forward[edge])
        arrives_closer = _ahead(toward[edge + 1], backward[edge] + _HALF_TURN_DEG)
        if not leaves_closer or arrives_closer:
            continue
        low, high = 0.0, length
        while high - low > _FOOT_TOLERANCE_M:
            middle = (low + high) / 2.0
            lon, lat, back = geod.fwd(longitudes[edge], latitudes[edge], forward[edge], middle)
            azimuth, _, _ = geod.inv(lon, lat, position[0], position[1])
            if _ahead(float(azimuth), float(back) + _HALF_TURN_DEG):
                low = middle
            else:
                high = middle
        offset = (low + high) / 2.0
        lon, lat, _ = geod.fwd(longitudes[edge], latitudes[edge], forward[edge], offset)
        _, _, distance = geod.inv(lon, lat, position[0], position[1])
        if float(distance) < best.distance_m:
            best = _Foot(float(distance), edge, offset, on_vertex=False)
    return best, lengths


def _ahead(toward_deg: float, heading_deg: float) -> bool:
    """Whether a position at azimuth ``toward_deg`` lies ahead of travel at ``heading_deg``."""
    return math.cos(math.radians(toward_deg - heading_deg)) > 0.0


def _line_parts(line: Geometry) -> list[list[Position]]:
    coordinates = cast("Sequence[object]", line.coordinates)
    if line.type == "Point":
        return [[_xy(cast("Sequence[float]", coordinates))]]
    if line.type == "LineString":
        return [_positions(coordinates)]
    return [_positions(part) for part in coordinates]


def _joined_at_antimeridian(parts: Sequence[Sequence[Position]], index: int, end: Position) -> bool:
    """Whether a part's end meets another part's end across the antimeridian."""
    longitude, latitude = end
    if abs(longitude) != _HALF_TURN_DEG:
        return False
    return any(
        other == (-longitude, latitude)
        for number, part in enumerate(parts)
        if number != index
        for other in (part[0], part[-1])
    )


def nearest_on_line(position: Position, line: Geometry, figure: Figure) -> Nearest:
    """Find the point of a line nearest a position, and whether it is the line's end.

    Each edge is a geodesic on the line's figure. A MultiLineString split at 180 degrees
    is measured part by part, and two parts that meet there are not ends of each other.

    Args:
        position: ``(longitude, latitude)`` in the line's coordinates (see ``place``).
        line: A LineString, a MultiLineString, or a Point segment.
        figure: The figure of the line's CRS.

    Returns:
        The distance, the part and fraction along it, and whether the point is an end.

    Raises:
        ValueError: The line is another type, or the figure is not its CRS's.
    """
    require_geometry(line, ("LineString", "MultiLineString", "Point"), "a measured line")
    _require_figure(line.crs, figure)
    parts = _line_parts(line)
    measured = [_nearest_on_part(part, position, figure) for part in parts]
    # The nearest part; a tie keeps the first.
    index = min(range(len(parts)), key=lambda number: (measured[number][0].distance_m, number))
    foot, lengths = measured[index]
    part = parts[index]
    total = sum(lengths)
    along = sum(lengths[: foot.edge]) + foot.offset_m
    last = len(part) - 1
    is_end = foot.on_vertex and foot.edge in {0, last} and part[0] != part[-1]
    at_end = is_end and not _joined_at_antimeridian(parts, index, part[foot.edge])
    return Nearest(
        distance_km=foot.distance_m / _METRES_PER_KM,
        part=index,
        fraction=along / total if total > 0.0 else 0.0,
        at_end=at_end,
    )


def closest_approach(points: Sequence[TrackPoint], position: Position, figure: Figure) -> Approach:
    """Find a forecast track's closest approach to a position, in distance and time.

    The points are taken in ``valid_at`` order. Between consecutive points the center moves
    along the geodesic at a constant rate in time, so the instant interpolates along the
    edge. A tie goes to the earliest instant, and one point is its own approach.

    Args:
        points: The forecast points.
        position: ``(longitude, latitude)`` in the points' coordinates (see ``place``).
        figure: The figure of the points' CRS.

    Returns:
        The minimum distance, its instant, and the hours from the first point to it.

    Raises:
        ValueError: There are no points, or the figure is not their CRS's.
    """
    if not points:
        message = "a forecast track needs at least one point"
        raise ValueError(message)
    ordered = sorted(points, key=lambda point: point.valid_at)
    for point in ordered:
        _require_figure(point.position.crs, figure)
    track = [_xy(cast("Sequence[float]", point.position.coordinates)) for point in ordered]
    foot, lengths = _nearest_on_part(track, position, figure)
    start = ordered[foot.edge].valid_at
    if foot.on_vertex:
        instant = start
    else:
        end = ordered[foot.edge + 1].valid_at
        instant = start + (end - start) * (foot.offset_m / lengths[foot.edge])
    return Approach(
        distance_km=foot.distance_m / _METRES_PER_KM,
        instant=instant,
        lead_h=(instant - ordered[0].valid_at).total_seconds() / _SECONDS_PER_HOUR,
    )
