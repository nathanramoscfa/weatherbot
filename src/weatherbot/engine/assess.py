# src/weatherbot/engine/assess.py
"""``assess``: the level one snapshot sets for one location, with its evidence.

The engine's clock is the snapshot's: a live snapshot's ``completed_at``, a replay
snapshot's advisory issuance (which is its ``completed_at``). Every input the rules lack
is named in the assessment, whose level then reads as a floor, and so is every input a
storm's threat lacks. The threats never change the level.
"""

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

from weatherbot.engine.breakpoints import breakpoint_span
from weatherbot.engine.cones import read_cones
from weatherbot.engine.geometry import place
from weatherbot.engine.official import alert_products, segment_products
from weatherbot.engine.outlook import read_regions
from weatherbot.engine.probabilities import read_probabilities
from weatherbot.engine.rules import RULES, Readings, Rule
from weatherbot.engine.threats import missing_inputs, storm_threats
from weatherbot.models import (
    RULE_LEVELS,
    Assessment,
    BreakpointSpan,
    Evidence,
    Location,
    RuleId,
    Snapshot,
    SourceId,
    SourceOutcome,
    Thresholds,
    UnavailableInput,
)

# The sources whose failure leaves the rules without an input, and what each carries.
RULE_SOURCES: Final[Mapping[SourceId, str]] = MappingProxyType(
    {
        "nhc-current-storms": "the active storms",
        "nhc-map-tropical-summary": (
            "the cones, forecast points, watches and warnings, wind-speed probabilities, "
            "and outlook"
        ),
        "nhc-map-tropical-weather": "the outlook and the wind-speed probabilities",
        "nhc-gis-archive": "the advisory's products",
    }
)
# The sources that carry the cones.
CONE_SOURCES: Final = frozenset({"nhc-map-tropical-summary", "nhc-gis-archive"})
ALERT_SOURCES: Final = ("nws-alerts-point", "nws-alerts-zone")


def _failed(snapshot: Snapshot) -> tuple[SourceOutcome, ...]:
    return tuple(outcome for outcome in snapshot.source_outcomes if outcome.status == "failed")


def _failed_sources(snapshot: Snapshot) -> list[UnavailableInput]:
    return [
        UnavailableInput(
            kind="source",
            source_id=outcome.source_id,
            reason=(
                f"{outcome.source_id} failed ({outcome.error_kind}), so "
                f"{RULE_SOURCES[outcome.source_id]} were not read"
            ),
        )
        for outcome in _failed(snapshot)
        if outcome.source_id in RULE_SOURCES
    ]


def _missing_alerts(snapshot: Snapshot, location: Location) -> list[UnavailableInput]:
    """NWS alerts for a location inside NWS coverage when the snapshot holds none for it."""
    if location.nws is None or location.name in snapshot.alerts:
        return []
    outcomes = {o.source_id: o for o in snapshot.source_outcomes if o.source_id in ALERT_SOURCES}
    failed = [o for o in outcomes.values() if o.status == "failed"]
    skipped = [o for o in outcomes.values() if o.status == "skipped"]
    if snapshot.origin == "replay":
        why = "a replay snapshot holds no NWS alerts"
    elif failed:
        why = "; ".join(f"{o.source_id} failed ({o.error_kind})" for o in failed)
    elif skipped:
        why = "; ".join(f"{o.source_id} was skipped ({o.reason})" for o in skipped)
    else:
        why = "the snapshot holds no alert list for this location"
    return [UnavailableInput(kind="nws_alerts", reason=f"NWS alerts were not checked: {why}")]


def _span(snapshot: Snapshot, location: Location) -> BreakpointSpan | None:
    """The span from the snapshot's catalogue, else the one stored with the location."""
    if snapshot.breakpoints:
        crs = snapshot.breakpoints[0].position.crs
        found = breakpoint_span(place(location.point, crs), snapshot.breakpoints)
        if found is not None:
            return found
    return location.breakpoint_span


def _decide(readings: Readings, rules: Sequence[Rule]) -> tuple[RuleId, tuple[Evidence, ...]]:
    """Evaluate the rules in order and stop at the first with a match."""
    for rule in rules:
        matches = rule.evaluate(readings)
        if matches:
            return rule.id, matches
    return RuleId.ALL_CLEAR, ()


def read(
    snapshot: Snapshot, location: Location, thresholds: Thresholds
) -> tuple[Readings, tuple[UnavailableInput, ...]]:
    """Read one snapshot's products at one location, as every rule reads them.

    Args:
        snapshot: The snapshot, live or replayed; its instant is the readings'.
        location: The location.
        thresholds: The coastal reach and end tolerance the segments are read with.

    Returns:
        The readings, and every input the rules and the threats lack: NWS alerts for a
        location inside NWS coverage when the snapshot holds no alert list for it, a
        failed roster or map source, a storm without a usable cone, a missing or
        uncovering probability product or an unusable band, the outlook of a replay
        snapshot, a storm without forecast points, and each arrival-time product a
        storm lacks.
    """
    as_of = snapshot.completed_at
    failed = {outcome.source_id for outcome in _failed(snapshot)}
    unavailable = [*_failed_sources(snapshot), *_missing_alerts(snapshot, location)]
    official = (
        *alert_products(snapshot.alerts.get(location.name, ()), location, as_of),
        *segment_products(snapshot.storms, location, thresholds, snapshot.breakpoints),
    )
    cones_failed = bool(failed & CONE_SOURCES)
    cones, missing_cones = read_cones(snapshot.storms, location, as_of, cones_failed=cones_failed)
    probabilities, missing_probabilities = read_probabilities(snapshot, location)
    regions, missing_regions = read_regions(snapshot, location)
    threats = storm_threats(snapshot.storms, location, as_of, cones)
    missing_threats = missing_inputs(snapshot, threats, points_failed=cones_failed)
    unavailable += [*missing_cones, *missing_probabilities, *missing_regions, *missing_threats]
    readings = Readings(
        as_of=as_of,
        location=location,
        thresholds=thresholds,
        official=official,
        cones=cones,
        probabilities=probabilities,
        regions=regions,
        threats=threats,
    )
    return readings, tuple(unavailable)


def assess(
    snapshot: Snapshot,
    location: Location,
    thresholds: Thresholds,
    *,
    rules: Sequence[Rule] = RULES,
) -> Assessment:
    """Assess one location against one snapshot.

    Each rule reads every source it names (``read``); the first rule with a match decides
    the level and the rule, its matches are the evidence, and ``all_clear`` decides when
    none does. The assessment lists every official product considered, the location's
    band of each wind-speed-probability product, its breakpoint span, one threat per
    storm, and every input the rules and the threats lacked.

    Args:
        snapshot: The snapshot, live or replayed; its instant is the assessment's.
        location: The location.
        thresholds: The thresholds the rules compare against.
        rules: The rules in evaluation order; the ladder's own by default.

    Returns:
        The assessment.
    """
    readings, unavailable = read(snapshot, location, thresholds)
    rule, evidence = _decide(readings, rules)
    return Assessment(
        location_name=location.name,
        snapshot_id=snapshot.snapshot_id,
        origin=snapshot.origin,
        as_of=readings.as_of,
        level=RULE_LEVELS[rule],
        rule=rule,
        evidence=evidence,
        official=readings.official,
        wind_probabilities=tuple(item.reading for item in readings.probabilities),
        breakpoint_span=_span(snapshot, location),
        threats=readings.threats,
        unavailable=unavailable,
        thresholds=thresholds,
        ruleset=thresholds.fingerprint(item.id for item in rules),
        complete=not unavailable,
    )
