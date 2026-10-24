# tests/services/test_database.py
"""Opening the database: migrations, the backup before them, and refusal.

The history tests walk the package's script directory, so every later revision joins
them without an edit. The backup and failure tests add a probe revision after the head to
a copy of the scripts, so they never depend on what the head revision creates.
"""

import hashlib
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from snapshot_support import recorded_snapshot, with_second_storm
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session

from weatherbot.services.config import AppPaths
from weatherbot.services.persistence import database as db
from weatherbot.services.persistence import repositories
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
from weatherbot.services.persistence.repositories import LocationRepository, SnapshotRepository
from weatherbot.services.persistence.tables import Base

HEAD = head_revision()
REVISIONS = [
    script.revision for script in ScriptDirectory(str(MIGRATIONS_DIRECTORY)).walk_revisions()
]
# Each merged revision's SHA-256, line endings as committed: a revision is frozen once merged.
FROZEN = {
    "0001_baseline.py": "d0e07ae21301ab7a8895607e914e9cca7dc62e2ce0b51fbdf6f8b0ef98f8505d",
    "0002_drift_warnings.py": "6ffcccb7b6da86250e57fa28d20158df74f6db7e2053f230bd6763ddebb0136a",
    "0003_assessments.py": "d2388aba5c3ab287e9953d37d36fe9f8b07d98c609129acd2c31a99bbf39681f",
    "0004_shared_geometry.py": "55d9619fdfcf2fc2566891ea603294ef18a8edcae5094d53cfe969cd3e0e6656",
    "0005_monitor.py": "f85816879172be57a0e3223da2bd99bbcaf1a0521da2895822f3e3c8e76f9520",
    "0006_notifications.py": "88ad27ba143120845fb027270935cd617f8120f970c307fa85fb5d4b6400ee69",
}
SNAPSHOT_HEX = "8f0c4d1e5b7a4c2e9d3f1a2b3c4d5e6f"
PROBE = "probe"
"""A test revision after the head, in a copy of the scripts."""
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
    """Move a database to ``target``: down to an earlier revision, else up to it."""
    with engine.begin() as connection:
        config = alembic_config(connection, migrations)
        current = MigrationContext.configure(connection).get_current_revision()
        script = ScriptDirectory(str(migrations))
        earlier = (
            {revision.revision for revision in script.iterate_revisions(current, "base")}
            if current is not None
            else set[str]()
        )
        if target == "base" or (target != current and target in earlier):
            command.downgrade(config, target)
        else:
            command.upgrade(config, target)


@pytest.fixture
def engine(paths: AppPaths) -> Iterator[Engine]:
    paths.data_dir.mkdir(parents=True)
    created = create_database_engine(paths.database_path)
    yield created
    created.dispose()


def _with_revision(tmp_path: Path, body: str) -> Path:
    """Copy the package's scripts and add the revision ``PROBE`` after the head."""
    migrations = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIRECTORY, migrations, ignore=shutil.ignore_patterns("__pycache__"))
    header = (
        '"""A test revision."""\n\nimport sqlalchemy as sa\nfrom alembic import op\n\n'
        f'revision = "{PROBE}"\ndown_revision = "{HEAD}"\nbranch_labels = None\n'
        "depends_on = None\n"
    )
    (migrations / "versions" / f"{PROBE}.py").write_text(header + body, encoding="utf-8")
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
            assert opened.revision == PROBE
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
    assert _revision_of(paths.database_path) == PROBE


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


# Revision 0003 -------------------------------------------------------------------------------

ASSESSMENT = text(
    "INSERT INTO assessments (id, location_id, snapshot_id, ruleset, as_of, level, rule, "
    "complete, thresholds, assessment, stored_at) VALUES (1, 1, :snapshot, 'r', '2026-10-17', "
    ":level, :rule, 1, '{}', '{}', '2026-10-18')"
)
COUNTS = {
    "assessments": "SELECT count(*) FROM assessments",
    "assessment_changes": "SELECT count(*) FROM assessment_changes",
    "alert_observations": "SELECT count(*) FROM alert_observations",
}


def _columns(path: Path, table: str) -> set[str]:
    with closing(sqlite3.connect(path)) as connection:
        return {
            row[0] for row in connection.execute("SELECT name FROM pragma_table_info(?)", (table,))
        }


def _rows(path: Path, statement: str) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(statement).fetchall()


def _seed_0002(path: Path) -> None:
    """A location with a snapshot that found no alert for it, written at revision 0002."""
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO locations (id, name, latitude, longitude, evacuation_order_in_effect, "
            "created_at, updated_at) VALUES (1, 'Place', 0.5, 0.5, 0, '2026-10-17', '2026-10-17')"
        )
        connection.execute(
            "INSERT INTO snapshots (id, started_at, completed_at, status) VALUES "
            "(?, '2026-10-17', '2026-10-17', 'complete')",
            (SNAPSHOT_HEX,),
        )
        connection.execute(
            "INSERT INTO alert_observations (snapshot_id, location_id, alert_id, position, "
            "found_by) VALUES (?, 1, NULL, 0, NULL)",
            (SNAPSHOT_HEX,),
        )
        connection.commit()


def test_0003_creates_the_assessment_tables_and_the_toggle_instant(
    paths: AppPaths, engine: Engine
) -> None:
    _migrate(engine, "0002")
    engine.dispose()
    _seed_0002(paths.database_path)
    tables = {"assessments", "assessment_evidence", "assessment_changes"}
    assert not tables & _tables(paths.database_path)

    with open_database(paths, now=lambda: STAMP) as opened:
        assert opened.revision == HEAD
        assert opened.backup_path is not None

    assert tables <= _tables(paths.database_path)
    assert "evacuation_order_set_at" in _columns(paths.database_path, "locations")
    assert _rows(paths.database_path, "SELECT name, evacuation_order_set_at FROM locations") == [
        ("Place", None)
    ]
    assert _rows(paths.database_path, COUNTS["alert_observations"]) == [(1,)]


def test_0003_downgrades_to_0002_without_losing_a_location_or_its_observations(
    paths: AppPaths, engine: Engine
) -> None:
    _migrate(engine, "0002")
    engine.dispose()
    _seed_0002(paths.database_path)
    _migrate(engine, "0003")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE locations SET evacuation_order_in_effect = 1, "
                "evacuation_order_set_at = '2026-10-18 12:00:00'"
            )
        )
        connection.execute(
            ASSESSMENT, {"snapshot": SNAPSHOT_HEX, "level": 4, "rule": "evacuation_order"}
        )

    _migrate(engine, "0002")
    engine.dispose()

    # A batch alteration would rebuild locations, and dropping the old table with foreign
    # keys on would delete the observations that cascade from it.
    assert current_revision(engine) == "0002"
    engine.dispose()
    assert "evacuation_order_set_at" not in _columns(paths.database_path, "locations")
    assert not {"assessments", "assessment_evidence"} & _tables(paths.database_path)
    assert _rows(paths.database_path, "SELECT name, evacuation_order_in_effect FROM locations") == [
        ("Place", 1)
    ]
    assert _rows(paths.database_path, COUNTS["alert_observations"]) == [(1,)]


def test_removing_a_location_at_0003_cascades_to_its_assessments(
    paths: AppPaths, engine: Engine
) -> None:
    _migrate(engine, "0002")
    engine.dispose()
    _seed_0002(paths.database_path)
    _migrate(engine, "head")
    with engine.begin() as connection:
        connection.execute(ASSESSMENT, {"snapshot": SNAPSHOT_HEX, "level": 1, "rule": "all_clear"})
        connection.execute(
            text(
                "INSERT INTO assessment_changes (assessment_id, position, kind, event) "
                "VALUES (1, 0, 'level_changed', '{}')"
            )
        )
        assert connection.execute(text(COUNTS["assessment_changes"])).scalar() == 1
        connection.execute(text("DELETE FROM locations"))
    engine.dispose()

    for table, statement in COUNTS.items():
        assert _rows(paths.database_path, statement) == [(0,)], table


# Revision 0004 -------------------------------------------------------------------------------

SHARED_GEOMETRY = {"geometry_contents", "snapshot_provenances", "snapshot_geometries"}
PRODUCT = text(
    "INSERT INTO product_geometries (snapshot_id, advisory_id, product_kind, position, crs, "
    "crs_datum, geojson, properties, provenance) VALUES (:snapshot, NULL, 'outlook_graphic', "
    "0, NULL, NULL, NULL, '{}', '{}')"
)
FAILING_0004 = """

_upgrade = upgrade


def upgrade() -> None:
    _upgrade()
    op.execute("SELECT no_such_function()")
"""


def _seed_0003(paths: AppPaths, engine: Engine) -> set[str]:
    """Revision 0003 with a location, a snapshot, an assessment, and a product; its tables."""
    _migrate(engine, "0002")
    engine.dispose()
    _seed_0002(paths.database_path)
    _migrate(engine, "0003")
    with engine.begin() as connection:
        connection.execute(ASSESSMENT, {"snapshot": SNAPSHOT_HEX, "level": 1, "rule": "all_clear"})
        connection.execute(PRODUCT, {"snapshot": SNAPSHOT_HEX})
    engine.dispose()
    return _tables(paths.database_path) - {"alembic_version"}


def _every_row(path: Path, tables: set[str]) -> dict[str, list[tuple[object, ...]]]:
    with closing(sqlite3.connect(path)) as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()  # noqa: S608 - a table name read from sqlite_master
            for table in sorted(tables)
        }


def _never_linked(_session: Session, _snapshot_id: UUID) -> bool:
    """Revision 0003's reader: every snapshot's products are in ``product_geometries``."""
    return False


def test_0004_upgrade_keeps_every_existing_row(paths: AppPaths, engine: Engine) -> None:
    tables = _seed_0003(paths, engine)
    before = _every_row(paths.database_path, tables)

    _migrate(engine, "0004")
    engine.dispose()

    assert _revision_of(paths.database_path) == "0004"
    assert _every_row(paths.database_path, tables) == before
    assert all(rows == [] for rows in _every_row(paths.database_path, SHARED_GEOMETRY).values())


@pytest.mark.anyio
async def test_0004_downgrade_keeps_every_saved_snapshot_loadable(
    paths: AppPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = await recorded_snapshot()
    one = recorded.snapshot
    later = one.completed_at + timedelta(minutes=15)
    two = with_second_storm(one).model_copy(
        update={
            "snapshot_id": UUID(int=one.snapshot_id.int + 1),
            "started_at": later,
            "completed_at": later,
        }
    )
    with open_database(paths) as opened:
        LocationRepository(opened.engine).add(recorded.location)
        repository = SnapshotRepository(opened.engine)
        repository.save(one, recorded.responses)
        repository.save(two, recorded.responses)
        with opened.engine.connect() as connection:
            linked = connection.execute(text("SELECT count(*) FROM snapshot_geometries")).scalar()

        _migrate(opened.engine, "0003")

        assert current_revision(opened.engine) == "0003"
        assert not SHARED_GEOMETRY & set(inspect(opened.engine).get_table_names())
        with opened.engine.connect() as connection:
            copied = connection.execute(text("SELECT count(*) FROM product_geometries")).scalar()
        assert copied == linked
        monkeypatch.setattr(repositories, "_links_products", _never_linked)
        assert repository.load(one.snapshot_id) == one
        assert repository.load(two.snapshot_id) == two


def test_0004_a_failed_upgrade_rolls_back_completely(
    tmp_path: Path, paths: AppPaths, engine: Engine
) -> None:
    migrations = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIRECTORY, migrations, ignore=shutil.ignore_patterns("__pycache__"))
    revision = migrations / "versions" / "0004_shared_geometry.py"
    revision.write_text(revision.read_text(encoding="utf-8") + FAILING_0004, encoding="utf-8")
    tables = _seed_0003(paths, engine)
    before = _every_row(paths.database_path, tables)

    with pytest.raises(MigrationFailedError):
        open_database(paths, migrations=migrations, now=lambda: STAMP)

    assert _revision_of(paths.database_path) == "0003"
    assert not SHARED_GEOMETRY & _tables(paths.database_path)
    assert _every_row(paths.database_path, tables) == before


# Revision 0005 -------------------------------------------------------------------------------

MONITOR = {"heartbeats", "monitor_cycles"}
CYCLE = text(
    "INSERT INTO monitor_cycles (runner, trigger, started_at, completed_at, snapshot_id, "
    "status, detail) VALUES ('status', 'manual', '2026-10-22', '2026-10-22', :snapshot, "
    "'complete', NULL)"
)
HEARTBEAT = text(
    "INSERT INTO heartbeats (kind, name, last_attempt_at, last_success_at, last_error_kind, "
    "expected_every_s, updated_at) VALUES ('source', 'nhc-current-storms', '2026-10-22', "
    "'2026-10-22', NULL, NULL, '2026-10-22')"
)


def _seed_0004(paths: AppPaths, engine: Engine) -> set[str]:
    """Revision 0004 with Phase 3's seeded rows; the tables it holds."""
    _seed_0003(paths, engine)
    _migrate(engine, "0004")
    engine.dispose()
    return _tables(paths.database_path) - {"alembic_version"}


def test_0005_upgrade_keeps_every_existing_row(paths: AppPaths, engine: Engine) -> None:
    tables = _seed_0004(paths, engine)
    before = _every_row(paths.database_path, tables)
    assert not MONITOR & tables

    _migrate(engine, "0005")
    engine.dispose()

    assert _revision_of(paths.database_path) == "0005"
    assert _every_row(paths.database_path, tables) == before
    assert all(rows == [] for rows in _every_row(paths.database_path, MONITOR).values())


def test_0005_downgrades_to_0004_cleanly_and_upgrades_again(
    paths: AppPaths, engine: Engine
) -> None:
    tables = _seed_0004(paths, engine)
    before = _every_row(paths.database_path, tables)
    _migrate(engine, "0005")
    with engine.begin() as connection:
        connection.execute(CYCLE, {"snapshot": SNAPSHOT_HEX})
        connection.execute(HEARTBEAT)
        assert connection.execute(text("SELECT consecutive_failures FROM heartbeats")).all() == [
            (0,)
        ]

    _migrate(engine, "0004")
    engine.dispose()

    assert _revision_of(paths.database_path) == "0004"
    assert not MONITOR & _tables(paths.database_path)
    assert _every_row(paths.database_path, tables) == before
    _migrate(engine, "0005")
    engine.dispose()
    assert _tables(paths.database_path) >= MONITOR


def test_0005_a_removed_snapshot_leaves_its_cycle_without_one(
    paths: AppPaths, engine: Engine
) -> None:
    _seed_0004(paths, engine)
    _migrate(engine, "0005")
    with engine.begin() as connection:
        connection.execute(CYCLE, {"snapshot": SNAPSHOT_HEX})
        connection.execute(text("DELETE FROM snapshots"))
    engine.dispose()

    assert _rows(paths.database_path, "SELECT snapshot_id, status FROM monitor_cycles") == [
        (None, "complete")
    ]


def test_0005_keeps_no_check_constraint_on_its_value_lists(paths: AppPaths) -> None:
    with open_database(paths) as opened:
        found = {table: inspect(opened.engine).get_check_constraints(table) for table in MONITOR}

    assert found == {table: [] for table in MONITOR}


# Revision 0006 -------------------------------------------------------------------------------

NOTIFICATIONS = {"notifications", "notification_decisions", "notification_deliveries"}


def _seed_0005(paths: AppPaths, engine: Engine) -> set[str]:
    """Revision 0005 with seeded rows; the tables it holds."""
    _seed_0004(paths, engine)
    _migrate(engine, "0005")
    with engine.begin() as connection:
        connection.execute(CYCLE, {"snapshot": SNAPSHOT_HEX})
        connection.execute(HEARTBEAT)
    engine.dispose()
    return _tables(paths.database_path) - {"alembic_version"}


def test_0006_upgrade_keeps_every_existing_row(paths: AppPaths, engine: Engine) -> None:
    tables = _seed_0005(paths, engine)
    before = _every_row(paths.database_path, tables)
    assert not NOTIFICATIONS & tables

    _migrate(engine, "0006")
    engine.dispose()

    assert _revision_of(paths.database_path) == "0006"
    assert _every_row(paths.database_path, tables) == before
    assert all(rows == [] for rows in _every_row(paths.database_path, NOTIFICATIONS).values())


def test_0006_downgrades_to_0005_cleanly_and_upgrades_again(
    paths: AppPaths, engine: Engine
) -> None:
    tables = _seed_0005(paths, engine)
    before = _every_row(paths.database_path, tables)
    _migrate(engine, "0006")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO notifications (location_id, assessment_id, cycle_id, kind, level, "
                "escalation, title, body, created_at) VALUES (1, 1, 1, 'location', 3, 1, "
                "'Place: level 3', '[]', '2026-10-22')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO notification_decisions (location_id, assessment_id, "
                "change_position, trigger, event_key, decision, level_after, notification_id, "
                "decided_at) VALUES (1, 1, 0, 'level', NULL, 'escalation', 3, 1, '2026-10-22')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO notification_deliveries (notification_id, channel, attempted_at, "
                "result, detail) VALUES (1, 'log', '2026-10-22', 'delivered', NULL)"
            )
        )

    _migrate(engine, "0005")
    engine.dispose()

    assert _revision_of(paths.database_path) == "0005"
    assert not NOTIFICATIONS & _tables(paths.database_path)
    assert _every_row(paths.database_path, tables) == before
    _migrate(engine, "0006")
    engine.dispose()
    assert _tables(paths.database_path) >= NOTIFICATIONS


def test_0006_keeps_no_check_constraint_on_extensible_value_lists(paths: AppPaths) -> None:
    with open_database(paths) as opened:
        inspector = inspect(opened.engine)
        decisions_checks = inspector.get_check_constraints("notification_decisions")
        deliveries_checks = inspector.get_check_constraints("notification_deliveries")
        notifications_checks = [c["name"] for c in inspector.get_check_constraints("notifications")]

    assert decisions_checks == []
    assert deliveries_checks == []
    assert notifications_checks == ["ck_notifications_level"]


@pytest.mark.parametrize("name", sorted(FROZEN))
def test_the_merged_revisions_are_byte_identical(name: str) -> None:
    # A Windows checkout may write CRLF; Git stores the file with LF either way.
    body = (MIGRATIONS_DIRECTORY / "versions" / name).read_bytes().replace(b"\r\n", b"\n")

    assert hashlib.sha256(body).hexdigest() == FROZEN[name]
