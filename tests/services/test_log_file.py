# tests/services/test_log_file.py
"""The rotating log file: 1 MiB rotation, UTC timestamps, coordinate redaction, and pythonw."""

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from weatherbot.services.logs import (
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    StandardErrorHandler,
    configure_logging,
)


def _close_rotating_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler):
            root.removeHandler(handler)
            handler.close()


def test_log_file_formats_utc_timestamps_and_redacts_coordinates_above_debug(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "logs" / "weatherbot.log"
    try:
        configure_logging("INFO", log_file=log_path)
        logger = logging.getLogger("weatherbot.test.logfile")
        logger.info("GET https://api.weather.gov/alerts/active?point=25.7757,-80.1966")
        logger.debug("GET https://api.weather.gov/alerts/active?point=25.7757,-80.1966")
    finally:
        _close_rotating_handlers()
        configure_logging("INFO")

    text = log_path.read_text(encoding="utf-8")
    assert re.search(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z INFO weatherbot\.test\.logfile: ",
        text,
        re.MULTILINE,
    )
    assert "point=<redacted>" in text
    assert "25.7757" not in text
    assert "-80.1966" not in text


def test_log_file_rotates_at_one_mib_with_five_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = tmp_path / "logs" / "weatherbot.log"
    try:
        configure_logging("INFO", log_file=log_path)
        root = logging.getLogger()
        rotating = next(h for h in root.handlers if isinstance(h, RotatingFileHandler))
        assert rotating.maxBytes == LOG_MAX_BYTES
        assert rotating.backupCount == LOG_BACKUP_COUNT

        monkeypatch.setattr(rotating, "maxBytes", 256)
        logger = logging.getLogger("weatherbot.test.rotation")
        for index in range(30):
            logger.info("rotation line %02d %s", index, "x" * 40)
    finally:
        _close_rotating_handlers()
        configure_logging("INFO")

    backups = sorted(p.name for p in log_path.parent.glob("weatherbot.log.*"))
    assert backups == [f"weatherbot.log.{i}" for i in range(1, LOG_BACKUP_COUNT + 1)]


def test_configure_logging_with_none_stderr_installs_only_file_handler_and_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = tmp_path / "logs" / "weatherbot.log"
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "stdout", None)
    try:
        configure_logging("INFO", log_file=log_path)
        root = logging.getLogger()
        assert not any(isinstance(h, StandardErrorHandler) for h in root.handlers)
        assert any(isinstance(h, RotatingFileHandler) for h in root.handlers)
        assert sys.stderr is not None
        assert sys.stdout is not None
        sys.stdout.write("pythonw stdout write raises nothing\n")
        logging.getLogger("weatherbot.test.pythonw").info("logged from pythonw")
    finally:
        if sys.stderr is not None and not sys.stderr.closed:
            sys.stderr.close()
        _close_rotating_handlers()

    assert "logged from pythonw" in log_path.read_text(encoding="utf-8")
