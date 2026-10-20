# scripts/export_ladder.py
"""Render the ladder's three canonical tables in docs/ALERT-LADDER.md; --check writes nothing."""

import argparse
import json
from collections.abc import Mapping
from typing import Final, cast

from ladder_data import ROOT, output_path
from weatherbot.engine import RULES
from weatherbot.models import AlertLevel, Thresholds
from weatherbot.models.ladder import CALIBRATION, CALIBRATION_EVIDENCE, THRESHOLD_UNITS

DOCUMENT: Final = ROOT / "docs/ALERT-LADDER.md"


def interval_text(name: str, row: Mapping[str, object]) -> str:
    """Render the outcome interval, explicitly bounding open ends by the legal domain."""
    lower, upper = row["lower"], row["upper"]
    low = f"{lower:g}" if isinstance(lower, int | float) else "legal minimum"
    high = f"{upper:g}" if isinstance(upper, int | float) else "legal maximum"
    relation = "≤" if row["upper_inclusive"] else "<"
    if lower == upper and lower is not None:
        return f"{{{low}}}"
    notes = [str(row[key]) for key in ("lower_open_reason", "upper_open_reason") if row[key]]
    suffix = "; " + "; ".join(notes) if notes else ""
    discrete = "; legal band floors only" if name.endswith("_pct") else ""
    return f"{low} ≤ x {relation if upper is not None else '≤'} {high}{discrete}{suffix}"


def tables() -> dict[str, str]:
    """Render levels/actions, ordered rules, and calibrated thresholds directly from code."""
    levels = ["| Level | Name | Actions |", "| --- | --- | --- |"]
    levels += [
        f"| {int(level)} | {level.label} | {level.actions} |" for level in reversed(AlertLevel)
    ]
    rules = [
        "| Order | Rule | Level | Trigger | Products read |",
        "| --- | --- | --- | --- | --- |",
    ]
    rules += [
        f"| {index} | `{rule.id}` | {int(rule.level)} | {rule.trigger} | "
        f"{', '.join(rule.reads) or 'none'} |"
        for index, rule in enumerate(RULES, 1)
    ]
    thresholds = [
        "| Threshold | Default | Unit | Outcome interval | Evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    thresholds += [
        f"| `{name}` | {getattr(Thresholds(), name):g} | {THRESHOLD_UNITS[name]} | "
        f"{interval_text(name, CALIBRATION[name])} | {CALIBRATION_EVIDENCE[name]} |"
        for name in Thresholds.model_fields
    ]
    return {
        name: "\n".join(rows)
        for name, rows in (("levels", levels), ("rules", rules), ("thresholds", thresholds))
    }


def render(text: str) -> str:
    """Replace exactly one marked block per table; refuse missing or repeated markers."""
    for name, table in tables().items():
        start, end = f"<!-- ladder:{name} -->", f"<!-- /ladder:{name} -->"
        if text.count(start) != 1 or text.count(end) != 1:
            message = f"ladder document requires one marker pair for {name}"
            raise ValueError(message)
        prefix, tail = text.split(start)
        _, suffix = tail.split(end)
        text = f"{prefix}{start}\n\n{table}\n\n{end}{suffix}"
    evidence = json.loads((ROOT / "docs/ladder-calibration.json").read_bytes())
    rows = cast("list[dict[str, object]]", evidence["pairs"])
    lead = [
        (
            "| Pair | First level 2 (advisory, UTC) | First level 3 (advisory, UTC) | "
            "First watch | First warning | L3 lead (h) | Reversals engine / official |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        first = cast("dict[str, object]", row["first_levels"])
        lead.append(
            f"| {row['pair']} | {_appearance(first.get('2'))} | {_appearance(first.get('3'))} | "
            f"{_appearance(row['first_watch'])} | {_appearance(row['first_warning'])} | "
            f"{row['level_3_watch_lead_h'] if row['level_3_watch_lead_h'] is not None else '—'} | "
            f"{row['level_reversals']} / {row['official_reversals']} |"
        )
    start, end = "<!-- calibration:lead-times -->", "<!-- /calibration:lead-times -->"
    if text.count(start) != 1 or text.count(end) != 1:
        message = "ladder document requires one calibration marker pair"
        raise ValueError(message)
    prefix, tail = text.split(start)
    _, suffix = tail.split(end)
    return f"{prefix}{start}\n\n" + "\n".join(lead) + f"\n\n{end}{suffix}"


def _appearance(value: object) -> str:
    if value is None:
        return "—"
    row = cast("dict[str, str]", value)
    return f"{row['advisory']} at {row['issued_at']}"


def main(argv: list[str] | None = None) -> int:
    """Write or verify the three canonical tables."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    path = output_path(DOCUMENT, ROOT / "docs")
    original = path.read_text(encoding="utf-8")
    current = render(original)
    if args.check:
        print("OK ladder tables are current" if original == current else "STALE ladder tables")
        return 0 if original == current else 1
    path.write_text(current, encoding="utf-8", newline="\n")
    print("wrote docs/ALERT-LADDER.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
