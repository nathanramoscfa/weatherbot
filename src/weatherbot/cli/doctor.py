# src/weatherbot/cli/doctor.py
"""``weatherbot doctor``: the paths, the database, and every source's reachability.

It never prints a coordinate: the locations are counted, and no probe sends one. It exits
1 when any check, probe, or layer discovery fails.
"""

import asyncio
from typing import Annotated

import typer

from weatherbot.cli.documents import (
    DoctorCheck,
    DoctorData,
    DoctorDatabase,
    DoctorDocument,
    DoctorPaths,
    LayerDiscoveryEntry,
    SourceProbeEntry,
)
from weatherbot.cli.runtime import EXIT_FAILED, EXIT_OK, Context, Output, context_of
from weatherbot.cli.runtime import open_tolerant_session as open_session
from weatherbot.cli.snapshots import drift_entries, utc
from weatherbot.cli.status import staleness_entries
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.doctor import DoctorReport, diagnose, missing_summary
from weatherbot.services.health import duration_text

UNRESOLVED = "<unresolved>"


def _paths(context: Context) -> DoctorPaths:
    paths = context.paths
    if paths is None:
        return DoctorPaths(
            config_dir=UNRESOLVED,
            data_dir=UNRESOLVED,
            settings_file=UNRESOLVED,
            database_file=UNRESOLVED,
        )
    return DoctorPaths(
        config_dir=str(paths.config_dir),
        data_dir=str(paths.data_dir),
        settings_file=str(paths.settings_path),
        database_file=str(paths.database_path),
    )


def _data(context: Context, report: DoctorReport, *, offline: bool) -> DoctorData:
    state = report.database
    database = (
        DoctorDatabase(
            revision=state.revision,
            head=state.head,
            at_head=state.revision == state.head,
            created=state.created,
            backup_file=str(state.backup_path) if state.backup_path else None,
        )
        if state is not None
        else None
    )
    return DoctorData(
        paths=_paths(context),
        database=database,
        locations=report.locations,
        checks=tuple(
            DoctorCheck(name=c.name, status=c.status, detail=c.detail) for c in report.checks
        ),
        offline=offline,
        probes=tuple(
            SourceProbeEntry(source_id=p.source_id, status=p.status, detail=p.detail)
            for p in report.probes
        ),
        layers=tuple(
            LayerDiscoveryEntry(
                source_id=layer.source_id,
                status=layer.status,
                expected=layer.expected,
                resolved=layer.resolved,
                missing=layer.missing,
            )
            for layer in report.layers
        ),
        drift_snapshot_id=report.drift_snapshot_id,
        drift_warnings=drift_entries(report.drift_warnings),
        heartbeats=staleness_entries(report.heartbeats),
        failed=report.failed,
    )


def _print(output: Output, data: DoctorData) -> None:
    paths = data.paths
    output.table(
        "Paths",
        ("What", "Path"),
        [
            ("Configuration directory", paths.config_dir),
            ("Settings file", paths.settings_file),
            ("Data directory", paths.data_dir),
            ("Database", paths.database_file),
        ],
    )
    output.table(
        "Checks", ("Check", "Result", "Detail"), [(c.name, c.status, c.detail) for c in data.checks]
    )
    if data.offline:
        output.line("Offline: no source was probed.")
    else:
        output.table(
            "Sources",
            ("Source", "Result", "Detail"),
            [(p.source_id, p.status, p.detail) for p in data.probes],
        )
        output.table(
            "Layer discovery",
            ("Service", "Result", "Resolved", "Missing"),
            [
                (
                    layer.source_id,
                    layer.status,
                    f"{layer.resolved} of {layer.expected}",
                    missing_summary(layer.missing),
                )
                for layer in data.layers
            ],
        )
    if data.drift_snapshot_id is None:
        output.line("No snapshot is stored, so there are no Source-drift warnings to list.")
    elif not data.drift_warnings:
        output.line(f"The latest snapshot ({data.drift_snapshot_id}) logged no Source drift.")
    else:
        output.table(
            f"Source drift in the latest snapshot ({data.drift_snapshot_id})",
            ("Source", "Warning"),
            [(w.source_id, w.message) for w in data.drift_warnings],
        )
    if data.heartbeats:
        output.table(
            "Heartbeats",
            ("Kind", "Name", "Last success", "Expected every", "Stale"),
            [
                (
                    beat.kind,
                    beat.name,
                    utc(beat.last_success_at) if beat.last_success_at else "never",
                    duration_text(beat.expected_every_s) if beat.expected_every_s else "-",
                    "yes" if beat.stale else "no",
                )
                for beat in data.heartbeats
            ],
        )
    verdict = "FAILED: a check failed" if data.failed else "Every check passed."
    output.line(verdict, style="bold red" if data.failed else "bold green")


def doctor(
    ctx: typer.Context,
    *,
    json_output: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
    offline: Annotated[bool, typer.Option("--offline", help="Check local state only.")] = False,
) -> None:
    """Check the paths, the database's revision, and every official source's reachability."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    with open_session(context, output) as (database, problem, created):
        report = asyncio.run(
            diagnose(
                settings_problem=context.problem,
                settings_file_exists=context.settings_file_exists,
                database=database,
                database_problem=problem,
                created=created,
                offline=offline,
                network=context.network,
                now=context.runtime.now(),
            )
        )
    data = _data(context, report, offline=offline)
    code = EXIT_FAILED if report.failed else EXIT_OK
    if json_output:
        output.document(
            DoctorDocument(generated_at=context.runtime.now(), disclaimer=NOTICE, data=data)
        )
        raise typer.Exit(code)
    _print(output, data)
    output.notice()
    raise typer.Exit(code)
