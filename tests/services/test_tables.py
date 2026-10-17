# tests/services/test_tables.py
"""The Phase 2 tables: their names, their constraints' names, and their instants."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, select
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.tables import Base, SettingRow, SnapshotRow

BASELINE_TABLES = {
    "locations",
    "snapshots",
    "source_outcomes",
    "outcome_responses",
    "raw_responses",
    "response_bodies",
    "storms",
    "storm_observations",
    "advisories",
    "product_geometries",
    "text_products",
    "text_product_observations",
    "feed_items",
    "feed_item_observations",
    "alerts",
    "alert_observations",
    "settings",
}
PHASE_2_TABLES = BASELINE_TABLES | {"drift_warnings"}  # revision 0002, Step 6
LATER_PHASES = ("assessment", "evidence", "notification", "heartbeat", "briefing", "ledger")
EASTERN = timezone(timedelta(hours=-4))


def test_the_tables_are_phase_2s_only() -> None:
    names = set(Base.metadata.tables)

    assert names == PHASE_2_TABLES
    assert not [name for name in names for word in LATER_PHASES if word in name]


def test_every_constraint_has_a_stable_name() -> None:
    kinds = (CheckConstraint, ForeignKeyConstraint, UniqueConstraint)
    unnamed = [
        (table.name, type(constraint).__name__)
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, kinds) and not constraint.name
    ]
    indexes = [index for table in Base.metadata.tables.values() for index in table.indexes]

    assert unnamed == []
    assert all(index.name for index in indexes)
    assert all(table.primary_key.name for table in Base.metadata.tables.values())


def test_instants_go_in_and_come_out_as_aware_utc() -> None:
    local = datetime(2026, 10, 17, 8, 30, tzinfo=EASTERN)
    with open_database(AppPaths.resolve()) as database:
        with Session(database.engine) as session, session.begin():
            session.add(SettingRow(key="probe", value=1, updated_at=local))
        with Session(database.engine) as session:
            stored = session.scalars(select(SettingRow.updated_at)).one()

    assert stored == local
    assert stored.tzinfo is UTC
    assert stored == datetime(2026, 10, 17, 12, 30, tzinfo=UTC)


def test_a_naive_instant_is_refused() -> None:
    naive = datetime(2026, 10, 17, 12, 30)  # noqa: DTZ001 - the value under test
    with (
        open_database(AppPaths.resolve()) as database,
        Session(database.engine) as session,
        pytest.raises(StatementError, match="timezone-aware"),
        session.begin(),
    ):
        session.add(SettingRow(key="probe", value=1, updated_at=naive))


def test_a_check_constraint_holds_in_the_database() -> None:
    now = datetime(2026, 10, 17, tzinfo=UTC)
    with (
        open_database(AppPaths.resolve()) as database,
        Session(database.engine) as session,
        pytest.raises(StatementError, match="CHECK constraint failed"),
        session.begin(),
    ):
        session.add(SnapshotRow(id=UUID(int=1), started_at=now, completed_at=now, status="done"))
