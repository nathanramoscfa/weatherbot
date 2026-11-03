# tests/test_phase06_verification.py
"""Phase 6 verifier integration and failure-reporting regressions."""

import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

import verify_phase06 as verification

ROOT = Path(__file__).resolve().parents[1]
STATIC_COUNT = 51
V_ROWS = 28
USAGE_ERROR = 2


def test_phase_06_roadmap_and_qa_findings_exist() -> None:
    assert (ROOT / "docs/roadmap/phase06-roadmap.md").is_file()
    assert (ROOT / "docs/phase06-qa-findings.md").is_file()


def test_fast_verification_passes_all_static_checks_within_thirty_seconds() -> None:
    result = subprocess.run(  # noqa: S603 - fixed script path and arguments, no shell
        [sys.executable, str(ROOT / "scripts/verify_phase06.py"), "--fast"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(re.findall(r"^\[PASS\] \d{2}: ", result.stdout, re.MULTILINE)) == STATIC_COUNT


def test_phase_verify_workflow_includes_phase_06() -> None:
    assert verification.check_50_matrix_includes_06_and_node_setup()


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
                verification.Outcome("V7.4", "security", status),
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
        ("--fast", "--ai"),
        ("--all", "--ai"),
        ("--post", "--ai"),
    ):
        with pytest.raises(SystemExit) as error:
            verification.parse_args([left, right])
        assert error.value.code == USAGE_ERROR


def test_junit_selection_must_match_at_least_one_test() -> None:
    suite = verification.Suite(tests={"tests.ai.test_ai_settings.test_a": "PASS"})

    status, detail = verification.evaluate_evidence(
        verification.Select("tests.ai.test_ai_settings", "tests.ai.test_ai_pricing"), suite
    )

    assert (status, detail) == ("FAIL", "no tests matched tests.ai.test_ai_pricing")


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
        tests={f"tests.ai.test_ai_eval.test_{n}": s for n, s in enumerate(statuses)}
    )
    status, _ = verification.evaluate_evidence(verification.Select("tests.ai.test_ai_eval"), suite)
    assert status == expected


def test_junit_statuses_are_read_from_pytest_vitest_and_playwright_reports(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        '<testsuites><testsuite name="suite">'
        '<testcase classname="tests.ai.test_ai_eval" name="test_ok"/>'
        '<testcase classname="src/ai/AiText.test.tsx" name="AiText &gt; renders literal"/>'
        '<testcase classname="ai.spec.ts" name="smoke"><failure message="x"/></testcase>'
        '<testcase classname="tests.ai" name="test_broken"><error message="x"/></testcase>'
        '<testcase classname="tests.ai" name="test_off"><skipped message="x"/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )

    assert verification.parse_junit(report) == {
        "tests.ai.test_ai_eval.test_ok": "PASS",
        "src/ai/AiText.test.tsx.AiText > renders literal": "PASS",
        "ai.spec.ts.smoke": "FAIL",
        "tests.ai.test_broken": "FAIL",
        "tests.ai.test_off": "SKIP",
    }
    assert verification.parse_junit(tmp_path / "missing.xml") == {}


def test_post_matrix_evaluates_all_twenty_eight_rows_from_recorded_evidence() -> None:
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


def test_ai_suite_refuses_in_ci_and_without_credential_without_calling_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[Sequence[str]] = []

    def forbidden_run_command(
        item_id: str,
        description: str,
        argv: Sequence[str],
        *,
        cwd: Path = verification.REPO_ROOT,
        env: Mapping[str, str] | None = None,
    ) -> verification.Outcome:
        _ = (cwd, env)
        called.append(argv)
        return verification.Outcome(item_id, description, "PASS")

    monkeypatch.setattr(verification, "run_command", forbidden_run_command)
    monkeypatch.setenv("CI", "true")
    ci_outcome = verification.ai_suite()
    assert ci_outcome.status == "FAIL"
    assert ci_outcome.detail == "refused in CI"

    def no_credential(_env: Mapping[str, str]) -> bool:
        return False

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(verification, "_user_registry_anthropic_key", lambda: None)
    monkeypatch.setattr(verification, "_has_operator_credential", no_credential)
    no_cred_outcome = verification.ai_suite()
    assert no_cred_outcome.status == "FAIL"
    assert no_cred_outcome.detail == "no Anthropic credential"
    assert called == []


@pytest.mark.parametrize(
    ("relative", "old", "new", "check"),
    [
        (
            "src/weatherbot/services/ai/pricing.py",
            'PRICES_AS_OF: Final = "2026-10-30"',
            'PRICES_AS_OF: Final = "2025-01-01"',
            "04",
        ),
        (
            "src/weatherbot/services/ai/schemas.py",
            "what_it_means_here: str",
            "what_it_means: str",
            "15",
        ),
        (
            "src/weatherbot/services/ai/chat.py",
            "MAX_TOOL_ROUNDS: Final = 6",
            "MAX_TOOL_ROUNDS: Final = 9",
            "24",
        ),
        (
            "src/weatherbot/cli/serve.py",
            "summarizer.prime",
            "summarizer.start",
            "34",
        ),
        (
            "frontend/src/api/keys.ts",
            'ai: () => invalidatableQueryKey("ai")',
            'ai: () => invalidatableQueryKey("claude")',
            "37",
        ),
        (
            "docs/AI.md",
            "## Runbook",
            "## Troubleshooting",
            "43",
        ),
        (
            "docs/phase06-qa-findings.md",
            "## Pre-ship items",
            "## Deferred items",
            "48",
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
        ("0008", "0008", True),
        ("0008", "0001", True),
        ("0007", "0008", False),
        ("unknown-revision", "0008", False),
    ],
)
def test_the_operator_database_head_must_descend_from_0008(
    head: str, ancestor: str, *, expected: bool
) -> None:
    assert verification.descends_from(head, ancestor) is expected
