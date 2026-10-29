# scripts/serve_demo.py
"""Offline demonstration server for the Playwright browser smoke and the idle CPU measurement.

Runs ``weatherbot serve``'s monitor and web server (through ``cli/serve.py``'s ``_loop``)
in a temporary data directory with both public landmarks stored (``"simulated Miami-Dade"``
and ``"Parliament Square"``), every request answered by recorded fixtures through ``respx``
(and any other refused), ``--port`` (default 8799), ``--corpus DIR``,
``--roster-interval-minutes`` (1 for the smoke; the default keeps production's intervals,
for the idle measurement), and ``--switch-file PATH`` (once that file exists, the roster
serves the next advisory and the forecast zone serves the synthetic Hurricane Warning,
reusing ``scripts/simulate_advisory.py``'s simulation). Prints its process id and address,
and one line per roster poll and per cycle; removes its temporary directory on exit; and
writes nothing in the checkout.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Final

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable

    from weatherbot.models import Snapshot
    from weatherbot.services.monitor import CycleResult, CycleTrigger
    from weatherbot.services.persistence.database import Database
    from weatherbot.sources.http import Fetcher, ValidatorStore

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for _extra in (
    REPO_ROOT / "src",
    REPO_ROOT / "scripts",
    REPO_ROOT / "tests" / "cli",
    REPO_ROOT / "tests" / "sources",
    REPO_ROOT / "tests" / "contract",
):
    _text = str(_extra)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from cli_support import (  # noqa: E402
    CORPUS,
    NASSAU,
    ROSTER_URL,
    add_landmark,
    directory,
    quiet_fetcher,
    recorded_services,
    runtime,
)
from source_support import NOW, entry  # noqa: E402

from simulate_advisory import (  # noqa: E402
    FORECAST_ALERTS_URL,
    SIMULATED_MIAMI,
    hurricane_warning_response,
    next_advisory_roster,
)
from weatherbot.cli.runtime import EXIT_OK, Context  # noqa: E402
from weatherbot.cli.serve import _loop  # noqa: E402  # pyright: ignore[reportPrivateUsage]
from weatherbot.services.config import AppPaths, Settings, load_settings  # noqa: E402
from weatherbot.services.monitor import MonitorService  # noqa: E402
from weatherbot.services.notifications import LogChannel  # noqa: E402
from weatherbot.services.persistence.database import open_database  # noqa: E402
from weatherbot.services.replay import ReplayCorpus  # noqa: E402
from weatherbot.services.schedule import MonitorSchedule  # noqa: E402

DEFAULT_PORT: Final = 8799


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Loopback TCP port to bind (default: 8799; 0 picks a free port).",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=CORPUS,
        help="Replay corpus directory to open (default: tests/fixtures/replay).",
    )
    parser.add_argument(
        "--roster-interval-minutes",
        type=int,
        default=None,
        help="Override roster poll intervals in minutes (1 for smoke; default keeps production).",
    )
    parser.add_argument(
        "--switch-file",
        type=Path,
        default=None,
        help="When this file exists, serve advisory 023 and the synthetic Hurricane Warning.",
    )
    return parser.parse_args(argv)


def _baseline_roster_response() -> httpx.Response:
    capture = directory("nhc-current-storms")
    (item,) = capture.entries
    return httpx.Response(
        200,
        content=capture.payload(item),
        headers={"content-type": "application/json"},
    )


def _baseline_forecast_alerts_response() -> httpx.Response:
    capture = directory("nws-alerts-zone")
    item = entry(capture, "alerts-zone-FLZ173.geojson")
    return httpx.Response(
        200,
        content=capture.payload(item),
        headers={"content-type": "application/geo+json"},
    )


class _ServeAddressHandler(logging.Handler):
    """Emits ``pid=<pid> address=<address>`` once ``cli/serve.py`` logs its address."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.printed = False

    def emit(self, record: logging.LogRecord) -> None:
        if self.printed:
            return
        msg = record.getMessage()
        prefix = "dashboard at "
        if msg.startswith(prefix):
            address = msg.removeprefix(prefix).strip()
            self.printed = True
            print(f"pid={os.getpid()} address={address}", flush=True)


def _install_demo_instrumentation() -> Callable[[], None]:
    """Wrap ``MonitorSchedule`` and ``MonitorService`` to print roster polls and cycles."""
    original_init = MonitorSchedule.__init__
    original_run_roster = MonitorSchedule.run_roster
    original_run_cycle = MonitorService.run_cycle
    first_schedule_created = False

    def _wrapped_init(  # type: ignore[no-untyped-def]
        self: MonitorSchedule, *args: object, **kwargs: object
    ) -> None:
        nonlocal first_schedule_created
        if first_schedule_created:
            # The initial startup cycle already ran before WebServer bound its socket,
            # so ``_loop``'s MonitorSchedule starts with its startup cycle satisfied.
            kwargs["run_startup"] = False
        first_schedule_created = True
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    async def _wrapped_run_roster(self: MonitorSchedule, now: datetime) -> None:
        await original_run_roster(self, now)
        print(f"roster_poll at={now.isoformat()}", flush=True)

    async def _wrapped_run_cycle(
        self: MonitorService,
        trigger: CycleTrigger,
        *,
        snapshot: Snapshot | None = None,
        assess: bool = True,
    ) -> CycleResult:
        result = await original_run_cycle(self, trigger, snapshot=snapshot, assess=assess)
        print(
            f"cycle id={result.cycle_id} trigger={result.trigger} status={result.status}",
            flush=True,
        )
        return result

    MonitorSchedule.__init__ = _wrapped_init  # type: ignore[method-assign]
    MonitorSchedule.run_roster = _wrapped_run_roster  # type: ignore[method-assign]
    MonitorService.run_cycle = _wrapped_run_cycle  # type: ignore[method-assign]

    def _restore() -> None:
        MonitorSchedule.__init__ = original_init  # type: ignore[method-assign]
        MonitorSchedule.run_roster = original_run_roster  # type: ignore[method-assign]
        MonitorService.run_cycle = original_run_cycle  # type: ignore[method-assign]

    return _restore


def _configure_demo_environ(root: Path, args: argparse.Namespace) -> None:
    os.environ["WEATHERBOT_DATA_DIR"] = str(root / "data")
    os.environ["WEATHERBOT_CONFIG_DIR"] = str(root / "config")
    os.environ["WEATHERBOT_WEB_PORT"] = str(int(args.port))
    os.environ["WEATHERBOT_NOTIFICATIONS_TOAST"] = "false"
    if args.roster_interval_minutes is not None:
        interval_text = str(int(args.roster_interval_minutes))
        os.environ["WEATHERBOT_MONITOR_ROSTER_INTERVAL_MINUTES"] = interval_text
        os.environ["WEATHERBOT_MONITOR_ROSTER_INTERVAL_RELEVANT_MINUTES"] = interval_text


def _run_serve_loop(
    database: Database,
    paths: AppPaths,
    settings: Settings,
    clock: Callable[[], datetime],
    corpus: ReplayCorpus | None,
) -> None:
    def _make_demo_fetcher(
        client: httpx.AsyncClient,
        validators: ValidatorStore,
        *,
        now: datetime = NOW,
    ) -> Fetcher:
        return quiet_fetcher(client, validators, now=clock() if now == NOW else now)

    rt = runtime(now=NOW, environ=dict(os.environ))
    object.__setattr__(rt, "now", clock)
    object.__setattr__(rt, "make_fetcher", _make_demo_fetcher)

    # Run the initial startup cycle before the web server binds its port so
    # assessments, snapshot, and heartbeats are ready on the first request.
    initial_schedule = MonitorSchedule(
        database.engine,
        paths,
        settings=settings,
        runner="serve",
        clock=clock,
        make_fetcher=rt.make_fetcher,
        channels=(LogChannel(), rt.make_toast(settings)),
        run_startup=True,
    )
    asyncio.run(initial_schedule.run_startup(clock()))

    context = Context(
        runtime=rt,
        paths=paths,
        settings=settings,
    )

    async def _run_with_sigbreak() -> None:
        loop = asyncio.get_running_loop()
        sigbreak = getattr(signal, "SIGBREAK", None)
        if sigbreak is not None:
            with contextlib.suppress(ValueError, OSError):
                signal.signal(
                    sigbreak,
                    lambda _s, _f: loop.call_soon_threadsafe(signal.raise_signal, signal.SIGINT),
                )
        await _loop(
            context,
            database,
            paths,
            "serve",
            open_browser=False,
            corpus=corpus,
        )

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run_with_sigbreak())


def main(argv: list[str] | None = None) -> int:
    """Run the recorded demonstration server until interrupted."""
    args = _parse_args(argv)
    start_monotonic = time.monotonic()

    def clock() -> datetime:
        return NOW + timedelta(seconds=max(0.0, time.monotonic() - start_monotonic))

    switch_file: Path | None = args.switch_file
    corpus_dir: Path | None = args.corpus
    corpus = (
        ReplayCorpus.open(corpus_dir) if corpus_dir is not None and corpus_dir.is_dir() else None
    )

    baseline_roster = _baseline_roster_response()
    next_roster = httpx.Response(
        200,
        content=next_advisory_roster(),
        headers={"content-type": "application/json"},
    )
    baseline_alerts = _baseline_forecast_alerts_response()

    def _is_switched() -> bool:
        return switch_file is not None and switch_file.exists()

    def _roster_side_effect(_request: httpx.Request) -> httpx.Response:
        return next_roster if _is_switched() else baseline_roster

    def _alerts_side_effect(_request: httpx.Request) -> httpx.Response:
        return hurricane_warning_response(clock()) if _is_switched() else baseline_alerts

    restore_instrumentation = _install_demo_instrumentation()
    serve_logger = logging.getLogger("weatherbot.cli.serve")
    address_handler = _ServeAddressHandler()
    serve_logger.addHandler(address_handler)
    serve_logger.setLevel(logging.INFO)

    try:
        with TemporaryDirectory(prefix="weatherbot-serve-demo-") as tmp:
            _configure_demo_environ(Path(tmp), args)
            with recorded_services() as router:
                router.get(ROSTER_URL).mock(side_effect=_roster_side_effect)
                router.get(FORECAST_ALERTS_URL).mock(side_effect=_alerts_side_effect)

                ran_miami = add_landmark(SIMULATED_MIAMI, "miami-dade", "--polygon", "forecast")
                if ran_miami.exit_code != EXIT_OK:
                    return ran_miami.exit_code
                ran_nassau = add_landmark(NASSAU, "nassau")
                if ran_nassau.exit_code != EXIT_OK:
                    return ran_nassau.exit_code

                paths = AppPaths.resolve(os.environ)
                settings = load_settings(paths, os.environ)
                with open_database(paths) as database:
                    _run_serve_loop(database, paths, settings, clock, corpus)
        return EXIT_OK
    finally:
        serve_logger.removeHandler(address_handler)
        restore_instrumentation()


if __name__ == "__main__":
    raise SystemExit(main())
