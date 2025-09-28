# tests/test_ai_web_search.py
"""Tests for AI-powered web search analysis module."""

from unittest.mock import Mock, patch

from weatherbot.ai_web_search import (
    AIWebSearchAnalyzer,
    analyze_weather_threat_web_search,
)


class TestAIWebSearchAnalyzer:
    """Test cases for AIWebSearchAnalyzer class."""

    def test_init(self):
        """Test initialization."""
        with patch('weatherbot.ai_web_search.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            analyzer = AIWebSearchAnalyzer("test-api-key")

            mock_openai.assert_called_once_with(api_key="test-api-key")
            assert analyzer.client == mock_client

    def test_analyze_weather_threat_web_search_success(self):
        """Test successful web search analysis."""
        with patch('weatherbot.ai_web_search.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = """
            ALERT_LEVEL: 2
            TITLE: Weather Watch
            MESSAGE: Potential severe weather conditions detected.
            """
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            analyzer = AIWebSearchAnalyzer("test-key")

            with patch.object(analyzer, '_create_search_queries') as mock_queries:
                with patch.object(analyzer, '_perform_web_searches') as mock_search:
                    mock_queries.return_value = ["test query"]
                    mock_search.return_value = {"test query": "search results"}

                    alert_level, title, message = analyzer.analyze_weather_threat_web_search(
                        latitude=25.0,
                        longitude=-80.0,
                        location_name="Test Location"
                    )

                    assert alert_level == 2
                    assert "Weather Watch" in title
                    assert "severe weather conditions" in message
                    assert "outside NOAA coverage" in message

    def test_analyze_weather_threat_web_search_exception(self):
        """Test web search analysis exception handling."""
        with patch('weatherbot.ai_web_search.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = Exception("API error")
            mock_openai.return_value = mock_client

            analyzer = AIWebSearchAnalyzer("test-key")

            with patch.object(analyzer, '_create_fallback_analysis') as mock_fallback:
                mock_fallback.return_value = (1, "Fallback Alert", "Fallback message")

                alert_level, title, message = analyzer.analyze_weather_threat_web_search(
                    latitude=25.0,
                    longitude=-80.0,
                    location_name="Test Location"
                )

                assert alert_level == 1
                assert title == "Fallback Alert"
                assert message == "Fallback message"

    def test_create_search_queries(self):
        """Test search query creation."""
        analyzer = AIWebSearchAnalyzer("test-key")

        queries = analyzer._create_search_queries("Test Location", 25.0, -80.0)

        assert len(queries) > 0
        assert any("Test Location" in query for query in queries)
        assert any("weather alerts" in query for query in queries)
        assert any("tropical storm" in query for query in queries)
        assert any("hurricane warning" in query for query in queries)

    def test_perform_web_searches_success(self):
        """Test successful web search performance."""
        analyzer = AIWebSearchAnalyzer("test-key")

        with patch.object(analyzer, '_search_web') as mock_search:
            mock_search.return_value = "Search result content"

            queries = ["query1", "query2", "query3"]
            results = analyzer._perform_web_searches(queries)

            assert len(results) <= 5  # Limited to 5 queries
            for query in queries:
                if query in results:
                    assert results[query] == "Search result content"

    def test_perform_web_searches_with_failures(self):
        """Test web search with some failures."""
        analyzer = AIWebSearchAnalyzer("test-key")

        def mock_search_side_effect(query):
            if "fail" in query:
                raise Exception("Search failed")
            return "Success result"

        with patch.object(analyzer, '_search_web') as mock_search:
            mock_search.side_effect = mock_search_side_effect

            queries = ["good_query", "fail_query", "another_good"]
            results = analyzer._perform_web_searches(queries)

            assert "good_query" in results
            assert "fail_query" not in results
            assert "another_good" in results

    def test_search_web_success(self):
        """Test successful individual web search."""
        with patch('weatherbot.ai_web_search.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = "Current weather conditions show no active threats."
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            analyzer = AIWebSearchAnalyzer("test-key")
            result = analyzer._search_web("test weather query")

            assert result == "Current weather conditions show no active threats."

    def test_search_web_short_response(self):
        """Test web search with short response."""
        with patch('weatherbot.ai_web_search.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = "No data"  # Too short
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            analyzer = AIWebSearchAnalyzer("test-key")
            result = analyzer._search_web("test query")

            assert result is None

    def test_search_web_exception(self):
        """Test web search exception handling."""
        with patch('weatherbot.ai_web_search.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = Exception("API error")
            mock_openai.return_value = mock_client

            analyzer = AIWebSearchAnalyzer("test-key")
            result = analyzer._search_web("test query")

            assert result is None

    def test_create_analysis_prompt(self):
        """Test analysis prompt creation."""
        analyzer = AIWebSearchAnalyzer("test-key")

        search_results = {
            "query1": "Weather alert active",
            "query2": "Storm approaching"
        }

        with patch('weatherbot.ai_web_search.datetime') as mock_datetime:
            mock_now = Mock()
            mock_now.strftime.return_value = "2023-09-28 12:00 UTC"
            mock_datetime.now.return_value = mock_now

            prompt = analyzer._create_analysis_prompt(
                "Test Location", 25.0, -80.0, search_results
            )

            assert "Test Location" in prompt
            assert "25.0000°N, -80.0000°W" in prompt
            assert "2023-09-28 12:00 UTC" in prompt
            assert "Weather alert active" in prompt
            assert "Storm approaching" in prompt
            assert "5-LEVEL WEATHER ALERT SYSTEM" in prompt

    def test_create_analysis_prompt_no_results(self):
        """Test analysis prompt with no search results."""
        analyzer = AIWebSearchAnalyzer("test-key")

        with patch('weatherbot.ai_web_search.datetime') as mock_datetime:
            mock_now = Mock()
            mock_now.strftime.return_value = "2023-09-28 12:00 UTC"
            mock_datetime.now.return_value = mock_now

            prompt = analyzer._create_analysis_prompt(
                "Test Location", 25.0, -80.0, {}
            )

            assert "No web search results available" in prompt

    def test_parse_ai_response_complete(self):
        """Test parsing complete AI response."""
        response = """
        ALERT_LEVEL: 3
        TITLE: Severe Weather Warning
        MESSAGE: Dangerous weather conditions expected within 12 hours.
        Take immediate precautions.
        """

        analyzer = AIWebSearchAnalyzer("test-key")
        alert_level, title, message = analyzer._parse_ai_response(response)

        assert alert_level == 3
        assert title == "Severe Weather Warning"
        assert "Dangerous weather conditions" in message
        assert "outside NOAA coverage" in message

    def test_parse_ai_response_minimal(self):
        """Test parsing minimal AI response."""
        response = "ALERT_LEVEL: 1"

        analyzer = AIWebSearchAnalyzer("test-key")
        alert_level, title, message = analyzer._parse_ai_response(response)

        assert alert_level == 1
        assert title == "Level 1 Weather Alert"
        assert message.endswith("outside NOAA coverage areas. For the most accurate forecasts, consult local meteorological services.")

    def test_parse_ai_response_no_level(self):
        """Test parsing response without alert level."""
        response = "Weather conditions are normal"

        analyzer = AIWebSearchAnalyzer("test-key")
        alert_level, title, message = analyzer._parse_ai_response(response)

        assert alert_level == 1
        assert title == "Level 1 Weather Alert"
        assert "Weather conditions are normal" in message

    def test_parse_ai_response_cleanup(self):
        """Test response cleanup."""
        response = """
        ALERT_LEVEL: 2
        TITLE: **Weather Alert**
        MESSAGE: Conditions are ```dangerous``` with **high winds**.
        """

        analyzer = AIWebSearchAnalyzer("test-key")
        alert_level, title, message = analyzer._parse_ai_response(response)

        assert alert_level == 2
        assert title == "Weather Alert"
        assert "dangerous" in message
        assert "high winds" in message
        assert "**" not in message
        assert "```" not in message

    def test_create_fallback_analysis_tropical_region(self):
        """Test fallback analysis for tropical region."""
        analyzer = AIWebSearchAnalyzer("test-key")

        # Coordinates in Atlantic (tropical region)
        alert_level, title, message = analyzer._create_fallback_analysis(
            "Bermuda", 32.3, -64.7, "Network error"
        )

        assert alert_level == 2  # Weather Watch
        assert title == "Weather Monitoring Required"
        assert "tropical cyclones" in message
        assert "Network error" in message

    def test_create_fallback_analysis_non_tropical_region(self):
        """Test fallback analysis for non-tropical region."""
        analyzer = AIWebSearchAnalyzer("test-key")

        # Coordinates outside tropical regions (Northern Europe - clearly non-tropical)
        alert_level, title, message = analyzer._create_fallback_analysis(
            "Stockholm", 65.0, 15.0, "API error"
        )

        assert alert_level == 1  # All Clear
        assert title == "All Clear - Limited Data Available"
        assert "outside typical tropical cyclone regions" in message
        assert "API error" in message

    def test_is_tropical_cyclone_region_atlantic(self):
        """Test tropical cyclone region detection for Atlantic."""
        analyzer = AIWebSearchAnalyzer("test-key")

        # Atlantic/Caribbean coordinates
        assert analyzer._is_tropical_cyclone_region(25.0, -80.0) is True  # Florida
        assert analyzer._is_tropical_cyclone_region(18.0, -66.0) is True  # Puerto Rico
        assert analyzer._is_tropical_cyclone_region(32.0, -64.0) is True  # Bermuda

    def test_is_tropical_cyclone_region_pacific_eastern(self):
        """Test tropical cyclone region detection for Eastern Pacific."""
        analyzer = AIWebSearchAnalyzer("test-key")

        # Eastern Pacific coordinates
        assert analyzer._is_tropical_cyclone_region(20.0, -110.0) is True  # Cabo
        assert analyzer._is_tropical_cyclone_region(15.0, -120.0) is True  # Eastern Pacific

    def test_is_tropical_cyclone_region_indian_ocean(self):
        """Test tropical cyclone region detection for Indian Ocean."""
        analyzer = AIWebSearchAnalyzer("test-key")

        # Indian Ocean coordinates
        assert analyzer._is_tropical_cyclone_region(-20.0, 60.0) is True  # Mauritius area
        assert analyzer._is_tropical_cyclone_region(10.0, 80.0) is True   # Bay of Bengal

    def test_is_tropical_cyclone_region_western_pacific(self):
        """Test tropical cyclone region detection for Western Pacific."""
        analyzer = AIWebSearchAnalyzer("test-key")

        # Western Pacific coordinates
        assert analyzer._is_tropical_cyclone_region(20.0, 140.0) is True  # Philippines area
        assert analyzer._is_tropical_cyclone_region(30.0, 130.0) is True  # Japan area

    def test_is_tropical_cyclone_region_non_tropical(self):
        """Test non-tropical regions."""
        analyzer = AIWebSearchAnalyzer("test-key")

        # Non-tropical coordinates
        assert analyzer._is_tropical_cyclone_region(65.0, -0.1) is False   # Northern Europe
        assert analyzer._is_tropical_cyclone_region(-40.0, -74.0) is False  # Southern Argentina
        assert analyzer._is_tropical_cyclone_region(-33.9, 18.4) is False  # Cape Town
        assert analyzer._is_tropical_cyclone_region(70.0, 37.6) is False   # Arctic

    def test_is_tropical_cyclone_region_edge_cases(self):
        """Test edge cases for tropical region detection."""
        analyzer = AIWebSearchAnalyzer("test-key")

        # Edge coordinates
        assert analyzer._is_tropical_cyclone_region(0.0, -50.0) is True    # Equator Atlantic
        assert analyzer._is_tropical_cyclone_region(60.0, -50.0) is True   # Northern edge
        assert analyzer._is_tropical_cyclone_region(-30.0, 50.0) is True   # Southern edge Indian
        assert analyzer._is_tropical_cyclone_region(61.0, -50.0) is False  # Just outside


class TestAnalyzeWeatherThreatWebSearch:
    """Test cases for analyze_weather_threat_web_search function."""

    def test_analyze_weather_threat_web_search_basic(self):
        """Test basic web search analysis function."""
        with patch('weatherbot.ai_web_search.AIWebSearchAnalyzer') as mock_analyzer_class:
            mock_analyzer = Mock()
            mock_analyzer.analyze_weather_threat_web_search.return_value = (
                2, "Weather Alert", "Severe weather possible"
            )
            mock_analyzer_class.return_value = mock_analyzer

            result = analyze_weather_threat_web_search(
                latitude=25.0,
                longitude=-80.0,
                location_name="Test Location",
                api_key="test-key"
            )

            assert result == (2, "Weather Alert", "Severe weather possible")
            mock_analyzer.analyze_weather_threat_web_search.assert_called_once_with(
                25.0, -80.0, "Test Location"
            )

    def test_analyze_weather_threat_web_search_with_different_params(self):
        """Test web search analysis with different parameters."""
        with patch('weatherbot.ai_web_search.AIWebSearchAnalyzer') as mock_analyzer_class:
            mock_analyzer = Mock()
            mock_analyzer.analyze_weather_threat_web_search.return_value = (
                1, "All Clear", "No threats detected"
            )
            mock_analyzer_class.return_value = mock_analyzer

            result = analyze_weather_threat_web_search(
                latitude=51.5,
                longitude=-0.1,
                location_name="London, UK",
                api_key="different-key"
            )

            assert result == (1, "All Clear", "No threats detected")
            mock_analyzer_class.assert_called_once_with("different-key")


class TestIntegration:
    """Integration tests for AI web search functionality."""

    def test_full_workflow_tropical_region(self):
        """Test full workflow for tropical region."""
        with patch('weatherbot.ai_web_search.OpenAI') as mock_openai:
            mock_client = Mock()

            # Mock search responses
            search_response = Mock()
            search_choice = Mock()
            search_choice.message.content = "Hurricane watch issued for the area"
            search_response.choices = [search_choice]

            # Mock analysis response
            analysis_response = Mock()
            analysis_choice = Mock()
            analysis_choice.message.content = """
            ALERT_LEVEL: 4
            TITLE: Hurricane Watch Active
            MESSAGE: Hurricane conditions possible within 48 hours. Prepare for evacuation.
            """
            analysis_response.choices = [analysis_choice]

            mock_client.chat.completions.create.side_effect = [
                search_response, search_response, search_response, search_response, search_response,  # 5 Search calls
                analysis_response  # Analysis call
            ]
            mock_openai.return_value = mock_client

            analyzer = AIWebSearchAnalyzer("test-key")
            alert_level, title, message = analyzer.analyze_weather_threat_web_search(
                latitude=25.0,
                longitude=-80.0,
                location_name="Miami, FL"
            )

            assert alert_level == 4
            assert "Hurricane Watch Active" in title
            assert "Hurricane conditions possible" in message
            assert "outside NOAA coverage" in message

    def test_full_workflow_non_tropical_region(self):
        """Test full workflow for non-tropical region."""
        with patch('weatherbot.ai_web_search.OpenAI') as mock_openai:
            mock_client = Mock()

            # Mock search responses
            search_response = Mock()
            search_choice = Mock()
            search_choice.message.content = "Normal weather conditions expected"
            search_response.choices = [search_choice]

            # Mock analysis response
            analysis_response = Mock()
            analysis_choice = Mock()
            analysis_choice.message.content = """
            ALERT_LEVEL: 1
            TITLE: All Clear
            MESSAGE: No severe weather threats detected for the area.
            """
            analysis_response.choices = [analysis_choice]

            mock_client.chat.completions.create.side_effect = [
                search_response, search_response, search_response, search_response, search_response,  # 5 Search calls
                analysis_response  # Analysis call
            ]
            mock_openai.return_value = mock_client

            analyzer = AIWebSearchAnalyzer("test-key")
            alert_level, title, message = analyzer.analyze_weather_threat_web_search(
                latitude=51.5,
                longitude=-0.1,
                location_name="London, UK"
            )

            assert alert_level == 1
            assert "All Clear" in title
            assert "No severe weather threats" in message
