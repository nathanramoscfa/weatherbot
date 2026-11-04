# tests/live/test_ntfy_live.py
"""Live contract test: posts one notification to a throwaway topic on ``ntfy.sh``."""

import secrets
from datetime import UTC, datetime
from http import HTTPStatus

import httpx
import pytest

from weatherbot.services.notifications import TEST_BODY, TEST_TITLE, StoredNotification
from weatherbot.services.ntfy import NtfyChannel, format_ntfy_message
from weatherbot.sources import USER_AGENT


@pytest.mark.live
@pytest.mark.enable_socket
@pytest.mark.anyio
async def test_live_ntfy_post_to_throwaway_topic_returns_id_time_and_topic() -> None:
    topic = f"weatherbot-live-{secrets.token_urlsafe(18)}"
    payload = {
        "topic": topic,
        "title": TEST_TITLE,
        "message": format_ntfy_message(TEST_BODY),
        "priority": 3,
        "tags": ["test_tube"],
    }
    async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
        response = await client.post(
            "https://ntfy.sh/",
            json=payload,
            headers={"User-Agent": USER_AGENT},
        )
        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert isinstance(data.get("id"), str)
        assert data["id"]
        assert isinstance(data.get("time"), int)
        assert data["time"] > 0
        assert data.get("topic") == topic

        channel = NtfyChannel("https://ntfy.sh", topic, None, client=client)
        notification = StoredNotification(
            id=1,
            location_name=None,
            location_time_zone=None,
            assessment_id=None,
            cycle_id=None,
            kind="test",
            level=None,
            escalation=False,
            title=TEST_TITLE,
            body=TEST_BODY,
            created_at=datetime.now(UTC),
        )
        outcome = await channel.deliver(notification)
        assert outcome.result == "delivered"
        assert outcome.detail is None
