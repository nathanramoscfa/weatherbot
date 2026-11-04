# tests/services/test_ntfy.py
"""Tests for ``NtfyChannel``, ``ntfy_channel``, payload formatting, retries, and privacy."""

import ast
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import httpx
import pytest
import respx
from scenarios import (
    as_hurricane_warning,
    miami_dade,
    recorded_maps,
    rip_current,
    with_alerts,
)

from weatherbot.engine import assess, diff
from weatherbot.models import AlertLevel, Thresholds
from weatherbot.services.config import NotificationSettings, Settings
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.notifications import (
    TEST_BODY,
    TEST_TITLE,
    NotificationKind,
    StoredNotification,
)
from weatherbot.services.ntfy import (
    NTFY_MAX_MESSAGE_BYTES,
    NTFY_TOPIC_UNSET,
    NtfyChannel,
    format_ntfy_message,
    ntfy_channel,
    priority_and_tags,
)
from weatherbot.services.policy import PolicySettings, PolicyState, decide
from weatherbot.sources import USER_AGENT

NTFY_SOURCE: Final = (
    Path(__file__).resolve().parents[2] / "src" / "weatherbot" / "services" / "ntfy.py"
)
FAKE_TOPIC: Final = "weatherbot-test-topic-987654321"
URGENT_PRIORITY: Final = 5
DEFAULT_PRIORITY: Final = 3
RETRY_CALL_COUNT: Final = 2


def _fake_token() -> str:
    return f"{'tk'}_{'a' * 29}"


def _notification(
    *,
    kind: NotificationKind = "location",
    level: int | None = 4,
    escalation: bool = True,
    title: str = "Miami-Dade County Hall: level 4, Warning / Watch / Evacuation",
    body: tuple[str, ...] = ("NWS Miami FL issued a Hurricane Watch that covers the location.",),
) -> StoredNotification:
    return StoredNotification(
        id=1,
        location_name="Miami-Dade County Hall" if kind == "location" else None,
        location_time_zone="America/New_York" if kind == "location" else None,
        assessment_id=1 if kind == "location" else None,
        cycle_id=1,
        kind=kind,
        level=AlertLevel(level) if level is not None else None,
        escalation=escalation,
        title=title,
        body=body,
        created_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
    )


def test_ntfy_source_sets_follow_redirects_false_and_never_joins_topic_to_url() -> None:
    tree = ast.parse(NTFY_SOURCE.read_text(encoding="utf-8"))
    found_follow_redirects = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg == "follow_redirects"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is False
                ):
                    found_follow_redirects = True
        if isinstance(node, ast.JoinedStr):
            names = {sub.id for sub in ast.walk(node) if isinstance(sub, ast.Name)}
            assert "topic" not in names
    assert found_follow_redirects


def test_ntfy_channel_factory_returns_none_when_off_and_unavailable_when_topic_missing() -> None:
    off_settings = Settings(notifications=NotificationSettings(ntfy=False))
    assert ntfy_channel(off_settings, environ={"WEATHERBOT_NTFY_TOPIC": FAKE_TOPIC}) is None

    on_settings = Settings(notifications=NotificationSettings(ntfy=True))
    unconfigured = ntfy_channel(on_settings, environ={})
    assert unconfigured is not None
    assert unconfigured.name == "ntfy"
    assert unconfigured.interrupts is True

    configured = ntfy_channel(
        on_settings,
        environ={
            "WEATHERBOT_NTFY_TOPIC": FAKE_TOPIC,
            "WEATHERBOT_NTFY_TOKEN": _fake_token(),
        },
    )
    assert isinstance(configured, NtfyChannel)
    assert FAKE_TOPIC not in repr(configured)
    assert _fake_token() not in repr(configured)
    assert repr(configured) == "NtfyChannel(host='ntfy.sh')"


@pytest.mark.anyio
async def test_unconfigured_channel_returns_unavailable_without_network_call() -> None:
    on_settings = Settings(notifications=NotificationSettings(ntfy=True))
    channel = ntfy_channel(on_settings, environ={"WEATHERBOT_NTFY_TOPIC": "   "})
    assert channel is not None
    outcome = await channel.deliver(_notification())
    assert outcome.result == "unavailable"
    assert outcome.detail == NTFY_TOPIC_UNSET


@pytest.mark.anyio
async def test_ntfy_posts_json_to_root_with_bearer_token_and_omits_auth_without_token() -> None:
    token = _fake_token()
    seen: list[httpx.Request] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "msg1"})

    with respx.mock(assert_all_called=True) as router:
        route = router.post("https://ntfy.sh/").mock(side_effect=_capture)
        channel = NtfyChannel("https://ntfy.sh", FAKE_TOPIC, token)
        outcome = await channel.deliver(_notification(level=5, escalation=True))

    assert outcome.result == "delivered"
    assert outcome.detail is None
    assert route.call_count == 1
    req = seen[0]
    assert str(req.url) == "https://ntfy.sh/"
    assert FAKE_TOPIC not in str(req.url)
    assert req.headers["User-Agent"] == USER_AGENT
    assert req.headers["Authorization"] == f"Bearer {token}"
    body = json.loads(req.content.decode("utf-8"))
    assert body["topic"] == FAKE_TOPIC
    assert body["priority"] == URGENT_PRIORITY
    assert body["tags"] == ["rotating_light"]
    assert body["message"].endswith(NOTICE)

    seen.clear()
    with respx.mock(assert_all_called=True) as router:
        route_no_token = router.post("https://ntfy.sh/").mock(side_effect=_capture)
        channel_no_token = NtfyChannel("https://ntfy.sh", FAKE_TOPIC, None)
        outcome2 = await channel_no_token.deliver(
            _notification(
                kind="test",
                level=None,
                escalation=False,
                title=TEST_TITLE,
                body=TEST_BODY,
            )
        )

    assert outcome2.result == "delivered"
    assert route_no_token.call_count == 1
    req2 = seen[0]
    assert "Authorization" not in req2.headers
    body2 = json.loads(req2.content.decode("utf-8"))
    assert body2["priority"] == DEFAULT_PRIORITY
    assert body2["tags"] == ["test_tube"]


def test_priority_and_tags_cover_all_notification_kinds_and_levels() -> None:
    assert priority_and_tags(_notification(kind="location", level=5, escalation=True)) == (
        5,
        ("rotating_light",),
    )
    assert priority_and_tags(_notification(kind="location", level=3, escalation=True)) == (
        4,
        ("warning",),
    )
    assert priority_and_tags(_notification(kind="location", level=4, escalation=False)) == (
        4,
        ("warning",),
    )
    assert priority_and_tags(_notification(kind="location", level=2, escalation=False)) == (
        3,
        ("warning",),
    )
    assert priority_and_tags(_notification(kind="location", level=1, escalation=False)) == (
        3,
        ("white_check_mark",),
    )
    assert priority_and_tags(_notification(kind="degraded", level=None, escalation=False)) == (
        4,
        ("warning",),
    )
    assert priority_and_tags(_notification(kind="stale_monitor", level=None, escalation=False)) == (
        4,
        ("warning",),
    )
    assert priority_and_tags(_notification(kind="recovered", level=None, escalation=False)) == (
        3,
        ("white_check_mark",),
    )
    assert priority_and_tags(_notification(kind="test", level=None, escalation=False)) == (
        3,
        ("test_tube",),
    )


def test_format_ntfy_message_keeps_size_bound_and_cuts_cleanly_at_multibyte_boundary() -> None:
    short = format_ntfy_message(("Advisory 12 issued.",))
    assert short == f"Advisory 12 issued.\n\n{NOTICE}"
    assert len(short.encode("utf-8")) <= NTFY_MAX_MESSAGE_BYTES

    # Build a multi-byte string ("🌀" is 4 UTF-8 bytes) exceeding 4,000 bytes.
    cyclone_line = "🌀" * 1100
    cut = format_ntfy_message((cyclone_line,))
    encoded = cut.encode("utf-8")
    assert len(encoded) <= NTFY_MAX_MESSAGE_BYTES
    assert cut.endswith(f"…\n\n{NOTICE}")
    # Decoding back from UTF-8 must contain no replacement characters.
    assert "\ufffd" not in cut


@pytest.mark.anyio
async def test_ntfy_retries_once_on_429_5xx_and_timeout_and_refuses_401_and_redirects() -> None:
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    # 1. 401 Unauthorized -> no retry, safe detail without body or secrets.
    with respx.mock(assert_all_called=True) as router:
        r_401 = router.post("https://ntfy.sh/").mock(
            return_value=httpx.Response(401, text=f"unauthorized for {FAKE_TOPIC}")
        )
        ch = NtfyChannel("https://ntfy.sh", FAKE_TOPIC, _fake_token(), sleep=fake_sleep)
        out_401 = await ch.deliver(_notification())
    assert (out_401.result, out_401.detail) == ("failed", "HTTP 401")
    assert r_401.call_count == 1
    assert waits == []
    assert FAKE_TOPIC not in (out_401.detail or "")

    # 2. 429 with Retry-After: 4 -> waits 4.0s (capped at 5s), retries once, succeeds on 200.
    with respx.mock(assert_all_called=True) as router:
        r_429 = router.post("https://ntfy.sh/").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "4"}),
                httpx.Response(200, json={"id": "ok"}),
            ]
        )
        ch = NtfyChannel("https://ntfy.sh", FAKE_TOPIC, None, sleep=fake_sleep)
        out_429 = await ch.deliver(_notification())
    assert (out_429.result, out_429.detail) == ("delivered", None)
    assert r_429.call_count == RETRY_CALL_COUNT
    assert waits == [4.0]
    waits.clear()

    # 3. 500 twice -> retries once after 3.0s, fails with HTTP 500.
    with respx.mock(assert_all_called=True) as router:
        r_500 = router.post("https://ntfy.sh/").mock(
            side_effect=[
                httpx.Response(500, text="internal error"),
                httpx.Response(500, text="still failing"),
            ]
        )
        ch = NtfyChannel("https://ntfy.sh", FAKE_TOPIC, None, sleep=fake_sleep)
        out_500 = await ch.deliver(_notification())
    assert (out_500.result, out_500.detail) == ("failed", "HTTP 500")
    assert r_500.call_count == RETRY_CALL_COUNT
    assert waits == [3.0]
    waits.clear()

    # 4. Timeout -> retries once after 3.0s, fails with ReadTimeout class name only.
    with respx.mock(assert_all_called=True) as router:
        r_timeout = router.post("https://ntfy.sh/").mock(
            side_effect=httpx.ReadTimeout(f"timeout on {FAKE_TOPIC}")
        )
        ch = NtfyChannel("https://ntfy.sh", FAKE_TOPIC, None, sleep=fake_sleep)
        out_timeout = await ch.deliver(_notification())
    assert (out_timeout.result, out_timeout.detail) == ("failed", "ReadTimeout")
    assert r_timeout.call_count == RETRY_CALL_COUNT
    assert waits == [3.0]
    waits.clear()

    # 5. Redirect (302) -> refused without following and without retrying.
    with respx.mock(assert_all_called=True) as router:
        r_redirect = router.post("https://ntfy.sh/").mock(
            return_value=httpx.Response(302, headers={"Location": "http://evil.example/steal"})
        )
        ch = NtfyChannel("https://ntfy.sh", FAKE_TOPIC, None, sleep=fake_sleep)
        out_redirect = await ch.deliver(_notification())
    assert (out_redirect.result, out_redirect.detail) == ("failed", "HTTP 302")
    assert r_redirect.call_count == 1
    assert waits == []


def test_change_sentences_and_policy_notification_lines_carry_no_distance_or_coordinate() -> None:
    loc = miami_dade()
    thresholds = Thresholds()
    a0 = assess(recorded_maps(), loc, thresholds)
    a1 = assess(with_alerts([as_hurricane_warning(rip_current())]), loc, thresholds)
    changes = diff(a0, a1)
    decided = decide(
        PolicyState(),
        a1,
        changes,
        PolicySettings(),
        a1.as_of,
    )
    assert decided.notification is not None
    lines = [*(c.detail for c in changes), *decided.notification.body]
    assert lines
    for line in lines:
        assert not re.search(
            r"\b\d+\s*(?:km|nmi|mi|miles|kilometres|kilometers)\b",
            line,
            re.IGNORECASE,
        )
        assert not re.search(r"-?\d+\.\d{2,}", line)
