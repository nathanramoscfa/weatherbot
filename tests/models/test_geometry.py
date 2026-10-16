# tests/models/test_geometry.py
"""Geometry: structure, ranges, Shapely's verdict, and a CRS that is never relabeled."""

import gzip
import json
from pathlib import Path
from typing import cast

import pytest
import shapely
from model_samples import REPOSITORY_ROOT, TROPICAL, landmark_point, landmark_square
from pydantic import ValidationError

from weatherbot.models import WGS84, Crs, Geometry

REPLAY = REPOSITORY_ROOT / "tests/fixtures/replay"


def replay_collection(path: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(gzip.decompress(path.read_bytes())))


def recorded_collections() -> list[Path]:
    return sorted(TROPICAL.glob("query-*.geojson"))


@pytest.mark.parametrize("path", recorded_collections(), ids=lambda p: p.name)
def test_every_recorded_live_geometry_builds_unchanged(path: Path) -> None:
    features = cast("list[dict[str, object]]", json.loads(path.read_text("utf-8"))["features"])

    for feature in features:
        source = cast("dict[str, object]", feature["geometry"])
        geometry = Geometry.from_geojson(source, WGS84)
        assert json.loads(geometry.model_dump_json(include={"type", "coordinates"})) == {
            "type": source["type"],
            "coordinates": source["coordinates"],
        }
        assert geometry.crs == WGS84


def test_every_replay_geometry_of_one_storm_keeps_its_native_crs() -> None:
    paths = sorted((REPLAY / "AL052019").glob("*/*.geojson.gz"))
    assert paths

    for path in paths:
        collection = replay_collection(path)
        crs = Crs.native(cast("dict[str, object]", collection["source_crs"]))
        assert crs.wkt == cast("dict[str, object]", collection["source_crs"])["wkt"]
        assert crs.is_geographic
        for feature in cast("list[dict[str, object]]", collection["features"]):
            geometry = Geometry.from_geojson(cast("dict[str, object]", feature["geometry"]), crs)
            assert geometry.crs.name == "native"
            if path.name.startswith("cone"):
                assert geometry.is_valid


def test_shapely_s_verdict_is_recorded_and_an_invalid_shape_is_kept() -> None:
    square = cast("tuple[tuple[tuple[float, float], ...], ...]", landmark_square().coordinates)
    a, b, c, d, _ = square[0]
    bowtie = Geometry(type="Polygon", coordinates=((a, c, b, d, a),), crs=WGS84)

    assert landmark_square().is_valid
    assert landmark_square().validity_reason == "Valid Geometry"
    assert not bowtie.is_valid
    assert bowtie.validity_reason.startswith("Self-intersection")
    assert bowtie.coordinates == ((a, c, b, d, a),)
    assert Geometry.model_validate_json(bowtie.model_dump_json()) == bowtie


def test_a_verdict_that_disagrees_with_shapely_is_rejected() -> None:
    document = json.loads(landmark_square().model_dump_json())
    document["is_valid"] = False

    with pytest.raises(ValidationError, match="Shapely"):
        Geometry.model_validate_json(json.dumps(document))


def test_to_shapely_keeps_every_coordinate() -> None:
    square = landmark_square()

    shape = square.to_shapely()

    assert shape.geom_type == "Polygon"
    assert shapely.get_coordinates(shape).tolist() == [list(p) for p in square_ring()]


def square_ring() -> tuple[tuple[float, float], ...]:
    return cast("tuple[tuple[tuple[float, float], ...], ...]", landmark_square().coordinates)[0]


@pytest.mark.parametrize(
    ("kind", "coordinates", "reason"),
    [
        ("Polygon", (square_ring()[:-1],), "closed"),
        ("Polygon", (square_ring()[:3],), "four positions"),
        ("LineString", (square_ring()[0],), "two positions"),
        ("MultiLineString", ((square_ring()[0],),), "two positions"),
        ("Point", square_ring(), "level"),
        ("MultiPolygon", (), "level"),
        ("Polygon", ((),), "level"),
    ],
)
def test_malformed_structure_is_rejected(kind: str, coordinates: object, reason: str) -> None:
    with pytest.raises(ValidationError, match=reason):
        Geometry.model_validate({"type": kind, "coordinates": coordinates, "crs": WGS84})


def test_a_geometry_collection_is_not_a_geometry_type() -> None:
    with pytest.raises(ValidationError):
        Geometry.from_geojson({"type": "GeometryCollection", "coordinates": ()}, WGS84)


@pytest.mark.parametrize("axis", [0, 1])
def test_an_out_of_range_coordinate_in_a_geographic_crs_is_rejected(axis: int) -> None:
    lon, lat = cast("tuple[float, float]", landmark_point().coordinates)
    shifted = (lon + 360.0, lat) if axis == 0 else (lon, lat + 180.0)

    with pytest.raises(ValidationError, match="out of range") as error:
        Geometry(type="Point", coordinates=shifted, crs=WGS84)
    assert str(shifted[axis]) not in str(error.value)


def test_a_projected_native_crs_skips_the_degree_range_check() -> None:
    projected = Crs.native({"wkt": 'PROJCS["WGS_1984_Web_Mercator_Auxiliary_Sphere"]'})
    lon, lat = cast("tuple[float, float]", landmark_point().coordinates)

    geometry = Geometry(type="Point", coordinates=(lon * 1e5, lat * 1e5), crs=projected)

    assert not projected.is_geographic
    assert geometry.crs == projected


def test_non_finite_numbers_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Geometry(type="Point", coordinates=(float("nan"), 0.0), crs=WGS84)


@pytest.mark.parametrize(
    "crs",
    [
        {"name": "native"},
        {"name": "native", "wkt": " "},
        {"name": "EPSG:4326", "wkt": "GEOGCS[]"},
        {"name": "EPSG:3857"},
    ],
)
def test_a_crs_is_explicit_and_complete(crs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Crs.model_validate(crs)


def test_no_geometry_function_relabels_or_transforms() -> None:
    names = {name for name in dir(Geometry) if not name.startswith("_")}
    names |= {name for name in dir(Crs) if not name.startswith("_")}

    assert not {
        name
        for name in names
        if any(w in name for w in ("transform", "reproject", "relabel", "to_crs"))
    }
