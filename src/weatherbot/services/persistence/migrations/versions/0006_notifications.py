# src/weatherbot/services/persistence/migrations/versions/0006_notifications.py
"""The notifications, their policy decisions, and their channel deliveries.

The tables arrive with their writer, ``NotificationService`` (Phase 4 Step 3). The
revision only expands: three new tables, with no CHECK constraint on any value list a
later phase may extend (``kind``, ``trigger``, ``decision``, ``channel``, ``result``),
because changing a CHECK in SQLite needs a batch rebuild, which cascades. A revision is
frozen once merged, so it names plain SQLAlchemy types, never the application's table
classes.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``notifications``, ``notification_decisions``, and ``notification_deliveries``."""
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("assessment_id", sa.Integer(), nullable=True),
        sa.Column("cycle_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("escalation", sa.Boolean(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False, comment="Notification body lines JSON"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("level BETWEEN 1 AND 5", name=op.f("ck_notifications_level")),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_notifications_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["monitor_cycles.id"],
            name=op.f("fk_notifications_cycle_id_monitor_cycles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_notifications_location_id_locations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notifications_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_notifications_cycle_id"), ["cycle_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_notifications_location_id"), ["location_id"], unique=False
        )

    op.create_table(
        "notification_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("change_position", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("event_key", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("level_after", sa.Integer(), nullable=True),
        sa.Column("notification_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_notification_decisions_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_notification_decisions_location_id_locations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name=op.f("fk_notification_decisions_notification_id_notifications"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_decisions")),
        sa.UniqueConstraint(
            "assessment_id",
            "trigger",
            "change_position",
            name=op.f("uq_notification_decisions_assessment_id_trigger_change_position"),
        ),
    )
    with op.batch_alter_table("notification_decisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notification_decisions_location_id"), ["location_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_notification_decisions_notification_id"),
            ["notification_id"],
            unique=False,
        )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column(
            "detail",
            sa.Text(),
            nullable=True,
            comment="An error kind, an HRESULT, or a setting name, never content",
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name=op.f("fk_notification_deliveries_notification_id_notifications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_deliveries")),
    )
    with op.batch_alter_table("notification_deliveries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notification_deliveries_notification_id"),
            ["notification_id"],
            unique=False,
        )


def downgrade() -> None:
    """Drop ``notification_deliveries``, ``notification_decisions``, and ``notifications``."""
    with op.batch_alter_table("notification_deliveries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notification_deliveries_notification_id"))
    op.drop_table("notification_deliveries")

    with op.batch_alter_table("notification_decisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notification_decisions_notification_id"))
        batch_op.drop_index(batch_op.f("ix_notification_decisions_location_id"))
    op.drop_table("notification_decisions")

    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notifications_location_id"))
        batch_op.drop_index(batch_op.f("ix_notifications_cycle_id"))
        batch_op.drop_index(batch_op.f("ix_notifications_created_at"))
    op.drop_table("notifications")
