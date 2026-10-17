# src/weatherbot/services/persistence/migrations/versions/0002_drift_warnings.py
"""The Source-drift warnings each snapshot's fetch logged, which ``doctor`` lists.

The table arrives with its writer, the snapshot service (Phase 2 Step 6). A revision is
frozen once merged, so it names plain SQLAlchemy types, never the application's table
classes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``drift_warnings``."""
    op.create_table(
        "drift_warnings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.id"],
            name=op.f("fk_drift_warnings_snapshot_id_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_drift_warnings")),
    )
    with op.batch_alter_table("drift_warnings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_drift_warnings_snapshot_id"), ["snapshot_id"], unique=False
        )


def downgrade() -> None:
    """Drop ``drift_warnings``."""
    with op.batch_alter_table("drift_warnings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_drift_warnings_snapshot_id"))

    op.drop_table("drift_warnings")
