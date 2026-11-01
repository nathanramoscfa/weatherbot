# tests/ai/test_ai_guard.py
"""The AI engine's authorizer: no write outside the AI tables, no schema change, reads allowed.

The row-write cases are parametrized over ``Base.metadata``, so a table a later revision
adds is refused without an edit here.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DatabaseError

from weatherbot.services.ai.guard import AI_TABLES, ai_engine
from weatherbot.services.ai.ledger import Ledger
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.tables import Base

OFFICIAL_TABLES = sorted(set(Base.metadata.tables) - AI_TABLES)
NOW = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
DENIED = "not authorized"
ALLOWANCE = 500_000


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


@pytest.fixture
def guarded(database: Database) -> Iterator[Engine]:
    engine = ai_engine(database.path)
    yield engine
    engine.dispose()


def _first_column(table: str) -> str:
    return next(iter(Base.metadata.tables[table].columns)).name


def test_the_ai_tables_are_the_ledger_and_the_outputs() -> None:
    assert frozenset({"ai_calls", "ai_outputs"}) == AI_TABLES
    assert "ai_calls" in Base.metadata.tables
    assert len(OFFICIAL_TABLES) == len(Base.metadata.tables) - 1


@pytest.mark.parametrize("table", OFFICIAL_TABLES)
@pytest.mark.parametrize("verb", ["insert", "update", "delete"])
def test_a_row_write_outside_the_ai_tables_is_refused(
    guarded: Engine, table: str, verb: str
) -> None:
    column = _first_column(table)
    statement = {
        "insert": f"INSERT INTO {table} DEFAULT VALUES",
        "update": f"UPDATE {table} SET {column} = {column}",  # noqa: S608 - as above
        "delete": f"DELETE FROM {table}",  # noqa: S608 - as above
    }[verb]

    with pytest.raises(DatabaseError, match=DENIED), guarded.begin() as connection:
        connection.execute(text(statement))


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE intruder (id INTEGER)",
        "CREATE TEMP TABLE intruder (id INTEGER)",
        "CREATE INDEX ix_intruder ON ai_calls (kind)",
        "CREATE VIEW intruder AS SELECT 1",
        "CREATE TRIGGER intruder AFTER INSERT ON ai_calls BEGIN SELECT 1; END",
        "DROP TABLE locations",
        "DROP TABLE ai_calls",
        "DROP INDEX ix_ai_calls_day",
        "ALTER TABLE locations ADD COLUMN intruder TEXT",
        "ALTER TABLE ai_calls ADD COLUMN intruder TEXT",
        "ATTACH DATABASE ':memory:' AS intruder",
        "REINDEX ai_calls",
        "ANALYZE",
    ],
)
def test_every_schema_change_is_refused(guarded: Engine, statement: str) -> None:
    with pytest.raises(DatabaseError, match=DENIED), guarded.begin() as connection:
        connection.execute(text(statement))


@pytest.mark.parametrize("table", sorted(Base.metadata.tables))
def test_reads_are_allowed_on_every_table(guarded: Engine, table: str) -> None:
    with guarded.connect() as connection:
        rows = connection.execute(text(f"SELECT * FROM {table} LIMIT 1")).all()  # noqa: S608 - metadata names

    assert rows == []


def test_pragmas_and_ai_table_writes_are_allowed(guarded: Engine) -> None:
    with guarded.begin() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        connection.execute(
            text(
                "INSERT INTO ai_calls (kind, status, day, started_at, ceiling_micro_usd, "
                "prices_as_of) VALUES ('pause', 'control', '2026-10-31', '2026-10-31', 0, "
                "'2026-10-30')"
            )
        )
        connection.execute(text("UPDATE ai_calls SET status = 'control'"))
        connection.execute(text("DELETE FROM ai_calls"))


def test_the_ledger_works_entirely_behind_the_authorizer(guarded: Engine) -> None:
    ledger = Ledger(guarded, cap_micro_usd=1_000_000, now=lambda: NOW)

    reservation = ledger.reserve("briefing", "claude-sonnet-5-5", "Somewhere", None, 10_000)
    ledger.pause()
    ledger.resume()
    ledger.allow(ALLOWANCE)

    assert reservation.id == 1
    assert ledger.today().allowance_micro_usd == ALLOWANCE


def test_the_normal_engine_on_the_same_file_is_unaffected(
    database: Database, guarded: Engine
) -> None:
    with guarded.connect() as connection:
        connection.execute(text("SELECT 1"))
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO settings (key, value, updated_at) VALUES ('probe', '1', '2026-10-31')"
            )
        )
