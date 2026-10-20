# tests/engine/test_golden_mutations.py
"""Every rule and finite threshold bound must change a frozen or named reference outcome."""

import json
from typing import cast

import pytest
from scenarios import SCENARIOS

from calibrate_ladder import changed, indistinguishable, outcomes, prepared, report
from ladder_data import GOLDENS
from weatherbot.engine import RULES, assess
from weatherbot.models import BAND_FLOORS, RuleId, Thresholds
from weatherbot.models.ladder import (
    CALIBRATION,
    CALIBRATION_EVIDENCE,
    INDISTINGUISHABLE_PAIRS,
    THRESHOLD_UNITS,
)


def references() -> tuple[RuleId, ...]:
    """The stored golden rules and the scenarios' declared expectations, never fresh outcomes."""
    by_case: dict[str, RuleId] = {}
    for path in GOLDENS.glob("*.json"):
        document = json.loads(path.read_bytes())
        for row in document["timeline"]:
            by_case[f"{path.stem}/{row['advisory']}"] = RuleId(row["rule"])
    by_case.update({scenario.name: scenario.rule for scenario in SCENARIOS})
    return tuple(by_case[item.case.name] for item in prepared())


@pytest.mark.parametrize("rule_id", tuple(rule.id for rule in RULES if rule.id != RuleId.ALL_CLEAR))
def test_removing_each_non_fallback_rule_changes_a_reference(rule_id: RuleId) -> None:
    remaining = tuple(rule for rule in RULES if rule.id != rule_id)
    assert outcomes(Thresholds(), remaining) != references(), rule_id


def test_the_indistinguishable_adjacent_swaps_are_exactly_the_recorded_pairs() -> None:
    baseline = references()
    unchanged: set[tuple[RuleId, RuleId]] = set()
    for index in range(len(RULES) - 1):
        swapped = list(RULES)
        swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
        pair = (RULES[index].id, RULES[index + 1].id)
        if outcomes(Thresholds(), swapped) == baseline:
            unchanged.add(pair)
    assert unchanged == set(INDISTINGUISHABLE_PAIRS)
    assert all(INDISTINGUISHABLE_PAIRS.values())
    assert {tuple(pair) for pair in indistinguishable()} == {
        tuple(str(rule) for rule in pair) for pair in unchanged
    }


@pytest.mark.parametrize("name", tuple(Thresholds.model_fields))
def test_crossing_each_finite_interval_end_changes_a_reference(name: str) -> None:
    row = CALIBRATION[name]
    baseline = references()
    for side in ("lower", "upper"):
        boundary = row[side]
        if boundary is None:
            assert row[f"{side}_open_reason"]
            continue
        assert isinstance(boundary, int | float)
        if name.endswith("_km"):
            value = boundary + (-0.001 if side == "lower" else 0.001)
        elif name.endswith("_pct"):
            value = BAND_FLOORS[BAND_FLOORS.index(int(boundary)) + (-1 if side == "lower" else 1)]
        else:
            value = int(boundary) + (-1 if side == "lower" else 1)
        assert outcomes(changed(Thresholds(), name, value)) != baseline, (name, side)


def test_every_rule_and_threshold_is_in_the_mutation_contract() -> None:
    names = set(Thresholds.model_fields)
    assert names == set(CALIBRATION) == set(CALIBRATION_EVIDENCE) == set(THRESHOLD_UNITS)
    assert {rule.id for rule in RULES} == set(RuleId)
    assert set(references()) == set(RuleId)
    assert outcomes(Thresholds()) == references()


def test_cached_readings_preserve_the_real_engine_at_each_threshold_witness() -> None:
    evidence = report()
    intervals = cast("dict[str, dict[str, object]]", evidence["intervals"])
    by_name = {item.case.name: item.case for item in prepared()}
    for name, row in intervals.items():
        for side in ("below", "above"):
            witness = cast("dict[str, object] | None", row[side])
            if witness is None:
                continue
            case = by_name[str(witness["case"])]
            value = cast("float", witness["value"])
            actual = assess(case.snapshot, case.location, changed(Thresholds(), name, value))
            assert {"level": int(actual.level), "rule": str(actual.rule)} == witness["after"]
