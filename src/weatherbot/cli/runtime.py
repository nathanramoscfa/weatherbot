# src/weatherbot/cli/runtime.py
"""What every command shares: its runtime, its output, and the database it opens.

``Runtime`` is what a command may be handed through Typer's context object: the
environment, the fetcher factory, the toast channel's factory, the application identity's
store, the clock, and whether output is a terminal. The tests pass one, with a fake toast
and a fake registry; a real run uses the defaults. ``Context.channels`` is the log with the
toast beside it. ``Output`` prints Rich tables to a terminal and plain text otherwise, and
keeps standard output to exactly one JSON document under ``--json``. ``open_session``
opens the database, prints the disclaimer's essentials the first time, and turns the
services' errors into messages and exit codes: 0 complete, 1 a partial or failed snapshot
or a failed check, and 2 a usage error.
"""

import sys
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, NoReturn

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table
from rich.text import Text

from weatherbot.services.config import AppPaths, ConfigError, Settings, load_settings
from weatherbot.services.disclaimer import ESSENTIALS, NOTICE, record_first_showing
from weatherbot.services.logs import configure_logging
from weatherbot.services.network import FetcherFactory, Network, default_fetcher
from weatherbot.services.notifications import Channel, LogChannel
from weatherbot.services.persistence.database import Database, DatabaseError, open_database
from weatherbot.services.persistence.repositories import SettingsRepository
from weatherbot.services.toast import Identity, system_identity, toast_channel

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_USAGE: Final = 2


def _now() -> datetime:
    return datetime.now(UTC)


type ToastFactory = Callable[[Settings], Channel]


@dataclass(frozen=True)
class Runtime:
    """A command's environment; tests hand one over as Typer's context object."""

    environ: Mapping[str, str] | None = None
    make_fetcher: FetcherFactory = default_fetcher
    make_toast: ToastFactory = toast_channel
    """The toast channel for the settings, as ``make_fetcher`` is the network."""
    identity: Callable[[], Identity] = system_identity
    """The toast's application identity: the registry on Windows, none elsewhere."""
    now: Callable[[], datetime] = _now
    terminal: bool | None = None
    """``None``: ask the console; ``True`` or ``False`` forces Rich tables or plain text."""
    width: int | None = None


@dataclass
class Context:
    """The runtime, the paths, and the settings, resolved once per invocation."""

    runtime: Runtime
    paths: AppPaths | None
    settings: Settings
    problem: str | None = None
    """Why the paths or the settings could not be resolved, if they could not."""
    settings_file_exists: bool = False

    @property
    def network(self) -> Network:
        """The timeout setting and the runtime's fetcher factory."""
        return Network(self.settings.http.timeout_seconds, self.runtime.make_fetcher)

    @property
    def channels(self) -> tuple[Channel, ...]:
        """The delivery channels: the in-app log, and the runtime's toast beside it."""
        return (LogChannel(), self.runtime.make_toast(self.settings))


def start(runtime: Runtime, *, verbose: bool) -> Context:
    """Resolve the paths and the settings, then configure logging once.

    Args:
        runtime: The runtime.
        verbose: Log at DEBUG regardless of the settings.

    Returns:
        The context; a configuration problem is kept for the command to report.
    """
    paths: AppPaths | None = None
    settings = Settings()
    problem: str | None = None
    exists = False
    try:
        paths = AppPaths.resolve(runtime.environ)
        exists = paths.settings_path.is_file()
        settings = load_settings(paths, runtime.environ)
    except ConfigError as error:
        problem = str(error)
    configure_logging("DEBUG" if verbose else settings.logging.level)
    return Context(runtime, paths, settings, problem, exists)


def context_of(ctx: typer.Context) -> Context:
    """Return the context the main callback stored.

    Args:
        ctx: Typer's context.

    Returns:
        The context.
    """
    found: object = ctx.find_root().meta["weatherbot"]
    if not isinstance(found, Context):  # pragma: no cover - the callback always sets it
        message = "the main callback did not run"
        raise TypeError(message)
    return found


@dataclass
class Output:
    """A command's output: Rich in a terminal, plain text otherwise, or one JSON document."""

    runtime: Runtime
    json_mode: bool = False
    out: Console = field(init=False)
    err: Console = field(init=False)

    def __post_init__(self) -> None:
        """Create the consoles; each finds ``sys.stdout`` or ``sys.stderr`` when it prints."""
        options = {"force_terminal": self.runtime.terminal, "width": self.runtime.width}
        self.out = Console(highlight=False, emoji=False, **options)  # pyright: ignore[reportArgumentType] - two keyword arguments
        self.err = Console(stderr=True, highlight=False, emoji=False, **options)  # pyright: ignore[reportArgumentType] - two keyword arguments

    @property
    def rich(self) -> bool:
        """Whether standard output is a terminal that gets Rich tables."""
        return self.out.is_terminal if self.runtime.terminal is None else self.runtime.terminal

    def line(self, text: str = "", *, style: str | None = None) -> None:
        """Print a line to standard output as given: no markup is interpreted.

        Args:
            text: The text.
            style: A Rich style, used in a terminal only.
        """
        self.out.print(
            Text(text, style=style or "") if self.rich else text, markup=False, soft_wrap=True
        )

    def note(self, text: str) -> None:
        """Print a line to standard error, as given.

        Args:
            text: The text.
        """
        self.err.print(text, markup=False, highlight=False, soft_wrap=True)

    def table(self, title: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        """Print a table: Rich in a terminal, aligned plain text otherwise.

        Args:
            title: The table's title.
            columns: The column headings.
            rows: The cells, already text.
        """
        if self.rich:
            table = Table(title=title, title_justify="left", show_lines=False)
            for column in columns:
                table.add_column(column, overflow="fold")
            for row in rows:
                table.add_row(*(Text(cell) for cell in row))
            self.out.print(table)
            return
        self.line(title)
        widths = [
            max(len(cells[index]) for cells in (columns, *rows)) for index in range(len(columns))
        ]
        for cells in (columns, *rows):
            self.line(
                "  ".join(
                    cell.ljust(width) for cell, width in zip(cells, widths, strict=True)
                ).rstrip()
            )

    def document(self, document: BaseModel) -> None:
        """Print one JSON document to standard output, and nothing else.

        Args:
            document: The document.
        """
        sys.stdout.write(f"{document.model_dump_json(indent=2)}\n")

    def notice(self) -> None:
        """End a read command with the one-line disclaimer notice (not under ``--json``)."""
        if not self.json_mode:
            self.line()
            self.line(NOTICE, style="dim")

    def essentials(self) -> None:
        """Print the disclaimer's essentials: to standard error under ``--json``."""
        write = self.note if self.json_mode else self.line
        write("DISCLAIMER")
        for paragraph in ESSENTIALS:
            write(paragraph)
        write("")


def fail(output: Output, message: str, code: int = EXIT_FAILED) -> NoReturn:
    """Print an error to standard error and exit.

    Args:
        output: The command's output.
        message: The error, free of coordinates.
        code: The exit status.

    Raises:
        Exit: Always.
    """
    output.note(f"Error: {message}")
    raise typer.Exit(code)


def _first_run(context: Context, output: Output, database: Database) -> None:
    settings = SettingsRepository(database.engine, now=context.runtime.now)
    if record_first_showing(settings, context.runtime.now):
        output.essentials()


@contextmanager
def open_session(context: Context, output: Output) -> Generator[Database]:
    """Open the database, and print the disclaimer's essentials the first time.

    Args:
        context: The invocation's context.
        output: The command's output.

    Yields:
        The open database, closed when the block ends.

    Raises:
        Exit: With status 1 when the configuration or the database is unusable.
    """
    if context.paths is None or context.problem:
        fail(output, context.problem or "the configuration is unusable")
    try:
        database = open_database(context.paths)
    except DatabaseError as error:
        fail(output, str(error))
    with database:
        _first_run(context, output, database)
        yield database


@contextmanager
def open_tolerant_session(
    context: Context, output: Output
) -> Generator[tuple[Database | None, str | None, bool]]:
    """Open the database if it can be opened, for a command that reports a failure.

    The disclaimer's essentials print the first time, and every time when the database
    cannot record that they did.

    Args:
        context: The invocation's context.
        output: The command's output.

    Yields:
        The database or ``None``, why it did not open, and whether opening created it.
    """
    if context.paths is None:
        output.essentials()
        yield None, context.problem, False
        return
    created = not context.paths.database_path.exists()
    try:
        database = open_database(context.paths)
    except DatabaseError as error:
        output.essentials()
        yield None, str(error), False
        return
    with database:
        _first_run(context, output, database)
        yield database, None, created
