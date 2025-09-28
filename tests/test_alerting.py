# tests/test_alerting.py
"""Alerting tests for weatherbot."""

from unittest.mock import Mock, patch

from weatherbot.alerting import AlertManager, create_alert_manager
from weatherbot.config import WeatherbotConfig


class TestAlertManager:
    """Test AlertManager class."""

    def test_init(self) -> None:
        """Test AlertManager initialization."""
        config = WeatherbotConfig(home_lat=25.7617, home_lon=-80.1918)

        with patch('weatherbot.alerting.ToastNotifier') as mock_toast:

            manager = AlertManager(config)

            assert manager.config == config
            mock_toast.assert_called_once()

    def test_raise_alert_toast_enabled(self) -> None:
        """Test raising alert with toast enabled."""
        config = WeatherbotConfig(home_lat=25.7617, home_lon=-80.1918)
        config.toast_enabled = True

        with patch('weatherbot.alerting.ToastNotifier') as mock_toast_class:

            mock_toast = Mock()
            mock_toast_class.return_value = mock_toast

            manager = AlertManager(config)

            manager.raise_alert(
                level="WARNING",
                title="Test Alert",
                message="Test message",
                duration=10
            )

            mock_toast.show_notification.assert_called_once_with(
                title="Test Alert",
                message="Test message",
                duration=10
            )


    def test_raise_alert_with_cone_geometries(self) -> None:
        """Test raising alert with cone geometries."""
        config = WeatherbotConfig(home_lat=25.7617, home_lon=-80.1918)
        config.toast_enabled = True

        cone_geometries = [{"type": "Polygon", "coordinates": [[[-80, 25], [-79, 26]]]}]
        storm_info = [{"name": "Hurricane Ian", "category": 3}]

        with patch('weatherbot.alerting.ToastNotifier') as mock_toast_class:

            mock_toast = Mock()
            mock_toast_class.return_value = mock_toast

            manager = AlertManager(config)

            manager.raise_alert(
                level="WARNING",
                title="Test Alert",
                message="Test message",
                cone_geometries=cone_geometries,
                storm_info=storm_info
            )

            mock_toast.show_notification.assert_called_once_with(
                title="Test Alert",
                message="Test message",
                duration=15
            )

    def test_raise_alert_toast_error(self) -> None:
        """Test raising alert when toast fails."""
        config = WeatherbotConfig(home_lat=25.7617, home_lon=-80.1918)
        config.toast_enabled = True

        with patch('weatherbot.alerting.ToastNotifier') as mock_toast_class:

            mock_toast = Mock()
            mock_toast.show_notification.side_effect = Exception("Toast error")
            mock_toast_class.return_value = mock_toast

            manager = AlertManager(config)

            # Should not raise exception
            manager.raise_alert(
                level="WARNING",
                title="Test Alert",
                message="Test message"
            )


    def test_raise_alert_toast_disabled(self) -> None:
        """Test raising alert when toast is disabled."""
        config = WeatherbotConfig(home_lat=25.7617, home_lon=-80.1918)
        config.toast_enabled = False

        with patch('weatherbot.alerting.ToastNotifier') as mock_toast_class:

            mock_toast = Mock()
            mock_toast_class.return_value = mock_toast

            manager = AlertManager(config)

            # Should not raise exception even if toast is disabled
            manager.raise_alert(
                level="WARNING",
                title="Test Alert",
                message="Test message"
            )

            # Toast should not be called
            mock_toast.show_notification.assert_not_called()

    def test_test_notifications(self) -> None:
        """Test notification testing functionality."""
        config = WeatherbotConfig(home_lat=25.7617, home_lon=-80.1918)
        config.toast_enabled = True

        with patch('weatherbot.alerting.ToastNotifier') as mock_toast_class:

            mock_toast = Mock()
            mock_toast.show_notification.return_value = True
            mock_toast_class.return_value = mock_toast

            manager = AlertManager(config)

            # Should not raise exception
            manager.test_notifications()

            mock_toast.show_notification.assert_called_once()

    def test_test_notifications_toast_disabled(self) -> None:
        """Test notification testing with toast disabled."""
        config = WeatherbotConfig(home_lat=25.7617, home_lon=-80.1918)
        config.toast_enabled = False

        with patch('weatherbot.alerting.ToastNotifier') as mock_toast_class:

            mock_toast = Mock()
            mock_toast_class.return_value = mock_toast

            manager = AlertManager(config)

            manager.test_notifications()

            # Toast should not be called
            mock_toast.show_notification.assert_not_called()



class TestCreateAlertManager:
    """Test create_alert_manager function."""

    def test_create_alert_manager(self) -> None:
        """Test creating alert manager."""
        config = WeatherbotConfig(home_lat=25.7617, home_lon=-80.1918)

        with patch('weatherbot.alerting.AlertManager') as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            result = create_alert_manager(config)

            assert result == mock_manager
            mock_manager_class.assert_called_once_with(config)
