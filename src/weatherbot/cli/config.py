# src/weatherbot/cli/config.py
"""``weatherbot config show`` and ``config path``: the effective settings, and the files.

``config show`` prints every setting's table, key, effective value, and origin: its
default, ``weatherbot.toml``, or the environment variable that overrides it, which it
names. No setting is a secret. ``config path`` prints where the settings file, the data
directory, the database, its backups, and the lock files live; the paths are the
operator's own and go to the operator's terminal only.
"""

from typing import Annotated

import typer

from weatherbot.cli.documents import (
    ConfigData,
    ConfigDocument,
    ConfigPathData,
    ConfigPathDocument,
    SettingEntry,
)
from weatherbot.cli.runtime import EXIT_OK, Output, context_of, fail
from weatherbot.services.config import ConfigError, setting_origins
from weatherbot.services.disclaimer import NOTICE

app = typer.Typer(
    name="config",
    help="Show the effective settings and where Weatherbot keeps its files.",
    no_args_is_help=True,
)

JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON document.")]


def _value(value: str | float | bool) -> str:  # noqa: FBT001 - a setting's value, printed
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


@app.command("show")
def show(ctx: typer.Context, *, json_output: JsonOption = False) -> None:
    """Print every setting's effective value and where it came from."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    paths = context.paths
    if paths is None or context.problem:
        fail(output, context.problem or "the configuration is unusable")
    try:
        origins = setting_origins(paths, context.runtime.environ)
    except ConfigError as error:
        fail(output, str(error))
    data = ConfigData(
        settings_file=str(paths.settings_path),
        settings_file_exists=context.settings_file_exists,
        settings=tuple(
            SettingEntry(
                table=item.table,
                key=item.key,
                value=item.value,
                origin=item.origin,
                variable=item.variable,
            )
            for item in origins
        ),
    )
    if json_output:
        output.document(
            ConfigDocument(generated_at=context.runtime.now(), disclaimer=NOTICE, data=data)
        )
        raise typer.Exit(EXIT_OK)
    read = (
        "read"
        if data.settings_file_exists
        else "not found: every value not overridden is its default"
    )
    output.line(f"Settings file: {data.settings_file} ({read})")
    output.table(
        "Settings",
        ("Setting", "Value", "Origin"),
        [
            (
                f"[{entry.table}] {entry.key}",
                _value(entry.value),
                entry.variable if entry.origin == "environment" else entry.origin,
            )
            for entry in data.settings
        ],
    )
    output.line(
        "Each value comes from its environment variable, then weatherbot.toml, then its "
        "default; the variables are WEATHERBOT_<TABLE>_<KEY>, except WEATHERBOT_LOG_LEVEL."
    )
    raise typer.Exit(EXIT_OK)


@app.command("path")
def path(ctx: typer.Context, *, json_output: JsonOption = False) -> None:
    """Print where the settings file, the database, its backups, and the locks live."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    paths = context.paths
    if paths is None:
        fail(output, context.problem or "the configuration is unusable")
    data = ConfigPathData(
        config_dir=str(paths.config_dir),
        settings_file=str(paths.settings_path),
        data_dir=str(paths.data_dir),
        database_file=str(paths.database_path),
        backup_dir=str(paths.backup_dir),
        cycle_lock_file=str(paths.cycle_lock_path),
        migrate_lock_file=str(paths.migrate_lock_path),
    )
    if json_output:
        output.document(
            ConfigPathDocument(generated_at=context.runtime.now(), disclaimer=NOTICE, data=data)
        )
        raise typer.Exit(EXIT_OK)
    output.table(
        "Paths",
        ("What", "Path"),
        [
            ("Configuration directory", data.config_dir),
            ("Settings file", data.settings_file),
            ("Data directory", data.data_dir),
            ("Database", data.database_file),
            ("Backups", data.backup_dir),
            ("Cycle lock", data.cycle_lock_file),
            ("Migration lock", data.migrate_lock_file),
        ],
    )
    raise typer.Exit(EXIT_OK)
