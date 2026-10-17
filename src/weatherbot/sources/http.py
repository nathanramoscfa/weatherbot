# src/weatherbot/sources/http.py
"""The HTTP layer every source client shares: one client, paced, bounded, and quiet.

``open_client()`` yields the one ``httpx.AsyncClient`` a run uses: the register's
User-Agent, TLS verification on, redirects refused, and fixed timeouts. A ``Fetcher``
sends each request through it with the register's per-host pacing, at most four attempts
with full-jitter backoff and ``Retry-After``, a cap on the body's size, conditional
requests through a ``ValidatorStore``, and typed errors (``weatherbot.sources.errors``).

A request URL can carry a location's coordinates (an NWS ``/points`` path, an alerts
``point``, a Nominatim ``lat`` and ``lon``). Only DEBUG records name the full URL; every
record above DEBUG and every error message names the host and a path with those values
redacted. ``RedactingFilter`` applies the same rule to any record a handler receives.
"""

import asyncio
import hashlib
import json
import logging
import random
import re
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Collection, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import MappingProxyType
from typing import Final, Protocol, cast
from urllib.parse import parse_qsl, urlsplit

import httpx

from weatherbot.models import AdvisoryNumber, Provenance, SourceId
from weatherbot.sources import USER_AGENT
from weatherbot.sources.errors import (
    DocumentedProblem,
    RedirectRefused,
    ResponseTooLarge,
    SourceHttpError,
    SourceUnavailable,
)

LOGGER: Final = logging.getLogger("weatherbot.sources")

# Seconds between two requests to one host (the register's etiquette). The NWS API and
# Nominatim ask for at most one request per second, so the clients keep a margin.
HOST_INTERVALS: Final[Mapping[str, float]] = MappingProxyType(
    {"api.weather.gov": 1.2, "nominatim.openstreetmap.org": 1.5}
)
DEFAULT_INTERVAL: Final = 0.5
"""Seconds between two requests to any host ``HOST_INTERVALS`` does not name."""

CONNECT_TIMEOUT_SECONDS: Final = 10.0
TIMEOUT: Final = httpx.Timeout(30.0, connect=CONNECT_TIMEOUT_SECONDS)
MAX_ATTEMPTS: Final = 4
BACKOFF_SECONDS: Final = (1.0, 2.0, 4.0)
"""The ceiling of the full-jitter wait before the second, third, and fourth attempts."""
MAX_RETRY_AFTER_SECONDS: Final = 60.0
DEFAULT_MAX_BYTES: Final = 8 * 1024 * 1024

# Response headers a result keeps, the fixture recorder's allowlist (never set-cookie).
HEADER_ALLOWLIST: Final = frozenset(
    {
        "content-type",
        "content-length",
        "last-modified",
        "etag",
        "date",
        "cache-control",
        "expires",
        "age",
    }
)

HTTP_OK: Final = 200
HTTP_NOT_MODIFIED: Final = 304
HTTP_TOO_MANY_REQUESTS: Final = 429
_REDIRECTS: Final = range(300, 400)
_SERVER_ERRORS: Final = range(500, 600)
PROBLEM_JSON: Final = "application/problem+json"

REDACTED: Final = "<redacted>"
# Every coordinate form scripts/check_personal_data.py's request_coordinates() recognizes:
# an NWS /points/{lat},{lon} path, a point parameter, and lat/lon or latitude/longitude.
COORDINATE_PARAMETERS: Final = frozenset({"point", "lat", "lon", "latitude", "longitude"})
_POINTS_PATH: Final = re.compile(r"(/points/)[^/?#\s]+", re.IGNORECASE)
_COORDINATE_QUERY: Final = re.compile(
    r"(?<![A-Za-z0-9_])(point|lat|lon|latitude|longitude)=[^&#\s]*", re.IGNORECASE
)
_COORDINATE_PAIR: Final = re.compile(r"-?\d{1,3}\.\d+\s*(?:,|%2C)\s*-?\d{1,3}\.\d+", re.IGNORECASE)


def redact_text(text: str) -> str:
    """Redact every request coordinate a text may carry: in a URL or as a bare pair.

    Args:
        text: A log message, an error message, or a URL.

    Returns:
        The text with ``/points/<redacted>``, ``point=<redacted>`` (and ``lat``, ``lon``,
        ``latitude``, ``longitude``), and any decimal ``lat,lon`` pair replaced.
    """
    text = _POINTS_PATH.sub(rf"\g<1>{REDACTED}", text)
    text = _COORDINATE_QUERY.sub(rf"\g<1>={REDACTED}", text)
    return _COORDINATE_PAIR.sub(REDACTED, text)


def redact_url(url: str) -> str:
    """Return ``host/path?query`` with every coordinate redacted, for a record above DEBUG.

    Args:
        url: A request URL.

    Returns:
        The host, the path (``/points/<redacted>``), and the query with the values of
        ``point``, ``lat``, ``lon``, ``latitude``, and ``longitude`` redacted.
    """
    parts = urlsplit(url)
    query = "&".join(
        f"{name}={REDACTED if name.lower() in COORDINATE_PARAMETERS else value}"
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
    )
    shown = f"{parts.hostname or ''}{_POINTS_PATH.sub(rf'\g<1>{REDACTED}', parts.path)}"
    return redact_text(f"{shown}?{query}" if query else shown)


def describe(url: str) -> str:
    """Return the host and the redacted path of a URL, for an error message: no query.

    Args:
        url: A request URL.

    Returns:
        For example ``api.weather.gov/points/<redacted>``.
    """
    parts = urlsplit(url)
    return redact_text(f"{parts.hostname or ''}{parts.path}")


class RedactingFilter(logging.Filter):
    """A handler filter that redacts request coordinates from every record above DEBUG."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact the record's message in place when it is above DEBUG.

        Args:
            record: The record.

        Returns:
            Always true: the record is kept, redacted.
        """
        if record.levelno > logging.DEBUG:
            message = record.getMessage()
            redacted = redact_text(message)
            if redacted != message:
                record.msg = redacted
                record.args = None
        return True


def client_timeout(seconds: float | None = None) -> httpx.Timeout:
    """Return a client's timeout: ``seconds`` for every phase, connecting at most 10 s.

    Args:
        seconds: The ``[http] timeout_seconds`` setting; ``None`` means 30 seconds.

    Returns:
        The timeout.
    """
    if seconds is None:
        return TIMEOUT
    return httpx.Timeout(seconds, connect=min(seconds, CONNECT_TIMEOUT_SECONDS))


@asynccontextmanager
async def open_client(timeout_seconds: float | None = None) -> AsyncGenerator[httpx.AsyncClient]:
    """Open the one HTTP client a run uses, and close it when the run ends.

    Args:
        timeout_seconds: The ``[http] timeout_seconds`` setting; ``None`` means 30.

    Yields:
        A client with the User-Agent header, TLS verification on, redirects refused, and
        the timeout, with a connect timeout of at most 10 seconds.
    """
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
        verify=True,
        timeout=client_timeout(timeout_seconds),
    ) as client:
        yield client


class HostPacer:
    """Spaces the requests to each host by its interval; hosts never wait for each other.

    Concurrent requests to one host leave in the order they asked, one interval apart.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        intervals: Mapping[str, float] = HOST_INTERVALS,
        default: float = DEFAULT_INTERVAL,
    ) -> None:
        """Create a pacer.

        Args:
            clock: Seconds on a monotonic clock.
            sleep: Waits a number of seconds.
            intervals: The minimum interval per host name.
            default: The minimum interval for any other host.
        """
        self._clock = clock
        self._sleep = sleep
        self._intervals = intervals
        self._default = default
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, host: str) -> None:
        """Wait until a request to ``host`` may leave, then count it as sent.

        Args:
            host: The request's host name.
        """
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            last = self._last.get(host)
            if last is not None:
                remaining = last + self._intervals.get(host, self._default) - self._clock()
                if remaining > 0:
                    await self._sleep(remaining)
            self._last[host] = self._clock()


@dataclass(frozen=True)
class StoredResponse:
    """What a ``ValidatorStore`` keeps per URL: the validators and the body they cover."""

    etag: str | None
    last_modified: str | None
    body: bytes = field(repr=False)
    sha256: str
    headers: Mapping[str, str]


class ValidatorStore(Protocol):
    """Keeps the last validated answer per URL, so a request can be conditional."""

    def load(self, url: str) -> StoredResponse | None:
        """Return the stored answer for ``url``, if any."""
        ...

    def save(self, url: str, stored: StoredResponse) -> None:
        """Store the answer for ``url``, replacing the previous one."""
        ...


class MemoryValidatorStore:
    """A ``ValidatorStore`` that lasts as long as the run (Step 5 persists one)."""

    def __init__(self) -> None:
        """Create an empty store."""
        self._stored: dict[str, StoredResponse] = {}

    def load(self, url: str) -> StoredResponse | None:
        """Return the stored answer for ``url``, if any.

        Args:
            url: The request URL.

        Returns:
            The stored answer.
        """
        return self._stored.get(url)

    def save(self, url: str, stored: StoredResponse) -> None:
        """Store the answer for ``url``.

        Args:
            url: The request URL.
            stored: The answer.
        """
        self._stored[url] = stored


@dataclass(frozen=True)
class FetchResult:
    """One answer: what a parser reads and what the raw-response cache stores.

    ``url`` and ``body`` stay out of ``repr``: the URL can carry coordinates.
    """

    source_id: SourceId
    url: str = field(repr=False)
    status: int
    body: bytes = field(repr=False)
    headers: Mapping[str, str]
    fetched_at: datetime
    sha256: str
    not_modified: bool = False

    def provenance(
        self, *, issued_at: datetime | None = None, advisory: AdvisoryNumber | None = None
    ) -> Provenance:
        """Return the provenance of the records parsed from this answer.

        Args:
            issued_at: The product's own issuance, when it states one.
            advisory: The product's advisory, when it has one.

        Returns:
            The provenance.
        """
        return Provenance(
            source_id=self.source_id,
            url=self.url,
            status=self.status,
            fetched_at=self.fetched_at,
            sha256=self.sha256,
            issued_at=issued_at,
            advisory=advisory,
            etag=self.headers.get("etag"),
            last_modified=self.headers.get("last-modified"),
            not_modified=self.not_modified,
        )


@dataclass(frozen=True)
class SourceResult[T]:
    """What a fetch function returns: the parsed records and the answers behind them."""

    records: T
    responses: tuple[FetchResult, ...]


def kept_headers(headers: httpx.Headers) -> dict[str, str]:
    """Keep only the allowlisted response headers, lower-cased and sorted by name.

    Args:
        headers: The response headers.

    Returns:
        The kept headers.
    """
    return {name: value for name, value in sorted(headers.items()) if name in HEADER_ALLOWLIST}


def retry_after_seconds(value: str | None, now: datetime) -> float | None:
    """Read a ``Retry-After`` header: delay seconds, or an HTTP date.

    Args:
        value: The header's value.
        now: The current instant, for an HTTP date.

    Returns:
        The seconds to wait (never negative), or ``None`` when absent or unreadable.
    """
    if value is None or not value.strip():
        return None
    text = value.strip()
    if text.isdigit():
        return float(text)
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - now).total_seconds(), 0.0)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _Answer:
    status: int
    headers: httpx.Headers
    body: bytes = field(repr=False)


@dataclass
class Fetcher:
    """Sends a run's requests: paced per host, retried, size-capped, and conditional."""

    client: httpx.AsyncClient
    pacer: HostPacer = field(default_factory=HostPacer)
    validators: ValidatorStore = field(default_factory=MemoryValidatorStore)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    jitter: Callable[[], float] = random.random
    """Returns a number in [0, 1): the full-jitter fraction of each backoff ceiling."""
    now: Callable[[], datetime] = _now
    clock: Callable[[], float] = time.monotonic
    attempts: int = MAX_ATTEMPTS

    async def get(
        self,
        url: str,
        *,
        source_id: SourceId,
        accept: Collection[int] = (HTTP_OK,),
        problems: Collection[int] = (),
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> FetchResult:
        """Fetch ``url``.

        Args:
            url: The complete request URL, query string included.
            source_id: The register id, for provenance, errors, and log records.
            accept: The statuses returned as results.
            problems: The statuses whose ``application/problem+json`` answer the source
                documents; each raises ``DocumentedProblem``.
            max_bytes: The most body bytes read before ``ResponseTooLarge``.

        Returns:
            The answer; a 304 returns the stored body with ``not_modified`` set.

        Raises:
            SourceUnavailable: Every attempt failed, or ``Retry-After`` asked for more than
                60 seconds.
            SourceHttpError: A status neither accepted nor documented.
            DocumentedProblem: A declared problem status with a problem+json body.
            ResponseTooLarge: The body passed ``max_bytes``.
            RedirectRefused: A redirect.
        """
        shown = describe(url)
        stored = self.validators.load(url)
        conditional: dict[str, str] = {}
        if stored is not None and stored.etag:
            conditional["If-None-Match"] = stored.etag
        if stored is not None and stored.last_modified:
            conditional["If-Modified-Since"] = stored.last_modified
        LOGGER.debug("%s GET %s", source_id, url)
        started = self.clock()
        answer = await self._attempts(
            url, conditional=conditional, max_bytes=max_bytes, source_id=source_id, shown=shown
        )
        status = answer.status
        elapsed = self.clock() - started
        LOGGER.info(
            "%s %s -> %d, %d bytes, %.2f s",
            source_id,
            redact_url(url),
            status,
            len(answer.body),
            elapsed,
        )
        headers = kept_headers(answer.headers)
        if status == HTTP_NOT_MODIFIED:
            if stored is None:
                message = f"HTTP 304 from {shown} to an unconditional request"
                raise SourceHttpError(source_id, message, status=status)
            return FetchResult(
                source_id=source_id,
                url=url,
                status=status,
                body=stored.body,
                headers={**stored.headers, **headers},
                fetched_at=self.now(),
                sha256=stored.sha256,
                not_modified=True,
            )
        if status in _REDIRECTS:
            location: str | None = answer.headers.get("location")
            target = urlsplit(location).hostname if location else None
            raise RedirectRefused(source_id, status=status, target_host=target or None)
        if status in problems:
            if answer.headers.get("content-type", "").startswith(PROBLEM_JSON):
                problem_type, title = _problem(answer.body)
                raise DocumentedProblem(
                    source_id, status=status, problem_type=problem_type, title=title
                )
            message = f"HTTP {status} from {shown} without a problem+json body"
            raise SourceHttpError(source_id, message, status=status)
        if status not in accept:
            message = f"unexpected HTTP {status} from {shown}"
            raise SourceHttpError(source_id, message, status=status)
        digest = hashlib.sha256(answer.body).hexdigest()
        if status == HTTP_OK and (headers.get("etag") or headers.get("last-modified")):
            self.validators.save(
                url,
                StoredResponse(
                    etag=headers.get("etag"),
                    last_modified=headers.get("last-modified"),
                    body=answer.body,
                    sha256=digest,
                    headers=headers,
                ),
            )
        return FetchResult(
            source_id=source_id,
            url=url,
            status=status,
            body=answer.body,
            headers=headers,
            fetched_at=self.now(),
            sha256=digest,
        )

    async def _attempts(
        self,
        url: str,
        *,
        conditional: Mapping[str, str],
        max_bytes: int,
        source_id: SourceId,
        shown: str,
    ) -> _Answer:
        """Send up to ``attempts`` requests; return the first answer that is not retried."""
        host = urlsplit(url).hostname or ""
        problem = "no attempt"
        for attempt in range(self.attempts):
            await self.pacer.wait(host)
            delay: float | None = None
            try:
                answer = await self._send(url, conditional, max_bytes, source_id, shown)
            except httpx.TransportError as error:
                problem = type(error).__name__
                LOGGER.info(
                    "%s %s: %s on attempt %d", source_id, redact_url(url), problem, attempt + 1
                )
            else:
                if answer.status != HTTP_TOO_MANY_REQUESTS and answer.status not in _SERVER_ERRORS:
                    return answer
                problem = f"HTTP {answer.status}"
                LOGGER.info(
                    "%s %s -> %d on attempt %d",
                    source_id,
                    redact_url(url),
                    answer.status,
                    attempt + 1,
                )
                delay = retry_after_seconds(answer.headers.get("retry-after"), self.now())
                if delay is not None and delay > MAX_RETRY_AFTER_SECONDS:
                    message = (
                        f"{shown} asked to retry after {delay:.0f} s, over the "
                        f"{MAX_RETRY_AFTER_SECONDS:.0f} s limit ({problem})"
                    )
                    raise SourceUnavailable(source_id, message)
            if attempt + 1 < self.attempts:
                ceiling = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                await self.sleep(max(self.jitter() * ceiling, delay or 0.0))
        message = f"{shown} failed after {self.attempts} attempts ({problem})"
        raise SourceUnavailable(source_id, message)

    async def _send(
        self,
        url: str,
        conditional: Mapping[str, str],
        max_bytes: int,
        source_id: SourceId,
        shown: str,
    ) -> _Answer:
        async with self.client.stream("GET", url, headers=dict(conditional)) as response:
            status = response.status_code
            if status in _REDIRECTS or status in _SERVER_ERRORS or status == HTTP_TOO_MANY_REQUESTS:
                return _Answer(status, response.headers, b"")
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > max_bytes:
                message = f"{shown} declares {declared} bytes, over the {max_bytes} byte cap"
                raise ResponseTooLarge(source_id, message)
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > max_bytes:
                    message = f"{shown} sent more than the {max_bytes} byte cap"
                    raise ResponseTooLarge(source_id, message)
            return _Answer(status, response.headers, bytes(body))


def _problem(body: bytes) -> tuple[str | None, str | None]:
    """Read a problem+json body's ``type`` and ``title``; never its ``detail``."""
    try:
        document: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    if not isinstance(document, dict):
        return None, None
    fields = cast("dict[str, object]", document)
    problem_type, title = fields.get("type"), fields.get("title")
    return (
        problem_type if isinstance(problem_type, str) else None,
        redact_text(title) if isinstance(title, str) else None,
    )
