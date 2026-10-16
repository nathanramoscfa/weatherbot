# src/weatherbot/models/geometry.py
"""GeoJSON-shaped geometry that always says which coordinate reference system it is in.

Live map queries ask for ``outSR=4326``, NWS GeoJSON is RFC 7946, and KML is WGS 84 by
its specification, so their geometry is ``EPSG:4326``. The replay corpus keeps the
archive's native geographic D_Sphere, so its geometry is ``native`` with the collection's
``source_crs`` WKT, verbatim. Validation checks structure, finite numbers, closed rings,
and, in a geographic CRS, longitude and latitude ranges. Shapely builds the shape and the
model records its verdict; nothing here repairs a shape, relabels a CRS, or transforms a
coordinate (repair is Phase 3's).
"""

import math
from collections.abc import Iterable, Mapping
from typing import Any, Final, Literal, Self, cast

import shapely
from pydantic import Field, model_validator
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from weatherbot.models.base import DomainModel

type GeometryType = Literal[
    "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"
]
type Position = tuple[float, float] | tuple[float, float, float]
type Coordinates = (
    Position
    | tuple[Position, ...]
    | tuple[tuple[Position, ...], ...]
    | tuple[tuple[tuple[Position, ...], ...], ...]
)

# How deeply each type nests positions: a Point is a position, a LineString a list of them.
_DEPTH: Final[Mapping[str, int]] = {
    "Point": 0,
    "MultiPoint": 1,
    "LineString": 1,
    "MultiLineString": 2,
    "Polygon": 2,
    "MultiPolygon": 3,
}
_MIN_LINE_POSITIONS: Final = 2
_MIN_RING_POSITIONS: Final = 4
_MAX_LONGITUDE: Final = 180.0
_MAX_LATITUDE: Final = 90.0
VALID_REASON: Final = "Valid Geometry"


class Crs(DomainModel):
    """A coordinate reference system: ``EPSG:4326``, or a native one with its WKT."""

    name: Literal["EPSG:4326", "native"]
    wkt: str | None = Field(default=None, description="The source WKT, verbatim (native).")
    datum: str | None = Field(default=None, description="The source datum name (native).")

    @classmethod
    def native(cls, source_crs: Mapping[str, object]) -> Self:
        """Build a native CRS from a replay collection's ``source_crs`` member, verbatim.

        Args:
            source_crs: The member: ``wkt`` and ``datum``.

        Returns:
            The native CRS.
        """
        return cls.model_validate(
            {"name": "native", "wkt": source_crs.get("wkt"), "datum": source_crs.get("datum")}
        )

    @model_validator(mode="after")
    def _wkt_belongs_to_native(self) -> Self:
        if self.name == "native" and not (self.wkt and self.wkt.strip()):
            message = "a native CRS needs its source WKT"
            raise ValueError(message)
        if self.name == "EPSG:4326" and (self.wkt is not None or self.datum is not None):
            message = "EPSG:4326 takes no WKT or datum"
            raise ValueError(message)
        return self

    @property
    def is_geographic(self) -> bool:
        """Whether coordinates are longitude and latitude in degrees."""
        if self.name == "EPSG:4326":
            return True
        return (self.wkt or "").lstrip().upper().startswith(("GEOGCS[", "GEOGCRS["))


WGS84: Final = Crs(name="EPSG:4326")
"""The CRS of live map queries (``outSR=4326``), NWS GeoJSON, and KML."""


def _positions(coordinates: Any, depth: int) -> Iterable[Any]:  # noqa: ANN401 - nested tuples
    if depth == 0:
        yield coordinates
        return
    for part in coordinates:
        yield from _positions(part, depth - 1)


def _structure_error(kind: str, coordinates: Any) -> str | None:  # noqa: ANN401, C901 - one rule per GeoJSON type
    depth = _DEPTH[kind]

    def nested(value: Any, level: int) -> bool:  # noqa: ANN401 - nested tuples
        if level == 0:
            return (
                isinstance(value, tuple)
                and len(value) in (2, 3)  # pyright: ignore[reportUnknownArgumentType]
                and all(isinstance(n, float) for n in value)  # pyright: ignore[reportUnknownVariableType]
            )
        return (
            isinstance(value, tuple)
            and len(value) > 0  # pyright: ignore[reportUnknownArgumentType]
            and all(nested(part, level - 1) for part in value)  # pyright: ignore[reportUnknownVariableType]
        )

    if not nested(coordinates, depth):
        return f"{kind} coordinates must nest positions {depth} level(s) deep"
    if kind == "LineString" and len(coordinates) < _MIN_LINE_POSITIONS:
        return "a LineString needs at least two positions"
    if kind == "MultiLineString" and any(len(line) < _MIN_LINE_POSITIONS for line in coordinates):
        return "each line of a MultiLineString needs at least two positions"
    rings: list[Any] = []
    if kind == "Polygon":
        rings = list(coordinates)
    elif kind == "MultiPolygon":
        rings = [ring for polygon in coordinates for ring in polygon]
    for ring in rings:
        if len(ring) < _MIN_RING_POSITIONS:
            return "a polygon ring needs at least four positions"
        if ring[0] != ring[-1]:
            return "a polygon ring must be closed"
    return None


class Geometry(DomainModel):
    """A GeoJSON-shaped geometry with an explicit CRS and Shapely's validity verdict.

    ``is_valid`` and ``validity_reason`` are Shapely's verdict on the coordinates as
    received; they are filled in when absent and checked when present. An invalid shape is
    kept as it is, with its reason: repairing it is Phase 3's decision.
    """

    type: GeometryType
    coordinates: Coordinates = Field(repr=False)
    crs: Crs
    is_valid: bool = False
    validity_reason: str = ""

    @classmethod
    def from_geojson(cls, mapping: Mapping[str, object], crs: Crs) -> Self:
        """Build a geometry from a GeoJSON geometry object, keeping every coordinate.

        Args:
            mapping: The GeoJSON ``geometry`` member: ``type`` and ``coordinates``.
            crs: The CRS the source states; it is recorded, never changed.

        Returns:
            The geometry.
        """
        return cls.model_validate(
            {
                "type": mapping.get("type"),
                "coordinates": _tupled(mapping.get("coordinates")),
                "crs": crs,
            }
        )

    @model_validator(mode="after")
    def _checked(self) -> Self:
        problem = _structure_error(self.type, self.coordinates)
        if problem is not None:
            raise ValueError(problem)
        numbers = [n for p in _positions(self.coordinates, _DEPTH[self.type]) for n in p]
        if not all(math.isfinite(n) for n in numbers):
            message = "coordinates must be finite numbers"
            raise ValueError(message)
        if self.crs.is_geographic:
            for position in _positions(self.coordinates, _DEPTH[self.type]):
                if abs(position[0]) > _MAX_LONGITUDE or abs(position[1]) > _MAX_LATITUDE:
                    # The message names the rule, never the coordinate.
                    message = "a longitude or latitude is out of range for a geographic CRS"
                    raise ValueError(message)
        built = self.to_shapely()
        valid = bool(shapely.is_valid(built))
        reason = str(shapely.is_valid_reason(built))
        fields = self.model_fields_set
        if ("is_valid" in fields and self.is_valid != valid) or (
            "validity_reason" in fields and self.validity_reason != reason
        ):
            message = "is_valid and validity_reason must be Shapely's verdict"
            raise ValueError(message)
        # The verdict is derived, not chosen: record it on the frozen instance once.
        object.__setattr__(self, "is_valid", valid)
        object.__setattr__(self, "validity_reason", reason)
        return self

    def to_shapely(self) -> BaseGeometry:
        """Build the Shapely shape of these coordinates, in this geometry's own CRS.

        Returns:
            The shape; its coordinates are this geometry's, untransformed.
        """
        return shape({"type": self.type, "coordinates": self.coordinates})


def require_geometry(geometry: Geometry, allowed: tuple[GeometryType, ...], what: str) -> None:
    """Refuse a geometry whose type a record does not allow.

    Args:
        geometry: The geometry.
        allowed: The types the record allows.
        what: The record's name, for the message.

    Raises:
        ValueError: The geometry's type is not allowed.
    """
    if geometry.type not in allowed:
        message = f"{what} geometry must be one of {', '.join(allowed)}, not {geometry.type}"
        raise ValueError(message)


def _tupled(value: object) -> object:
    """Turn the lists of parsed JSON into tuples and integers into floats, values unchanged."""
    if isinstance(value, list | tuple):
        return tuple(_tupled(item) for item in cast("Iterable[object]", value))
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value
