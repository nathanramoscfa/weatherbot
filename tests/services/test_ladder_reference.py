# tests/services/test_ladder_reference.py
"""Tests for ``weatherbot.services.ladder``."""

import json
import re

import pytest
from pydantic import ValidationError

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.engine import RULES
from weatherbot.engine.official import CODE_NAMES, LADDER_CODES, LADDER_EVENTS
from weatherbot.models import RULE_LEVELS, AlertLevel, Thresholds
from weatherbot.models.ladder import THRESHOLD_UNITS
from weatherbot.services.config import EngineSettings, Settings
from weatherbot.services.ladder import ladder_reference

DECIMAL_COORDINATE = re.compile(r"(?<![\d.])\d{1,3}\.\d{3,}(?![\d.])")


def test_ladder_reference_matches_engine_levels_rules_events_codes_and_thresholds() -> None:
    settings = Settings(
        engine=EngineSettings(
            coastal_reach_km=30.0,
            segment_end_tolerance_km=7.5,
            cone_horizon_h=96,
            hurricane_wind_floor_pct=20,
            tropical_storm_wind_floor_pct=10,
            development_chance_floor_pct=20,
        )
    )
    thresholds = settings.engine.thresholds()
    ref = ladder_reference(thresholds)

    # Levels equal AlertLevel in order with labels and actions.
    assert [lvl.number for lvl in ref.levels] == [int(level) for level in AlertLevel]
    assert [lvl.label for lvl in ref.levels] == [level.label for level in AlertLevel]
    assert [lvl.actions for lvl in ref.levels] == [level.actions for level in AlertLevel]

    # Rules equal RULES in evaluation order with ids, levels, sentences, and sources.
    assert [rule.order for rule in ref.rules] == list(range(1, len(RULES) + 1))
    assert [rule.id for rule in ref.rules] == [rule.id for rule in RULES]
    assert [rule.level for rule in ref.rules] == [int(rule.level) for rule in RULES]
    assert [rule.sentence for rule in ref.rules] == [rule.trigger for rule in RULES]
    assert [rule.sources for rule in ref.rules] == [rule.reads for rule in RULES]

    # Events and codes equal LADDER_EVENTS and LADDER_CODES.
    assert [(ev.event, ev.rule, ev.level) for ev in ref.events] == [
        (name, rule_id, int(RULE_LEVELS[rule_id])) for name, rule_id in LADDER_EVENTS.items()
    ]
    assert [(item.code, item.name, item.rule, item.level) for item in ref.codes] == [
        (code, CODE_NAMES[code], rule_id, int(RULE_LEVELS[rule_id]))
        for code, rule_id in LADDER_CODES.items()
    ]

    # Thresholds equal the configured settings' thresholds with units and descriptions.
    assert [(th.name, th.value, th.unit) for th in ref.thresholds] == [
        (name, getattr(thresholds, name), THRESHOLD_UNITS[name]) for name in Thresholds.model_fields
    ]
    assert all(th.description for th in ref.thresholds)
    assert ref.ruleset == thresholds.fingerprint()


def test_ladder_reference_is_frozen_and_contains_no_coordinate() -> None:
    ref = ladder_reference()
    with pytest.raises(ValidationError):
        ref.ruleset = "mutated"  # type: ignore[misc]

    serialized = json.dumps(ref.model_dump(mode="json"))
    lat, lon = synthetic_coordinates(load_landmarks(), (), seed=8)
    assert lat not in serialized
    assert lon not in serialized
    assert not DECIMAL_COORDINATE.search(serialized)
