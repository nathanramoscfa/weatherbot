# tests/test_ai_enhancer.py
"""Tests for AI-powered storm enhancement module."""

from unittest.mock import Mock, patch

from weatherbot.ai_enhancer import (
    AIStormEnhancer,
    enhance_storm_positions_with_ai,
)


class TestAIStormEnhancer:
    """Test cases for AIStormEnhancer class."""

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            enhancer = AIStormEnhancer("test-api-key")

            mock_openai.assert_called_once_with(api_key="test-api-key")
            assert enhancer.client == mock_client

    def test_init_without_api_key(self):
        """Test initialization without API key."""
        enhancer = AIStormEnhancer()
        assert enhancer.client is None

    def test_init_with_invalid_api_key(self):
        """Test initialization with invalid API key."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_openai.side_effect = Exception("Invalid API key")

            enhancer = AIStormEnhancer("invalid-key")

            assert enhancer.client is None

    def test_get_disturbance_positions_no_client(self):
        """Test getting positions without OpenAI client."""
        enhancer = AIStormEnhancer()

        with patch.object(enhancer, '_get_positions_from_web_search') as mock_fallback:
            mock_fallback.return_value = [{"name": "AL93", "latitude": 23.2}]

            result = enhancer.get_disturbance_positions()

            mock_fallback.assert_called_once()
            assert result == [{"name": "AL93", "latitude": 23.2}]

    def test_get_disturbance_positions_with_client_success(self):
        """Test getting positions with successful AI web search."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            enhancer = AIStormEnhancer("test-key")

            with patch.object(enhancer, '_ai_web_search_storm_positions') as mock_search:
                mock_search.return_value = [{"name": "AL93", "latitude": 23.2}]

                result = enhancer.get_disturbance_positions()

                mock_search.assert_called_once()
                assert result == [{"name": "AL93", "latitude": 23.2}]

    def test_get_disturbance_positions_fallback_to_nhc(self):
        """Test fallback to NHC text analysis when web search fails."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            enhancer = AIStormEnhancer("test-key")

            with patch.object(enhancer, '_ai_web_search_storm_positions') as mock_search:
                with patch.object(enhancer, '_fetch_nhc_text_outlook') as mock_nhc:
                    with patch.object(enhancer, '_extract_positions_with_ai') as mock_extract:
                        mock_search.return_value = []
                        mock_nhc.return_value = "NHC text"
                        mock_extract.return_value = [{"name": "AL94", "latitude": 25.8}]

                        result = enhancer.get_disturbance_positions()

                        mock_search.assert_called_once()
                        mock_nhc.assert_called_once()
                        mock_extract.assert_called_once_with("NHC text")
                        assert result == [{"name": "AL94", "latitude": 25.8}]

    def test_get_disturbance_positions_exception_fallback(self):
        """Test exception handling with fallback to web search."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            enhancer = AIStormEnhancer("test-key")

            with patch.object(enhancer, '_ai_web_search_storm_positions') as mock_search:
                with patch.object(enhancer, '_get_positions_from_web_search') as mock_fallback:
                    mock_search.side_effect = Exception("API error")
                    mock_fallback.return_value = [{"name": "fallback", "latitude": 20.0}]

                    result = enhancer.get_disturbance_positions()

                    mock_fallback.assert_called_once()
                    assert result == [{"name": "fallback", "latitude": 20.0}]

    @patch('weatherbot.ai_enhancer.requests.get')
    def test_fetch_nhc_text_outlook_success(self, mock_get):
        """Test successful NHC text outlook fetch."""
        mock_response = Mock()
        mock_response.text = """
        <html>
        Tropical Weather Outlook
        Some disturbance information here.
        Forecaster Smith
        </html>
        """
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        enhancer = AIStormEnhancer()
        result = enhancer._fetch_nhc_text_outlook()

        assert "Tropical Weather Outlook" in result
        assert "Forecaster" in result
        mock_get.assert_called_once()

    @patch('weatherbot.ai_enhancer.requests.get')
    def test_fetch_nhc_text_outlook_no_markers(self, mock_get):
        """Test NHC text fetch without proper markers."""
        mock_response = Mock()
        mock_response.text = "Some random text without markers"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        enhancer = AIStormEnhancer()
        result = enhancer._fetch_nhc_text_outlook()

        assert len(result) <= 5000
        assert "Some random text" in result

    @patch('weatherbot.ai_enhancer.requests.get')
    def test_fetch_nhc_text_outlook_exception(self, mock_get):
        """Test NHC text fetch exception handling."""
        mock_get.side_effect = Exception("Network error")

        enhancer = AIStormEnhancer()
        result = enhancer._fetch_nhc_text_outlook()

        assert result == ""

    def test_extract_positions_with_ai_success(self):
        """Test successful AI position extraction."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = '''
            [
              {
                "name": "AL93",
                "latitude": 23.5,
                "longitude": -59.2,
                "type": "Tropical Disturbance",
                "probability": "70%"
              }
            ]
            '''
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            enhancer = AIStormEnhancer("test-key")
            result = enhancer._extract_positions_with_ai("NHC text")

            assert len(result) == 1
            assert result[0]["name"] == "AL93"
            assert result[0]["latitude"] == 23.5
            assert result[0]["longitude"] == -59.2

    def test_extract_positions_with_ai_no_json(self):
        """Test AI position extraction with no JSON in response."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = "No JSON data found"
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            enhancer = AIStormEnhancer("test-key")
            result = enhancer._extract_positions_with_ai("NHC text")

            assert result == []

    def test_extract_positions_with_ai_exception(self):
        """Test AI position extraction exception handling."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = Exception("API error")
            mock_openai.return_value = mock_client

            enhancer = AIStormEnhancer("test-key")
            result = enhancer._extract_positions_with_ai("NHC text")

            assert result == []

    def test_ai_web_search_storm_positions_success(self):
        """Test successful AI web search for storm positions."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = '''
            [
              {
                "name": "AL93",
                "latitude": 23.5,
                "longitude": -59.2,
                "type": "Disturbance",
                "probability": "70%"
              }
            ]
            '''
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            enhancer = AIStormEnhancer("test-key")
            result = enhancer._ai_web_search_storm_positions()

            assert len(result) == 1
            assert result[0]["name"] == "AL93"

    def test_ai_web_search_storm_positions_exception(self):
        """Test AI web search exception handling."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = Exception("API error")
            mock_openai.return_value = mock_client

            enhancer = AIStormEnhancer("test-key")
            result = enhancer._ai_web_search_storm_positions()

            assert result == []

    def test_generate_smart_alert_no_client(self):
        """Test smart alert generation without OpenAI client."""
        enhancer = AIStormEnhancer()

        title, message = enhancer.generate_smart_alert(
            alert_level=3,
            storm_names=["Hurricane Test"],
            storm_details=[{"type": "Hurricane"}],
            location="Test Location"
        )

        assert title == "Level 3 Alert"
        assert message == "Monitor weather conditions."

    def test_generate_smart_alert_with_client_success(self):
        """Test successful smart alert generation."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = """
            TITLE: Hurricane Test Approaching
            MESSAGE: Hurricane Test is approaching Test Location.
            Take immediate action to secure property and evacuate if necessary.
            """
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            enhancer = AIStormEnhancer("test-key")
            title, message = enhancer.generate_smart_alert(
                alert_level=4,
                storm_names=["Hurricane Test"],
                storm_details=[{"type": "Hurricane"}],
                location="Test Location"
            )

            assert "Hurricane Test Approaching" in title
            assert "Hurricane Test is approaching" in message

    def test_generate_smart_alert_exception(self):
        """Test smart alert generation exception handling."""
        with patch('weatherbot.ai_enhancer.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = Exception("API error")
            mock_openai.return_value = mock_client

            enhancer = AIStormEnhancer("test-key")
            title, message = enhancer.generate_smart_alert(
                alert_level=3,
                storm_names=["Hurricane Test"],
                storm_details=[{"type": "Hurricane"}],
                location="Test Location"
            )

            assert title == "Level 3 Alert"
            assert "Monitor weather conditions" in message

    def test_get_positions_from_web_search(self):
        """Test fallback web search positions."""
        enhancer = AIStormEnhancer()
        result = enhancer._get_positions_from_web_search()

        assert len(result) == 2
        assert result[0]["name"] == "AL93"
        assert result[0]["latitude"] == 23.2
        assert result[1]["name"] == "AL94"
        assert result[1]["latitude"] == 25.8


class TestEnhanceStormPositionsWithAI:
    """Test cases for enhance_storm_positions_with_ai function."""

    def test_enhance_storm_positions_basic(self):
        """Test basic storm position enhancement."""
        mock_cone = Mock()
        mock_cone.current_position = None
        mock_cone.storm_name = "Tropical Disturbance"

        cones = [mock_cone]

        with patch('weatherbot.ai_enhancer.AIStormEnhancer') as mock_enhancer_class:
            mock_enhancer = Mock()
            mock_enhancer.get_disturbance_positions.return_value = [
                {
                    "name": "AL93",
                    "latitude": 23.5,
                    "longitude": -59.2,
                    "type": "Tropical Disturbance",
                    "probability": "70%"
                }
            ]
            mock_enhancer_class.return_value = mock_enhancer

            result = enhance_storm_positions_with_ai(cones, "test-key")

            assert len(result) == 1
            assert result[0].current_position == (23.5, -59.2)
            assert result[0].storm_id == "AL93"
            assert result[0].advisory_num == "70%"

    def test_enhance_storm_positions_no_match(self):
        """Test enhancement with no matching AI positions."""
        mock_cone = Mock()
        mock_cone.current_position = None
        mock_cone.storm_name = "Hurricane Test"

        cones = [mock_cone]

        with patch('weatherbot.ai_enhancer.AIStormEnhancer') as mock_enhancer_class:
            mock_enhancer = Mock()
            mock_enhancer.get_disturbance_positions.return_value = []
            mock_enhancer_class.return_value = mock_enhancer

            result = enhance_storm_positions_with_ai(cones, "test-key")

            assert len(result) == 1
            assert result[0].current_position is None

    def test_enhance_storm_positions_existing_position(self):
        """Test enhancement with existing position (no change)."""
        mock_cone = Mock()
        mock_cone.current_position = (25.0, -60.0)
        mock_cone.storm_name = "Tropical Disturbance"

        cones = [mock_cone]

        with patch('weatherbot.ai_enhancer.AIStormEnhancer') as mock_enhancer_class:
            mock_enhancer = Mock()
            mock_enhancer.get_disturbance_positions.return_value = [
                {
                    "name": "AL93",
                    "latitude": 23.5,
                    "longitude": -59.2,
                    "type": "Tropical Disturbance"
                }
            ]
            mock_enhancer_class.return_value = mock_enhancer

            result = enhance_storm_positions_with_ai(cones, "test-key")

            assert len(result) == 1
            assert result[0].current_position == (25.0, -60.0)  # Unchanged

    def test_enhance_storm_positions_no_api_key(self):
        """Test enhancement without API key."""
        mock_cone = Mock()
        mock_cone.current_position = None
        mock_cone.storm_name = "Tropical Disturbance"

        cones = [mock_cone]

        result = enhance_storm_positions_with_ai(cones, None)

        assert len(result) == 1
        # Without API key, fallback method should still provide positions for disturbances
        assert result[0].current_position is not None
        assert result[0].current_position == (23.2, -59.7)  # From fallback data
