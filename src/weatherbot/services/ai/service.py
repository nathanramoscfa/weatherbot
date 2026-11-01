# src/weatherbot/services/ai/service.py
"""``AiService``: what every surface asks for the AI's state, and the one caller it builds.

``state()`` is computed without a request: ``off`` while ``[ai] enabled`` is false or no
credential exists, ``unavailable`` for an unpriced model or while three consecutive 401
or 403 answers hold it, ``paused`` while the ledger's pause holds, ``capped`` when today's
headroom is below the ceiling of the smallest request (a change summary at
``summary_model``), and ``ready`` otherwise. A larger request that would not fit is still
refused as ``capped`` while the state reads ``ready``. ``caller()`` constructs the client
once, on first use, and never while AI is off; ``probe()`` sends one free
``count_tokens`` request, which the ledger does not record, for ``doctor``'s online
check. The credential's source is resolved once per service and never its value.

This module imports the SDK only inside ``caller()`` and ``probe()``, so a surface can
read the state's types without loading it.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import TYPE_CHECKING, Final, Literal

from sqlalchemy import Engine

from weatherbot.services.ai.errors import (
    AiUnavailable,
    AiUnavailableReason,
    AuthGuard,
    from_exception,
)
from weatherbot.services.ai.ledger import Ledger, LedgerDay, micro_usd
from weatherbot.services.ai.pricing import PRICES, ceiling_micro_usd
from weatherbot.services.config import AiSettings

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

    from weatherbot.services.ai.caller import AiCaller
    from weatherbot.services.ai.client import ClaudeFactory

type AiStateName = Literal["off", "ready", "paused", "capped", "unavailable"]
type CredentialSource = Literal["environment", "auth_token", "profile", "none"]

SMALLEST_REQUEST_PROMPT_TOKENS: Final = 2_000
"""A change summary's frozen prompt alone: a floor for the smallest request's prompt."""
SMALLEST_REQUEST_MAX_TOKENS: Final = 1_500
"""A change summary's ``max_tokens``."""
PROBE_TEXT: Final = "ready"


@dataclass(frozen=True)
class AiState:
    """The AI's state, as ``/api/health``, ``doctor``, and the pages show it."""

    state: AiStateName
    reason: AiUnavailableReason | None
    credential: CredentialSource | None
    """Where the credential comes from; ``None`` while ``[ai] enabled`` is false."""
    model: str
    summary_model: str
    change_summaries: bool
    outlook_narration: bool
    today: LedgerDay


def smallest_ceiling(model: str) -> int:
    """The ceiling of the smallest request, a change summary, on ``model``.

    Args:
        model: The summary model.

    Returns:
        The ceiling in micro-dollars.
    """
    return ceiling_micro_usd(model, SMALLEST_REQUEST_PROMPT_TOKENS, SMALLEST_REQUEST_MAX_TOKENS)


class AiService:
    """The AI's state, its ledger, and the one caller every product uses."""

    def __init__(  # noqa: PLR0913 - the engine and settings, then keyword-only seams
        self,
        engine: Engine,
        settings: AiSettings,
        *,
        factory: "ClaudeFactory",
        environ: Mapping[str, str] | None = None,
        now: Callable[[], datetime],
        local_zone: tzinfo | None = None,
    ) -> None:
        """Create the service; no client is constructed yet.

        Args:
            engine: The AI engine (``guard.ai_engine``); ``close`` disposes of it.
            settings: The ``[ai]`` table.
            factory: Builds the client; the SDK resolves the credential.
            environ: The environment; ``os.environ`` when omitted.
            now: The clock.
            local_zone: The operator's zone for the ledger's day; the machine's by default.
        """
        self._engine = engine
        self._settings = settings
        self._factory = factory
        self._environ: Mapping[str, str] = os.environ if environ is None else environ
        self._now = now
        self._ledger = Ledger(
            engine, cap_micro_usd=micro_usd(settings.daily_cap_usd), now=now, local_zone=local_zone
        )
        self._auth = AuthGuard(now)
        self._credential: CredentialSource | None = None
        self._client: AsyncAnthropic | None = None
        self._caller: AiCaller | None = None

    @property
    def settings(self) -> AiSettings:
        """The ``[ai]`` table."""
        return self._settings

    @property
    def ledger(self) -> Ledger:
        """The ledger."""
        return self._ledger

    def credential(self) -> CredentialSource:
        """Resolve where the credential comes from, once; never its value.

        Returns:
            The source.
        """
        if self._credential is None:
            from weatherbot.services.ai.client import credential_source  # noqa: PLC0415 - the SDK loads only when AI is asked

            self._credential = credential_source(self._environ, self._factory)
        return self._credential

    def _priced(self) -> bool:
        return self._settings.model in PRICES and self._settings.summary_model in PRICES

    def _blocked(self) -> tuple[AiStateName, AiUnavailableReason] | None:
        """Why AI cannot take a request now, before the ledger is read."""
        if not self._settings.enabled:
            return "off", "disabled"
        if not self._priced():
            return "unavailable", "price_unknown"
        if self.credential() == "none":
            return "off", "no_credential"
        if self._auth.held:
            return "unavailable", "auth_failed"
        return None

    def state(self) -> AiState:
        """Compute the AI's state without a request.

        Returns:
            The state, the reason, the credential's source, the models, the features,
            and today's spend.
        """
        today = self._ledger.today()
        blocked = self._blocked()
        name: AiStateName = "ready"
        reason: AiUnavailableReason | None = None
        if blocked is not None:
            name, reason = blocked
        elif today.paused:
            name, reason = "paused", "paused"
        elif today.headroom_micro_usd < smallest_ceiling(self._settings.summary_model):
            name, reason = "capped", "capped"
        return AiState(
            state=name,
            reason=reason,
            credential=self.credential() if self._settings.enabled else None,
            model=self._settings.model,
            summary_model=self._settings.summary_model,
            change_summaries=self._settings.change_summaries,
            outlook_narration=self._settings.outlook_narration,
            today=today,
        )

    def caller(self) -> "AiCaller":
        """Return the caller, constructing the client on first use.

        Returns:
            The caller every request goes through.

        Raises:
            AiUnavailable: ``disabled``, ``price_unknown``, or ``no_credential``; the client
                is never constructed then.
        """
        blocked = self._blocked()
        if blocked is not None and blocked[1] != "auth_failed":
            raise AiUnavailable(reason=blocked[1])
        if self._caller is None:
            import anthropic  # noqa: PLC0415 - the SDK loads only when AI is used

            from weatherbot.services.ai.caller import AiCaller  # noqa: PLC0415 - as above
            from weatherbot.services.ai.client import has_credential  # noqa: PLC0415 - as above

            try:
                client = self._factory()
            except anthropic.CredentialsError:
                raise AiUnavailable(reason="no_credential") from None
            if not has_credential(client):
                raise AiUnavailable(reason="no_credential")
            self._client = client
            self._caller = AiCaller(lambda: client, self._ledger, now=self._now, auth=self._auth)
        return self._caller

    async def probe(self) -> int:
        """Prove the credential with one free ``count_tokens`` request; the ledger skips it.

        Returns:
            The probe's token count.

        Raises:
            AiUnavailable: AI is off, or Anthropic answered with an error (its reason only).
        """
        import anthropic  # noqa: PLC0415 - the SDK loads only when AI is used

        self.caller()
        client = self._client
        if client is None:  # pragma: no cover - caller() set it or raised
            raise AiUnavailable(reason="no_credential")
        try:
            counted = await client.messages.count_tokens(
                model=self._settings.model,
                messages=[{"role": "user", "content": PROBE_TEXT}],
            )
        except anthropic.AnthropicError as error:
            if isinstance(error, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
                self._auth.refused()
            raise from_exception(error) from None
        self._auth.answered()
        return counted.input_tokens

    async def close(self) -> None:
        """Close the client, if one was built, and dispose of the AI engine."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._caller = None
        self._engine.dispose()
