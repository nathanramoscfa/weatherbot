# tests/scripts/test_serve_demo.py
"""Offline tests for ``scripts/serve_demo.py`` argument parsing and switch-file simulation."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from source_support import NOW

if TYPE_CHECKING:
    import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from serve_demo import (  # noqa: E402
    DEFAULT_PORT,
    _baseline_forecast_alerts_response,  # pyright: ignore[reportPrivateUsage]
    _baseline_roster_response,  # pyright: ignore[reportPrivateUsage]
    _parse_args,  # pyright: ignore[reportPrivateUsage]
    _ServeAddressHandler,  # pyright: ignore[reportPrivateUsage]
)
from simulate_advisory import (  # noqa: E402
    hurricane_warning_response,
    next_advisory_roster,
)


def test_parse_args_defaults_and_overrides(tmp_path: Path) -> None:
    defaults = _parse_args([])
    assert defaults.port == DEFAULT_PORT
    assert defaults.roster_interval_minutes is None
    assert defaults.switch_file is None

    switch_file = tmp_path / "switch.flag"
    corpus_dir = tmp_path / "corpus"
    overridden = _parse_args(
        [
            "--port",
            "0",
            "--corpus",
            str(corpus_dir),
            "--roster-interval-minutes",
            "1",
            "--switch-file",
            str(switch_file),
        ]
    )
    assert overridden.port == 0
    assert overridden.corpus == corpus_dir
    assert overridden.roster_interval_minutes == 1
    assert overridden.switch_file == switch_file


def test_baseline_and_switched_responses_serve_advisory_023_and_hurricane_warning() -> None:
    baseline_roster = json.loads(_baseline_roster_response().content)
    switched_roster = json.loads(next_advisory_roster())
    assert baseline_roster["activeStorms"][0]["publicAdvisory"]["advNum"] == "022a"
    assert switched_roster["activeStorms"][0]["publicAdvisory"]["advNum"] == "023"

    baseline_alerts = json.loads(_baseline_forecast_alerts_response().content)
    switched_alerts = json.loads(hurricane_warning_response(NOW).content)
    assert baseline_alerts["features"][0]["properties"]["event"] != "Hurricane Warning"
    assert len(switched_alerts["features"]) == 1
    assert switched_alerts["features"][0]["properties"]["event"] == "Hurricane Warning"


def test_serve_address_handler_emits_pid_and_address_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    handler = _ServeAddressHandler()
    logger = logging.getLogger("test.serve_demo.address")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("unrelated message")
        logger.info("dashboard at http://127.0.0.1:8799")
        logger.info("dashboard at http://127.0.0.1:8799")
    finally:
        logger.removeHandler(handler)

    captured = capsys.readouterr()
    lines = [line.strip() for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0].startswith("pid=")
    assert lines[0].endswith("address=http://127.0.0.1:8799")
