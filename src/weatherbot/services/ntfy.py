# src/weatherbot/services/ntfy.py
"""The ``ntfy`` phone notification channel: posts JSON to the server root.

``NtfyChannel`` posts JSON to ``{ntfy_server}/`` with ``"topic"`` in the request body
rather than the URL path so the topic stays out of URL strings, ``httpx`` request URLs,
exception messages, and proxy/server access logs. Every message appends the one-line
disclaimer notice and is truncated at a UTF-8 character boundary to at most 4,000 bytes
so ``ntfy`` never converts the notification into a file attachment and never cuts off the
disclaimer.

Neither ``WEATHERBOT_NTFY_TOPIC`` nor ``WEATHERBOT_NTFY_TOKEN`` is ever included in
``repr``, log messages, or stored delivery details.
"""

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit

import httpx

from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.notifications import Channel, Delivery, StoredNotification
from weatherbot.services.toast import NullChannel
from weatherbot.sources import USER_AGENT

if TYPE_CHECKING:
    from weatherbot.services.config import NotificationSettings, Settings

type Attempt = Delivery
type Notification = StoredNotification

NTFY_TOPIC_VARIABLE: Final = "WEATHERBOT_NTFY_TOPIC"
NTFY_TOKEN_VARIABLE: Final = "WEATHERBOT_NTFY_TOKEN"  # noqa: S105 - env var name, not a secret
DEFAULT_NTFY_SERVER: Final = "https://ntfy.sh"
NTFY_OFF: Final = "turned off by [notifications] ntfy"
NTFY_TOPIC_UNSET: Final = "WEATHERBOT_NTFY_TOPIC is not set"

NTFY_TIMEOUT_SECONDS: Final = 5.0
NTFY_RETRY_WAIT_SECONDS: Final = 3.0
NTFY_MAX_RETRY_WAIT_SECONDS: Final = 5.0
NTFY_MAX_MESSAGE_BYTES: Final = 4000
TRUNCATION_SUFFIX: Final = "…"
HTTP_TOO_MANY_REQUESTS: Final = 429
HTTP_SERVER_ERROR_MIN: Final = 500

TAGS_BY_KIND: Final[dict[str, tuple[str, ...]]] = {
    "degraded": ("warning",),
    "stale_monitor": ("warning",),
    "recovered": ("white_check_mark",),
    "test": ("test_tube",),
}
TAGS_BY_LEVEL: Final[dict[int, tuple[str, ...]]] = {
    5: ("rotating_light",),
    4: ("warning",),
    3: ("warning",),
    2: ("warning",),
    1: ("white_check_mark",),
}


def priority_and_tags(notification: StoredNotification) -> tuple[int, tuple[str, ...]]:
    """Return the ``ntfy`` priority (3..5) and fixed-table tag names for ``notification``."""
    kind_tags = TAGS_BY_KIND.get(notification.kind)
    if kind_tags is not None:
        priority = 4 if notification.kind in {"degraded", "stale_monitor"} else 3
        return priority, kind_tags

    level = int(notification.level) if notification.level is not None else 3
    if notification.escalation and level == 5:  # noqa: PLR2004 - level 5 extreme threat
        priority = 5
    elif notification.escalation or level >= 4:  # noqa: PLR2004 - level 4 severe threat
        priority = 4
    else:
        priority = 3
    tags = TAGS_BY_LEVEL.get(level, ("warning",))
    return priority, tags


def format_ntfy_message(body: Sequence[str]) -> str:
    """Format ``body`` lines with the disclaimer notice, capped at 4,000 UTF-8 bytes."""
    lines = tuple(line for line in body if line != NOTICE)
    footer = f"\n\n{NOTICE}" if lines else NOTICE
    joined = "\n".join(lines)
    full = f"{joined}{footer}"
    if len(full.encode("utf-8")) <= NTFY_MAX_MESSAGE_BYTES:
        return full
    suffix_bytes = len(TRUNCATION_SUFFIX.encode("utf-8"))
    footer_bytes = len(footer.encode("utf-8"))
    budget = max(0, NTFY_MAX_MESSAGE_BYTES - suffix_bytes - footer_bytes)
    truncated = joined.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
    return f"{truncated}{TRUNCATION_SUFFIX}{footer}"


def _retry_delay(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After", "").strip()
    if raw:
        try:
            parsed = float(raw)
        except ValueError:
            pass
        else:
            if parsed > 0:
                return min(parsed, NTFY_MAX_RETRY_WAIT_SECONDS)
    return NTFY_RETRY_WAIT_SECONDS


class NtfyChannel:
    """Phone notification channel that posts JSON to an ``ntfy`` server's root."""

    def __init__(  # noqa: PLR0913 - channel configuration and optional test seams
        self,
        server: str = DEFAULT_NTFY_SERVER,
        topic: str | None = None,
        token: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        environ: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        timeout: float = NTFY_TIMEOUT_SECONDS,
    ) -> None:
        """Create the channel.

        Args:
            server: Validated ``ntfy`` server base URL.
            topic: ``ntfy`` topic; when ``None``, resolved from ``environ`` on send.
            token: Optional bearer token; when ``None``, resolved from ``environ`` on send.
            client: Optional pre-configured ``httpx.AsyncClient``.
            environ: Environment mapping when ``topic``/``token`` are not passed directly.
            transport: Optional custom ``httpx.AsyncBaseTransport`` for testing.
            sleep: Async pause function used before the single retry.
            timeout: Per-request timeout in seconds.
        """
        self._server = server.rstrip("/")
        self._topic = topic
        self._token = token
        self._client = client
        self._environ = environ
        self._transport = transport
        self._sleep = sleep
        self._timeout = timeout

    @property
    def name(self) -> str:
        """The channel's identifier."""
        return "ntfy"

    @property
    def interrupts(self) -> bool:
        """A phone notification interrupts the operator."""
        return True

    def __repr__(self) -> str:
        """Show only the server host; never include the topic or token."""
        host = urlsplit(self._server).hostname or self._server
        return f"NtfyChannel(host={host!r})"

    def _resolve_credentials(self) -> tuple[str, str]:
        env = os.environ if self._environ is None else self._environ
        topic = (
            self._topic.strip()
            if self._topic is not None
            else env.get(NTFY_TOPIC_VARIABLE, "").strip()
        )
        token = (
            self._token.strip()
            if self._token is not None
            else env.get(NTFY_TOKEN_VARIABLE, "").strip()
        )
        return topic, token

    async def deliver(self, notification: StoredNotification) -> Delivery:
        """Post ``notification`` to ``{server}/`` with at most one retry on transient failure."""
        topic, token = self._resolve_credentials()
        if not topic:
            return Delivery("unavailable", NTFY_TOPIC_UNSET)
        priority, tags = priority_and_tags(notification)
        payload: dict[str, object] = {
            "topic": topic,
            "title": notification.title,
            "message": format_ntfy_message(notification.body),
            "priority": priority,
            "tags": list(tags),
        }
        headers: dict[str, str] = {
            "User-Agent": USER_AGENT,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        url = f"{self._server}/"

        if self._client is not None:
            return await self._deliver_with_client(self._client, url, payload, headers)

        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=self._timeout,
            transport=self._transport,
        ) as client:
            return await self._deliver_with_client(client, url, payload, headers)

    async def _deliver_with_client(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
    ) -> Delivery:
        outcome, retry_wait = await self._post_once(client, url, payload, headers)
        if retry_wait is None:
            return outcome
        await self._sleep(retry_wait)
        second_outcome, _ = await self._post_once(client, url, payload, headers)
        return second_outcome

    @staticmethod
    async def _post_once(
        client: httpx.AsyncClient,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
    ) -> tuple[Delivery, float | None]:
        try:
            response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as error:
            return Delivery("failed", type(error).__name__), NTFY_RETRY_WAIT_SECONDS
        status = response.status_code
        if 200 <= status < 300:  # noqa: PLR2004 - HTTP 2xx range
            return Delivery("delivered"), None
        if status == HTTP_TOO_MANY_REQUESTS:
            return Delivery("failed", f"HTTP {status}"), _retry_delay(response)
        if status >= HTTP_SERVER_ERROR_MIN:
            return Delivery("failed", f"HTTP {status}"), NTFY_RETRY_WAIT_SECONDS
        return Delivery("failed", f"HTTP {status}"), None


def ntfy_channel(
    settings: "Settings | NotificationSettings | None" = None,
    environ: Mapping[str, str] | None = None,
    *,
    client: httpx.AsyncClient | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Channel | None:
    """Build the ``ntfy`` channel for ``settings``, or ``None`` when ``ntfy`` is off."""
    enabled = False
    server = DEFAULT_NTFY_SERVER
    if settings is not None:
        from weatherbot.services.config import Settings  # noqa: PLC0415 - avoid cycle

        notif = settings.notifications if isinstance(settings, Settings) else settings
        enabled = notif.ntfy
        server = notif.ntfy_server
    if not enabled:
        return None
    env = os.environ if environ is None else environ
    topic = env.get(NTFY_TOPIC_VARIABLE, "").strip()
    if not topic:
        return NullChannel(NTFY_TOPIC_UNSET, channel_name="ntfy", result="unavailable")
    token = env.get(NTFY_TOKEN_VARIABLE, "").strip() or None
    return NtfyChannel(
        server,
        topic,
        token,
        client=client,
        environ=environ,
        transport=transport,
        sleep=sleep,
    )
