# scripts/measure_idle.py
"""Measure the idle CPU shares of ``serve_demo.py`` and the Chromium dashboard tab over 600 s.

Starts ``scripts/serve_demo.py`` at production intervals on a free loopback port, runs
``npm --prefix frontend run e2e:idle`` against it, samples the server process's CPU time
(``user + system``) with ``psutil`` at the start and end of the same 600 s measurement
window (after ``idle.spec.ts``'s 30 s settle), prints both shares of one core (``< 0.5%``
each) along with the window duration and the number of roster polls and cycles
``serve_demo.py`` reported inside the window, and exits 1 if either share is ``>= 0.5%``.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import signal
import socket
import subprocess  # runs serve_demo.py and npm from fixed argument lists, never a shell  # nosec B404
import sys
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Final, cast

import psutil

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
FRONTEND_DIR: Final = REPO_ROOT / "frontend"
STATIC_INDEX_PATH: Final = REPO_ROOT / "src" / "weatherbot" / "web" / "static" / "index.html"
WINDOW_START_FLAG_PATH: Final = FRONTEND_DIR / "test-results" / "idle-window-started.flag"
IDLE_METRICS_PATH: Final = FRONTEND_DIR / "test-results" / "idle-metrics.json"

STARTUP_TIMEOUT_S: Final = 60.0
POLL_INTERVAL_S: Final = 0.2
IDLE_BUDGET_PCT: Final = 0.5


@dataclass
class _DemoOutputTracker:
    """Thread-safe reader for ``serve_demo.py`` stdout lines."""

    ready_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    pid: int | None = None
    address: str | None = None
    in_window: bool = False
    roster_polls_in_window: int = 0
    cycles_in_window: int = 0
    lines: list[str] = field(default_factory=list[str])

    def feed_line(self, raw_line: str) -> None:
        line = raw_line.strip()
        if not line:
            return
        with self.lock:
            self.lines.append(line)
            if line.startswith("pid=") and " address=" in line:
                parts = dict(token.split("=", 1) for token in line.split() if "=" in token)
                with_pid = parts.get("pid")
                if with_pid is not None and with_pid.isdigit():
                    self.pid = int(with_pid)
                self.address = parts.get("address")
                self.ready_event.set()
            elif self.in_window:
                if line.startswith("roster_poll "):
                    self.roster_polls_in_window += 1
                elif line.startswith("cycle "):
                    self.cycles_in_window += 1

    def set_window_active(self, *, active: bool) -> None:
        with self.lock:
            self.in_window = active


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        address = sock.getsockname()
        return int(address[1])


def _resolve_npm_executable() -> str:
    candidate = shutil.which("npm")
    if candidate is None:
        message = "measure_idle: `npm` executable not found on PATH"
        raise RuntimeError(message)
    return str(Path(candidate).resolve())


def _wait_for_health(port: int, deadline: float) -> None:
    while time.monotonic() < deadline:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5.0)
        try:
            conn.request("GET", "/api/health", headers={"Host": f"127.0.0.1:{port}"})
            response = conn.getresponse()
            response.read()
            if response.status == HTTPStatus.OK:
                return
        except (OSError, http.client.HTTPException):
            pass
        finally:
            conn.close()
        time.sleep(POLL_INTERVAL_S)
    message = f"measure_idle: timed out waiting for http://127.0.0.1:{port}/api/health"
    raise RuntimeError(message)


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        if sys.platform == "win32":
            ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
            if isinstance(ctrl_break, int):
                process.send_signal(ctrl_break)
        else:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
    if process.stdout is not None:
        process.stdout.close()


def _cpu_seconds(proc: psutil.Process) -> float:
    times = proc.cpu_times()
    return float(times.user + times.system)


def evaluate_idle_shares(
    *,
    server_cpu_pct: float,
    tab_cpu_pct: float,
    budget_pct: float = IDLE_BUDGET_PCT,
) -> bool:
    """Return ``True`` when both CPU shares are strictly under ``budget_pct``."""
    return 0.0 <= server_cpu_pct < budget_pct and 0.0 <= tab_cpu_pct < budget_pct


def _cleanup_marker_files() -> None:
    for marker in (WINDOW_START_FLAG_PATH, IDLE_METRICS_PATH):
        if marker.exists():
            marker.unlink()


def _ensure_frontend_built(npm_exe: str) -> None:
    if STATIC_INDEX_PATH.is_file():
        return
    subprocess.run(  # noqa: S603 - fixed argument list, no shell  # nosec B603
        [npm_exe, "--prefix", str(FRONTEND_DIR), "run", "build"],
        cwd=REPO_ROOT,
        check=True,
    )


def _sample_idle_window(
    e2e_proc: subprocess.Popen[str],
    ps_proc: psutil.Process,
    tracker: _DemoOutputTracker,
) -> tuple[float, float, float]:
    while e2e_proc.poll() is None and not WINDOW_START_FLAG_PATH.is_file():
        time.sleep(POLL_INTERVAL_S)
    if not WINDOW_START_FLAG_PATH.is_file():
        message = (
            f"measure_idle: e2e:idle exited ({e2e_proc.returncode}) before "
            "starting the 600 s measurement window"
        )
        raise RuntimeError(message)

    start_cpu_s = _cpu_seconds(ps_proc)
    start_monotonic = time.monotonic()
    tracker.set_window_active(active=True)

    while e2e_proc.poll() is None and not IDLE_METRICS_PATH.is_file():
        time.sleep(POLL_INTERVAL_S)

    tracker.set_window_active(active=False)
    end_cpu_s = _cpu_seconds(ps_proc)
    end_monotonic = time.monotonic()
    e2e_proc.wait(timeout=30.0)

    measured_window_s = max(1.0, end_monotonic - start_monotonic)
    server_cpu_delta_s = max(0.0, end_cpu_s - start_cpu_s)
    return measured_window_s, server_cpu_delta_s, (server_cpu_delta_s / measured_window_s) * 100.0


def main() -> int:
    """Run ``serve_demo.py`` and ``e2e:idle`` over the 600 s window and check both budgets."""
    npm_exe = _resolve_npm_executable()
    _ensure_frontend_built(npm_exe)
    _cleanup_marker_files()

    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    tracker = _DemoOutputTracker()
    creationflags = (
        int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if sys.platform == "win32" else 0
    )

    serve_proc = subprocess.Popen(  # noqa: S603 - fixed argument list, no shell  # nosec B603
        [sys.executable, str(REPO_ROOT / "scripts" / "serve_demo.py"), "--port", str(port)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=creationflags,
    )

    def _read_stdout() -> None:
        if serve_proc.stdout is None:
            return
        for raw_line in serve_proc.stdout:
            tracker.feed_line(raw_line)

    reader = threading.Thread(target=_read_stdout, daemon=True)
    reader.start()

    try:
        if not tracker.ready_event.wait(timeout=STARTUP_TIMEOUT_S):
            message = "measure_idle: timed out waiting for serve_demo.py startup line"
            raise RuntimeError(message)
        _wait_for_health(port, time.monotonic() + STARTUP_TIMEOUT_S)

        target_pid = tracker.pid or serve_proc.pid
        ps_proc = psutil.Process(target_pid)

        e2e_env = os.environ.copy()
        e2e_env["E2E_BASE_URL"] = base_url
        e2e_proc = subprocess.Popen(  # noqa: S603 - fixed argument list, no shell  # nosec B603
            [npm_exe, "--prefix", str(FRONTEND_DIR), "run", "e2e:idle"],
            cwd=REPO_ROOT,
            env=e2e_env,
            text=True,
        )
        try:
            measured_window_s, server_cpu_delta_s, server_cpu_pct = _sample_idle_window(
                e2e_proc, ps_proc, tracker
            )
        finally:
            if e2e_proc.poll() is None:
                e2e_proc.terminate()
                e2e_proc.wait(timeout=10.0)

        if not IDLE_METRICS_PATH.is_file():
            print("measure_idle: idle-metrics.json was not written", file=sys.stderr)
            return 1

        raw_metrics: object = json.loads(IDLE_METRICS_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw_metrics, dict):
            print("measure_idle: invalid idle-metrics.json payload", file=sys.stderr)
            return 1
        metrics = cast("dict[str, float]", raw_metrics)
        tab_cpu_pct = float(metrics.get("tab_cpu_percent", 100.0))
        tab_cpu_delta_s = float(metrics.get("task_duration_delta_seconds", 0.0))

        print(
            f"idle measurement: window={measured_window_s:.1f}s "
            f"server_cpu={server_cpu_pct:.4f}% ({server_cpu_delta_s:.3f}s) "
            f"tab_cpu={tab_cpu_pct:.4f}% ({tab_cpu_delta_s:.3f}s) "
            f"roster_polls={tracker.roster_polls_in_window} "
            f"cycles={tracker.cycles_in_window} "
            f"budget=<{IDLE_BUDGET_PCT:.1f}%",
            flush=True,
        )

        if e2e_proc.returncode != 0:
            return 1
        if not evaluate_idle_shares(
            server_cpu_pct=server_cpu_pct,
            tab_cpu_pct=tab_cpu_pct,
        ):
            return 1
        return 0
    finally:
        _stop_process(serve_proc)
        reader.join(timeout=5.0)
        _cleanup_marker_files()


if __name__ == "__main__":
    raise SystemExit(main())
