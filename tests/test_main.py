# tests/test_main.py
"""Main module tests for weatherbot."""

from unittest.mock import patch

from weatherbot.__main__ import app


class TestMain:
    """Test main module functionality."""

    def test_app_import(self) -> None:
        """Test that app can be imported."""
        from weatherbot.__main__ import app
        assert app is not None

    @patch('weatherbot.__main__.app')
    def test_main_execution(self, mock_app) -> None:
        """Test main execution when run as script."""
        # Simulate running the module as main
        import weatherbot.__main__

        # The app should be callable
        assert callable(weatherbot.__main__.app)

    def test_app_is_callable(self) -> None:
        """Test that app is callable."""
        assert callable(app)
