# src/weatherbot/coverage_validator.py
"""Coordinate coverage validation for NOAA data sources."""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CoverageStatus(Enum):
    """Coverage status for coordinates."""
    COVERED = "covered"
    MARGINAL = "marginal"
    OUTSIDE = "outside"
    UNKNOWN = "unknown"


class CoverageValidator:
    """Validates if coordinates are within NOAA coverage areas."""

    # NOAA/NHC Atlantic Basin boundaries (approximate)
    ATLANTIC_BASIN_BOUNDS = {
        "min_lat": 0.0,
        "max_lat": 60.0,
        "min_lon": -100.0,  # Western boundary
        "max_lon": 0.0,     # Eastern boundary (prime meridian)
    }

    # NOAA/NHC Eastern Pacific Basin boundaries
    EASTERN_PACIFIC_BASIN_BOUNDS = {
        "min_lat": 0.0,
        "max_lat": 60.0,
        "min_lon": -180.0,  # Western boundary (International Date Line)
        "max_lon": -100.0,  # Eastern boundary (Mexico/Central America)
    }

    # NOAA/NHC Central Pacific Basin boundaries
    CENTRAL_PACIFIC_BASIN_BOUNDS = {
        "min_lat": 0.0,
        "max_lat": 60.0,
        "min_lon": -180.0,  # Western boundary (International Date Line)
        "max_lon": -140.0,  # Eastern boundary (140°W)
    }

    # NWS coverage area (US and territories)
    NWS_BOUNDS = {
        "min_lat": 15.0,    # Southern US territories
        "max_lat": 72.0,    # Northern Alaska
        "min_lon": -180.0,  # Western Alaska
        "max_lon": -65.0,   # Eastern US
    }

    # Caribbean and Gulf of Mexico (high priority for hurricanes)
    CARIBBEAN_BOUNDS = {
        "min_lat": 10.0,
        "max_lat": 30.0,
        "min_lon": -90.0,
        "max_lon": -60.0,
    }

    def __init__(self) -> None:
        """Initialize coverage validator."""
        self.warnings = []
        self.errors = []

    def validate_coordinates(
        self,
        latitude: float,
        longitude: float
    ) -> dict[str, Any]:
        """Validate coordinates against NOAA coverage areas.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees

        Returns:
            Dictionary with validation results
        """
        self.warnings = []
        self.errors = []

        # Basic coordinate validation
        if not (-90 <= latitude <= 90):
            self.errors.append(f"Invalid latitude: {latitude}")
            return self._create_result(CoverageStatus.UNKNOWN)

        if not (-180 <= longitude <= 180):
            self.errors.append(f"Invalid longitude: {longitude}")
            return self._create_result(CoverageStatus.UNKNOWN)

        # Determine which NHC basin the location falls into
        basin = self._determine_nhc_basin(latitude, longitude)

        # Check NHC coverage for the appropriate basin
        nhc_status = self._check_nhc_coverage(latitude, longitude, basin)

        # Check NWS coverage
        nws_status = self._check_nws_coverage(latitude, longitude)

        # Check Caribbean priority area
        caribbean_status = self._check_caribbean_coverage(latitude, longitude)

        # Determine overall status
        overall_status = self._determine_overall_status(
            nhc_status, nws_status, caribbean_status
        )

        return self._create_result(
            overall_status,
            nhc_status=nhc_status,
            nws_status=nws_status,
            caribbean_status=caribbean_status,
            basin=basin
        )

    def _determine_nhc_basin(self, lat: float, lon: float) -> str:
        """Determine which NHC basin a location falls into.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Basin name: 'atlantic', 'eastern_pacific', 'central_pacific', or 'none'
        """
        # Check Atlantic Basin (0°N to 60°N, 100°W to 0°E)
        if (self.ATLANTIC_BASIN_BOUNDS["min_lat"] <= lat <= self.ATLANTIC_BASIN_BOUNDS["max_lat"] and
            self.ATLANTIC_BASIN_BOUNDS["min_lon"] <= lon <= self.ATLANTIC_BASIN_BOUNDS["max_lon"]):
            return "atlantic"

        # Check Central Pacific Basin first (more specific: 0°N to 60°N, 180°W to 140°W)
        if (self.CENTRAL_PACIFIC_BASIN_BOUNDS["min_lat"] <= lat <= self.CENTRAL_PACIFIC_BASIN_BOUNDS["max_lat"] and
            self.CENTRAL_PACIFIC_BASIN_BOUNDS["min_lon"] <= lon <= self.CENTRAL_PACIFIC_BASIN_BOUNDS["max_lon"]):
            return "central_pacific"

        # Check Eastern Pacific Basin (0°N to 60°N, 180°W to 100°W)
        if (self.EASTERN_PACIFIC_BASIN_BOUNDS["min_lat"] <= lat <= self.EASTERN_PACIFIC_BASIN_BOUNDS["max_lat"] and
            self.EASTERN_PACIFIC_BASIN_BOUNDS["min_lon"] <= lon <= self.EASTERN_PACIFIC_BASIN_BOUNDS["max_lon"]):
            return "eastern_pacific"

        return "none"

    def _check_nhc_coverage(self, lat: float, lon: float, basin: str) -> CoverageStatus:
        """Check NHC coverage for the appropriate basin.

        Args:
            lat: Latitude
            lon: Longitude
            basin: Basin name ('atlantic', 'eastern_pacific', 'central_pacific', 'none')

        Returns:
            Coverage status for NHC
        """
        if basin == "none":
            self.warnings.append(
                f"Location ({lat:.4f}, {lon:.4f}) is outside all NHC basins. "
                "No hurricane forecast data available."
            )
            return CoverageStatus.OUTSIDE

        # Get the appropriate bounds for the basin
        if basin == "atlantic":
            bounds = self.ATLANTIC_BASIN_BOUNDS
            basin_name = "Atlantic"
        elif basin == "eastern_pacific":
            bounds = self.EASTERN_PACIFIC_BASIN_BOUNDS
            basin_name = "Eastern Pacific"
        elif basin == "central_pacific":
            bounds = self.CENTRAL_PACIFIC_BASIN_BOUNDS
            basin_name = "Central Pacific"
        else:
            return CoverageStatus.OUTSIDE

        if (bounds["min_lat"] <= lat <= bounds["max_lat"] and
            bounds["min_lon"] <= lon <= bounds["max_lon"]):
            return CoverageStatus.COVERED

        # Check if close to boundaries (marginal coverage)
        lat_margin = 5.0
        lon_margin = 10.0

        if (bounds["min_lat"] - lat_margin <= lat <= bounds["max_lat"] + lat_margin and
            bounds["min_lon"] - lon_margin <= lon <= bounds["max_lon"] + lon_margin):
            self.warnings.append(
                f"Location ({lat:.4f}, {lon:.4f}) is near NHC {basin_name} Basin boundary. "
                "Hurricane forecasts may be less accurate."
            )
            return CoverageStatus.MARGINAL

        self.warnings.append(
            f"Location ({lat:.4f}, {lon:.4f}) is outside NHC {basin_name} Basin. "
            "No hurricane forecast data available."
        )
        return CoverageStatus.OUTSIDE

    def _check_nws_coverage(self, lat: float, lon: float) -> CoverageStatus:
        """Check NWS coverage.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Coverage status for NWS
        """
        bounds = self.NWS_BOUNDS

        if (bounds["min_lat"] <= lat <= bounds["max_lat"] and
            bounds["min_lon"] <= lon <= bounds["max_lon"]):
            return CoverageStatus.COVERED

        # Check if in US territories or close to US
        if (10.0 <= lat <= 20.0 and -180.0 <= lon <= -65.0):
            self.warnings.append(
                f"Location ({lat:.4f}, {lon:.4f}) may be in US territory. "
                "NWS alerts may be available."
            )
            return CoverageStatus.MARGINAL

        self.warnings.append(
            f"Location ({lat:.4f}, {lon:.4f}) is outside NWS coverage area. "
            "No official weather alerts available."
        )
        return CoverageStatus.OUTSIDE

    def _check_caribbean_coverage(self, lat: float, lon: float) -> CoverageStatus:
        """Check Caribbean/Gulf coverage (high hurricane risk area).

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Coverage status for Caribbean
        """
        bounds = self.CARIBBEAN_BOUNDS

        if (bounds["min_lat"] <= lat <= bounds["max_lat"] and
            bounds["min_lon"] <= lon <= bounds["max_lon"]):
            return CoverageStatus.COVERED

        return CoverageStatus.OUTSIDE

    def _determine_overall_status(
        self,
        nhc_status: CoverageStatus,
        nws_status: CoverageStatus,
        caribbean_status: CoverageStatus
    ) -> CoverageStatus:
        """Determine overall coverage status.

        Args:
            nhc_status: NHC coverage status
            nws_status: NWS coverage status
            caribbean_status: Caribbean coverage status

        Returns:
            Overall coverage status
        """
        # If any service is covered, overall is at least marginal
        if (CoverageStatus.COVERED in (nhc_status, nws_status, caribbean_status)):
            return CoverageStatus.COVERED

        # If any service is marginal, overall is marginal
        if (CoverageStatus.MARGINAL in (nhc_status, nws_status)):
            return CoverageStatus.MARGINAL

        # Otherwise outside coverage
        return CoverageStatus.OUTSIDE

    def _create_result(
        self,
        status: CoverageStatus,
        nhc_status: CoverageStatus | None = None,
        nws_status: CoverageStatus | None = None,
        caribbean_status: CoverageStatus | None = None,
        basin: str | None = None
    ) -> dict[str, Any]:
        """Create validation result dictionary.

        Args:
            status: Overall coverage status
            nhc_status: NHC coverage status
            nws_status: NWS coverage status
            caribbean_status: Caribbean coverage status
            basin: NHC basin name

        Returns:
            Validation result dictionary
        """
        return {
            "status": status,
            "nhc_status": nhc_status,
            "nws_status": nws_status,
            "caribbean_status": caribbean_status,
            "basin": basin,
            "warnings": self.warnings.copy(),
            "errors": self.errors.copy(),
            "is_covered": status == CoverageStatus.COVERED,
            "is_marginal": status == CoverageStatus.MARGINAL,
            "is_outside": status == CoverageStatus.OUTSIDE,
        }

    def get_coverage_recommendations(
        self,
        latitude: float,
        longitude: float
    ) -> list[str]:
        """Get recommendations for out-of-coverage coordinates.

        Args:
            latitude: Latitude
            longitude: Longitude

        Returns:
            List of recommendations
        """
        recommendations = []

        # Determine which basin the location is in
        basin = self._determine_nhc_basin(latitude, longitude)

        if basin == "none":
            recommendations.extend([
                "This location is outside all NOAA hurricane basins.",
                "Consider using coordinates within NOAA coverage areas:",
                "",
                "Atlantic Basin (0°N to 60°N, 100°W to 0°E):",
                "  • US East Coast, Caribbean, Gulf of Mexico, Atlantic Ocean",
                "  • Example: Miami, FL (25.7617°N, 80.1918°W)",
                "",
                "Eastern Pacific Basin (0°N to 60°N, 180°W to 100°W):",
                "  • West Coast of North America, Mexico, Central America",
                "  • Example: Los Angeles, CA (34.0522°N, 118.2437°W)",
                "",
                "Central Pacific Basin (0°N to 60°N, 180°W to 140°W):",
                "  • Hawaii, Pacific Islands",
                "  • Example: Honolulu, HI (21.3099°N, 157.8581°W)"
            ])
        else:
            # Location is in a basin, provide basin-specific info
            basin_names = {
                "atlantic": "Atlantic",
                "eastern_pacific": "Eastern Pacific",
                "central_pacific": "Central Pacific"
            }
            recommendations.append(f"Location is in the {basin_names.get(basin, 'Unknown')} Basin.")

        # Check if in NWS coverage
        if not self._is_in_nws_coverage(latitude, longitude):
            recommendations.extend([
                "",
                "This location is outside NWS coverage area.",
                "Consider using coordinates within the United States or territories:",
                "  • Continental US: 24°N to 49°N, 67°W to 125°W",
                "  • Alaska: 51°N to 72°N, 130°W to 173°E",
                "  • Hawaii: 18°N to 22°N, 154°W to 162°W",
                "  • Puerto Rico: 17°N to 18°N, 65°W to 68°W"
            ])

        # Suggest alternative coordinates for each basin
        if recommendations:
            recommendations.extend([
                "",
                "Suggested alternative coordinates for hurricane monitoring:",
                "",
                "Atlantic Basin:",
                "  • Miami, FL: 25.7617°N, 80.1918°W",
                "  • New Orleans, LA: 29.9511°N, 90.0715°W",
                "  • San Juan, PR: 18.2208°N, 66.5901°W",
                "  • Houston, TX: 29.7604°N, 95.3698°W",
                "",
                "Eastern Pacific Basin:",
                "  • Los Angeles, CA: 34.0522°N, 118.2437°W",
                "  • San Diego, CA: 32.7157°N, 117.1611°W",
                "  • Cabo San Lucas, Mexico: 22.8905°N, 109.9167°W",
                "",
                "Central Pacific Basin:",
                "  • Honolulu, HI: 21.3099°N, 157.8581°W",
                "  • Hilo, HI: 19.7297°N, 155.0900°W"
            ])

        return recommendations

    def _is_in_atlantic_basin(self, lat: float, lon: float) -> bool:
        """Check if coordinates are in Atlantic Basin."""
        bounds = self.ATLANTIC_BASIN_BOUNDS
        return (bounds["min_lat"] <= lat <= bounds["max_lat"] and
                bounds["min_lon"] <= lon <= bounds["max_lon"])

    def _is_in_nws_coverage(self, lat: float, lon: float) -> bool:
        """Check if coordinates are in NWS coverage."""
        bounds = self.NWS_BOUNDS
        return (bounds["min_lat"] <= lat <= bounds["max_lat"] and
                bounds["min_lon"] <= lon <= bounds["max_lon"])


def validate_coordinate_coverage(latitude: float, longitude: float) -> dict[str, any]:
    """Validate coordinate coverage for NOAA data sources.

    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees

    Returns:
        Validation result dictionary
    """
    validator = CoverageValidator()
    return validator.validate_coordinates(latitude, longitude)
