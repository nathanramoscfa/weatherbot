# tests/test_phase02_verification.py
"""Phase 2 verifier integration and failure-reporting regressions."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

import verify_phase02 as verification

ROOT = Path(__file__).resolve().parents[1]
STATIC_COUNT = 47
V_ROWS = 26
USAGE_ERROR = 2


def test_roadmap_doc_exists() -> None:
    assert (ROOT / "docs/roadmap/phase02-roadmap.md").is_file()


def test_qa_findings_doc_exists() -> None:
    assert (ROOT / "docs/phase02-qa-findings.md").is_file()


def test_verify_script_runs_fast() -> None:
    result = subprocess.run(  # noqa: S603 - fixed script path and arguments, no shell
        [sys.executable, str(ROOT / "scripts/verify_phase02.py"), "--fast"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(re.findall(r"^\[PASS\] \d{2} ", result.stdout, re.MULTILINE)) == STATIC_COUNT


def test_phase_verify_matrix_includes_02() -> None:
    assert verification.matrix_includes_02()


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
    assert [item.reason for item in outcomes] == ["ValueError", ""]
    assert "PRIVATE-SAMPLE-MUST-NOT-APPEAR" not in output
    assert verification.summary("fast", outcomes, 0) == 1


def test_there_are_47_static_checks() -> None:
    assert len(verification.STATIC_CHECKS) == STATIC_COUNT


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


def run(cases: dict[str, str]) -> verification.PytestRun:
    return verification.PytestRun(verification.Outcome("t", "tests", "PASS"), cases)


def test_test_evidence_needs_a_match_for_every_selection() -> None:
    tests = run({"tests.models.test_times::test_a": "passed"})

    found = verification.evidence(
        "V", tests, [verification.Select("tests.models"), verification.Select("tests.cli")]
    )

    assert (found.status, found.reason) == ("FAIL", "nothing under tests.cli")


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (("passed", "passed"), "PASS"),
        (("passed", "failed"), "FAIL"),
        (("passed", "skipped"), "SKIP"),
    ],
)
def test_test_evidence_never_turns_a_failure_or_a_skip_into_a_pass(
    statuses: tuple[str, str], expected: str
) -> None:
    tests = run({f"tests.models.test_times::test_{n}": s for n, s in enumerate(statuses)})

    assert verification.evidence("V", tests, [verification.Select("tests.models")]).status == (
        expected
    )


def test_a_selection_matches_its_module_its_classes_and_its_name_only() -> None:
    selection = verification.Select("tests.sources.test_nws", "coordinate")

    assert selection.matches("tests.sources.test_nws::test_no_record_carries_a_coordinate[x]")
    assert selection.matches("tests.sources.test_nws.TestPoints::test_a_coordinate")
    assert not selection.matches("tests.sources.test_nws::test_format_point")
    assert not selection.matches("tests.sources.test_nws_extra::test_a_coordinate")


def test_junit_statuses_are_read_from_pytest_s_report(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        '<testsuites><testsuite name="pytest">'
        '<testcase classname="tests.a" name="test_ok"/>'
        '<testcase classname="tests.a" name="test_bad"><failure message="x"/></testcase>'
        '<testcase classname="tests.a" name="test_broken"><error message="x"/></testcase>'
        '<testcase classname="tests.a" name="test_off"><skipped message="x"/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )

    assert verification.junit_cases(report) == {
        "tests.a::test_ok": "passed",
        "tests.a::test_bad": "failed",
        "tests.a::test_broken": "failed",
        "tests.a::test_off": "skipped",
    }
    assert verification.junit_cases(tmp_path / "missing.xml") == {}


def test_the_post_matrix_reports_exactly_26_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    passing = verification.Outcome("x", "stub", "PASS")
    cases = {
        f"{module}::test_{name}": "passed"
        for module in (
            "tests.models.test_times",
            "tests.test_architecture",
            "tests.test_phase01_verification",
            "tests.test_phase02_verification",
            "tests.test_cli",
        )
        for name in ("a",)
    }
    tests = run(cases)
    monkeypatch.setattr(
        verification,
        "py_suites",
        lambda: verification.PySuites([passing], tests, passing),
    )
    monkeypatch.setattr(verification, "live_suite", lambda: tests)
    monkeypatch.setattr(verification, "security_suites", lambda: [passing])

    def probe(*_: object) -> verification.Outcome:
        return passing

    monkeypatch.setattr(verification, "probe", probe)
    statics = [verification.Outcome(f"{n:02d}", "static", "PASS") for n in range(1, 48)]

    rows = verification.post_matrix(statics)

    assert [row.id for row in rows] == [
        f"V{group}.{n}"
        for group, count in enumerate((4, 4, 4, 3, 4, 3, 4), 1)
        for n in range(1, count + 1)
    ]
    assert len(statics) + len(rows) == STATIC_COUNT + V_ROWS


@pytest.mark.parametrize(
    ("relative", "old", "new"),
    [
        (".github/workflows/live-smoke.yml", "  workflow_dispatch:\n", "  push:\n"),
        (".github/workflows/live-smoke.yml", "  contents: read\n", "  contents: write\n"),
        ("src/weatherbot/sources/nws.py", "def format_point(", "def write_point("),
        (".gitignore", "*.sqlite3-*\n", ""),
    ],
)
def test_a_changed_deliverable_turns_its_check_red(
    monkeypatch: pytest.MonkeyPatch, relative: str, old: str, new: str
) -> None:
    original = verification.read

    def edited(path: str, root: Path = verification.REPO_ROOT) -> str:
        text = original(path, root)
        if path == relative:
            assert old in text
            return text.replace(old, new)
        return text

    verification.syntax.cache_clear()
    monkeypatch.setattr(verification, "read", edited)
    try:
        failed = [o.id for o in verification.run_static_checks() if o.status == "FAIL"]
    finally:
        verification.syntax.cache_clear()

    assert len(failed) == 1
