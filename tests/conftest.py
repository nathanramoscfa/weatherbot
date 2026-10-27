# tests/conftest.py
"""Shared fixtures and guards for the whole test suite."""

import os
from pathlib import Path
from typing import Final

import pytest
from hypothesis import settings

import fetch_replay_corpus as corpus
from weatherbot.services.replay import ReplayCorpus

# Development-tool variables, read by scripts and the corpus tests, never by the
# application: the personal-data denylist's path and the replay-corpus cache. Every other
# WEATHERBOT_* variable is cleared for each test.
TOOL_VARIABLES: Final = frozenset({"WEATHERBOT_DENYLIST", "WEATHERBOT_CORPUS_CACHE"})

# Every property test runs under one profile: derandomized, so each run tries the same
# examples; with no example database, so a run writes nothing; and with no deadline, so a
# slow runner never fails a correct test.
HYPOTHESIS_PROFILE: Final = "weatherbot"
settings.register_profile(HYPOTHESIS_PROFILE, derandomize=True, database=None, deadline=None)
settings.load_profile(HYPOTHESIS_PROFILE)


@pytest.fixture(scope="session")
def full_replay_corpus(tmp_path_factory: pytest.TempPathFactory) -> ReplayCorpus:
    """Share one verified conversion; consumers stream its snapshots to bound memory."""
    cache = Path(os.environ.get("WEATHERBOT_CORPUS_CACHE", corpus.DEFAULT_CACHE))
    if not cache.is_dir():
        pytest.skip("replay cache absent; run fetch explicitly")
    out = tmp_path_factory.mktemp("full-replay")
    corpus.convert_full(corpus.load_manifest(), cache, out)
    return ReplayCorpus.open(out)


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


@pytest.fixture(autouse=True)
def isolate_application_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the configuration and data directories under ``tmp_path`` for every test.

    No test can then read the operator's ``weatherbot.toml`` or open the operator's
    database, and no setting from the developer's environment leaks into a test. The
    toast is turned off, so no test, the live suite included, shows a real toast; the
    ``desktop`` tests turn it back on.

    Args:
        tmp_path: The test's own temporary directory.
        monkeypatch: Used to set and clear the environment for the test's duration.
    """
    for name in list(os.environ):
        if name.upper().startswith("WEATHERBOT_") and name.upper() not in TOOL_VARIABLES:
            monkeypatch.delenv(name)
    monkeypatch.setenv("WEATHERBOT_CONFIG_DIR", str(tmp_path / "weatherbot-config"))
    monkeypatch.setenv("WEATHERBOT_DATA_DIR", str(tmp_path / "weatherbot-data"))
    monkeypatch.setenv("WEATHERBOT_NOTIFICATIONS_TOAST", "false")
    monkeypatch.setenv("WEATHERBOT_WEB_PORT", "0")
