# src/weatherbot/services/persistence/database.py
"""Opening the database: connection settings, a backup before every migration, and refusal.

``open_database(paths)`` creates a new database at the Alembic head without a backup. An
existing database behind the head is first copied through SQLite's online backup API,
which is consistent under WAL (a raw file copy is not), to
``backups/weatherbot-<UTC stamp>-<revision>.sqlite3``, and then upgraded; the copy is the
rollback (docs/roadmap/ROADMAP.md, "Data and schema migrations" and "Rollback"). A
database at a revision this code does not know was written by a newer package: it refuses
to open, and nothing here ever downgrades. Two processes that open a database behind the
head take ``migrate.lock`` in turn, so it is backed up and upgraded once.

A transaction that writes begins ``BEGIN IMMEDIATE`` (``writing_session`` and
``immediate``), so it takes SQLite's write lock before it reads: a plain deferred
``BEGIN`` that reads and then writes while another process commits fails at once with
``database is locked``, where an immediate one waits up to the busy timeout. A read-only
transaction stays deferred.
"""

import logging
import sqlite3
from collections.abc import Callable, Generator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Self

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import ConnectionPoolEntry

from weatherbot.services.config import AppPaths, ensure_directory
from weatherbot.services.locks import LockBusyError, ProcessLock

LOGGER: Final = logging.getLogger("weatherbot.services.persistence")

MIGRATIONS_DIRECTORY: Final = Path(__file__).resolve().parent / "migrations"
BUSY_TIMEOUT_MS: Final = 30_000
IMMEDIATE: Final = "weatherbot_begin_immediate"
"""The execution option that makes a connection's transactions begin ``IMMEDIATE``."""
MIGRATE_LOCK_WAIT_S: Final = 600
BASE: Final = "base"
"""How a backup's name spells a database with no revision applied."""
RUNBOOK: Final = "docs/roadmap/ROADMAP.md, Runbooks, 'Migration failed at start-up'"


class DatabaseError(Exception):
    """The database cannot be opened as it is."""


class UnknownRevisionError(DatabaseError):
    """The database is at a revision this package does not know."""


class MigrationFailedError(DatabaseError):
    """An upgrade failed. The copy made before it is kept, and ``backup_path`` names it."""

    def __init__(self, message: str, backup_path: Path) -> None:
        """Create the error.

        Args:
            message: What failed, and where the backup is.
            backup_path: The copy made before the upgrade.
        """
        super().__init__(message)
        self.backup_path = backup_path


def _configure_connection(dbapi_connection: sqlite3.Connection, _: ConnectionPoolEntry) -> None:
    """Set every connection's pragmas, and let SQLAlchemy own the transactions.

    pysqlite's own transaction handling leaves DDL outside a transaction, so a failed
    migration could stop half done; with it off, ``_begin`` opens each transaction.
    """
    dbapi_connection.isolation_level = None
    with closing(dbapi_connection.cursor()) as cursor:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS:d}")


def _begin(connection: Connection) -> None:
    immediate = connection.get_execution_options().get(IMMEDIATE, False)
    connection.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")


def immediate(engine: Engine) -> Engine:
    """The same engine, sharing its pool, whose transactions begin ``IMMEDIATE``.

    Args:
        engine: A database engine from ``create_database_engine``.

    Returns:
        The engine for writing transactions.
    """
    return engine.execution_options(**{IMMEDIATE: True})


@contextmanager
def writing_session(engine: Engine) -> Generator[Session]:
    """Open a session in a writing transaction that begins ``IMMEDIATE`` and commits after.

    Args:
        engine: The database.

    Yields:
        The session; the transaction commits when the block ends, or rolls back.
    """
    with Session(immediate(engine)) as session, session.begin():
        yield session


def create_database_engine(path: Path) -> Engine:
    """Create the engine of a database file: foreign keys on, WAL, and a busy timeout.

    Args:
        path: The database file.

    Returns:
        The engine; no connection is made yet.
    """
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    event.listen(engine, "connect", _configure_connection)
    event.listen(engine, "begin", _begin)
    return engine


def alembic_config(connection: Connection, migrations: Path = MIGRATIONS_DIRECTORY) -> Config:
    """Configure Alembic in code, for one open connection.

    Args:
        connection: The connection the migrations run on.
        migrations: The migration scripts.

    Returns:
        The configuration.
    """
    config = Config()
    config.set_main_option("script_location", str(migrations))
    config.attributes["connection"] = connection
    return config


def head_revision(migrations: Path = MIGRATIONS_DIRECTORY) -> str:
    """Return the head revision this package's migrations reach.

    Args:
        migrations: The migration scripts.

    Returns:
        The head revision.

    Raises:
        DatabaseError: The scripts have more than one head.
    """
    script = ScriptDirectory(str(migrations))
    head = script.get_current_head()
    if head is None:
        message = "the migrations have no single head"
        raise DatabaseError(message)
    return head


def current_revision(engine: Engine) -> str | None:
    """Return the revision a database is at, or ``None`` when none is applied.

    Args:
        engine: The database.

    Returns:
        The revision.
    """
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


@dataclass
class Database:
    """An open database at the head revision."""

    engine: Engine
    path: Path
    revision: str
    backup_path: Path | None = None
    """The copy made before this open's migration, when one ran."""

    def close(self) -> None:
        """Close every pooled connection."""
        self.engine.dispose()

    def __enter__(self) -> Self:
        """Use the database in a ``with`` block.

        Returns:
            The database.
        """
        return self

    def __exit__(self, *_: object) -> None:
        """Close the database."""
        self.close()


def _stamp(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def backup_database(source: Path, backup_dir: Path, revision: str | None, now: datetime) -> Path:
    """Copy a database through SQLite's online backup API.

    Args:
        source: The database file.
        backup_dir: Where the copy goes; created owner-only if missing.
        revision: The database's revision, for the copy's name.
        now: The instant in the copy's name.

    Returns:
        The copy.

    Raises:
        DatabaseError: A copy of that name already exists.
    """
    ensure_directory(backup_dir)
    target = backup_dir / f"weatherbot-{_stamp(now)}-{revision or BASE}.sqlite3"
    if target.exists():
        message = f"a backup named {target.name} already exists"
        raise DatabaseError(message)
    with (
        closing(sqlite3.connect(source)) as reader,
        closing(sqlite3.connect(target)) as writer,
    ):
        reader.backup(writer)
    return target


def _table_names(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return inspect(connection).get_table_names()


def _upgrade(engine: Engine, migrations: Path) -> None:
    with immediate(engine).begin() as connection:
        command.upgrade(alembic_config(connection, migrations), "head")


def _migrate(
    engine: Engine, paths: AppPaths, migrations: Path, now: Callable[[], datetime]
) -> Database:
    """Bring an engine's database to the head: create, refuse, or back up and upgrade."""
    head = head_revision(migrations)
    path = paths.database_path
    current = current_revision(engine)
    known = {script.revision for script in ScriptDirectory(str(migrations)).walk_revisions()}
    if current is not None and current not in known:
        message = (
            f"the database is at revision {current}, which this version of Weatherbot "
            f"does not know: a newer version wrote it. Upgrade Weatherbot, or restore a "
            f"backup from {paths.backup_dir}; it is never downgraded automatically"
        )
        raise UnknownRevisionError(message)
    if current == head:
        return Database(engine=engine, path=path, revision=head)
    tables = _table_names(engine)
    if current is None and not tables:
        LOGGER.info("creating the database at revision %s", head)
        _upgrade(engine, migrations)
        return Database(engine=engine, path=path, revision=head)
    if current is None and tables != ["alembic_version"]:
        message = "the database file holds tables but no revision: it is not Weatherbot's"
        raise DatabaseError(message)
    engine.dispose()
    backup = backup_database(path, paths.backup_dir, current, now())
    LOGGER.info(
        "copied the database to %s before upgrading %s to %s", backup, current or BASE, head
    )
    try:
        _upgrade(engine, migrations)
    except Exception as error:
        message = (
            f"upgrading the database from {current or BASE} to {head} failed "
            f"({type(error).__name__}). The copy made first is {backup}: restore it, "
            f"install the previous version of Weatherbot, and report the failure ({RUNBOOK})"
        )
        raise MigrationFailedError(message, backup) from error
    return Database(engine=engine, path=path, revision=head, backup_path=backup)


def open_database(
    paths: AppPaths,
    *,
    migrations: Path = MIGRATIONS_DIRECTORY,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Database:
    """Open the database at the head revision, creating or upgrading it first.

    Args:
        paths: Where the database and its backups live.
        migrations: The migration scripts; tests pass their own.
        now: The clock, for a backup's name.

    Returns:
        The open database, at the head.

    Raises:
        UnknownRevisionError: A newer package wrote the database; upgrade the package or
            restore a backup.
        MigrationFailedError: The upgrade failed; the copy made before it is kept.
        DatabaseError: The file holds tables but no revision: it is not this package's.
    """
    ensure_directory(paths.data_dir)
    engine = create_database_engine(paths.database_path)
    try:
        head = head_revision(migrations)
        if current_revision(engine) == head:
            return Database(engine=engine, path=paths.database_path, revision=head)
        lock = ProcessLock(paths.migrate_lock_path)
        try:
            lock.acquire(MIGRATE_LOCK_WAIT_S)
        except LockBusyError:
            message = "another process has been migrating the database too long; try again"
            raise DatabaseError(message) from None
        try:
            # Read the revision again under the lock: another process may have migrated it.
            return _migrate(engine, paths, migrations, now)
        finally:
            lock.release()
    except BaseException:
        engine.dispose()
        raise
