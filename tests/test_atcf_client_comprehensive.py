# tests/test_atcf_client_comprehensive.py
"""Comprehensive tests for ATCF client module."""

from unittest.mock import Mock, patch

import pytest
import requests

from weatherbot.atcf_client import (
    ATCF_BASE,
    ATCF_BTK,
    INVEST_FILE_RE,
    ATCFClient,
    get_atcf_invest_positions,
)


class TestATCFClient:
    """Test cases for ATCFClient class."""

    def test_init_default(self):
        """Test default initialization."""
        client = ATCFClient()

        assert client.timeout == 30
        assert client.session is not None

    def test_init_custom_timeout(self):
        """Test initialization with custom timeout."""
        client = ATCFClient(timeout=60)

        assert client.timeout == 60

    @patch('weatherbot.atcf_client.requests.Session.get')
    def test_make_request_success(self, mock_get):
        """Test successful HTTP request."""
        mock_response = Mock()
        mock_response.text = "ATCF data content"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = ATCFClient()
        result = client._make_request("https://test.url")

        assert result == "ATCF data content"
        mock_get.assert_called_once()

    @patch('weatherbot.atcf_client.requests.Session.get')
    def test_make_request_cached(self, mock_get):
        """Test cached HTTP request."""
        # First request
        mock_response = Mock()
        mock_response.text = "ATCF data content"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = ATCFClient()

        # Clear cache first
        from weatherbot.cache import api_cache
        api_cache.clear()

        # First call should make request
        result1 = client._make_request("https://test.url")

        # Second call should use cache
        result2 = client._make_request("https://test.url")

        assert result1 == result2
        assert mock_get.call_count == 1  # Only called once

    @patch('weatherbot.atcf_client.requests.Session.get')
    @patch('weatherbot.atcf_client.api_cache')
    def test_make_request_exception(self, mock_cache, mock_get):
        """Test HTTP request exception handling with retry exhaustion."""
        mock_cache.get.return_value = None  # No cached data
        mock_get.side_effect = requests.RequestException("Network error")

        client = ATCFClient()

        # The retry mechanism will eventually raise a RetryError
        from tenacity import RetryError
        with pytest.raises(RetryError):
            client._make_request("https://test.url")

    @patch.object(ATCFClient, '_make_request')
    def test_get_invest_files_success(self, mock_request):
        """Test successful invest files retrieval."""
        mock_html = '''
        <html>
        <body>
        <a href="bal932023.dat">bal932023.dat</a>
        <a href="bal942023.dat">bal942023.dat</a>
        <a href="bep952023.dat">bep952023.dat</a>
        <a href="other_file.txt">other_file.txt</a>
        </body>
        </html>
        '''
        mock_request.return_value = mock_html

        client = ATCFClient()
        result = client.get_invest_files()

        assert len(result) == 3
        assert any("bal932023.dat" in url for url in result)
        assert any("bal942023.dat" in url for url in result)
        assert any("bep952023.dat" in url for url in result)

    @patch.object(ATCFClient, '_make_request')
    def test_get_invest_files_no_matches(self, mock_request):
        """Test invest files retrieval with no matches."""
        mock_html = '''
        <html>
        <body>
        <a href="other_file.txt">other_file.txt</a>
        <a href="another_file.dat">another_file.dat</a>
        </body>
        </html>
        '''
        mock_request.return_value = mock_html

        client = ATCFClient()
        result = client.get_invest_files()

        assert result == []

    @patch.object(ATCFClient, '_make_request')
    def test_get_invest_files_exception(self, mock_request):
        """Test invest files retrieval exception handling."""
        mock_request.side_effect = Exception("Request error")

        client = ATCFClient()
        result = client.get_invest_files()

        assert result == []

    @patch.object(ATCFClient, '_make_request')
    @patch.object(ATCFClient, '_parse_atcf_text')
    def test_parse_atcf_file_success(self, mock_parse, mock_request):
        """Test successful ATCF file parsing."""
        mock_request.return_value = "ATCF file content"
        mock_parse.return_value = [{"lat": 23.5, "lon": -59.2}]

        client = ATCFClient()
        result = client.parse_atcf_file("https://test.url/bal932023.dat")

        assert result == [{"lat": 23.5, "lon": -59.2}]
        mock_request.assert_called_once_with("https://test.url/bal932023.dat")
        mock_parse.assert_called_once_with("ATCF file content", "https://test.url/bal932023.dat")

    @patch.object(ATCFClient, '_make_request')
    def test_parse_atcf_file_exception(self, mock_request):
        """Test ATCF file parsing exception handling."""
        mock_request.side_effect = Exception("Parse error")

        client = ATCFClient()
        result = client.parse_atcf_file("https://test.url/bal932023.dat")

        assert result == []

    def test_parse_atcf_text_success(self):
        """Test successful ATCF text parsing."""
        atcf_text = """
        AL, 93, 2023092912,   , BEST,   0, 235N,  597W,  25, 1008, DB,   0,    ,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    L,   0,    ,   0,   0,     INVEST, D, 0,    ,    0,    0,    0,    0, genesis-num, 001,
        AL, 93, 2023092918,   , BEST,   0, 240N,  595W,  30, 1006, DB,   0,    ,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    L,   0,    ,   0,   0,     INVEST, D, 0,    ,    0,    0,    0,    0, genesis-num, 002,
        """

        client = ATCFClient()
        result = client._parse_atcf_text(atcf_text, "test_url")

        assert len(result) == 2
        assert result[0]["lat"] == 23.5
        assert result[0]["lon"] == -59.7
        assert result[0]["wind_kt"] == 25
        assert result[0]["pressure_mb"] == 1008
        assert result[0]["invest_id"] == "AL93"
        assert result[1]["lat"] == 24.0
        assert result[1]["lon"] == -59.5
        assert result[1]["wind_kt"] == 30
        assert result[1]["pressure_mb"] == 1006

    def test_parse_atcf_text_empty(self):
        """Test ATCF text parsing with empty content."""
        client = ATCFClient()
        result = client._parse_atcf_text("", "test_url")

        assert result == []

    def test_parse_atcf_text_comments_only(self):
        """Test ATCF text parsing with comments only."""
        atcf_text = """
        # This is a comment
        # Another comment
        """

        client = ATCFClient()
        result = client._parse_atcf_text(atcf_text, "test_url")

        assert result == []

    def test_parse_atcf_text_insufficient_fields(self):
        """Test ATCF text parsing with insufficient fields."""
        atcf_text = "AL, 93, 2023092912"  # Not enough fields

        client = ATCFClient()
        result = client._parse_atcf_text(atcf_text, "test_url")

        assert result == []

    def test_parse_atcf_text_invalid_coordinates(self):
        """Test ATCF text parsing with invalid coordinates."""
        atcf_text = "AL, 93, 2023092912,   , BEST,   0, XXXN,  XXXW,  25, 1008, DB,   0,    ,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    L,   0,    ,   0,   0,     INVEST, D, 0,    ,    0,    0,    0,    0, genesis-num, 001,"

        client = ATCFClient()
        result = client._parse_atcf_text(atcf_text, "test_url")

        assert result == []

    def test_parse_coordinate_north_positive(self):
        """Test coordinate parsing for north positive."""
        client = ATCFClient()

        result = client._atcf_coord_to_float("235N")
        assert result == 23.5

    def test_parse_coordinate_south_negative(self):
        """Test coordinate parsing for south negative."""
        client = ATCFClient()

        result = client._atcf_coord_to_float("235S")
        assert result == -23.5

    def test_parse_coordinate_east_positive(self):
        """Test coordinate parsing for east positive."""
        client = ATCFClient()

        result = client._atcf_coord_to_float("1200E")
        assert result == 120.0

    def test_parse_coordinate_west_negative(self):
        """Test coordinate parsing for west negative."""
        client = ATCFClient()

        result = client._atcf_coord_to_float("597W")
        assert result == -59.7

    def test_parse_coordinate_invalid(self):
        """Test coordinate parsing with invalid format."""
        client = ATCFClient()

        result = client._atcf_coord_to_float("INVALID")
        assert result is None

    def test_parse_coordinate_empty(self):
        """Test coordinate parsing with empty string."""
        client = ATCFClient()

        result = client._atcf_coord_to_float("")
        assert result is None

    def test_atcf_coord_to_float_missing_value(self):
        """Test coordinate parsing for missing value (-999)."""
        client = ATCFClient()

        result = client._atcf_coord_to_float("-999")
        assert result is None

    @patch.object(ATCFClient, 'get_invest_files')
    @patch.object(ATCFClient, 'parse_atcf_file')
    def test_get_all_invest_positions_success(self, mock_parse, mock_get_files):
        """Test successful retrieval of all invest positions."""
        mock_get_files.return_value = [
            "https://test.url/bal932023.dat",
            "https://test.url/bal942023.dat"
        ]

        mock_parse.side_effect = [
            [{"invest_id": "AL93", "lat": 23.5, "lon": -59.7, "timestamp": "2023-09-29T12:00:00Z", "tau": 0}],
            [{"invest_id": "AL94", "lat": 25.0, "lon": -80.0, "timestamp": "2023-09-29T18:00:00Z", "tau": 0}]
        ]

        client = ATCFClient()
        result = client.get_current_invest_positions()

        assert len(result) == 2
        assert "AL93" in result
        assert result["AL93"] == (23.5, -59.7)
        assert "AL94" in result
        assert result["AL94"] == (25.0, -80.0)

    @patch.object(ATCFClient, 'get_invest_files')
    def test_get_all_invest_positions_no_files(self, mock_get_files):
        """Test invest positions retrieval with no files."""
        mock_get_files.return_value = []

        client = ATCFClient()
        result = client.get_current_invest_positions()

        assert result == {}

    @patch.object(ATCFClient, 'get_invest_files')
    @patch.object(ATCFClient, 'parse_atcf_file')
    def test_get_all_invest_positions_empty_tracks(self, mock_parse, mock_get_files):
        """Test invest positions retrieval with empty tracks."""
        mock_get_files.return_value = ["https://test.url/bal932023.dat"]
        mock_parse.return_value = []

        client = ATCFClient()
        result = client.get_current_invest_positions()

        assert result == {}



class TestInvestFileRegex:
    """Test cases for invest file regex pattern."""

    def test_invest_file_regex_atlantic_valid(self):
        """Test regex matching for valid Atlantic invest files."""
        valid_files = [
            "bal932023.dat",
            "BAL942023.DAT",
            "bal952023.dat",
            "bal992023.dat"
        ]

        for filename in valid_files:
            assert INVEST_FILE_RE.search(filename) is not None

    def test_invest_file_regex_pacific_valid(self):
        """Test regex matching for valid Pacific invest files."""
        valid_files = [
            "bep902023.dat",
            "BEP952023.DAT",
            "bcp962023.dat",
            "BCP992023.DAT"
        ]

        for filename in valid_files:
            assert INVEST_FILE_RE.search(filename) is not None

    def test_invest_file_regex_invalid(self):
        """Test regex non-matching for invalid files."""
        invalid_files = [
            "bal012023.dat",  # Not invest number (01)
            "bal892023.dat",  # Not invest number (89)
            "bwp932023.dat",  # Invalid basin (wp)
            "al932023.dat",   # Missing 'b' prefix
            "bal932023.txt",  # Wrong extension
            "other_file.dat", # Completely different
            "bal93.dat"       # Missing year
        ]

        for filename in invalid_files:
            assert INVEST_FILE_RE.search(filename) is None


class TestGetAtcfInvestPositions:
    """Test cases for get_atcf_invest_positions function."""

    @patch('weatherbot.atcf_client.ATCFClient')
    def test_get_atcf_invest_positions_success(self, mock_client_class):
        """Test successful ATCF invest positions retrieval."""
        mock_client = Mock()
        mock_client.get_current_invest_positions.return_value = {
            "AL93": (23.5, -59.7)
        }
        mock_client_class.return_value = mock_client

        result = get_atcf_invest_positions()

        assert len(result) == 1
        assert "AL93" in result
        assert result["AL93"] == (23.5, -59.7)

    @patch('weatherbot.atcf_client.ATCFClient')
    def test_get_atcf_invest_positions_empty(self, mock_client_class):
        """Test ATCF invest positions retrieval with no positions."""
        mock_client = Mock()
        mock_client.get_current_invest_positions.return_value = {}
        mock_client_class.return_value = mock_client

        result = get_atcf_invest_positions()

        assert result == {}

    @patch('weatherbot.atcf_client.ATCFClient')
    def test_get_atcf_invest_positions_exception(self, mock_client_class):
        """Test ATCF invest positions retrieval exception handling."""
        mock_client = Mock()
        mock_client.get_current_invest_positions.side_effect = Exception("ATCF error")
        mock_client_class.return_value = mock_client

        with pytest.raises(Exception, match="ATCF error"):
            get_atcf_invest_positions()


class TestConstants:
    """Test cases for module constants."""

    def test_atcf_base_url(self):
        """Test ATCF base URL."""
        assert ATCF_BASE == "https://ftp.nhc.noaa.gov/atcf/"

    def test_atcf_btk_url(self):
        """Test ATCF BTK URL."""
        assert ATCF_BTK == "https://ftp.nhc.noaa.gov/atcf/btk/"

    def test_request_timeout(self):
        """Test request timeout constant."""
        from weatherbot.atcf_client import REQUEST_TIMEOUT
        assert REQUEST_TIMEOUT == 30


class TestIntegration:
    """Integration tests for ATCF client functionality."""

    @patch('weatherbot.atcf_client.requests.Session.get')
    def test_full_workflow_success(self, mock_get):
        """Test full ATCF workflow from file discovery to position extraction."""
        # Mock directory listing response
        directory_response = Mock()
        directory_response.text = '''
        <html>
        <body>
        <a href="bal932023.dat">bal932023.dat</a>
        <a href="bal942023.dat">bal942023.dat</a>
        </body>
        </html>
        '''
        directory_response.raise_for_status.return_value = None

        # Mock ATCF file content
        atcf_content_93 = """
        AL, 93, 2023092912,   , BEST,   0, 235N,  597W,  25, 1008, DB,   0,    ,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    L,   0,    ,   0,   0,     INVEST, D, 0,    ,    0,    0,    0,    0, genesis-num, 001,
        AL, 93, 2023092918,   , BEST,   0, 240N,  595W,  30, 1006, DB,   0,    ,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    L,   0,    ,   0,   0,     INVEST, D, 0,    ,    0,    0,    0,    0, genesis-num, 002,
        """

        atcf_content_94 = """
        AL, 94, 2023092912,   , BEST,   0, 258N,  741W,  20, 1010, DB,   0,    ,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    0,    L,   0,    ,   0,   0,     INVEST, D, 0,    ,    0,    0,    0,    0, genesis-num, 001,
        """

        file_response_93 = Mock()
        file_response_93.text = atcf_content_93
        file_response_93.raise_for_status.return_value = None

        file_response_94 = Mock()
        file_response_94.text = atcf_content_94
        file_response_94.raise_for_status.return_value = None

        # Configure mock to return different responses based on URL
        def mock_get_side_effect(url, **kwargs):
            if url.endswith("btk/"):  # Directory listing
                return directory_response
            if "bal932023.dat" in url:
                return file_response_93
            if "bal942023.dat" in url:
                return file_response_94
            raise requests.RequestException(f"Unknown URL: {url}")

        mock_get.side_effect = mock_get_side_effect

        # Clear cache to ensure fresh requests
        from weatherbot.cache import api_cache
        api_cache.clear()

        # Run the full workflow
        result = get_atcf_invest_positions()

        # Verify results
        assert len(result) == 2

        # Check AL93 data (latest position from the ATCF data)
        assert "AL93" in result
        assert result["AL93"] == (24.0, -59.5)  # Latest position

        # Check AL94 data
        assert "AL94" in result
        assert result["AL94"] == (25.8, -74.1)

    @patch('weatherbot.atcf_client.requests.Session.get')
    def test_full_workflow_no_files(self, mock_get):
        """Test full workflow with no invest files available."""
        # Mock empty directory listing
        directory_response = Mock()
        directory_response.text = '''
        <html>
        <body>
        <a href="other_file.txt">other_file.txt</a>
        </body>
        </html>
        '''
        directory_response.raise_for_status.return_value = None
        mock_get.return_value = directory_response

        # Clear cache
        from weatherbot.cache import api_cache
        api_cache.clear()

        result = get_atcf_invest_positions()

        assert result == {}

    @patch('weatherbot.atcf_client.requests.Session.get')
    def test_full_workflow_network_error(self, mock_get):
        """Test full workflow with network error."""
        mock_get.side_effect = requests.RequestException("Network error")

        result = get_atcf_invest_positions()

        assert result == {}
