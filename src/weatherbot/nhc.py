# src/weatherbot/nhc.py
"""NHC forecast cone polygon fetching and parsing."""

import contextlib
import hashlib
import logging

import requests
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .cache import api_cache

logger = logging.getLogger(__name__)

# NHC MapServer base URL
NHC_MAPSERVER_BASE = (
    "https://mapservices.weather.noaa.gov/tropical/rest/services/"
    "tropical/NHC_tropical_weather/MapServer"
)

# Request timeout in seconds
REQUEST_TIMEOUT = 30


class NHCCone:
    """Represents an NHC forecast cone."""

    def __init__(
        self,
        geometry: BaseGeometry,
        storm_id: str | None = None,
        advisory_num: str | None = None,
        storm_name: str | None = None,
        storm_type: str | None = None,
        current_position: tuple[float, float] | None = None,
        max_winds: int | None = None,
        min_pressure: int | None = None,
        movement: str | None = None,
    ) -> None:
        """Initialize NHC cone.

        Args:
            geometry: Cone polygon geometry
            storm_id: Storm identifier (e.g., 'AL012023')
            advisory_num: Advisory number
            storm_name: Storm name
            storm_type: Storm type (Hurricane, Tropical Storm, etc.)
            current_position: Current storm center (lat, lon)
            max_winds: Maximum sustained winds (mph)
            min_pressure: Minimum central pressure (mb)
            movement: Storm movement description
        """
        self.geometry = geometry
        self.storm_id = storm_id
        self.advisory_num = advisory_num
        self.storm_name = storm_name
        self.storm_type = storm_type or "Unknown"
        self.current_position = current_position
        self.max_winds = max_winds
        self.min_pressure = min_pressure
        self.movement = movement

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"NHCCone(storm_id='{self.storm_id}', "
            f"advisory_num='{self.advisory_num}', "
            f"storm_name='{self.storm_name}', "
            f"storm_type='{self.storm_type}')"
        )

    def get_storm_info_html(self) -> str:
        """Get HTML formatted storm information.

        Returns:
            HTML formatted storm details
        """
        info_parts = [f"<b>🌀 {self.storm_name or 'Unknown Storm'}</b>"]

        if self.storm_type:
            info_parts.append(f"<b>Type:</b> {self.storm_type}")

        if self.advisory_num:
            info_parts.append(f"<b>Advisory:</b> {self.advisory_num}")

        if self.max_winds:
            info_parts.append(f"<b>Max Winds:</b> {self.max_winds} mph")

        if self.min_pressure:
            info_parts.append(f"<b>Pressure:</b> {self.min_pressure} mb")

        if self.movement:
            info_parts.append(f"<b>Movement:</b> {self.movement}")

        if self.current_position:
            lat, lon = self.current_position
            info_parts.append(f"<b>Position:</b> {lat:.1f}°N, {abs(lon):.1f}°W")

        return "<br>".join(info_parts)


class NHCClient:
    """Client for fetching NHC forecast cone data."""

    def __init__(self, timeout: int = REQUEST_TIMEOUT) -> None:
        """Initialize NHC client.

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
    def _make_request(self, url: str, params: dict | None = None) -> dict:
        """Make HTTP request with retry logic and caching.

        Args:
            url: Request URL
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            requests.RequestException: On HTTP errors
        """
        # Create cache key from URL and params
        cache_key = hashlib.md5(f"{url}_{params}".encode(), usedforsecurity=False).hexdigest()

        # Try cache first
        cached_data = api_cache.get(cache_key)
        if cached_data is not None:
            logger.debug(f"Using cached data for: {url}")
            return cached_data

        # Make request
        logger.debug(f"Making request to: {url}")
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()

        # Cache the response
        api_cache.set(cache_key, data)

        return data

    def discover_cone_layer(self) -> int | None:
        """Discover the forecast cone layer ID.

        Returns:
            Layer ID if found, None otherwise
        """
        try:
            url = f"{NHC_MAPSERVER_BASE}?f=json"
            data = self._make_request(url)

            if "layers" not in data:
                logger.warning("No layers found in MapServer response")
                return None

            # Look for layer with "Forecast Cone" in the name
            for layer in data["layers"]:
                layer_name = layer.get("name", "").lower()
                if "forecast cone" in layer_name or "cone" in layer_name:
                    layer_id = layer.get("id")
                    logger.info(f"Found cone layer: {layer['name']} (ID: {layer_id})")
                    return layer_id

            logger.warning("No forecast cone layer found")
            return None

        except Exception as e:
            logger.error(f"Failed to discover cone layer: {e}")
            return None

    def fetch_active_cones(self) -> list[NHCCone]:
        """Fetch active Atlantic forecast cones and disturbances.

        Returns:
            List of active forecast cones including disturbances
        """
        all_cones = []

        # Get all layer information to find active systems
        layers = self.get_layers_info()

        # Look for all forecast cone layers (Atlantic and disturbances)
        cone_layer_ids = []
        for layer in layers:
            layer_name = layer.get("name", "").lower()
            if "forecast cone" in layer_name and layer.get("id") is not None:
                cone_layer_ids.append(layer.get("id"))
                logger.debug(f"Found cone layer: {layer['name']} (ID: {layer['id']})")

        # Also add development region layers for disturbances
        development_layer_ids = []
        for layer in layers:
            layer_name = layer.get("name", "").lower()
            if ("potential development" in layer_name or
                "development region" in layer_name) and layer.get("id") is not None:
                development_layer_ids.append(layer.get("id"))
                logger.debug(f"Found development layer: {layer['name']} (ID: {layer['id']})")

        # Fetch forecast cones and try to get current positions
        for layer_id in cone_layer_ids:
            try:
                url = f"{NHC_MAPSERVER_BASE}/{layer_id}/query"
                params = {
                    "where": "1=1",  # Get all features
                    "outFields": "*",
                    "f": "geojson",
                    "outSR": "4326",  # WGS84
                }

                data = self._make_request(url, params)

                if "features" not in data or not data["features"]:
                    continue

                for feature in data["features"]:
                    try:
                        cone = self._parse_cone_feature(feature)
                        if cone:
                            # Get current position from forecast points layer
                            cone.current_position = self._get_storm_current_position(layer_id)

                            # Also try to get additional storm details
                            cone = self._enhance_storm_details(cone, layer_id)

                            all_cones.append(cone)
                            logger.debug(f"Added cone for layer {layer_id}: {cone}")
                    except Exception as e:
                        logger.warning(f"Failed to parse cone feature: {e}")
                        continue

            except Exception as e:
                logger.debug(f"No data for cone layer {layer_id}: {e}")
                continue

        # Fetch development regions (disturbances)
        for layer_id in development_layer_ids:
            try:
                url = f"{NHC_MAPSERVER_BASE}/{layer_id}/query"
                params = {
                    "where": "1=1",
                    "outFields": "*",
                    "f": "geojson",
                    "outSR": "4326",
                }

                data = self._make_request(url, params)

                if "features" not in data or not data["features"]:
                    continue

                for feature in data["features"]:
                    try:
                        # Parse development region as a cone
                        cone = self._parse_development_feature(feature)
                        if cone:
                            # Try to get position from geometry centroid as fallback
                            if not cone.current_position and hasattr(cone, 'geometry'):
                                try:
                                    centroid = cone.geometry.centroid
                                    cone.current_position = (centroid.y, centroid.x)
                                    logger.debug(f"Using geometry centroid for disturbance: {cone.current_position}")
                                except Exception as e:
                                    logger.debug(f"Failed to get centroid: {e}")

                            all_cones.append(cone)
                            logger.debug(f"Added development region for layer {layer_id}: {cone}")
                    except Exception as e:
                        logger.warning(f"Failed to parse development feature: {e}")
                        continue

            except Exception as e:
                logger.debug(f"No data for development layer {layer_id}: {e}")
                continue

        # Try to get disturbance positions from current location layers
        all_cones = self._add_disturbance_positions(all_cones)

        # Enhance with AI if available
        try:
            from .ai_enhancer import enhance_storm_positions_with_ai
            from .config import load_config

            config = load_config()
            if config.openai_api_key:
                all_cones = enhance_storm_positions_with_ai(all_cones, config.openai_api_key)
            else:
                logger.info("No OpenAI API key configured, using geometric positioning")
        except Exception as e:
            logger.debug(f"AI enhancement not available: {e}")

        logger.info(f"Fetched {len(all_cones)} active forecast cones and disturbances")
        return all_cones

    def _add_disturbance_positions(self, cones: list[NHCCone]) -> list[NHCCone]:
        """Try to add positions to disturbances that don't have them.

        Args:
            cones: List of existing cones

        Returns:
            Enhanced cones with positions
        """
        # Try to get current disturbance locations from "Current Location" layers
        current_location_layers = [1, 2]  # Two-Day and Seven-Day Current Location

        for layer_id in current_location_layers:
            try:
                url = f"{NHC_MAPSERVER_BASE}/{layer_id}/query"
                params = {
                    "where": "1=1",
                    "outFields": "*",
                    "f": "geojson",
                    "outSR": "4326",
                }

                data = self._make_request(url, params)

                if "features" not in data or not data["features"]:
                    continue

                for feature in data["features"]:
                    try:
                        # Check if this is a disturbance position
                        feature.get("properties", {})
                        geometry = feature.get("geometry")

                        if geometry and geometry.get("type") == "Point":
                            coords = geometry.get("coordinates")
                            if coords and len(coords) >= 2:
                                lon, lat = coords[0], coords[1]
                                position = (float(lat), float(lon))

                                # Try to match this position to a disturbance without position
                                for cone in cones:
                                    if (not cone.current_position and
                                        "disturbance" in cone.storm_name.lower()):
                                        # Check if this position is near the cone
                                        if self._position_near_geometry(position, cone.geometry):
                                            cone.current_position = position
                                            logger.debug(f"Matched disturbance position: {position} to {cone.storm_name}")
                                            break

                    except Exception as e:
                        logger.debug(f"Failed to process current location feature: {e}")
                        continue

            except Exception as e:
                logger.debug(f"Failed to get current locations from layer {layer_id}: {e}")
                continue

        return cones

    def _position_near_geometry(self, position: tuple[float, float], geometry: BaseGeometry) -> bool:
        """Check if a position is near a geometry (within or close to it).

        Args:
            position: Position tuple (lat, lon)
            geometry: Geometry to check against

        Returns:
            True if position is near the geometry
        """
        try:
            from shapely.geometry import Point
            point = Point(position[1], position[0])  # lon, lat for Shapely

            # Check if point is within geometry or within a reasonable buffer
            return geometry.contains(point) or geometry.buffer(2.0).contains(point)
        except Exception:
            return False

    def _parse_cone_feature(self, feature: dict) -> NHCCone | None:
        """Parse a GeoJSON feature into an NHC cone.

        Args:
            feature: GeoJSON feature

        Returns:
            NHC cone or None if parsing fails
        """
        try:
            # Parse geometry
            geometry_data = feature.get("geometry")
            if not geometry_data:
                logger.warning("Feature has no geometry")
                return None

            geometry = shape(geometry_data)

            # Handle MultiPolygon by taking the first polygon
            if isinstance(geometry, MultiPolygon):
                if len(geometry.geoms) > 0:
                    geometry = geometry.geoms[0]
                else:
                    logger.warning("Empty MultiPolygon")
                    return None

            if not isinstance(geometry, Polygon):
                logger.warning(f"Unexpected geometry type: {type(geometry)}")
                return None

            # Extract properties
            props = feature.get("properties", {})
            storm_id = props.get("STORMID") or props.get("stormid")
            advisory_num = props.get("ADVISNUM") or props.get("advisnum")
            storm_name = props.get("STORMNAME") or props.get("stormname")
            storm_type = props.get("STORMTYPE") or props.get("stormtype")

            # Extract storm details
            max_winds = props.get("MAXWIND") or props.get("maxwind")
            min_pressure = props.get("MSLP") or props.get("mslp")
            movement = props.get("MOVEMENT") or props.get("movement")

            # Extract current position from multiple possible field names
            current_lat = (props.get("LAT") or props.get("lat") or
                          props.get("CLAT") or props.get("clat") or
                          props.get("LATITUDE") or props.get("latitude"))
            current_lon = (props.get("LON") or props.get("lon") or
                          props.get("CLON") or props.get("clon") or
                          props.get("LONGITUDE") or props.get("longitude"))

            current_position = None
            if current_lat is not None and current_lon is not None:
                try:
                    lat_val = float(current_lat)
                    lon_val = float(current_lon)
                    # Ensure longitude is negative for Atlantic (west of prime meridian)
                    if lon_val > 0:
                        lon_val = -lon_val
                    current_position = (lat_val, lon_val)
                    logger.debug(f"Found storm position in cone data: {current_position}")
                except (ValueError, TypeError):
                    pass

            # Convert to appropriate types
            if storm_id is not None:
                storm_id = str(storm_id)
            if advisory_num is not None:
                advisory_num = str(advisory_num)
            if storm_name is not None:
                storm_name = str(storm_name)
            if storm_type is not None:
                storm_type = str(storm_type)
            if max_winds is not None:
                try:
                    max_winds = int(float(max_winds))
                except (ValueError, TypeError):
                    max_winds = None
            if min_pressure is not None:
                try:
                    min_pressure = int(float(min_pressure))
                except (ValueError, TypeError):
                    min_pressure = None

            return NHCCone(
                geometry=geometry,
                storm_id=storm_id,
                advisory_num=advisory_num,
                storm_name=storm_name,
                storm_type=storm_type,
                current_position=current_position,
                max_winds=max_winds,
                min_pressure=min_pressure,
                movement=movement,
            )

        except Exception as e:
            logger.error(f"Failed to parse cone feature: {e}")
            return None

    def _parse_development_feature(self, feature: dict) -> NHCCone | None:
        """Parse a development region feature into an NHC cone.

        Args:
            feature: GeoJSON feature for development region

        Returns:
            NHC cone representing the development area
        """
        try:
            # Parse geometry
            geometry_data = feature.get("geometry")
            if not geometry_data:
                logger.warning("Development feature has no geometry")
                return None

            geometry = shape(geometry_data)

            # Handle MultiPolygon by taking the first polygon
            if isinstance(geometry, MultiPolygon):
                if len(geometry.geoms) > 0:
                    geometry = geometry.geoms[0]
                else:
                    logger.warning("Empty development MultiPolygon")
                    return None

            if not isinstance(geometry, Polygon):
                logger.warning(f"Unexpected development geometry type: {type(geometry)}")
                return None

            # Extract properties for development areas
            props = feature.get("properties", {})

            # Development areas might have different property names
            storm_id = (props.get("STORMID") or props.get("stormid") or
                       props.get("BASIN") or props.get("ID") or "DEVELOPMENT")

            # Use probability or development chance as advisory
            advisory_num = (props.get("PROB") or props.get("prob") or
                          props.get("CHANCE") or props.get("chance") or
                          props.get("DEVELOPMENT_CHANCE") or "DEV")

            storm_name = (props.get("STORMNAME") or props.get("stormname") or
                         props.get("NAME") or props.get("DESCRIPTION") or
                         "Tropical Disturbance")

            # Try to extract position from development area properties
            current_position = None
            center_lat = (props.get("CENTER_LAT") or props.get("center_lat") or
                         props.get("LAT") or props.get("lat"))
            center_lon = (props.get("CENTER_LON") or props.get("center_lon") or
                         props.get("LON") or props.get("lon"))

            if center_lat is not None and center_lon is not None:
                try:
                    lat_val = float(center_lat)
                    lon_val = float(center_lon)
                    if lon_val > 0:  # Ensure western longitude
                        lon_val = -lon_val
                    current_position = (lat_val, lon_val)
                    logger.debug(f"Found development position: {current_position}")
                except (ValueError, TypeError):
                    pass

            # Convert to strings if present
            if storm_id is not None:
                storm_id = str(storm_id)
            if advisory_num is not None:
                advisory_num = str(advisory_num)
            if storm_name is not None:
                storm_name = str(storm_name)

            return NHCCone(
                geometry=geometry,
                storm_id=storm_id,
                advisory_num=advisory_num,
                storm_name=storm_name,
                storm_type="Tropical Disturbance",
                current_position=current_position,
            )

        except Exception as e:
            logger.error(f"Failed to parse development feature: {e}")
            return None

    def _get_storm_current_position(self, cone_layer_id: int) -> tuple[float, float] | None:
        """Get current storm position from forecast points layer.

        Args:
            cone_layer_id: Cone layer ID

        Returns:
            Current position (lat, lon) or None
        """
        # Try multiple approaches to get storm position
        position_attempts = [
            (cone_layer_id - 2, "Forecast Points"),  # Standard offset
            (cone_layer_id - 1, "Alternative Points"),  # Alternative offset
            (cone_layer_id + 1, "Track Points"),  # Track layer
        ]

        for points_layer_id, layer_type in position_attempts:
            try:
                url = f"{NHC_MAPSERVER_BASE}/{points_layer_id}/query"
                params = {
                    "where": "1=1",
                    "outFields": "*",
                    "f": "geojson",
                    "outSR": "4326",
                }

                data = self._make_request(url, params)

                if "features" not in data or not data["features"]:
                    continue

                # Look for current position (TAU=0 or most recent)
                best_feature = None
                min_tau = float('inf')

                for feature in data["features"]:
                    props = feature.get("properties", {})

                    # Check multiple TAU field names
                    tau = (props.get("TAU") or props.get("tau") or
                          props.get("FHOUR") or props.get("fhour") or
                          props.get("HOUR") or props.get("hour") or 0)

                    try:
                        tau_val = float(tau)
                        if tau_val < min_tau:
                            min_tau = tau_val
                            best_feature = feature
                    except (ValueError, TypeError):
                        if best_feature is None:
                            best_feature = feature

                if best_feature:
                    # Try to get position from geometry
                    geometry = best_feature.get("geometry")
                    if geometry and geometry.get("type") == "Point":
                        coords = geometry.get("coordinates")
                        if coords and len(coords) >= 2:
                            lon, lat = coords[0], coords[1]
                            position = (float(lat), float(lon))
                            logger.debug(f"Found storm position from {layer_type} (layer {points_layer_id}): {position}")
                            return position

                    # Try to get position from properties
                    props = best_feature.get("properties", {})
                    lat = (props.get("LAT") or props.get("lat") or
                          props.get("CLAT") or props.get("clat"))
                    lon = (props.get("LON") or props.get("lon") or
                          props.get("CLON") or props.get("clon"))

                    if lat is not None and lon is not None:
                        try:
                            lat_val = float(lat)
                            lon_val = float(lon)
                            if lon_val > 0:  # Ensure western longitude
                                lon_val = -lon_val
                            position = (lat_val, lon_val)
                            logger.debug(f"Found storm position from {layer_type} properties: {position}")
                            return position
                        except (ValueError, TypeError):
                            pass

            except Exception as e:
                logger.debug(f"Failed to get position from {layer_type} (layer {points_layer_id}): {e}")
                continue

        return None

    def _enhance_storm_details(self, cone: NHCCone, cone_layer_id: int) -> NHCCone:
        """Enhance storm details with additional data from related layers.

        Args:
            cone: Existing cone object
            cone_layer_id: Cone layer ID

        Returns:
            Enhanced cone object
        """
        try:
            # Try to get more details from forecast points layer
            points_layer_id = cone_layer_id - 2

            url = f"{NHC_MAPSERVER_BASE}/{points_layer_id}/query"
            params = {
                "where": "1=1",
                "outFields": "*",
                "f": "json",  # Use JSON for better property access
                "outSR": "4326",
            }

            data = self._make_request(url, params)

            if data.get("features"):
                # Get the most recent forecast point (current position)
                current_feature = None
                for feature in data["features"]:
                    attrs = feature.get("attributes", {})
                    tau = attrs.get("TAU") or attrs.get("FHOUR") or 0
                    if tau == 0:
                        current_feature = feature
                        break

                if not current_feature and data["features"]:
                    current_feature = data["features"][0]

                if current_feature:
                    attrs = current_feature.get("attributes", {})

                    # Update storm details with more complete information
                    if not cone.storm_type or cone.storm_type == "Unknown":
                        cone.storm_type = attrs.get("STORMTYPE") or attrs.get("INTENSITY") or cone.storm_type

                    if not cone.max_winds:
                        winds = attrs.get("MAXWIND") or attrs.get("VMAX")
                        if winds:
                            with contextlib.suppress(ValueError, TypeError):
                                cone.max_winds = int(float(winds))

                    if not cone.min_pressure:
                        pressure = attrs.get("MSLP") or attrs.get("MINCP")
                        if pressure:
                            with contextlib.suppress(ValueError, TypeError):
                                cone.min_pressure = int(float(pressure))

                    if not cone.movement:
                        cone.movement = attrs.get("MOVEMENT") or attrs.get("MOTION")

                    # Get actual current position from geometry
                    if not cone.current_position:
                        geometry = current_feature.get("geometry")
                        if geometry and geometry.get("type") == "Point":
                            coords = geometry.get("coordinates")
                            if coords and len(coords) >= 2:
                                lon, lat = coords[0], coords[1]
                                cone.current_position = (float(lat), float(lon))

        except Exception as e:
            logger.debug(f"Failed to enhance storm details for layer {cone_layer_id}: {e}")

        return cone

    def get_layers_info(self) -> list[dict]:
        """Get information about all available layers.

        Returns:
            List of layer information dictionaries
        """
        try:
            url = f"{NHC_MAPSERVER_BASE}?f=json"
            data = self._make_request(url)

            layers = data.get("layers", [])
            layer_info = []

            for layer in layers:
                info = {
                    "id": layer.get("id"),
                    "name": layer.get("name"),
                    "type": layer.get("type"),
                    "description": layer.get("description", ""),
                }
                layer_info.append(info)

            return layer_info

        except Exception as e:
            logger.error(f"Failed to get layers info: {e}")
            return []


def get_active_cones() -> tuple[list[NHCCone], list[BaseGeometry]]:
    """Get active forecast cones and their geometries.

    Returns:
        Tuple of (cone objects, geometries list)
    """
    # Use hybrid approach: CurrentStorms.json for hurricanes + MapServer for disturbances
    all_cones = []

    # Get hurricanes/tropical storms from CurrentStorms.json (more accurate)
    try:
        from .nhc_current_storms import get_current_storms_with_positions
        current_storms = get_current_storms_with_positions()

        if current_storms:
            logger.info(f"Got {len(current_storms)} named storms from CurrentStorms.json")
            all_cones.extend(current_storms)
    except Exception as e:
        logger.warning(f"CurrentStorms.json failed: {e}")

    # Get disturbances with precise ATCF positions
    try:
        from .atcf_client import get_atcf_invest_positions
        atcf_positions = get_atcf_invest_positions()

        if atcf_positions:
            logger.info(f"Got {len(atcf_positions)} ATCF invest positions")

            # Get disturbance cones from MapServer and enhance with ATCF positions
            client = NHCClient()
            mapserver_cones = client.fetch_active_cones()

            for cone in mapserver_cones:
                is_disturbance = (
                    "disturbance" in (cone.storm_name or "").lower() or
                    "development" in (cone.storm_name or "").lower() or
                    cone.storm_type == "Unknown" or
                    cone.advisory_num == "DEV"
                )

                if is_disturbance:
                    # Try to match with ATCF position
                    best_match = None
                    min_distance = float('inf')

                    for invest_id, position in atcf_positions.items():
                        if cone.current_position:
                            # Calculate distance to existing position
                            cone_lat, cone_lon = cone.current_position
                            atcf_lat, atcf_lon = position
                            distance = ((cone_lat - atcf_lat)**2 + (cone_lon - atcf_lon)**2)**0.5

                            if distance < min_distance and distance < 10.0:  # Within 10 degrees
                                min_distance = distance
                                best_match = (invest_id, position)

                    # Update with ATCF position if found
                    if best_match:
                        invest_id, atcf_position = best_match
                        cone.current_position = atcf_position
                        cone.storm_id = invest_id
                        cone.storm_name = f"Invest {invest_id}"
                        logger.info(f"Enhanced {invest_id} with ATCF position: {atcf_position}")

                    all_cones.append(cone)
        else:
            # Fallback to MapServer only
            client = NHCClient()
            mapserver_cones = client.fetch_active_cones()

            for cone in mapserver_cones:
                is_disturbance = (
                    "disturbance" in (cone.storm_name or "").lower() or
                    "development" in (cone.storm_name or "").lower() or
                    cone.storm_type == "Unknown" or
                    cone.advisory_num == "DEV"
                )

                if is_disturbance:
                    all_cones.append(cone)

    except Exception as e:
        logger.warning(f"ATCF/MapServer disturbance fetch failed: {e}")

    # If we have no data at all, fall back to full MapServer
    if not all_cones:
        logger.warning("No storms found via hybrid approach, using full MapServer fallback")
        client = NHCClient()
        all_cones = client.fetch_active_cones()

    geometries = [cone.geometry for cone in all_cones]
    logger.info(f"Total active systems: {len(all_cones)}")
    return all_cones, geometries
