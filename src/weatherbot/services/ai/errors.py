# src/weatherbot/services/ai/errors.py
"""Why AI is unavailable: a fixed reason for every SDK error and every unusable stop.

An SDK error's message can quote the request or the response, so nothing here ever copies
one: ``from_exception`` maps the SDK's classes, most specific first, to a reason whose
message is fixed text. ``from_stop`` does the same for a message that arrived but cannot
be used: a ``refusal`` (with its category, an open set the API names), a ``max_tokens``
stop, or a ``model_context_window_exceeded`` stop. There is no fallback to another model
on a refusal: the brief names the model, and a refusal is "AI unavailable (declined)".

The SDK is imported only inside ``from_exception``, where an SDK error already exists, so
this module loads without it.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final, Literal, get_args

if TYPE_CHECKING:
    from anthropic.types import Message

type AiUnavailableReason = Literal[
    "disabled",
    "no_credential",
    "price_unknown",
    "paused",
    "capped",
    "busy",
    "auth_failed",
    "permission",
    "not_found",
    "rate_limited",
    "overloaded",
    "server_error",
    "timeout",
    "network",
    "bad_request",
    "too_large",
    "declined",
    "truncated",
]
AI_UNAVAILABLE_REASONS: Final[tuple[AiUnavailableReason, ...]] = get_args(
    AiUnavailableReason.__value__
)
MAX_CATEGORY_LENGTH: Final = 32
"""The ledger's ``refusal_category`` column."""
AUTH_FAILURES_TO_HOLD: Final = 3
AUTH_HOLD: Final = timedelta(hours=1)

MESSAGES: Final[dict[AiUnavailableReason, str]] = {
    "disabled": "AI is turned off by [ai] enabled",
    "no_credential": "there is no Anthropic credential",
    "price_unknown": "the model is not in the price table, so the cap cannot price it",
    "paused": "AI is paused",
    "capped": "today's AI cap is reached",
    "busy": "too many AI requests are running",
    "auth_failed": "Anthropic refused the credential (authentication failed)",
    "permission": "the credential is not allowed to use this model",
    "not_found": "Anthropic does not know the model",
    "rate_limited": "Anthropic is rate-limiting this credential",
    "overloaded": "Anthropic is overloaded or temporarily unavailable",
    "server_error": "Anthropic answered with a server error",
    "timeout": "the request to Anthropic timed out",
    "network": "Anthropic could not be reached",
    "bad_request": "Anthropic refused the request as malformed",
    "too_large": "the request is too large",
    "declined": "the model declined to answer",
    "truncated": "the answer was cut off at its token limit",
}


class AiUnavailable(Exception):  # noqa: N818 - a state the surfaces show, not a fault
    """AI cannot answer this request; the message is fixed text for the reason."""

    def __init__(self, reason: AiUnavailableReason, *, category: str | None = None) -> None:
        """Create the error.

        Args:
            reason: Why AI is unavailable.
            category: A refusal's category, as the API names it.
        """
        super().__init__(f"AI unavailable: {MESSAGES[reason]}")
        self.reason: AiUnavailableReason = reason
        self.category = category[:MAX_CATEGORY_LENGTH] if category else None


class InvalidOutputError(ValueError):
    """An answer whose text did not match its schema; the model's text is never quoted."""

    def __init__(self) -> None:
        """Create the error with its fixed message."""
        super().__init__("the answer did not match its schema")


def from_exception(error: BaseException) -> AiUnavailable:
    """Map an SDK error to its reason, most specific class first; the message is never copied.

    Args:
        error: The error the SDK raised.

    Returns:
        The reason AI is unavailable.
    """
    import anthropic  # noqa: PLC0415 - an SDK error exists, so the SDK is already loaded

    status_classes: tuple[tuple[type[anthropic.APIStatusError], AiUnavailableReason], ...] = (
        (anthropic.AuthenticationError, "auth_failed"),
        (anthropic.PermissionDeniedError, "permission"),
        (anthropic.NotFoundError, "not_found"),
        (anthropic.RateLimitError, "rate_limited"),
        (anthropic.OverloadedError, "overloaded"),
        (anthropic.ServiceUnavailableError, "overloaded"),
        (anthropic.InternalServerError, "server_error"),
        (anthropic.RequestTooLargeError, "too_large"),
        (anthropic.BadRequestError, "bad_request"),
    )
    for cls, reason in status_classes:
        if isinstance(error, cls):
            return AiUnavailable(reason)
    if isinstance(error, anthropic.APIStatusError):
        server_error_floor = 500
        return AiUnavailable(
            "server_error" if error.status_code >= server_error_floor else "bad_request"
        )
    if isinstance(error, anthropic.APITimeoutError):
        return AiUnavailable("timeout")
    if isinstance(error, anthropic.APIConnectionError):
        return AiUnavailable("network")
    if isinstance(error, anthropic.CredentialsError):
        return AiUnavailable("no_credential")
    return AiUnavailable("server_error")


def from_stop(message: "Message") -> AiUnavailable | None:
    """Map a message's stop to a reason when the message cannot be used.

    Args:
        message: The final message.

    Returns:
        ``declined`` (with the refusal's category), ``truncated``, or ``too_large``, or
        ``None`` when the message ended normally.
    """
    if message.stop_reason == "refusal":
        details = message.stop_details
        return AiUnavailable("declined", category=details.category if details else None)
    if message.stop_reason == "max_tokens":
        return AiUnavailable("truncated")
    if message.stop_reason == "model_context_window_exceeded":
        return AiUnavailable("too_large")
    return None


class AuthGuard:
    """Counts consecutive 401 and 403 answers; three hold AI at ``auth_failed`` for an hour."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        """Create the guard, with no failure counted.

        Args:
            now: The clock.
        """
        self._now = now
        self._failures = 0
        self._held_until: datetime | None = None
        self._probing = False

    @property
    def held(self) -> bool:
        """Whether the hold refuses requests now (a probe in flight counts)."""
        if self._held_until is None:
            return False
        return self._probing or self._now() < self._held_until

    def admit(self) -> None:
        """Let a request through, or refuse it while the hold lasts.

        Raises:
            AiUnavailable: ``auth_failed`` while held, or while the one probe after the
                hold is in flight.
        """
        if self._held_until is None:
            return
        if self.held:
            raise AiUnavailable(reason="auth_failed")
        self._probing = True

    def refused(self) -> None:
        """Count a 401 or 403 answer."""
        self._failures += 1
        self._probing = False
        if self._failures >= AUTH_FAILURES_TO_HOLD:
            self._held_until = self._now() + AUTH_HOLD

    def answered(self) -> None:
        """Clear the count and the hold: Anthropic accepted the credential."""
        self._failures = 0
        self._held_until = None
        self._probing = False

    def unanswered(self) -> None:
        """End a probe that got no answer (a network failure): the next request probes."""
        self._probing = False
