# src/weatherbot/services/toast.py
r"""The Windows toast channel, the identity it shows under, and the channel everywhere else.

``ToastChannel`` shows a notification as a Windows toast through pywinrt's
``winrt-Windows.UI.Notifications``: the title, the first two body lines (the in-app log
keeps every line), and the disclaimer's notice as its attribution, under Weatherbot's own
application identity, ``Weatherbot.Monitor``. It reports what Windows said and no more:
``delivered`` when Windows accepted the toast and raised no failure within ``wait_s``;
``failed`` with the HRESULT (or the error's class); ``disabled`` with the notification
setting Windows reports; ``unavailable`` when the identity is not registered. With Do Not
Disturb on, Windows puts a toast straight into the notification center without a banner
and tells the app nothing, so ``delivered`` means accepted, not seen.

An unpackaged app shows toasts under an identity registered as
``HKEY_CURRENT_USER\Software\Classes\AppUserModelId\Weatherbot.Monitor`` with a
``DisplayName``, which needs no administrator rights. ``register_identity()`` writes that
one key, explicitly and idempotently, when ``weatherbot notify setup`` asks; sending never
writes it, nothing under ``HKEY_LOCAL_MACHINE`` is touched, and ``unregister_identity()``
removes the key. Off Windows all three report that no identity is needed.

``NullChannel`` answers ``unavailable`` off Windows and while ``[notifications] toast`` is
off; ``toast_channel(settings)`` picks one. Every ``winreg`` and ``winrt`` import sits inside
``if sys.platform == "win32":``, so the module imports cleanly elsewhere, and the ``winrt``
packages load on the first toast, so a broken install fails a toast, never a command. A
delivery's detail is an HRESULT, an error class, a setting's name, or what to run, never
the notification's text.
"""

import asyncio
import contextlib
import html
import logging
import sys
from collections.abc import Callable
from typing import Final, Literal, Protocol

from weatherbot.services.config import Settings
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.notifications import (
    Channel,
    Delivery,
    DeliveryResult,
    StoredNotification,
)

if sys.platform == "win32":
    import winreg

LOGGER: Final = logging.getLogger("weatherbot.services.toast")

APP_ID: Final = "Weatherbot.Monitor"
DISPLAY_NAME: Final = "Weatherbot"
IDENTITY_KEY: Final = rf"Software\Classes\AppUserModelId\{APP_ID}"
"""The identity's key under ``HKEY_CURRENT_USER``."""
IDENTITY_PATH: Final = rf"HKEY_CURRENT_USER\{IDENTITY_KEY}"
DISPLAY_NAME_VALUE: Final = "DisplayName"

MISSING_IDENTITY: Final = "run weatherbot notify setup"
TOAST_OFF: Final = "turned off by [notifications] toast"
BODY_LINES: Final = 2
CONTROL_CHARACTERS: Final = dict.fromkeys(range(0x20), " ")
DEFAULT_WAIT_S: Final = 2.0
ENABLED: Final = 0
SETTING_NAMES: Final[dict[int, str]] = {
    0: "Enabled",
    1: "DisabledForApplication",
    2: "DisabledForUser",
    3: "DisabledByGroupPolicy",
    4: "DisabledByManifest",
}
"""Windows' ``NotificationSetting`` values, named as its documentation names them."""

type IdentityOutcome = Literal["registered", "unchanged", "removed", "absent", "not_needed"]
type FailureHandler = Callable[[int], None]
"""Hears a toast's failure as its HRESULT; Windows calls it on one of its own threads."""


def hresult_text(code: int) -> str:
    """Spell an HRESULT as Windows documents it: ``0x80070490``.

    Args:
        code: The HRESULT, signed or unsigned.

    Returns:
        Eight hexadecimal digits after ``0x``.
    """
    return f"0x{code & 0xFFFFFFFF:08X}"


def setting_name(setting: int) -> str:
    """Name a ``NotificationSetting`` value.

    Args:
        setting: The value Windows reported.

    Returns:
        Its documented name, or the number for a value this code does not know.
    """
    return SETTING_NAMES.get(setting, f"NotificationSetting {setting}")


def _error_detail(error: OSError) -> str:
    code: object = getattr(error, "winerror", None)
    return hresult_text(code) if isinstance(code, int) else type(error).__name__


def _plain(text: str) -> str:
    """One line of text: a control character would make the toast's XML invalid."""
    return text.translate(CONTROL_CHARACTERS)


def toast_xml(notification: StoredNotification) -> str:
    """Build a notification's toast: its title, two body lines, and the notice.

    Every inserted value passes ``html.escape``, so a storm's or a location's name cannot
    add markup.

    Args:
        notification: The stored notification.

    Returns:
        The ``ToastGeneric`` toast document.
    """
    lines = (notification.title, *notification.body[:BODY_LINES])
    texts = "".join(f"<text>{html.escape(_plain(line))}</text>" for line in lines)
    attribution = f'<text placement="attribution">{html.escape(NOTICE)}</text>'
    return (
        f'<toast><visual><binding template="ToastGeneric">{texts}{attribution}'
        "</binding></visual></toast>"
    )


def delivery_failed(result: DeliveryResult, *, windows: bool, toast_on: bool) -> bool:
    """Say whether a delivery's result means a channel does not work here.

    ``failed`` and ``disabled`` always do. ``unavailable`` does on Windows with the toast
    on, where it means the identity is missing; off Windows, or with the toast off, it is
    what the channel is expected to answer.

    Args:
        result: The delivery's result.
        windows: Whether this machine shows toasts (it needs the identity).
        toast_on: ``[notifications] toast``.

    Returns:
        Whether the result is a failure.
    """
    if result in {"failed", "disabled"}:
        return True
    return result == "unavailable" and windows and toast_on


class Notifier(Protocol):
    """What ``ToastChannel`` needs from Windows' toast notifier: the seam tests replace."""

    def setting(self) -> int:
        """Return Windows' notification setting for the identity.

        Raises ``OSError`` when Windows cannot say (0x80070490, "element not found").
        """
        ...

    def show(self, xml: str, on_failed: FailureHandler) -> Callable[[], None]:
        """Show the toast ``xml`` describes; ``on_failed`` hears its failure, on any thread.

        Returns the function that stops listening, which keeps the toast alive until then.
        """
        ...


type NotifierFactory = Callable[[], Notifier]


class IdentityMissingError(Exception):
    """Weatherbot's application identity is not registered: ``notify setup`` registers it."""


class ToastUnavailableError(Exception):
    """No toast can be shown here; the message names the platform."""


class IdentityStore(Protocol):
    """Where the identity's display name is kept: the registry on Windows; a test's fake."""

    def display_name(self) -> str | None:
        """Return the registered display name: ``None`` without the key, ``""`` without a name."""
        ...

    def write(self, display_name: str) -> None:
        """Register the identity under ``display_name``."""
        ...

    def remove(self) -> None:
        """Remove the identity's key."""
        ...


class Identity:
    """Weatherbot's application identity in a store; without a store, none is needed."""

    def __init__(self, store: IdentityStore | None) -> None:
        """Keep the identity in ``store``.

        Args:
            store: The registry on Windows, a test's fake, or ``None`` off Windows.
        """
        self._store = store

    @property
    def needed(self) -> bool:
        """Whether this machine shows toasts, and so needs the identity."""
        return self._store is not None

    def registered(self) -> bool | None:
        """Say whether the identity is registered.

        Returns:
            ``None`` when no identity is needed.
        """
        if self._store is None:
            return None
        return bool(self._store.display_name())

    def register(self) -> IdentityOutcome:
        """Register the identity, unless it is registered already.

        Returns:
            ``registered``, ``unchanged``, or ``not_needed``.
        """
        if self._store is None:
            return "not_needed"
        if self._store.display_name() == DISPLAY_NAME:
            return "unchanged"
        self._store.write(DISPLAY_NAME)
        LOGGER.info("toast identity %s registered", APP_ID)
        return "registered"

    def unregister(self) -> IdentityOutcome:
        """Remove the identity, if it is registered.

        Returns:
            ``removed``, ``absent``, or ``not_needed``.
        """
        if self._store is None:
            return "not_needed"
        if self._store.display_name() is None:
            return "absent"
        self._store.remove()
        LOGGER.info("toast identity %s removed", APP_ID)
        return "removed"


if sys.platform == "win32":

    class _RegistryStore:
        """The identity's key under ``HKEY_CURRENT_USER``: the only registry writer."""

        def display_name(self) -> str | None:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, IDENTITY_KEY)
            except FileNotFoundError:
                return None
            with key:
                try:
                    value, kind = winreg.QueryValueEx(key, DISPLAY_NAME_VALUE)
                except FileNotFoundError:
                    return ""
            return value if kind == winreg.REG_SZ and isinstance(value, str) else ""

        def write(self, display_name: str) -> None:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, IDENTITY_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, DISPLAY_NAME_VALUE, 0, winreg.REG_SZ, display_name)

        def remove(self) -> None:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, IDENTITY_KEY)

    class _WindowsNotifier:
        """Windows' toast notifier for Weatherbot's identity, through pywinrt."""

        def __init__(self) -> None:
            from winrt.windows.ui.notifications import (  # noqa: PLC0415 - loaded on the first toast
                ToastNotificationManager,
            )

            self._notifier = ToastNotificationManager.create_toast_notifier_with_id(APP_ID)

        def setting(self) -> int:
            return int(self._notifier.setting)

        def show(self, xml: str, on_failed: FailureHandler) -> Callable[[], None]:
            from winrt.windows.data.xml.dom import XmlDocument  # noqa: PLC0415 - loaded on the first toast
            from winrt.windows.ui.notifications import (  # noqa: PLC0415 - loaded on the first toast
                ToastFailedEventArgs,
                ToastNotification,
            )

            document = XmlDocument()
            document.load_xml(xml)
            toast = ToastNotification(document)

            def failed(_: ToastNotification, args: ToastFailedEventArgs) -> None:
                on_failed(args.error_code.value)

            token = toast.add_failed(failed)
            self._notifier.show(toast)
            return lambda: toast.remove_failed(token)


def system_identity() -> Identity:
    """Return the identity in this machine's store: the registry on Windows, none elsewhere.

    Returns:
        The identity.
    """
    if sys.platform == "win32":
        return Identity(_RegistryStore())
    return Identity(None)


def register_identity() -> IdentityOutcome:
    """Register the identity under ``HKEY_CURRENT_USER``, unless it is registered already.

    Returns:
        ``registered``, ``unchanged``, or ``not_needed`` off Windows.
    """
    return system_identity().register()


def unregister_identity() -> IdentityOutcome:
    """Remove the identity's key from ``HKEY_CURRENT_USER``, if it is there.

    Returns:
        ``removed``, ``absent``, or ``not_needed`` off Windows.
    """
    return system_identity().unregister()


def identity_registered() -> bool | None:
    """Say whether the identity is registered under ``HKEY_CURRENT_USER``.

    Returns:
        ``None`` off Windows, where no identity is needed.
    """
    return system_identity().registered()


def system_notifier() -> Notifier:
    """Return Windows' toast notifier for Weatherbot's identity.

    Returns:
        The notifier.

    Raises:
        IdentityMissingError: The identity is not registered.
        ToastUnavailableError: This is not Windows.
    """
    if sys.platform != "win32":
        raise ToastUnavailableError(sys.platform)
    if not identity_registered():
        raise IdentityMissingError
    return _WindowsNotifier()


def _settle(failure: asyncio.Future[int], code: int) -> None:
    if not failure.done():
        failure.set_result(code)


class ToastChannel:
    """The Windows toast channel: shows a notification and says what Windows did with it."""

    def __init__(
        self, notifier_factory: NotifierFactory = system_notifier, wait_s: float = DEFAULT_WAIT_S
    ) -> None:
        """Create the channel; nothing touches Windows until a delivery.

        Args:
            notifier_factory: Returns Windows' notifier; tests hand over a fake.
            wait_s: How long a delivery waits for Windows to report a failure.
        """
        self._factory = notifier_factory
        self._wait_s = wait_s

    @property
    def name(self) -> str:
        """The channel's identifier."""
        return "toast"

    @property
    def interrupts(self) -> bool:
        """A desktop toast interrupts the operator."""
        return True

    async def deliver(self, notification: StoredNotification) -> Delivery:
        """Show the toast and report Windows' answer; never raise.

        Args:
            notification: The stored notification.

        Returns:
            ``delivered``, ``failed``, ``disabled``, or ``unavailable``, with its detail.
        """
        try:
            return await self._deliver(notification)
        except IdentityMissingError:
            return Delivery("unavailable", MISSING_IDENTITY)
        except ToastUnavailableError as error:
            return Delivery("unavailable", str(error))
        except OSError as error:
            return Delivery("failed", _error_detail(error))
        except Exception as error:  # noqa: BLE001 - a channel reports its failure; it never fails the cycle
            return Delivery("failed", type(error).__name__)

    async def _deliver(self, notification: StoredNotification) -> Delivery:
        notifier = self._factory()
        try:
            setting = notifier.setting()
        except OSError as error:
            LOGGER.debug("toast: Windows did not say its setting (%s)", _error_detail(error))
        else:
            if setting != ENABLED:
                return Delivery("disabled", setting_name(setting))
        loop = asyncio.get_running_loop()
        failure: asyncio.Future[int] = loop.create_future()

        def on_failed(code: int) -> None:
            # Windows calls this on its own thread; the loop may have closed after the wait.
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(_settle, failure, code)

        stop_listening = notifier.show(toast_xml(notification), on_failed)
        try:
            code = await asyncio.wait_for(failure, self._wait_s)
        except TimeoutError:
            return Delivery("delivered")
        finally:
            with contextlib.suppress(OSError):
                stop_listening()
        return Delivery("failed", hresult_text(code))


class NullChannel:
    """The toast channel where there is none: always ``unavailable``, saying why."""

    def __init__(self, reason: str = sys.platform) -> None:
        """Answer every delivery with ``reason``.

        Args:
            reason: The platform's name, or that the toast is turned off.
        """
        self._reason = reason

    @property
    def name(self) -> str:
        """The channel's identifier."""
        return "toast"

    @property
    def interrupts(self) -> bool:
        """A desktop toast interrupts the operator."""
        return True

    async def deliver(self, notification: StoredNotification) -> Delivery:
        """Answer ``unavailable``.

        Args:
            notification: The stored notification, which goes nowhere.

        Returns:
            ``unavailable`` with the reason.
        """
        del notification
        return Delivery("unavailable", self._reason)


def toast_channel(settings: Settings) -> Channel:
    """Return the toast channel for these settings on this machine.

    Args:
        settings: The effective settings.

    Returns:
        ``ToastChannel`` on Windows with ``[notifications] toast`` on, else ``NullChannel``.
    """
    if not settings.notifications.toast:
        return NullChannel(TOAST_OFF)
    if sys.platform == "win32":
        return ToastChannel()
    return NullChannel()
