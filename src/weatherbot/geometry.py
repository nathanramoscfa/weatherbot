# src/weatherbot/geometry.py
"""Geometry helpers for weatherbot."""

import json
import logging
from pathlib import Path

from shapely.geometry import Point, Polygon, shape
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)


def load_county_polygon(geojson_path: Path) -> Polygon:
    """Load county polygon from GeoJSON file.

    Args:
        geojson_path: Path to GeoJSON file

    Returns:
        County polygon

    Raises:
        FileNotFoundError: If GeoJSON file doesn't exist
        ValueError: If GeoJSON is invalid or has no features
    """
    if not geojson_path.exists():
        raise FileNotFoundError(f"County GeoJSON file not found: {geojson_path}")

    try:
        with open(geojson_path, encoding="utf-8") as f:
            geojson_data = json.load(f)

        if "features" not in geojson_data or not geojson_data["features"]:
            raise ValueError("GeoJSON must contain at least one feature")

        # Use the first feature's geometry
        first_feature = geojson_data["features"][0]
        geometry = shape(first_feature["geometry"])

        if not isinstance(geometry, Polygon):
            raise ValueError("First feature must be a Polygon")

        logger.debug(f"Loaded county polygon from {geojson_path}")
        return geometry

    except Exception as e:
        logger.error(f"Failed to load county polygon from {geojson_path}: {e}")
        raise


def point_in_any(polygons: list[BaseGeometry], point: tuple[float, float]) -> bool:
    """Check if a point intersects any polygon.

    Args:
        polygons: List of polygons to check
        point: Point coordinates (longitude, latitude)

    Returns:
        True if point is in any polygon
    """
    if not polygons:
        return False

    shapely_point = Point(point[0], point[1])

    for polygon in polygons:
        try:
            if polygon.contains(shapely_point) or polygon.intersects(shapely_point):
                return True
        except Exception as e:
            logger.warning(f"Error checking point intersection: {e}")
            continue

    return False


def polygon_intersects_any(
    polygons: list[BaseGeometry],
    target_polygon: Polygon,
) -> bool:
    """Check if target polygon intersects any of the given polygons.

    Args:
        polygons: List of polygons to check against
        target_polygon: Polygon to check for intersection

    Returns:
        True if target polygon intersects any polygon
    """
    if not polygons:
        return False

    for polygon in polygons:
        try:
            if polygon.intersects(target_polygon):
                return True
        except Exception as e:
            logger.warning(f"Error checking polygon intersection: {e}")
            continue

    return False


def create_point(longitude: float, latitude: float) -> Point:
    """Create a Shapely Point from coordinates.

    Args:
        longitude: Longitude in decimal degrees
        latitude: Latitude in decimal degrees

    Returns:
        Shapely Point object
    """
    return Point(longitude, latitude)


def validate_coordinates(longitude: float, latitude: float) -> None:
    """Validate coordinate values.

    Args:
        longitude: Longitude in decimal degrees
        latitude: Latitude in decimal degrees

    Raises:
        ValueError: If coordinates are invalid
    """
    if not -180 <= longitude <= 180:
        raise ValueError(f"Invalid longitude: {longitude}")
    if not -90 <= latitude <= 90:
        raise ValueError(f"Invalid latitude: {latitude}")
