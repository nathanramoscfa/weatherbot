# src/weatherbot/models/times.py
"""Instants, and the only functions that turn NOAA's time text into them.

Every instant in a model is an aware ``datetime`` in UTC: a naive value is rejected and an
aware one is converted to UTC. NOAA's local text (``HMM AM ZZZ Ddd Mon DD YYYY``) stays
beside the instant in a ``*_local_text`` field, and only the functions here parse it. Each
function either returns the one instant its text names or says why it cannot; none of them
guesses a time zone, a week, or a month.
"""

import re
from datetime import UTC, date, datetime, time, timedelta, timezone
from types import MappingProxyType
from typing import Annotated, Final

from pydantic import AfterValidator, AwareDatetime

from weatherbot.models.base import DomainModel


def to_utc(value: datetime) -> datetime:
    """Return an aware instant in UTC.

    Args:
        value: An aware ``datetime``.

    Returns:
        The same instant, with ``datetime.UTC`` as its zone.

    Raises:
        ValueError: ``value`` is naive.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        message = "a naive datetime is not an instant; give it a time zone"
        raise ValueError(message)
    return value.astimezone(UTC)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(to_utc)]
"""An aware instant, normalized to UTC. Pydantic rejects a naive value before ``to_utc``."""

# The abbreviations NHC prints in the three basins' products, as offsets from UTC. Any
# other abbreviation yields no instant: an unknown zone is never guessed.
NHC_ZONE_OFFSETS: Final = MappingProxyType(
    {
        "AST": timedelta(hours=-4),
        "EDT": timedelta(hours=-4),
        "EST": timedelta(hours=-5),
        "CDT": timedelta(hours=-5),
        "CST": timedelta(hours=-6),
        "MDT": timedelta(hours=-6),
        "MST": timedelta(hours=-7),
        "PDT": timedelta(hours=-7),
        "PST": timedelta(hours=-8),
        "HST": timedelta(hours=-10),
        "UTC": timedelta(0),
        "GMT": timedelta(0),
    }
)

# A track point's ``validtime`` names a day of the month and a UTC time; the one instant
# with that day and time inside this window around the advisory's issuance is the answer.
TRACK_WINDOW_BEFORE: Final = timedelta(days=1)
TRACK_WINDOW_AFTER: Final = timedelta(days=8)

# The arrival-time products cover the first 120 hours after their publication.
ARRIVAL_HORIZON: Final = timedelta(hours=120)

_HALF_DAY_HOURS: Final = 12
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_WEEKDAYS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_MONTHS: Final = (
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
)

_NHC_LOCAL_TIME = re.compile(
    r"(?P<hour>\d{1,2})(?P<minute>\d{2})\s+(?P<meridiem>AM|PM)\s+(?P<zone>[A-Za-z]{2,5})\s+"
    r"(?P<weekday>[A-Za-z]{3})\s+(?P<month>[A-Za-z]{3})\s+(?P<day>\d{1,2})\s+(?P<year>\d{4})"
)
_TRACK_VALID_TIME = re.compile(r"(?P<day>\d{2})/(?P<hour>\d{2})(?P<minute>\d{2})")
_SYNOPTIC_TIME = re.compile(r"(?P<stamp>\d{10})(?:_\S*)?")
_ARRIVAL_LABEL = re.compile(
    r"(?P<weekday>mon|tue|wed|thu|fri|sat|sun)\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*"
    r"(?P<meridiem>am|pm)",
    re.IGNORECASE,
)


def _clock(hour: int, minute: int, meridiem: str) -> time:
    """Return the 24-hour clock time of a 12-hour reading such as ``5:00 PM``."""
    if not 1 <= hour <= _HALF_DAY_HOURS or not 0 <= minute < 60:  # noqa: PLR2004 - minutes per hour
        message = f"{hour}:{minute:02d} {meridiem} is not a 12-hour clock time"
        raise ValueError(message)
    hour %= _HALF_DAY_HOURS
    if meridiem.lower() == "pm":
        hour += _HALF_DAY_HOURS
    return time(hour, minute)


def parse_nhc_local_time(text: str) -> datetime | None:
    """Parse NHC's local issuance text: ``HMM AM|PM ZZZ Ddd Mon DD YYYY``.

    Args:
        text: The text of an ``advdate``, an advisory header, or a ``pubAdvTime``.

    Returns:
        The instant in UTC, or ``None`` when the abbreviation is not in
        ``NHC_ZONE_OFFSETS``: an unknown zone yields no instant, never a guess.

    Raises:
        ValueError: The text is not in NHC's format, or its weekday disagrees with its date.
    """
    match = _NHC_LOCAL_TIME.fullmatch(text.strip())
    if match is None:
        message = f"not an NHC local time: {text!r}"
        raise ValueError(message)
    month = match["month"].lower()
    if month not in _MONTHS:
        message = f"unknown month in {text!r}"
        raise ValueError(message)
    day = date(int(match["year"]), _MONTHS.index(month) + 1, int(match["day"]))
    if _WEEKDAYS[day.weekday()] != match["weekday"].lower():
        message = f"the weekday in {text!r} disagrees with its date"
        raise ValueError(message)
    clock = _clock(int(match["hour"]), int(match["minute"]), match["meridiem"])
    offset = NHC_ZONE_OFFSETS.get(match["zone"])
    if offset is None:
        return None
    return datetime.combine(day, clock, tzinfo=timezone(offset)).astimezone(UTC)


def resolve_track_valid_time(text: str, anchor: datetime) -> datetime:
    """Resolve a forecast point's ``validtime`` (``DD/HHMM``, UTC) against its advisory.

    Args:
        text: The ``validtime`` text, such as ``12/2100``.
        anchor: The advisory's issuance, an aware instant.

    Returns:
        The one instant with that day of the month and that time in
        [``anchor`` - 1 day, ``anchor`` + 8 days].

    Raises:
        ValueError: The text is malformed, or no instant or more than one fits the window.
    """
    match = _TRACK_VALID_TIME.fullmatch(text.strip())
    if match is None:
        message = f"not a DD/HHMM valid time: {text!r}"
        raise ValueError(message)
    anchor = to_utc(anchor)
    clock = time(int(match["hour"]), int(match["minute"]))
    earliest, latest = anchor - TRACK_WINDOW_BEFORE, anchor + TRACK_WINDOW_AFTER
    candidates: list[datetime] = []
    day = earliest.date()
    while day <= latest.date():
        if day.day == int(match["day"]):
            instant = datetime.combine(day, clock, tzinfo=UTC)
            if earliest <= instant <= latest:
                candidates.append(instant)
        day += timedelta(days=1)
    if len(candidates) != 1:
        message = f"{text!r} matches {len(candidates)} instants near the advisory, not one"
        raise ValueError(message)
    return candidates[0]


def parse_synoptic_time(text: str) -> datetime:
    """Parse a ``YYYYMMDDHH`` synoptic time (UTC), alone or leading an ``idp_source``.

    Args:
        text: ``YYYYMMDDHH``, or a stamp led by one, as ``YYYYMMDDHH_wsp34knt120hr_5km``.

    Returns:
        The instant in UTC.

    Raises:
        ValueError: The text does not start with a valid ``YYYYMMDDHH`` stamp.
    """
    match = _SYNOPTIC_TIME.fullmatch(text.strip())
    if match is None:
        message = f"not a YYYYMMDDHH synoptic time: {text!r}"
        raise ValueError(message)
    try:
        return datetime.strptime(match["stamp"], "%Y%m%d%H").replace(tzinfo=UTC)
    except ValueError:
        message = f"not a valid YYYYMMDDHH synoptic time: {text!r}"
        raise ValueError(message) from None


def from_epoch_ms(value: int) -> datetime:
    """Convert ArcGIS epoch milliseconds (``idp_filedate``, ``idp_ingestdate``) exactly.

    Args:
        value: Milliseconds since 1970-01-01 UTC.

    Returns:
        The instant in UTC, with no floating-point rounding.

    Raises:
        TypeError: ``value`` is not an integer.
    """
    if isinstance(value, bool) or not isinstance(value, int):  # pyright: ignore[reportUnnecessaryIsInstance] - JSON input is untyped
        message = "epoch milliseconds must be an integer"
        raise TypeError(message)
    return _EPOCH + timedelta(milliseconds=value)


class ArrivalResolution(DomainModel):
    """What ``resolve_arrival_label`` found: an instant, or the reason there is none."""

    valid_at: UtcDatetime | None
    reason: str | None


def resolve_arrival_label(
    label: str, published_at: datetime, zone: str | None
) -> ArrivalResolution:
    """Resolve an arrival-time label such as ``Tue 8 am`` to an instant (issue #11).

    The label names a local weekday and clock time in the product's zone. The answer is
    the first instant at or after ``published_at`` whose local weekday and clock time
    match, provided it falls less than 120 hours after ``published_at``.

    Args:
        label: The label, ``Ddd H am|pm`` or ``Ddd H:MM am|pm`` in any case.
        published_at: The product's publication (``pubAdvTime``), an aware instant.
        zone: The product's ``timezone`` abbreviation.

    Returns:
        The instant, or ``None`` with the reason: a label that does not parse, an unknown
        zone, or an instant beyond the horizon.
    """
    match = _ARRIVAL_LABEL.fullmatch(label.strip())
    if match is None:
        return ArrivalResolution(valid_at=None, reason=f"label {label!r} does not parse")
    offset = NHC_ZONE_OFFSETS.get(zone.strip().upper()) if zone is not None else None
    if offset is None:
        return ArrivalResolution(valid_at=None, reason=f"unknown time zone {zone!r}")
    try:
        clock = _clock(int(match["hour"]), int(match["minute"] or 0), match["meridiem"])
    except ValueError:
        return ArrivalResolution(valid_at=None, reason=f"label {label!r} does not parse")
    published_at = to_utc(published_at)
    local_zone = timezone(offset)
    published_local = published_at.astimezone(local_zone)
    days_ahead = (_WEEKDAYS.index(match["weekday"].lower()) - published_local.weekday()) % 7
    day = published_local.date() + timedelta(days=days_ahead)
    candidate = datetime.combine(day, clock, tzinfo=local_zone)
    if candidate < published_local:
        candidate += timedelta(days=7)
    instant = candidate.astimezone(UTC)
    if instant - published_at >= ARRIVAL_HORIZON:
        return ArrivalResolution(
            valid_at=None, reason=f"label {label!r} lies beyond the 120-hour horizon"
        )
    return ArrivalResolution(valid_at=instant, reason=None)
