# tests/test_phase04_verification.py
"""Phase 4 verifier integration and failure-reporting regressions."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

import verify_phase04 as verification

ROOT = Path(__file__).resolve().parents[1]
STATIC_COUNT = 51
V_ROWS = 29
USAGE_ERROR = 2


def test_phase_04_roadmap_and_qa_findings_exist() -> None:
    assert (ROOT / "docs/roadmap/phase04-roadmap.md").is_file()
    assert (ROOT / "docs/phase04-qa-findings.md").is_file()


def test_fast_verification_passes_all_static_checks_within_thirty_seconds() -> None:
    result = subprocess.run(  # noqa: S603 - fixed script path and arguments, no shell
        [sys.executable, str(ROOT / "scripts/verify_phase04.py"), "--fast"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(re.findall(r"^\[PASS\] \d{2}: ", result.stdout, re.MULTILINE)) == STATIC_COUNT


def test_phase_verify_workflow_includes_phase_04() -> None:
    assert verification.check_49_matrix_includes_04()


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


def test_static_check_table_has_51_entries() -> None:
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
                verification.Outcome("V7.3", "security", status),
                verification.Outcome("01", "static", "PASS"),
            ]
        )
        == 1
    )


def test_mode_flags_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as error:
        verification.parse_args(["--fast", "--post"])
    assert error.value.code == USAGE_ERROR


def test_junit_selection_must_match_at_least_one_test() -> None:
    suite = verification.Suite(tests={"tests.services.test_policy.test_a": "PASS"})

    status, detail = verification.evaluate_evidence(verification.Select("tests.cli"), suite)

    assert (status, detail) == ("FAIL", "no tests matched tests.cli")


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
        tests={f"tests.services.test_policy.test_{n}": s for n, s in enumerate(statuses)}
    )
    status, _ = verification.evaluate_evidence(verification.Select("tests.services"), suite)
    assert status == expected


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

    assert verification.parse_junit(report) == {
        "tests.a.test_ok": "PASS",
        "tests.a.test_bad": "FAIL",
        "tests.a.test_broken": "FAIL",
        "tests.a.test_off": "SKIP",
    }
    assert verification.parse_junit(tmp_path / "missing.xml") == {}


def test_post_matrix_evaluates_all_twenty_nine_rows_from_recorded_evidence() -> None:
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
    statics = [verification.Outcome(f"{n:02d}", "static", "PASS") for n in range(1, 52)]

    rows = verification.post_matrix(suite)

    assert [row.item_id for row in rows] == [
        f"V{group}.{n}"
        for group, count in enumerate((4, 5, 4, 3, 4, 5, 4), 1)
        for n in range(1, count + 1)
    ]
    assert all(row.status == "PASS" for row in rows)
    assert len(statics) + len(rows) == STATIC_COUNT + V_ROWS
    assert verification.summarize([*statics, *rows]) == 0


@pytest.mark.parametrize(
    ("relative", "old", "new", "check"),
    [
        (
            "src/weatherbot/services/persistence/migrations/versions/0004_shared_geometry.py",
            'down_revision: str | None = "0003"',
            'down_revision: str | None = "0002"',
            "01",
        ),
        (
            "src/weatherbot/services/monitor.py",
            '"resume", "fallback"',
            '"resume", "other_trigger"',
            "08",
        ),
        (
            "src/weatherbot/services/policy.py",
            '"quiet_hours",',
            '"suppressed_quiet",',
            "17",
        ),
        (
            "src/weatherbot/services/toast.py",
            'APP_ID: Final = "Weatherbot.Monitor"',
            'APP_ID: Final = "Weatherbot.Other"',
            "26",
        ),
        (
            "src/weatherbot/services/scheduler.py",
            "MAX_SLEEP_S: Final[float] = 60.0",
            "MAX_SLEEP_S: Final[float] = 120.0",
            "32",
        ),
        (
            "src/weatherbot/services/tasks.py",
            'TASK_FOLDER: Final[str] = r"\\Weatherbot\\"',
            'TASK_FOLDER: Final[str] = r"\\Other\\"',
            "40",
        ),
        (
            "README.md",
            "and Phase 4 (monitoring and notifications) are complete",
            "Phase 4 (monitoring and notifications) is in progress",
            "46",
        ),
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

    monkeypatch.setattr(verification, "read", edited)
    failed = [o.item_id for o in verification.run_static_checks() if o.status == "FAIL"]

    assert failed == [check]


@pytest.mark.parametrize(
    ("head", "ancestor", "expected"),
    [
        ("0006", "0006", True),
        ("0006", "0001", True),
        ("0005", "0006", False),
        ("unknown-revision", "0006", False),
    ],
)
def test_the_operator_database_head_must_descend_from_0006(
    head: str, ancestor: str, *, expected: bool
) -> None:
    assert verification.descends_from(head, ancestor) is expected
