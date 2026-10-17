# src/weatherbot/services/disclaimer.py
"""The disclaimer: its full text in the package, its essentials, and when it was shown.

``DISCLAIMER.md`` ships inside the package as ``weatherbot/DISCLAIMER.md``, byte for byte
the repository's copy (a test compares them). The command line prints ``ESSENTIALS``
the first time any command opens the database and records that time in the
``settings`` table; every read command ends with ``NOTICE``, and every ``--json``
document carries it.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from importlib.resources import files
from typing import Final

from weatherbot.services.persistence.repositories import SettingsRepository

SHOWN_AT_KEY: Final = "disclaimer_shown_at"
PACKAGED_FILE: Final = "DISCLAIMER.md"
DISCLAIMER_URL: Final = "https://github.com/nathanramoscfa/weatherbot/blob/main/DISCLAIMER.md"

NOTICE: Final = "Informational only; never a substitute for official guidance. See DISCLAIMER.md."
"""The one line every read command ends with and every ``--json`` document carries."""

ESSENTIALS: Final = (
    (
        "Weatherbot is informational only. It is not an official source, is not affiliated "
        "with or endorsed by NOAA, the NHC, or the NWS, and must never be the sole source "
        "for a life-safety decision."
    ),
    (
        "Verify everything with the National Hurricane Center (nhc.noaa.gov), the National "
        "Weather Service (weather.gov), and your local emergency management, and follow "
        "every official evacuation order regardless of what Weatherbot shows."
    ),
    (
        'The software is provided "as is", without warranty, and its authors accept no '
        "liability for decisions made from it."
    ),
    f"Read the full text in DISCLAIMER.md: {DISCLAIMER_URL}",
)
"""What the first run prints, one paragraph per item."""


def full_text() -> str:
    """Return the full disclaimer as the package ships it.

    Returns:
        The text of ``weatherbot/DISCLAIMER.md``.
    """
    return files("weatherbot").joinpath(PACKAGED_FILE).read_text(encoding="utf-8")


def record_first_showing(
    settings: SettingsRepository, now: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> bool:
    """Record the first showing of the disclaimer, unless it was recorded before.

    Args:
        settings: The database's settings.
        now: The clock.

    Returns:
        Whether this is the first showing: the caller prints ``ESSENTIALS`` then.
    """
    if settings.get(SHOWN_AT_KEY) is not None:
        return False
    settings.set(SHOWN_AT_KEY, now().astimezone(UTC).isoformat())
    return True
