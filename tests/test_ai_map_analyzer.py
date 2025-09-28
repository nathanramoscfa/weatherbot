# tests/test_ai_map_analyzer.py
"""Tests for AI-powered map analysis module."""

from unittest.mock import Mock, patch

from weatherbot.ai_map_analyzer import (
    NOAA_MAP_URLS,
    AIMapAnalyzer,
    analyze_hurricane_threat_with_ai,
)


class TestAIMapAnalyzer:
    """Test cases for AIMapAnalyzer class."""

    def test_init(self):
        """Test initialization."""
        with patch('weatherbot.ai_map_analyzer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            analyzer = AIMapAnalyzer("test-api-key")

            mock_openai.assert_called_once_with(api_key="test-api-key")
            assert analyzer.client == mock_client

    def test_analyze_threat_for_location_success(self):
        """Test successful threat analysis."""
        with patch('weatherbot.ai_map_analyzer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = """
            ALERT_LEVEL: 2
            TITLE: Tropical Storm Threat
            MESSAGE: Current conditions show potential tropical storm development.
            """
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            analyzer = AIMapAnalyzer("test-key")

            with patch.object(analyzer, '_get_nhc_text_context') as mock_context:
                mock_context.return_value = "NHC context"

                alert_level, title, message = analyzer.analyze_threat_for_location(
                    latitude=25.0,
                    longitude=-80.0,
                    location_name="Miami, FL"
                )

                assert alert_level == 2
                assert "Tropical Storm Threat" in title
                assert "tropical storm development" in message

    def test_analyze_threat_for_location_with_geometric_results(self):
        """Test threat analysis with geometric results."""
        with patch('weatherbot.ai_map_analyzer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = """
            ALERT_LEVEL: 3
            TITLE: Hurricane Watch
            MESSAGE: Hurricane conditions possible within 48 hours.
            """
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            analyzer = AIMapAnalyzer("test-key")

            geometric_results = {
                "is_in_any_cone": True,
                "nws_alerts": [],
                "storm_threats": []
            }

            with patch.object(analyzer, '_get_nhc_text_context') as mock_context:
                with patch.object(analyzer, '_format_geometric_context') as mock_format:
                    mock_context.return_value = "NHC context"
                    mock_format.return_value = "Geometric context"

                    alert_level, title, _message = analyzer.analyze_threat_for_location(
                        latitude=25.0,
                        longitude=-80.0,
                        location_name="Miami, FL",
                        geometric_results=geometric_results
                    )

                    assert alert_level == 3
                    assert "Hurricane Watch" in title

    def test_analyze_threat_for_location_override_with_nws_alerts(self):
        """Test that NWS alerts take precedence over geometric analysis."""
        with patch('weatherbot.ai_map_analyzer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = """
            ALERT_LEVEL: 4
            TITLE: Hurricane Warning
            MESSAGE: Hurricane conditions expected within 36 hours.
            """
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            analyzer = AIMapAnalyzer("test-key")

            # Mock NWS alert
            mock_alert = Mock()
            mock_alert.event = "Hurricane Warning"

            geometric_results = {
                "is_in_any_cone": False,  # Not in cone
                "nws_alerts": [mock_alert],  # But has NWS alert
                "storm_threats": []
            }

            with patch.object(analyzer, '_get_nhc_text_context') as mock_context:
                with patch.object(analyzer, '_format_geometric_context') as mock_format:
                    mock_context.return_value = "NHC context"
                    mock_format.return_value = "Geometric context"

                    alert_level, title, _message = analyzer.analyze_threat_for_location(
                        latitude=25.0,
                        longitude=-80.0,
                        location_name="Miami, FL",
                        geometric_results=geometric_results
                    )

                    # Should not be overridden because NWS alerts take precedence
                    assert alert_level == 4
                    assert "Hurricane Warning" in title

    def test_analyze_threat_for_location_override_without_nws_alerts(self):
        """Test geometric override when not in cone and no NWS alerts."""
        with patch('weatherbot.ai_map_analyzer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = """
            ALERT_LEVEL: 3
            TITLE: Hurricane Threat
            MESSAGE: Hurricane conditions possible.
            """
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            analyzer = AIMapAnalyzer("test-key")

            geometric_results = {
                "is_in_any_cone": False,  # Not in cone
                "nws_alerts": [],  # No NWS alerts
                "storm_threats": []
            }

            with patch.object(analyzer, '_get_nhc_text_context') as mock_context:
                with patch.object(analyzer, '_format_geometric_context') as mock_format:
                    mock_context.return_value = "NHC context"
                    mock_format.return_value = "Geometric context"

                    alert_level, title, _message = analyzer.analyze_threat_for_location(
                        latitude=25.0,
                        longitude=-80.0,
                        location_name="Miami, FL",
                        geometric_results=geometric_results
                    )

                    # Should be overridden to Level 1
                    assert alert_level == 1
                    assert "All Clear" in title

    def test_analyze_threat_for_location_different_basin(self):
        """Test threat analysis for different basin."""
        with patch('weatherbot.ai_map_analyzer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = """
            ALERT_LEVEL: 2
            TITLE: Pacific Storm Threat
            MESSAGE: Eastern Pacific storm developing.
            """
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            analyzer = AIMapAnalyzer("test-key")

            with patch.object(analyzer, '_get_nhc_text_context') as mock_context:
                mock_context.return_value = "Pacific NHC context"

                alert_level, title, _message = analyzer.analyze_threat_for_location(
                    latitude=20.0,
                    longitude=-110.0,
                    location_name="Cabo San Lucas",
                    basin="eastern_pacific"
                )

                assert alert_level == 2
                assert "Pacific Storm Threat" in title

    def test_analyze_threat_for_location_exception(self):
        """Test exception handling in threat analysis."""
        with patch('weatherbot.ai_map_analyzer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = Exception("API error")
            mock_openai.return_value = mock_client

            analyzer = AIMapAnalyzer("test-key")

            alert_level, title, message = analyzer.analyze_threat_for_location(
                latitude=25.0,
                longitude=-80.0,
                location_name="Miami, FL"
            )

            assert alert_level == 1
            assert title == "System Error"
            assert "Unable to analyze hurricane threat" in message

    @patch('weatherbot.ai_map_analyzer.requests.get')
    def test_get_nhc_text_context_success(self, mock_get):
        """Test successful NHC text context retrieval."""
        mock_response = Mock()
        mock_response.text = """
        <html>
        Active Systems:
        Hurricane Test - Category 2
        Forecaster Smith
        </html>
        """
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        analyzer = AIMapAnalyzer("test-key")
        result = analyzer._get_nhc_text_context()

        assert "ACTIVE SYSTEMS:" in result
        assert "Hurricane Test" in result

    @patch('weatherbot.ai_map_analyzer.requests.get')
    def test_get_nhc_text_context_with_current_storms(self, mock_get):
        """Test NHC context with CurrentStorms.json data."""
        # Mock main request
        mock_response = Mock()
        mock_response.text = "Active Systems: Test"
        mock_response.raise_for_status.return_value = None

        # Mock CurrentStorms.json request
        mock_storms_response = Mock()
        mock_storms_response.status_code = 200
        mock_storms_response.json.return_value = {
            "activeStorms": [
                {
                    "isActive": True,
                    "name": "Hurricane Test",
                    "classification": "Hurricane",
                    "intensity": "Category 2",
                    "movement": "NW at 15 mph"
                }
            ]
        }

        mock_get.side_effect = [mock_response, mock_storms_response]

        analyzer = AIMapAnalyzer("test-key")
        result = analyzer._get_nhc_text_context()

        assert "DETAILED STORM INFO:" in result
        assert "Hurricane Test: Hurricane, Category 2, NW at 15 mph" in result

    @patch('weatherbot.ai_map_analyzer.requests.get')
    def test_get_nhc_text_context_exception(self, mock_get):
        """Test NHC context exception handling."""
        mock_get.side_effect = Exception("Network error")

        analyzer = AIMapAnalyzer("test-key")
        result = analyzer._get_nhc_text_context()

        assert "NHC context unavailable" in result

    def test_parse_ai_response_complete(self):
        """Test parsing complete AI response."""
        response = """
        ALERT_LEVEL: 3
        TITLE: Hurricane Watch Issued
        MESSAGE: Hurricane conditions are possible within 48 hours.
        Take immediate preparations.
        """

        analyzer = AIMapAnalyzer("test-key")
        alert_level, title, message = analyzer._parse_ai_response(response)

        assert alert_level == 3
        assert title == "Hurricane Watch Issued"
        assert "Hurricane conditions are possible" in message

    def test_parse_ai_response_minimal(self):
        """Test parsing minimal AI response."""
        response = "ALERT_LEVEL: 2"

        analyzer = AIMapAnalyzer("test-key")
        alert_level, title, message = analyzer._parse_ai_response(response)

        assert alert_level == 2
        assert title == "Level 2 Alert"
        assert message == "ALERT_LEVEL: 2"

    def test_parse_ai_response_no_level(self):
        """Test parsing response without alert level."""
        response = "Some random response without level"

        analyzer = AIMapAnalyzer("test-key")
        alert_level, title, message = analyzer._parse_ai_response(response)

        assert alert_level == 1
        assert title == "Level 1 Alert"
        assert message == "Some random response without level"

    def test_parse_ai_response_markdown_cleanup(self):
        """Test markdown cleanup in response parsing."""
        response = """
        ALERT_LEVEL: 2
        TITLE: **Hurricane Threat**
        MESSAGE: Hurricane conditions ```possible``` within **48 hours**.
        ```
        """

        analyzer = AIMapAnalyzer("test-key")
        alert_level, title, message = analyzer._parse_ai_response(response)

        assert alert_level == 2
        assert title == "Hurricane Threat"
        assert "Hurricane conditions possible within 48 hours." in message
        assert "```" not in message
        assert "**" not in message

    def test_format_geometric_context_complete(self):
        """Test formatting complete geometric context."""
        mock_alert_level = Mock()
        mock_alert_level.name = "TROPICAL_STORM_THREAT"
        mock_alert_level.value = 2

        mock_threat = Mock()
        mock_threat.cone.storm_name = "Hurricane Test"
        mock_threat.category.value = "Category 2"
        mock_threat.distance_km = 150.0
        mock_threat.confidence = 0.85

        mock_nws_alert = Mock()
        mock_nws_alert.event = "Hurricane Watch"

        geometric_results = {
            "alert_level": mock_alert_level,
            "is_in_any_cone": True,
            "storm_threats": [mock_threat],
            "nws_alerts": [mock_nws_alert],
            "total_storms_analyzed": 3
        }

        analyzer = AIMapAnalyzer("test-key")
        result = analyzer._format_geometric_context(geometric_results)

        assert "PRECISE GEOMETRIC ANALYSIS RESULTS:" in result
        assert "Geometric Alert Level: TROPICAL_STORM_THREAT (Level 2)" in result
        assert "Location in any forecast cone: True" in result
        assert "Hurricane Test (Category 2)" in result
        assert "Hurricane Watch" in result
        assert "Total storms analyzed: 3" in result

    def test_format_geometric_context_outside_cone(self):
        """Test formatting context when outside cone."""
        geometric_results = {
            "is_in_any_cone": False,
            "nws_alerts": [],
            "storm_threats": [],
            "total_storms_analyzed": 2
        }

        analyzer = AIMapAnalyzer("test-key")
        result = analyzer._format_geometric_context(geometric_results)

        assert "Location in any forecast cone: False" in result
        assert "Do NOT claim the location is 'within the forecast cone'" in result
        assert "CRITICAL: Do NOT claim" in result

    def test_format_geometric_context_with_nws_alerts(self):
        """Test formatting context with NWS alerts."""
        mock_nws_alert = Mock()
        mock_nws_alert.event = "Hurricane Warning"

        geometric_results = {
            "is_in_any_cone": True,
            "nws_alerts": [mock_nws_alert],
            "storm_threats": [],
            "total_storms_analyzed": 1
        }

        analyzer = AIMapAnalyzer("test-key")
        result = analyzer._format_geometric_context(geometric_results)

        assert "NWS ALERTS PRESENT" in result
        assert "OFFICIAL WARNINGS TAKE ABSOLUTE PRECEDENCE" in result
        assert "Do NOT override official NWS alerts" in result

    def test_format_geometric_context_empty(self):
        """Test formatting empty geometric context."""
        analyzer = AIMapAnalyzer("test-key")
        result = analyzer._format_geometric_context({})

        assert result == ""

    def test_format_geometric_context_none(self):
        """Test formatting None geometric context."""
        analyzer = AIMapAnalyzer("test-key")
        result = analyzer._format_geometric_context(None)

        assert result == ""


class TestAnalyzeHurricaneThreatWithAI:
    """Test cases for analyze_hurricane_threat_with_ai function."""

    def test_analyze_hurricane_threat_basic(self):
        """Test basic hurricane threat analysis."""
        with patch('weatherbot.ai_map_analyzer.AIMapAnalyzer') as mock_analyzer_class:
            mock_analyzer = Mock()
            mock_analyzer.analyze_threat_for_location.return_value = (
                3, "Hurricane Watch", "Hurricane conditions possible"
            )
            mock_analyzer_class.return_value = mock_analyzer

            result = analyze_hurricane_threat_with_ai(
                latitude=25.0,
                longitude=-80.0,
                location_name="Miami, FL",
                api_key="test-key"
            )

            assert result == (3, "Hurricane Watch", "Hurricane conditions possible")
            mock_analyzer.analyze_threat_for_location.assert_called_once_with(
                25.0, -80.0, "Miami, FL", "atlantic", None
            )

    def test_analyze_hurricane_threat_with_geometric_results(self):
        """Test analysis with geometric results."""
        with patch('weatherbot.ai_map_analyzer.AIMapAnalyzer') as mock_analyzer_class:
            mock_analyzer = Mock()
            mock_analyzer.analyze_threat_for_location.return_value = (
                2, "Tropical Storm Threat", "Storm developing"
            )
            mock_analyzer_class.return_value = mock_analyzer

            geometric_results = {"is_in_any_cone": True}

            result = analyze_hurricane_threat_with_ai(
                latitude=25.0,
                longitude=-80.0,
                location_name="Miami, FL",
                api_key="test-key",
                basin="eastern_pacific",
                geometric_results=geometric_results
            )

            assert result == (2, "Tropical Storm Threat", "Storm developing")
            mock_analyzer.analyze_threat_for_location.assert_called_once_with(
                25.0, -80.0, "Miami, FL", "eastern_pacific", geometric_results
            )


class TestNOAAMapURLs:
    """Test cases for NOAA map URLs configuration."""

    def test_noaa_map_urls_structure(self):
        """Test NOAA map URLs have correct structure."""
        assert "atlantic" in NOAA_MAP_URLS
        assert "eastern_pacific" in NOAA_MAP_URLS
        assert "central_pacific" in NOAA_MAP_URLS

        for _basin, urls in NOAA_MAP_URLS.items():
            assert "7day" in urls
            assert "2day" in urls
            assert "text" in urls
            assert urls["7day"].startswith("https://")
            assert urls["2day"].startswith("https://")
            assert urls["text"].startswith("https://")

    def test_noaa_map_urls_atlantic(self):
        """Test Atlantic basin URLs."""
        atlantic_urls = NOAA_MAP_URLS["atlantic"]
        assert "two_atl_7d0.png" in atlantic_urls["7day"]
        assert "two_atl_2d0.png" in atlantic_urls["2day"]
        assert "basin=atlc" in atlantic_urls["text"]

    def test_noaa_map_urls_eastern_pacific(self):
        """Test Eastern Pacific basin URLs."""
        epac_urls = NOAA_MAP_URLS["eastern_pacific"]
        assert "two_epac_7d0.png" in epac_urls["7day"]
        assert "two_epac_2d0.png" in epac_urls["2day"]
        assert "basin=epac" in epac_urls["text"]

    def test_noaa_map_urls_central_pacific(self):
        """Test Central Pacific basin URLs."""
        cpac_urls = NOAA_MAP_URLS["central_pacific"]
        assert "two_cpac_7d0.png" in cpac_urls["7day"]
        assert "two_cpac_2d0.png" in cpac_urls["2day"]
        assert "basin=cpac" in cpac_urls["text"]
