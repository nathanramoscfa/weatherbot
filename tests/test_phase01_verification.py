# tests/test_phase01_verification.py
"""Phase 1 verifier integration and failure-reporting regressions."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

import verify_phase01 as verification

ROOT = Path(__file__).resolve().parents[1]
STATIC_COUNT = 50
USAGE_ERROR = 2


def test_roadmap_doc_exists() -> None:
    assert (ROOT / "docs/roadmap/phase01-roadmap.md").is_file()


def test_qa_findings_doc_exists() -> None:
    assert (ROOT / "docs/phase01-qa-findings.md").is_file()


def test_verify_script_runs_fast() -> None:
    result = subprocess.run(  # noqa: S603 - fixed script path and arguments, no shell
        [sys.executable, str(ROOT / "scripts/verify_phase01.py"), "--fast"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(re.findall(r"^\[PASS\] \d{2} ", result.stdout, re.MULTILINE)) == STATIC_COUNT


def test_phase_verify_matrix_includes_01() -> None:
    assert verification.matrix_includes_01()


def test_static_checks_continue_after_failure_without_echoing_content(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken() -> bool:
        message = "PRIVATE-SAMPLE-MUST-NOT-APPEAR"
        raise ValueError(message)

    monkeypatch.setattr(
        verification,
        "STATIC_CHECKS",
        (
            ("broken check", broken),
            ("later check", lambda: True),
        ),
    )
    outcomes = verification.run_static_checks()
    output = capsys.readouterr().out
    assert [item.status for item in outcomes] == ["FAIL", "PASS"]
    assert "PRIVATE-SAMPLE-MUST-NOT-APPEAR" not in output
    assert verification.summary("fast", outcomes, 0) == 1


def test_skipped_evidence_cannot_pass_the_post_matrix() -> None:
    result = verification.aggregate(
        "V7.4",
        "security",
        [
            verification.Outcome("secrets", "history scan", "SKIP"),
            verification.Outcome("sast", "SAST", "PASS"),
        ],
    )
    assert result.status == "SKIP"


def test_mode_flags_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as error:
        verification.parse_args(["--fast", "--post"])
    assert error.value.code == USAGE_ERROR
