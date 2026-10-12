# src/weatherbot/cli/__init__.py
"""Command-line layer: Typer commands over the services.

The cli layer sits above the services layer, with the web layer. It holds no business
logic of its own.
"""

from typing import Annotated

import typer

from weatherbot import __version__

app = typer.Typer(
    name="weatherbot",
    help="A personal hurricane-threat monitor. Informational only; never a substitute "
    "for official guidance.",
    no_args_is_help=True,
)


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
) -> None:
    """Weatherbot: a personal hurricane-threat monitor."""
