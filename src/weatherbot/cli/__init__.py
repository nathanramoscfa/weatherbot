# src/weatherbot/cli/__init__.py
"""Command-line layer: Typer commands over the services.

The cli layer sits above the services layer, with the web layer. It holds no business
logic of its own: each command opens the database, calls a service, and prints the result
as Rich tables in a terminal, plain text otherwise, or one JSON document with ``--json``.
"""

from typing import Annotated

import typer

from weatherbot import __version__
from weatherbot.cli import doctor as doctor_command
from weatherbot.cli import locations, snapshots
from weatherbot.cli import replay as replay_command
from weatherbot.cli import status as status_command
from weatherbot.cli.runtime import Runtime, start

app = typer.Typer(
    name="weatherbot",
    help="A personal hurricane-threat monitor. Informational only; never a substitute "
    "for official guidance.",
    no_args_is_help=True,
)
app.add_typer(locations.app)
app.command("fetch")(snapshots.fetch)
app.command("storms")(snapshots.storms)
app.command("alerts")(snapshots.alerts)
app.command("status")(status_command.status)
app.command("replay")(replay_command.replay)
app.command("doctor")(doctor_command.doctor)


def _print_version_and_exit(*, value: bool) -> None:
    """Print the version string alone and exit, when ``--version`` was given.

    Args:
        value: Whether the ``--version`` flag was passed.

    Raises:
        Exit: With status 0 after printing, so Typer skips every other step.
    """
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    ctx: typer.Context,
    *,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version_and_exit,
            is_eager=True,
            help="Print the version and exit.",
        ),
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Log at DEBUG, to standard error.")
    ] = False,
) -> None:
    """Weatherbot: a personal hurricane-threat monitor."""
    del version  # handled eagerly by its callback
    runtime = ctx.obj if isinstance(ctx.obj, Runtime) else Runtime()
    ctx.meta["weatherbot"] = start(runtime, verbose=verbose)
