# scripts/release_smoke.py
"""Install a Weatherbot distribution in an isolated environment and run release smokes.

Standard library only so it can run on clean CI runners without project dependencies.
Supports three distribution sources:

- ``--wheel PATH``: install a built wheel through ``uv tool install``.
- ``--index testpypi --version V [--sha256 HEX]``: poll TestPyPI's JSON API up to 10 minutes,
  download the ``py3-none-any`` wheel, check its SHA-256, and install that file so every
  dependency resolves from PyPI rather than TestPyPI.
- ``--index pypi --version V [--sha256 HEX]``: poll PyPI's JSON API up to 10 minutes, then
  install ``weatherbot==V`` twice — once through ``uv tool install`` and separately through
  ``pip install`` in a fresh virtual environment — verifying both.
- ``--latest --min-version 2.0.0``: query PyPI's latest release; if below ``--min-version``,
  exit 0 without installing; otherwise run an unpinned ``uv tool install weatherbot`` and
  verify it.

Every install runs in temporary tool, data, and configuration directories with ``node``
removed from ``PATH`` and every ``ANTHROPIC_*`` and ``WEATHERBOT_*`` variable cleared.
Verification checks ``weatherbot --version``, ``weatherbot doctor --offline --json``,
``scripts/smoke_installed_web.py``, and (on Windows) importing pywinrt 4 and loading the
toast channel's XML into ``XmlDocument`` without showing a toast.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess  # fixed argument lists, never a shell  # nosec B404
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, cast
from urllib.parse import urlsplit

type IndexName = Literal["pypi", "testpypi"]

PACKAGE_NAME: Final = "weatherbot"
SMOKE_WEB_SCRIPT: Final = Path(__file__).resolve().with_name("smoke_installed_web.py")
DEFAULT_POLL_TIMEOUT_S: Final = 600.0
DEFAULT_POLL_INTERVAL_S: Final = 10.0
HTTP_TIMEOUT_S: Final = 30.0
HTTP_OK: Final = 200
HTTP_NOT_FOUND: Final = 404

TRUSTED_HOSTS: Final = frozenset(
    {
        "pypi.org",
        "test.pypi.org",
        "files.pythonhosted.org",
        "test-files.pythonhosted.org",
    }
)
INDEX_API_BASE: Final[dict[IndexName, str]] = {
    "pypi": "https://pypi.org/pypi",
    "testpypi": "https://test.pypi.org/pypi",
}
WHEEL_FILENAME_RE: Final = re.compile(r"^weatherbot-(?P<version>[^-]+)-py3-none-any\.whl$")
PEP440_RE: Final = re.compile(
    r"^(?:(?P<epoch>\d+)!)?"
    r"(?P<release>\d+(?:\.\d+)*)"
    r"(?:(?P<pre_l>a|b|rc)(?P<pre_n>\d+))?"
    r"(?:\.post(?P<post>\d+))?"
    r"(?:\.dev(?P<dev>\d+))?$"
)
PRE_RANK: Final[dict[str, int]] = {"a": 0, "b": 1, "rc": 2}
WINDOWS_TOAST_XML_CHECK: Final = (
    "from datetime import UTC, datetime; "
    "from winrt.windows.data.xml.dom import XmlDocument; "
    "import winrt.windows.ui.notifications; "
    "from weatherbot.services.notifications import StoredNotification; "
    "from weatherbot.services.toast import toast_xml; "
    "note = StoredNotification("
    "id=1, location_name=None, location_time_zone=None, assessment_id=None, cycle_id=None, "
    "kind='test', level=None, escalation=False, "
    "title='Weatherbot smoke', body=('XML load check.',), created_at=datetime.now(UTC)); "
    "xml = toast_xml(note); "
    "doc = XmlDocument(); "
    "doc.load_xml(xml); "
    "assert 'ToastGeneric' in doc.get_xml(), 'unexpected toast XML'"
)


@dataclass(frozen=True)
class CommandResult:
    """Captured result from one subprocess call."""

    returncode: int
    stdout: str
    stderr: str


type FetchBytes = Callable[[str], tuple[int, bytes]]
type RunCommand = Callable[[Sequence[str], Path, Mapping[str, str]], CommandResult]
type SleepFn = Callable[[float], None]
type MonotonicFn = Callable[[], float]
type WhichFn = Callable[[str, str | None], str | None]


@dataclass(frozen=True)
class RuntimeDeps:
    """Injectable external dependencies for offline unit testing."""

    fetch_bytes: FetchBytes
    run_command: RunCommand
    sleep: SleepFn = time.sleep
    monotonic: MonotonicFn = time.monotonic
    platform: str = sys.platform
    which: WhichFn = lambda name, path: shutil.which(name, path=path)


def parse_pep440(raw: str) -> tuple[int, tuple[int, ...], int, int, int, int, int]:
    """Return a PEP 440 sort key for ``raw`` using the standard library alone.

    Ordering matches PEP 440: ``1.0.0 < 2.0.0.dev0 < 2.0.0a1 < 2.0.0b1 < 2.0.0rc1 < 2.0.0``.
    """
    match = PEP440_RE.fullmatch(raw.strip())
    if match is None:
        message = f"unsupported PEP 440 version: {raw!r}"
        raise ValueError(message)
    epoch = int(match["epoch"]) if match["epoch"] is not None else 0
    release = tuple(int(part) for part in match["release"].split("."))
    pre_l = match["pre_l"]
    pre_n = int(match["pre_n"]) if match["pre_n"] is not None else 0
    post_raw = match["post"]
    dev_raw = match["dev"]

    if pre_l is None and post_raw is None and dev_raw is not None:
        # Pure dev release of a final release sorts before pre-releases (2.0.0.dev0 < 2.0.0rc1).
        stage = 0
        pre_kind = -1
        pre_num = 0
        post_num = -1
        dev_stage = 0
        dev_num = int(dev_raw)
    elif pre_l is not None:
        stage = 1
        pre_kind = PRE_RANK[pre_l]
        pre_num = pre_n
        post_num = int(post_raw) if post_raw is not None else -1
        dev_stage = 0 if dev_raw is not None else 1
        dev_num = int(dev_raw) if dev_raw is not None else 0
    elif post_raw is not None:
        stage = 3
        pre_kind = 0
        pre_num = 0
        post_num = int(post_raw)
        dev_stage = 0 if dev_raw is not None else 1
        dev_num = int(dev_raw) if dev_raw is not None else 0
    else:
        stage = 2
        pre_kind = 0
        pre_num = 0
        post_num = 0
        dev_stage = 1
        dev_num = 0
    return (epoch, release, stage, pre_kind, pre_num, post_num, dev_stage * 1_000_000_000 + dev_num)


def validate_trusted_url(url: str) -> str:
    """Require an HTTPS URL on one of the official PyPI / TestPyPI hosts."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in TRUSTED_HOSTS:
        message = f"refusing untrusted URL: {url!r}"
        raise ValueError(message)
    return url


def _default_fetch_bytes(url: str) -> tuple[int, bytes]:
    safe_url = validate_trusted_url(url)
    request = urllib.request.Request(  # noqa: S310 - scheme and host verified by validate_trusted_url
        safe_url,
        headers={"Accept": "application/json, application/octet-stream"},
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - scheme and host verified above  # nosec B310
            request, timeout=HTTP_TIMEOUT_S
        ) as response:
            status = int(getattr(response, "status", HTTP_OK))
            return status, bytes(response.read())
    except urllib.error.HTTPError as error:
        return int(error.code), b""


def _default_run_command(argv: Sequence[str], cwd: Path, env: Mapping[str, str]) -> CommandResult:
    completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell  # nosec B603
        list(argv),
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def default_deps() -> RuntimeDeps:
    """Build production runtime dependencies."""
    return RuntimeDeps(fetch_bytes=_default_fetch_bytes, run_command=_default_run_command)


def _dir_contains_node(directory: Path, *, windows: bool) -> bool:
    if not directory.is_dir():
        return False
    names = ("node.exe", "node.cmd", "node.bat", "node") if windows else ("node",)
    return any((directory / name).is_file() for name in names)


def scrub_path_without_node(raw_path: str, *, windows: bool) -> str:
    """Remove every ``PATH`` directory that holds a ``node`` executable."""
    kept: list[str] = []
    for entry in raw_path.split(os.pathsep):
        cleaned = entry.strip()
        if not cleaned:
            continue
        if _dir_contains_node(Path(cleaned), windows=windows):
            continue
        kept.append(cleaned)
    return os.pathsep.join(kept)


def build_smoke_env(
    base_env: Mapping[str, str],
    *,
    work_dir: Path,
    deps: RuntimeDeps,
    prepend_bin: Path | None = None,
) -> dict[str, str]:
    """Construct an isolated child environment with secrets and ``node`` stripped."""
    windows = deps.platform == "win32"
    env: dict[str, str] = {}
    for key, value in base_env.items():
        upper = key.upper()
        if upper.startswith(("ANTHROPIC_", "WEATHERBOT_")):
            continue
        if upper in {
            "UV_LOCKED",
            "VIRTUAL_ENV",
            "UV_PROJECT_ENVIRONMENT",
            "PYTHONPATH",
            "UV_PYTHON",
        }:
            continue
        env[key] = value

    path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
    scrubbed = scrub_path_without_node(env.get(path_key, ""), windows=windows)
    if prepend_bin is not None:
        scrubbed = f"{prepend_bin}{os.pathsep}{scrubbed}" if scrubbed else str(prepend_bin)
    if deps.which("node", scrubbed) is not None:
        message = "node is still reachable on PATH after scrubbing"
        raise RuntimeError(message)
    env[path_key] = scrubbed

    data_dir = work_dir / "data"
    config_dir = work_dir / "config"
    tool_dir = work_dir / "uv-tools"
    tool_bin_dir = work_dir / "uv-bin"
    for directory in (data_dir, config_dir, tool_dir, tool_bin_dir):
        directory.mkdir(parents=True, exist_ok=True)

    env["UV_TOOL_DIR"] = str(tool_dir)
    env["UV_TOOL_BIN_DIR"] = str(tool_bin_dir)
    env["WEATHERBOT_DATA_DIR"] = str(data_dir)
    env["WEATHERBOT_CONFIG_DIR"] = str(config_dir)
    return env


def _require_ok(result: CommandResult, description: str) -> CommandResult:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        message = f"{description} failed (exit {result.returncode}): {detail}"
        raise RuntimeError(message)
    return result


def _tool_paths(work_dir: Path, *, windows: bool) -> tuple[Path, Path]:
    """Return ``(weatherbot_exe, tool_python)`` for a ``uv tool install`` into ``work_dir``."""
    scripts_dir = "Scripts" if windows else "bin"
    exe_suffix = ".exe" if windows else ""
    weatherbot_exe = work_dir / "uv-bin" / f"weatherbot{exe_suffix}"
    tool_python = work_dir / "uv-tools" / PACKAGE_NAME / scripts_dir / f"python{exe_suffix}"
    return weatherbot_exe, tool_python


def _venv_paths(venv_dir: Path, *, windows: bool) -> tuple[Path, Path]:
    """Return ``(weatherbot_exe, venv_python)`` for a fresh virtual environment."""
    scripts_dir = "Scripts" if windows else "bin"
    exe_suffix = ".exe" if windows else ""
    return (
        venv_dir / scripts_dir / f"weatherbot{exe_suffix}",
        venv_dir / scripts_dir / f"python{exe_suffix}",
    )


@dataclass(frozen=True)
class _InstallContext:
    """Shared installation context for uv/pip release smoke helpers."""

    uv_exe: str
    python: str | None
    base_env: Mapping[str, str]
    deps: RuntimeDeps


@dataclass(frozen=True)
class _InstalledTarget:
    """Resolved executables and directory for one installed Weatherbot copy."""

    label: str
    weatherbot_exe: Path
    tool_python: Path
    expected_version: str
    work_dir: Path


def _verify_installed(
    target: _InstalledTarget,
    env: Mapping[str, str],
    deps: RuntimeDeps,
) -> None:
    """Run all release smoke assertions against one installed Weatherbot environment."""
    version_res = _require_ok(
        deps.run_command([str(target.weatherbot_exe), "--version"], target.work_dir, env),
        f"{target.label}: weatherbot --version",
    )
    actual_version = version_res.stdout.strip()
    if actual_version != target.expected_version:
        message = (
            f"{target.label}: version {actual_version!r} != expected {target.expected_version!r}"
        )
        raise RuntimeError(message)

    doctor_res = _require_ok(
        deps.run_command(
            [str(target.weatherbot_exe), "doctor", "--offline", "--json"], target.work_dir, env
        ),
        f"{target.label}: weatherbot doctor --offline --json",
    )
    try:
        doctor_doc: object = json.loads(doctor_res.stdout)
    except json.JSONDecodeError as error:
        message = f"{target.label}: doctor --offline --json returned invalid JSON"
        raise RuntimeError(message) from error
    if not isinstance(doctor_doc, dict):
        message = f"{target.label}: doctor --offline --json did not return a JSON object"
        raise TypeError(message)

    _require_ok(
        deps.run_command([str(target.tool_python), str(SMOKE_WEB_SCRIPT)], target.work_dir, env),
        f"{target.label}: smoke_installed_web.py",
    )

    if deps.platform == "win32":
        _require_ok(
            deps.run_command(
                [str(target.tool_python), "-c", WINDOWS_TOAST_XML_CHECK], target.work_dir, env
            ),
            f"{target.label}: Windows pywinrt toast XML check",
        )
    print(f"OK {target.label} weatherbot=={actual_version}")


def _find_wheel_entry(payload: dict[str, object], version: str) -> tuple[str, str, str] | None:
    """Return ``(filename, url, sha256)`` for ``weatherbot-<version>-py3-none-any.whl``."""
    wanted_filename = f"{PACKAGE_NAME}-{version}-py3-none-any.whl"
    urls_raw = payload.get("urls", [])
    if not isinstance(urls_raw, list):
        return None
    for item in cast("list[object]", urls_raw):
        if not isinstance(item, dict):
            continue
        entry = cast("dict[str, object]", item)
        if entry.get("filename") != wanted_filename:
            continue
        url = entry.get("url")
        digests = entry.get("digests")
        if not isinstance(url, str) or not isinstance(digests, dict):
            continue
        sha256 = cast("dict[str, object]", digests).get("sha256")
        if isinstance(sha256, str) and len(sha256) == 64:  # noqa: PLR2004 - SHA-256 hex length
            return wanted_filename, validate_trusted_url(url), sha256.lower()
    return None


def poll_index_for_wheel(
    index: IndexName,
    version: str,
    *,
    deps: RuntimeDeps,
    timeout_s: float = DEFAULT_POLL_TIMEOUT_S,
    interval_s: float = DEFAULT_POLL_INTERVAL_S,
) -> tuple[str, str, str]:
    """Poll ``index`` JSON API until ``weatherbot-<version>-py3-none-any.whl`` is listed."""
    api_url = validate_trusted_url(f"{INDEX_API_BASE[index]}/{PACKAGE_NAME}/{version}/json")
    deadline = deps.monotonic() + timeout_s
    last_reason = "not yet queried"
    while True:
        status, body = deps.fetch_bytes(api_url)
        if status == HTTP_OK:
            try:
                parsed: object = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                last_reason = f"malformed JSON ({type(error).__name__})"
            else:
                if isinstance(parsed, dict):
                    found = _find_wheel_entry(cast("dict[str, object]", parsed), version)
                    if found is not None:
                        return found
                    last_reason = "wheel not listed yet"
                else:
                    last_reason = "JSON root is not an object"
        elif status == HTTP_NOT_FOUND:
            last_reason = "HTTP 404"
        else:
            last_reason = f"HTTP {status}"

        if deps.monotonic() >= deadline:
            message = (
                f"timed out after {timeout_s:.0f}s waiting for {PACKAGE_NAME}=={version} "
                f"on {index} ({last_reason})"
            )
            raise RuntimeError(message)
        deps.sleep(interval_s)


def _resolve_uv(base_env: Mapping[str, str], deps: RuntimeDeps) -> str:
    path_key = next((k for k in base_env if k.upper() == "PATH"), "PATH")
    uv_exe = deps.which("uv", base_env.get(path_key))
    if uv_exe is None:
        message = "`uv` executable not found on PATH"
        raise FileNotFoundError(message)
    return uv_exe


def _uv_tool_install_and_verify(
    ctx: _InstallContext,
    *,
    label: str,
    target: str,
    expected_version: str,
) -> None:
    windows = ctx.deps.platform == "win32"
    with tempfile.TemporaryDirectory(
        prefix="weatherbot-release-smoke-",
        ignore_cleanup_errors=windows,
    ) as tmp:
        work_dir = Path(tmp)
        env = build_smoke_env(ctx.base_env, work_dir=work_dir, deps=ctx.deps)
        install_argv = [ctx.uv_exe, "tool", "install"]
        if ctx.python is not None:
            install_argv.extend(["--python", ctx.python])
        install_argv.append(target)
        _require_ok(
            ctx.deps.run_command(install_argv, work_dir, env),
            f"{label}: uv tool install",
        )
        weatherbot_exe, tool_python = _tool_paths(work_dir, windows=windows)
        verify_env = build_smoke_env(
            ctx.base_env, work_dir=work_dir, deps=ctx.deps, prepend_bin=weatherbot_exe.parent
        )
        _verify_installed(
            _InstalledTarget(label, weatherbot_exe, tool_python, expected_version, work_dir),
            verify_env,
            ctx.deps,
        )


def _pip_install_and_verify(
    ctx: _InstallContext,
    *,
    label: str,
    version: str,
) -> None:
    windows = ctx.deps.platform == "win32"
    with tempfile.TemporaryDirectory(
        prefix="weatherbot-pip-smoke-",
        ignore_cleanup_errors=windows,
    ) as tmp:
        work_dir = Path(tmp)
        venv_dir = work_dir / "venv"
        env = build_smoke_env(ctx.base_env, work_dir=work_dir, deps=ctx.deps)
        venv_argv = [ctx.uv_exe, "venv", "--seed"]
        if ctx.python is not None:
            venv_argv.extend(["--python", ctx.python])
        venv_argv.append(str(venv_dir))
        _require_ok(ctx.deps.run_command(venv_argv, work_dir, env), f"{label}: uv venv --seed")

        weatherbot_exe, venv_python = _venv_paths(venv_dir, windows=windows)
        _require_ok(
            ctx.deps.run_command(
                [str(venv_python), "-m", "pip", "install", f"{PACKAGE_NAME}=={version}"],
                work_dir,
                env,
            ),
            f"{label}: pip install",
        )
        verify_env = build_smoke_env(
            ctx.base_env, work_dir=work_dir, deps=ctx.deps, prepend_bin=weatherbot_exe.parent
        )
        _verify_installed(
            _InstalledTarget(label, weatherbot_exe, venv_python, version, work_dir),
            verify_env,
            ctx.deps,
        )


def smoke_wheel(
    wheel_path: Path,
    *,
    version: str | None = None,
    python: str | None = None,
    base_env: Mapping[str, str] | None = None,
    deps: RuntimeDeps | None = None,
) -> None:
    """Install a local wheel with ``uv tool install`` and verify it."""
    active_deps = deps or default_deps()
    env = base_env if base_env is not None else os.environ
    resolved = wheel_path.resolve()
    if not resolved.is_file():
        message = f"wheel file not found: {resolved}"
        raise FileNotFoundError(message)
    expected_version = version
    if expected_version is None:
        match = WHEEL_FILENAME_RE.fullmatch(resolved.name)
        if match is None:
            message = f"cannot infer version from wheel filename {resolved.name!r}; pass --version"
            raise ValueError(message)
        expected_version = match["version"]
    ctx = _InstallContext(_resolve_uv(env, active_deps), python, env, active_deps)
    _uv_tool_install_and_verify(
        ctx,
        label="wheel (uv tool)",
        target=str(resolved),
        expected_version=expected_version,
    )


def smoke_index(  # noqa: PLR0913 - explicit release-smoke parameters
    index: IndexName,
    version: str,
    *,
    sha256: str | None = None,
    python: str | None = None,
    poll_timeout_s: float = DEFAULT_POLL_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    base_env: Mapping[str, str] | None = None,
    deps: RuntimeDeps | None = None,
) -> None:
    """Poll ``index`` for ``version`` and run the published-package smoke checks."""
    active_deps = deps or default_deps()
    env = base_env if base_env is not None else os.environ
    ctx = _InstallContext(_resolve_uv(env, active_deps), python, env, active_deps)
    filename, wheel_url, index_sha256 = poll_index_for_wheel(
        index,
        version,
        deps=active_deps,
        timeout_s=poll_timeout_s,
        interval_s=poll_interval_s,
    )
    if sha256 is not None and index_sha256 != sha256.lower():
        message = f"{index}: listed wheel SHA-256 {index_sha256} != expected {sha256.lower()}"
        raise RuntimeError(message)

    if index == "testpypi":
        status, wheel_bytes = active_deps.fetch_bytes(wheel_url)
        if status != HTTP_OK:
            message = f"testpypi: failed to download wheel ({status}) from {wheel_url}"
            raise RuntimeError(message)
        actual_sha256 = hashlib.sha256(wheel_bytes).hexdigest()
        if actual_sha256 != index_sha256:
            message = f"testpypi: downloaded wheel SHA-256 {actual_sha256} != index {index_sha256}"
            raise RuntimeError(message)
        if sha256 is not None and actual_sha256 != sha256.lower():
            message = (
                f"testpypi: downloaded wheel SHA-256 {actual_sha256} != expected {sha256.lower()}"
            )
            raise RuntimeError(message)
        with tempfile.TemporaryDirectory(prefix="weatherbot-testpypi-wheel-") as dl_tmp:
            wheel_file = Path(dl_tmp) / filename
            wheel_file.write_bytes(wheel_bytes)
            _uv_tool_install_and_verify(
                ctx,
                label="testpypi wheel (uv tool, PyPI deps)",
                target=str(wheel_file),
                expected_version=version,
            )
        return

    _uv_tool_install_and_verify(
        ctx,
        label="pypi (uv tool)",
        target=f"{PACKAGE_NAME}=={version}",
        expected_version=version,
    )
    _pip_install_and_verify(ctx, label="pypi (pip)", version=version)


def smoke_latest(
    *,
    min_version: str = "2.0.0",
    python: str | None = None,
    base_env: Mapping[str, str] | None = None,
    deps: RuntimeDeps | None = None,
) -> bool:
    """Install the unpinned PyPI release when it is at or above ``min_version``.

    Returns:
        ``True`` if a release at or above ``min_version`` was installed and verified,
        ``False`` when PyPI still holds only an older release.
    """
    active_deps = deps or default_deps()
    env = base_env if base_env is not None else os.environ
    api_url = validate_trusted_url(f"{INDEX_API_BASE['pypi']}/{PACKAGE_NAME}/json")
    status, body = active_deps.fetch_bytes(api_url)
    if status != HTTP_OK:
        message = f"pypi: failed to query {PACKAGE_NAME} JSON ({status})"
        raise RuntimeError(message)
    parsed = cast("dict[str, object]", json.loads(body.decode("utf-8")))
    info = cast("dict[str, object]", parsed["info"])
    latest = str(info["version"])
    if parse_pep440(latest) < parse_pep440(min_version):
        print(f"no release at or above {min_version} on PyPI (latest is {latest})")
        return False
    ctx = _InstallContext(_resolve_uv(env, active_deps), python, env, active_deps)
    _uv_tool_install_and_verify(
        ctx,
        label="pypi latest (uv tool)",
        target=PACKAGE_NAME,
        expected_version=latest,
    )
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``scripts/release_smoke.py``."""
    parser = argparse.ArgumentParser(
        description="Install Weatherbot in an isolated environment and run release smokes."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--wheel", type=Path, help="Path to a built wheel file.")
    source.add_argument(
        "--index",
        choices=("pypi", "testpypi"),
        help="Install a published release from PyPI or TestPyPI.",
    )
    source.add_argument(
        "--latest",
        action="store_true",
        help="Install the newest unpinned PyPI release when >= --min-version.",
    )
    parser.add_argument("--version", help="Expected release version (required with --index).")
    parser.add_argument("--sha256", help="Expected wheel SHA-256 digest (hex).")
    parser.add_argument("--min-version", default="2.0.0", help="Minimum version for --latest.")
    parser.add_argument("--python", help="Target Python version (e.g. 3.13 or 3.15).")
    parser.add_argument(
        "--poll-timeout",
        type=float,
        default=DEFAULT_POLL_TIMEOUT_S,
        help="Seconds to wait for --index JSON to list the version (default: 600).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_S,
        help="Seconds between --index poll attempts (default: 10).",
    )
    args = parser.parse_args(argv)

    if args.index is not None and not args.version:
        parser.error("--index requires --version")

    try:
        if args.wheel is not None:
            smoke_wheel(args.wheel, version=args.version, python=args.python)
        elif args.index is not None:
            smoke_index(
                cast("IndexName", args.index),
                args.version,
                sha256=args.sha256,
                python=args.python,
                poll_timeout_s=args.poll_timeout,
                poll_interval_s=args.poll_interval,
            )
        else:
            smoke_latest(min_version=args.min_version, python=args.python)
    except (RuntimeError, TypeError, ValueError, FileNotFoundError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
