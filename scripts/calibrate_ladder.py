# scripts/calibrate_ladder.py
"""Sweep the ladder's legal thresholds against the eight replays and shared scenarios.

Continuous distance thresholds are swept at every measured segment distance, their
only discontinuities, rather than on a grid that could miss a narrow interval. Integer
hours and probability band floors are enumerated exhaustively. Only level and deciding
rule define an unchanged outcome; fingerprints and evidence wording do not.
"""

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import cache
from itertools import pairwise
from typing import Final, cast

from ladder_data import ROOT, Case, cases, output_path, utc
from weatherbot.engine import RULES, Rule
from weatherbot.engine.assess import read
from weatherbot.engine.rules import Readings
from weatherbot.models import BAND_FLOORS, RULE_LEVELS, AlertLevel, RuleId, Thresholds, ladder

REPORT: Final = ROOT / "docs/ladder-calibration.json"
DISTANCES: Final = {"coastal_reach_km": 200.0, "segment_end_tolerance_km": 50.0}
PROBABILITIES: Final = (
    "hurricane_wind_floor_pct",
    "tropical_storm_wind_floor_pct",
    "development_chance_floor_pct",
)


@dataclass(frozen=True)
class Prepared:
    """Geometry measured once at the maximum legal segment reaches."""

    case: Case
    readings: Readings

    def at(self, thresholds: Thresholds) -> Readings:
        """Apply the two distance thresholds to the premeasured candidate products."""
        official = tuple(
            p
            for p in self.readings.official
            if p.kind == "nws_alert"
            or (
                p.distance_km is not None
                and p.distance_km
                <= (
                    thresholds.segment_end_tolerance_km if p.at_end else thresholds.coastal_reach_km
                )
            )
        )
        return replace(self.readings, thresholds=thresholds, official=official)


@cache
def prepared() -> tuple[Prepared, ...]:
    """Read the corpus and the scenarios, with no writes or network requests."""
    wide = Thresholds(coastal_reach_km=200.0, segment_end_tolerance_km=50.0)
    return tuple(Prepared(case, read(case.snapshot, case.location, wide)[0]) for case in cases())


def winner(readings: Readings, rules: Sequence[Rule] = RULES) -> RuleId:
    """Evaluate the real rule predicates, returning the first match or all clear."""
    return next((rule.id for rule in rules if rule.evaluate(readings)), RuleId.ALL_CLEAR)


def outcomes(thresholds: Thresholds, rules: Sequence[Rule] = RULES) -> tuple[RuleId, ...]:
    """Project all reference cases to their deciding rules (which also fix the levels)."""
    return tuple(winner(item.at(thresholds), rules) for item in prepared())


def changed(thresholds: Thresholds, name: str, value: float) -> Thresholds:
    """Build and validate a single-threshold mutation."""
    return Thresholds.model_validate(thresholds.model_dump() | {name: value})


def legal_values(name: str, thresholds: Thresholds) -> tuple[float, ...]:
    """Every discontinuity of a distance, every hour, or every probability band floor."""
    if name in PROBABILITIES:
        return BAND_FLOORS
    if name == "cone_horizon_h":
        return tuple(range(1, 121))
    at_end = name == "segment_end_tolerance_km"
    maximum = DISTANCES[name]
    return tuple(
        sorted(
            {
                0.0,
                maximum,
                getattr(thresholds, name),
                *(
                    p.distance_km
                    for item in prepared()
                    for p in item.readings.official
                    if p.kind == "watch_warning_segment"
                    and p.at_end == at_end
                    and p.distance_km is not None
                    and p.distance_km <= maximum
                ),
            }
        )
    )


def _witness(name: str, value: float, baseline: tuple[RuleId, ...]) -> dict[str, object]:
    after = outcomes(changed(Thresholds(), name, value))
    index = next(i for i, (old, new) in enumerate(zip(baseline, after, strict=True)) if old != new)
    return {
        "case": prepared()[index].case.name,
        "value": round(value, 6),
        "before": {"level": int(RULE_LEVELS[baseline[index]]), "rule": str(baseline[index])},
        "after": {"level": int(RULE_LEVELS[after[index]]), "rule": str(after[index])},
    }


def sweep(name: str) -> dict[str, object]:
    """Find the contiguous interval around a default, with a witness beyond each bound."""
    thresholds = Thresholds()
    baseline = outcomes(thresholds)
    values = legal_values(name, thresholds)
    index = values.index(getattr(thresholds, name))
    same = [outcomes(changed(thresholds, name, value)) == baseline for value in values]
    low = high = index
    while low > 0 and same[low - 1]:
        low -= 1
    while high + 1 < len(values) and same[high + 1]:
        high += 1
    continuous = name in DISTANCES
    lower = values[low] if low else None
    # A distance starts changing at the next measured distance (exclusive); discrete
    # fields retain their last passing legal value (inclusive).
    upper = (values[high + 1] if continuous else values[high]) if high + 1 < len(values) else None
    below = round(values[low] - 0.001, 6) if continuous and low else values[low - 1]
    above = values[high + 1] if high + 1 < len(values) else None
    if continuous and above is not None:
        above = round(above + 0.001, 6)
    return {
        "default": getattr(thresholds, name),
        "lower": round(lower, 6) if lower is not None else None,
        "upper": round(upper, 6) if upper is not None else None,
        "upper_inclusive": not continuous,
        "lower_open_reason": f"legal minimum {values[0]:g}; the corpus cannot bind below it"
        if low == 0
        else None,
        "upper_open_reason": f"legal maximum {values[-1]:g}; the corpus cannot bind above it"
        if high + 1 == len(values)
        else None,
        "below": _witness(name, below, baseline) if low else None,
        "above": _witness(name, above, baseline) if above is not None else None,
        "values_examined": len(values),
    }


def reversals(levels: Sequence[int]) -> int:
    """Count direction changes after dropping repeated levels; the final decline counts once."""
    directions = [1 if b > a else -1 for a, b in pairwise(levels) if a != b]
    return sum(a != b for a, b in pairwise(directions))


def summaries() -> list[dict[str, object]]:
    """Report first appearances, official watches/warnings, reversals and closest approaches."""
    thresholds = Thresholds()
    groups = tuple(
        dict.fromkeys(item.case.group for item in prepared() if item.case.group != "scenarios")
    )
    result: list[dict[str, object]] = []
    for group in groups:
        items = [p for p in prepared() if p.case.group == group]
        readings = [p.at(thresholds) for p in items]
        rules = [winner(r) for r in readings]
        levels = [int(RULE_LEVELS[rule]) for rule in rules]
        first: dict[str, dict[str, object]] = {}
        for item, r, level in zip(items, readings, levels, strict=True):
            first.setdefault(
                str(level), {"advisory": item.case.advisory, "issued_at": utc(r.as_of)}
            )
        official = [
            max((int(RULE_LEVELS[p.rule]) for p in r.official if p.covers and p.rule), default=1)
            for r in readings
        ]
        watch = next(
            (
                i
                for i, r in enumerate(readings)
                if any(p.code in {"TWA", "HWA"} and p.covers for p in r.official)
            ),
            None,
        )
        warning = next(
            (
                i
                for i, r in enumerate(readings)
                if any(p.code in {"TWR", "HWR"} and p.covers for p in r.official)
            ),
            None,
        )
        first3 = next(
            (i for i, level in enumerate(levels) if level == AlertLevel.WATCH_HURRICANE_THREAT),
            None,
        )
        first2 = next(
            (i for i, level in enumerate(levels) if level == AlertLevel.TROPICAL_STORM_THREAT), None
        )
        approaches = [
            (threat.closest_approach_km, item.case.advisory, threat.closest_approach_at)
            for item, r in zip(items, readings, strict=True)
            for threat in r.threats
            if threat.closest_approach_km is not None
        ]
        closest = min(approaches, key=lambda x: x[0]) if approaches else None
        result.append(
            {
                "pair": group,
                "first_levels": first,
                "first_watch": {
                    "advisory": items[watch].case.advisory,
                    "issued_at": utc(readings[watch].as_of),
                }
                if watch is not None
                else None,
                "first_warning": {
                    "advisory": items[warning].case.advisory,
                    "issued_at": utc(readings[warning].as_of),
                }
                if warning is not None
                else None,
                "level_3_watch_lead_h": (
                    readings[watch].as_of - readings[first3].as_of
                ).total_seconds()
                / 3600
                if watch is not None and first3 is not None
                else None,
                "level_2_before_3": first2 < first3
                if first2 is not None and first3 is not None
                else None,
                "level_reversals": reversals(levels),
                "official_reversals": reversals(official),
                "closest_forecast_approach": {
                    "km": round(closest[0], 3),
                    "advisory": closest[1],
                    "instant": utc(closest[2].replace(microsecond=0)) if closest[2] else None,
                }
                if closest
                else None,
            }
        )
    return result


def indistinguishable() -> list[list[str]]:
    """Name exactly the adjacent swaps whose deciding outcomes the reference cannot distinguish."""
    baseline = outcomes(Thresholds())
    found: list[list[str]] = []
    for i in range(len(RULES) - 1):
        rules = list(RULES)
        rules[i], rules[i + 1] = rules[i + 1], rules[i]
        if outcomes(Thresholds(), rules) == baseline:
            found.append([str(RULES[i].id), str(RULES[i + 1].id)])
    return found


def report() -> dict[str, object]:
    """Build the reproducible evidence document; its date records this calibration decision."""
    return {
        "_file": "docs/ladder-calibration.json",
        "date": "2026-10-20",
        "criteria_decision": (
            "Operator approved measured ordering/reversal exceptions on 2026-10-20; "
            "retain the 48-hour watch lead target."
        ),
        "intervals": {name: sweep(name) for name in Thresholds.model_fields},
        "pairs": summaries(),
        "indistinguishable_adjacent_pairs": indistinguishable(),
    }


def main(argv: list[str] | None = None) -> int:
    """Write the evidence, or verify every recorded interval against a fresh sweep."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    document = report()
    if args.check:
        intervals = cast("dict[str, dict[str, object]]", document["intervals"])
        expected = ladder.CALIBRATION
        current = {
            name: {
                key: value
                for key, value in row.items()
                if key not in {"below", "above", "values_examined"}
            }
            for name, row in intervals.items()
        }
        ok = (
            current == expected and REPORT.is_file() and json.loads(REPORT.read_bytes()) == document
        )
        print(
            "OK calibration intervals and evidence are current"
            if ok
            else "STALE calibration intervals or evidence"
        )
        return 0 if ok else 1
    path = output_path(REPORT, ROOT / "docs")
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
