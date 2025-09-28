# src/weatherbot/notifiers/toast.py
"""Windows toast notifications."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ToastNotifier:
    """Windows toast notification handler."""

    def __init__(self, icon_path: Path | None = None) -> None:
        """Initialize toast notifier.

        Args:
            icon_path: Path to notification icon
        """
        self.icon_path = icon_path
        self._toast_lib = self._get_toast_library()

    def _get_toast_library(self) -> object | None:
        """Get the best available toast notification library.

        Returns:
            Toast notification library or None if unavailable
        """
        try:
            # Try win11toast first (best features)
            import win11toast
            logger.debug("Using win11toast for notifications")
            return win11toast
        except ImportError:
            pass

        try:
            # Fallback to winotify
            import winotify
            logger.debug("Using winotify for notifications")
            return winotify
        except ImportError:
            pass

        try:
            # Last resort: win10toast
            from win10toast import ToastNotifier as Win10Toast
            logger.debug("Using win10toast for notifications")
            return Win10Toast()
        except ImportError:
            pass

        logger.warning("No toast notification library available")
        return None

    def show_notification(
        self,
        title: str,
        message: str,
        duration: int = 10,
    ) -> bool:
        """Show a toast notification.

        Args:
            title: Notification title
            message: Notification message
            duration: Display duration in seconds

        Returns:
            True if notification was shown successfully
        """
        if not self._toast_lib:
            logger.warning("Cannot show toast: no notification library available")
            return False

        try:
            # Handle different libraries
            if hasattr(self._toast_lib, "notify"):
                # win11toast
                self._show_win11toast(title, message, duration)
            elif hasattr(self._toast_lib, "Notification"):
                # winotify
                self._show_winotify(title, message, duration)
            else:
                # win10toast
                self._show_win10toast(title, message, duration)

            logger.info(f"Showed toast notification: {title}")
            return True

        except Exception as e:
            logger.error(f"Failed to show toast notification: {e}")
            return False

    def _show_win11toast(self, title: str, message: str, duration: int) -> None:
        """Show notification using win11toast.

        Args:
            title: Notification title
            message: Notification message
            duration: Display duration in seconds
        """
        kwargs = {
            "title": title,
            "body": message,
            "duration": "long",  # win11toast uses 'short' or 'long'
        }

        if self.icon_path and self.icon_path.exists():
            kwargs["icon"] = str(self.icon_path)

        self._toast_lib.notify(**kwargs)

    def _show_winotify(self, title: str, message: str, duration: int) -> None:
        """Show notification using winotify.

        Args:
            title: Notification title
            message: Notification message
            duration: Display duration in seconds
        """
        toast = self._toast_lib.Notification(
            app_id="weatherbot",
            title=title,
            msg=message,
            duration=duration,
        )

        if self.icon_path and self.icon_path.exists():
            toast.set_icon(str(self.icon_path))

        toast.show()

    def _show_win10toast(self, title: str, message: str, duration: int) -> None:
        """Show notification using win10toast.

        Args:
            title: Notification title
            message: Notification message
            duration: Display duration in seconds
        """
        kwargs = {
            "title": title,
            "msg": message,
            "duration": duration,
            "threaded": True,
        }

        if self.icon_path and self.icon_path.exists():
            kwargs["icon_path"] = str(self.icon_path)

        self._toast_lib.show_toast(**kwargs)
