# src/weatherbot/logging_setup.py
"""Logging configuration for Weatherbot."""

import logging
import logging.handlers
from pathlib import Path


def setup_logging(
    log_level: str = "INFO",
    log_file: Path | None = None,
    console: bool = True,
) -> None:
    """Configure logging with rotating file handler and console output.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (default: logs/weatherbot.log)
        console: Whether to log to console
    """
    if log_file is None:
        log_file = Path("logs") / "weatherbot.log"

    # Ensure log directory exists
    log_file.parent.mkdir(exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Add rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Add console handler if requested
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Set specific logger levels
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
