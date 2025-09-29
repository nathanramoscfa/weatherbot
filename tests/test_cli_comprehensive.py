# tests/test_cli_comprehensive.py
"""Comprehensive tests for CLI interface."""

from datetime import UTC
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import typer
from typer.testing import CliRunner

from weatherbot.cli import (
    _analyze_threat_level,
    _check_cone_intersection,
    _display_coverage_results,
    _display_terminal_analysis,
    _generate_html_report,
    _get_alert_level_color,
    _get_storm_cone_data_for_report,
    _handle_marginal_coverage,
    _handle_outside_coverage,
    _is_in_cooldown,
    _map_alert_level_to_enum,
    _print_wrapped_text,
    _run_ai_monitoring_cycle,
    _run_monitoring_cycle,
    _validate_noaa_coverage,
    _wrap_text_to_width,
    app,
    debug_app,
    state_app,
)


class TestCLIApp:
    """Test main CLI application."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        # Set up required environment variables for CI
        import os
        self._original_home_lat = os.environ.get("HOME_LAT")
        self._original_home_lon = os.environ.get("HOME_LON")
        os.environ.setdefault("HOME_LAT", "25.0")
        os.environ.setdefault("HOME_LON", "-80.0")

    def teardown_method(self):
        """Clean up test fixtures."""
        import os
        # Restore original environment variables
        if self._original_home_lat is None:
            os.environ.pop("HOME_LAT", None)
        else:
            os.environ["HOME_LAT"] = self._original_home_lat
        if self._original_home_lon is None:
            os.environ.pop("HOME_LON", None)
        else:
            os.environ["HOME_LON"] = self._original_home_lon

    @patch('weatherbot.cli.load_config')
    @patch('weatherbot.cli.setup_logging')
    @patch('weatherbot.cli.validate_coordinates')
    @patch('weatherbot.cli._validate_noaa_coverage')
    @patch('weatherbot.cli.StateManager')
    @patch('weatherbot.cli.create_alert_manager')
    @patch('weatherbot.cli._run_monitoring_cycle')
    def test_run_command_basic(self, mock_run_cycle, mock_create_alert,
                              mock_state_manager, mock_validate_coverage,
                              mock_validate_coords, mock_setup_logging,
                              mock_load_config):
        """Test basic run command."""
        # Setup mocks
        mock_config = Mock()
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0
        mock_config.use_county_intersect = False
        mock_config.log_level = "INFO"
        mock_config.openai_api_key = None
        mock_load_config.return_value = mock_config

        mock_state_mgr = Mock()
        mock_state_manager.return_value = mock_state_mgr

        mock_alert_mgr = Mock()
        mock_create_alert.return_value = mock_alert_mgr

        # Run command
        result = self.runner.invoke(app, ["run"])

        # Verify
        assert result.exit_code == 0
        mock_load_config.assert_called_once()
        mock_setup_logging.assert_called_once()
        mock_validate_coords.assert_called_once_with(-80.0, 25.0)
        mock_validate_coverage.assert_called_once()
        mock_run_cycle.assert_called_once()

    @patch('weatherbot.cli.load_config')
    @patch('weatherbot.cli.setup_logging')
    @patch('weatherbot.cli.validate_coordinates')
    @patch('weatherbot.cli._validate_noaa_coverage')
    @patch('weatherbot.cli.StateManager')
    @patch('weatherbot.cli.create_alert_manager')
    @patch('weatherbot.cli._run_ai_monitoring_cycle')
    def test_run_command_with_ai(self, mock_run_ai_cycle, mock_create_alert,
                                mock_state_manager, mock_validate_coverage,
                                mock_validate_coords, mock_setup_logging,
                                mock_load_config):
        """Test run command with AI enabled."""
        # Setup mocks
        mock_config = Mock()
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0
        mock_config.use_county_intersect = False
        mock_config.log_level = "INFO"
        mock_config.openai_api_key = "test-key"
        mock_load_config.return_value = mock_config

        # Run command
        result = self.runner.invoke(app, ["run"])

        # Verify AI cycle was used
        assert result.exit_code == 0
        mock_run_ai_cycle.assert_called_once()

    @patch('weatherbot.cli.load_config')
    @patch('weatherbot.cli.setup_logging')
    def test_run_command_verbose(self, mock_setup_logging, mock_load_config):
        """Test run command with verbose flag."""
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.openai_api_key = None  # No AI key to avoid AI cycle
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0
        mock_config.use_county_intersect = False
        mock_config.alert_cooldown_minutes = 60
        mock_load_config.return_value = mock_config

        with patch('weatherbot.cli.validate_coordinates'):
            with patch('weatherbot.cli._validate_noaa_coverage'):
                with patch('weatherbot.cli.StateManager'):
                    with patch('weatherbot.cli.create_alert_manager'):
                        with patch('weatherbot.cli._run_monitoring_cycle'):
                            result = self.runner.invoke(app, ["run", "--verbose"])

        assert result.exit_code == 0
        mock_setup_logging.assert_called_with(log_level="DEBUG")

    def test_run_command_exception(self):
        """Test run command exception handling."""
        with patch('weatherbot.cli.load_config') as mock_load_config:
            mock_load_config.side_effect = Exception("Config error")

            result = self.runner.invoke(app, ["run"])

            assert result.exit_code == 1

    @patch('weatherbot.cli.load_config')
    @patch('weatherbot.cli.setup_logging')
    @patch('weatherbot.cli.create_alert_manager')
    def test_test_alert_command(self, mock_create_alert, mock_setup_logging,
                               mock_load_config):
        """Test test-alert command."""
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_load_config.return_value = mock_config

        mock_alert_mgr = Mock()
        mock_create_alert.return_value = mock_alert_mgr

        result = self.runner.invoke(app, ["test-alert"])

        assert result.exit_code == 0
        mock_alert_mgr.test_notifications.assert_called_once()

    def test_test_alert_command_exception(self):
        """Test test-alert command exception handling."""
        with patch('weatherbot.cli.load_config') as mock_load_config:
            mock_load_config.side_effect = Exception("Config error")

            result = self.runner.invoke(app, ["test-alert"])

            assert result.exit_code == 1

    @patch('weatherbot.cli.load_config')
    @patch('weatherbot.cli.setup_logging')
    @patch('weatherbot.cli._display_coverage_results')
    def test_check_coverage_command(self, mock_display, mock_setup_logging,
                                   mock_load_config):
        """Test check-coverage command."""
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.validate_coverage.return_value = {"status": "covered"}
        mock_load_config.return_value = mock_config

        result = self.runner.invoke(app, ["check-coverage"])

        assert result.exit_code == 0
        mock_config.validate_coverage.assert_called_once()
        mock_display.assert_called_once()

    def test_check_coverage_command_exception(self):
        """Test check-coverage command exception handling."""
        with patch('weatherbot.cli.load_config') as mock_load_config:
            mock_load_config.side_effect = Exception("Config error")

            result = self.runner.invoke(app, ["check-coverage"])

            assert result.exit_code == 1

    @patch('weatherbot.cli.load_config')
    @patch('weatherbot.coverage_validator.CoverageValidator')
    @patch('weatherbot.ai_map_analyzer.NOAA_MAP_URLS')
    @patch('webbrowser.open')
    def test_show_map_command(self, mock_webbrowser, mock_urls,
                             mock_validator_class, mock_load_config):
        """Test show-map command."""
        mock_config = Mock()
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0
        mock_load_config.return_value = mock_config

        mock_validator = Mock()
        mock_validator.validate_coordinates.return_value = {"basin": "atlantic"}
        mock_validator_class.return_value = mock_validator

        # Mock the NOAA_MAP_URLS dictionary structure
        atlantic_urls = {"7day": "https://test.url/map.png"}
        mock_urls.get.return_value = atlantic_urls
        mock_urls.__getitem__.return_value = atlantic_urls

        result = self.runner.invoke(app, ["show-map"])

        assert result.exit_code == 0
        mock_webbrowser.assert_called_once_with("https://test.url/map.png")

    def test_show_map_command_exception(self):
        """Test show-map command exception handling."""
        with patch('weatherbot.config.load_config') as mock_load_config:
            mock_load_config.side_effect = Exception("Config error")

            result = self.runner.invoke(app, ["show-map"])

            assert result.exit_code == 1

    @patch('weatherbot.cli.load_config')
    @patch('weatherbot.cli.setup_logging')
    @patch('weatherbot.cli._run_web_search_analysis')
    def test_ai_analysis_command_outside_coverage(self, mock_web_search,
                                                 mock_setup_logging,
                                                 mock_load_config):
        """Test ai-analysis command for outside coverage."""
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.openai_api_key = "test-key"
        mock_config.validate_coverage.return_value = {"is_outside": True}
        mock_load_config.return_value = mock_config

        result = self.runner.invoke(app, ["ai-analysis"])

        assert result.exit_code == 0
        mock_web_search.assert_called_once()

    @patch('weatherbot.cli.load_config')
    @patch('weatherbot.cli.setup_logging')
    @patch('weatherbot.cli._run_noaa_analysis')
    def test_ai_analysis_command_inside_coverage(self, mock_noaa_analysis,
                                                mock_setup_logging,
                                                mock_load_config):
        """Test ai-analysis command for inside coverage."""
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.openai_api_key = "test-key"
        mock_config.validate_coverage.return_value = {"is_outside": False}
        mock_load_config.return_value = mock_config

        result = self.runner.invoke(app, ["ai-analysis"])

        assert result.exit_code == 0
        mock_noaa_analysis.assert_called_once()

    @patch('weatherbot.cli.load_config')
    @patch('weatherbot.cli.setup_logging')
    def test_ai_analysis_command_no_api_key(self, mock_setup_logging, mock_load_config):
        """Test ai-analysis command without API key."""
        mock_config = Mock()
        mock_config.openai_api_key = None
        mock_config.log_level = "INFO"
        mock_load_config.return_value = mock_config

        result = self.runner.invoke(app, ["ai-analysis"])

        assert result.exit_code == 0
        assert "No OpenAI API key configured" in result.stdout

    def test_ai_analysis_command_exception(self):
        """Test ai-analysis command exception handling."""
        with patch('weatherbot.cli.load_config') as mock_load_config:
            mock_load_config.side_effect = Exception("Config error")

            result = self.runner.invoke(app, ["ai-analysis"])

            assert result.exit_code == 1


class TestDebugCommands:
    """Test debug commands."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch('weatherbot.nhc.NHCClient')
    def test_debug_layers_command(self, mock_nhc_client_class):
        """Test debug layers command."""
        mock_client = Mock()
        mock_client.get_layers_info.return_value = [
            {"id": 1, "name": "Test Layer", "type": "Feature", "description": "Test"}
        ]
        mock_client.discover_cone_layer.return_value = 5
        mock_nhc_client_class.return_value = mock_client

        result = self.runner.invoke(debug_app, ["layers"])

        assert result.exit_code == 0
        assert "Test Layer" in result.stdout

    @patch('weatherbot.nhc.NHCClient')
    def test_debug_layers_command_no_layers(self, mock_nhc_client_class):
        """Test debug layers command with no layers."""
        mock_client = Mock()
        mock_client.get_layers_info.return_value = []
        mock_nhc_client_class.return_value = mock_client

        result = self.runner.invoke(debug_app, ["layers"])

        assert result.exit_code == 0
        assert "No layers found" in result.stdout

    def test_debug_layers_command_exception(self):
        """Test debug layers command exception handling."""
        with patch('weatherbot.nhc.NHCClient') as mock_nhc_client_class:
            mock_nhc_client_class.side_effect = Exception("NHC error")

            result = self.runner.invoke(debug_app, ["layers"])

            assert result.exit_code == 1

    @patch('weatherbot.cache.api_cache')
    def test_debug_clear_cache_command(self, mock_cache):
        """Test debug clear-cache command."""
        result = self.runner.invoke(debug_app, ["clear-cache"])

        assert result.exit_code == 0
        mock_cache.clear.assert_called_once()

    def test_debug_clear_cache_command_exception(self):
        """Test debug clear-cache command exception handling."""
        with patch('weatherbot.cache.api_cache') as mock_cache:
            mock_cache.clear.side_effect = Exception("Cache error")

            result = self.runner.invoke(debug_app, ["clear-cache"])

            assert result.exit_code == 1

    @patch('weatherbot.nhc.NHCClient')
    def test_debug_storm_data_command(self, mock_nhc_client_class):
        """Test debug storm-data command."""
        mock_cone = Mock()
        mock_cone.storm_name = "Hurricane Test"
        mock_cone.storm_type = "Hurricane"
        mock_cone.advisory_num = "5"
        mock_cone.current_position = (25.0, -80.0)
        mock_cone.max_winds = 85
        mock_cone.min_pressure = 980

        mock_client = Mock()
        mock_client.fetch_active_cones.return_value = [mock_cone]
        mock_nhc_client_class.return_value = mock_client

        result = self.runner.invoke(debug_app, ["storm-data"])

        assert result.exit_code == 0
        assert "Hurricane Test" in result.stdout

    @patch('weatherbot.nhc.NHCClient')
    def test_debug_storm_data_command_no_storms(self, mock_nhc_client_class):
        """Test debug storm-data command with no storms."""
        mock_client = Mock()
        mock_client.fetch_active_cones.return_value = []
        mock_nhc_client_class.return_value = mock_client

        result = self.runner.invoke(debug_app, ["storm-data"])

        assert result.exit_code == 0
        assert "No active storms found" in result.stdout

    @patch('weatherbot.nhc_current_storms.get_current_storms_with_positions')
    def test_debug_current_storms_command(self, mock_get_storms):
        """Test debug current-storms command."""
        mock_storm = Mock()
        mock_storm.storm_name = "Hurricane Test"
        mock_storm.storm_type = "Hurricane"
        mock_storm.current_position = (25.0, -80.0)
        mock_storm.max_winds = 85
        mock_storm.min_pressure = 980
        mock_storm.movement = "NW at 15 mph"

        mock_get_storms.return_value = [mock_storm]

        result = self.runner.invoke(debug_app, ["current-storms"])

        assert result.exit_code == 0
        # The table might format the name across multiple rows, so check for parts
        assert "Hurricane" in result.stdout and "Test" in result.stdout

    @patch('weatherbot.nhc_current_storms.get_current_storms_with_positions')
    def test_debug_current_storms_command_no_storms(self, mock_get_storms):
        """Test debug current-storms command with no storms."""
        mock_get_storms.return_value = []

        result = self.runner.invoke(debug_app, ["current-storms"])

        assert result.exit_code == 0
        assert "No storms found" in result.stdout

    @patch('weatherbot.nhc_storm_tracker.discover_new_storms')
    @patch('weatherbot.nhc_storm_tracker.get_all_active_storm_cones')
    def test_debug_discover_storms_command(self, mock_get_cones, mock_discover):
        """Test debug discover-storms command."""
        mock_discover.return_value = [
            {
                "storm_name": "Hurricane Test",
                "storm_id": "AL05",
                "basin": "atlantic",
                "page_url": "https://test.url",
                "cone_url": "https://test.url/cone"
            }
        ]

        mock_cone = Mock()
        mock_cone.storm_name = "Hurricane Test"
        mock_cone.storm_type = "Hurricane"
        mock_get_cones.return_value = [mock_cone]

        result = self.runner.invoke(debug_app, ["discover-storms"])

        assert result.exit_code == 0
        assert "Hurricane Test" in result.stdout

    @patch('weatherbot.nhc_storm_tracker.discover_new_storms')
    def test_debug_discover_storms_command_no_storms(self, mock_discover):
        """Test debug discover-storms command with no storms."""
        mock_discover.return_value = []

        result = self.runner.invoke(debug_app, ["discover-storms"])

        assert result.exit_code == 0
        assert "No individual storm pages found" in result.stdout

    @patch('weatherbot.cli.load_config')
    @patch('weatherbot.ai_enhancer.AIStormEnhancer')
    def test_debug_test_ai_command(self, mock_enhancer_class, mock_load_config):
        """Test debug test-ai command."""
        mock_config = Mock()
        mock_config.openai_api_key = "test-key"
        mock_load_config.return_value = mock_config

        mock_enhancer = Mock()
        mock_enhancer.get_disturbance_positions.return_value = [
            {
                "name": "AL93",
                "type": "Disturbance",
                "latitude": 23.5,
                "longitude": -59.2,
                "probability": "70%"
            }
        ]
        mock_enhancer_class.return_value = mock_enhancer

        result = self.runner.invoke(debug_app, ["test-ai"])

        assert result.exit_code == 0
        assert "AL93" in result.stdout

    @patch('weatherbot.cli.load_config')
    def test_debug_test_ai_command_no_api_key(self, mock_load_config):
        """Test debug test-ai command without API key."""
        mock_config = Mock()
        mock_config.openai_api_key = None
        mock_load_config.return_value = mock_config

        result = self.runner.invoke(debug_app, ["test-ai"])

        assert result.exit_code == 0
        assert "No OpenAI API key configured" in result.stdout


class TestStateCommands:
    """Test state management commands."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch('weatherbot.cli.StateManager')
    def test_state_show_command(self, mock_state_manager_class):
        """Test state show command."""
        mock_state_manager = Mock()
        mock_state_manager.show_state.return_value = {
            "last_update": "2023-09-28T12:00:00Z",
            "in_cone": False
        }
        mock_state_manager_class.return_value = mock_state_manager

        result = self.runner.invoke(state_app, ["show"])

        assert result.exit_code == 0
        assert "2023-09-28T12:00:00Z" in result.stdout

    def test_state_show_command_exception(self):
        """Test state show command exception handling."""
        with patch('weatherbot.cli.StateManager') as mock_state_manager_class:
            mock_state_manager_class.side_effect = Exception("State error")

            result = self.runner.invoke(state_app, ["show"])

            assert result.exit_code == 1

    @patch('weatherbot.cli.StateManager')
    def test_state_clear_command(self, mock_state_manager_class):
        """Test state clear command."""
        mock_state_manager = Mock()
        mock_state_manager_class.return_value = mock_state_manager

        result = self.runner.invoke(state_app, ["clear"])

        assert result.exit_code == 0
        mock_state_manager.clear_state.assert_called_once()

    def test_state_clear_command_exception(self):
        """Test state clear command exception handling."""
        with patch('weatherbot.cli.StateManager') as mock_state_manager_class:
            mock_state_manager = Mock()
            mock_state_manager.clear_state.side_effect = Exception("Clear error")
            mock_state_manager_class.return_value = mock_state_manager

            result = self.runner.invoke(state_app, ["clear"])

            assert result.exit_code == 1


class TestMonitoringCycles:
    """Test monitoring cycle functions."""

    def test_run_ai_monitoring_cycle_success(self):
        """Test successful AI monitoring cycle."""
        mock_config = Mock()
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0
        mock_config.use_county_intersect = False
        mock_config.openai_api_key = "test-key"
        mock_config.alert_cooldown_minutes = 60
        mock_config.get_county_geojson_path.return_value = Path("test.geojson")

        mock_state_manager = Mock()
        mock_state = Mock()
        mock_state.updated = Mock()
        mock_state_manager.load_state.return_value = mock_state

        mock_alert_manager = Mock()

        with patch('weatherbot.cli._is_in_cooldown') as mock_cooldown:
            with patch('weatherbot.cli.analyze_location_threat_enhanced') as mock_analyze:
                with patch('weatherbot.ai_map_analyzer.analyze_hurricane_threat_with_ai') as mock_ai:
                    with patch('weatherbot.reports.get_location_name') as mock_location:
                        mock_cooldown.return_value = False
                        mock_analyze.return_value = {"alert_level": Mock(value=2)}
                        mock_ai.return_value = (2, "Test Alert", "Test message")
                        mock_location.return_value = "Test Location"

                        _run_ai_monitoring_cycle(mock_config, mock_state_manager, mock_alert_manager)

                        mock_alert_manager.raise_alert.assert_called_once()

    def test_run_ai_monitoring_cycle_cooldown(self):
        """Test AI monitoring cycle during cooldown."""
        mock_config = Mock()
        mock_config.alert_cooldown_minutes = 60

        mock_state_manager = Mock()
        mock_state = Mock()
        mock_state_manager.load_state.return_value = mock_state

        mock_alert_manager = Mock()

        with patch('weatherbot.cli._is_in_cooldown') as mock_cooldown:
            mock_cooldown.return_value = True

            _run_ai_monitoring_cycle(mock_config, mock_state_manager, mock_alert_manager)

            mock_alert_manager.raise_alert.assert_not_called()

    def test_run_ai_monitoring_cycle_exception(self):
        """Test AI monitoring cycle exception handling."""
        mock_config = Mock()
        mock_config.alert_cooldown_minutes = 60

        mock_state_manager = Mock()
        mock_state_manager.load_state.side_effect = Exception("State error")

        mock_alert_manager = Mock()

        # Should raise the exception since there's no try-catch around load_state
        with pytest.raises(Exception, match="State error"):
            _run_ai_monitoring_cycle(mock_config, mock_state_manager, mock_alert_manager)

    def test_run_monitoring_cycle_success(self):
        """Test successful regular monitoring cycle."""
        mock_config = Mock()
        mock_config.alert_cooldown_minutes = 60

        mock_state_manager = Mock()
        mock_state = Mock()
        mock_state_manager.load_state.return_value = mock_state

        mock_alert_manager = Mock()

        with patch('weatherbot.cli._is_in_cooldown') as mock_cooldown:
            with patch('weatherbot.cli._check_forecast_cones') as mock_cones:
                with patch('weatherbot.cli._check_nws_alerts') as mock_nws:
                    mock_cooldown.return_value = False

                    _run_monitoring_cycle(mock_config, mock_state_manager, mock_alert_manager)

                    mock_cones.assert_called_once()
                    mock_nws.assert_called_once()
                    mock_state_manager.save_state.assert_called_once()

    def test_is_in_cooldown_true(self):
        """Test cooldown detection when in cooldown."""
        from datetime import datetime, timedelta

        mock_state = Mock()
        mock_state.updated = datetime.now(UTC) - timedelta(minutes=30)

        result = _is_in_cooldown(mock_state, 60)
        assert result is True

    def test_is_in_cooldown_false(self):
        """Test cooldown detection when not in cooldown."""
        from datetime import datetime, timedelta

        mock_state = Mock()
        mock_state.updated = datetime.now(UTC) - timedelta(minutes=90)

        result = _is_in_cooldown(mock_state, 60)
        assert result is False

    def test_is_in_cooldown_disabled(self):
        """Test cooldown detection when disabled."""
        mock_state = Mock()

        result = _is_in_cooldown(mock_state, 0)
        assert result is False


class TestUtilityFunctions:
    """Test utility functions."""

    def test_map_alert_level_to_enum(self):
        """Test alert level mapping."""
        from weatherbot.alert_levels import AlertLevel

        assert _map_alert_level_to_enum(1) == AlertLevel.ALL_CLEAR
        assert _map_alert_level_to_enum(2) == AlertLevel.TROPICAL_STORM_THREAT
        assert _map_alert_level_to_enum(3) == AlertLevel.TROPICAL_STORM_WATCH_HURRICANE_THREAT
        assert _map_alert_level_to_enum(4) == AlertLevel.TROPICAL_STORM_WARNING_HURRICANE_WATCH_EVACUATION
        assert _map_alert_level_to_enum(5) == AlertLevel.HURRICANE_WARNING
        assert _map_alert_level_to_enum(99) == AlertLevel.ALL_CLEAR  # Default

    def test_get_alert_level_color(self):
        """Test alert level color mapping."""
        assert _get_alert_level_color(1) == "green"
        assert _get_alert_level_color(2) == "cyan"
        assert _get_alert_level_color(3) == "yellow"
        assert _get_alert_level_color(4) == "red"
        assert _get_alert_level_color(5) == "red"

    def test_wrap_text_to_width(self):
        """Test text wrapping."""
        text = "This is a very long line that should be wrapped at a specific width"
        result = _wrap_text_to_width(text, 20)

        assert len(result) > 1
        for line in result:
            assert len(line) <= 20

    @patch('weatherbot.cli.console')
    def test_print_wrapped_text(self, mock_console):
        """Test wrapped text printing."""
        text = "This is a test line that should be wrapped"
        _print_wrapped_text(mock_console, text, "white", 20)

        assert mock_console.print.called

    def test_analyze_threat_level_basic(self):
        """Test basic threat level analysis."""
        mock_config = Mock()
        mock_config.use_county_intersect = False
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0

        mock_cone = Mock()
        mock_cone.storm_type = "Hurricane"

        mock_geometry = Mock()

        cones = [mock_cone]
        geometries = [mock_geometry]

        with patch('weatherbot.cli.point_in_any') as mock_point_in:
            mock_point_in.return_value = True

            result = _analyze_threat_level(mock_config, cones, geometries)

            assert result["is_in_any_cone"] is True
            assert len(result["affecting_storms"]) == 1

    def test_check_cone_intersection_point_check(self):
        """Test cone intersection with point check."""
        mock_config = Mock()
        mock_config.use_county_intersect = False
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0

        mock_geometry = Mock()
        geometries = [mock_geometry]

        with patch('weatherbot.cli.point_in_any') as mock_point_in:
            mock_point_in.return_value = True

            result = _check_cone_intersection(mock_config, geometries)

            assert result is True

    def test_check_cone_intersection_county_intersect(self):
        """Test cone intersection with county intersect."""
        mock_config = Mock()
        mock_config.use_county_intersect = True
        mock_config.get_county_geojson_path.return_value = Path("test.geojson")

        mock_geometry = Mock()
        geometries = [mock_geometry]

        with patch('weatherbot.cli.load_county_polygon') as mock_load:
            with patch('weatherbot.cli.polygon_intersects_any') as mock_intersect:
                mock_polygon = Mock()
                mock_load.return_value = mock_polygon
                mock_intersect.return_value = True

                result = _check_cone_intersection(mock_config, geometries)

                assert result is True

    @patch('weatherbot.cli.console')
    def test_display_coverage_results(self, mock_console):
        """Test coverage results display."""
        mock_config = Mock()
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0

        mock_status = Mock()
        mock_status.value = "covered"

        coverage_result = {
            "status": mock_status,
            "is_covered": True,
            "is_marginal": False,
            "is_outside": False,
            "warnings": [],
            "errors": []
        }

        _display_coverage_results(mock_console, mock_config, coverage_result)

        assert mock_console.print.called

    @patch('weatherbot.cli.console')
    def test_display_terminal_analysis(self, mock_console):
        """Test terminal analysis display."""
        from weatherbot.alert_levels import AlertInfo, AlertLevel

        # Mock the console.measure method to return a proper measurement
        mock_measurement = Mock()
        mock_measurement.maximum = 20  # Return an integer width
        mock_console.measure.return_value = mock_measurement

        mock_config = Mock()
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0
        mock_config.validate_coverage.return_value = {"is_outside": False, "basin": "atlantic"}

        alert_info = AlertInfo(
            level=AlertLevel.TROPICAL_STORM_THREAT,
            icon="🌪️",
            color="#ff6b35",
            sound_pattern="intermittent",
            title_prefix="Tropical Storm Threat",
            guidance="Monitor conditions"
        )

        _display_terminal_analysis(
            mock_console, 2, AlertLevel.TROPICAL_STORM_THREAT, alert_info,
            "Test Alert", "Test message", mock_config, "Test Location"
        )

        assert mock_console.print.called

    def test_get_storm_cone_data_for_report_success(self):
        """Test getting storm cone data for report."""
        mock_config = Mock()
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0

        with patch('weatherbot.nhc_storm_tracker.discover_new_storms') as mock_discover:
            mock_discover.return_value = [
                {
                    "storm_name": "Hurricane Test",
                    "storm_id": "AL05",
                    "cone_url": "https://test.url/cone",
                    "page_url": "https://test.url",
                    "latitude": 26.0,
                    "longitude": -81.0
                }
            ]

            result = _get_storm_cone_data_for_report(mock_config)

            assert len(result) == 1
            assert result[0]["name"] == "Hurricane Test"

    def test_get_storm_cone_data_for_report_distance_filter(self):
        """Test storm cone data filtering by distance."""
        mock_config = Mock()
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0

        with patch('weatherbot.nhc_storm_tracker.discover_new_storms') as mock_discover:
            mock_discover.return_value = [
                {
                    "storm_name": "Far Storm",
                    "storm_id": "AL05",
                    "cone_url": "https://test.url/cone",
                    "page_url": "https://test.url",
                    "latitude": 60.0,  # Very far away
                    "longitude": -150.0
                }
            ]

            result = _get_storm_cone_data_for_report(mock_config)

            assert len(result) == 0  # Should be filtered out

    @patch('weatherbot.reports.generate_html_report')
    def test_generate_html_report_wrapper(self, mock_generate):
        """Test HTML report generation wrapper."""
        from weatherbot.alert_levels import AlertInfo, AlertLevel

        mock_config = Mock()
        alert_info = AlertInfo(
            level=AlertLevel.TROPICAL_STORM_THREAT,
            icon="🌪️",
            color="#ff6b35",
            sound_pattern="intermittent",
            title_prefix="Test",
            guidance="Test"
        )
        mock_generate.return_value = "test_report.html"

        _generate_html_report(
            2, AlertLevel.TROPICAL_STORM_THREAT, alert_info,
            "Test Title", "Test Message", mock_config, "Test Location", []
        )

        mock_generate.assert_called_once()

    def test_validate_noaa_coverage_success(self):
        """Test NOAA coverage validation success."""
        mock_config = Mock()
        mock_config.validate_coverage.return_value = {
            "errors": [],
            "warnings": [],
            "is_outside": False,
            "is_marginal": False
        }

        # Should not raise exception
        _validate_noaa_coverage(mock_config)

    def test_validate_noaa_coverage_with_errors(self):
        """Test NOAA coverage validation with errors."""
        mock_config = Mock()
        mock_config.validate_coverage.return_value = {
            "errors": ["Invalid coordinates"],
            "warnings": [],
            "is_outside": False,
            "is_marginal": False
        }

        with pytest.raises(typer.Exit):
            _validate_noaa_coverage(mock_config)

    @patch('weatherbot.cli.console')
    @patch('sys.stdin.isatty')
    @patch('builtins.input')
    def test_handle_outside_coverage_continue(self, mock_input, mock_isatty, mock_console):
        """Test handling outside coverage with continue."""
        mock_isatty.return_value = True
        mock_input.return_value = "yes"

        mock_config = Mock()
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0

        coverage_result = {"is_outside": True}

        with patch('weatherbot.coverage_validator.CoverageValidator') as mock_validator_class:
            mock_validator = Mock()
            mock_validator.get_coverage_recommendations.return_value = ["Test recommendation"]
            mock_validator_class.return_value = mock_validator

            # Should not raise exception
            _handle_outside_coverage(mock_config, coverage_result)

    @patch('weatherbot.cli.console')
    @patch('sys.stdin.isatty')
    @patch('builtins.input')
    def test_handle_outside_coverage_exit(self, mock_input, mock_isatty, mock_console):
        """Test handling outside coverage with exit."""
        mock_isatty.return_value = True
        mock_input.return_value = "no"

        mock_config = Mock()
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0

        coverage_result = {"is_outside": True}

        with patch('weatherbot.coverage_validator.CoverageValidator') as mock_validator_class:
            mock_validator = Mock()
            mock_validator.get_coverage_recommendations.return_value = ["Test recommendation"]
            mock_validator_class.return_value = mock_validator

            with pytest.raises(typer.Exit):
                _handle_outside_coverage(mock_config, coverage_result)

    @patch('weatherbot.cli.console')
    def test_handle_marginal_coverage(self, mock_console):
        """Test handling marginal coverage."""
        mock_config = Mock()
        mock_config.home_lat = 25.0
        mock_config.home_lon = -80.0

        coverage_result = {"is_marginal": True}

        # Should not raise exception
        _handle_marginal_coverage(mock_config, coverage_result)

        assert mock_console.print.called
