# src/weatherbot/services/ai/guard.py
"""The AI engine: the database opened so that the AI package can write only its own tables.

``ai_engine(path)`` is ``create_database_engine(path)`` with one more ``connect``
listener, which installs a SQLite authorizer on every connection it makes. The authorizer
refuses an ``INSERT``, ``UPDATE``, or ``DELETE`` on any table but ``ai_calls`` and
``ai_outputs``, and every statement that changes the schema or the file's shape
(``CREATE``, ``DROP``, ``ALTER``, ``ATTACH``, ``DETACH``, ``REINDEX``, ``ANALYZE``); it
allows reads, pragmas, and transactions. So no path through the package, a prompt-injected
tool call included, can write an assessment, a storm, an alert, a snapshot, a location, a
setting, or a notification. The AI engine never migrates (``open_database`` on the normal
engine does), and whoever creates one disposes of it.
"""

import sqlite3
from pathlib import Path
from typing import Final

from sqlalchemy import Engine, event
from sqlalchemy.pool import ConnectionPoolEntry

from weatherbot.services.persistence.database import create_database_engine

AI_TABLES: Final = frozenset({"ai_calls", "ai_outputs"})
ROW_WRITES: Final = frozenset({sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE})
SCHEMA_CHANGES: Final = frozenset(
    {
        sqlite3.SQLITE_CREATE_INDEX,
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_INDEX,
        sqlite3.SQLITE_CREATE_TEMP_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
        sqlite3.SQLITE_CREATE_TEMP_VIEW,
        sqlite3.SQLITE_CREATE_TRIGGER,
        sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_CREATE_VTABLE,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_INDEX,
        sqlite3.SQLITE_DROP_TEMP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_TRIGGER,
        sqlite3.SQLITE_DROP_TEMP_VIEW,
        sqlite3.SQLITE_DROP_TRIGGER,
        sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_DROP_VTABLE,
        sqlite3.SQLITE_ALTER_TABLE,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_REINDEX,
        sqlite3.SQLITE_ANALYZE,
    }
)


def _authorize(
    action: int, arg1: str | None, _arg2: str | None, _database: str | None, _source: str | None
) -> int:
    """Refuse a row write outside the AI tables and every schema change; allow the rest."""
    if action in ROW_WRITES and arg1 not in AI_TABLES:
        return sqlite3.SQLITE_DENY
    if action in SCHEMA_CHANGES:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _install_authorizer(dbapi_connection: sqlite3.Connection, _: ConnectionPoolEntry) -> None:
    dbapi_connection.set_authorizer(_authorize)


def ai_engine(path: Path) -> Engine:
    """Open the database file for the AI package, behind the authorizer.

    Args:
        path: The database file, already at the head revision.

    Returns:
        The engine; no connection is made yet. Dispose of it when done.
    """
    engine = create_database_engine(path)
    event.listen(engine, "connect", _install_authorizer)
    return engine
