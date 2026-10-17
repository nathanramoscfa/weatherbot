# src/weatherbot/sources/drift.py
"""Source-drift warnings: an official product disagrees with another, or with the register.

A drift warning never fails a fetch. It is logged at WARNING on ``weatherbot.sources``
with ``extra={"source_drift": <source id>}``, so the snapshot service (Step 6) can collect
the warnings of a run and ``doctor`` can report them. The message names products and
fields, never a coordinate.
"""

from typing import Final

from weatherbot.models import SourceId
from weatherbot.sources.http import LOGGER

DRIFT_ATTRIBUTE: Final = "source_drift"
"""The ``LogRecord`` attribute that marks a drift warning and names its source."""


def warn_drift(source_id: SourceId, message: str) -> None:
    """Log a Source-drift warning.

    Args:
        source_id: The register id of the source that drifted.
        message: What disagrees, free of coordinates.
    """
    LOGGER.warning("Source drift: %s: %s", source_id, message, extra={DRIFT_ATTRIBUTE: source_id})
