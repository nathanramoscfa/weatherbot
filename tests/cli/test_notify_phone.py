# tests/cli/test_notify_phone.py
"""Tests for ``weatherbot notify test`` with the ``ntfy`` channel off, unconfigured, and on."""

import os

import httpx
import pytest
import respx
from cli_support import FakeToast, parse, run, runtime

from weatherbot.cli.documents import NotifyTestDocument
from weatherbot.services.notifications import TEST_BODY

FAKE_TOPIC = "weatherbot-cli-topic-987654321"


def _fake_token() -> str:
    return f"{'tk'}_{'c' * 29}"


def test_notify_test_with_ntfy_off_omits_ntfy_and_exits_0() -> None:
    toast = FakeToast()
    ran = run(["notify", "test", "--json"], runtime(toast=toast))
    assert ran.exit_code == 0, ran.stderr
    doc = parse(ran, NotifyTestDocument)
    assert not doc.data.failed
    assert doc.data.notification.body == TEST_BODY
    assert [d.channel for d in doc.data.notification.deliveries] == ["log", "toast"]


def test_notify_test_with_ntfy_on_and_unconfigured_exits_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEATHERBOT_NOTIFICATIONS_NTFY", "true")
    monkeypatch.delenv("WEATHERBOT_NTFY_TOPIC", raising=False)
    toast = FakeToast()

    ran = run(["notify", "test"], runtime(toast=toast))
    assert ran.exit_code == 1
    assert "ntfy: unavailable (WEATHERBOT_NTFY_TOPIC is not set)" in ran.stdout

    json_ran = run(["notify", "test", "--json"], runtime(toast=toast))
    assert json_ran.exit_code == 1
    doc = parse(json_ran, NotifyTestDocument)
    assert doc.data.failed is True
    assert [(d.channel, d.result) for d in doc.data.notification.deliveries] == [
        ("log", "delivered"),
        ("toast", "delivered"),
        ("ntfy", "unavailable"),
    ]


def test_notify_test_with_ntfy_on_and_configured_delivers_and_json_holds_no_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _fake_token()
    monkeypatch.setenv("WEATHERBOT_NOTIFICATIONS_NTFY", "true")
    env = {
        **os.environ,
        "WEATHERBOT_NOTIFICATIONS_NTFY": "true",
        "WEATHERBOT_NTFY_TOPIC": FAKE_TOPIC,
        "WEATHERBOT_NTFY_TOKEN": token,
    }
    toast = FakeToast()

    with respx.mock(assert_all_called=True) as router:
        router.post("https://ntfy.sh/").mock(
            return_value=httpx.Response(200, json={"id": "msg-cli"})
        )
        ran = run(["notify", "test", "--json"], runtime(toast=toast, environ=env))

    assert ran.exit_code == 0, ran.stderr
    assert FAKE_TOPIC not in ran.stdout
    assert token not in ran.stdout
    doc = parse(ran, NotifyTestDocument)
    assert not doc.data.failed
    assert [(d.channel, d.result) for d in doc.data.notification.deliveries] == [
        ("log", "delivered"),
        ("toast", "delivered"),
        ("ntfy", "delivered"),
    ]
