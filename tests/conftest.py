# tests/conftest.py
"""Shared fixtures and guards for the whole test suite."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def run_in_temporary_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test in its own temporary working directory.

    A relative path in the code under test then resolves inside ``tmp_path`` and can
    never read or write the repository. This guards against the failure that destroyed
    version 1's recorded responses: tests that cleared a cache directory addressed by a
    relative path while the working directory was the repository root.

    Args:
        tmp_path: The test's own temporary directory.
        monkeypatch: Used to change the working directory for the test's duration.

    """
    monkeypatch.chdir(tmp_path)
