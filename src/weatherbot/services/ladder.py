# src/weatherbot/services/ladder.py
"""The threat ladder's reference metadata, built from the engine's own definitions.

``ladder_reference(thresholds)`` returns a frozen ``LadderReference`` carrying the five
threat levels (1..5) from ``AlertLevel``, the eleven rules in evaluation order from
``RULES``, the NWS alert event names and NHC coastal watch-warning codes the ladder reads
from ``weatherbot.engine.official``, and the running thresholds with their units and
descriptions. ``GET /api/ladder`` serves this reference so the web UI never maintains a
separate copy of the engine's vocabulary.
"""

from typing import cast

from weatherbot.engine import RULES
from weatherbot.engine.official import CODE_NAMES, LADDER_CODES, LADDER_EVENTS
from weatherbot.models import (
    RULE_LEVELS,
    AlertLevel,
    DomainModel,
    RuleId,
    Thresholds,
    WatchWarningCode,
)
from weatherbot.models.ladder import THRESHOLD_UNITS


class LadderLevel(DomainModel):
    """One of the five threat levels in ``AlertLevel`` order."""

    number: int
    label: str
    actions: str


class LadderRule(DomainModel):
    """One of the eleven rules in ``RULES`` evaluation order."""

    order: int
    id: RuleId
    level: int
    sentence: str
    sources: tuple[str, ...]


class LadderEvent(DomainModel):
    """An NWS alert event name read by the ladder and the rule and level it triggers."""

    event: str
    rule: RuleId
    level: int


class LadderCode(DomainModel):
    """An NHC coastal watch-warning code read by the ladder and the rule and level it triggers."""

    code: WatchWarningCode
    name: str
    rule: RuleId
    level: int


class LadderThreshold(DomainModel):
    """One running engine threshold with its value, unit, and description."""

    name: str
    value: float | int
    unit: str
    description: str


class LadderReference(DomainModel):
    """The complete threat-ladder reference metadata for the running thresholds."""

    levels: tuple[LadderLevel, ...]
    rules: tuple[LadderRule, ...]
    events: tuple[LadderEvent, ...]
    codes: tuple[LadderCode, ...]
    thresholds: tuple[LadderThreshold, ...]
    ruleset: str


_DEFAULT_THRESHOLDS = Thresholds()


def ladder_reference(thresholds: Thresholds = _DEFAULT_THRESHOLDS) -> LadderReference:
    """Build the threat-ladder reference metadata for ``thresholds``.

    Args:
        thresholds: The thresholds the engine is running; defaults to ``Thresholds()``.

    Returns:
        The frozen reference of levels, rules, official events and codes, and thresholds.
    """
    levels = tuple(
        LadderLevel(
            number=int(level),
            label=level.label,
            actions=level.actions,
        )
        for level in AlertLevel
    )
    rules = tuple(
        LadderRule(
            order=index,
            id=rule.id,
            level=int(rule.level),
            sentence=rule.trigger,
            sources=rule.reads,
        )
        for index, rule in enumerate(RULES, start=1)
    )
    events = tuple(
        LadderEvent(
            event=event_name,
            rule=rule_id,
            level=int(RULE_LEVELS[rule_id]),
        )
        for event_name, rule_id in LADDER_EVENTS.items()
    )
    codes = tuple(
        LadderCode(
            code=code,
            name=CODE_NAMES[code],
            rule=rule_id,
            level=int(RULE_LEVELS[rule_id]),
        )
        for code, rule_id in LADDER_CODES.items()
    )
    threshold_items = tuple(
        LadderThreshold(
            name=name,
            value=cast("float | int", getattr(thresholds, name)),
            unit=THRESHOLD_UNITS[name],
            description=field_info.description or "",
        )
        for name, field_info in Thresholds.model_fields.items()
    )
    return LadderReference(
        levels=levels,
        rules=rules,
        events=events,
        codes=codes,
        thresholds=threshold_items,
        ruleset=thresholds.fingerprint(),
    )
