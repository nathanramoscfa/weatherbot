# src/weatherbot/cli/check.py
"""``weatherbot check`` and ``weatherbot check --once``: the monitor loop or one cycle.

``check --once`` runs one cycle on demand (``MonitorService``, trigger ``manual``, runner
``check-once``): it fetches and stores a snapshot, assesses and stores every location, and
records the heartbeats and the cycle. It prints each location's level and the changes
since its previous assessment, then the cycle's status. It exits 0 on a complete cycle, 1
on a partial, failed, or skipped one, and 2 on a usage error.

Without ``--once``, ``check`` takes ``data_dir/monitor.lock`` (``ProcessLock``) and runs
the scheduler in the terminal with runner ``check``, writing the rotating log file at
``data_dir/logs/weatherbot.log`` until stopped.
"""

import asyncio
import contextlib
from typing import Annotated

import typer

from weatherbot.cli.documents import (
    CheckData,
    CheckDocument,
    CheckLocationEntry,
    CycleEntry,
)
from weatherbot.cli.notify import notification_entries
from weatherbot.cli.runtime import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    Context,
    Output,
    context_of,
    fail,
    open_monitor_session,
)
from weatherbot.cli.serve import run_monitor_loop
from weatherbot.cli.snapshots import (
    ADD_HINT,
    BUSY,
    JsonOption,
    drift_entries,
    print_header,
    run_cycle,
    snapshot_info,
    utc,
)
from weatherbot.cli.status import change_entries
from weatherbot.services.assessments import AssessedLocation
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.logs import configure_logging
from weatherbot.services.monitor import CycleResult
from weatherbot.services.persistence.database import Database
from weatherbot.services.schedule import FallbackResult, run_fallback_check
from weatherbot.services.tasks import TaskSchedulerError, query
from weatherbot.services.tasks import run as run_task


def _location(result: AssessedLocation) -> CheckLocationEntry:
    assessment = result.stored.assessment
    return CheckLocationEntry(
        name=result.location.name,
        level=int(assessment.level),
        level_name=assessment.level.label,
        rule=str(assessment.rule),
        complete=assessment.complete,
        changes=change_entries(result.stored.changes),
        stored_before=not result.created,
    )


def _cycle(result: CycleResult) -> CycleEntry:
    return CycleEntry(
        cycle_id=result.cycle_id,
        runner=result.runner,
        trigger=result.trigger,
        status=result.status,
        started_at=result.started_at,
        completed_at=result.completed_at,
    )


def _print(output: Output, data: CheckData) -> None:
    if not data.locations:
        output.line(f"No location is stored, so none was assessed; {ADD_HINT}.")
    for entry in data.locations:
        floor = "" if entry.complete else "at least "
        output.line()
        output.line(f"{entry.name}: {floor}level {entry.level}, {entry.level_name}", style="bold")
        if entry.changes:
            output.line("  Changes since the previous assessment:")
            for change in entry.changes:
                output.line(f"    - {change.detail}")
        else:
            output.line("  Changes since the previous assessment: none.")
    for notification in data.notifications:
        output.line()
        output.line(f"Notification sent: {notification.title}", style="bold")
        for line in notification.body:
            output.line(f"  {line}")
    if data.confirm_at is not None:
        output.line()
        output.line(f"Confirmation cycle due at {utc(data.confirm_at)}.")
    for warning in data.drift_warnings:
        output.line(f"Source drift: {warning.message}", style="yellow")
    output.line()
    cycle = data.cycle
    output.line(f"Cycle {cycle.cycle_id} ({cycle.runner}, {cycle.trigger}): {cycle.status}.")


def _run_if_stale(context: Context, output: Output, database: Database) -> FallbackResult:
    paths = context.paths
    if paths is None:  # pragma: no cover - open_monitor_session refuses unresolved paths
        fail(output, context.problem or "the configuration is unusable")

    def _serve_installed() -> bool:
        if not context.runtime.windows:
            return False
        try:
            found = query(runner=context.runtime.task_runner)
        except TaskSchedulerError:
            return False
        return any(item.name == "serve" for item in found)

    def _start_serve() -> None:
        if not context.runtime.windows:
            return
        with contextlib.suppress(TaskSchedulerError, ValueError):
            run_task("serve", runner=context.runtime.task_runner)

    return asyncio.run(
        run_fallback_check(
            database.engine,
            paths,
            settings=context.settings,
            clock=context.runtime.now,
            sleep=context.runtime.sleep,
            make_fetcher=context.runtime.make_fetcher,
            channels=context.channels,
            serve_installed=_serve_installed,
            start_serve=_start_serve,
        )
    )


def check(
    ctx: typer.Context,
    *,
    once: Annotated[bool, typer.Option("--once", help="Run one monitor cycle and exit.")] = False,
    if_stale: Annotated[
        bool,
        typer.Option(
            "--if-stale",
            help="Skip the cycle if the background monitor holds the lock and is fresh.",
        ),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Run the monitor scheduler in the terminal, or one cycle on demand with ``--once``."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    if not once:
        if if_stale:
            fail(output, "--if-stale requires --once", EXIT_USAGE)
        if json_output:
            fail(output, "--json requires --once", EXIT_USAGE)
        run_monitor_loop(ctx, runner="check")
    if if_stale:
        if context.paths is None or context.problem:
            fail(output, context.problem or "the configuration is unusable")
        configure_logging(
            "DEBUG" if context.verbose else context.settings.logging.level,
            log_file=context.paths.log_file_path,
        )
        with open_monitor_session(context, output) as database:
            fallback = _run_if_stale(context, output, database)
        if not fallback.ran_cycle:
            if not json_output:
                output.line("Monitor is healthy; fallback check skipped.")
                output.notice()
            raise typer.Exit(EXIT_OK)
        if fallback.cycle is None or fallback.cycle.snapshot is None:
            fail(output, BUSY)
        snapshot = fallback.cycle.snapshot
        cycle = fallback.cycle
    else:
        with open_monitor_session(context, output) as database:
            snapshot, cycle = run_cycle(
                context, output, database, runner="check-once", no_fetch=False, assess=True
            )
    now = context.runtime.now()
    info = snapshot_info(snapshot, now)
    data = CheckData(
        cycle=_cycle(cycle),
        locations=tuple(_location(result) for result in cycle.assessed),
        notifications=notification_entries(cycle.notifications),
        confirm_at=cycle.confirm_at,
        drift_warnings=drift_entries(cycle.drift_warnings),
    )
    code = EXIT_OK if cycle.status == "complete" else EXIT_FAILED
    if json_output:
        output.document(
            CheckDocument(generated_at=now, disclaimer=NOTICE, snapshot=info, data=data)
        )
        raise typer.Exit(code)
    print_header(output, info, stored=False)
    _print(output, data)
    output.notice()
    raise typer.Exit(code)
