# src/weatherbot/engine/changes.py
"""``diff``: the typed change events between two assessments of one location.

Phase 4's notification policy reads these: a level change in either direction, a new
advisory for a storm (with whether its cone covers the location), a new, replaced, or
withdrawn official product that covers the location, and a cone entered or left. Only
covering products make official events. An NWS alert is identified by its id; a new
alert whose ``references`` names a covering predecessor replaces it. An NHC storm's
covering watch-warning segments are identified by storm and code, because a segment is
reissued with every advisory: a code that appears is added, one that goes is removed,
and codes that go while others come in the same storm (a Hurricane Watch upgraded to a
Hurricane Warning) are one change.

``diff`` is pure and deterministic, and emits its events in a fixed order: the level, the
advisories, the official products, then the cones. With no previous assessment it
returns the initial events.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from typing import Final

from weatherbot.engine.official import CODE_NAMES
from weatherbot.models import (
    AdvisoryNumber,
    Assessment,
    ChangeEvent,
    OfficialProduct,
    StormThreat,
    WatchWarningCode,
)

# The sources whose failure leaves an assessment without its storms: a storm missing then
# has not gone, so it leaves no cone.
STORM_SOURCES: Final = frozenset({"nhc-current-storms", "nhc-gis-archive"})
# NHC's codes from the strongest down; any other code sorts after them, by name.
_CODE_ORDER: Final = ("HWR", "TWR", "HWA", "TWA")


def _code_key(code: str) -> tuple[int, str]:
    return (_CODE_ORDER.index(code) if code in _CODE_ORDER else len(_CODE_ORDER), code)


def _named(code: str) -> str:
    try:
        return f"{CODE_NAMES[WatchWarningCode(code)]} ({code})"
    except (KeyError, ValueError):
        return f"code {code}"


def _codes(codes: Sequence[str]) -> str:
    return " and ".join(_named(code) for code in codes)


def _level(previous: Assessment | None, current: Assessment) -> Iterator[ChangeEvent]:
    level = current.level
    before = previous.level if previous is not None else None
    if before == level:
        return
    now = f"level {int(level)} ({level.label}), by the rule {current.rule}"
    if before is None:
        direction, detail = "initial", f"The first assessment is at {now}."
    else:
        direction = "up" if level > before else "down"
        verb = "rose" if direction == "up" else "fell"
        detail = f"The level {verb} from {int(before)} ({before.label}) to {now}."
    yield ChangeEvent(
        kind="level_changed",
        previous_level=before,
        level=level,
        direction=direction,
        rule=current.rule,
        detail=detail,
    )


def _advisories(before: dict[str, StormThreat], current: Assessment) -> Iterator[ChangeEvent]:
    for threat in current.threats:
        was = before.get(threat.atcf_id)
        previous = was.advisory if was is not None else None
        if threat.advisory is None or threat.advisory == previous:
            continue
        cone = ""
        if threat.in_cone is not None:
            cone = ", whose cone covers the location" if threat.in_cone else ", whose cone does not"
        detail = f"NHC issued advisory {threat.advisory} for {threat.storm_name}{cone}."
        yield ChangeEvent(
            kind="advisory_issued",
            atcf_id=threat.atcf_id,
            storm_name=threat.storm_name,
            previous_advisory=previous,
            advisory=threat.advisory,
            in_cone=threat.in_cone,
            detail=detail,
        )


def _alert_event(kind: str, product: OfficialProduct, verb: str) -> ChangeEvent:
    issuer = product.issuer or "The NWS"
    return ChangeEvent.model_validate(
        {
            "kind": kind,
            "product": "nws_alert",
            "alert_id": product.alert_id,
            "codes": (product.code,),
            "detail": f"{issuer} {verb} a {product.code} that covers the location.",
        }
    )


def _alerts(previous: Assessment | None, current: Assessment) -> Iterator[ChangeEvent]:
    def covering(assessment: Assessment) -> list[OfficialProduct]:
        return [p for p in assessment.official if p.kind == "nws_alert" and p.covers]

    before = {p.alert_id: p for p in covering(previous)} if previous is not None else {}
    now = covering(current)
    replaced: set[str | None] = set()
    for product in now:
        if product.alert_id in before:
            continue
        predecessor = next((before[ref] for ref in product.references if ref in before), None)
        if predecessor is None:
            yield _alert_event("official_added", product, "issued")
            continue
        replaced.add(predecessor.alert_id)
        yield ChangeEvent(
            kind="official_changed",
            product="nws_alert",
            previous_alert_id=predecessor.alert_id,
            alert_id=product.alert_id,
            previous_codes=(predecessor.code,),
            codes=(product.code,),
            detail=(
                f"{product.issuer or 'The NWS'} replaced a {predecessor.code} that covers the "
                f"location with a {product.code}."
            ),
        )
    current_ids = {product.alert_id for product in now}
    for product in before.values():
        if product.alert_id not in current_ids | replaced:
            yield _alert_event("official_removed", product, "no longer has")


@dataclass(frozen=True, slots=True)
class _Storm:
    """One storm's covering segments: its id and name, an advisory, and their codes."""

    atcf_id: str
    name: str
    advisory: AdvisoryNumber | None
    codes: frozenset[str]


def _segments_of(assessment: Assessment | None) -> dict[str, _Storm]:
    """Each storm's covering segment codes, with its name and the segments' advisory."""
    found: dict[str, _Storm] = {}
    for product in assessment.official if assessment is not None else ():
        if product.kind != "watch_warning_segment" or not product.covers or not product.atcf_id:
            continue
        held = found.get(product.atcf_id)
        found[product.atcf_id] = _Storm(
            atcf_id=product.atcf_id,
            name=product.storm_name or product.atcf_id,
            advisory=held.advisory if held else product.advisory,
            codes=frozenset({product.code}) | (held.codes if held else frozenset[str]()),
        )
    return found


def _segment_event(
    kind: str, storm: _Storm, codes: Sequence[str], previous: Sequence[str] = ()
) -> ChangeEvent:
    at = f", advisory {storm.advisory}" if storm.advisory is not None else ""
    if kind == "official_changed":
        detail = f"NHC replaced the {_codes(previous)} with the {_codes(codes)}"
    elif kind == "official_added":
        detail = f"NHC issued the {_codes(codes)}"
    else:
        detail = f"NHC no longer has the {_codes(codes)}"
    return ChangeEvent.model_validate(
        {
            "kind": kind,
            "product": "watch_warning_segment",
            "atcf_id": storm.atcf_id,
            "storm_name": storm.name,
            "advisory": storm.advisory,
            "previous_codes": tuple(previous),
            "codes": tuple(codes),
            "detail": f"{detail} that covers the location for {storm.name}{at}.",
        }
    )


def _segments(
    previous: Assessment | None, current: Assessment, now_threats: dict[str, StormThreat]
) -> Iterator[ChangeEvent]:
    before, now = _segments_of(previous), _segments_of(current)
    for atcf_id in [*now, *(storm for storm in before if storm not in now)]:
        storm = now.get(atcf_id) or before[atcf_id]
        if atcf_id not in now and atcf_id in now_threats:
            # Removed at the storm's current advisory, which has no covering segment.
            storm = replace(storm, advisory=now_threats[atcf_id].advisory)
        old = before[atcf_id].codes if atcf_id in before else frozenset[str]()
        new = now[atcf_id].codes if atcf_id in now else frozenset[str]()
        added = sorted(new - old, key=_code_key)
        removed = sorted(old - new, key=_code_key)
        if added and removed:
            yield _segment_event("official_changed", storm, added, removed)
            continue
        for code in added:
            yield _segment_event("official_added", storm, (code,))
        for code in removed:
            yield _segment_event("official_removed", storm, (code,))


def _cone_event(kind: str, threat: StormThreat, detail: str) -> ChangeEvent:
    return ChangeEvent.model_validate(
        {
            "kind": kind,
            "atcf_id": threat.atcf_id,
            "storm_name": threat.storm_name,
            "advisory": threat.advisory,
            "detail": detail,
        }
    )


def _cones(
    before: dict[str, StormThreat], current: Assessment, now: dict[str, StormThreat]
) -> Iterator[ChangeEvent]:
    for threat in current.threats:
        was = before.get(threat.atcf_id)
        was_in = was.in_cone if was is not None else None
        at = f", advisory {threat.advisory}" if threat.advisory is not None else ""
        if threat.in_cone is True and was_in is not True:
            detail = f"The location entered the cone of {threat.storm_name}{at}."
            yield _cone_event("cone_entered", threat, detail)
        elif threat.in_cone is False and was_in is True:
            detail = f"The location left the cone of {threat.storm_name}{at}."
            yield _cone_event("cone_left", threat, detail)
    known = not any(
        item.kind == "source" and item.source_id in STORM_SOURCES for item in current.unavailable
    )
    for atcf_id, threat in before.items():
        if atcf_id not in now and threat.in_cone is True and known:
            name = threat.storm_name
            detail = f"{name} is no longer listed, so its cone no longer covers the location."
            yield _cone_event("cone_left", threat, detail)


def diff(previous: Assessment | None, current: Assessment) -> tuple[ChangeEvent, ...]:
    """Return the change events from one assessment of a location to the next.

    Args:
        previous: The location's previous assessment, or ``None`` for its first.
        current: Its current assessment.

    Returns:
        The events in a fixed order: the level, the advisories, the official products,
        the cones. With no previous assessment, the initial events: the level, each
        storm's advisory, each covering official product, and each covering cone.

    Raises:
        ValueError: The assessments are of two locations, or ``current`` is older than
            ``previous``.
    """
    if previous is not None and previous.location_name != current.location_name:
        message = "diff compares two assessments of one location"
        raise ValueError(message)
    if previous is not None and current.as_of < previous.as_of:
        message = "diff's current assessment is older than its previous one"
        raise ValueError(message)
    before = {threat.atcf_id: threat for threat in previous.threats} if previous else {}
    now = {threat.atcf_id: threat for threat in current.threats}
    return (
        *_level(previous, current),
        *_advisories(before, current),
        *_alerts(previous, current),
        *_segments(previous, current, now),
        *_cones(before, current, now),
    )
