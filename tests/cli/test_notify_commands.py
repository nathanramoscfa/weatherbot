# tests/cli/test_notify_commands.py
"""``notify test`` and ``notify setup``, with a fake toast and a fake registry.

``notify test`` stores a test notification that names no location, delivers it through the
log and the toast, and exits 1 when a channel failed or was disabled, or when the toast was
unavailable on Windows with the toast on. ``notify setup`` registers and removes the
identity in the fake registry and says which. No test here reaches Windows.
"""

from typing import Final

import pytest
from cli_support import FakeRegistry, FakeToast, parse, run, runtime

from weatherbot.cli.documents import NotificationsDocument, NotifySetupDocument, NotifyTestDocument
from weatherbot.services.notifications import TEST_BODY, TEST_TITLE, DeliveryResult
from weatherbot.services.toast import APP_ID, DISPLAY_NAME, IDENTITY_PATH, Identity

FAILED: Final = 1
TOAST_ON: Final = "WEATHERBOT_NOTIFICATIONS_TOAST"


class RefusingRegistry(FakeRegistry):
    """A registry that refuses every write, as one locked by policy would."""

    def write(self, display_name: str) -> None:
        """Refuse."""
        del display_name
        message = "access is denied"
        raise PermissionError(message)


def test_notify_test_stores_a_test_notification_and_delivers_it_through_both_channels() -> None:
    toast = FakeToast()

    ran = run(["notify", "test"], runtime(toast=toast))

    assert ran.exit_code == 0, ran.stderr
    assert f"Sent a test notification: {TEST_TITLE}" in ran.stdout
    assert "  log: delivered" in ran.stdout
    assert "  toast: delivered" in ran.stdout
    assert [(item.title, item.body, item.location_name) for item in toast.handed] == [
        (TEST_TITLE, TEST_BODY, None)
    ]
    log = parse(run(["notify", "log", "--json"]), NotificationsDocument)
    (stored,) = log.data.notifications
    assert (stored.kind, stored.location, stored.level, stored.title) == (
        "test",
        None,
        None,
        TEST_TITLE,
    )
    assert [(d.channel, d.result) for d in stored.deliveries] == [
        ("log", "delivered"),
        ("toast", "delivered"),
    ]


def test_notify_test_json_validates_and_names_each_delivery() -> None:
    document = parse(run(["notify", "test", "--json"]), NotifyTestDocument)

    assert document.command == "notify test"
    assert not document.data.failed
    assert document.data.notification.kind == "test"
    assert document.data.notification.body == TEST_BODY
    assert [d.channel for d in document.data.notification.deliveries] == ["log", "toast"]


@pytest.mark.parametrize(
    ("result", "detail"),
    [("failed", "0x80070490"), ("disabled", "DisabledForUser")],
)
def test_notify_test_exits_1_when_the_toast_failed_or_was_disabled(
    result: DeliveryResult, detail: str
) -> None:
    toast = FakeToast(result, detail)

    ran = run(["notify", "test"], runtime(toast=toast))
    document = parse(run(["notify", "test", "--json"], runtime(toast=toast)), NotifyTestDocument)

    assert ran.exit_code == FAILED
    assert f"  toast: {result} ({detail})" in ran.stdout
    assert "FAILED: a channel did not deliver it" in ran.stdout
    assert document.data.failed


def test_an_unavailable_toast_fails_on_windows_only_with_the_toast_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = FakeToast("unavailable", "run weatherbot notify setup")
    windows = Identity(FakeRegistry())

    # tests/conftest.py turns the toast off: unavailable is then what is expected.
    assert run(["notify", "test"], runtime(toast=missing, identity=windows)).exit_code == 0
    monkeypatch.setenv(TOAST_ON, "true")
    on_windows = run(["notify", "test"], runtime(toast=missing, identity=windows))
    elsewhere = run(["notify", "test"], runtime(toast=FakeToast("unavailable", "linux")))
    off_windows = run(
        ["notify", "test"],
        runtime(toast=FakeToast("unavailable", "linux"), identity=Identity(None)),
    )

    assert on_windows.exit_code == FAILED
    assert "  toast: unavailable (run weatherbot notify setup)" in on_windows.stdout
    # The default runtime is a Windows machine whose identity is registered.
    assert elsewhere.exit_code == FAILED
    assert off_windows.exit_code == 0
    assert "  toast: unavailable (linux)" in off_windows.stdout


def test_notify_setup_registers_once_and_remove_removes_once() -> None:
    registry = FakeRegistry()
    rt = runtime(identity=Identity(registry))

    first = run(["notify", "setup"], rt)
    again = run(["notify", "setup"], rt)
    document = parse(run(["notify", "setup", "--json"], rt), NotifySetupDocument)

    assert (first.exit_code, again.exit_code) == (0, 0)
    assert first.stdout.strip() == (
        f"Registered the toast identity {APP_ID} ({DISPLAY_NAME}) at {IDENTITY_PATH}."
    )
    assert "is registered already; nothing changed" in again.stdout
    assert (registry.value, registry.writes) == (DISPLAY_NAME, 1)
    assert (document.data.action, document.data.outcome) == ("register", "unchanged")
    assert document.data.registry_key == IDENTITY_PATH

    removed = run(["notify", "setup", "--remove"], rt)
    gone = parse(run(["notify", "setup", "--remove", "--json"], rt), NotifySetupDocument)

    assert removed.exit_code == 0
    assert removed.stdout.strip() == f"Removed the toast identity {APP_ID} from {IDENTITY_PATH}."
    assert (gone.data.action, gone.data.outcome) == ("remove", "absent")
    assert (registry.value, registry.removals) == (None, 1)


def test_notify_setup_off_windows_changes_nothing() -> None:
    rt = runtime(identity=Identity(None))

    ran = run(["notify", "setup"], rt)
    document = parse(run(["notify", "setup", "--remove", "--json"], rt), NotifySetupDocument)

    assert ran.exit_code == 0
    assert ran.stdout.strip() == "Not Windows: toasts need no identity here, and nothing changed."
    assert (document.data.outcome, document.data.registry_key) == ("not_needed", None)


def test_a_refused_registry_write_exits_1_and_names_only_the_error_class() -> None:
    ran = run(["notify", "setup"], runtime(identity=Identity(RefusingRegistry())))

    assert ran.exit_code == FAILED
    assert "the registry refused the change (PermissionError)" in ran.stderr
    assert "access is denied" not in ran.stderr
