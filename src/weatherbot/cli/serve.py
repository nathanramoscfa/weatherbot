# src/weatherbot/cli/serve.py
"""``weatherbot serve`` and the shared scheduled monitor loop.

``serve`` is the long-lived scheduled monitor and local web server; ``check`` (without
``--once``) runs the same scheduled monitor loop in the terminal without the web server.
Both acquire ``monitor.lock`` with zero wait (exiting 2 when another monitor process holds
it), write the rotating log file ``logs/weatherbot.log``, and clear the runner heartbeat's
expected cadence on a clean stop so a deliberately stopped monitor never reads as stale.
"""

import asyncio
import contextlib
import logging
import signal
import sys
from pathlib import Path
from typing import Annotated, Final

import typer

from weatherbot.cli.runtime import (
    EXIT_OK,
    EXIT_USAGE,
    Context,
    Output,
    Runtime,
    context_of,
    fail,
    open_monitor_session,
)
from weatherbot.services.config import AppPaths, Settings, WebSettings, setting_origins
from weatherbot.services.locks import ProcessLock
from weatherbot.services.logs import configure_logging
from weatherbot.services.monitor import CycleRunner
from weatherbot.services.persistence.database import Database
from weatherbot.services.replay import ReplayCorpus, ReplayError
from weatherbot.services.schedule import run_monitor
from weatherbot.services.tasks import TaskSchedulerError, query

LOGGER: Final = logging.getLogger("weatherbot.cli.serve")
DEFAULT_WEB_PORT: Final = 8765


def monitor_already_running_message(lock: ProcessLock, *, settings: Settings | None = None) -> str:
    """Format the ``EXIT_USAGE`` message naming the holder's pid, start instant, and URL."""
    web = settings.web if settings is not None else WebSettings()
    address = web.address(web.port or DEFAULT_WEB_PORT)
    pid: str | None = None
    since: str | None = None
    with contextlib.suppress(OSError):
        for line in lock.info_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("pid "):
                pid = line.removeprefix("pid ").strip()
            elif line.startswith("since "):
                since = line.removeprefix("since ").strip()
    if pid and since:
        return f"the monitor is already running (pid {pid}, since {since}); dashboard at {address}"
    return f"the monitor is already running; dashboard at {address}"


def _should_open_browser(rt: Runtime, *, open_flag: bool | None) -> bool:
    if open_flag is not None:
        return open_flag
    if rt.terminal is not None:
        return rt.terminal
    return sys.__stdout__ is not None and sys.__stdout__.isatty()


def _install_stop_signals(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError, ValueError):
            with contextlib.suppress(ValueError, OSError):
                signal.signal(sig, lambda _s, _f: loop.call_soon_threadsafe(stop_event.set))


def _open_cli_corpus(output: Output, corpus_dir: Path) -> ReplayCorpus:
    """Validate and open ``--corpus DIR`` before acquiring ``monitor.lock``."""
    if not corpus_dir.is_dir():
        fail(output, f"--corpus must name a directory: {corpus_dir}", EXIT_USAGE)
    try:
        return ReplayCorpus.open(corpus_dir)
    except ReplayError as error:
        fail(output, f"{corpus_dir} is not a replay corpus: {error}", EXIT_USAGE)


def _open_configured_corpus(settings: Settings) -> ReplayCorpus | None:
    """Open ``[web] corpus`` when configured; log a warning and return ``None`` on failure."""
    raw = settings.web.corpus
    if not raw:
        return None
    directory = Path(raw)
    if not directory.is_dir():
        LOGGER.warning("[web] corpus is not a directory; starting without replay")
        return None
    try:
        return ReplayCorpus.open(directory)
    except ReplayError as error:
        LOGGER.warning("[web] corpus is unusable (%s); starting without replay", error)
        return None


async def _loop(  # noqa: PLR0913 - runner loop state and optional web/corpus options
    context: Context,
    database: Database,
    paths: AppPaths,
    runner: CycleRunner,
    *,
    open_browser: bool = False,
    corpus: ReplayCorpus | None = None,
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
    _install_stop_signals(stop)

    if runner != "serve":
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
        return

    from weatherbot.web.app import WebState, create_app  # noqa: PLC0415
    from weatherbot.web.server import WebServer  # noqa: PLC0415

    rt = context.runtime
    settings = context.settings
    origins = setting_origins(paths, rt.environ)
    state = WebState(
        database=database,
        paths=paths,
        settings=settings,
        setting_origins=origins,
        clock=rt.now,
        started_at=rt.now(),
        corpus=corpus,
    )
    web_app = create_app(state)
    web_server = WebServer(
        web_app,
        host=settings.web.host,
        port=settings.web.port,
    )
    web_task = asyncio.create_task(web_server.serve(stop))
    started_task = asyncio.create_task(web_server.started.wait())
    try:
        await asyncio.wait(
            {web_task, started_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if web_server.started.is_set():
            address = web_server.address
            LOGGER.info("dashboard at %s", address)
            if open_browser:
                rt.open_browser(address)
        await run_monitor(
            database.engine,
            paths,
            settings=settings,
            runner=runner,
            stop=stop,
            clock=rt.now,
            sleep=rt.sleep,
            make_fetcher=rt.make_fetcher,
            channels=context.channels,
            check_installed=_check_installed,
        )
    finally:
        if not started_task.done():
            started_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await started_task
        stop.set()
        with contextlib.suppress(asyncio.CancelledError):
            await web_task


def run_monitor_loop(
    ctx: typer.Context,
    *,
    runner: CycleRunner,
    open_browser: bool | None = None,
    corpus: Path | None = None,
) -> None:
    """Take ``data_dir/monitor.lock``, configure ``weatherbot.log``, and run ``runner``."""
    context = context_of(ctx)
    output = Output(context.runtime)
    paths = context.paths
    if paths is None or context.problem:
        fail(output, context.problem or "the configuration is unusable")

    opened_corpus = _open_cli_corpus(output, corpus) if corpus is not None else None

    configure_logging(
        "DEBUG" if context.verbose else context.settings.logging.level,
        log_file=paths.log_file_path,
    )
    if opened_corpus is None and runner == "serve":
        opened_corpus = _open_configured_corpus(context.settings)

    lock = ProcessLock(paths.monitor_lock_path)
    if not lock.try_acquire():
        fail(
            output,
            monitor_already_running_message(lock, settings=context.settings),
            EXIT_USAGE,
        )
    try:
        should_open = _should_open_browser(context.runtime, open_flag=open_browser)
        with (
            open_monitor_session(context, output) as database,
            contextlib.suppress(KeyboardInterrupt),
        ):
            asyncio.run(
                _loop(
                    context,
                    database,
                    paths,
                    runner,
                    open_browser=should_open,
                    corpus=opened_corpus,
                )
            )
    finally:
        lock.release()
        configure_logging("DEBUG" if context.verbose else context.settings.logging.level)
    raise typer.Exit(EXIT_OK)


def serve(
    ctx: typer.Context,
    open_browser: Annotated[
        bool | None,
        typer.Option(
            "--open/--no-open",
            help="Open the dashboard in the default browser once listening "
            "(default: open in an interactive terminal, off when headless).",
        ),
    ] = None,
    corpus: Annotated[
        Path | None,
        typer.Option(
            "--corpus",
            help="Replay corpus directory for the map's historical replay "
            "(overrides [web] corpus).",
        ),
    ] = None,
) -> None:
    """Run the long-lived scheduled monitor and local web server."""
    run_monitor_loop(ctx, runner="serve", open_browser=open_browser, corpus=corpus)
