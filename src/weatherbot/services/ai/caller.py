# src/weatherbot/services/ai/caller.py
"""``AiCaller``: the one path every Messages request takes — reserve, send, settle.

Before a request is sent its ceiling is computed: the request body serialized with every
image's base64 data left out, at 2.5 characters a token, plus each image's
⌈width/28⌉ x ⌈height/28⌉ visual tokens read from the PNG's header, all at the input price,
plus ``max_tokens`` at the output price. An estimated prompt past ``MAX_PROMPT_TOKENS`` is
refused as ``too_large``; otherwise the ledger reserves the ceiling (or refuses it as
``paused`` or ``capped``) and only then is the request sent. It settles from the final
message's usage when one arrived; at zero, ``failed``, when an error answered before any
output; and at the ceiling, ``incomplete``, when a stream ended without its final message
(cancelled, disconnected, or timed out), because the SDK's usage stops at
``message_start`` while the tokens were billed. The settle is a short synchronous write in
a ``finally``, so a second cancellation cannot skip it.

Structured output is asked for with ``output_config.format``, the output model's schema
through the SDK's ``transform_schema``, and validated here after the stop is checked and
the usage is read. The SDK's own ``messages.parse`` and ``stream(output_format=...)``
validate inside the SDK and raise before the stop reason and the final usage arrive, so a
refusal or a ``max_tokens`` stop would reach neither its reason nor the ledger (probed
2026-11-01).

A request never carries ``temperature``, ``top_p``, or ``top_k`` (API version 2026-10-21
refuses them) and always carries ``max_tokens``. Three consecutive 401 or 403 answers
hold the caller at ``auth_failed`` for an hour (or until the process restarts); then one
request is let through, and a success clears the hold.
"""

import asyncio
import base64
import binascii
import json
import math
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Self, cast

import anthropic
from anthropic import AsyncAnthropic
from anthropic.lib.streaming import AsyncMessageStream, ParsedMessageStreamEvent
from anthropic.types import Message, Usage
from pydantic import BaseModel, ValidationError

from weatherbot.services.ai.errors import (
    AiUnavailable,
    AuthGuard,
    InvalidOutputError,
    from_exception,
    from_stop,
)
from weatherbot.services.ai.ledger import CallKind, Ledger, Outcome, Reservation
from weatherbot.services.ai.pricing import MAX_PROMPT_TOKENS, TokenUsage, ceiling_micro_usd

type RequestParams = Mapping[str, Any]
"""A Messages request's body without ``model``: ``max_tokens``, ``messages``, and the rest."""

CHARACTERS_PER_TOKEN: Final = 2.5
IMAGE_TILE_PX: Final = 28
PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
PNG_HEADER_BYTES: Final = 24
"""The signature, the IHDR chunk's length and type, then the width and the height."""
SAMPLING_PARAMETERS: Final = frozenset({"temperature", "top_p", "top_k"})
RESERVED_PARAMETERS: Final = frozenset({"model", "stream", "output_format"})
INVALID_OUTPUT: Final = "invalid_output"
"""The ledger's ``error_kind`` for an answer whose text did not match its schema."""


def _strip_images(value: object, sizes: list[tuple[int, int]]) -> object:
    """Copy a request body with each base64 image's data emptied, recording its size."""
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        source = mapping.get("source")
        if mapping.get("type") == "image" and isinstance(source, Mapping):
            image = cast("Mapping[str, object]", source)
            data = image.get("data")
            if isinstance(data, str):
                sizes.append(png_size(data))
                return {**mapping, "source": {**image, "data": ""}}
        return {key: _strip_images(item, sizes) for key, item in mapping.items()}
    if isinstance(value, list | tuple):
        items = cast("list[object] | tuple[object, ...]", value)
        return [_strip_images(item, sizes) for item in items]
    return value


def png_size(data: str) -> tuple[int, int]:
    """Read a base64 PNG's width and height from its header.

    Args:
        data: The image's base64 text.

    Returns:
        The width and the height in pixels.

    Raises:
        ValueError: The data is not a PNG; only PNG images are measured.
    """
    message = "an image must be base64 PNG data"
    try:
        head = base64.b64decode(data[:32], validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(message) from None
    if len(head) < PNG_HEADER_BYTES or not head.startswith(PNG_SIGNATURE):
        raise ValueError(message)
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def image_tokens(width: int, height: int) -> int:
    """Count an image's visual tokens: one per 28-pixel tile, ⌈w/28⌉ x ⌈h/28⌉.

    Args:
        width: Pixels.
        height: Pixels.

    Returns:
        The tokens.
    """
    return math.ceil(width / IMAGE_TILE_PX) * math.ceil(height / IMAGE_TILE_PX)


def estimate_prompt_tokens(model: str, params: RequestParams) -> int:
    """Estimate a request's prompt tokens, conservatively.

    Args:
        model: The model.
        params: The request body without ``model``, its output format included.

    Returns:
        The serialized text (image data left out) at 2.5 characters a token, plus every
        image's visual tokens.
    """
    sizes: list[tuple[int, int]] = []
    stripped = cast("dict[str, object]", _strip_images(params, sizes))
    characters = len(json.dumps({"model": model, **stripped}, ensure_ascii=False, default=str))
    text_tokens = math.ceil(characters / CHARACTERS_PER_TOKEN)
    return text_tokens + sum(image_tokens(width, height) for width, height in sizes)


def usage_of(usage: Usage) -> TokenUsage:
    """Read the SDK's usage by price: five-minute and one-hour writes apart when reported.

    Args:
        usage: A message's usage.

    Returns:
        The usage; ``cache_creation_input_tokens`` counts as five-minute writes when the
        message does not split them by lifetime.
    """
    creation = usage.cache_creation
    if creation is not None:
        write_5m = creation.ephemeral_5m_input_tokens
        write_1h = creation.ephemeral_1h_input_tokens
    else:
        write_5m = usage.cache_creation_input_tokens or 0
        write_1h = 0
    return TokenUsage(
        input_tokens=usage.input_tokens,
        cache_write_5m_tokens=write_5m,
        cache_write_1h_tokens=write_1h,
        cache_read_tokens=usage.cache_read_input_tokens or 0,
        output_tokens=usage.output_tokens,
    )


def outcome_of(message: Message, request_id: str | None) -> Outcome:
    """Say how a request that returned a final message ended, priced from its usage.

    Args:
        message: The final message.
        request_id: Its request id.

    Returns:
        ``declined`` for a refusal, ``failed`` for a stop that leaves the answer unusable,
        and ``ok`` otherwise.
    """
    stop = from_stop(message)
    status = "ok" if stop is None else "declined" if stop.reason == "declined" else "failed"
    return Outcome(
        status=status,
        usage=usage_of(message.usage),
        stop_reason=message.stop_reason,
        refusal_category=stop.category if stop is not None else None,
        error_kind=stop.reason if stop is not None and status == "failed" else None,
        request_id=request_id,
    )


def text_of(message: Message) -> str:
    """Join a message's text blocks.

    Args:
        message: A message.

    Returns:
        Its text, without thinking or tool blocks.
    """
    return "".join(block.text for block in message.content if block.type == "text")


def validate_output[T: BaseModel](output_format: type[T], message: Message) -> T:
    """Validate a message's text against its output model.

    Args:
        output_format: The output's Pydantic model.
        message: A message that stopped normally.

    Returns:
        The validated output.

    Raises:
        InvalidOutputError: The text does not match; the model's text is never quoted.
    """
    try:
        return output_format.model_validate_json(text_of(message))
    except ValidationError:
        raise InvalidOutputError from None


@dataclass(frozen=True)
class Parsed[T: BaseModel]:
    """A structured request's message and its validated output."""

    message: Message
    output: T
    request_id: str | None


@dataclass(frozen=True)
class _Call:
    kind: CallKind
    model: str
    location: str | None
    prompt_version: str | None


def request_kwargs(
    params: RequestParams, output_format: type[BaseModel] | None = None
) -> dict[str, Any]:
    """Check a request body and add the output model's schema as ``output_config.format``.

    Args:
        params: The request body without ``model``.
        output_format: The structured output's Pydantic model, if any.

    Returns:
        The keyword arguments for ``messages.create`` or ``messages.stream``.

    Raises:
        ValueError: The body carries a sampling parameter, ``model``, ``stream``,
            ``output_format``, or its own ``output_config.format``.
        TypeError: The body has no integer ``max_tokens``.
    """
    keys = set(params)
    if keys & SAMPLING_PARAMETERS:
        message = "a request never carries temperature, top_p, or top_k"
        raise ValueError(message)
    if keys & RESERVED_PARAMETERS:
        message = "model, stream, and output_format are the caller's arguments, not params"
        raise ValueError(message)
    if not isinstance(params.get("max_tokens"), int):
        message = "a request always carries an integer max_tokens"
        raise TypeError(message)
    kwargs = dict(params)
    if output_format is not None:
        config = cast("Mapping[str, object]", params.get("output_config") or {})
        if "format" in config:
            message = "pass the output's model as output_format, not output_config.format"
            raise ValueError(message)
        schema = anthropic.transform_schema(output_format.model_json_schema())
        kwargs["output_config"] = {**config, "format": {"type": "json_schema", "schema": schema}}
    return kwargs


class StreamEvents:
    """The SDK's stream events, watched for the final message and the usage so far."""

    def __init__(self, stream: AsyncMessageStream[None]) -> None:
        """Watch a stream.

        Args:
            stream: The SDK's stream.
        """
        self._stream = stream
        self._iterator = stream.__aiter__()
        self.started = False
        self.final: Message | None = None
        self.output: BaseModel | None = None
        """The final text validated against the output model, set once the block ends."""
        self._usage = TokenUsage()

    @property
    def request_id(self) -> str | None:
        """The stream's request id."""
        return self._stream.request_id

    @property
    def usage(self) -> TokenUsage:
        """The usage the stream has reported so far."""
        return self._usage

    def __aiter__(self) -> Self:
        """Iterate the events."""
        return self

    async def __anext__(self) -> "ParsedMessageStreamEvent[None]":
        """Read the next event, noting the usage so far and the final message."""
        event = await self._iterator.__anext__()
        self.started = True
        snapshot = self._stream.current_message_snapshot
        self._usage = usage_of(snapshot.usage)
        if event.type == "message_stop":
            self.final = snapshot
        return event


class AiCaller:
    """Sends Messages requests through the ledger: every request reserved and settled."""

    def __init__(
        self,
        factory: Callable[[], AsyncAnthropic],
        ledger: Ledger,
        *,
        now: Callable[[], datetime],
        auth: AuthGuard | None = None,
    ) -> None:
        """Create the caller.

        Args:
            factory: Returns the client; the service hands over the one it built.
            ledger: The ledger every request reserves and settles in.
            now: The clock.
            auth: The authentication hold, shared by the service's callers.
        """
        self._factory = factory
        self._ledger = ledger
        self._auth = auth or AuthGuard(now)

    async def _reserve(self, call: _Call, kwargs: RequestParams) -> Reservation:
        prompt_tokens = estimate_prompt_tokens(call.model, kwargs)
        if prompt_tokens > MAX_PROMPT_TOKENS:
            raise AiUnavailable(reason="too_large")
        ceiling = ceiling_micro_usd(call.model, prompt_tokens, int(kwargs["max_tokens"]))
        self._auth.admit()
        try:
            return await asyncio.to_thread(
                self._ledger.reserve,
                call.kind,
                call.model,
                call.location,
                call.prompt_version,
                ceiling,
            )
        except BaseException:
            self._auth.unanswered()
            raise

    def _failure(
        self, error: anthropic.AnthropicError, *, started: bool
    ) -> tuple[Outcome, AiUnavailable]:
        unavailable = from_exception(error)
        if isinstance(error, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
            self._auth.refused()
        elif isinstance(error, anthropic.APIStatusError):
            self._auth.answered()
        else:
            self._auth.unanswered()
        request_id = error.request_id if isinstance(error, anthropic.APIStatusError) else None
        # A timeout, or an error after output began, may have been billed: the ceiling.
        timed_out = isinstance(error, anthropic.APITimeoutError)
        status = "incomplete" if started or timed_out else "failed"
        return Outcome(status, error_kind=unavailable.reason, request_id=request_id), unavailable

    async def _send(
        self,
        call: _Call,
        kwargs: dict[str, Any],
        output_format: type[BaseModel] | None,
        send: Callable[[AsyncAnthropic], Awaitable[Message]],
    ) -> tuple[Message, BaseModel | None, str | None]:
        reservation = await self._reserve(call, kwargs)
        outcome = Outcome("incomplete")
        try:
            try:
                message = await send(self._factory())
            except anthropic.AnthropicError as error:
                outcome, unavailable = self._failure(error, started=False)
                raise unavailable from None
            request_id = message._request_id  # noqa: SLF001  # pyright: ignore[reportPrivateUsage] - the SDK's public request id
            outcome = outcome_of(message, request_id)
            self._auth.answered()
            stop = from_stop(message)
            if stop is not None:
                raise stop
            output = None
            if output_format is not None:
                try:
                    output = validate_output(output_format, message)
                except InvalidOutputError:
                    outcome = Outcome(
                        "failed",
                        outcome.usage,
                        outcome.stop_reason,
                        None,
                        INVALID_OUTPUT,
                        request_id,
                    )
                    raise
            return message, output, request_id
        finally:
            self._auth.unanswered()
            self._ledger.settle(reservation, outcome)

    async def parse[T: BaseModel](  # noqa: PLR0913 - the request's keyword-only fields
        self,
        *,
        kind: CallKind,
        model: str,
        location: str | None,
        prompt_version: str | None,
        params: RequestParams,
        output_format: type[T],
    ) -> Parsed[T]:
        """Send a structured request and return the message with its validated output.

        Args:
            kind: The product.
            model: The model.
            location: The location's name, or ``None``.
            prompt_version: The frozen prompt's SHA-256, when one applies.
            params: The request body without ``model``.
            output_format: The output's Pydantic model.

        Returns:
            The message, its output, and its request id.

        Raises:
            AiUnavailable: Refused before sending, answered with an error, or stopped by a
                refusal, ``max_tokens``, or the context window.
            InvalidOutputError: The answer's text did not match ``output_format``.
        """
        kwargs = request_kwargs(params, output_format)
        call = _Call(kind, model, location, prompt_version)

        async def send(client: AsyncAnthropic) -> Message:
            return await client.messages.create(model=model, stream=False, **kwargs)

        message, output, request_id = await self._send(call, kwargs, output_format, send)
        return Parsed(message, cast("T", output), request_id)

    async def create(
        self,
        *,
        kind: CallKind,
        model: str,
        location: str | None,
        prompt_version: str | None,
        params: RequestParams,
    ) -> Message:
        """Send a request and return its message.

        Args:
            kind: The product.
            model: The model.
            location: The location's name, or ``None``.
            prompt_version: The frozen prompt's SHA-256, when one applies.
            params: The request body without ``model``.

        Returns:
            The message.

        Raises:
            AiUnavailable: Refused before sending, answered with an error, or stopped by a
                refusal, ``max_tokens``, or the context window.
        """
        kwargs = request_kwargs(params)
        call = _Call(kind, model, location, prompt_version)

        async def send(client: AsyncAnthropic) -> Message:
            return await client.messages.create(model=model, stream=False, **kwargs)

        message, _, _ = await self._send(call, kwargs, None, send)
        return message

    @asynccontextmanager
    async def stream(  # noqa: PLR0913 - the request's keyword-only fields
        self,
        *,
        kind: CallKind,
        model: str,
        location: str | None,
        prompt_version: str | None,
        params: RequestParams,
        output_format: type[BaseModel] | None = None,
    ) -> AsyncGenerator[StreamEvents]:
        """Stream a request: yield its events, then settle on exit, cancellation included.

        Args:
            kind: The product.
            model: The model.
            location: The location's name, or ``None``.
            prompt_version: The frozen prompt's SHA-256, when one applies.
            params: The request body without ``model``.
            output_format: The structured output's Pydantic model, if any; the final text
                is validated against it once the block ends.

        Yields:
            The SDK's events; ``final`` holds the final message once it arrives, and
            ``output`` the validated output once the block ends.

        Raises:
            AiUnavailable: Refused before sending, answered with an error, or (once the
                block ends) stopped by a refusal, ``max_tokens``, or the context window.
            InvalidOutputError: The final text did not match ``output_format``.
        """
        kwargs = request_kwargs(params, output_format)
        call = _Call(kind, model, location, prompt_version)
        reservation = await self._reserve(call, kwargs)
        events: StreamEvents | None = None
        outcome: Outcome | None = None
        try:
            try:
                manager = self._factory().messages.stream(model=model, **kwargs)
                async with manager as sdk_stream:
                    self._auth.answered()
                    events = StreamEvents(sdk_stream)
                    yield events
                final = events.final
            except anthropic.AnthropicError as error:
                started = events is not None and events.started
                outcome, unavailable = self._failure(error, started=started)
                if events is not None:
                    outcome = Outcome(
                        outcome.status,
                        usage=events.usage,
                        error_kind=outcome.error_kind,
                        request_id=outcome.request_id or events.request_id,
                    )
                raise unavailable from None
            if final is not None:
                outcome = outcome_of(final, events.request_id)
                stop = from_stop(final)
                if stop is not None:
                    raise stop
                if output_format is not None:
                    try:
                        events.output = validate_output(output_format, final)
                    except InvalidOutputError:
                        outcome = Outcome(
                            "failed",
                            outcome.usage,
                            outcome.stop_reason,
                            None,
                            INVALID_OUTPUT,
                            outcome.request_id,
                        )
                        raise
        finally:
            self._auth.unanswered()
            if outcome is None:
                # Cancelled, disconnected, or left before the final message: the ceiling.
                outcome = Outcome(
                    "incomplete",
                    usage=events.usage if events is not None else TokenUsage(),
                    request_id=events.request_id if events is not None else None,
                )
            self._ledger.settle(reservation, outcome)
