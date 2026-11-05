# src/weatherbot/cli/prune.py
"""``weatherbot prune``: plan or execute database retention from the terminal.

``weatherbot prune [--dry-run] [--days N] [--cutoff INSTANT] [--vacuum] [--json]``
computes a retention plan or runs batched pruning against ``weatherbot.sqlite3``
while preserving the keep-list invariants.
"""

from datetime import UTC, datetime
from typing import Annotated

import typer

from weatherbot.cli.documents import PruneData, PruneDocument
from weatherbot.cli.runtime import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    Output,
    context_of,
    fail,
    open_session,
)
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.database import DatabaseError
from weatherbot.services.retention import (
    DELETABLE_TABLES,
    MonitorRunningError,
    RetentionBusyError,
    RetentionCutoffError,
    RetentionPlan,
    RetentionService,
    validate_cutoff,
    validate_days,
)

DryRunOption = Annotated[
    bool,
    typer.Option(
        "--dry-run",
        help="Compute and print the retention plan and its cutoff without deleting rows.",
    ),
]
DaysOption = Annotated[
    int | None,
    typer.Option(
        "--days",
        help="Override [retention] history_days for this run (30 to 3650).",
    ),
]
CutoffOption = Annotated[
    str | None,
    typer.Option(
        "--cutoff",
        help="Run or preview an explicit UTC cutoff instant from a prior --dry-run (ISO 8601).",
    ),
]
VacuumOption = Annotated[
    bool,
    typer.Option(
        "--vacuum",
        help="Run SQLite VACUUM after pruning (refused while weatherbot serve or check runs).",
    ),
]
JsonOption = Annotated[
    bool,
    typer.Option("--json", help="Print one JSON document."),
]


def _parse_cutoff(output: Output, raw: str, *, now: datetime) -> datetime:
    normalized = raw.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        fail(output, "--cutoff must be an ISO 8601 UTC timestamp", EXIT_USAGE)
    try:
        return validate_cutoff(parsed, now=now)
    except RetentionCutoffError as error:
        fail(output, str(error), EXIT_USAGE)


def _print_counts_table(output: Output, title: str, counts: dict[str, int]) -> None:
    rows = [(table, str(count)) for table, count in counts.items() if count > 0]
    if rows:
        output.table(title, ("Table", "Rows"), rows)


def _emit(
    output: Output,
    *,
    now: datetime,
    json_output: bool,
    data: PruneData,
) -> None:
    if json_output:
        output.document(PruneDocument(generated_at=now, disclaimer=NOTICE, data=data))
        return
    if data.mode == "disabled":
        output.line("Retention is off ([retention] history_days = 0); nothing pruned.")
        if data.vacuumed and data.database_bytes_after_vacuum is not None:
            output.line(
                f"VACUUM complete; database size is {data.database_bytes_after_vacuum:,} bytes."
            )
        output.notice()
        return

    cutoff_text = data.cutoff.astimezone(UTC).isoformat() if data.cutoff is not None else "-"
    if data.mode == "dry_run":
        output.line(f"Dry-run retention plan (cutoff {cutoff_text}):")
        output.line(f"  Rows to delete: {data.total_rows:,}")
        if data.estimated_bytes is not None:
            output.line(f"  Estimated payload bytes: {data.estimated_bytes:,}")
        if data.kept:
            output.line("  Protected by keep-list: " + ", ".join(data.kept))
        _print_counts_table(output, "Planned deletions", data.counts)
        output.line(f"Run `weatherbot prune --cutoff {cutoff_text}` to execute this exact plan.")
        output.notice()
        return

    output.line(f"Retention prune {data.status} (cutoff {cutoff_text}):")
    output.line(f"  Batches executed: {data.batches}")
    output.line(f"  Total rows deleted: {data.total_rows:,}")
    if data.backup_file is not None:
        output.line(f"  Pre-prune backup: {data.backup_file}")
    _print_counts_table(output, "Deleted rows", data.counts)
    if data.vacuumed and data.database_bytes_after_vacuum is not None:
        output.line(
            f"  VACUUM complete; database size is {data.database_bytes_after_vacuum:,} bytes."
        )
    output.notice()


def prune(  # noqa: C901, PLR0912, PLR0913, PLR0915 - CLI command options and mode dispatch
    ctx: typer.Context,
    *,
    dry_run: DryRunOption = False,
    days: DaysOption = None,
    cutoff: CutoffOption = None,
    vacuum: VacuumOption = False,
    json_output: JsonOption = False,
) -> None:
    """Plan or execute database history retention."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    paths = context.paths
    if paths is None or context.problem:
        fail(output, context.problem or "the configuration is unusable")

    if days is not None and cutoff is not None:
        fail(output, "pass either --days or --cutoff, not both", EXIT_USAGE)
    if vacuum and dry_run:
        fail(output, "--vacuum cannot be combined with --dry-run", EXIT_USAGE)

    now = context.runtime.now().astimezone(UTC)
    parsed_cutoff: datetime | None = None
    effective_days: int | None = None

    if cutoff is not None:
        parsed_cutoff = _parse_cutoff(output, cutoff, now=now)
    elif days is not None:
        try:
            effective_days = validate_days(days)
        except RetentionCutoffError as error:
            fail(output, str(error), EXIT_USAGE)
    else:
        configured = context.settings.retention.history_days
        if configured > 0:
            effective_days = configured

    with open_session(context, output) as database:
        service = RetentionService(
            database.engine,
            paths,
            now=context.runtime.now,
        )
        if vacuum:
            try:
                service.check_vacuum_allowed()
            except MonitorRunningError as error:
                fail(output, str(error), EXIT_USAGE)

        if parsed_cutoff is None and effective_days is None:
            vacuum_bytes: int | None = None
            if vacuum:
                try:
                    vacuum_bytes = service.vacuum()
                except MonitorRunningError as error:
                    fail(output, str(error), EXIT_USAGE)
                except RetentionBusyError as error:
                    fail(output, str(error), EXIT_FAILED)
            data = PruneData(
                mode="disabled",
                history_days=0,
                cutoff=None,
                status="disabled",
                batches=0,
                total_rows=0,
                estimated_bytes=None,
                counts=dict.fromkeys(DELETABLE_TABLES, 0),
                kept=(),
                backup_file=None,
                vacuumed=vacuum,
                database_bytes_after_vacuum=vacuum_bytes,
            )
            _emit(output, now=now, json_output=json_output, data=data)
            raise typer.Exit(EXIT_OK)

        plan: RetentionPlan = (
            service.plan_cutoff(parsed_cutoff)
            if parsed_cutoff is not None
            else service.plan(effective_days or 30)
        )
        if dry_run:
            data = PruneData(
                mode="dry_run",
                history_days=effective_days,
                cutoff=plan.cutoff,
                status="dry_run",
                batches=0,
                total_rows=plan.total_rows,
                estimated_bytes=plan.estimated_bytes,
                counts=plan.counts,
                kept=plan.kept,
                backup_file=None,
                vacuumed=False,
                database_bytes_after_vacuum=None,
            )
            _emit(output, now=now, json_output=json_output, data=data)
            raise typer.Exit(EXIT_OK)

        try:
            result = service.run(plan.cutoff)
        except (RetentionBusyError, DatabaseError) as error:
            fail(output, str(error), EXIT_FAILED)

        vacuumed = False
        vacuum_bytes = None
        if vacuum and result.status == "complete":
            try:
                vacuum_bytes = service.vacuum()
                vacuumed = True
            except MonitorRunningError as error:
                fail(output, str(error), EXIT_USAGE)
            except RetentionBusyError as error:
                fail(output, str(error), EXIT_FAILED)

        data = PruneData(
            mode="pruned",
            history_days=effective_days,
            cutoff=result.cutoff,
            status=result.status,
            batches=result.batches,
            total_rows=result.total_deleted,
            estimated_bytes=None,
            counts=result.counts,
            kept=plan.kept,
            backup_file=result.backup_path.name if result.backup_path is not None else None,
            vacuumed=vacuumed,
            database_bytes_after_vacuum=vacuum_bytes,
        )
        _emit(output, now=now, json_output=json_output, data=data)
        raise typer.Exit(EXIT_OK if result.status == "complete" else EXIT_FAILED)
