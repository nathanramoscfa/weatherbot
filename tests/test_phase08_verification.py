# tests/test_phase08_verification.py
"""Phase 8 verifier integration and failure-reporting regressions."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

import verify_phase08 as verification

ROOT = Path(__file__).resolve().parents[1]
STATIC_COUNT = 60
V_ROWS = 38
USAGE_ERROR = 2


def test_phase_08_roadmap_and_qa_findings_exist() -> None:
    assert (ROOT / "docs/roadmap/phase08-roadmap.md").is_file()
    assert (ROOT / "docs/phase08-qa-findings.md").is_file()


def test_fast_verification_passes_all_static_checks_within_thirty_seconds() -> None:
    result = subprocess.run(  # noqa: S603 - fixed script path and arguments, no shell
        [sys.executable, str(ROOT / "scripts/verify_phase08.py"), "--fast"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(re.findall(r"^\[PASS\] \d{2}: ", result.stdout, re.MULTILINE)) == STATIC_COUNT


def test_phase_verify_workflow_includes_phase_08() -> None:
    assert verification.check_58_phase_verify_workflow_includes_08()


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


def test_static_check_table_has_60_entries() -> None:
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
    suite = verification.Suite(tests={"tests.services.test_ladder_reference.test_a": "PASS"})

    status, detail = verification.evaluate_evidence(
        verification.Select(
            "tests.services.test_ladder_reference",
            "tests.web.test_ladder_route",
        ),
        suite,
    )

    assert (status, detail) == ("FAIL", "no tests matched tests.web.test_ladder_route")


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
        tests={f"tests.services.test_ladder_reference.test_{n}": s for n, s in enumerate(statuses)}
    )
    status, _ = verification.evaluate_evidence(
        verification.Select("tests.services.test_ladder_reference"),
        suite,
    )
    assert status == expected


def test_junit_statuses_are_read_from_pytest_vitest_and_playwright_reports(
    tmp_path: Path,
) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        '<testsuites><testsuite name="suite">'
        '<testcase classname="tests.services.test_ladder_reference" name="test_ok"/>'
        '<testcase classname="src/ui/Tabs.test.tsx" name="Tabs &gt; keyboard"/>'
        '<testcase classname="phase8.spec.ts" name="smoke"><failure message="x"/></testcase>'
        '<testcase classname="tests.services" name="test_broken"><error message="x"/></testcase>'
        '<testcase classname="tests.live.test_ntfy_live" name="test_off">'
        '<skipped message="x"/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )

    assert verification.parse_junit(report) == {
        "tests.services.test_ladder_reference.test_ok": "PASS",
        "src/ui/Tabs.test.tsx.Tabs > keyboard": "PASS",
        "phase8.spec.ts.smoke": "FAIL",
        "tests.services.test_broken": "FAIL",
        "tests.live.test_ntfy_live.test_off": "SKIP",
    }
    assert verification.parse_junit(tmp_path / "missing.xml") == {}


def test_post_matrix_evaluates_all_thirty_eight_rows_from_recorded_evidence() -> None:
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
    statics = [verification.Outcome(f"{n:02d}", "static", "PASS") for n in range(1, 61)]

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
    verification.run_probe("dogfood_probe", "sample probe", explode, suite)
    output = capsys.readouterr().out
    assert suite.commands["dogfood_probe"] == "FAIL"
    assert "RuntimeError" in output
    assert "SENSITIVE-PROBE-TEXT" not in output
    row_status, _ = verification.evaluate_evidence("dogfood_probe", suite)
    assert row_status == "FAIL"
    assert verification.summarize([verification.Outcome("V8.2", "dogfood", row_status)]) == 1


@pytest.mark.parametrize(
    ("relative", "old", "new", "check"),
    [
        # Step 1 -> Check 03
        (
            "scripts/serve_demo.py",
            '"--scenario"',
            '"--demo-mode"',
            "03",
        ),
        # Step 2 -> Check 08
        (
            "frontend/src/index.css",
            "--text-caption: 0.8125rem;",
            "--text-caption: 0.75rem;",
            "08",
        ),
        # Step 3 -> Check 19
        (
            "frontend/src/api/keys.ts",
            'invalidatableQueryKey("settings", "ladder")',
            'invalidatableQueryKey("settings", "rules")',
            "19",
        ),
        # Step 4 -> Check 27
        (
            "frontend/src/dashboard/ExportPopover.tsx",
            '"export-report-all"',
            '"export-report-every"',
            "27",
        ),
        # Step 5 -> Check 33
        (
            "frontend/e2e/map.spec.ts",
            "leaflet-map-container",
            "legacy-map-container",
            "33",
        ),
        # Step 6 -> Check 36
        (
            "frontend/src/pages/Replay.tsx",
            "xl:grid-cols-2",
            "xl:grid-cols-1",
            "36",
        ),
        # Step 7 -> Check 41
        (
            "frontend/src/pages/Ask.tsx",
            '"ask-chip-1"',
            '"prompt-chip-1"',
            "41",
        ),
        # Step 8 -> Check 50
        (
            "frontend/src/app/AppShell.test.tsx",
            "Stale monitor data:",
            "Monitor data notice:",
            "50",
        ),
        # Step 9 -> Check 51
        (
            "docs/phase08-dogfood.md",
            "Operator sign-off (2026-11-17):",
            "Operator review pending:",
            "51",
        ),
        # Step 10 -> Check 56
        (
            "docs/phase08-qa-findings.md",
            "## Pre-ship items",
            "## Deferred items",
            "56",
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


def test_the_live_status_moves_check_52_until_phase_9_converts_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = verification.read

    def edited(path: str, root: Path = verification.REPO_ROOT) -> str:
        text = original(path, root)
        if path == "README.md":
            assert "## Status" in text
            return re.sub(
                r"^## Status$.*?(?=^## )",
                "## Status\n\nPhase 8 (UI/UX redesign and visual dogfooding) is in progress.\n\n",
                text,
                count=1,
                flags=re.MULTILINE | re.DOTALL,
            )
        return text

    monkeypatch.setattr(verification, "read", edited)
    failed = [o.item_id for o in verification.run_static_checks() if o.status == "FAIL"]

    assert failed == ["52"]


def test_the_changelog_phase_08_heading_decides_check_52(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = verification.read

    def edited(path: str, root: Path = verification.REPO_ROOT) -> str:
        text = original(path, root)
        if path == "CHANGELOG.md":
            old = "### Phase 8 — UI/UX redesign and visual dogfooding"
            assert old in text
            return text.replace(old, "### Phase 8 — Draft")
        return text

    monkeypatch.setattr(verification, "read", edited)
    failed = [o.item_id for o in verification.run_static_checks() if o.status == "FAIL"]

    assert failed == ["52"]


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
