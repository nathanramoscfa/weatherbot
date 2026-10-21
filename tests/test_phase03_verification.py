# tests/test_phase03_verification.py
"""Phase 3 verifier integration and failure-reporting regressions."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

import verify_phase03 as verification

ROOT = Path(__file__).resolve().parents[1]
STATIC_COUNT = 52
V_ROWS = 28
USAGE_ERROR = 2


def test_roadmap_doc_exists() -> None:
    assert (ROOT / "docs/roadmap/phase03-roadmap.md").is_file()


def test_qa_findings_doc_exists() -> None:
    assert (ROOT / "docs/phase03-qa-findings.md").is_file()


def test_verify_script_runs_fast() -> None:
    result = subprocess.run(  # noqa: S603 - fixed script path and arguments, no shell
        [sys.executable, str(ROOT / "scripts/verify_phase03.py"), "--fast"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(re.findall(r"^\[PASS\] \d{2} ", result.stdout, re.MULTILINE)) == STATIC_COUNT


def test_phase_verify_matrix_includes_03() -> None:
    assert verification.matrix_includes_03()


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


def test_there_are_52_static_checks() -> None:
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
    tests = run({"tests.engine.test_rules::test_a": "passed"})

    found = verification.evidence(
        "V",
        tests,
        [verification.Select("tests.engine.test_rules"), verification.Select("tests.cli")],
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
    tests = run({f"tests.engine.test_rules::test_{n}": s for n, s in enumerate(statuses)})

    assert verification.evidence("V", tests, [verification.Select("tests.engine")]).status == (
        expected
    )


def test_a_selection_matches_its_module_its_classes_and_its_name_only() -> None:
    selection = verification.Select("tests.engine.test_arrivals", "dorian_036")

    assert selection.matches("tests.engine.test_arrivals::test_the_archived_dorian_036_pair[x]")
    assert selection.matches("tests.engine.test_arrivals.TestReading::test_dorian_036")
    assert not selection.matches("tests.engine.test_arrivals::test_irma_036")
    assert not selection.matches("tests.engine.test_arrivals_extra::test_dorian_036")


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


def test_the_post_matrix_reports_exactly_28_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    passing = verification.Outcome("x", "stub", "PASS")
    tests = run({"tests.test_phase03_verification::test_a": "passed"})
    monkeypatch.setattr(
        verification,
        "py_suites",
        lambda: verification.PySuites([passing], tests, passing),
    )
    monkeypatch.setattr(verification, "live_suite", lambda: tests)
    monkeypatch.setattr(
        verification, "corpus_suite", lambda: verification.CorpusSuite([passing], tests)
    )
    monkeypatch.setattr(verification, "security_suites", lambda: [passing])

    def probe(*_: object) -> verification.Outcome:
        return passing

    monkeypatch.setattr(verification, "probe", probe)
    statics = [verification.Outcome(f"{n:02d}", "static", "PASS") for n in range(1, 53)]

    rows = verification.post_matrix(statics)

    assert [row.id for row in rows] == [
        f"V{group}.{n}"
        for group, count in enumerate((4, 4, 3, 3, 5, 5, 4), 1)
        for n in range(1, count + 1)
    ]
    assert len(statics) + len(rows) == STATIC_COUNT + V_ROWS


@pytest.mark.parametrize(
    ("relative", "old", "new", "check"),
    [
        ("src/weatherbot/engine/geodesy.py", "def distance_km(", "def distance_m(", "02"),
        (
            "tests/fixtures/replay/corpus-manifest.json",
            '"recorded_on": "2026-10-15"',
            '"recorded_on": "15 October"',
            "13",
        ),
        (".github/workflows/replay-corpus.yml", "      - src/weatherbot/engine/**\n", "", "16"),
        ("src/weatherbot/models/assessment.py", '    "cone_left",\n)\n', ")\n", "32"),
        (
            "src/weatherbot/models/ladder.py",
            '"0% follows the brief',
            '"0% (provisional) follows the brief',
            "38",
        ),
        ("src/weatherbot/cli/__init__.py", 'app.command("replay")', 'app.command("rerun")', "43"),
        ("README.md", "weatherbot locations evacuation", "weatherbot locations toggle", "47"),
    ],
)
def test_a_changed_deliverable_turns_exactly_its_check_red(
    monkeypatch: pytest.MonkeyPatch, relative: str, old: str, new: str, check: str
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

    assert failed == [check]


@pytest.mark.parametrize(
    ("head", "ancestor", "expected"),
    [
        ("0003", "0003", True),
        ("0003", "0001", True),
        ("0002", "0003", False),
        ("unknown-revision", "0003", False),
    ],
)
def test_the_operator_database_head_must_descend_from_0003(
    head: str, ancestor: str, *, expected: bool
) -> None:
    assert verification.descends_from(head, ancestor) is expected


def issues(county: dict[str, object], surge: dict[str, object]) -> dict[str, object]:
    return {"issues/10": county, f"issues/{verification.STORM_SURGE_ISSUE}": surge}


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        (
            issues({"state": "closed", "comments": 2}, {"state": "open", "comments": 0}),
            True,
        ),
        (
            issues({"state": "closed", "comments": 2}, {"state": "closed", "comments": 1}),
            True,
        ),
        (
            issues({"state": "open", "comments": 2}, {"state": "open", "comments": 0}),
            False,
        ),
        (
            issues({"state": "closed", "comments": 0}, {"state": "open", "comments": 0}),
            False,
        ),
        (
            issues({"state": "closed", "comments": 2}, {"state": "closed", "comments": 0}),
            False,
        ),
    ],
)
def test_issue_10_must_be_decided_and_the_surge_issue_open_or_decided(
    monkeypatch: pytest.MonkeyPatch, answers: dict[str, object], *, expected: bool
) -> None:
    monkeypatch.setattr(verification, "github_api", answers.__getitem__)

    assert verification.issues_decided() is expected
