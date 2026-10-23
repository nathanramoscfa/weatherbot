# tests/services/test_toast.py
"""``ToastChannel``, ``NullChannel``, the toast's XML, and the toast's application identity.

Every test runs on Windows and Ubuntu alike: a fake notifier stands in for Windows' and a
fake store for the registry, so no test shows a toast or writes the registry. A real toast
is the ``desktop`` test's (``tests/desktop/test_toast_desktop.py``).
"""

import ast
import asyncio
import re
import subprocess
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest
from cli_support import FakeRegistry

from weatherbot.services import toast
from weatherbot.services.config import AppPaths, NotificationSettings, Settings, load_settings
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.notifications import (
    TEST_BODY,
    TEST_TITLE,
    Channel,
    Delivery,
    StoredNotification,
)
from weatherbot.services.toast import (
    APP_ID,
    DISPLAY_NAME,
    ENABLED,
    MISSING_IDENTITY,
    TOAST_OFF,
    FailureHandler,
    Identity,
    IdentityMissingError,
    NullChannel,
    ToastChannel,
    ToastUnavailableError,
    delivery_failed,
    toast_channel,
    toast_xml,
)

SOURCE: Final = Path(__file__).resolve().parents[2] / "src" / "weatherbot"
QUICK_S: Final = 0.01
ELEMENT_NOT_FOUND: Final = -2147023728  # 0x80070490, as pywinrt reports it: signed
NOTIFICATION_DISABLED: Final = 0x803E0111
REGISTRY_WRITES: Final = frozenset(
    {
        "SetValue",
        "SetValueEx",
        "CreateKey",
        "CreateKeyEx",
        "DeleteKey",
        "DeleteKeyEx",
        "DeleteValue",
    }
)


def _notification(title: str = TEST_TITLE, body: tuple[str, ...] = TEST_BODY) -> StoredNotification:
    return StoredNotification(
        id=1,
        location_name=None,
        location_time_zone=None,
        assessment_id=None,
        cycle_id=None,
        kind="test",
        level=None,
        escalation=False,
        title=title,
        body=body,
        created_at=datetime(2026, 10, 23, 12, tzinfo=UTC),
    )


class HResultError(OSError):
    """An ``OSError`` that carries an HRESULT on every platform, as pywinrt's do on Windows."""

    # Shadows ``OSError.winerror`` (a slot on Windows, absent elsewhere), so each instance's
    # own value is read on both platforms.
    winerror = 0

    def __init__(self, code: int) -> None:
        """Carry ``code``."""
        super().__init__("a WinRT call failed")
        self.winerror = code


class FakeNotifier:
    """Windows' notifier as the channel sees it: a setting, ``show``, and ``Failed``."""

    def __init__(
        self,
        *,
        setting: int | OSError = ENABLED,
        show_error: Exception | None = None,
        fail_with: int | None = None,
        fail_after_s: float = 0.0,
    ) -> None:
        """Answer with ``setting``, raise ``show_error``, or raise ``Failed`` after a delay."""
        self._setting = setting
        self._show_error = show_error
        self._fail_with = fail_with
        self._fail_after_s = fail_after_s
        self.shown: list[str] = []
        self.handler_threads: list[str] = []
        self.timers: list[threading.Timer] = []
        self.listening = False

    def setting(self) -> int:
        """The configured setting, or its ``OSError``."""
        if isinstance(self._setting, OSError):
            raise self._setting
        return self._setting

    def show(self, xml: str, on_failed: FailureHandler) -> Callable[[], None]:
        """Record the toast, and raise its failure from a timer thread when configured."""
        if self._show_error is not None:
            raise self._show_error
        self.shown.append(xml)
        self.listening = True
        if self._fail_with is not None:
            code = self._fail_with

            def fail() -> None:
                self.handler_threads.append(threading.current_thread().name)
                on_failed(code)

            # Windows raises Failed on one of its own threads, after show has returned.
            timer = threading.Timer(self._fail_after_s, fail)
            self.timers.append(timer)
            timer.start()
        return self._stop

    def _stop(self) -> None:
        self.listening = False


def _deliver(channel: Channel) -> Delivery:
    return asyncio.run(channel.deliver(_notification()))


def _channel(notifier: FakeNotifier, wait_s: float = QUICK_S) -> ToastChannel:
    return ToastChannel(notifier_factory=lambda: notifier, wait_s=wait_s)


# The toast's XML --------------------------------------------------------------------------


def test_toast_xml_escapes_markup_in_the_title_and_lines_and_carries_the_notice() -> None:
    xml = toast_xml(
        _notification(
            'Storm <b>"Ana"</b> & co',
            ("Line <1> & 'quoted'", "Line 2", "Line 3 stays in the log"),
        )
    )

    assert "<b>" not in xml
    assert "&lt;b&gt;&quot;Ana&quot;&lt;/b&gt; &amp; co" in xml
    assert "Line &lt;1&gt; &amp; &#x27;quoted&#x27;" in xml
    assert "Line 3" not in xml
    assert f'<text placement="attribution">{NOTICE}</text>' in xml
    assert xml.startswith('<toast><visual><binding template="ToastGeneric">')
    # The title and two lines, then the attribution: three text elements and the notice.
    assert xml.count("<text") == 4  # noqa: PLR2004 - title, two lines, attribution


def test_toast_xml_turns_control_characters_into_spaces() -> None:
    xml = toast_xml(_notification("Title\x07bell", ("one\ntwo",)))

    assert "<text>Title bell</text>" in xml
    assert "<text>one two</text>" in xml


# Delivery results -------------------------------------------------------------------------


def test_an_enabled_setting_delivers_and_stops_listening_after_the_wait() -> None:
    notifier = FakeNotifier()

    assert _deliver(_channel(notifier)) == Delivery("delivered")
    assert notifier.shown == [toast_xml(_notification())]
    assert not notifier.listening


@pytest.mark.parametrize(
    ("setting", "name"),
    [
        (1, "DisabledForApplication"),
        (2, "DisabledForUser"),
        (3, "DisabledByGroupPolicy"),
        (4, "DisabledByManifest"),
        (9, "NotificationSetting 9"),
    ],
)
def test_each_disabled_setting_is_disabled_with_its_name_and_shows_nothing(
    setting: int, name: str
) -> None:
    notifier = FakeNotifier(setting=setting)

    assert _deliver(_channel(notifier)) == Delivery("disabled", name)
    assert notifier.shown == []


def test_a_setting_windows_cannot_read_still_delivers() -> None:
    notifier = FakeNotifier(setting=HResultError(ELEMENT_NOT_FOUND))

    assert _deliver(_channel(notifier)) == Delivery("delivered")
    assert len(notifier.shown) == 1


def test_an_exception_from_show_is_failed_with_its_hresult_in_hexadecimal() -> None:
    notifier = FakeNotifier(show_error=HResultError(ELEMENT_NOT_FOUND))

    assert _deliver(_channel(notifier)) == Delivery("failed", "0x80070490")


def test_an_error_without_an_hresult_is_failed_with_its_class() -> None:
    assert _deliver(_channel(FakeNotifier(show_error=OSError("no code")))) == Delivery(
        "failed", "OSError"
    )
    assert _deliver(_channel(FakeNotifier(show_error=ValueError("bad xml")))) == Delivery(
        "failed", "ValueError"
    )


def test_a_failed_event_raised_from_another_thread_is_failed_with_its_hresult() -> None:
    notifier = FakeNotifier(fail_with=NOTIFICATION_DISABLED, fail_after_s=0.05)

    delivery = _deliver(_channel(notifier, wait_s=10.0))

    assert delivery == Delivery("failed", "0x803E0111")
    assert notifier.handler_threads
    assert notifier.handler_threads[0] != threading.main_thread().name
    assert not notifier.listening


def test_a_failure_after_the_wait_leaves_the_delivery_delivered() -> None:
    notifier = FakeNotifier(fail_with=NOTIFICATION_DISABLED, fail_after_s=0.2)

    assert _deliver(_channel(notifier)) == Delivery("delivered")
    # The late handler finds the loop closed and is ignored: an exception on its thread
    # would fail the test (filterwarnings = error).
    for timer in notifier.timers:
        timer.join()
    assert len(notifier.handler_threads) == 1


def test_a_missing_identity_is_unavailable_and_names_the_setup_command() -> None:
    def missing() -> FakeNotifier:
        raise IdentityMissingError

    assert _deliver(ToastChannel(notifier_factory=missing)) == Delivery(
        "unavailable", MISSING_IDENTITY
    )
    assert MISSING_IDENTITY == "run weatherbot notify setup"


def test_off_windows_the_system_notifier_is_unavailable_with_the_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def elsewhere() -> FakeNotifier:
        platform = "linux"
        raise ToastUnavailableError(platform)

    assert _deliver(ToastChannel(notifier_factory=elsewhere)) == Delivery("unavailable", "linux")
    # Never a real ToastChannel's delivery here: on the operator's machine it would show.
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(ToastUnavailableError, match="linux"):
        toast.system_notifier()


def test_the_null_channel_is_always_unavailable() -> None:
    assert NullChannel().name == "toast"
    assert _deliver(NullChannel()) == Delivery("unavailable", sys.platform)
    assert _deliver(NullChannel(TOAST_OFF)) == Delivery("unavailable", TOAST_OFF)


def test_delivery_failed_reads_unavailable_as_a_failure_only_on_windows_with_the_toast_on() -> None:
    for result in ("failed", "disabled"):
        assert delivery_failed(result, windows=False, toast_on=False)
    assert not delivery_failed("delivered", windows=True, toast_on=True)
    assert delivery_failed("unavailable", windows=True, toast_on=True)
    assert not delivery_failed("unavailable", windows=False, toast_on=True)
    assert not delivery_failed("unavailable", windows=True, toast_on=False)


# Picking the channel ----------------------------------------------------------------------


def test_toast_channel_honours_the_toast_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    on = Settings()
    off = Settings(notifications=NotificationSettings(toast=False))

    expected = ToastChannel if sys.platform == "win32" else NullChannel
    assert isinstance(toast_channel(on), expected)
    assert toast_channel(on).name == "toast"
    assert _deliver(toast_channel(off)) == Delivery("unavailable", TOAST_OFF)

    monkeypatch.setattr(sys, "platform", "linux")
    assert isinstance(toast_channel(on), NullChannel)


def test_the_toast_setting_reads_the_file_and_its_override() -> None:
    paths = AppPaths.resolve()
    paths.config_dir.mkdir(parents=True)
    paths.settings_path.write_text("[notifications]\ntoast = false\n", encoding="utf-8")

    assert Settings().notifications.toast
    assert not load_settings(paths, {}).notifications.toast
    assert load_settings(paths, {"WEATHERBOT_NOTIFICATIONS_TOAST": "true"}).notifications.toast


# The application identity -----------------------------------------------------------------


def test_register_writes_the_display_name_once_and_unregister_removes_it_once() -> None:
    registry = FakeRegistry()
    identity = Identity(registry)

    assert identity.needed
    assert identity.registered() is False
    assert identity.register() == "registered"
    assert identity.register() == "unchanged"
    assert (registry.value, registry.writes) == (DISPLAY_NAME, 1)
    assert identity.registered() is True
    assert identity.unregister() == "removed"
    assert identity.unregister() == "absent"
    assert (registry.value, registry.removals) == (None, 1)


def test_a_key_without_a_display_name_is_not_registered_and_register_fixes_it() -> None:
    registry = FakeRegistry("")
    identity = Identity(registry)

    assert identity.registered() is False
    assert identity.register() == "registered"
    assert identity.registered() is True


def test_without_a_store_no_identity_is_needed_and_nothing_is_touched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = Identity(None)
    assert (identity.needed, identity.registered()) == (False, None)
    assert identity.register() == identity.unregister() == "not_needed"

    monkeypatch.setattr(sys, "platform", "linux")
    assert toast.register_identity() == "not_needed"
    assert toast.unregister_identity() == "not_needed"
    assert toast.identity_registered() is None


def test_sending_reads_the_identity_and_never_writes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = FakeRegistry()
    monkeypatch.setattr(toast, "system_identity", lambda: Identity(registry))
    monkeypatch.setattr(sys, "platform", "win32")

    # The system notifier a real ToastChannel sends through refuses before reaching Windows.
    with pytest.raises(IdentityMissingError):
        toast.system_notifier()
    assert (registry.value, registry.writes, registry.removals) == (None, 0, 0)
    assert APP_ID == "Weatherbot.Monitor"
    assert toast.IDENTITY_PATH == (
        r"HKEY_CURRENT_USER\Software\Classes\AppUserModelId\Weatherbot.Monitor"
    )


def test_only_the_registry_store_writes_the_registry_and_only_under_hkcu() -> None:
    writers: list[str] = []
    hives: set[str] = set()
    for path in sorted(SOURCE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr.startswith("HKEY_"):
                hives.add(node.attr)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in REGISTRY_WRITES
            ):
                writers.append(f"{path.relative_to(SOURCE).as_posix()}:{node.func.attr}")

    assert sorted(writers) == [
        "services/toast.py:CreateKeyEx",
        "services/toast.py:DeleteKey",
        "services/toast.py:SetValueEx",
    ]
    assert hives == {"HKEY_CURRENT_USER"}
    source = (SOURCE / "services" / "toast.py").read_text(encoding="utf-8")
    store = source.split("class _RegistryStore:", 1)[1].split("class _WindowsNotifier:", 1)[0]
    assert all(name in store for name in ("CreateKeyEx", "SetValueEx", "DeleteKey"))
    assert re.findall(r"winreg\.HKEY_\w+", source) == ["winreg.HKEY_CURRENT_USER"] * 3


def test_importing_the_toast_module_loads_no_winrt_package() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, weatherbot.services.toast; "
                "print(sorted(m for m in sys.modules if m.split('.')[0] == 'winrt'))"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    # pywinrt loads on the first toast, never on import, so neither Ubuntu nor Windows
    # imports a winrt module here.
    assert ast.literal_eval(completed.stdout.strip()) == []
