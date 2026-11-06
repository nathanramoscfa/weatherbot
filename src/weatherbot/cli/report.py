# src/weatherbot/cli/report.py
"""``weatherbot report``: write a self-contained HTML threat report to disk.

``weatherbot report [LOCATION] --out PATH [--force] [--with-briefing]`` builds a
privacy-reduced report from stored assessments (and, only when ``--with-briefing`` is
passed, each location's latest unwithheld stored AI briefing) and writes it atomically
via a sibling temporary file and ``os.replace``. It never loads the Anthropic SDK.
"""

import os
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from weatherbot.cli.runtime import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    Output,
    context_of,
    fail,
    open_session,
)
from weatherbot.services.persistence.repositories import LocationNotFoundError
from weatherbot.services.report import (
    NoReportAssessmentError,
    ReportService,
    render_report,
)


def _write_atomic(out: Path, content: str) -> None:
    """Write ``content`` to a temporary file in ``out.parent`` and replace ``out``."""
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{out.name}.",
        suffix=".tmp",
        dir=out.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp_path, out)  # noqa: PTH105 - atomic os.replace per step specification
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def report(
    ctx: typer.Context,
    location: Annotated[
        str | None,
        typer.Argument(help="Export this location only; every stored location by default."),
    ] = None,
    *,
    out: Annotated[
        Path,
        typer.Option("--out", help="Destination path for the self-contained HTML report."),
    ],
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite the destination file if it already exists."),
    ] = False,
    with_briefing: Annotated[
        bool,
        typer.Option(
            "--with-briefing",
            help="Include each location's latest unwithheld stored AI briefing.",
        ),
    ] = False,
) -> None:
    """Write a self-contained, offline HTML threat report to ``--out``."""
    context = context_of(ctx)
    output = Output(context.runtime)

    parent = out.parent
    if not parent.exists() or not parent.is_dir():
        fail(output, f"parent directory does not exist: {parent}", EXIT_USAGE)
    if out.is_dir():
        fail(output, f"destination path is a directory: {out}", EXIT_USAGE)
    if out.exists() and not force:
        fail(
            output,
            f"destination file already exists: {out} (pass --force to overwrite)",
            EXIT_USAGE,
        )

    with open_session(context, output) as database:
        service = ReportService(database.engine, now=context.runtime.now)
        try:
            data = service.build(location, with_briefing=with_briefing)
        except LocationNotFoundError:
            fail(output, f"no location is named {location!r}", EXIT_USAGE)
        except NoReportAssessmentError as error:
            fail(output, str(error), EXIT_FAILED)

    rendered = render_report(data)
    if out.exists() and not force:
        fail(
            output,
            f"destination file already exists: {out} (pass --force to overwrite)",
            EXIT_USAGE,
        )
    _write_atomic(out, rendered)
    output.line(f"Wrote report to {out}")
    output.notice()
    raise typer.Exit(EXIT_OK)
