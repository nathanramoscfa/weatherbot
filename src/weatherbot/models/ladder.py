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

type BandFloor = Literal[0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90]
"""A floor: one of the lower bounds of NHC's wind-speed-probability bands, in percent."""

BAND_FLOORS: Final[tuple[int, ...]] = (0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90)
"""Every legal floor, in increasing order (a test keeps it equal to the bands)."""

COASTAL_REACH_MAX_KM: Final = 200.0
SEGMENT_END_TOLERANCE_MAX_KM: Final = 50.0
CONE_HORIZON_MIN_H: Final = 1
CONE_HORIZON_MAX_H: Final = 120


class Thresholds(DomainModel):
    """The six values the rules compare against, at the provisional defaults.

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
