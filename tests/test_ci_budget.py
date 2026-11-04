# tests/test_ci_budget.py
"""Tests for the Phase 7 Step 1 CI test budget, xdist configuration, and worker guards."""

import os
import re
import shlex
import socket
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Final

import pytest
from pytest_socket import SocketConnectBlockedError

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
CI_WORKFLOW: Final = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT: Final = REPOSITORY_ROOT / "pyproject.toml"
WORKER_ASSERT_ENV: Final = "_WEATHERBOT_ASSERT_XDIST_WORKER"
TEST_NET_1_HOST: Final = "192.0.2.1"
HTTPS_PORT: Final = 443


def _test_job_block(workflow_text: str) -> str:
    match = re.search(
        r"^  test:\n.*?(?=^  [\w-]+:|\Z)",
        workflow_text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None
    return match[0]


def test_ci_test_job_runs_xdist_with_coverage_floors_and_serial_addopts() -> None:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    deps = [str(item) for item in pyproject["project"]["dependencies"]]
    dev_deps = [str(item) for item in pyproject["dependency-groups"]["dev"]]
    plan_deps = [str(item) for item in pyproject["dependency-groups"]["planning"]]

    assert any(dep.startswith("pytest-xdist>=") for dep in dev_deps)
    assert not any(dep.startswith(("pytest-xdist", "execnet")) for dep in deps)
    assert not any(dep.startswith(("pytest-xdist", "execnet")) for dep in plan_deps)

    addopts = str(pyproject["tool"]["pytest"]["ini_options"]["addopts"])
    addopts_args = shlex.split(addopts)
    assert "--allow-hosts=127.0.0.1,::1" in addopts_args
    assert not any(arg == "-n" or arg.startswith(("-n", "--numprocesses")) for arg in addopts_args)

    test_job = _test_job_block(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert "timeout-minutes: 40" in test_job
    assert "COVERAGE_FILE: ${{ runner.temp }}/.coverage" in test_job
    for needle in (
        "uv run pytest",
        "-n auto",
        "--cov=weatherbot.engine",
        "--cov=weatherbot.services.policy",
        "--cov=weatherbot.services.ai.context",
        "--cov=weatherbot.services.ai.validate",
        "--cov-branch",
        "--cov-report=term-missing:skip-covered",
        "--cov-fail-under=90",
        '--include="*/services/policy.py"',
        '--include="*/services/ai/context.py"',
        '--include="*/services/ai/validate.py"',
    ):
        assert needle in test_job


def test_socket_and_cwd_guards_hold_in_worker_process(tmp_path: Path) -> None:
    if os.environ.get(WORKER_ASSERT_ENV) == "1":
        assert os.environ.get("PYTEST_XDIST_WORKER", "").startswith("gw")

    assert Path.cwd() == tmp_path
    assert Path.cwd() != REPOSITORY_ROOT

    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client,
        pytest.warns(UserWarning, match=r"socket\.socket\.connect"),
        pytest.raises(SocketConnectBlockedError),
    ):
        client.connect((TEST_NET_1_HOST, HTTPS_PORT))


def test_xdist_worker_refuses_non_loopback_socket() -> None:
    result = subprocess.run(  # noqa: S603 - fixed interpreter and test target, no shell
        [
            sys.executable,
            "-m",
            "pytest",
            "-n",
            "1",
            f"{Path(__file__).resolve()}::test_socket_and_cwd_guards_hold_in_worker_process",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
        env={**os.environ, WORKER_ASSERT_ENV: "1"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
