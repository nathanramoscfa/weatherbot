# src/weatherbot/services/network.py
"""How the services reach the official sources: one client and one fetcher per run.

``Network`` opens the run's one HTTP client with the ``[http] timeout_seconds`` setting
and builds its ``Fetcher`` on a validator store, which is the database's raw-response
cache wherever a database is open, so requests are conditional between runs. The fetcher
factory is a seam: the tests build fetchers whose pacing waits are recorded, never slept.
``SourceError`` is re-exported for the command line, which imports the services only.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from weatherbot.sources.errors import SourceError
from weatherbot.sources.http import (
    COORDINATE_PARAMETERS,
    REDACTED,
    Fetcher,
    FetchResult,
    ValidatorStore,
    open_client,
    redact_text,
)

__all__ = ["FetcherFactory", "Network", "SourceError", "default_fetcher", "product_key"]

type FetcherFactory = Callable[[httpx.AsyncClient, ValidatorStore], Fetcher]


def default_fetcher(client: httpx.AsyncClient, validators: ValidatorStore) -> Fetcher:
    """Build the fetcher a real run uses: the register's pacing, retries, and the store.

    Args:
        client: The run's client.
        validators: The validator store.

    Returns:
        The fetcher.
    """
    return Fetcher(client, validators=validators)


@dataclass(frozen=True)
class Network:
    """The run's network settings: the timeout and the fetcher factory."""

    timeout_seconds: float | None = None
    make_fetcher: FetcherFactory = default_fetcher

    @asynccontextmanager
    async def fetcher(self, validators: ValidatorStore) -> AsyncGenerator[Fetcher]:
        """Open the run's one client and yield its fetcher; the client closes after.

        Args:
            validators: The validator store the fetcher's requests are conditional on.

        Yields:
            The fetcher.
        """
        async with open_client(self.timeout_seconds) as client:
            yield self.make_fetcher(client, validators)


def product_key(result: FetchResult) -> str:
    """Name the product an answer carried within its source: its path and query.

    A coordinate never enters a key: the ``/points`` path and the coordinate parameters
    are redacted, so a caller that needs a key per location adds the location's name.

    Args:
        result: The answer.

    Returns:
        The key, such as ``/CurrentStorms.json``.
    """
    parts = urlsplit(result.url)
    query = "&".join(
        f"{name}={REDACTED}" if name.lower() in COORDINATE_PARAMETERS else item
        for item in parts.query.split("&")
        if item
        for name in (item.split("=", 1)[0],)
    )
    return redact_text(f"{parts.path}?{query}" if query else parts.path)
