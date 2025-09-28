# tests/test_reports.py
"""Tests for report generation."""

from unittest.mock import Mock, patch

from weatherbot.alert_levels import AlertInfo, AlertLevel
from weatherbot.reports import generate_html_report, get_location_name


class TestGetLocationName:
    """Test get_location_name function."""

    @patch('weatherbot.reports.requests.get')
    def test_get_location_name_success(self, mock_get) -> None:
        """Test successful location name retrieval."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'address': {
                'city': 'Miami',
                'county': 'Miami-Dade County',
                'state': 'Florida',
                'country': 'United States'
            }
        }
        mock_get.return_value = mock_response

        result = get_location_name(25.7617, -80.1918)

        assert result == "Miami, Florida"
        mock_get.assert_called_once()

    @patch('weatherbot.reports.requests.get')
    def test_get_location_name_partial_data(self, mock_get) -> None:
        """Test location name with partial address data."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'address': {
                'city': 'Miami',
                'state': 'Florida'
                # Missing county and country
            }
        }
        mock_get.return_value = mock_response

        result = get_location_name(25.7617, -80.1918)

        assert result == "Miami, Florida"

    @patch('weatherbot.reports.requests.get')
    def test_get_location_name_no_address(self, mock_get) -> None:
        """Test location name when no address data available."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        result = get_location_name(25.7617, -80.1918)

        assert result == "Location 25.7617°N, -80.1918°W"

    @patch('weatherbot.reports.requests.get')
    def test_get_location_name_request_failure(self, mock_get) -> None:
        """Test location name when request fails."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        result = get_location_name(25.7617, -80.1918)

        assert result == "Location 25.7617°N, -80.1918°W"

    @patch('weatherbot.reports.requests.get')
    def test_get_location_name_request_exception(self, mock_get) -> None:
        """Test location name when request raises exception."""
        mock_get.side_effect = Exception("Network error")

        result = get_location_name(25.7617, -80.1918)

        assert result == "Location 25.7617°N, -80.1918°W"


class TestGenerateHtmlReport:
    """Test generate_html_report function."""

    def test_generate_html_report_basic(self) -> None:
        """Test basic HTML report generation."""
        # Mock data - create AlertInfo object
        alert_info = AlertInfo(
            level=AlertLevel.TROPICAL_STORM_THREAT,
            icon="⚠️",
            color="#FF9800",
            sound_pattern="moderate",
            title_prefix="TROPICAL STORM THREAT",
            guidance="Tropical storm conditions possible within 48-72 hours."
        )

        config = Mock()
        config.home_lat = 25.7617
        config.home_lon = -80.1918
        config.openai_api_key = None

        result = generate_html_report(
            alert_level=3,
            alert_enum=AlertLevel.TROPICAL_STORM_THREAT,
            alert_info=alert_info,
            title="Tropical Storm Threat",
            message="Tropical storm conditions possible",
            config=config,
            location_name="Miami, FL"
        )

        assert isinstance(result, str)
        assert result.endswith(".html")
        assert "hurricane_threat_analysis" in result

    def test_generate_html_report_no_storms(self) -> None:
        """Test HTML report generation with no storms."""
        alert_info = AlertInfo(
            level=AlertLevel.ALL_CLEAR,
            icon="✅",
            color="#4CAF50",
            sound_pattern="none",
            title_prefix="ALL CLEAR",
            guidance="No active weather disturbances threatening your location."
        )

        config = Mock()
        config.home_lat = 25.7617
        config.home_lon = -80.1918
        config.openai_api_key = None

        result = generate_html_report(
            alert_level=0,
            alert_enum=AlertLevel.ALL_CLEAR,
            alert_info=alert_info,
            title="All Clear",
            message="No active weather disturbances",
            config=config,
            location_name="Miami, FL"
        )

        assert isinstance(result, str)
        assert result.endswith(".html")
        assert "hurricane_threat_analysis" in result

    def test_generate_html_report_with_storm_data(self) -> None:
        """Test HTML report generation with storm cone data."""
        alert_info = AlertInfo(
            level=AlertLevel.HURRICANE_WARNING,
            icon="🌀",
            color="#B71C1C",
            sound_pattern="emergency",
            title_prefix="HURRICANE WARNING",
            guidance="Hurricane conditions expected within 36 hours."
        )

        config = Mock()
        config.home_lat = 25.7617
        config.home_lon = -80.1918
        config.openai_api_key = None

        # Mock storm cone data
        storm_cone_data = [
            {"coordinates": [[-80.0, 25.0], [-79.0, 26.0], [-78.0, 25.5]]}
        ]

        result = generate_html_report(
            alert_level=5,
            alert_enum=AlertLevel.HURRICANE_WARNING,
            alert_info=alert_info,
            title="Hurricane Warning",
            message="Hurricane conditions expected",
            config=config,
            location_name="Miami, FL",
            storm_cone_data=storm_cone_data
        )

        assert isinstance(result, str)
        assert result.endswith(".html")
        assert "hurricane_threat_analysis" in result
