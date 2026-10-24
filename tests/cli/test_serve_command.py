# tests/cli/test_serve_command.py
"""``weatherbot serve`` and ``weatherbot check``: single-instance lock, startup, and heartbeat."""

from typing import Final

from cli_support import MIAMI, add_landmark, quiet_fetcher, recorded_services, run, runtime
from source_support import NOW

from weatherbot.cli.runtime import Runtime
from weatherbot.services.config import AppPaths
from weatherbot.services.locks import ProcessLock
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import CycleRepository, HeartbeatRepository

USAGE: Final = 2


def test_serve_and_check_exit_2_when_monitor_lock_is_already_held() -> None:
    paths = AppPaths.resolve()
    holder = ProcessLock(paths.monitor_lock_path)
    assert holder.try_acquire()
    try:
        for command in (["serve"], ["check"]):
            result = run(command)
            assert result.exit_code == USAGE
            assert "the monitor is already running" in result.stderr
            assert "pid " in result.stderr
            assert "since " in result.stderr
    finally:
        holder.release()


def test_serve_runs_startup_cycle_and_records_runner_heartbeat() -> None:
    paths = AppPaths.resolve()
    seen_running_cadence: list[int | None] = []

    async def _stop_on_first_sleep(_seconds: float) -> None:
        with open_database(paths) as db:
            hb = next(
                r
                for r in HeartbeatRepository(db.engine).rows()
                if r.kind == "runner" and r.name == "serve"
            )
            seen_running_cadence.append(hb.expected_every_s)
        raise KeyboardInterrupt

    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        base_rt = runtime(now=NOW)
        rt = Runtime(
            environ=base_rt.environ,
            make_fetcher=quiet_fetcher,
            make_toast=base_rt.make_toast,
            identity=base_rt.identity,
            now=lambda: NOW,
            sleep=_stop_on_first_sleep,
            terminal=False,
        )
        result = run(["serve"], rt)

    assert result.exit_code == 0, result.stderr
    assert seen_running_cadence == [300]
    assert not ProcessLock(paths.monitor_lock_path).locked

    with open_database(paths) as database:
        cycles = CycleRepository(database.engine).recent(5)
        runner_hb = next(
            r
            for r in HeartbeatRepository(database.engine).rows()
            if r.kind == "runner" and r.name == "serve"
        )
    assert len(cycles) == 1
    assert (cycles[0].runner, cycles[0].trigger, cycles[0].status) == (
        "serve",
        "startup",
        "complete",
    )
    assert runner_hb.last_success_at == NOW
    # Clean stop clears expected_every_s so a stopped monitor never reads as stale.
    assert runner_hb.expected_every_s is None
    assert paths.log_file_path.is_file()
