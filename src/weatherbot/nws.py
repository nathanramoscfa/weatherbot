# src/weatherbot/nws.py
"""NWS alerts API integration."""

import logging
from datetime import datetime

import requests
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# NWS API base URL
NWS_API_BASE = "https://api.weather.gov"

# Request timeout in seconds
REQUEST_TIMEOUT = 30

# Target hurricane and tropical storm events
HURRICANE_EVENTS = [
    "Hurricane Watch",
    "Hurricane Warning",
    "Tropical Storm Watch",
    "Tropical Storm Warning"
]


class NWSAlert(BaseModel):
    """Represents an NWS alert."""

    id: str = Field(description="Alert CAP ID")
    event: str = Field(description="Alert event type")
    severity: str = Field(description="Alert severity")
    urgency: str = Field(description="Alert urgency")
    certainty: str = Field(description="Alert certainty")
    headline: str = Field(description="Alert headline")
    description: str = Field(description="Alert description")
    effective: datetime | None = Field(
        default=None,
        description="Effective time",
    )
    expires: datetime | None = Field(
        default=None,
        description="Expiration time",
    )
    areas: list[str] = Field(
        default_factory=list,
        description="Affected areas",
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"NWSAlert(id='{self.id}', event='{self.event}', severity='{self.severity}')"

    def is_hurricane_alert(self) -> bool:
        """Check if this is a hurricane or tropical storm alert.

        Returns:
            True if this is a hurricane or tropical storm alert
        """
        return self.event in HURRICANE_EVENTS

    def get_severity_prefix(self) -> str:
        """Get severity prefix for notifications.

        Returns:
            Emoji prefix based on event type
        """
        if self.event == "Hurricane Warning":
            return "🛑🛑 WARNING"
        if self.event == "Hurricane Watch":
            return "🛑 WATCH"
        if self.event == "Tropical Storm Warning":
            return "🚨 WARNING"
        if self.event == "Tropical Storm Watch":
            return "⚠️ WATCH"
        return "⚠️ ALERT"


class NWSClient:
    """Client for fetching NWS alerts."""

    def __init__(self, timeout: int = REQUEST_TIMEOUT) -> None:
        """Initialize NWS client.

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
        """Make HTTP request with retry logic.

        Args:
            url: Request URL
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            requests.RequestException: On HTTP errors
        """
        logger.debug(f"Making request to: {url}")
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def fetch_point_alerts(
        self,
        latitude: float,
        longitude: float,
        events: list[str] | None = None,
    ) -> list[NWSAlert]:
        """Fetch active alerts for a specific point.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            events: List of event types to filter (default: hurricane events)

        Returns:
            List of active alerts
        """
        if events is None:
            events = HURRICANE_EVENTS

        try:
            # Fetch all alerts for the point without event filtering
            # This is more reliable than filtering by event on the API side
            url = f"{NWS_API_BASE}/alerts/active"
            params = {
                "point": f"{latitude},{longitude}",
            }

            data = self._make_request(url, params)

            if "features" not in data:
                logger.warning("No features in alerts response")
                return []

            alerts = []
            for feature in data["features"]:
                try:
                    alert = self._parse_alert_feature(feature)
                    if alert and alert.event in events:
                        alerts.append(alert)
                except Exception as e:
                    logger.warning(f"Failed to parse alert feature: {e}")
                    continue

            logger.info(f"Fetched {len(alerts)} hurricane-related alerts for point ({latitude}, {longitude})")
            return alerts

        except Exception as e:
            logger.error(f"Failed to fetch alerts for point: {e}")
            return []


    def _parse_alert_feature(self, feature: dict) -> NWSAlert | None:
        """Parse a GeoJSON feature into an NWS alert.

        Args:
            feature: GeoJSON feature

        Returns:
            NWS alert or None if parsing fails
        """
        try:
            props = feature.get("properties", {})

            # Required fields
            alert_id = props.get("id")
            if not alert_id:
                logger.warning("Alert missing ID")
                return None

            event = props.get("event", "Unknown")
            severity = props.get("severity", "Unknown")
            urgency = props.get("urgency", "Unknown")
            certainty = props.get("certainty", "Unknown")
            headline = props.get("headline", "")
            description = props.get("description", "")

            # Parse timestamps
            effective = self._parse_timestamp(props.get("effective"))
            expires = self._parse_timestamp(props.get("expires"))

            # Extract area names
            areas = []
            area_desc = props.get("areaDesc", "")
            if area_desc:
                areas = [area.strip() for area in area_desc.split(";")]

            return NWSAlert(
                id=alert_id,
                event=event,
                severity=severity,
                urgency=urgency,
                certainty=certainty,
                headline=headline,
                description=description,
                effective=effective,
                expires=expires,
                areas=areas,
            )

        except Exception as e:
            logger.error(f"Failed to parse alert feature: {e}")
            return None

    def _parse_timestamp(self, timestamp_str: str | None) -> datetime | None:
        """Parse ISO timestamp string.

        Args:
            timestamp_str: ISO timestamp string

        Returns:
            Parsed datetime or None if invalid
        """
        if not timestamp_str:
            return None

        try:
            # Handle timezone info
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            elif "+" in timestamp_str or timestamp_str.count("-") > 2:
                # Already has timezone info
                pass
            else:
                # Assume UTC if no timezone
                timestamp_str += "+00:00"

            return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return None


def get_hurricane_alerts(latitude: float, longitude: float) -> list[NWSAlert]:
    """Get hurricane and tropical storm alerts for a specific point.

    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees

    Returns:
        List of hurricane and tropical storm alerts
    """
    client = NWSClient()
    return client.fetch_point_alerts(latitude, longitude, HURRICANE_EVENTS)
