# tests/engine/test_ladder_document.py
"""The written ladder, its calibration, and the fixed output paths remain reviewable."""

from pathlib import Path
from typing import cast

import pytest

import calibrate_ladder
import export_ladder
import ladder_data
from weatherbot.models import BAND_FLOORS, Thresholds

REACH_MIN_KM = 7.6
REACH_MAX_KM = 29.1
END_MAX_KM = 11.3
WATCH_LEAD_MIN_H = 48


def test_all_three_document_tables_equal_the_code_rendering() -> None:
    text = export_ladder.DOCUMENT.read_text(encoding="utf-8")
    assert export_ladder.render(text) == text
    assert export_ladder.main(["--check"]) == 0


def test_calibration_intervals_and_evidence_equal_a_fresh_sweep() -> None:
    assert calibrate_ladder.main(["--check"]) == 0


def test_defaults_meet_the_retained_calibration_criteria() -> None:
    thresholds = Thresholds()
    assert REACH_MIN_KM <= thresholds.coastal_reach_km <= REACH_MAX_KM
    assert thresholds.segment_end_tolerance_km <= END_MAX_KM
    assert thresholds.cone_horizon_h % 12 == 0
    assert thresholds.hurricane_wind_floor_pct in BAND_FLOORS
    assert thresholds.tropical_storm_wind_floor_pct in BAND_FLOORS
    assert thresholds.development_chance_floor_pct == 0
    pairs = calibrate_ladder.summaries()
    watches = [row for row in pairs if row["first_watch"] is not None]
    assert watches
    assert all(cast("float", row["level_3_watch_lead_h"]) >= WATCH_LEAD_MIN_H for row in watches)


def test_missing_or_duplicated_document_markers_fail() -> None:
    text = export_ladder.DOCUMENT.read_text(encoding="utf-8")
    for bad in (text.replace("<!-- ladder:rules -->", ""), text + "<!-- ladder:rules -->"):
        with pytest.raises(ValueError, match="one marker pair"):
            export_ladder.render(bad)


def test_tool_outputs_cannot_escape_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ladder_data, "ROOT", tmp_path)
    allowed = tmp_path / "docs"
    assert ladder_data.output_path(allowed / "ladder.json", allowed) == allowed / "ladder.json"
    with pytest.raises(ValueError, match="designated repository directory"):
        ladder_data.output_path(allowed / "../../outside.json", allowed)
    with pytest.raises(ValueError, match="designated repository directory"):
        ladder_data.output_path(tmp_path.parent / "outside.json", tmp_path.parent)
