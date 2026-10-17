# src/weatherbot/services/logs.py
"""Logging: one redacting handler on the root logger, and a run's Source-drift warnings.

``configure_logging`` installs one standard-error handler on the root logger with the
Step 2 ``RedactingFilter``, so a record from any logger, httpx's included, names no
request coordinate above DEBUG. httpx and httpcore log each request's full URL at INFO,
and Alembic its migration chatter, so they stay at WARNING unless the level is DEBUG.
``collect_drift`` gathers the Source-drift warnings a fetch logs
(``weatherbot.sources.drift``) for the snapshot.
"""

import logging
import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Final, cast, override

from weatherbot.services.persistence.repositories import DriftWarning
from weatherbot.sources.drift import DRIFT_ATTRIBUTE
from weatherbot.sources.http import LOGGER as SOURCES_LOGGER
from weatherbot.sources.http import RedactingFilter, redact_text

if TYPE_CHECKING:
    from weatherbot.models import SourceId

FORMAT: Final = "%(levelname)s %(name)s: %(message)s"
QUIET_LIBRARIES: Final = ("httpx", "httpcore", "alembic")
"""Libraries that log request URLs or migration chatter at INFO: WARNING unless DEBUG."""


class StandardErrorHandler(logging.Handler):
    """A handler on whatever ``sys.stderr`` is when a record arrives.

    A test runner replaces standard error per command; the handler follows it.
    """

    def __init__(self) -> None:
        """Create the handler with the redaction filter and the format."""
        super().__init__()
        self.addFilter(RedactingFilter())
        self.setFormatter(logging.Formatter(FORMAT))

    @override
    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stderr.write(f"{self.format(record)}\n")
        except RecursionError:
            raise
        except Exception:  # noqa: BLE001 - logging's contract: a handler reports, never raises
            self.handleError(record)


def configure_logging(level: str) -> None:
    """Configure logging for a command: one redacting handler, at ``level``.

    Calling it again replaces the level and keeps the one handler.

    Args:
        level: ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, or ``CRITICAL``.
    """
    root = logging.getLogger()
    handler = next((h for h in root.handlers if isinstance(h, StandardErrorHandler)), None)
    if handler is None:
        handler = StandardErrorHandler()
        root.addHandler(handler)
    root.setLevel(level)
    handler.setLevel(level)
    quiet = logging.DEBUG if level == "DEBUG" else logging.WARNING
    for name in QUIET_LIBRARIES:
        logging.getLogger(name).setLevel(quiet)


class DriftCollector(logging.Handler):
    """Keeps every Source-drift warning logged while it is attached."""

    def __init__(self) -> None:
        """Create an empty collector."""
        super().__init__(logging.WARNING)
        self.warnings: list[DriftWarning] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        source: object = getattr(record, DRIFT_ATTRIBUTE, None)
        if isinstance(source, str):
            message = redact_text(record.getMessage()).removeprefix(f"Source drift: {source}: ")
            self.warnings.append(DriftWarning(cast("SourceId", source), message))


@contextmanager
def collect_drift() -> Generator[DriftCollector]:
    """Collect the Source-drift warnings logged inside the block.

    The sources logger is lowered to WARNING for the block when the configured level is
    higher, so a warning is still collected; the root handler's own level still decides
    whether it is printed.

    Yields:
        The collector; its ``warnings`` fill as the block runs.
    """
    collector = DriftCollector()
    previous = SOURCES_LOGGER.level
    if SOURCES_LOGGER.getEffectiveLevel() > logging.WARNING:
        SOURCES_LOGGER.setLevel(logging.WARNING)
    SOURCES_LOGGER.addHandler(collector)
    try:
        yield collector
    finally:
        SOURCES_LOGGER.removeHandler(collector)
        SOURCES_LOGGER.setLevel(previous)
