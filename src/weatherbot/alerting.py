# src/weatherbot/alerting.py
"""Central alerting coordination for Weatherbot."""

import logging

from .config import WeatherbotConfig
from .notifiers.toast import ToastNotifier

logger = logging.getLogger(__name__)


class AlertManager:
    """Manages all alert delivery methods."""

    def __init__(self, config: WeatherbotConfig) -> None:
        """Initialize alert manager.

        Args:
            config: Weatherbot configuration
        """
        self.config = config

        # Initialize notifiers
        icon_path = config.get_alert_icon_path()
        self.toast_notifier = ToastNotifier(icon_path=icon_path)

    def raise_alert(
        self,
        level: str,
        title: str,
        message: str,
        duration: int = 15,
        cone_geometries: list | None = None,
        storm_info: list | None = None,
    ) -> None:
        """Raise an alert using configured notification methods.

        Args:
            level: Alert level (CONE, WATCH, WARNING)
            title: Alert title
            message: Alert message
            duration: Notification duration in seconds
            cone_geometries: Hurricane cone geometries for map display
            storm_info: Storm information for map display
        """
        logger.warning(f"ALERT [{level}]: {title} - {message}")

        # Show toast if enabled
        if self.config.toast_enabled:
            try:
                self.toast_notifier.show_notification(
                    title=title,
                    message=message,
                    duration=duration,
                )
            except Exception as e:
                logger.error(f"Failed to show toast notification: {e}")

    def test_notifications(self) -> None:
        """Test all notification methods."""
        test_title = "🚨 WEATHERBOT TEST ALERT"
        test_message = "Toast notification test - system is working!"

        logger.info("Testing notification systems...")

        # Test toast
        if self.config.toast_enabled:
            try:
                success = self.toast_notifier.show_notification(
                    title=test_title,
                    message=test_message,
                    duration=5,
                )
                if success:
                    logger.info("✅ Toast notification test successful")
                else:
                    logger.warning("❌ Toast notification test failed")
            except Exception as e:
                logger.error(f"❌ Toast notification test error: {e}")
        else:
            logger.info("Toast notifications are disabled")

        logger.info("Notification test completed")


def create_alert_manager(config: WeatherbotConfig) -> AlertManager:
    """Create an alert manager instance.

    Args:
        config: Weatherbot configuration

    Returns:
        Configured alert manager
    """
    return AlertManager(config)
