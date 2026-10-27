# scripts/smoke_installed_web.py
"""Smoke-test an installed ``weatherbot`` wheel's web server and built frontend.

Starts ``weatherbot serve --no-open`` in a temporary working, configuration, and data
directory with ``WEATHERBOT_WEB_PORT`` set to an ephemeral loopback port,
``WEATHERBOT_NOTIFICATIONS_TOAST=false``, ``HTTPS_PROXY=http://127.0.0.1:9``, and
``NO_PROXY=127.0.0.1,localhost`` so the startup cycle's outbound requests fail fast
without leaving the machine. Polls ``/api/health`` for up to 60 seconds, verifies that
``/api/health`` reports a non-empty ``version`` and ``ui.present == True``, and verifies
that ``/`` serves the built ``index.html`` with a ``Content-Security-Policy`` header
carrying a per-response ``'nonce-...`` token.
"""

import http.client
import json
import os
import re
import shutil
import signal
import socket
import subprocess  # runs weatherbot from a fixed argument list, never a shell  # nosec B404
import sys
import tempfile
import time
from http import HTTPStatus
from pathlib import Path
from typing import Final, cast

STARTUP_TIMEOUT_S: Final = 60.0
POLL_INTERVAL_S: Final = 0.25
NONCE_DIRECTIVE_RE: Final = re.compile(r"'nonce-[A-Za-z0-9_-]{16,}'")


def _resolve_weatherbot_executable() -> str:
    """Resolve the ``weatherbot`` executable installed alongside ``sys.executable`` or on PATH."""
    venv_bin_dir = str(Path(sys.executable).parent)
    resolved_bin_dir = str(Path(sys.executable).resolve().parent)
    candidate = (
        shutil.which("weatherbot", path=venv_bin_dir)
        or shutil.which("weatherbot", path=resolved_bin_dir)
        or shutil.which("weatherbot")
    )
    if candidate is None:
        message = "smoke_installed_web: `weatherbot` executable not found"
        raise RuntimeError(message)
    return str(Path(candidate).resolve())


def _pick_free_port() -> int:
    """Pick an available loopback TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        address = sock.getsockname()
        return int(address[1])


def _http_get(port: int, path: str) -> tuple[int, dict[str, str], str]:
    """Perform a loopback HTTP GET and return ``(status, lowercase_headers, body)``."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5.0)
    try:
        conn.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
        response = conn.getresponse()
        body = response.read().decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in response.getheaders()}
        return response.status, headers, body
    finally:
        conn.close()


def _wait_for_health(
    port: int,
    process: subprocess.Popen[str],
    deadline: float,
) -> dict[str, object]:
    """Poll ``/api/health`` until it answers 200 OK or the deadline expires."""
    last_error = "no response yet"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            message = (
                f"smoke_installed_web: `weatherbot serve` exited early "
                f"with code {process.returncode}:\n{output}"
            )
            raise RuntimeError(message)
        try:
            status, _headers, body = _http_get(port, "/api/health")
            if status == HTTPStatus.OK:
                parsed: object = json.loads(body)
                if isinstance(parsed, dict):
                    return cast("dict[str, object]", parsed)
            last_error = f"HTTP {status}"
        except (OSError, http.client.HTTPException, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(POLL_INTERVAL_S)

    message = f"smoke_installed_web: timed out waiting for /api/health ({last_error})"
    raise RuntimeError(message)


def _stop_process(process: subprocess.Popen[str]) -> None:
    """Terminate the child process cleanly."""
    if process.poll() is None:
        if sys.platform == "win32":
            ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
            if isinstance(ctrl_break, int):
                process.send_signal(ctrl_break)
        else:
            process.terminate()
        try:
            process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)
    if process.stdout is not None:
        process.stdout.close()


def _verify_smoke_responses(port: int, health: dict[str, object]) -> int:
    """Validate ``/api/health`` fields and ``GET /`` response headers and body."""
    version = health.get("version")
    if not isinstance(version, str) or not version.strip():
        print(
            "smoke_installed_web: /api/health missing non-empty version",
            file=sys.stderr,
        )
        return 1

    ui_raw = health.get("ui")
    ui = cast("dict[str, object]", ui_raw) if isinstance(ui_raw, dict) else {}
    if ui.get("present") is not True:
        print(
            f"smoke_installed_web: expected ui.present=True, got {ui_raw!r}",
            file=sys.stderr,
        )
        return 1

    root_status, root_headers, root_body = _http_get(port, "/")
    if root_status != HTTPStatus.OK:
        print(
            f"smoke_installed_web: GET / returned HTTP {root_status}",
            file=sys.stderr,
        )
        return 1

    csp = root_headers.get("content-security-policy", "")
    if NONCE_DIRECTIVE_RE.search(csp) is None:
        print(
            "smoke_installed_web: GET / Content-Security-Policy missing nonce directive",
            file=sys.stderr,
        )
        return 1

    if '<div id="root"></div>' not in root_body or "__CSP_NONCE__" in root_body:
        print(
            "smoke_installed_web: GET / did not return nonce-substituted built index.html",
            file=sys.stderr,
        )
        return 1

    print(f"smoke_installed_web: ok version={version} index_sha256={ui.get('index_sha256')}")
    return 0


def main() -> int:
    """Run the installed-wheel web server smoke check."""
    executable = _resolve_weatherbot_executable()
    port = _pick_free_port()

    with tempfile.TemporaryDirectory(
        prefix="weatherbot-web-smoke-",
        ignore_cleanup_errors=sys.platform == "win32",
    ) as tmp:
        work_dir = Path(tmp)
        data_dir = work_dir / "data"
        config_dir = work_dir / "config"
        data_dir.mkdir(parents=True, exist_ok=True)
        config_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env.update(
            {
                "WEATHERBOT_DATA_DIR": str(data_dir),
                "WEATHERBOT_CONFIG_DIR": str(config_dir),
                "WEATHERBOT_WEB_HOST": "127.0.0.1",
                "WEATHERBOT_WEB_PORT": str(port),
                "WEATHERBOT_NOTIFICATIONS_TOAST": "false",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "HTTP_PROXY": "http://127.0.0.1:9",
                "NO_PROXY": "127.0.0.1,localhost",
            }
        )

        creationflags = (
            int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            if sys.platform == "win32"
            else 0
        )
        process = subprocess.Popen(  # noqa: S603 - fixed argument list, no shell  # nosec B603
            [executable, "serve", "--no-open"],
            cwd=work_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )
        try:
            deadline = time.monotonic() + STARTUP_TIMEOUT_S
            health = _wait_for_health(port, process, deadline)
            return _verify_smoke_responses(port, health)
        finally:
            _stop_process(process)


if __name__ == "__main__":
    raise SystemExit(main())
