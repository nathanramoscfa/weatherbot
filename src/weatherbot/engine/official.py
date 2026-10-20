# src/weatherbot/engine/official.py
"""Which official watches and warnings cover a location: NWS alerts and NHC segments.

NWS alerts follow issue #10's rule. An alert counts only with status ``Actual``, a message
type other than ``Cancel``, and an ``expires`` after the snapshot's instant. It covers the
location when the point query returned it, or when its UGC list (``affected_zone_ids``,
``geocode_ugc``) names the location's forecast zone or county zone. A county query's
alert whose list names neither is listed as context and never sets a level: a warning
for one end of a county does not raise all of it, and an alert in the county is never
hidden. The ladder reads four events, by exact NWS name; a covering alert of any other
event is listed and sets no level.

An NHC watch-warning segment covers the location when its nearest point is at most the
coastal reach away and inside the segment, or at most the end tolerance away at its end,
measured on the segment's own figure. A covering segment with an unknown ``tcww`` code is
listed and sets no level.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from types import MappingProxyType
from typing import Final

from weatherbot.engine.breakpoints import segment_ends
from weatherbot.engine.geodesy import figure_of
from weatherbot.engine.geometry import nearest_on_line, place
from weatherbot.models import (
    AlertQuery,
    Breakpoint,
    Citation,
    Location,
    NwsAlert,
    OfficialProduct,
    RuleId,
    StormProducts,
    Thresholds,
    WatchWarningCode,
    WatchWarningSegment,
)

LADDER_EVENTS: Final[Mapping[str, RuleId]] = MappingProxyType(
    {
        "Hurricane Warning": RuleId.HURRICANE_WARNING,
        "Tropical Storm Warning": RuleId.TROPICAL_STORM_WARNING,
        "Hurricane Watch": RuleId.HURRICANE_WATCH,
        "Tropical Storm Watch": RuleId.TROPICAL_STORM_WATCH,
    }
)
"""The NWS events the ladder reads, by exact event name, and the rule each triggers."""

LADDER_CODES: Final[Mapping[WatchWarningCode, RuleId]] = MappingProxyType(
    {
        WatchWarningCode.HURRICANE_WARNING: RuleId.HURRICANE_WARNING,
        WatchWarningCode.TROPICAL_STORM_WARNING: RuleId.TROPICAL_STORM_WARNING,
        WatchWarningCode.HURRICANE_WATCH: RuleId.HURRICANE_WATCH,
        WatchWarningCode.TROPICAL_STORM_WATCH: RuleId.TROPICAL_STORM_WATCH,
    }
)
"""The NHC ``tcww`` codes and the rule each triggers."""

CODE_NAMES: Final[Mapping[WatchWarningCode, str]] = MappingProxyType(
    {
        WatchWarningCode.HURRICANE_WARNING: "Hurricane Warning",
        WatchWarningCode.TROPICAL_STORM_WARNING: "Tropical Storm Warning",
        WatchWarningCode.HURRICANE_WATCH: "Hurricane Watch",
        WatchWarningCode.TROPICAL_STORM_WATCH: "Tropical Storm Watch",
    }
)

OUTSIDE_ZONES: Final = "county-zone alert outside this location's zones"
"""The reason a county query's alert that names neither of the location's zones is context."""

ACTUAL: Final = "Actual"
CANCEL: Final = "Cancel"
_NO_LEVEL: Final = "sets no level"


def _query_name(query: AlertQuery) -> str:
    return "point" if query.kind == "point" else f"zone {query.zone_id}"


def _cited(alert: NwsAlert) -> Citation:
    """Cite a zone query that returned the alert, else the point query (without its URL)."""
    query = next((q for q in alert.found_by if q.kind == "zone"), alert.found_by[0])
    return Citation.of(query.provenance)


def _alert_coverage(alert: NwsAlert, location: Location, as_of: datetime) -> tuple[bool, str]:
    if alert.status.raw != ACTUAL:
        return False, f"its status is {alert.status.raw}, not {ACTUAL}"
    if alert.message_type.raw == CANCEL:
        return False, "it is a Cancel message"
    if alert.expires <= as_of:
        return False, "it expired before the snapshot's instant"
    if any(query.kind == "point" for query in alert.found_by):
        return True, "the point query returned it"
    zones = (*alert.affected_zone_ids, *alert.geocode_ugc)
    coverage = location.nws
    own = (
        [z for z in (coverage.forecast_zone, coverage.county_zone) if z in zones]
        if coverage
        else []
    )
    if own:
        return True, f"its zone list names this location's zone {own[0]}"
    return False, OUTSIDE_ZONES


def alert_product(alert: NwsAlert, location: Location, as_of: datetime) -> OfficialProduct:
    """Apply issue #10's rule to one NWS alert.

    Args:
        alert: An alert the snapshot holds for the location.
        location: The location.
        as_of: The snapshot's instant.

    Returns:
        The alert as an official product: whether it covers the location, why, and the
        rule it triggers (``None`` when it covers nothing or its event is not a ladder
        event).
    """
    covers, reason = _alert_coverage(alert, location, as_of)
    rule = LADDER_EVENTS.get(alert.event) if covers else None
    if covers and rule is None:
        reason = f"{reason}; the ladder reads no {alert.event}, so it {_NO_LEVEL}"
    return OfficialProduct(
        kind="nws_alert",
        citation=_cited(alert),
        code=alert.event,
        alert_id=alert.id,
        issuer=alert.sender_name,
        issued_at=alert.sent,
        expires_at=alert.expires,
        found_by=tuple(_query_name(query) for query in alert.found_by),
        zones=tuple(dict.fromkeys((*alert.affected_zone_ids, *alert.geocode_ugc))),
        covers=covers,
        rule=rule,
        reason=reason,
    )


def alert_products(
    alerts: Sequence[NwsAlert], location: Location, as_of: datetime
) -> tuple[OfficialProduct, ...]:
    """Apply issue #10's rule to every NWS alert the snapshot holds for a location.

    Args:
        alerts: The location's alerts, as the snapshot holds them.
        location: The location.
        as_of: The snapshot's instant.

    Returns:
        Every alert, covering or not, in the snapshot's order.
    """
    return tuple(alert_product(alert, location, as_of) for alert in alerts)


def segment_product(
    storm: StormProducts,
    segment: WatchWarningSegment,
    location: Location,
    thresholds: Thresholds,
    breakpoints: Sequence[Breakpoint],
) -> OfficialProduct | None:
    """Apply the coverage rule to one NHC watch-warning segment.

    Args:
        storm: The segment's storm.
        segment: The segment.
        location: The location.
        thresholds: The coastal reach and the end tolerance.
        breakpoints: The snapshot's catalogue, which names a covering segment's ends.

    Returns:
        The covering segment as an official product, or ``None`` when it does not cover
        the location.
    """
    crs = segment.geometry.crs
    nearest = nearest_on_line(place(location.point, crs), segment.geometry, figure_of(crs))
    reach = thresholds.segment_end_tolerance_km if nearest.at_end else thresholds.coastal_reach_km
    if nearest.distance_km > reach:
        return None
    where = "at its end" if nearest.at_end else "inside the segment"
    reason = f"its nearest point is {nearest.distance_km:.1f} km away, {where}"
    code = segment.tcww.code
    rule = LADDER_CODES.get(code) if code is not None else None
    if rule is None:
        reason = f"{reason}; the code {segment.tcww.raw} is unknown, so it {_NO_LEVEL}"
    return OfficialProduct(
        kind="watch_warning_segment",
        citation=Citation.of(segment.provenance),
        code=segment.tcww.raw,
        atcf_id=storm.atcf_id,
        storm_name=storm.name,
        advisory=segment.advisory.number,
        issued_at=segment.advisory.issued_at,
        distance_km=nearest.distance_km,
        at_end=nearest.at_end,
        crs=crs.label,
        breakpoints=segment_ends(segment.geometry, breakpoints),
        covers=True,
        rule=rule,
        reason=reason,
    )


def segment_products(
    storms: Sequence[StormProducts],
    location: Location,
    thresholds: Thresholds,
    breakpoints: Sequence[Breakpoint],
) -> tuple[OfficialProduct, ...]:
    """Find every NHC watch-warning segment that covers a location.

    Args:
        storms: The snapshot's storms.
        location: The location.
        thresholds: The coastal reach and the end tolerance.
        breakpoints: The snapshot's catalogue.

    Returns:
        The covering segments, by storm and then in each storm's order.
    """
    return tuple(
        product
        for storm in storms
        for segment in storm.watch_warnings
        if (product := segment_product(storm, segment, location, thresholds, breakpoints))
    )
