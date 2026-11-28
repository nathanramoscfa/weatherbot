# tests/test_cli.py
"""Tests for the ``weatherbot`` command-line entry point."""

import re
import subprocess
import sys
from importlib.metadata import version

from typer.testing import CliRunner

import weatherbot
from weatherbot.cli import app

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def test_version_matches_the_project_version() -> None:
    expected = version("weatherbot")
    assert expected
    assert weatherbot.__version__ == expected


def test_version_option_prints_the_version_alone() -> None:
    expected = version("weatherbot")
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout == f"{expected}\n"


def test_help_works() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    # Rich styles the help text when the runner forces color (GitHub Actions does).
    assert "--version" in ANSI_ESCAPE.sub("", result.stdout)


def test_module_entry_point_prints_the_version() -> None:
    expected = version("weatherbot")
    completed = subprocess.run(
        [sys.executable, "-m", "weatherbot", "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == expected
