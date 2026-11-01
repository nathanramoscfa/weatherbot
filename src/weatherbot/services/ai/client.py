# src/weatherbot/services/ai/client.py
"""The Anthropic client, and where its credential comes from — never the credential itself.

``default_client`` builds the one client shape Weatherbot uses: asynchronous, two retries,
a two-minute timeout that connects within ten seconds, and an HTTP client that refuses
redirects, as every other client in the project does. The SDK resolves the credential in
its own order (``ANTHROPIC_API_KEY``, ``ANTHROPIC_AUTH_TOKEN``, an ``ant auth login``
profile); nothing here reads the key's value. ``credential_source`` names the source by
which variable is set, and for a profile by whether the SDK can construct a client, and
keeps nothing. A blank variable is unset, exactly as the SDK reads it.
"""

from collections.abc import Callable, Mapping
from typing import Final

import anthropic
from anthropic import AsyncAnthropic

from weatherbot.services.ai.service import CredentialSource

type ClaudeClient = AsyncAnthropic
"""The client type, named here so a module outside the package never imports the SDK."""
type ClaudeFactory = Callable[[], ClaudeClient]

API_KEY_VARIABLE: Final = "ANTHROPIC_API_KEY"
AUTH_TOKEN_VARIABLE: Final = "ANTHROPIC_AUTH_TOKEN"  # noqa: S105 - a variable's name, not a token
MAX_RETRIES: Final = 2
TIMEOUT_S: Final = 120.0
CONNECT_TIMEOUT_S: Final = 10.0
SOURCE_TEXT: Final[dict[CredentialSource, str]] = {
    "environment": "the environment (ANTHROPIC_API_KEY)",
    "auth_token": "the environment (ANTHROPIC_AUTH_TOKEN)",  # a label, not a token  # nosec B105
    "profile": "an ant auth login profile",
    "none": "no credential",
}
"""How a person reads each source; never a value or a path."""


def default_client() -> AsyncAnthropic:
    """Build the client; the SDK resolves the credential.

    Returns:
        The client.

    Raises:
        CredentialsError: The SDK found no credential.
    """
    return AsyncAnthropic(
        max_retries=MAX_RETRIES,
        timeout=anthropic.Timeout(TIMEOUT_S, connect=CONNECT_TIMEOUT_S),
        http_client=anthropic.DefaultAsyncHttpxClient(follow_redirects=False),
    )


def _set(environ: Mapping[str, str], variable: str) -> bool:
    # The SDK reads ``environ.get(variable) or None``: only an empty value is unset.
    return bool(environ.get(variable))


def credential_source(environ: Mapping[str, str], factory: ClaudeFactory) -> CredentialSource:
    """Name where the SDK will find the credential, in the SDK's order; keep nothing.

    Args:
        environ: The environment.
        factory: Builds a client; called only when neither variable is set, to learn
            whether a profile supplies the credential (the client must also hold one:
            ``has_credential``). The client is dropped unused.

    Returns:
        ``environment``, ``auth_token``, ``profile``, or ``none``.
    """
    if _set(environ, API_KEY_VARIABLE):
        return "environment"
    if _set(environ, AUTH_TOKEN_VARIABLE):
        return "auth_token"
    try:
        client = factory()
    except anthropic.CredentialsError:
        return "none"
    return "profile" if has_credential(client) else "none"


def has_credential(client: AsyncAnthropic) -> bool:
    """Whether the SDK resolved any credential for a client; never the credential itself.

    With no profile directory at all, the SDK constructs a client with nothing resolved
    and fails only at its first request, with a ``TypeError`` (probed with anthropic
    2.3.0), so a constructed client is not proof of a credential.

    Args:
        client: A constructed client.

    Returns:
        Whether it holds an API key, an auth token, or a credentials provider.
    """
    return any(
        value is not None for value in (client.api_key, client.auth_token, client.credentials)
    )


def blank_key(environ: Mapping[str, str]) -> bool:
    """Whether ``ANTHROPIC_API_KEY`` is set but blank, for ``doctor`` to note.

    An empty variable is unset to the SDK, so a profile still applies; a variable of only
    whitespace is sent, and Anthropic refuses it.

    Args:
        environ: The environment.

    Returns:
        Whether the variable exists and is empty or only whitespace.
    """
    return API_KEY_VARIABLE in environ and not environ[API_KEY_VARIABLE].strip()
