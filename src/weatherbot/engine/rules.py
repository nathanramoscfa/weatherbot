# src/weatherbot/engine/rules.py
"""The eleven ladder rules, in the order the engine evaluates them.

Each rule reads every source it names from the readings of one snapshot at one location
and returns its matches as evidence; the first rule with a match decides the level. The
order is fixed: within a level, official products precede the operator's toggle, and
both precede geometry and probability.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from weatherbot.engine.cones import ConeReading
from weatherbot.engine.official import CODE_NAMES
from weatherbot.engine.outlook import RegionReading
from weatherbot.engine.probabilities import ProbabilityReading
from weatherbot.models import (
    RULE_LEVELS,
    AlertLevel,
    Citation,
    Evidence,
    Location,
    OfficialProduct,
    RuleId,
    StormThreat,
    Thresholds,
    WatchWarningCode,
)

_TIME: Final = "%Y-%m-%d %H:%M UTC"


@dataclass(frozen=True, slots=True)
class Readings:
    """What the rules read: one snapshot's products, tested at one location."""

    as_of: datetime
    location: Location
    thresholds: Thresholds
    official: tuple[OfficialProduct, ...]
    cones: tuple[ConeReading, ...]
    probabilities: tuple[ProbabilityReading, ...]
    regions: tuple[RegionReading, ...]
    threats: tuple[StormThreat, ...] = ()
    """One per storm; no rule reads them, so the level never depends on them."""


type Evaluate = Callable[[Readings], tuple[Evidence, ...]]


@dataclass(frozen=True, slots=True)
class Rule:
    """One rule: its id, its trigger in words, the products it reads, and its test."""

    id: RuleId
    trigger: str
    reads: tuple[str, ...]
    evaluate: Evaluate

    @property
    def level(self) -> AlertLevel:
        """The level the rule sets."""
        return RULE_LEVELS[self.id]


def _official_evidence(rule: RuleId, product: OfficialProduct) -> Evidence:
    if product.kind == "nws_alert":
        test = "point_query" if "point" in product.found_by else "zone_list"
        sent = f" at {product.issued_at:{_TIME}}" if product.issued_at else ""
        until = f", in effect until {product.expires_at:{_TIME}}" if product.expires_at else ""
        detail = f"{product.issuer} issued a {product.code}{sent}{until}; {product.reason}."
        return Evidence(
            rule=rule,
            product="nws_alert",
            citation=product.citation,
            code=product.code,
            issued_at=product.issued_at,
            test=test,
            detail=detail,
        )
    code = WatchWarningCode(product.code)
    ends = product.breakpoints
    span = f" from {ends[0]} to {ends[-1]}" if len(ends) > 1 else ""
    detail = (
        f"NHC {CODE_NAMES[code]} ({product.code}) segment{span} for {product.storm_name}, "
        f"advisory {product.advisory}: {product.reason}."
    )
    return Evidence(
        rule=rule,
        product="watch_warning_segment",
        citation=product.citation,
        code=product.code,
        atcf_id=product.atcf_id,
        storm_name=product.storm_name,
        advisory=product.advisory,
        issued_at=product.issued_at,
        test="segment_distance",
        distance_km=product.distance_km,
        at_end=product.at_end,
        crs=product.crs,
        breakpoints=product.breakpoints,
        detail=detail,
    )


def _official(rule: RuleId) -> Evaluate:
    """A rule matched by the covering NWS alerts and NHC segments that trigger it."""

    def evaluate(readings: Readings) -> tuple[Evidence, ...]:
        return tuple(
            _official_evidence(rule, product)
            for product in readings.official
            if product.covers and product.rule == rule
        )

    return evaluate


def _evacuation_order(readings: Readings) -> tuple[Evidence, ...]:
    location = readings.location
    if not location.evacuation_order_in_effect:
        return ()
    since = location.evacuation_order_set_at
    when = f" since {since:{_TIME}}" if since is not None else ""
    detail = f"The operator's evacuation-order toggle is on for this location{when}."
    return (
        Evidence(
            rule=RuleId.EVACUATION_ORDER,
            product="evacuation_toggle",
            issued_at=since,
            test="toggle",
            detail=detail,
        ),
    )


def _cone_evidence(rule: RuleId, reading: ConeReading, thresholds: Thresholds) -> Evidence:
    storm, cone, approach = reading.storm, reading.cone, reading.approach
    where = f"the cone of {storm.name} ({storm.atcf_id}), advisory {cone.advisory.number}"
    if approach is None or reading.lead_h is None:
        closest = "; the snapshot holds no forecast points for it"
    else:
        closest = (
            f"; the forecast track comes within {approach.distance_km:.0f} km at "
            f"{approach.instant:{_TIME}}, {reading.lead_h:.0f} h after the snapshot"
        )
        if reading.hurricane and reading.lead_h <= thresholds.cone_horizon_h:
            closest += ", and the storm is forecast to be a hurricane by then"
        elif reading.hurricane:
            closest += f", beyond the {thresholds.cone_horizon_h} h horizon"
        else:
            closest += ", and the storm is not forecast to be a hurricane by then"
    repaired = f" ({reading.note})" if reading.note else ""
    return Evidence(
        rule=rule,
        product="cone",
        citation=Citation.of(cone.provenance),
        atcf_id=storm.atcf_id,
        storm_name=storm.name,
        advisory=cone.advisory.number,
        issued_at=cone.advisory.issued_at,
        test="point_in_polygon",
        distance_km=approach.distance_km if approach else None,
        crs=cone.geometry.crs.label,
        closest_approach_at=approach.instant if approach else None,
        lead_h=reading.lead_h,
        detail=f"The location is inside {where}{repaired}{closest}.",
    )


def _hurricane_cone(readings: Readings) -> tuple[Evidence, ...]:
    horizon = readings.thresholds.cone_horizon_h
    return tuple(
        _cone_evidence(RuleId.HURRICANE_CONE, reading, readings.thresholds)
        for reading in readings.cones
        if reading.covers
        and reading.hurricane
        and reading.lead_h is not None
        and reading.lead_h <= horizon
    )


def _storm_cone(readings: Readings) -> tuple[Evidence, ...]:
    return tuple(
        _cone_evidence(RuleId.STORM_CONE, reading, readings.thresholds)
        for reading in readings.cones
        if reading.covers
    )


def _wind(rule: RuleId, threshold: int, floor: Callable[[Thresholds], int]) -> Evaluate:
    """A rule matched by the location's band of one threshold at or above a floor."""

    def evaluate(readings: Readings) -> tuple[Evidence, ...]:
        least = floor(readings.thresholds)
        matches: list[Evidence] = []
        for item in readings.probabilities:
            band, reading = item.band, item.reading
            if reading.threshold_kt != threshold or band is None or band.lower_pct < least:
                continue
            detail = (
                f"The {threshold}-kt wind-speed probabilities of "
                f"{reading.synoptic_at:{_TIME}} put the location in the {band.label} band, "
                f"at or above the {least}% floor."
            )
            matches.append(
                Evidence(
                    rule=rule,
                    product="wind_probability",
                    citation=reading.citation,
                    code=band.label,
                    issued_at=reading.synoptic_at,
                    test="band",
                    crs=reading.crs,
                    chance_pct=band.lower_pct,
                    threshold_kt=reading.threshold_kt,
                    detail=detail,
                )
            )
        return tuple(matches)

    return evaluate


def _development_region(readings: Readings) -> tuple[Evidence, ...]:
    least = readings.thresholds.development_chance_floor_pct
    matches: list[Evidence] = []
    for reading in readings.regions:
        chance = reading.chance_7day_pct
        # A region that states no chance meets only a floor of zero.
        meets = chance >= least if chance is not None else least == 0
        if not reading.covers or not meets:
            continue
        area = reading.area
        stated = f"a {chance}% chance" if chance is not None else "no stated chance"
        detail = (
            f"The location is inside the {area.basin} seven-day development region of the "
            f"outlook of {area.issued_at:{_TIME}}, with {stated} of formation in seven days."
        )
        matches.append(
            Evidence(
                rule=RuleId.DEVELOPMENT_REGION,
                product="development_region",
                citation=Citation.of(area.provenance),
                code=area.basin,
                issued_at=area.issued_at,
                test="point_in_polygon",
                crs=area.geometry.crs.label,
                chance_pct=chance,
                detail=detail,
            )
        )
    return tuple(matches)


def _all_clear(_: Readings) -> tuple[Evidence, ...]:
    return ()


_WARNINGS: Final = ("NWS alerts", "NHC watch-warning segments")
_CONES: Final = ("NHC cones", "NHC forecast points")

RULES: Final[tuple[Rule, ...]] = (
    Rule(
        RuleId.HURRICANE_WARNING,
        "A Hurricane Warning covers the location.",
        _WARNINGS,
        _official(RuleId.HURRICANE_WARNING),
    ),
    Rule(
        RuleId.TROPICAL_STORM_WARNING,
        "A Tropical Storm Warning covers the location.",
        _WARNINGS,
        _official(RuleId.TROPICAL_STORM_WARNING),
    ),
    Rule(
        RuleId.HURRICANE_WATCH,
        "A Hurricane Watch covers the location.",
        _WARNINGS,
        _official(RuleId.HURRICANE_WATCH),
    ),
    Rule(
        RuleId.EVACUATION_ORDER,
        "The operator's evacuation-order toggle is on.",
        ("the location's evacuation-order toggle",),
        _evacuation_order,
    ),
    Rule(
        RuleId.TROPICAL_STORM_WATCH,
        "A Tropical Storm Watch covers the location.",
        _WARNINGS,
        _official(RuleId.TROPICAL_STORM_WATCH),
    ),
    Rule(
        RuleId.HURRICANE_CONE,
        "The location is inside the cone of a storm that is a hurricane at or before its "
        "closest approach, and that approach comes within the cone horizon.",
        _CONES,
        _hurricane_cone,
    ),
    Rule(
        RuleId.HURRICANE_WIND_PROBABILITY,
        "The location's 64-kt wind-speed probability band starts at or above the "
        "hurricane wind floor.",
        ("NHC 64-kt wind-speed probabilities",),
        _wind(RuleId.HURRICANE_WIND_PROBABILITY, 64, lambda t: t.hurricane_wind_floor_pct),
    ),
    Rule(
        RuleId.STORM_CONE,
        "The location is inside the cone of any active storm.",
        _CONES,
        _storm_cone,
    ),
    Rule(
        RuleId.DEVELOPMENT_REGION,
        "The location is inside a seven-day potential development region whose chance is "
        "at least the development chance floor.",
        ("NHC tropical weather outlook development regions",),
        _development_region,
    ),
    Rule(
        RuleId.TROPICAL_STORM_WIND_PROBABILITY,
        "The location's 34-kt wind-speed probability band starts at or above the "
        "tropical-storm wind floor.",
        ("NHC 34-kt wind-speed probabilities",),
        _wind(
            RuleId.TROPICAL_STORM_WIND_PROBABILITY, 34, lambda t: t.tropical_storm_wind_floor_pct
        ),
    ),
    Rule(RuleId.ALL_CLEAR, "No other rule matches.", (), _all_clear),
)
"""The ladder's rules, in evaluation order: the first with a match decides."""
