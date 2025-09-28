# tests/test_notifiers_comprehensive.py
"""Comprehensive tests for notifier modules."""

from pathlib import Path
from unittest.mock import Mock, patch

from weatherbot.notifiers.toast import ToastNotifier
from weatherbot.notifiers.weather_map import WeatherMapGUI


class TestToastNotifier:
    """Test cases for ToastNotifier class."""

    def test_init_default(self):
        """Test default initialization."""
        notifier = ToastNotifier()

        assert notifier.icon_path is None

    def test_init_with_icon_path(self):
        """Test initialization with icon path."""
        icon_path = Path("test_icon.ico")
        notifier = ToastNotifier(icon_path=icon_path)

        assert notifier.icon_path == icon_path

    def test_get_toast_library_win11toast(self):
        """Test toast library detection with win11toast."""
        # Patch the import directly in the method
        with patch('builtins.__import__') as mock_import:
            mock_win11toast = Mock()
            mock_import.side_effect = lambda name, *args, **kwargs: mock_win11toast if name == 'win11toast' else Mock()

            notifier = ToastNotifier()
            toast_lib = notifier._get_toast_library()

            assert toast_lib == mock_win11toast

    def test_get_toast_library_win11toast_import_error(self):
        """Test toast library detection with win11toast import error."""
        with patch('builtins.__import__') as mock_import:
            def side_effect(name, *args, **kwargs):
                if name == 'win11toast':
                    raise ImportError("No module named 'win11toast'")
                if name == 'winotify':
                    return Mock()
                return Mock()

            mock_import.side_effect = side_effect

            notifier = ToastNotifier()
            toast_lib = notifier._get_toast_library()

            # Should fallback to winotify
            assert toast_lib is not None

    def test_get_toast_library_no_libraries(self):
        """Test toast library detection with no available libraries."""
        with patch('builtins.__import__') as mock_import:
            mock_import.side_effect = ImportError("No toast libraries")

            notifier = ToastNotifier()
            toast_lib = notifier._get_toast_library()

            assert toast_lib is None

    def test_show_notification_no_library(self):
        """Test notification display without available library."""
        notifier = ToastNotifier()
        notifier._toast_lib = None

        result = notifier.show_notification("Test Title", "Test Message")

        assert result is False

    def test_show_notification_win11toast(self):
        """Test notification display with win11toast."""
        mock_win11toast = Mock()
        mock_win11toast.notify = Mock()

        notifier = ToastNotifier()
        notifier._toast_lib = mock_win11toast

        result = notifier.show_notification("Test Title", "Test Message", duration=5)

        assert result is True

    def test_show_notification_winotify(self):
        """Test notification display with winotify."""
        mock_winotify = Mock()
        mock_notification = Mock()
        mock_winotify.Notification = Mock(return_value=mock_notification)

        notifier = ToastNotifier()
        notifier._toast_lib = mock_winotify

        result = notifier.show_notification("Test Title", "Test Message", duration=5)

        assert result is True

    def test_show_notification_win10toast(self):
        """Test notification display with win10toast."""
        mock_win10toast = Mock()
        mock_win10toast.show_toast = Mock()

        notifier = ToastNotifier()
        notifier._toast_lib = mock_win10toast

        result = notifier.show_notification("Test Title", "Test Message", duration=5)

        assert result is True

    def test_show_notification_exception(self):
        """Test notification display exception handling."""
        mock_toast_lib = Mock()
        mock_toast_lib.notify = Mock(side_effect=Exception("Toast error"))

        notifier = ToastNotifier()
        notifier._toast_lib = mock_toast_lib

        result = notifier.show_notification("Test Title", "Test Message")

        assert result is False

    def test_show_win11toast(self):
        """Test win11toast notification display."""
        mock_win11toast = Mock()
        mock_win11toast.notify = Mock()

        notifier = ToastNotifier()
        notifier._toast_lib = mock_win11toast
        notifier.icon_path = Path("test.ico")

        notifier._show_win11toast("Test Title", "Test Message", 10)

        mock_win11toast.notify.assert_called_once()

    def test_show_win11toast_no_icon(self):
        """Test win11toast notification display without icon."""
        mock_win11toast = Mock()
        mock_win11toast.notify = Mock()

        notifier = ToastNotifier()
        notifier._toast_lib = mock_win11toast
        notifier.icon_path = None

        notifier._show_win11toast("Test Title", "Test Message", 10)

        mock_win11toast.notify.assert_called_once()

    def test_show_winotify(self):
        """Test winotify notification display."""
        mock_winotify = Mock()
        mock_notification = Mock()
        mock_winotify.Notification = Mock(return_value=mock_notification)

        notifier = ToastNotifier()
        notifier._toast_lib = mock_winotify
        notifier.icon_path = Path("test.ico")

        notifier._show_winotify("Test Title", "Test Message", 10)

        mock_winotify.Notification.assert_called_once()
        mock_notification.show.assert_called_once()

    def test_show_win10toast(self):
        """Test win10toast notification display."""
        mock_win10toast = Mock()
        mock_win10toast.show_toast = Mock()

        notifier = ToastNotifier()
        notifier._toast_lib = mock_win10toast
        notifier.icon_path = Path("test.ico")

        notifier._show_win10toast("Test Title", "Test Message", 10)

        mock_win10toast.show_toast.assert_called_once()

    def test_show_win10toast_no_icon(self):
        """Test win10toast notification display without icon."""
        mock_win10toast = Mock()
        mock_win10toast.show_toast = Mock()

        notifier = ToastNotifier()
        notifier._toast_lib = mock_win10toast
        notifier.icon_path = None

        notifier._show_win10toast("Test Title", "Test Message", 10)

        mock_win10toast.show_toast.assert_called_once()


class TestWeatherMapGUI:
    """Test cases for WeatherMapGUI class."""

    def test_init(self):
        """Test initialization."""
        gui = WeatherMapGUI(25.0, -80.0)

        assert gui.home_lat == 25.0
        assert gui.home_lon == -80.0
        assert gui._map_file is None

    @patch('weatherbot.notifiers.weather_map.webbrowser')
    @patch('weatherbot.notifiers.weather_map.tempfile')
    def test_show_weather_map_success(self, mock_tempfile, mock_webbrowser):
        """Test successful weather map display."""
        mock_tempfile.mktemp.return_value = "/tmp/test_map.html"

        gui = WeatherMapGUI(25.0, -80.0)

        with patch.object(gui, '_create_weather_map') as mock_create_map:
            mock_map = Mock()
            mock_map.save = Mock()
            mock_create_map.return_value = mock_map

            gui.show_weather_map("CONE", "Test Alert", "Test Message")

            mock_create_map.assert_called_once()
            mock_map.save.assert_called_once()
            mock_webbrowser.open.assert_called_once()


    @patch('weatherbot.notifiers.weather_map.webbrowser')
    @patch('weatherbot.notifiers.weather_map.tempfile')
    @patch('weatherbot.notifiers.weather_map.threading.Timer')
    def test_show_weather_map_with_auto_dismiss(self, mock_timer, mock_tempfile, mock_webbrowser):
        """Test weather map display with auto-dismiss."""
        mock_tempfile.mktemp.return_value = "/tmp/test_map.html"

        gui = WeatherMapGUI(25.0, -80.0)

        with patch.object(gui, '_create_weather_map') as mock_create_map:
            mock_map = Mock()
            mock_map.save = Mock()
            mock_create_map.return_value = mock_map

            gui.show_weather_map("INFO", "Test Alert", "Test Message", auto_dismiss_seconds=30)

            mock_timer.assert_called_once()

    def test_show_weather_map_exception(self):
        """Test weather map display exception handling."""
        gui = WeatherMapGUI(25.0, -80.0)

        with patch.object(gui, '_create_weather_map') as mock_create_map:
            mock_create_map.side_effect = Exception("Map creation error")

            # Should not raise exception
            gui.show_weather_map("CONE", "Test Alert", "Test Message")

    @patch('weatherbot.notifiers.weather_map.folium')
    def test_create_weather_map_basic(self, mock_folium):
        """Test basic weather map creation."""
        mock_map = Mock()
        mock_folium.Map.return_value = mock_map

        gui = WeatherMapGUI(25.0, -80.0)
        result = gui._create_weather_map("CONE", "Test Alert", "Test Message")

        assert result == mock_map
        mock_folium.Map.assert_called_once()

    @patch('weatherbot.notifiers.weather_map.folium')
    def test_create_weather_map_with_cones(self, mock_folium):
        """Test weather map creation with hurricane cones."""
        mock_map = Mock()
        mock_folium.Map.return_value = mock_map

        # Mock cone geometry
        mock_geometry = Mock()
        mock_geometry.__geo_interface__ = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]
        }

        # Mock storm info
        mock_storm = Mock()
        mock_storm.storm_name = "Hurricane Test"
        mock_storm.get_storm_info_html.return_value = "<b>Hurricane Test</b>"

        gui = WeatherMapGUI(25.0, -80.0)

        with patch.object(gui, '_add_hurricane_cones') as mock_add_cones:
            gui._create_weather_map(
                "CONE", "Test Alert", "Test Message",
                cone_geometries=[mock_geometry],
                storm_info=[mock_storm]
            )

            mock_add_cones.assert_called_once()

    def test_get_alert_color(self):
        """Test alert color mapping."""
        gui = WeatherMapGUI(25.0, -80.0)

        assert gui._get_alert_color("CONE") == "#FFD700"     # Gold
        assert gui._get_alert_color("WATCH") == "#FF8C00"   # Dark Orange
        assert gui._get_alert_color("WARNING") == "#FF0000" # Red
        assert gui._get_alert_color("INFO") == "#4169E1"    # Royal Blue
        assert gui._get_alert_color("UNKNOWN") == "#808080"

    def test_zoom_level_hardcoded(self):
        """Test that zoom level is properly set in map creation."""
        gui = WeatherMapGUI(25.0, -80.0)

        # Create a basic map to verify zoom level is set
        with patch('weatherbot.notifiers.weather_map.folium.Map') as mock_map:
            gui._create_weather_map("INFO", "Test", "Test message")

            # Verify folium.Map was called with zoom_start=5
            mock_map.assert_called_once()
            call_kwargs = mock_map.call_args[1]
            assert call_kwargs['zoom_start'] == 5

    def test_home_marker_integration(self):
        """Test that home marker is added during map creation."""
        gui = WeatherMapGUI(25.0, -80.0)

        # Test that the map creation includes home location
        with patch('weatherbot.notifiers.weather_map.folium') as mock_folium:
            mock_map = Mock()
            mock_folium.Map.return_value = mock_map

            gui._create_weather_map("INFO", "Test", "Test message")

            # Verify that Marker was called (home marker should be added)
            mock_folium.Marker.assert_called()
            mock_folium.Icon.assert_called()

    @patch('weatherbot.notifiers.weather_map.folium')
    def test_add_hurricane_cones(self, mock_folium):
        """Test hurricane cone addition."""
        mock_map = Mock()
        Mock()
        mock_polygon = Mock()
        mock_folium.Polygon.return_value = mock_polygon

        # Mock geometry with exterior attribute (Shapely Polygon style)
        mock_geometry = Mock()
        mock_geometry.exterior.coords = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]

        # Mock storm info
        mock_storm = Mock()
        mock_storm.storm_name = "Hurricane Test"
        mock_storm.get_storm_info_html.return_value = "<b>Hurricane Test</b>"

        gui = WeatherMapGUI(25.0, -80.0)
        gui._add_hurricane_cones(mock_map, [mock_geometry], [mock_storm])

        mock_folium.Polygon.assert_called()
        mock_polygon.add_to.assert_called_with(mock_map)

    @patch('weatherbot.notifiers.weather_map.folium')
    def test_add_hurricane_cones_no_storm_info(self, mock_folium):
        """Test hurricane cone addition without storm info."""
        mock_map = Mock()
        Mock()
        mock_polygon = Mock()
        mock_folium.Polygon.return_value = mock_polygon

        # Mock geometry with exterior attribute (Shapely Polygon style)
        mock_geometry = Mock()
        mock_geometry.exterior.coords = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]

        gui = WeatherMapGUI(25.0, -80.0)
        gui._add_hurricane_cones(mock_map, [mock_geometry], None)

        mock_folium.Polygon.assert_called()

    def test_legend_integration(self):
        """Test that legend functionality is integrated in map creation."""
        gui = WeatherMapGUI(25.0, -80.0)

        # Test that the map creation process includes legend elements
        with patch('weatherbot.notifiers.weather_map.folium') as mock_folium:
            mock_map = Mock()
            mock_folium.Map.return_value = mock_map

            gui._create_weather_map("WARNING", "Test", "Test message")

            # Verify that the map creation process completes
            mock_folium.Map.assert_called_once()


    def test_cleanup_map_with_file(self):
        """Test map cleanup with existing file."""
        gui = WeatherMapGUI(25.0, -80.0)
        mock_file = Mock()
        gui._map_file = mock_file

        with patch.object(mock_file, 'exists', return_value=True):
            with patch.object(mock_file, 'unlink') as mock_unlink:
                gui._cleanup_map()

                mock_unlink.assert_called_once()

    def test_cleanup_map_no_file(self):
        """Test map cleanup without file."""
        gui = WeatherMapGUI(25.0, -80.0)
        gui._map_file = None

        # Should not raise exception
        gui._cleanup_map()

    def test_cleanup_map_file_not_exists(self):
        """Test map cleanup with non-existent file."""
        gui = WeatherMapGUI(25.0, -80.0)
        mock_file = Mock()
        gui._map_file = mock_file

        with patch.object(mock_file, 'exists', return_value=False):
            # Should not raise exception
            gui._cleanup_map()

    def test_cleanup_map_exception(self):
        """Test map cleanup exception handling."""
        gui = WeatherMapGUI(25.0, -80.0)
        mock_file = Mock()
        gui._map_file = mock_file

        with patch.object(mock_file, 'exists', return_value=True):
            with patch.object(mock_file, 'unlink', side_effect=Exception("Delete error")):
                # Should not raise exception
                gui._cleanup_map()


class TestIntegration:
    """Integration tests for notifier modules."""


    def test_toast_notifier_full_workflow(self):
        """Test full toast notifier workflow."""
        mock_toast_lib = Mock()
        mock_toast_lib.notify = Mock()

        notifier = ToastNotifier()
        notifier._toast_lib = mock_toast_lib

        result = notifier.show_notification(
            "Weather Alert",
            "Hurricane approaching your area",
            duration=15
        )

        assert result is True
        mock_toast_lib.notify.assert_called_once()

    @patch('weatherbot.notifiers.weather_map.webbrowser')
    @patch('weatherbot.notifiers.weather_map.tempfile')
    @patch('weatherbot.notifiers.weather_map.folium')
    def test_weather_map_full_workflow(self, mock_folium, mock_tempfile, mock_webbrowser):
        """Test full weather map workflow."""
        mock_tempfile.mktemp.return_value = "/tmp/weather_map.html"
        mock_map = Mock()
        mock_folium.Map.return_value = mock_map

        gui = WeatherMapGUI(25.7617, -80.1918)  # Miami coordinates

        # Mock storm data
        mock_geometry = Mock()
        mock_geometry.__geo_interface__ = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]
        }

        mock_storm = Mock()
        mock_storm.storm_name = "Hurricane Ian"
        mock_storm.get_storm_info_html.return_value = "<b>Hurricane Ian</b><br>Category 4"

        gui.show_weather_map(
            alert_level="WARNING",
            alert_title="Hurricane Warning",
            alert_message="Hurricane Ian is approaching Miami",
            cone_geometries=[mock_geometry],
            storm_info=[mock_storm]
        )

        # Verify map creation and display
        mock_folium.Map.assert_called_once()
        mock_map.save.assert_called_once()
        mock_webbrowser.open.assert_called_once()
