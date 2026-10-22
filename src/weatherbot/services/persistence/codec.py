# src/weatherbot/services/persistence/codec.py
"""How a domain model becomes columns and comes back equal.

A product splits into its geometry (GeoJSON in its own CRS, recorded as ``EPSG:4326`` or
the verbatim WKT and datum), its provenance, and its other fields. A product of several
shapes stores them as a FeatureCollection whose features carry each part's fields. Every
model comes back through ``model_validate_json``, so it passes the same strict checks it
passed when it was parsed, and Shapely's verdict is recomputed, never stored.

A product's content is everything but its provenance, as canonical JSON: equal products
have equal content whichever fetch they came from, so its SHA-256 names it alone.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final, cast

from pydantic import BaseModel

from weatherbot.models import (
    WGS84,
    ArrivalTimeProduct,
    Breakpoint,
    ConeGeometry,
    Crs,
    DisplayLayer,
    DomainModel,
    ForecastTrack,
    OutlookArea,
    OutlookGraphic,
    TrackPoint,
    WatchWarningSegment,
    WindProbabilityProduct,
    WindRadii,
)

type Json = dict[str, Any]

PRODUCT_MODELS: Final[Mapping[str, type[DomainModel]]] = MappingProxyType(
    {
        "cone": ConeGeometry,
        "track_point": TrackPoint,
        "track": ForecastTrack,
        "watch_warning": WatchWarningSegment,
        "wind_radii": WindRadii,
        "arrival_time": ArrivalTimeProduct,
        "outlook_area": OutlookArea,
        "wind_probability": WindProbabilityProduct,
        "breakpoint": Breakpoint,
        "display_layer": DisplayLayer,
        "outlook_graphic": OutlookGraphic,
    }
)
# The field that holds a product's one geometry, or its list of shapes.
_GEOMETRY_FIELD: Final = MappingProxyType(
    {
        "cone": "geometry",
        "track_point": "position",
        "track": "geometry",
        "watch_warning": "geometry",
        "wind_radii": "geometry",
        "outlook_area": "geometry",
        "breakpoint": "position",
    }
)
_PARTS_FIELD: Final = MappingProxyType({"arrival_time": "lines", "wind_probability": "bands"})


def crs_columns(crs: Crs) -> tuple[str, str | None]:
    """Spell a CRS as columns: ``EPSG:4326``, or the verbatim WKT and its datum.

    Args:
        crs: The CRS.

    Returns:
        The CRS text and the datum.
    """
    if crs.name == "EPSG:4326":
        return crs.name, None
    return cast("str", crs.wkt), crs.datum


def crs_from_columns(text: str, datum: str | None) -> Crs:
    """Read a CRS back from its columns.

    Args:
        text: ``EPSG:4326``, or the verbatim WKT.
        datum: The native datum.

    Returns:
        The CRS.
    """
    if text == WGS84.name:
        return WGS84
    return Crs(name="native", wkt=text, datum=datum)


def _json_default(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    message = f"{type(value).__name__} is not JSON"
    raise TypeError(message)


def validated[M: BaseModel](model: type[M], data: Mapping[str, object]) -> M:
    """Build a model through its JSON validation, as a parser's output was built.

    Args:
        model: The model.
        data: Its fields; models and instants are written as JSON first.

    Returns:
        The model.
    """
    return model.model_validate_json(json.dumps(data, default=_json_default))


def dump(model: BaseModel) -> Json:
    """Return a model's JSON as a mapping.

    Args:
        model: The model.

    Returns:
        Its JSON.
    """
    return model.model_dump(mode="json")


def geojson(geometry: Json) -> Json:
    """Return a dumped geometry as a GeoJSON geometry: its type and coordinates only.

    Args:
        geometry: A dumped ``Geometry``.

    Returns:
        The GeoJSON geometry.
    """
    return {"type": geometry["type"], "coordinates": geometry["coordinates"]}


def with_crs(geometry: Json, crs: Crs) -> Json:
    """Return a GeoJSON geometry as a dumped ``Geometry`` in a CRS.

    Args:
        geometry: The GeoJSON geometry.
        crs: Its CRS.

    Returns:
        The ``Geometry`` fields; Shapely's verdict is recomputed on validation.
    """
    return {**geojson(geometry), "crs": dump(crs)}


@dataclass(frozen=True)
class EncodedProduct:
    """A product as columns: its content's, and its provenance."""

    crs: str | None
    crs_datum: str | None
    geojson: Json | None
    properties: Json
    provenance: Json


def _shared_crs(crs_values: list[Json]) -> Crs | None:
    distinct = {json.dumps(value, sort_keys=True) for value in crs_values}
    if len(distinct) > 1:
        message = "a product's shapes share one CRS"
        raise ValueError(message)
    return Crs.model_validate_json(distinct.pop()) if distinct else None


def encode_product(kind: str, record: DomainModel) -> EncodedProduct:
    """Split a product into its columns.

    Args:
        kind: The product kind (``PRODUCT_MODELS``).
        record: The product.

    Returns:
        Its columns.

    Raises:
        ValueError: The record is not of its kind, or its shapes are in two CRSs.
    """
    if type(record) is not PRODUCT_MODELS[kind]:
        message = f"a {kind} product is a {PRODUCT_MODELS[kind].__name__}"
        raise ValueError(message)
    data = dump(record)
    provenance = cast("Json", data.pop("provenance"))
    crs: Crs | None = None
    shape: Json | None = None
    if kind in _GEOMETRY_FIELD:
        geometry = cast("Json", data.pop(_GEOMETRY_FIELD[kind]))
        crs, shape = Crs.model_validate(geometry["crs"]), geojson(geometry)
    elif kind in _PARTS_FIELD:
        parts = cast("list[Json]", data.pop(_PARTS_FIELD[kind]))
        crs = _shared_crs([part["geometry"]["crs"] for part in parts])
        features: list[Json] = []
        for part in parts:
            geometry = cast("Json", part.pop("geometry"))
            features.append({"type": "Feature", "geometry": geojson(geometry), "properties": part})
        shape = {"type": "FeatureCollection", "features": features}
    elif kind == "display_layer":
        shape = cast("Json", data.pop("feature_collection"))
        crs = Crs.model_validate(data.pop("crs"))
    text, datum = crs_columns(crs) if crs is not None else (None, None)
    return EncodedProduct(
        crs=text, crs_datum=datum, geojson=shape, properties=data, provenance=provenance
    )


def canonical_content(kind: str, encoded: EncodedProduct) -> bytes:
    """Return a product's content, everything but its provenance, as canonical JSON.

    A provenance carries its fetch's instant, so it differs on every fetch of an unchanged
    product; leaving it out lets every snapshot of the product share one content.

    Args:
        kind: The product kind.
        encoded: Its columns.

    Returns:
        The kind, CRS, datum, GeoJSON, and properties as sorted, compact JSON in UTF-8.
    """
    content = {
        "product_kind": kind,
        "crs": encoded.crs,
        "crs_datum": encoded.crs_datum,
        "geojson": encoded.geojson,
        "properties": encoded.properties,
    }
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


def from_content(content: bytes, provenance: Json) -> EncodedProduct:
    """Read a product's columns back from its canonical content and its provenance.

    Args:
        content: The canonical JSON ``canonical_content`` wrote.
        provenance: The provenance it was linked with.

    Returns:
        The columns, equal to the ones encoded.
    """
    data = cast("Json", json.loads(content))
    return EncodedProduct(
        crs=data["crs"],
        crs_datum=data["crs_datum"],
        geojson=data["geojson"],
        properties=data["properties"],
        provenance=provenance,
    )


def decode_product(kind: str, encoded: EncodedProduct) -> DomainModel:
    """Rebuild a product from its columns.

    Args:
        kind: The product kind.
        encoded: Its columns.

    Returns:
        The product, equal to the one encoded.
    """
    data: Json = {**encoded.properties, "provenance": encoded.provenance}
    crs = crs_from_columns(encoded.crs, encoded.crs_datum) if encoded.crs is not None else None
    shape = encoded.geojson
    if kind in _GEOMETRY_FIELD and shape is not None and crs is not None:
        data[_GEOMETRY_FIELD[kind]] = with_crs(shape, crs)
    elif kind in _PARTS_FIELD and shape is not None:
        features = cast("list[Json]", shape["features"])
        data[_PARTS_FIELD[kind]] = [
            {**feature["properties"], "geometry": with_crs(feature["geometry"], cast("Crs", crs))}
            for feature in features
        ]
    elif kind == "display_layer" and crs is not None:
        data["feature_collection"] = shape
        data["crs"] = dump(crs)
    return validated(PRODUCT_MODELS[kind], data)
