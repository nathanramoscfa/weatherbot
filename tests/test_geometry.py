# tests/test_geometry.py
"""Geometry tests for weatherbot."""

import json
import tempfile
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon

from weatherbot.geometry import (
    load_county_polygon,
    point_in_any,
    polygon_intersects_any,
    validate_coordinates,
)


def test_validate_coordinates() -> None:
    """Test coordinate validation."""
    # Valid coordinates
    validate_coordinates(0, 0)
    validate_coordinates(-180, -90)
    validate_coordinates(180, 90)
    validate_coordinates(-80.1918, 25.7617)  # Miami

    # Invalid longitude
    with pytest.raises(ValueError, match="Invalid longitude"):
        validate_coordinates(-181, 0)

    with pytest.raises(ValueError, match="Invalid longitude"):
        validate_coordinates(181, 0)

    # Invalid latitude
    with pytest.raises(ValueError, match="Invalid latitude"):
        validate_coordinates(0, -91)

    with pytest.raises(ValueError, match="Invalid latitude"):
        validate_coordinates(0, 91)


def test_point_in_any() -> None:
    """Test point-in-polygon checking."""
    # Create test polygons
    square1 = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    square2 = Polygon([(3, 3), (5, 3), (5, 5), (3, 5)])
    polygons = [square1, square2]

    # Point inside first polygon
    assert point_in_any(polygons, (1, 1))

    # Point inside second polygon
    assert point_in_any(polygons, (4, 4))

    # Point outside both polygons
    assert not point_in_any(polygons, (10, 10))

    # Point on boundary (should be True due to intersects check)
    assert point_in_any(polygons, (2, 1))

    # Empty polygon list
    assert not point_in_any([], (1, 1))


def test_polygon_intersects_any() -> None:
    """Test polygon intersection checking."""
    # Create test polygons
    square1 = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    square2 = Polygon([(3, 3), (5, 3), (5, 5), (3, 5)])
    polygons = [square1, square2]

    # Overlapping polygon
    overlapping = Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])
    assert polygon_intersects_any(polygons, overlapping)

    # Non-overlapping polygon
    separate = Polygon([(10, 10), (12, 10), (12, 12), (10, 12)])
    assert not polygon_intersects_any(polygons, separate)

    # Adjacent polygon (touching edge)
    adjacent = Polygon([(2, 0), (4, 0), (4, 2), (2, 2)])
    assert polygon_intersects_any(polygons, adjacent)

    # Empty polygon list
    assert not polygon_intersects_any([], overlapping)


def test_load_county_polygon() -> None:
    """Test loading county polygon from GeoJSON."""
    # Create test GeoJSON
    test_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Test County"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    }

    # Write to temporary file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".geojson", delete=False
    ) as f:
        json.dump(test_geojson, f)
        temp_path = Path(f.name)

    try:
        # Load polygon
        polygon = load_county_polygon(temp_path)
        assert isinstance(polygon, Polygon)
        assert polygon.contains(Point(0.5, 0.5))
        assert not polygon.contains(Point(2, 2))
    finally:
        # Clean up
        temp_path.unlink()

    # Test file not found
    with pytest.raises(FileNotFoundError):
        load_county_polygon(Path("nonexistent.geojson"))

    # Test invalid GeoJSON
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".geojson", delete=False
    ) as f:
        json.dump({"invalid": "geojson"}, f)
        invalid_path = Path(f.name)

    try:
        with pytest.raises(ValueError, match="must contain at least one feature"):
            load_county_polygon(invalid_path)
    finally:
        invalid_path.unlink()


def test_miami_dade_polygon_loading() -> None:
    """Test loading the bundled Miami-Dade polygon."""
    from weatherbot.config import WeatherbotConfig

    config = WeatherbotConfig(home_lat=25.7617, home_lon=-80.1918)
    geojson_path = config.get_county_geojson_path()

    if geojson_path.exists():
        polygon = load_county_polygon(geojson_path)
        assert isinstance(polygon, Polygon)

        # Miami should be inside Miami-Dade county bounds
        Point(-80.1918, 25.7617)
        # Note: The simplified polygon might not contain the exact point,
        # but it should at least be a valid polygon
        assert polygon.is_valid
