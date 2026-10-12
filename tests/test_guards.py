# tests/test_guards.py
"""Tests for the guards every test runs under: no network, and a temporary directory."""

import socket
from pathlib import Path

import pytest
from pytest_socket import SocketConnectBlockedError

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# TEST-NET-1 (RFC 5737): reserved for documentation, never routed.
NON_LOOPBACK_ADDRESS = "192.0.2.1"


def test_connection_to_a_non_loopback_address_is_blocked() -> None:
    # pytest-socket warns while it builds the exception, and the suite turns warnings
    # into errors, so a blocked connection in real test code fails on the warning
    # first. Expecting both proves the guard fired and keeps this test's own run quiet.
    with (
        pytest.warns(UserWarning, match=NON_LOOPBACK_ADDRESS),
        pytest.raises(SocketConnectBlockedError),
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client,
    ):
        client.connect((NON_LOOPBACK_ADDRESS, 80))


def test_loopback_connections_are_allowed() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=5):
            pass


def test_working_directory_is_a_temporary_directory(tmp_path: Path) -> None:
    assert Path.cwd().resolve() == tmp_path.resolve()
    assert Path.cwd().resolve() != REPOSITORY_ROOT


def test_relative_paths_cannot_reach_the_repository() -> None:
    assert not Path("pyproject.toml").exists()
    assert not Path("src").exists()
    assert not Path("cache").exists()
