# src/weatherbot/enhanced_cone_analyzer.py
"""Enhanced cone intersection analyzer with optimized accuracy and performance."""

import logging
from dataclasses import dataclass
from enum import Enum

from shapely.geometry.base import BaseGeometry

from .alert_levels import AlertLevel
from .atcf_client import get_atcf_invest_positions
from .geometry import load_county_polygon, point_in_any, polygon_intersects_any
from .nhc import NHCCone, get_active_cones
from .nhc_current_storms import get_current_storms_with_positions
from .nhc_storm_tracker import get_all_active_storm_cones
from .nws import get_hurricane_alerts

logger = logging.getLogger(__name__)


class StormCategory(Enum):
    """Enhanced storm categorization for precise threat assessment."""

    HURRICANE_MAJOR = "major_hurricane"  # Cat 3-5
    HURRICANE_MINOR = "minor_hurricane"  # Cat 1-2
    TROPICAL_STORM = "tropical_storm"
    TROPICAL_DEPRESSION = "tropical_depression"
    INVEST_DISTURBANCE = "invest_disturbance"
    DEVELOPMENT_AREA = "development_area"
    UNKNOWN = "unknown"


@dataclass
class StormThreat:
    """Comprehensive storm threat assessment."""

    cone: NHCCone
    category: StormCategory
    in_cone: bool
    distance_km: float | None
    threat_level: AlertLevel
    confidence: float  # 0.0 to 1.0
    official_warnings: list[str]
    estimated_arrival_hours: int | None


class EnhancedConeAnalyzer:
    """Enhanced cone intersection analyzer with maximum accuracy."""

    def __init__(self) -> None:
        """Initialize the enhanced analyzer."""
        self.logger = logging.getLogger(__name__)

    def analyze_location_threat(
        self,
        latitude: float,
        longitude: float,
        use_county_intersect: bool = False,
        county_geojson_path: str | None = None,
    ) -> dict[str, AlertLevel | list[StormThreat] | bool]:
        """Perform comprehensive threat analysis for a location.

        Args:
            latitude: Location latitude
            longitude: Location longitude
            use_county_intersect: Use county-level intersection
            county_geojson_path: Path to county GeoJSON file

        Returns:
            Comprehensive threat analysis results
        """
        self.logger.info(f"Analyzing threat for location: {latitude:.4f}, {longitude:.4f}")

        # Get all active storm data with enhanced accuracy
        cones, geometries = self._get_enhanced_storm_data()

        # Filter storms by distance to location (2000km radius for relevance)
        if cones:
            cones = self._filter_storms_by_distance(cones, (latitude, longitude), 2000.0)
            geometries = [cone.geometry for cone in cones if cone.geometry]

        # Get official NWS alerts
        nws_alerts = self._get_nws_alerts(latitude, longitude)

        # Analyze each storm threat
        storm_threats = []
        highest_threat = AlertLevel.ALL_CLEAR
        is_in_any_cone = False

        for cone, geometry in zip(cones, geometries, strict=False):
            threat = self._analyze_storm_threat(
                cone, geometry, latitude, longitude,
                use_county_intersect, county_geojson_path, nws_alerts
            )

            if threat.in_cone:
                is_in_any_cone = True
                storm_threats.append(threat)

                # Update highest threat level
                if threat.threat_level.value > highest_threat.value:
                    highest_threat = threat.threat_level

        # Apply NWS alert overrides
        if nws_alerts:
            highest_threat = self._apply_nws_overrides(highest_threat, nws_alerts)

        self.logger.info(f"Analysis complete: {len(storm_threats)} threatening storms, "
                        f"highest threat: {highest_threat.name}")

        return {
            "alert_level": highest_threat,
            "storm_threats": storm_threats,
            "is_in_any_cone": is_in_any_cone,
            "nws_alerts": nws_alerts,
            "total_storms_analyzed": len(cones),
        }

    def _get_enhanced_storm_data(self) -> tuple[list[NHCCone], list[BaseGeometry]]:
        """Get enhanced storm data from multiple sources with fallbacks.

        Returns:
            Tuple of (enhanced cones, geometries)
        """
        enhanced_cones = []

        # Priority 1: Individual storm tracking pages (most complete cone data)
        try:
            individual_storm_cones = get_all_active_storm_cones()
            if individual_storm_cones:
                enhanced_cones.extend(individual_storm_cones)
                self.logger.info(f"Retrieved {len(individual_storm_cones)} cones from individual storm pages")
        except Exception as e:
            self.logger.warning(f"Individual storm tracking failed: {e}")

        # Priority 2: Named storms from CurrentStorms.json (metadata enhancement)
        try:
            current_storms = get_current_storms_with_positions()
            if current_storms:
                # Merge with individual storm data to avoid duplicates
                existing_ids = {cone.storm_id for cone in enhanced_cones if cone.storm_id}
                for storm in current_storms:
                    if storm.storm_id not in existing_ids:
                        enhanced_cones.append(storm)
                self.logger.info(f"Added {len(current_storms)} named storms from CurrentStorms.json")
        except Exception as e:
            self.logger.warning(f"CurrentStorms.json failed: {e}")

        # Priority 2: ATCF invest positions for disturbances
        try:
            atcf_positions = get_atcf_invest_positions()
            if atcf_positions:
                self.logger.info(f"Retrieved {len(atcf_positions)} ATCF invest positions")
                # Enhance existing cones with ATCF data
                enhanced_cones = self._enhance_with_atcf_data(enhanced_cones, atcf_positions)
        except Exception as e:
            self.logger.warning(f"ATCF enhancement failed: {e}")

        # Priority 3: MapServer fallback for any missing data
        try:
            all_cones, _all_geometries = get_active_cones()

            # Add any cones not already captured
            existing_ids = {cone.storm_id for cone in enhanced_cones if cone.storm_id}
            for cone in all_cones:
                if cone.storm_id not in existing_ids:
                    enhanced_cones.append(cone)

            self.logger.info(f"Total enhanced cones: {len(enhanced_cones)}")

        except Exception as e:
            self.logger.error(f"MapServer fallback failed: {e}")
            # Use whatever we have

        # Extract geometries
        geometries = [cone.geometry for cone in enhanced_cones]

        return enhanced_cones, geometries

    def _enhance_with_atcf_data(
        self,
        cones: list[NHCCone],
        atcf_positions: dict[str, tuple[float, float]]
    ) -> list[NHCCone]:
        """Enhance cone data with precise ATCF positions.

        Args:
            cones: Existing cone data
            atcf_positions: ATCF position data

        Returns:
            Enhanced cone list
        """
        enhanced = cones.copy()

        for invest_id, position in atcf_positions.items():
            # Check if we already have this invest
            found = False
            for cone in enhanced:
                if (cone.storm_id == invest_id or
                    (cone.storm_name and invest_id.lower() in cone.storm_name.lower())):
                    # Update with precise ATCF position
                    cone.current_position = position
                    found = True
                    break

            if not found:
                # Create new cone for ATCF invest
                from shapely.geometry import Point
                point_geom = Point(position[1], position[0]).buffer(2.0)  # 2-degree buffer

                new_cone = NHCCone(
                    geometry=point_geom,
                    storm_id=invest_id,
                    storm_name=f"Invest {invest_id}",
                    storm_type="Tropical Disturbance",
                    current_position=position,
                    advisory_num="ATCF"
                )
                enhanced.append(new_cone)
                self.logger.info(f"Added ATCF invest {invest_id} at {position}")

        return enhanced

    def _analyze_storm_threat(
        self,
        cone: NHCCone,
        geometry: BaseGeometry,
        latitude: float,
        longitude: float,
        use_county_intersect: bool,
        county_geojson_path: str | None,
        nws_alerts: list[dict],
    ) -> StormThreat:
        """Analyze threat from a specific storm.

        Args:
            cone: Storm cone data
            geometry: Cone geometry
            latitude: Target latitude
            longitude: Target longitude
            use_county_intersect: Use county intersection
            county_geojson_path: County GeoJSON path
            nws_alerts: NWS alerts

        Returns:
            Storm threat assessment
        """
        # Check intersection with high precision
        in_cone = self._check_precise_intersection(
            geometry, latitude, longitude, use_county_intersect, county_geojson_path, cone
        )

        # Categorize storm
        category = self._categorize_storm(cone)

        # Calculate distance
        distance_km = self._calculate_distance(cone, latitude, longitude)

        # Determine threat level
        threat_level = self._determine_threat_level(cone, category, in_cone, nws_alerts)

        # Calculate confidence
        confidence = self._calculate_confidence(cone, category, in_cone)

        # Get relevant warnings
        warnings = self._get_relevant_warnings(cone, nws_alerts)

        # Estimate arrival time
        arrival_hours = self._estimate_arrival_time(cone, latitude, longitude)

        return StormThreat(
            cone=cone,
            category=category,
            in_cone=in_cone,
            distance_km=distance_km,
            threat_level=threat_level,
            confidence=confidence,
            official_warnings=warnings,
            estimated_arrival_hours=arrival_hours,
        )

    def _check_precise_intersection(
        self,
        geometry: BaseGeometry,
        latitude: float,
        longitude: float,
        use_county_intersect: bool,
        county_geojson_path: str | None,
        cone: NHCCone | None = None,
    ) -> bool:
        """Check intersection with maximum precision.

        Args:
            geometry: Cone geometry
            latitude: Target latitude
            longitude: Target longitude
            use_county_intersect: Use county intersection
            county_geojson_path: County GeoJSON path
            cone: Optional cone data for smarter filtering

        Returns:
            True if location intersects cone
        """
        try:
            # Smart filtering: Only filter out large areas for unnamed disturbances
            # Named storms and PTCs should always be checked regardless of size
            if hasattr(geometry, 'area') and geometry.area > 50.0:
                # Check if this is a named storm or PTC
                is_named_storm = False
                if cone:
                    storm_name = (cone.storm_name or "").lower()
                    storm_type = (cone.storm_type or "").lower()
                    storm_id = (cone.storm_id or "").lower()

                    # Allow named storms, PTCs, and numbered systems (AL09, etc.)
                    is_named_storm = (
                        "named storm" in storm_type or
                        "hurricane" in storm_type or
                        "tropical storm" in storm_type or
                        "potential tropical cyclone" in storm_type or
                        "cyclone" in storm_name or
                        bool(storm_name and storm_name not in ["unknown", "invest"]) or
                        (storm_id and any(char.isdigit() for char in storm_id) and "al" in storm_id)
                    )

                if not is_named_storm:
                    self.logger.debug(f"Skipping large development area (area: {geometry.area:.2f} sq deg)")
                    return False
                self.logger.debug(f"Allowing large named storm cone (area: {geometry.area:.2f} sq deg)")


            if use_county_intersect and county_geojson_path:
                from pathlib import Path
                county_path = Path(county_geojson_path) if isinstance(county_geojson_path, str) else county_geojson_path
                county_polygon = load_county_polygon(county_path)
                return polygon_intersects_any([geometry], county_polygon)
            # High-precision point check
            point = (longitude, latitude)  # Note: lon, lat order for Shapely
            return point_in_any([geometry], point)
        except Exception as e:
            self.logger.debug(f"Intersection check failed: {e}")
            # Fallback to simple point check
            point = (longitude, latitude)
            return point_in_any([geometry], point)

    def _filter_storms_by_distance(self, cones: list[NHCCone], location: tuple[float, float], max_distance_km: float) -> list[NHCCone]:
        """Filter storms by distance from location.

        Args:
            cones: List of storm cones
            location: (latitude, longitude) of reference location
            max_distance_km: Maximum distance in kilometers

        Returns:
            Filtered list of relevant storms
        """
        from math import asin, cos, radians, sin, sqrt

        def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            """Calculate the great circle distance between two points in km."""
            # Convert decimal degrees to radians
            lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

            # Haversine formula
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            r = 6371  # Radius of earth in kilometers
            return c * r

        target_lat, target_lon = location
        relevant_storms = []

        for cone in cones:
            if cone.current_position is not None and len(cone.current_position) == 2:
                storm_lat, storm_lon = cone.current_position
                distance = haversine_distance(target_lat, target_lon, storm_lat, storm_lon)

                # Always include storms that are close or have cones that might affect the location
                if distance <= max_distance_km:
                    relevant_storms.append(cone)
                    self.logger.debug(f"Including {cone.storm_name or cone.storm_id}: {distance:.0f}km away")
                else:
                    self.logger.debug(f"Excluding {cone.storm_name or cone.storm_id}: {distance:.0f}km away (too far)")
            # Include storms without position data (better safe than sorry)
            # Also try to estimate position from geometry centroid if available
            elif hasattr(cone, 'geometry') and cone.geometry is not None:
                try:
                    centroid = cone.geometry.centroid
                    storm_lat, storm_lon = centroid.y, centroid.x
                    distance = haversine_distance(target_lat, target_lon, storm_lat, storm_lon)

                    if distance <= max_distance_km:
                        relevant_storms.append(cone)
                        self.logger.debug(f"Including {cone.storm_name or cone.storm_id}: {distance:.0f}km away (from centroid)")
                    else:
                        self.logger.debug(f"Excluding {cone.storm_name or cone.storm_id}: {distance:.0f}km away (from centroid)")
                except Exception:
                    # If centroid calculation fails, include the storm anyway
                    relevant_storms.append(cone)
                    self.logger.debug(f"Including {cone.storm_name or cone.storm_id}: no position data, centroid failed")
            else:
                relevant_storms.append(cone)
                self.logger.debug(f"Including {cone.storm_name or cone.storm_id}: no position or geometry data")

        return relevant_storms

    def _categorize_storm(self, cone: NHCCone) -> StormCategory:
        """Categorize storm with enhanced precision.

        Args:
            cone: Storm cone data

        Returns:
            Storm category
        """
        storm_type = (cone.storm_type or "").lower()
        storm_name = (cone.storm_name or "").lower()
        max_winds = cone.max_winds or 0

        # Convert max_winds to integer if it's a string
        if isinstance(max_winds, str):
            try:
                max_winds = int(max_winds)
            except (ValueError, TypeError):
                max_winds = 0

        # Hurricane categorization
        if "hurricane" in storm_type or max_winds >= 74:
            if max_winds >= 111:  # Category 3+
                return StormCategory.HURRICANE_MAJOR
            return StormCategory.HURRICANE_MINOR

        # Tropical Storm
        if "tropical storm" in storm_type or "storm" in storm_type or (39 <= max_winds < 74):
            return StormCategory.TROPICAL_STORM

        # Tropical Depression
        if "depression" in storm_type or (0 < max_winds < 39):
            return StormCategory.TROPICAL_DEPRESSION

        # Invest/Disturbance
        if ("invest" in storm_name or "disturbance" in storm_type or
            "development" in storm_type or (cone.storm_id and "9" in cone.storm_id)):
            return StormCategory.INVEST_DISTURBANCE

        # Development area
        if "development" in storm_name or "area" in storm_name:
            return StormCategory.DEVELOPMENT_AREA

        return StormCategory.UNKNOWN

    def _determine_threat_level(
        self,
        cone: NHCCone,
        category: StormCategory,
        in_cone: bool,
        nws_alerts: list[dict],
    ) -> AlertLevel:
        """Determine precise threat level.

        Args:
            cone: Storm cone data
            category: Storm category
            in_cone: Whether location is in cone
            nws_alerts: NWS alerts

        Returns:
            Alert level
        """
        if not in_cone:
            return AlertLevel.ALL_CLEAR

        # Check for official warnings first
        for alert in nws_alerts:
            # Handle both NWSAlert objects and dict objects
            if hasattr(alert, 'event'):
                # NWSAlert object
                event = alert.event.lower()
            else:
                # Dict object
                event = alert.get("event", "").lower()

            if "hurricane warning" in event:
                return AlertLevel.HURRICANE_WARNING
            if "hurricane watch" in event or "tropical storm warning" in event:
                return AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION
            if "tropical storm watch" in event:
                return AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT

        # Determine based on storm category
        if category == StormCategory.HURRICANE_MAJOR:
            return AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION  # Level 4
        if category == StormCategory.HURRICANE_MINOR:
            return AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT  # Level 3
        if category == StormCategory.TROPICAL_STORM or category in [StormCategory.TROPICAL_DEPRESSION, StormCategory.INVEST_DISTURBANCE]:
            return AlertLevel.TROPICAL_STORM_THREAT  # Level 2
        # Development areas and unknown - be conservative
        # Only allow Level 2 for tropical waves if they're actually threatening (in_cone=True)
        # This prevents false positives for distant development areas
        return AlertLevel.ALL_CLEAR  # Level 1

    def _calculate_distance(
        self,
        cone: NHCCone,
        latitude: float,
        longitude: float
    ) -> float | None:
        """Calculate distance to storm center in kilometers.

        Args:
            cone: Storm cone data
            latitude: Target latitude
            longitude: Target longitude

        Returns:
            Distance in kilometers or None
        """
        if not cone.current_position:
            return None

        storm_lat, storm_lon = cone.current_position

        # Haversine formula for great circle distance
        import math

        lat1, lon1 = math.radians(latitude), math.radians(longitude)
        lat2, lon2 = math.radians(storm_lat), math.radians(storm_lon)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = (math.sin(dlat/2)**2 +
             math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2)
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in kilometers
        r = 6371

        return c * r

    def _calculate_confidence(
        self,
        cone: NHCCone,
        category: StormCategory,
        in_cone: bool
    ) -> float:
        """Calculate confidence in the assessment.

        Args:
            cone: Storm cone data
            category: Storm category
            in_cone: Whether location is in cone

        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 0.5  # Base confidence

        # Higher confidence for named storms
        if cone.storm_name and "unknown" not in cone.storm_name.lower():
            confidence += 0.2

        # Higher confidence for recent advisories
        if cone.advisory_num and cone.advisory_num != "Unknown":
            confidence += 0.1

        # Higher confidence for storms with position data
        if cone.current_position:
            confidence += 0.1

        # Higher confidence for well-defined categories
        if category in [StormCategory.HURRICANE_MAJOR, StormCategory.HURRICANE_MINOR,
                       StormCategory.TROPICAL_STORM]:
            confidence += 0.1

        return min(1.0, confidence)

    def _get_relevant_warnings(
        self,
        cone: NHCCone,
        nws_alerts: list[dict]
    ) -> list[str]:
        """Get warnings relevant to this storm.

        Args:
            cone: Storm cone data
            nws_alerts: NWS alerts

        Returns:
            List of relevant warning descriptions
        """
        warnings = []
        storm_name = (cone.storm_name or "").lower()

        for alert in nws_alerts:
            # Handle both NWSAlert objects and dict objects
            if hasattr(alert, 'description'):
                # NWSAlert object
                alert_desc = alert.description.lower()
                event = alert.event
            else:
                # Dict object
                alert_desc = alert.get("description", "").lower()
                event = alert.get("event", "")

            if storm_name and storm_name in alert_desc:
                warnings.append(event)

        return warnings

    def _estimate_arrival_time(
        self,
        cone: NHCCone,
        latitude: float,
        longitude: float
    ) -> int | None:
        """Estimate storm arrival time in hours.

        Args:
            cone: Storm cone data
            latitude: Target latitude
            longitude: Target longitude

        Returns:
            Estimated hours until arrival or None
        """
        if not cone.current_position or not cone.movement:
            return None

        distance_km = self._calculate_distance(cone, latitude, longitude)
        if not distance_km:
            return None

        # Parse movement for speed (rough estimate)
        movement = cone.movement.lower()
        speed_kph = 15  # Default 15 km/h

        # Try to extract speed from movement string
        import re
        speed_match = re.search(r'(\d+)\s*(?:mph|kph|km/h|knots)', movement)
        if speed_match:
            speed = int(speed_match.group(1))
            if 'mph' in movement or 'knots' in movement:
                speed_kph = speed * 1.6  # Convert to km/h
            else:
                speed_kph = speed

        if speed_kph > 0:
            return int(distance_km / speed_kph)

        return None

    def _get_nws_alerts(self, latitude: float, longitude: float) -> list[dict]:
        """Get NWS alerts for location.

        Args:
            latitude: Location latitude
            longitude: Location longitude

        Returns:
            List of NWS alerts
        """
        try:
            # Try NWS first (for US locations)
            nws_alerts = get_hurricane_alerts(latitude, longitude)

            # For international locations (like Bahamas), also check NHC text products
            nhc_alerts = self._get_nhc_alerts_for_location(latitude, longitude)

            # Combine both sources
            return nws_alerts + nhc_alerts

        except Exception as e:
            self.logger.warning(f"Failed to get alerts: {e}")
            return []

    def _get_nhc_alerts_for_location(self, latitude: float, longitude: float) -> list[dict]:
        """Get NHC watches/warnings for international locations like Bahamas.

        Args:
            latitude: Location latitude
            longitude: Location longitude

        Returns:
            List of NHC alerts in NWS-compatible format
        """
        alerts = []

        try:
            import requests

            # Check if location is in Bahamas region (expanded to include central Bahamas)
            if not (23.0 <= latitude <= 27.0 and -80.0 <= longitude <= -72.0):
                return alerts  # Only check for Bahamas region

            # Get current NHC text products for active storms
            headers = {"User-Agent": "weatherbot (alerts@example.com)"}

            # Try to get current storm advisories that might mention Bahamas
            try:
                # Get the tropical weather outlook
                outlook_url = "https://www.nhc.noaa.gov/text/refresh/MIATWOAT+shtml/latest.shtml"
                response = requests.get(outlook_url, headers=headers, timeout=15)

                if response.status_code == 200:
                    text = response.text.lower()

                    # Look for Bahamas mentions with watches/warnings
                    if "bahamas" in text or "nassau" in text:
                        if "tropical storm watch" in text:
                            alerts.append({
                                "event": "Tropical Storm Watch",
                                "description": "Tropical Storm Watch in effect for portions of the Bahamas",
                                "severity": "Moderate",
                                "urgency": "Expected",
                                "source": "NHC"
                            })
                        if "tropical storm warning" in text:
                            alerts.append({
                                "event": "Tropical Storm Warning",
                                "description": "Tropical Storm Warning in effect for portions of the Bahamas",
                                "severity": "Moderate",
                                "urgency": "Immediate",
                                "source": "NHC"
                            })
                        if "hurricane watch" in text:
                            alerts.append({
                                "event": "Hurricane Watch",
                                "description": "Hurricane Watch in effect for portions of the Bahamas",
                                "severity": "Severe",
                                "urgency": "Expected",
                                "source": "NHC"
                            })
                        if "hurricane warning" in text:
                            alerts.append({
                                "event": "Hurricane Warning",
                                "description": "Hurricane Warning in effect for portions of the Bahamas",
                                "severity": "Extreme",
                                "urgency": "Immediate",
                                "source": "NHC"
                            })

            except Exception as e:
                self.logger.debug(f"Could not check NHC outlook: {e}")

            # Also check individual storm advisories
            try:
                # Check specific storm advisories that might affect Bahamas
                # PTC Nine is currently AT4, so check that advisory
                storm_advisories = [
                    "https://www.nhc.noaa.gov/text/refresh/MIATCPAT4+shtml/latest.shtml",  # PTC Nine
                    "https://www.nhc.noaa.gov/text/refresh/MIATCPAT3+shtml/latest.shtml",  # Humberto
                    "https://www.nhc.noaa.gov/text/refresh/MIATCPAT1+shtml/latest.shtml",  # AT1
                    "https://www.nhc.noaa.gov/text/refresh/MIATCPAT2+shtml/latest.shtml",  # AT2
                    "https://www.nhc.noaa.gov/text/refresh/MIATCPAT5+shtml/latest.shtml",  # AT5
                ]

                for advisory_url in storm_advisories:
                    try:
                        adv_response = requests.get(advisory_url, headers=headers, timeout=10)
                        if adv_response.status_code == 200:
                            adv_text = adv_response.text.lower()

                            # Check if this advisory mentions Bahamas
                            if "bahamas" in adv_text or "nassau" in adv_text:
                                self.logger.debug(f"Found Bahamas mention in {advisory_url}")

                                # Extract storm name from the advisory
                                storm_name = "Unknown Storm"
                                try:
                                    # Look for storm name patterns in the text
                                    import re
                                    name_patterns = [
                                        r'hurricane\s+(\w+)',
                                        r'tropical storm\s+(\w+)',
                                        r'potential tropical cyclone\s+(\w+)',
                                        r'(\w+)\s+advisory'
                                    ]
                                    for pattern in name_patterns:
                                        match = re.search(pattern, adv_text)
                                        if match:
                                            storm_name = match.group(1).title()
                                            break
                                except:
                                    pass

                                # Parse watches and warnings more precisely
                                # Check if this location is specifically mentioned in watch/warning areas

                                # For Nassau/New Providence (northwestern Bahamas)
                                if latitude >= 24.5 and latitude <= 26.5 and longitude >= -78.5 and longitude <= -76.5:
                                    # Nassau area - check ONLY northwestern Bahamas alerts
                                    # Parse the text more carefully to distinguish between central and northwestern

                                    # Look for the specific watch/warning sections
                                    lines = adv_text.split('\n')
                                    in_watch_section = False
                                    in_warning_section = False

                                    for line in lines:
                                        line_clean = line.strip().lower()

                                        # Identify sections
                                        if "tropical storm watch is in effect for" in line_clean:
                                            in_watch_section = True
                                            in_warning_section = False
                                            continue
                                        if "tropical storm warning is in effect for" in line_clean:
                                            in_warning_section = True
                                            in_watch_section = False
                                            continue
                                        if line_clean.startswith("a ") and ("watch" in line_clean or "warning" in line_clean):
                                            in_watch_section = False
                                            in_warning_section = False
                                            continue

                                        # Check if Nassau/New Providence is mentioned in the current section
                                        if in_watch_section and ("northwestern bahamas" in line_clean or "new providence" in line_clean):
                                            alerts.append({
                                                "event": "Tropical Storm Watch",
                                                "description": "Tropical Storm Watch in effect for northwestern Bahamas including New Providence",
                                                "severity": "Moderate",
                                                "urgency": "Expected",
                                                "source": "NHC",
                                                "storm": storm_name
                                            })
                                            break  # Only add once

                                        if in_warning_section and ("northwestern bahamas" in line_clean or "new providence" in line_clean):
                                            alerts.append({
                                                "event": "Tropical Storm Warning",
                                                "description": "Tropical Storm Warning in effect for northwestern Bahamas including New Providence",
                                                "severity": "Moderate",
                                                "urgency": "Immediate",
                                                "source": "NHC",
                                                "storm": storm_name
                                            })
                                            break  # Only add once

                                # For Exuma and central Bahamas (central Bahamas)
                                elif latitude >= 23.0 and latitude <= 25.0 and longitude >= -77.0 and longitude <= -75.0:
                                    # Central Bahamas area - check for central Bahamas alerts
                                    # Parse the text more carefully to distinguish between central and northwestern

                                    # Look for the specific watch/warning sections
                                    lines = adv_text.split('\n')
                                    in_watch_section = False
                                    in_warning_section = False

                                    for line in lines:
                                        line_clean = line.strip().lower()

                                        # Identify sections
                                        if "tropical storm watch is in effect for" in line_clean:
                                            in_watch_section = True
                                            in_warning_section = False
                                            continue
                                        if "tropical storm warning is in effect for" in line_clean:
                                            in_warning_section = True
                                            in_watch_section = False
                                            continue
                                        if line_clean.startswith("a ") and ("watch" in line_clean or "warning" in line_clean):
                                            in_watch_section = False
                                            in_warning_section = False
                                            continue

                                        # Check if central Bahamas/Exuma is mentioned in the current section
                                        if in_watch_section and ("central bahamas" in line_clean or "exuma" in line_clean or "exumas" in line_clean):
                                            alerts.append({
                                                "event": "Tropical Storm Watch",
                                                "description": "Tropical Storm Watch in effect for central Bahamas including Exuma",
                                                "severity": "Moderate",
                                                "urgency": "Expected",
                                                "source": "NHC",
                                                "storm": storm_name
                                            })
                                            break  # Only add once

                                        if in_warning_section and ("central bahamas" in line_clean or "exuma" in line_clean or "exumas" in line_clean):
                                            alerts.append({
                                                "event": "Tropical Storm Warning",
                                                "description": "Tropical Storm Warning in effect for central Bahamas including Exuma",
                                                "severity": "Moderate",
                                                "urgency": "Immediate",
                                                "source": "NHC",
                                                "storm": storm_name
                                            })
                                            break  # Only add once
                                else:
                                    # Other Bahamas areas - use general detection
                                    if "tropical storm watch" in adv_text and "bahamas" in adv_text:
                                        alerts.append({
                                            "event": "Tropical Storm Watch",
                                            "description": "Tropical Storm Watch in effect for portions of the Bahamas",
                                            "severity": "Moderate",
                                            "urgency": "Expected",
                                            "source": "NHC",
                                            "storm": storm_name
                                        })

                                    if "tropical storm warning" in adv_text and "bahamas" in adv_text:
                                        alerts.append({
                                            "event": "Tropical Storm Warning",
                                            "description": "Tropical Storm Warning in effect for portions of the Bahamas",
                                            "severity": "Moderate",
                                            "urgency": "Immediate",
                                            "source": "NHC",
                                            "storm": storm_name
                                        })

                                if "hurricane watch" in adv_text and ("bahamas" in adv_text or "nassau" in adv_text):
                                    alerts.append({
                                        "event": "Hurricane Watch",
                                        "description": "Hurricane Watch in effect for portions of the Bahamas",
                                        "severity": "Severe",
                                        "urgency": "Expected",
                                        "source": "NHC",
                                        "storm": storm_name
                                    })

                                if "hurricane warning" in adv_text and ("bahamas" in adv_text or "nassau" in adv_text):
                                    alerts.append({
                                        "event": "Hurricane Warning",
                                        "description": "Hurricane Warning in effect for portions of the Bahamas",
                                        "severity": "Extreme",
                                        "urgency": "Immediate",
                                        "source": "NHC",
                                        "storm": storm_name
                                    })

                    except Exception as e:
                        self.logger.debug(f"Could not check advisory {advisory_url}: {e}")

            except Exception as e:
                self.logger.debug(f"Could not check storm advisories: {e}")

        except Exception as e:
            self.logger.warning(f"NHC alert check failed: {e}")

        return alerts

    def _apply_nws_overrides(
        self,
        current_level: AlertLevel,
        nws_alerts: list[dict]
    ) -> AlertLevel:
        """Apply NWS alert overrides to threat level.

        Args:
            current_level: Current alert level
            nws_alerts: NWS alerts

        Returns:
            Potentially upgraded alert level
        """
        highest_nws_level = AlertLevel.ALL_CLEAR

        for alert in nws_alerts:
            # Handle both NWSAlert objects and dict objects
            if hasattr(alert, 'event'):
                # NWSAlert object
                event = alert.event.lower()
            else:
                # Dict object
                event = alert.get("event", "").lower()

            if "hurricane warning" in event:
                nws_level = AlertLevel.HURRICANE_WARNING
            elif "hurricane watch" in event or "tropical storm warning" in event:
                nws_level = AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION
            elif "tropical storm watch" in event:
                nws_level = AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT
            else:
                continue

            if nws_level.value > highest_nws_level.value:
                highest_nws_level = nws_level

        # Return the higher of current level or NWS level
        return (highest_nws_level if highest_nws_level.value > current_level.value
                else current_level)


def analyze_location_threat_enhanced(
    latitude: float,
    longitude: float,
    use_county_intersect: bool = False,
    county_geojson_path: str | None = None,
) -> dict[str, AlertLevel | list[StormThreat] | bool]:
    """Enhanced location threat analysis with maximum accuracy.

    Args:
        latitude: Location latitude
        longitude: Location longitude
        use_county_intersect: Use county-level intersection
        county_geojson_path: Path to county GeoJSON file

    Returns:
        Comprehensive threat analysis results
    """
    analyzer = EnhancedConeAnalyzer()
    return analyzer.analyze_location_threat(
        latitude, longitude, use_county_intersect, county_geojson_path
    )
