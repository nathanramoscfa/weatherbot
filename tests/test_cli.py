# tests/test_cli.py
"""Tests for the ``weatherbot`` command-line entry point."""

import subprocess
import sys
from importlib.metadata import version

from typer.testing import CliRunner

import weatherbot
from weatherbot.cli import app

EXPECTED_VERSION = "2.0.0.dev0"


def test_version_matches_the_project_version() -> None:
    assert weatherbot.__version__ == EXPECTED_VERSION
    assert version("weatherbot") == EXPECTED_VERSION


def test_version_option_prints_the_version_alone() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout == f"{EXPECTED_VERSION}\n"


def test_help_works() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--version" in result.stdout


def test_module_entry_point_prints_the_version() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "weatherbot", "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == EXPECTED_VERSION
