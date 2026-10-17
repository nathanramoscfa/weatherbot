# src/weatherbot/sources/errors.py
"""The errors a source raises, each with the source's register id and a kind.

A message names the source, the host, and a path with every coordinate redacted, and
never a query string or a response body: a request URL can carry a location's
coordinates, and an error message reaches logs and terminals.
"""

from typing import ClassVar

from weatherbot.models import SourceId


class SourceError(Exception):
    """A source failed; ``kind`` names how, for the snapshot's outcome record."""

    kind: ClassVar[str] = "source_error"

    def __init__(self, source_id: SourceId, message: str) -> None:
        """Create the error.

        Args:
            source_id: The register id of the source that failed.
            message: What failed, free of coordinates and query strings.
        """
        super().__init__(f"{source_id}: {message}")
        self.source_id: SourceId = source_id


class SourceUnavailable(SourceError):  # noqa: N818 - the roadmap fixes this name
    """Every attempt failed: transport errors, 5xx, or 429 answers."""

    kind: ClassVar[str] = "unavailable"


class SourceHttpError(SourceError):
    """A status the caller did not declare, or an ArcGIS error object in a 200 answer."""

    kind: ClassVar[str] = "http_error"

    def __init__(self, source_id: SourceId, message: str, *, status: int) -> None:
        """Create the error.

        Args:
            source_id: The register id.
            message: What failed.
            status: The HTTP status, or the ArcGIS error object's code.
        """
        super().__init__(source_id, message)
        self.status = status


class DocumentedProblem(SourceError):  # noqa: N818 - the roadmap fixes this name
    """An ``application/problem+json`` answer with a status the caller declared.

    The NWS API documents these answers (an out-of-coverage ``/points`` request is a 404
    ``InvalidPoint``). ``problem_type`` and ``title`` are kept; ``detail`` is not, because
    it repeats the requested coordinates.
    """

    kind: ClassVar[str] = "documented_problem"

    def __init__(
        self, source_id: SourceId, *, status: int, problem_type: str | None, title: str | None
    ) -> None:
        """Create the error.

        Args:
            source_id: The register id.
            status: The HTTP status.
            problem_type: The problem's ``type`` URI.
            title: The problem's ``title``, with any coordinate redacted.
        """
        super().__init__(source_id, f"HTTP {status} problem {problem_type or 'about:blank'}")
        self.status = status
        self.problem_type = problem_type
        self.title = title


class SourceSchemaError(SourceError):
    """A payload that breaks the register's shape: a missing field, a wrong type."""

    kind: ClassVar[str] = "schema"


class ResponseTooLarge(SourceError):  # noqa: N818 - the roadmap fixes this name
    """A body over the request's size cap; reading stopped at the cap."""

    kind: ClassVar[str] = "too_large"


class RedirectRefused(SourceError):  # noqa: N818 - the roadmap fixes this name
    """A redirect, which no client follows; the message names only the target host."""

    kind: ClassVar[str] = "redirect_refused"

    def __init__(self, source_id: SourceId, *, status: int, target_host: str | None) -> None:
        """Create the error.

        Args:
            source_id: The register id.
            status: The redirect status.
            target_host: The host the ``Location`` header names, if any.
        """
        super().__init__(
            source_id, f"HTTP {status} redirect to {target_host or 'an unnamed host'} refused"
        )
        self.status = status
        self.target_host = target_host
