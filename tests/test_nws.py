# tests/test_nws.py
"""Tests for NWS alerts API integration."""

from unittest.mock import Mock, patch

import pytest

from weatherbot.nws import NWSAlert, NWSClient, get_hurricane_alerts


class TestNWSAlert:
    """Test NWSAlert class."""

    def test_nws_alert_creation(self) -> None:
        """Test NWSAlert creation with all fields."""
        alert = NWSAlert(
            id="test-alert-123",
            event="Hurricane Warning",
            severity="Severe",
            urgency="Immediate",
            certainty="Observed",
            headline="Hurricane Warning for Miami-Dade County",
            description="Hurricane conditions expected within 36 hours.",
            effective="2023-09-28T12:00:00Z",
            expires="2023-09-29T12:00:00Z"
        )

        assert alert.id == "test-alert-123"
        assert alert.event == "Hurricane Warning"
        assert alert.severity == "Severe"
        assert alert.urgency == "Immediate"
        assert alert.certainty == "Observed"
        assert alert.headline == "Hurricane Warning for Miami-Dade County"
        assert alert.description == "Hurricane conditions expected within 36 hours."

    def test_nws_alert_minimal(self) -> None:
        """Test NWSAlert creation with minimal fields."""
        alert = NWSAlert(
            id="test-alert-456",
            event="Tropical Storm Watch",
            severity="Moderate",
            urgency="Expected",
            certainty="Likely",
            headline="Tropical Storm Watch",
            description="Tropical storm conditions possible."
        )

        assert alert.id == "test-alert-456"
        assert alert.event == "Tropical Storm Watch"
        assert alert.effective is None
        assert alert.expires is None
        assert alert.areas == []

    def test_is_hurricane_alert(self) -> None:
        """Test hurricane alert detection."""
        hurricane_alert = NWSAlert(
            id="alert-1",
            event="Hurricane Warning",
            severity="Severe",
            urgency="Immediate",
            certainty="Observed",
            headline="Hurricane Warning",
            description="Hurricane conditions expected."
        )

        tropical_alert = NWSAlert(
            id="alert-2",
            event="Tropical Storm Watch",
            severity="Moderate",
            urgency="Expected",
            certainty="Likely",
            headline="Tropical Storm Watch",
            description="Tropical storm conditions possible."
        )

        tornado_alert = NWSAlert(
            id="alert-3",
            event="Tornado Warning",
            severity="Severe",
            urgency="Immediate",
            certainty="Observed",
            headline="Tornado Warning",
            description="Tornado conditions expected."
        )

        assert hurricane_alert.is_hurricane_alert() is True
        assert tropical_alert.is_hurricane_alert() is True
        assert tornado_alert.is_hurricane_alert() is False

    def test_get_severity_prefix(self) -> None:
        """Test severity prefix generation."""
        hurricane_warning = NWSAlert(
            id="alert-1",
            event="Hurricane Warning",
            severity="Severe",
            urgency="Immediate",
            certainty="Observed",
            headline="Hurricane Warning",
            description="Hurricane conditions expected."
        )

        hurricane_watch = NWSAlert(
            id="alert-2",
            event="Hurricane Watch",
            severity="Moderate",
            urgency="Expected",
            certainty="Likely",
            headline="Hurricane Watch",
            description="Hurricane conditions possible."
        )

        tropical_warning = NWSAlert(
            id="alert-3",
            event="Tropical Storm Warning",
            severity="Severe",
            urgency="Immediate",
            certainty="Observed",
            headline="Tropical Storm Warning",
            description="Tropical storm conditions expected."
        )

        tropical_watch = NWSAlert(
            id="alert-4",
            event="Tropical Storm Watch",
            severity="Moderate",
            urgency="Expected",
            certainty="Likely",
            headline="Tropical Storm Watch",
            description="Tropical storm conditions possible."
        )

        other_alert = NWSAlert(
            id="alert-5",
            event="Flood Warning",
            severity="Severe",
            urgency="Immediate",
            certainty="Observed",
            headline="Flood Warning",
            description="Flood conditions expected."
        )

        assert hurricane_warning.get_severity_prefix() == "🛑🛑 WARNING"
        assert hurricane_watch.get_severity_prefix() == "🛑 WATCH"
        assert tropical_warning.get_severity_prefix() == "🚨 WARNING"
        assert tropical_watch.get_severity_prefix() == "⚠️ WATCH"
        assert other_alert.get_severity_prefix() == "⚠️ ALERT"


class TestNWSClient:
    """Test NWSClient class."""

    def test_init(self) -> None:
        """Test NWSClient initialization."""
        client = NWSClient()

        assert client.timeout == 30
        assert client.session is not None
        assert "weatherbot" in client.session.headers["User-Agent"]

    @patch('weatherbot.nws.NWSClient._make_request')
    def test_fetch_point_alerts_success(self, mock_make_request) -> None:
        """Test successful point alerts retrieval."""
        mock_make_request.return_value = {
            "features": [
                {
                    "properties": {
                        "id": "test-alert-123",
                        "event": "Hurricane Warning",
                        "severity": "Severe",
                        "urgency": "Immediate",
                        "certainty": "Observed",
                        "headline": "Hurricane Warning",
                        "description": "Hurricane conditions expected.",
                        "effective": "2023-09-28T12:00:00Z",
                        "expires": "2023-09-29T12:00:00Z",
                        "areaDesc": "Miami-Dade County"
                    }
                }
            ]
        }

        client = NWSClient()

        alerts = client.fetch_point_alerts(25.7617, -80.1918)

        assert len(alerts) == 1
        assert alerts[0].event == "Hurricane Warning"

    @patch('weatherbot.nws.NWSClient._make_request')
    def test_fetch_point_alerts_no_features(self, mock_make_request) -> None:
        """Test alerts retrieval with no features."""
        mock_make_request.return_value = {"features": []}

        client = NWSClient()

        alerts = client.fetch_point_alerts(25.7617, -80.1918)

        assert len(alerts) == 0

    @patch('weatherbot.nws.NWSClient._make_request')
    def test_fetch_point_alerts_request_exception(self, mock_make_request) -> None:
        """Test alerts retrieval with request exception."""
        mock_make_request.side_effect = Exception("Network error")

        client = NWSClient()

        alerts = client.fetch_point_alerts(25.7617, -80.1918)

        assert len(alerts) == 0


class TestGetHurricaneAlerts:
    """Test get_hurricane_alerts function."""

    @patch('weatherbot.nws.NWSClient')
    def test_get_hurricane_alerts_success(self, mock_client_class) -> None:
        """Test successful hurricane alerts fetching."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_alerts = [
            NWSAlert(
                id="alert-1",
                event="Hurricane Warning",
                severity="Severe",
                urgency="Immediate",
                certainty="Observed",
                headline="Hurricane Warning",
                description="Hurricane conditions expected."
            )
        ]
        mock_client.fetch_point_alerts.return_value = mock_alerts

        alerts = get_hurricane_alerts(25.7617, -80.1918)

        assert len(alerts) == 1
        assert alerts[0].event == "Hurricane Warning"

    @patch('weatherbot.nws.NWSClient')
    def test_get_hurricane_alerts_no_alerts(self, mock_client_class) -> None:
        """Test fetching when no alerts available."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.fetch_point_alerts.return_value = []

        alerts = get_hurricane_alerts(25.7617, -80.1918)

        assert len(alerts) == 0

    @patch('weatherbot.nws.NWSClient')
    def test_get_hurricane_alerts_client_error(self, mock_client_class) -> None:
        """Test fetching when client raises error."""
        mock_client_class.side_effect = Exception("Client error")

        with pytest.raises(Exception, match="Client error"):
            get_hurricane_alerts(25.7617, -80.1918)
