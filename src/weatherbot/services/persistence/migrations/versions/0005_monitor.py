# src/weatherbot/services/persistence/migrations/versions/0005_monitor.py
"""The heartbeats and the monitor's cycles.

``heartbeats`` keeps, per source, watch, and monitor process, the last attempt, the last
success, the run of consecutive failures, and the cadence its writer expects, unique by
kind and name; ``monitor_cycles`` records each cycle's runner, trigger, instants,
snapshot, and outcome (Phase 4 Step 2). Neither table has a CHECK constraint on its value
lists (kinds, runners, triggers, statuses): the services validate them, because a later
phase may extend a list and changing a CHECK in SQLite rebuilds the table, which cascades.
The upgrade only creates; the downgrade drops both tables. A revision is frozen once
merged, so it names plain SQLAlchemy types, never the application's table classes.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``heartbeats`` and ``monitor_cycles``."""
    op.create_table(
        "heartbeats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False, comment="source, watch, or runner"),
        sa.Column(
            "name",
            sa.String(length=64),
            nullable=False,
            comment="A source id, a watch, or a process",
        ),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "last_error_kind",
            sa.Text(),
            nullable=True,
            comment="An error kind or an exception class name, never a message",
        ),
        sa.Column(
            "expected_every_s",
            sa.Integer(),
            nullable=True,
            comment="The cadence its writer expects, in seconds; NULL: none is promised",
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heartbeats")),
        sa.UniqueConstraint("kind", "name", name=op.f("uq_heartbeats_kind_name")),
    )
    op.create_table(
        "monitor_cycles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("runner", sa.String(length=12), nullable=False),
        sa.Column("trigger", sa.String(length=12), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True, comment="A reason or an exception class"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.id"],
            name=op.f("fk_monitor_cycles_snapshot_id_snapshots"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitor_cycles")),
    )
    op.create_index(
        op.f("ix_monitor_cycles_started_at"), "monitor_cycles", ["started_at"], unique=False
    )


def downgrade() -> None:
    """Drop ``monitor_cycles`` and ``heartbeats``."""
    op.drop_index(op.f("ix_monitor_cycles_started_at"), table_name="monitor_cycles")
    op.drop_table("monitor_cycles")
    op.drop_table("heartbeats")
