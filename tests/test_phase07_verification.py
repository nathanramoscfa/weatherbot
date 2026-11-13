# tests/test_phase07_verification.py
"""Phase 7 verifier integration and failure-reporting regressions."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

import verify_phase07 as verification

ROOT = Path(__file__).resolve().parents[1]
STATIC_COUNT = 65
V_ROWS = 42
USAGE_ERROR = 2


def test_phase_07_roadmap_and_qa_findings_exist() -> None:
    assert (ROOT / "docs/roadmap/phase07-roadmap.md").is_file()
    assert (ROOT / "docs/phase07-qa-findings.md").is_file()


def test_fast_verification_passes_all_static_checks_within_thirty_seconds() -> None:
    result = subprocess.run(  # noqa: S603 - fixed script path and arguments, no shell
        [sys.executable, str(ROOT / "scripts/verify_phase07.py"), "--fast"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(re.findall(r"^\[PASS\] \d{2}: ", result.stdout, re.MULTILINE)) == STATIC_COUNT


def test_phase_verify_workflow_includes_phase_07() -> None:
    assert verification.check_64_phase_verify_workflow_includes_07()


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
    assert [item.detail for item in outcomes] == ["ValueError", ""]
    assert "PRIVATE-SAMPLE-MUST-NOT-APPEAR" not in output
    assert verification.summarize(outcomes) == 1


def test_static_check_table_has_65_entries() -> None:
    assert len(verification.STATIC_CHECKS) == STATIC_COUNT


def test_skipped_evidence_cannot_pass_a_verification_item() -> None:
    suite = verification.Suite(
        commands={"gitleaks": "SKIP", "bandit": "PASS", "audit_deps": "PASS"},
    )
    status, _ = verification.evaluate_evidence("gitleaks", suite)
    assert status == "SKIP"
    assert (
        verification.summarize(
            [
                verification.Outcome("V10.4", "security", status),
                verification.Outcome("01", "static", "PASS"),
            ]
        )
        == 1
    )


def test_mode_flags_are_mutually_exclusive() -> None:
    for left, right in (
        ("--fast", "--post"),
        ("--py", "--node"),
        ("--ui", "--security"),
        ("--all", "--post"),
        ("--live", "--fast"),
    ):
        with pytest.raises(SystemExit) as error:
            verification.parse_args([left, right])
        assert error.value.code == USAGE_ERROR


def test_junit_selection_must_match_at_least_one_test() -> None:
    suite = verification.Suite(tests={"tests.services.test_ntfy.test_a": "PASS"})

    status, detail = verification.evaluate_evidence(
        verification.Select("tests.services.test_ntfy", "tests.services.test_retention"),
        suite,
    )

    assert (status, detail) == ("FAIL", "no tests matched tests.services.test_retention")


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (("PASS", "PASS"), "PASS"),
        (("PASS", "FAIL"), "FAIL"),
        (("PASS", "SKIP"), "SKIP"),
    ],
)
def test_test_evidence_never_turns_a_failure_or_a_skip_into_a_pass(
    statuses: tuple[verification.Status, verification.Status],
    expected: verification.Status,
) -> None:
    suite = verification.Suite(
        tests={f"tests.services.test_ntfy.test_{n}": s for n, s in enumerate(statuses)}
    )
    status, _ = verification.evaluate_evidence(
        verification.Select("tests.services.test_ntfy"),
        suite,
    )
    assert status == expected


def test_junit_statuses_are_read_from_pytest_vitest_and_playwright_reports(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        '<testsuites><testsuite name="suite">'
        '<testcase classname="tests.services.test_ntfy" name="test_ok"/>'
        '<testcase classname="src/charts/scale.test.ts" name="scale &gt; linear"/>'
        '<testcase classname="phase7.spec.ts" name="smoke"><failure message="x"/></testcase>'
        '<testcase classname="tests.services" name="test_broken"><error message="x"/></testcase>'
        '<testcase classname="tests.live.test_ntfy_live" name="test_off">'
        '<skipped message="x"/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )

    assert verification.parse_junit(report) == {
        "tests.services.test_ntfy.test_ok": "PASS",
        "src/charts/scale.test.ts.scale > linear": "PASS",
        "phase7.spec.ts.smoke": "FAIL",
        "tests.services.test_broken": "FAIL",
        "tests.live.test_ntfy_live.test_off": "SKIP",
    }
    assert verification.parse_junit(tmp_path / "missing.xml") == {}


def test_post_matrix_evaluates_all_forty_two_rows_from_recorded_evidence() -> None:
    commands: dict[str, verification.Status] = {}
    tests: dict[str, verification.Status] = {}
    for row in verification.V_MATRIX:
        for item in row.evidence:
            if isinstance(item, str):
                commands[item] = "PASS"
            else:
                for prefix in item.prefixes:
                    tests[f"{prefix}.test_sample"] = "PASS"
    suite = verification.Suite(commands=commands, tests=tests)
    statics = [verification.Outcome(f"{n:02d}", "static", "PASS") for n in range(1, 66)]

    rows = verification.post_matrix(suite)

    assert [row.item_id for row in rows] == [
        f"V{group}.{n}"
        for group, count in enumerate(verification.EXPECTED_V_DISTRIBUTION, 1)
        for n in range(1, count + 1)
    ]
    assert all(row.status == "PASS" for row in rows)
    assert len(statics) + len(rows) == STATIC_COUNT + V_ROWS
    assert verification.summarize([*statics, *rows]) == 0


def test_failed_probe_records_fail_status_without_raising(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def explode() -> bool:
        message = "SENSITIVE-PROBE-TEXT"
        raise RuntimeError(message)

    suite = verification.Suite()
    verification.run_probe("probe_key", "sample probe", explode, suite)
    output = capsys.readouterr().out
    assert suite.commands["probe_key"] == "FAIL"
    assert "RuntimeError" in output
    assert "SENSITIVE-PROBE-TEXT" not in output


@pytest.mark.parametrize(
    ("relative", "old", "new", "check"),
    [
        # Step 1 -> Check 02
        (
            ".github/workflows/ci.yml",
            "-n auto",
            "-n 0",
            "02",
        ),
        # Step 2 -> Check 08
        (
            "src/weatherbot/sources/http.py",
            '"q"}',
            '"query_text"}',
            "08",
        ),
        # Step 3 -> Check 14
        (
            "src/weatherbot/services/ntfy.py",
            "follow_redirects=False",
            "follow_redirects=True",
            "14",
        ),
        # Step 4 -> Check 27
        (
            "src/weatherbot/services/config.py",
            '"WEATHERBOT_RETENTION_HISTORY_DAYS"',
            '"WEATHERBOT_RETENTION_DAYS"',
            "27",
        ),
        # Step 5 -> Check 35
        (
            "src/weatherbot/web/guards.py",
            "https://nowcoast.noaa.gov",
            "https://example.invalid",
            "35",
        ),
        # Step 6 -> Check 44
        (
            "frontend/src/charts/LevelSparkline.tsx",
            'role="img"',
            'role="img" style={{}}',
            "44",
        ),
        # Step 7 -> Check 50
        (
            "src/weatherbot/engine/changes.py",
            '", whose cone does not cover the location"',
            '", whose cone does not"',
            "50",
        ),
        # Step 8 -> Check 52
        (
            "src/weatherbot/services/report.py",
            "html.escape(",
            "str(",
            "52",
        ),
        # Step 9 -> Check 57
        (
            "scripts/measure_idle.py",
            "IDLE_BUDGET_PCT: Final = 0.5",
            "IDLE_BUDGET_PCT: Final = 1.5",
            "57",
        ),
        # Step 10 -> Check 62
        (
            "docs/phase07-qa-findings.md",
            "## Pre-ship items",
            "## Deferred items",
            "62",
        ),
    ],
)
def test_a_changed_deliverable_turns_exactly_its_check_red(
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    old: str,
    new: str,
    check: str,
) -> None:
    original = verification.read

    def edited(path: str, root: Path = verification.REPO_ROOT) -> str:
        text = original(path, root)
        if path == relative:
            assert old in text
            return text.replace(old, new)
        return text

    monkeypatch.setattr(verification, "read", edited)
    failed = [o.item_id for o in verification.run_static_checks() if o.status == "FAIL"]

    assert failed == [check]


@pytest.mark.parametrize(
    ("head", "ancestor", "expected"),
    [
        ("0010", "0010", True),
        ("0010", "0001", True),
        ("0009", "0010", False),
        ("unknown-revision", "0010", False),
    ],
)
def test_the_operator_database_head_must_descend_from_0010(
    head: str,
    ancestor: str,
    *,
    expected: bool,
) -> None:
    assert verification.descends_from(head, ancestor) is expected
