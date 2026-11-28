# tests/scripts/test_release_smoke.py
"""Offline unit tests for ``scripts/release_smoke.py`` with network and subprocess replaced."""

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

import release_smoke as rs


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _make_deps(
    *,
    responses: Mapping[str, list[tuple[int, bytes]]] | None = None,
    version_output: str = "2.0.0",
    platform: str = "linux",
    commands: list[tuple[tuple[str, ...], dict[str, str]]] | None = None,
    clock: _FakeClock | None = None,
) -> tuple[rs.RuntimeDeps, list[tuple[tuple[str, ...], dict[str, str]]], _FakeClock]:
    recorded = commands if commands is not None else []
    active_clock = clock if clock is not None else _FakeClock()
    queues = {url: list(items) for url, items in (responses or {}).items()}

    def fetch_bytes(url: str) -> tuple[int, bytes]:
        rs.validate_trusted_url(url)
        items = queues.get(url)
        if not items:
            return 404, b""
        return items.pop(0) if len(items) > 1 else items[0]

    def run_command(argv: Sequence[str], cwd: Path, env: Mapping[str, str]) -> rs.CommandResult:
        del cwd
        recorded.append((tuple(argv), dict(env)))
        if len(argv) >= 2 and argv[1] == "--version":  # noqa: PLR2004
            return rs.CommandResult(0, f"{version_output}\n", "")
        if len(argv) >= 2 and argv[1] == "doctor":  # noqa: PLR2004
            return rs.CommandResult(0, '{"ok": true}\n', "")
        return rs.CommandResult(0, "ok\n", "")

    def which(name: str, path: str | None) -> str | None:
        if name == "uv":
            return "/usr/bin/uv"
        if name == "node" and path and "node-bin" in path:
            return "/opt/node-bin/node"
        return None

    deps = rs.RuntimeDeps(
        fetch_bytes=fetch_bytes,
        run_command=run_command,
        sleep=active_clock.sleep,
        monotonic=active_clock.monotonic,
        platform=platform,
        which=which,
    )
    return deps, recorded, active_clock


def test_pep440_ordering_handles_dev_rc_and_final() -> None:
    ordered = [
        "1.0.0",
        "2.0.0.dev0",
        "2.0.0a1",
        "2.0.0b1",
        "2.0.0rc1",
        "2.0.0rc2",
        "2.0.0",
        "2.0.1",
    ]
    keys = [rs.parse_pep440(item) for item in ordered]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(ordered)


def test_build_smoke_env_strips_secrets_and_node(tmp_path: Path) -> None:
    node_dir = tmp_path / "node-bin"
    node_dir.mkdir()
    (node_dir / "node").write_text("", encoding="utf-8")
    good_dir = tmp_path / "usr-bin"
    good_dir.mkdir()

    deps, _, _ = _make_deps(platform="linux")
    base_env = {
        "PATH": f"{node_dir}{os.pathsep}{good_dir}",
        "ANTHROPIC_API_KEY": "synthetic-placeholder",
        "WEATHERBOT_WEB_TOKEN": "synthetic-placeholder",
        "WEATHERBOT_NTFY_TOPIC": "synthetic-placeholder",
        "UV_LOCKED": "1",
        "HOME": str(tmp_path),
    }
    smoke_env = rs.build_smoke_env(base_env, work_dir=tmp_path / "work", deps=deps)
    assert "ANTHROPIC_API_KEY" not in smoke_env
    assert "WEATHERBOT_WEB_TOKEN" not in smoke_env
    assert "WEATHERBOT_NTFY_TOPIC" not in smoke_env
    assert "UV_LOCKED" not in smoke_env
    assert str(node_dir) not in smoke_env["PATH"]
    assert str(good_dir) in smoke_env["PATH"]
    assert smoke_env["WEATHERBOT_DATA_DIR"].endswith("data")
    assert smoke_env["WEATHERBOT_CONFIG_DIR"].endswith("config")


def test_smoke_wheel_installs_with_python_and_checks_windows_winrt(tmp_path: Path) -> None:
    wheel = tmp_path / "weatherbot-2.0.0rc1-py3-none-any.whl"
    wheel.write_bytes(b"wheel-bytes")
    deps, commands, _ = _make_deps(version_output="2.0.0rc1", platform="win32")

    rs.smoke_wheel(wheel, python="3.15", base_env={"PATH": "/usr/bin"}, deps=deps)

    argvs = [argv for argv, _ in commands]
    assert argvs[0] == ("/usr/bin/uv", "tool", "install", "--python", "3.15", str(wheel.resolve()))
    assert argvs[1][1:] == ("--version",)
    assert argvs[2][1:] == ("doctor", "--offline", "--json")
    assert argvs[3][1] == str(rs.SMOKE_WEB_SCRIPT)
    assert argvs[4][1] == "-c"
    assert "XmlDocument" in argvs[4][2]


def test_smoke_testpypi_polls_verifies_sha256_and_installs_wheel_file() -> None:
    wheel_bytes = b"fake-testpypi-wheel"
    digest = hashlib.sha256(wheel_bytes).hexdigest()
    wheel_url = "https://test-files.pythonhosted.org/packages/weatherbot-2.0.0rc1-py3-none-any.whl"
    api_url = "https://test.pypi.org/pypi/weatherbot/2.0.0rc1/json"
    api_body = json.dumps(
        {
            "urls": [
                {
                    "filename": "weatherbot-2.0.0rc1-py3-none-any.whl",
                    "url": wheel_url,
                    "digests": {"sha256": digest},
                }
            ]
        }
    ).encode("utf-8")

    deps, commands, clock = _make_deps(
        responses={api_url: [(404, b""), (200, api_body)], wheel_url: [(200, wheel_bytes)]},
        version_output="2.0.0rc1",
        platform="linux",
    )

    rs.smoke_index(
        "testpypi",
        "2.0.0rc1",
        sha256=digest,
        python="3.13",
        poll_timeout_s=60.0,
        poll_interval_s=5.0,
        base_env={"PATH": "/usr/bin"},
        deps=deps,
    )
    assert clock.sleeps == [5.0]
    install_argv = commands[0][0]
    assert install_argv[:5] == ("/usr/bin/uv", "tool", "install", "--python", "3.13")
    assert install_argv[5].endswith("weatherbot-2.0.0rc1-py3-none-any.whl")
    assert len(commands) == 4  # noqa: PLR2004 - install + version + doctor + smoke_web


def test_smoke_testpypi_rejects_digest_mismatch() -> None:
    wheel_bytes = b"tampered-wheel"
    wrong_digest = "0" * 64
    listed_digest = hashlib.sha256(wheel_bytes).hexdigest()
    wheel_url = "https://test-files.pythonhosted.org/packages/weatherbot-2.0.0rc1-py3-none-any.whl"
    api_url = "https://test.pypi.org/pypi/weatherbot/2.0.0rc1/json"
    api_body = json.dumps(
        {
            "urls": [
                {
                    "filename": "weatherbot-2.0.0rc1-py3-none-any.whl",
                    "url": wheel_url,
                    "digests": {"sha256": listed_digest},
                }
            ]
        }
    ).encode("utf-8")
    deps, commands, _ = _make_deps(
        responses={api_url: [(200, api_body)], wheel_url: [(200, wheel_bytes)]},
        version_output="2.0.0rc1",
    )
    with pytest.raises(RuntimeError, match="SHA-256"):
        rs.smoke_index(
            "testpypi",
            "2.0.0rc1",
            sha256=wrong_digest,
            base_env={"PATH": "/usr/bin"},
            deps=deps,
        )
    assert commands == []


def test_smoke_pypi_runs_both_uv_tool_and_pip_install() -> None:
    digest = "a" * 64
    wheel_url = "https://files.pythonhosted.org/packages/weatherbot-2.0.0-py3-none-any.whl"
    api_url = "https://pypi.org/pypi/weatherbot/2.0.0/json"
    api_body = json.dumps(
        {
            "urls": [
                {
                    "filename": "weatherbot-2.0.0-py3-none-any.whl",
                    "url": wheel_url,
                    "digests": {"sha256": digest},
                }
            ]
        }
    ).encode("utf-8")
    deps, commands, _ = _make_deps(
        responses={api_url: [(200, api_body)]},
        version_output="2.0.0",
        platform="linux",
    )

    rs.smoke_index(
        "pypi",
        "2.0.0",
        sha256=digest,
        python="3.15",
        base_env={"PATH": "/usr/bin"},
        deps=deps,
    )
    argvs = [argv for argv, _ in commands]
    assert ("/usr/bin/uv", "tool", "install", "--python", "3.15", "weatherbot==2.0.0") in argvs
    assert any(argv[:5] == ("/usr/bin/uv", "venv", "--seed", "--python", "3.15") for argv in argvs)
    assert any(argv[1:] == ("-m", "pip", "install", "weatherbot==2.0.0") for argv in argvs)


def test_smoke_latest_skips_cleanly_while_pypi_is_below_min_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    api_url = "https://pypi.org/pypi/weatherbot/json"
    api_body = json.dumps({"info": {"version": "1.0.0"}}).encode("utf-8")
    deps, commands, _ = _make_deps(responses={api_url: [(200, api_body)]})

    installed = rs.smoke_latest(min_version="2.0.0", base_env={"PATH": "/usr/bin"}, deps=deps)
    assert installed is False
    assert commands == []
    assert "no release at or above 2.0.0 on PyPI" in capsys.readouterr().out


def test_smoke_latest_installs_unpinned_when_at_or_above_min_version() -> None:
    api_url = "https://pypi.org/pypi/weatherbot/json"
    api_body = json.dumps({"info": {"version": "2.0.0"}}).encode("utf-8")
    deps, commands, _ = _make_deps(
        responses={api_url: [(200, api_body)]},
        version_output="2.0.0",
    )

    installed = rs.smoke_latest(min_version="2.0.0", base_env={"PATH": "/usr/bin"}, deps=deps)
    assert installed is True
    assert commands[0][0] == ("/usr/bin/uv", "tool", "install", "weatherbot")


def test_untrusted_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="untrusted URL"):
        rs.validate_trusted_url("https://evil.example/weatherbot-2.0.0-py3-none-any.whl")
    with pytest.raises(ValueError, match="untrusted URL"):
        rs.validate_trusted_url("http://pypi.org/pypi/weatherbot/json")


def test_poll_times_out_when_version_never_appears() -> None:
    deps, _, clock = _make_deps(responses={})
    with pytest.raises(RuntimeError, match="timed out"):
        rs.poll_index_for_wheel("pypi", "2.0.0", deps=deps, timeout_s=20.0, interval_s=10.0)
    assert clock.sleeps == [10.0, 10.0]
