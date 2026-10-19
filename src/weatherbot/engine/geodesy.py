# src/weatherbot/engine/geodesy.py
"""The figure of the Earth each geometry is measured on, and geodesic distance and bearing.

Every geometry says which CRS it is in, and the CRS implies the figure: live geometry is
``EPSG:4326``, measured on the WGS 84 ellipsoid; replay geometry keeps the archive's
native geographic ``D_Sphere``, measured on the sphere its WKT names (radius 6,371,200 m).
Nothing is relabelled. Distances and bearings go through ``pyproj.Geod`` alone: no
``Transformer``, no PROJ database, and no network.
"""

import math
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Final

from pyproj import Geod

from weatherbot.models import Crs

type Position = tuple[float, float]
"""A longitude and a latitude, in degrees, in a figure's own coordinates."""

WGS84_NAME: Final = "WGS 84"
WGS84_SEMI_MAJOR_M: Final = 6378137.0
WGS84_INVERSE_FLATTENING: Final = 298.257223563
_FULL_TURN_DEG: Final = 360.0
_METRES_PER_KM: Final = 1000.0
_DEGREE_RADIANS: Final = math.pi / 180.0
_SPHEROIDS: Final = frozenset({"SPHEROID", "ELLIPSOID"})
_LENGTH_UNITS: Final = frozenset({"UNIT", "LENGTHUNIT"})
_ANGLE_UNITS: Final = frozenset({"UNIT", "ANGLEUNIT"})
_MALFORMED: Final = "WKT rule: the text is not well-formed WKT"
_TOKEN: Final = re.compile(
    r'\s*(?:(?P<open>[\[(])|(?P<close>[])])|(?P<comma>,)|"(?P<string>(?:[^"]|"")*)"'
    r"|(?P<number>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)(?![\w.])"
    r"|(?P<word>[A-Za-z_]\w*))"
)


@dataclass(frozen=True, slots=True)
class Figure:
    """A figure of the Earth: a named ellipsoid or sphere, and the ``Geod`` that measures on it.

    ``inverse_flattening`` is 0 for a sphere, as WKT writes it. Two figures are equal when
    their name, semi-major axis, and inverse flattening are.
    """

    name: str
    semi_major_m: float
    inverse_flattening: float
    geod: Geod = field(compare=False, repr=False)

    @property
    def is_sphere(self) -> bool:
        """Whether the figure is a sphere (no flattening)."""
        return self.inverse_flattening == 0.0


def _build(name: str, semi_major_m: float, inverse_flattening: float) -> Figure:
    flattening = 0.0 if inverse_flattening == 0.0 else 1.0 / inverse_flattening
    return Figure(name, semi_major_m, inverse_flattening, Geod(a=semi_major_m, f=flattening))


@dataclass(frozen=True, slots=True)
class _Node:
    """One WKT keyword and its arguments: strings, numbers, bare words, and nested nodes."""

    keyword: str
    arguments: tuple["str | float | _Node", ...]

    def walk(self) -> Iterator["_Node"]:
        """Yield this node and every node under it, depth first."""
        yield self
        for argument in self.arguments:
            if isinstance(argument, _Node):
                yield from argument.walk()

    def number(self, index: int, what: str) -> float:
        """Return the ``index``-th number among this node's own arguments."""
        numbers = [argument for argument in self.arguments if isinstance(argument, float)]
        if len(numbers) <= index:
            message = f"WKT rule: {what} is missing a number"
            raise ValueError(message)
        return numbers[index]


class _Parser:
    """A recursive-descent reader of ``KEYWORD[argument, ...]``, with ``[]`` or ``()``."""

    def __init__(self, wkt: str) -> None:
        self._tokens: list[tuple[str, str]] = []
        text = wkt.strip()
        position = 0
        while position < len(text):
            match = _TOKEN.match(text, position)
            if match is None or match.lastgroup is None:
                raise ValueError(_MALFORMED)
            self._tokens.append((match.lastgroup, match[match.lastgroup]))
            position = match.end()
        self._index = 0

    def _kind(self, offset: int = 0) -> str:
        index = self._index + offset
        return self._tokens[index][0] if index < len(self._tokens) else "end"

    def document(self) -> _Node:
        root = self._node()
        if self._kind() != "end":
            raise ValueError(_MALFORMED)
        return root

    def _node(self) -> _Node:
        if self._kind() != "word" or self._kind(1) != "open":
            raise ValueError(_MALFORMED)
        keyword = self._tokens[self._index][1].upper()
        self._index += 2
        arguments: list[str | float | _Node] = [self._argument()]
        while self._kind() == "comma":
            self._index += 1
            arguments.append(self._argument())
        if self._kind() != "close":
            raise ValueError(_MALFORMED)
        self._index += 1
        return _Node(keyword, tuple(arguments))

    def _argument(self) -> "str | float | _Node":
        kind = self._kind()
        if kind == "word" and self._kind(1) == "open":
            return self._node()
        if kind not in {"string", "number", "word"}:
            raise ValueError(_MALFORMED)
        value = self._tokens[self._index][1]
        self._index += 1
        return float(value) if kind == "number" else value.replace('""', '"')


def _geographic_root(wkt: str) -> _Node:
    root = _Parser(wkt).document()
    if root.keyword in {"PROJCS", "PROJCRS"}:
        message = "WKT rule: a projected CRS is refused; the engine measures geographic CRSs"
        raise ValueError(message)
    if root.keyword not in {"GEOGCS", "GEOGCRS"}:
        message = "WKT rule: the top-level node must be GEOGCS or GEOGCRS"
        raise ValueError(message)
    return root


def _spheroid(nodes: Sequence[_Node]) -> _Node:
    spheroids = [node for node in nodes if node.keyword in _SPHEROIDS]
    if len(spheroids) != 1:
        message = "WKT rule: a geographic CRS must name exactly one spheroid"
        raise ValueError(message)
    # A unit inside the spheroid is its length unit.
    for unit in (node for node in spheroids[0].walk() if node.keyword in _LENGTH_UNITS):
        if unit.number(0, "a length unit") != 1.0:
            message = "WKT rule: a spheroid's length unit must be the metre"
            raise ValueError(message)
    return spheroids[0]


def _require_degrees_from_greenwich(nodes: Sequence[_Node], spheroid: _Node) -> None:
    inside = list(spheroid.walk())
    # Every unit outside the spheroid is angular.
    angular = [
        node
        for node in nodes
        if node.keyword in _ANGLE_UNITS and not any(node is other for other in inside)
    ]
    if not angular:
        message = "WKT rule: a geographic CRS must name its angular unit"
        raise ValueError(message)
    for unit in angular:
        if not math.isclose(unit.number(0, "an angular unit"), _DEGREE_RADIANS, rel_tol=1e-12):
            message = "WKT rule: the angular unit must be the degree"
            raise ValueError(message)
    for meridian in (node for node in nodes if node.keyword == "PRIMEM"):
        if meridian.number(0, "a prime meridian") != 0.0:
            message = "WKT rule: the prime meridian must be Greenwich"
            raise ValueError(message)


def _figure_from_wkt(wkt: str) -> Figure:
    """Read the figure of a geographic CRS from its WKT, refusing anything ambiguous."""
    nodes = list(_geographic_root(wkt).walk())
    spheroid = _spheroid(nodes)
    _require_degrees_from_greenwich(nodes, spheroid)
    names = [argument for argument in spheroid.arguments if isinstance(argument, str)]
    semi_major_m = spheroid.number(0, "a spheroid")
    inverse_flattening = spheroid.number(1, "a spheroid")
    if not names or semi_major_m <= 0.0 or inverse_flattening < 0.0:
        message = "WKT rule: a spheroid needs a name, a positive axis, and a flattening"
        raise ValueError(message)
    return _build(names[0], semi_major_m, inverse_flattening)


@cache
def _figure(wkt: str | None) -> Figure:
    if wkt is None:
        return _build(WGS84_NAME, WGS84_SEMI_MAJOR_M, WGS84_INVERSE_FLATTENING)
    return _figure_from_wkt(wkt)


def figure_of(crs: Crs) -> Figure:
    """Return the figure a CRS implies, cached by CRS.

    ``EPSG:4326`` is WGS 84. A ``native`` CRS is read from its WKT by a strict parser: the
    top-level node must be ``GEOGCS`` or ``GEOGCRS``, with exactly one ``SPHEROID`` or
    ``ELLIPSOID`` (name, semi-major axis in metres, inverse flattening), the degree as its
    angular unit, and Greenwich as its prime meridian.

    Args:
        crs: The CRS a geometry records.

    Returns:
        The figure to measure that geometry on.

    Raises:
        ValueError: The WKT is projected, malformed, or ambiguous; the message names the
            rule, never the WKT.
    """
    # The CRS model admits a WKT exactly when the CRS is native.
    return _figure(crs.wkt)


def distance_km(a: Position, b: Position, figure: Figure) -> float:
    """Return the geodesic distance between two positions, in kilometres.

    Args:
        a: A ``(longitude, latitude)`` in the figure's coordinates.
        b: Another.
        figure: The figure both positions are on.

    Returns:
        The length of the shortest geodesic between them.
    """
    _, _, metres = figure.geod.inv(a[0], a[1], b[0], b[1])
    return float(metres) / _METRES_PER_KM


def initial_bearing_deg(a: Position, b: Position, figure: Figure) -> float:
    """Return the initial bearing of the geodesic from ``a`` toward ``b``.

    Args:
        a: The ``(longitude, latitude)`` the bearing is taken from.
        b: The position it points toward.
        figure: The figure both positions are on.

    Returns:
        Degrees clockwise from true north, from 0 to under 360.
    """
    azimuth, _, _ = figure.geod.inv(a[0], a[1], b[0], b[1])
    bearing = float(azimuth) % _FULL_TURN_DEG
    # A tiny negative azimuth rounds up to a full turn under the modulo.
    return 0.0 if bearing >= _FULL_TURN_DEG else bearing
