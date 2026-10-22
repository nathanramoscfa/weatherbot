# src/weatherbot/cli/check.py
"""``weatherbot check --once``: one monitor cycle, on demand.

It runs the cycle every scheduled run will (``MonitorService``, trigger ``manual``, runner
``check-once``): it fetches and stores a snapshot, assesses and stores every location, and
records the heartbeats and the cycle. It prints each location's level and the changes
since its previous assessment, then the cycle's status. It exits 0 on a complete cycle, 1
on a partial, failed, or skipped one, and 2 on a usage error. Without ``--once`` it exits
2: the monitor loop arrives with the scheduler.
"""

from typing import Annotated, Final

import typer

from weatherbot.cli.documents import (
    CheckData,
    CheckDocument,
    CheckLocationEntry,
    CycleEntry,
)
from weatherbot.cli.runtime import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    Output,
    context_of,
    fail,
    open_session,
)
from weatherbot.cli.snapshots import (
    ADD_HINT,
    JsonOption,
    drift_entries,
    print_header,
    run_cycle,
    snapshot_info,
)
from weatherbot.cli.status import change_entries
from weatherbot.services.assessments import AssessedLocation
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.monitor import CycleResult

NO_LOOP: Final = (
    "the monitor loop arrives with the scheduler; run one cycle with: weatherbot check --once"
)


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
    for warning in data.drift_warnings:
        output.line(f"Source drift: {warning.message}", style="yellow")
    output.line()
    cycle = data.cycle
    output.line(f"Cycle {cycle.cycle_id} ({cycle.runner}, {cycle.trigger}): {cycle.status}.")


def check(
    ctx: typer.Context,
    *,
    once: Annotated[bool, typer.Option("--once", help="Run one monitor cycle and exit.")] = False,
    json_output: JsonOption = False,
) -> None:
    """Run one monitor cycle: fetch, assess and store every location, and record it."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    if not once:
        fail(output, NO_LOOP, EXIT_USAGE)
    with open_session(context, output) as database:
        snapshot, cycle = run_cycle(
            context, output, database, runner="check-once", no_fetch=False, assess=True
        )
    now = context.runtime.now()
    info = snapshot_info(snapshot, now)
    data = CheckData(
        cycle=_cycle(cycle),
        locations=tuple(_location(result) for result in cycle.assessed),
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
