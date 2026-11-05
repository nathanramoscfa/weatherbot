# src/weatherbot/services/persistence/migrations/versions/0010_retention_indexes.py
"""Retention foreign-key indexes on four child columns.

Adds the four child-column indexes that retention deletes and foreign-key cascades scan:
``ix_snapshot_geometries_content_id``, ``ix_raw_responses_sha256``,
``ix_monitor_cycles_snapshot_id``, and ``ix_notifications_assessment_id``. Uses plain
``op.create_index`` and ``op.drop_index`` (never ``batch_alter_table``), and leaves
``ai_outputs`` untouched (Phase 6's database test pins its three indexes). A revision is
frozen once merged, so it names plain SQLAlchemy types, never the application's table
classes.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the four retention foreign-key indexes."""
    op.create_index(
        op.f("ix_snapshot_geometries_content_id"),
        "snapshot_geometries",
        ["content_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_raw_responses_sha256"),
        "raw_responses",
        ["sha256"],
        unique=False,
    )
    op.create_index(
        op.f("ix_monitor_cycles_snapshot_id"),
        "monitor_cycles",
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_assessment_id"),
        "notifications",
        ["assessment_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the four retention foreign-key indexes."""
    op.drop_index(op.f("ix_notifications_assessment_id"), table_name="notifications")
    op.drop_index(op.f("ix_monitor_cycles_snapshot_id"), table_name="monitor_cycles")
    op.drop_index(op.f("ix_raw_responses_sha256"), table_name="raw_responses")
    op.drop_index(op.f("ix_snapshot_geometries_content_id"), table_name="snapshot_geometries")
