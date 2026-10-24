# src/weatherbot/cli/serve.py
"""``weatherbot serve``: run the background monitor scheduler under ``monitor.lock``.

Takes ``data_dir/monitor.lock`` without waiting, configures the rotating log file at
``data_dir/logs/weatherbot.log``, and runs the monitor scheduler and process heartbeat
with runner name ``serve`` until stopped (Ctrl+C or process termination). On a clean stop
it clears the ``serve`` runner heartbeat's expected cadence so a monitor stopped on
purpose never reads as stale. Phase 5 adds the local web server to the same process and
event loop.
"""

import asyncio
import contextlib

import typer

from weatherbot.cli.runtime import (
    EXIT_OK,
    EXIT_USAGE,
    Context,
    Output,
    context_of,
    fail,
    open_monitor_session,
)
from weatherbot.services.config import AppPaths
from weatherbot.services.locks import ProcessLock
from weatherbot.services.logs import configure_logging
from weatherbot.services.monitor import CycleRunner
from weatherbot.services.persistence.database import Database
from weatherbot.services.schedule import run_monitor
from weatherbot.services.tasks import TaskSchedulerError, query


def monitor_already_running_message(lock: ProcessLock) -> str:
    """Format the ``EXIT_USAGE`` message naming the holder's pid and start instant."""
    pid: str | None = None
    since: str | None = None
    with contextlib.suppress(OSError):
        for line in lock.info_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("pid "):
                pid = line.removeprefix("pid ").strip()
            elif line.startswith("since "):
                since = line.removeprefix("since ").strip()
    if pid and since:
        return f"the monitor is already running (pid {pid}, since {since})"
    return "the monitor is already running"


async def _loop(
    context: Context,
    database: Database,
    paths: AppPaths,
    runner: CycleRunner,
) -> None:
    def _check_installed() -> bool:
        if not context.runtime.windows:
            return False
        try:
            found = query(runner=context.runtime.task_runner)
        except TaskSchedulerError:
            return False
        return any(item.name == "check" for item in found)

    stop = asyncio.Event()
    await run_monitor(
        database.engine,
        paths,
        settings=context.settings,
        runner=runner,
        stop=stop,
        clock=context.runtime.now,
        sleep=context.runtime.sleep,
        make_fetcher=context.runtime.make_fetcher,
        channels=context.channels,
        check_installed=_check_installed,
    )


def run_monitor_loop(ctx: typer.Context, *, runner: CycleRunner) -> None:
    """Take ``data_dir/monitor.lock``, configure ``weatherbot.log``, and run ``runner``."""
    context = context_of(ctx)
    output = Output(context.runtime)
    paths = context.paths
    if paths is None or context.problem:
        fail(output, context.problem or "the configuration is unusable")

    configure_logging(
        "DEBUG" if context.verbose else context.settings.logging.level,
        log_file=paths.log_file_path,
    )
    lock = ProcessLock(paths.monitor_lock_path)
    if not lock.try_acquire():
        fail(output, monitor_already_running_message(lock), EXIT_USAGE)
    try:
        with (
            open_monitor_session(context, output) as database,
            contextlib.suppress(KeyboardInterrupt),
        ):
            asyncio.run(_loop(context, database, paths, runner))
    finally:
        lock.release()
    raise typer.Exit(EXIT_OK)


def serve(ctx: typer.Context) -> None:
    """Run the monitor scheduler (Phase 5 adds the web server to the same process and loop)."""
    run_monitor_loop(ctx, runner="serve")
