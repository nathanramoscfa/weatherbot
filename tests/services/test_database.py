# tests/services/test_database.py
"""Opening the database: migrations, the backup before them, and refusal.

The history tests walk the package's script directory, so every later revision joins
them without an edit. The backup and failure tests add a revision to a copy of the
scripts, because the baseline is the only revision so far.
"""

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text

from weatherbot.services.config import AppPaths
from weatherbot.services.persistence import database as db
from weatherbot.services.persistence.database import (
    MIGRATIONS_DIRECTORY,
    DatabaseError,
    MigrationFailedError,
    UnknownRevisionError,
    alembic_config,
    create_database_engine,
    current_revision,
    head_revision,
    open_database,
)
from weatherbot.services.persistence.tables import Base

HEAD = head_revision()
REVISIONS = [
    script.revision for script in ScriptDirectory(str(MIGRATIONS_DIRECTORY)).walk_revisions()
]
STAMP = datetime(2026, 10, 17, 12, 30, 5, tzinfo=UTC)
EXTRA_TABLE = """
def upgrade() -> None:
    op.create_table("probe", sa.Column("id", sa.Integer(), primary_key=True))


def downgrade() -> None:
    op.drop_table("probe")
"""
FAILING = """
def upgrade() -> None:
    op.create_table("probe", sa.Column("id", sa.Integer(), primary_key=True))
    op.execute("SELECT no_such_function()")


def downgrade() -> None:
    op.drop_table("probe")
"""


@pytest.fixture
def paths() -> AppPaths:
    return AppPaths.resolve()


def _migrate(engine: Engine, target: str, migrations: Path = MIGRATIONS_DIRECTORY) -> None:
    with engine.begin() as connection:
        config = alembic_config(connection, migrations)
        if target == "base":
            command.downgrade(config, "base")
        else:
            command.upgrade(config, target)


@pytest.fixture
def engine(paths: AppPaths) -> Iterator[Engine]:
    paths.data_dir.mkdir(parents=True)
    created = create_database_engine(paths.database_path)
    yield created
    created.dispose()


def _with_revision(tmp_path: Path, body: str) -> Path:
    """Copy the package's scripts and add revision ``0002`` after the head."""
    migrations = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIRECTORY, migrations, ignore=shutil.ignore_patterns("__pycache__"))
    header = (
        '"""A test revision."""\n\nimport sqlalchemy as sa\nfrom alembic import op\n\n'
        f'revision = "0002"\ndown_revision = "{HEAD}"\nbranch_labels = None\ndepends_on = None\n'
    )
    (migrations / "versions" / "0002_probe.py").write_text(header + body, encoding="utf-8")
    return migrations


def _tables(path: Path) -> set[str]:
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {name for (name,) in rows}


def _revision_of(path: Path) -> str | None:
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None


# Creation and the history --------------------------------------------------------------------


def test_a_new_database_is_created_at_head_without_a_backup(paths: AppPaths) -> None:
    with open_database(paths) as opened:
        assert opened.revision == HEAD
        assert current_revision(opened.engine) == HEAD
        assert opened.backup_path is None
    assert not paths.backup_dir.exists()
    assert set(Base.metadata.tables) <= _tables(paths.database_path)


def test_every_connection_sets_foreign_keys_wal_and_a_busy_timeout(paths: AppPaths) -> None:
    with open_database(paths) as opened:
        for _ in range(2):
            with opened.engine.connect() as connection:
                assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
                assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
                timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()
                assert timeout == db.BUSY_TIMEOUT_MS
            opened.engine.dispose()


def test_downgrade_to_base_then_upgrade_to_head(paths: AppPaths) -> None:
    with open_database(paths) as opened:
        _migrate(opened.engine, "base")
        assert current_revision(opened.engine) is None
        assert inspect(opened.engine).get_table_names() == ["alembic_version"]
        _migrate(opened.engine, "head")
        assert current_revision(opened.engine) == HEAD
        assert set(Base.metadata.tables) <= set(inspect(opened.engine).get_table_names())


@pytest.mark.parametrize("revision", ["base", *REVISIONS])
def test_every_revision_in_the_history_upgrades_to_head(
    paths: AppPaths, engine: Engine, revision: str
) -> None:
    _migrate(engine, "head")
    _migrate(engine, revision)
    engine.dispose()

    with open_database(paths, now=lambda: STAMP) as opened:
        assert opened.revision == HEAD
        assert current_revision(opened.engine) == HEAD
        assert (opened.backup_path is None) == (revision == HEAD)


def test_the_tables_and_the_migrations_agree(paths: AppPaths) -> None:
    with open_database(paths) as opened, opened.engine.begin() as connection:
        command.check(alembic_config(connection))


# The backup before an upgrade ----------------------------------------------------------------


def test_an_upgrade_from_a_behind_revision_backs_up_first_through_the_online_api(
    tmp_path: Path, paths: AppPaths, engine: Engine
) -> None:
    migrations = _with_revision(tmp_path, EXTRA_TABLE)
    _migrate(engine, HEAD, migrations)
    engine.dispose()
    # A row that lives only in the write-ahead log while another connection stays open:
    # a raw copy of the database file would miss it; the online backup API does not.
    holder = sqlite3.connect(paths.database_path)
    holder.execute("SELECT count(*) FROM settings").fetchall()  # attach it to the WAL
    writer = sqlite3.connect(paths.database_path)
    writer.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES ('probe', '1', '2026-10-17')"
    )
    writer.commit()
    writer.close()
    raw_copy = tmp_path / "raw-copy.sqlite3"
    shutil.copyfile(paths.database_path, raw_copy)

    try:
        with open_database(paths, migrations=migrations, now=lambda: STAMP) as opened:
            assert opened.revision == "0002"
            backup = opened.backup_path
    finally:
        holder.close()

    assert backup is not None
    assert backup == paths.backup_dir / f"weatherbot-20261017T123005Z-{HEAD}.sqlite3"
    assert _revision_of(backup) == HEAD
    assert "probe" not in _tables(backup)
    with closing(sqlite3.connect(backup)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("SELECT key FROM settings").fetchall() == [("probe",)]
    with closing(sqlite3.connect(raw_copy)) as connection:
        assert connection.execute("SELECT key FROM settings").fetchall() == []
    assert _revision_of(paths.database_path) == "0002"


def test_a_failed_upgrade_keeps_its_backup_and_names_it(
    tmp_path: Path, paths: AppPaths, engine: Engine
) -> None:
    migrations = _with_revision(tmp_path, FAILING)
    _migrate(engine, HEAD, migrations)
    engine.dispose()

    with pytest.raises(MigrationFailedError) as failure:
        open_database(paths, migrations=migrations, now=lambda: STAMP)

    backup = failure.value.backup_path
    assert str(backup) in str(failure.value)
    assert "Migration failed at start-up" in str(failure.value)
    assert backup.is_file()
    assert _revision_of(backup) == HEAD
    # The upgrade ran in one transaction, so nothing of it stayed behind.
    assert _revision_of(paths.database_path) == HEAD
    assert "probe" not in _tables(paths.database_path)


def test_a_backup_never_overwrites_another(tmp_path: Path, paths: AppPaths, engine: Engine) -> None:
    migrations = _with_revision(tmp_path, EXTRA_TABLE)
    _migrate(engine, HEAD, migrations)
    engine.dispose()
    paths.backup_dir.mkdir()
    taken = paths.backup_dir / f"weatherbot-20261017T123005Z-{HEAD}.sqlite3"
    taken.write_bytes(b"an earlier copy")

    with pytest.raises(DatabaseError, match="already exists"):
        open_database(paths, migrations=migrations, now=lambda: STAMP)

    assert taken.read_bytes() == b"an earlier copy"
    assert _revision_of(paths.database_path) == HEAD


# Refusal -------------------------------------------------------------------------------------


def test_a_revision_the_code_does_not_know_refuses_to_open(paths: AppPaths, engine: Engine) -> None:
    _migrate(engine, "head")
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '9999'"))
    engine.dispose()

    with pytest.raises(UnknownRevisionError) as refusal:
        open_database(paths)

    message = str(refusal.value)
    assert "9999" in message
    assert "Upgrade Weatherbot" in message
    assert "restore a backup" in message
    assert _revision_of(paths.database_path) == "9999"
    assert not paths.backup_dir.exists()


def test_a_file_with_tables_but_no_revision_is_refused(paths: AppPaths) -> None:
    paths.data_dir.mkdir(parents=True)
    with closing(sqlite3.connect(paths.database_path)) as connection:
        connection.execute("CREATE TABLE other (id INTEGER)")

    with pytest.raises(DatabaseError, match="not Weatherbot's"):
        open_database(paths)


def test_the_head_is_the_last_revision_of_the_history() -> None:
    assert REVISIONS[0] == HEAD
    assert ScriptDirectory(str(MIGRATIONS_DIRECTORY)).get_base() == REVISIONS[-1]
