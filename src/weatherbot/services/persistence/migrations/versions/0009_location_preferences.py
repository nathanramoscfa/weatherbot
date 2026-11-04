# src/weatherbot/services/persistence/migrations/versions/0009_location_preferences.py
"""Per-location notification preferences on ``locations``.

Adds four columns to ``locations`` with server defaults so existing rows need no backfill:
``notify_toast`` (1), ``notify_browser`` (1), ``notify_phone`` (1), and
``notify_phone_min_level`` (2). Uses plain ``op.add_column`` and ``op.drop_column`` (SQLite
3.35+ supports ``ALTER TABLE DROP COLUMN`` directly when no index or constraint references
the column) rather than ``batch_alter_table``, because a batch rebuild of ``locations``
with ``PRAGMA foreign_keys=ON`` would cascade-delete child observations, assessments, and
notifications. A revision is frozen once merged, so it names plain SQLAlchemy types, never
the application's table classes.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add per-location notification preference columns to ``locations``."""
    op.add_column(
        "locations",
        sa.Column("notify_toast", sa.Boolean(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "locations",
        sa.Column("notify_browser", sa.Boolean(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "locations",
        sa.Column("notify_phone", sa.Boolean(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "locations",
        sa.Column(
            "notify_phone_min_level", sa.Integer(), server_default=sa.text("2"), nullable=False
        ),
    )


def downgrade() -> None:
    """Drop the per-location notification preference columns from ``locations``."""
    op.drop_column("locations", "notify_phone_min_level")
    op.drop_column("locations", "notify_phone")
    op.drop_column("locations", "notify_browser")
    op.drop_column("locations", "notify_toast")
