# src/weatherbot/services/logs.py
"""Logging: one redacting handler on the root logger, and a run's Source-drift warnings.

``configure_logging`` installs one standard-error handler on the root logger with the
Step 2 ``RedactingFilter``, so a record from any logger, httpx's included, names no
request coordinate above DEBUG, and with ``SecretFilter``, so no record at any level
carries an Anthropic key shape, an ``Authorization`` or ``X-Api-Key`` value, or the value
after ``ANTHROPIC_API_KEY=``; ``RedactingFormatter`` applies both to tracebacks. httpx and
httpcore log each request's full URL at INFO, and Alembic its migration chatter, so they
stay at WARNING unless the level is DEBUG. The Anthropic SDK logs each request's whole
options, the prompt and the question included, at DEBUG, so ``anthropic``, ``httpx2``,
and ``httpcore2`` stay at WARNING at every level, DEBUG included. ``collect_drift`` gathers
the Source-drift warnings a fetch logs (``weatherbot.sources.drift``) for the snapshot.
"""

import atexit
import io
import logging
import os
import re
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Final, TextIO, cast, override

from weatherbot.services.config import ensure_directory
from weatherbot.services.persistence.repositories import DriftWarning
from weatherbot.sources.drift import DRIFT_ATTRIBUTE
from weatherbot.sources.http import LOGGER as SOURCES_LOGGER
from weatherbot.sources.http import REDACTED, RedactingFilter, redact_text

if TYPE_CHECKING:
    from weatherbot.models import SourceId

type _ExcInfo = (
    tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]
)

FORMAT: Final = "%(levelname)s %(name)s: %(message)s"
FILE_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_MAX_BYTES: Final = 1_048_576
LOG_BACKUP_COUNT: Final = 5
QUIET_LIBRARIES: Final = (
    "httpx",
    "httpcore",
    "alembic",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
)
"""Libraries that log request URLs or migration chatter at INFO: WARNING unless DEBUG."""
SILENT_LIBRARIES: Final = ("anthropic", "httpx2", "httpcore2")
"""The Anthropic SDK and its HTTP stack, which log whole requests at DEBUG: always WARNING."""
# The key's prefix is assembled, so this file holds no key-shaped string for the scans.
_KEY_SHAPE: Final = re.compile(re.escape("sk" + "-" + "ant" + "-") + r"[A-Za-z0-9_\-]+")
_HEADER_VALUE: Final = re.compile(
    r"(\b(?:authorization|x-api-key)\b[\"']?\s*[:=]\s*[\"']?)(?:bearer\s+)?[^\s\"',;}]+",
    re.IGNORECASE,
)
_KEY_ASSIGNMENT: Final = re.compile(
    r"(\bANTHROPIC_API_KEY\s*=\s*[\"']?)[^\s\"',;}]+", re.IGNORECASE
)

_DEVNULL_HOLDERS: list[TextIO] = []


def redact_secrets(text: str) -> str:
    """Redact every credential a text may carry: a key shape and an authorization value.

    Args:
        text: A log message or a formatted traceback.

    Returns:
        The text with an Anthropic key shape, the value after ``Authorization:`` or
        ``X-Api-Key:`` (any case, with or without ``Bearer``), and the value after
        ``ANTHROPIC_API_KEY=`` replaced by ``<redacted>``.
    """
    text = _KEY_SHAPE.sub(REDACTED, text)
    text = _HEADER_VALUE.sub(rf"\g<1>{REDACTED}", text)
    return _KEY_ASSIGNMENT.sub(rf"\g<1>{REDACTED}", text)


class SecretFilter(logging.Filter):
    """A handler filter that redacts credentials from every record, at every level."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact_secrets(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


class RedactingFormatter(logging.Formatter):
    """Formats records and redacts formatted tracebacks (``formatException`` and ``exc_text``)."""

    @override
    def formatException(self, ei: _ExcInfo) -> str:
        return redact_secrets(redact_text(super().formatException(ei)))

    @override
    def format(self, record: logging.LogRecord) -> str:
        if record.exc_text is not None:
            record.exc_text = redact_secrets(redact_text(record.exc_text))
        formatted = super().format(record)
        if record.exc_text is not None:
            record.exc_text = redact_secrets(redact_text(record.exc_text))
        return formatted


class UtcFormatter(RedactingFormatter):
    """Formats ``%(asctime)s`` as a UTC ISO-8601 timestamp (``YYYY-MM-DDTHH:MM:SSZ``)."""

    @override
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        instant = datetime.fromtimestamp(record.created, UTC)
        if datefmt is not None:
            return instant.strftime(datefmt)
        return instant.strftime("%Y-%m-%dT%H:%M:%SZ")


class StandardErrorHandler(logging.Handler):
    """A handler on whatever ``sys.stderr`` is when a record arrives.

    A test runner replaces standard error per command; the handler follows it.
    """

    def __init__(self) -> None:
        """Create the handler with the redaction filter and the format."""
        super().__init__()
        self.addFilter(RedactingFilter())
        self.addFilter(SecretFilter())
        self.setFormatter(RedactingFormatter(FORMAT))

    @override
    def emit(self, record: logging.LogRecord) -> None:
        stream: TextIO | None = sys.stderr
        if stream is None:
            return
        try:
            stream.write(f"{self.format(record)}\n")
        except RecursionError:
            raise
        except Exception:  # noqa: BLE001 - logging's contract: a handler reports, never raises
            self.handleError(record)


def _close_devnull_holders() -> None:
    for stream in _DEVNULL_HOLDERS:
        if not stream.closed:
            stream.close()
    _DEVNULL_HOLDERS.clear()


atexit.register(_close_devnull_holders)


def _devnull_stream() -> TextIO:
    if not _DEVNULL_HOLDERS or _DEVNULL_HOLDERS[0].closed:
        _DEVNULL_HOLDERS.clear()
        _DEVNULL_HOLDERS.append(
            io.open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115, UP020 - process lifetime sink
        )
    return _DEVNULL_HOLDERS[0]


def configure_logging(level: str, *, log_file: Path | None = None) -> None:
    """Configure logging for a command: redacting handlers at ``level``.

    Calling it again replaces the level and any previous rotating file handler. Under
    ``pythonw.exe`` (``sys.stderr`` is ``None``), only the file handler is installed and
    ``sys.stdout`` and ``sys.stderr`` are pointed at ``os.devnull``.

    Args:
        level: ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, or ``CRITICAL``.
        log_file: Optional path to the rotating log file (1 MiB, five backup files).
    """
    root = logging.getLogger()
    for existing in list(root.handlers):
        if isinstance(existing, RotatingFileHandler):
            root.removeHandler(existing)
            existing.close()

    headless = sys.stderr is None
    if headless:
        for existing in list(root.handlers):
            if isinstance(existing, StandardErrorHandler):
                root.removeHandler(existing)
        sink = _devnull_stream()
        sys.stderr = sink
        if sys.stdout is None:
            sys.stdout = sink
    else:
        handler = next((h for h in root.handlers if isinstance(h, StandardErrorHandler)), None)
        if handler is None:
            handler = StandardErrorHandler()
            root.addHandler(handler)
        handler.setLevel(level)

    if log_file is not None:
        ensure_directory(log_file.parent)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.addFilter(RedactingFilter())
        file_handler.addFilter(SecretFilter())
        file_handler.setFormatter(UtcFormatter(FILE_FORMAT))
        file_handler.setLevel(level)
        root.addHandler(file_handler)

    root.setLevel(level)
    _set_library_levels(level)


def _set_library_levels(level: str) -> None:
    quiet = logging.DEBUG if level == "DEBUG" else logging.WARNING
    levels = [(name, quiet) for name in QUIET_LIBRARIES]
    levels += [(name, logging.WARNING) for name in SILENT_LIBRARIES]
    for name, library_level in levels:
        lib_logger = logging.getLogger(name)
        lib_logger.setLevel(library_level)
        lib_logger.propagate = True


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
