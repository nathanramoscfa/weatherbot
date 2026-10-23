# src/weatherbot/models/ladder.py
"""The alert ladder: its five levels, its eleven rules in order, and the thresholds.

The levels' names and actions are the brief's §7 columns, and nothing in them is
season- or home-specific. ``RuleId`` lists the rules in the order the engine evaluates
them: the first rule that matches decides the level. ``Thresholds`` holds the six
values the rules compare against, each with its unit in its name, and is recorded in
every assessment with its fingerprint.
"""

import hashlib
import json
from collections.abc import Iterable, Mapping
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Final, Literal

from pydantic import Field

from weatherbot.models.base import DomainModel


class AlertLevel(IntEnum):
    """The five levels, from All Clear (1) to Hurricane Warning (5)."""

    ALL_CLEAR = 1
    TROPICAL_STORM_THREAT = 2
    WATCH_HURRICANE_THREAT = 3
    WARNING_WATCH_EVACUATION = 4
    HURRICANE_WARNING = 5

    @property
    def label(self) -> str:
        """The level's name, as the brief's ladder writes it."""
        return _LABELS[self]

    @property
    def actions(self) -> str:
        """The actions the brief's ladder shows at this level."""
        return _ACTIONS[self]


_LABELS: Final[Mapping[AlertLevel, str]] = MappingProxyType(
    {
        AlertLevel.ALL_CLEAR: "All Clear",
        AlertLevel.TROPICAL_STORM_THREAT: "Tropical Storm Threat",
        AlertLevel.WATCH_HURRICANE_THREAT: "Watch / Hurricane Threat",
        AlertLevel.WARNING_WATCH_EVACUATION: "Warning / Watch / Evacuation",
        AlertLevel.HURRICANE_WARNING: "Hurricane Warning",
    }
)
_ACTIONS: Final[Mapping[AlertLevel, str]] = MappingProxyType(
    {
        AlertLevel.ALL_CLEAR: "Normal activities",
        AlertLevel.TROPICAL_STORM_THREAT: "Monitor daily; review plans",
        AlertLevel.WATCH_HURRICANE_THREAT: "Stock supplies; pack; set an exit plan",
        AlertLevel.WARNING_WATCH_EVACUATION: (
            "Evacuate vulnerable areas; secure transport; assume routes close"
        ),
        AlertLevel.HURRICANE_WARNING: (
            "Shelter if not evacuated; expect outages; follow local orders"
        ),
    }
)


class RuleId(StrEnum):
    """The eleven rules, in the order the engine evaluates them.

    Within a level, official products precede the operator's toggle, and both precede
    geometry and probability. ``all_clear`` decides when no other rule matches.
    """

    HURRICANE_WARNING = "hurricane_warning"
    TROPICAL_STORM_WARNING = "tropical_storm_warning"
    HURRICANE_WATCH = "hurricane_watch"
    EVACUATION_ORDER = "evacuation_order"
    TROPICAL_STORM_WATCH = "tropical_storm_watch"
    HURRICANE_CONE = "hurricane_cone"
    HURRICANE_WIND_PROBABILITY = "hurricane_wind_probability"
    STORM_CONE = "storm_cone"
    DEVELOPMENT_REGION = "development_region"
    TROPICAL_STORM_WIND_PROBABILITY = "tropical_storm_wind_probability"
    ALL_CLEAR = "all_clear"


RULE_ORDER: Final[tuple[RuleId, ...]] = tuple(RuleId)
"""The rules in evaluation order."""

RULE_LEVELS: Final[Mapping[RuleId, AlertLevel]] = MappingProxyType(
    {
        RuleId.HURRICANE_WARNING: AlertLevel.HURRICANE_WARNING,
        RuleId.TROPICAL_STORM_WARNING: AlertLevel.WARNING_WATCH_EVACUATION,
        RuleId.HURRICANE_WATCH: AlertLevel.WARNING_WATCH_EVACUATION,
        RuleId.EVACUATION_ORDER: AlertLevel.WARNING_WATCH_EVACUATION,
        RuleId.TROPICAL_STORM_WATCH: AlertLevel.WATCH_HURRICANE_THREAT,
        RuleId.HURRICANE_CONE: AlertLevel.WATCH_HURRICANE_THREAT,
        RuleId.HURRICANE_WIND_PROBABILITY: AlertLevel.WATCH_HURRICANE_THREAT,
        RuleId.STORM_CONE: AlertLevel.TROPICAL_STORM_THREAT,
        RuleId.DEVELOPMENT_REGION: AlertLevel.TROPICAL_STORM_THREAT,
        RuleId.TROPICAL_STORM_WIND_PROBABILITY: AlertLevel.TROPICAL_STORM_THREAT,
        RuleId.ALL_CLEAR: AlertLevel.ALL_CLEAR,
    }
)
"""The level each rule sets."""

RULE_TRIGGERS: Final[Mapping[RuleId, str]] = MappingProxyType(
    {
        RuleId.HURRICANE_WARNING: "A Hurricane Warning covers the location.",
        RuleId.TROPICAL_STORM_WARNING: "A Tropical Storm Warning covers the location.",
        RuleId.HURRICANE_WATCH: "A Hurricane Watch covers the location.",
        RuleId.EVACUATION_ORDER: "The operator's evacuation-order toggle is on.",
        RuleId.TROPICAL_STORM_WATCH: "A Tropical Storm Watch covers the location.",
        RuleId.HURRICANE_CONE: (
            "The location is inside the cone of a storm that is a hurricane at or before its "
            "closest approach, and that approach comes within the cone horizon."
        ),
        RuleId.HURRICANE_WIND_PROBABILITY: (
            "The location's 64-kt wind-speed probability band starts at or above the hurricane "
            "wind floor."
        ),
        RuleId.STORM_CONE: "The location is inside the cone of any active storm.",
        RuleId.DEVELOPMENT_REGION: (
            "The location is inside a seven-day potential development region whose chance is at "
            "least the development chance floor."
        ),
        RuleId.TROPICAL_STORM_WIND_PROBABILITY: (
            "The location's 34-kt wind-speed probability band starts at or above the "
            "tropical-storm wind floor."
        ),
        RuleId.ALL_CLEAR: "No other rule matches.",
    }
)
"""Each rule's trigger, in the words of ``docs/ALERT-LADDER.md``."""

type BandFloor = Literal[0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90]
"""A floor: one of the lower bounds of NHC's wind-speed-probability bands, in percent."""

BAND_FLOORS: Final[tuple[int, ...]] = (0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90)
"""Every legal floor, in increasing order (a test keeps it equal to the bands)."""

COASTAL_REACH_MAX_KM: Final = 200.0
SEGMENT_END_TOLERANCE_MAX_KM: Final = 50.0
CONE_HORIZON_MIN_H: Final = 1
CONE_HORIZON_MAX_H: Final = 120


class Thresholds(DomainModel):
    """The six values the rules compare against, at the calibrated defaults.

    A wind floor is compared with a band's lower bound, the probability the band
    guarantees, so each floor is one of those bounds. The development chance floor is
    compared with an outlook region's seven-day chance.
    """

    coastal_reach_km: float = Field(
        default=25.0,
        ge=0.0,
        le=COASTAL_REACH_MAX_KM,
        description="How far a watch-warning segment reaches from its line.",
    )
    segment_end_tolerance_km: float = Field(
        default=5.0,
        ge=0.0,
        le=SEGMENT_END_TOLERANCE_MAX_KM,
        description="How far a segment reaches past its end.",
    )
    cone_horizon_h: int = Field(
        default=120,
        ge=CONE_HORIZON_MIN_H,
        le=CONE_HORIZON_MAX_H,
        description="How soon a hurricane's closest approach must come to be a threat.",
    )
    hurricane_wind_floor_pct: BandFloor = Field(
        default=10, description="The lowest 64-kt band lower bound that is a threat."
    )
    tropical_storm_wind_floor_pct: BandFloor = Field(
        default=5, description="The lowest 34-kt band lower bound that is a threat."
    )
    development_chance_floor_pct: BandFloor = Field(
        default=0, description="The lowest seven-day development chance that is a threat."
    )

    def fingerprint(self, rules: Iterable[RuleId] = RULE_ORDER) -> str:
        """Return the SHA-256 of the thresholds and the rule order, as canonical JSON.

        Args:
            rules: The rules in evaluation order; the ladder's own order by default.

        Returns:
            The hexadecimal digest, which changes with any threshold or any reordering.
        """
        document = {"rules": [str(rule) for rule in rules], "thresholds": self.model_dump()}
        canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Outcome intervals rounded to six decimals for portable readbacks.
CALIBRATION: Final[Mapping[str, Mapping[str, object]]] = MappingProxyType(
    {
        name: MappingProxyType(row)
        for name, row in {
            "coastal_reach_km": {
                "default": 25.0,
                "lower": 3.799558,
                "lower_open_reason": None,
                "upper": 112.159296,
                "upper_inclusive": False,
                "upper_open_reason": None,
            },
            "cone_horizon_h": {
                "default": 120,
                "lower": 117,
                "lower_open_reason": None,
                "upper": None,
                "upper_inclusive": True,
                "upper_open_reason": "legal maximum 120; the corpus cannot bind above it",
            },
            "development_chance_floor_pct": {
                "default": 0,
                "lower": None,
                "lower_open_reason": "legal minimum 0; the corpus cannot bind below it",
                "upper": 20,
                "upper_inclusive": True,
                "upper_open_reason": None,
            },
            "hurricane_wind_floor_pct": {
                "default": 10,
                "lower": 10,
                "lower_open_reason": None,
                "upper": 10,
                "upper_inclusive": True,
                "upper_open_reason": None,
            },
            "segment_end_tolerance_km": {
                "default": 5.0,
                "lower": None,
                "lower_open_reason": "legal minimum 0; the corpus cannot bind below it",
                "upper": 22.610062,
                "upper_inclusive": False,
                "upper_open_reason": None,
            },
            "tropical_storm_wind_floor_pct": {
                "default": 5,
                "lower": 5,
                "lower_open_reason": None,
                "upper": 5,
                "upper_inclusive": True,
                "upper_open_reason": None,
            },
        }.items()
    }
)

THRESHOLD_UNITS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "coastal_reach_km": "km",
        "cone_horizon_h": "h",
        "development_chance_floor_pct": "%",
        "hurricane_wind_floor_pct": "%",
        "segment_end_tolerance_km": "km",
        "tropical_storm_wind_floor_pct": "%",
    }
)

CALIBRATION_EVIDENCE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "coastal_reach_km": "25 km is inside the 7.6-29.1 km safety gap; covering lines pass "
        "within 3.8 km, non-covering alongside lines start at 58.2 km.",
        "segment_end_tolerance_km": "5 km is less than half the nearest short-ending segment "
        "distance (22.6 km); none of the covering landmark segments "
        "needs an end extension.",
        "cone_horizon_h": "120 h is the round forecast maximum; the five pairs with a watch "
        "first reach level 3 at least 54 h before it. A 116 h horizon changes "
        "a recorded hurricane-cone outcome.",
        "hurricane_wind_floor_pct": "10% separates adjacent recorded advisories; 5% promotes "
        "the weaker band, while 20% demotes the stronger. Every covering watch "
        "retains at least 54 h lead; named witnesses are in the calibration report.",
        "tropical_storm_wind_floor_pct": "5% distinguishes the lowest positive 34-kt band from "
        "the <5% band. Ordering/reversal exceptions are "
        "recorded, never smoothed.",
        "development_chance_floor_pct": "0% follows the brief: any seven-day region. The "
        "recorded Atlantic scenario is 20%; the archive has no "
        "outlook, so this is not corpus-calibrated.",
    }
)

INDISTINGUISHABLE_PAIRS: Final[Mapping[tuple[RuleId, RuleId], str]] = MappingProxyType(
    {
        (
            RuleId.HURRICANE_WARNING,
            RuleId.TROPICAL_STORM_WARNING,
        ): "No reference has both as its earliest matches; stronger rules can mask overlaps.",
        (
            RuleId.TROPICAL_STORM_WARNING,
            RuleId.HURRICANE_WATCH,
        ): "No reference has both as its earliest matches; stronger rules can mask overlaps.",
        (
            RuleId.HURRICANE_WATCH,
            RuleId.EVACUATION_ORDER,
        ): "No reference has both as its earliest matches; stronger rules can mask overlaps.",
        (
            RuleId.EVACUATION_ORDER,
            RuleId.TROPICAL_STORM_WATCH,
        ): "No reference has both as its earliest matches; stronger rules can mask overlaps.",
        (
            RuleId.TROPICAL_STORM_WATCH,
            RuleId.HURRICANE_CONE,
        ): "No reference has both as its earliest matches; stronger rules can mask overlaps.",
        (
            RuleId.STORM_CONE,
            RuleId.DEVELOPMENT_REGION,
        ): "No reference has both as its earliest matches; stronger rules can mask overlaps.",
        (
            RuleId.DEVELOPMENT_REGION,
            RuleId.TROPICAL_STORM_WIND_PROBABILITY,
        ): "No reference has both as its earliest matches; stronger rules can mask overlaps.",
        (
            RuleId.TROPICAL_STORM_WIND_PROBABILITY,
            RuleId.ALL_CLEAR,
        ): "all_clear is a fallback with no matching predicate; it never short-circuits a rule.",
    }
)
