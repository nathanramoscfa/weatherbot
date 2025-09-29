# src/weatherbot/nhc_current_storms.py
"""Enhanced NHC current storms data fetching using CurrentStorms.json."""

import contextlib
import logging
from typing import Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .cache import api_cache
from .nhc import NHCCone

logger = logging.getLogger(__name__)

# NHC CurrentStorms JSON API
CURRENT_STORMS_JSON = "https://www.nhc.noaa.gov/CurrentStorms.json"

# Request timeout
REQUEST_TIMEOUT = 30


class CurrentStormsClient:
    """Client for fetching current storm data from NHC CurrentStorms.json."""

    def __init__(self, timeout: int = REQUEST_TIMEOUT) -> None:
        """Initialize client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "weatherbot (alerts@example.com)"
        })

    @retry(
        retry=retry_if_exception_type((requests.RequestException,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def _make_request(self, url: str) -> dict:
        """Make HTTP request with caching.

        Args:
            url: Request URL

        Returns:
            JSON response data
        """
        import hashlib
        cache_key = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()

        # Try cache first
        cached_data = api_cache.get(cache_key)
        if cached_data is not None:
            logger.debug(f"Using cached data for: {url}")
            return cached_data

        logger.debug(f"Making request to: {url}")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()

        # Cache the response
        api_cache.set(cache_key, data)

        return data

    def fetch_current_storms(self) -> list[NHCCone]:
        """Fetch current active storms with precise coordinates.

        Returns:
            List of current storms as NHCCone objects
        """
        try:
            # Get current storms metadata
            storms_data = self._make_request(CURRENT_STORMS_JSON)

            active_storms = storms_data.get("activeStorms", [])
            if not active_storms:
                logger.info("No active storms found in CurrentStorms.json")
                return []

            cones = []
            for storm in active_storms:
                try:
                    cone = self._parse_storm_data(storm)
                    if cone:
                        # Try to get precise track data
                        track_positions = self._get_storm_track_positions(storm)
                        if track_positions:
                            # Use most recent position
                            cone.current_position = track_positions[-1]

                        cones.append(cone)
                        logger.info(f"Added current storm: {cone}")
                except Exception as e:
                    logger.warning(f"Failed to parse storm: {e}")
                    continue

            logger.info(f"Fetched {len(cones)} current storms from CurrentStorms.json")
            return cones

        except Exception as e:
            logger.error(f"Failed to fetch current storms: {e}")
            return []

    def _parse_storm_data(self, storm: dict) -> NHCCone | None:
        """Parse storm data from CurrentStorms.json.

        Args:
            storm: Storm data dictionary

        Returns:
            NHCCone object or None
        """
        try:
            # Extract basic information
            storm_name = storm.get("name") or storm.get("tcName")
            storm_id = storm.get("id") or storm.get("tcid") or storm.get("stormNumber")
            storm.get("basin") or storm.get("basinId")

            # Get classification and intensity
            classification = storm.get("classification") or storm.get("intensity")
            max_winds = storm.get("intensityMPH") or storm.get("intensity") or storm.get("maxWinds")
            min_pressure = storm.get("pressureMB") or storm.get("pressure") or storm.get("minPressure")

            # Build movement string
            movement = storm.get("movement") or storm.get("motion")
            if not movement:
                move_dir = storm.get("movementDir")
                move_speed = storm.get("movementSpeed")
                if move_dir is not None and move_speed is not None:
                    movement = f"{move_dir}° at {move_speed} mph"

            # Get current position (use numeric fields first)
            current_position = None
            lat = storm.get("latitudeNumeric") or storm.get("lat") or storm.get("latitude")
            lon = storm.get("longitudeNumeric") or storm.get("lon") or storm.get("longitude")

            # Handle string coordinates like "35.1N"
            if isinstance(lat, str):
                try:
                    lat_val = float(lat.replace("N", "").replace("S", ""))
                    if "S" in lat:
                        lat_val = -lat_val
                    lat = lat_val
                except (ValueError, TypeError):
                    lat = None

            if isinstance(lon, str):
                try:
                    lon_val = float(lon.replace("W", "").replace("E", ""))
                    if "W" in lon:
                        lon_val = -lon_val
                    lon = lon_val
                except (ValueError, TypeError):
                    lon = None

            if lat is not None and lon is not None:
                with contextlib.suppress(ValueError, TypeError):
                    current_position = (float(lat), float(lon))

            # Convert storm type
            storm_type = "Unknown"
            if classification:
                class_upper = classification.upper()
                if class_upper in ["HU", "HURRICANE"]:
                    storm_type = "Hurricane"
                elif class_upper in ["TS", "TROPICAL STORM"]:
                    storm_type = "Tropical Storm"
                elif class_upper in ["TD", "TROPICAL DEPRESSION"]:
                    storm_type = "Tropical Depression"
                elif class_upper in ["PTC", "POTENTIAL TROPICAL CYCLONE"]:
                    storm_type = "Potential Tropical Cyclone"
                else:
                    storm_type = classification

            # Try to get actual forecast cone geometry from GIS data
            geometry = self._get_storm_cone_geometry(storm)

            # If no cone available, create a buffer around current position
            if not geometry:
                from shapely.geometry import Point
                if current_position:
                    point = Point(current_position[1], current_position[0])  # lon, lat
                    geometry = point.buffer(2.0)  # 2 degree buffer for hurricanes
                else:
                    geometry = Point(0, 0).buffer(0.1)

            return NHCCone(
                geometry=geometry,
                storm_id=storm_id,
                advisory_num=storm.get("lastUpdate") or storm.get("advisory"),
                storm_name=storm_name,
                storm_type=storm_type,
                current_position=current_position,
                max_winds=max_winds,
                min_pressure=min_pressure,
                movement=movement,
            )

        except Exception as e:
            logger.error(f"Failed to parse storm data: {e}")
            return None

    def _get_storm_track_positions(self, storm: dict) -> list[tuple[float, float]]:
        """Get track positions from storm GeoJSON data.

        Args:
            storm: Storm data dictionary

        Returns:
            List of (lat, lon) positions
        """
        positions = []

        try:
            # Look for track GeoJSON URLs
            products = storm.get("products") or storm.get("productUrls") or {}
            track_urls = []

            # Find GeoJSON track URLs
            for key, value in products.items():
                if isinstance(value, str) and value.lower().endswith(".geojson"):
                    if "track" in key.lower() or "forecast" in key.lower():
                        track_urls.append(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and item.lower().endswith(".geojson"):
                            track_urls.append(item)

            # Fetch and parse track data
            for url in track_urls:
                try:
                    geojson_data = self._make_request(url)
                    features = geojson_data.get("features", [])

                    for feature in features:
                        geom = feature.get("geometry", {})
                        if geom.get("type") == "Point":
                            coords = geom.get("coordinates", [])
                            if len(coords) >= 2:
                                lon, lat = coords[0], coords[1]
                                positions.append((float(lat), float(lon)))

                except Exception as e:
                    logger.debug(f"Failed to fetch track from {url}: {e}")
                    continue

        except Exception as e:
            logger.debug(f"Failed to get track positions: {e}")

        return positions

    def _get_storm_cone_geometry(self, storm: dict) -> Optional:
        """Get forecast cone geometry from storm GIS data.

        Args:
            storm: Storm data from CurrentStorms.json

        Returns:
            Cone geometry or None
        """
        try:
            # Look for cone GIS data
            track_cone = storm.get("trackCone")
            if not track_cone:
                return None

            # Try to get cone from zip file (contains GeoJSON)
            zip_url = track_cone.get("zipFile")
            if zip_url:
                # For now, return None and use position buffer
                # TODO: Could extract GeoJSON from zip file
                return None

        except Exception as e:
            logger.debug(f"Failed to get cone geometry: {e}")

        return None


def get_current_storms_with_positions() -> list[NHCCone]:
    """Get current storms with precise positions from NHC CurrentStorms.json.

    Returns:
        List of current storms with accurate positions
    """
    client = CurrentStormsClient()
    return client.fetch_current_storms()
