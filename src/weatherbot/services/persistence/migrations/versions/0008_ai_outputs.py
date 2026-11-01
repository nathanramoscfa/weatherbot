# src/weatherbot/services/persistence/migrations/versions/0008_ai_outputs.py
"""The AI's products: briefings, change summaries, and narrations, as validated or withheld.

The table arrives with its writer, the AI package's ``OutputRepository`` (Phase 6 Step 2),
which writes through the AI engine. A row holds what Claude wrote for one location's
assessment (or, for a narration, one outlook graphic), the model and the frozen prompt's
version, and whether it passed the validators: ``ok`` with its content as JSON, or
``withheld`` with its reason and no content, because a withheld product's text is never
stored. ``call_id`` names the ledger row of the request that wrote it. Removing an
assessment removes its products; ``snapshot_id`` names a snapshot without a foreign key,
as the ledger names a location. The revision only expands: one new table with indexes on
``(kind, assessment_id)``, ``(kind, location_name, created_at)``, and ``graphic_sha256``,
and no CHECK constraint on a value list a later phase may extend (``kind``, ``status``),
because changing a CHECK in SQLite needs a batch rebuild, which cascades. The downgrade
drops the table. A revision is frozen once merged, so it names plain SQLAlchemy types,
never the application's table classes.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``ai_outputs``."""
    op.create_table(
        "ai_outputs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "kind", sa.String(length=16), nullable=False, comment="briefing, summary, or narration"
        ),
        sa.Column("location_name", sa.String(length=64), nullable=True),
        sa.Column("assessment_id", sa.Integer(), nullable=True),
        sa.Column("snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("graphic_sha256", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, comment="ok or withheld"),
        sa.Column(
            "withheld_reason",
            sa.String(length=32),
            nullable=True,
            comment="A validator's rule or a fixed reason, never the model's text",
        ),
        sa.Column(
            "content",
            sa.JSON(),
            nullable=True,
            comment="The validated product JSON; NULL when withheld",
        ),
        sa.Column("call_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_ai_outputs_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["ai_calls.id"],
            name=op.f("fk_ai_outputs_call_id_ai_calls"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_outputs")),
    )
    op.create_index(
        op.f("ix_ai_outputs_kind_assessment_id"),
        "ai_outputs",
        ["kind", "assessment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_outputs_kind_location_name_created_at"),
        "ai_outputs",
        ["kind", "location_name", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_outputs_graphic_sha256"), "ai_outputs", ["graphic_sha256"], unique=False
    )


def downgrade() -> None:
    """Drop ``ai_outputs``."""
    op.drop_index(op.f("ix_ai_outputs_graphic_sha256"), table_name="ai_outputs")
    op.drop_index(op.f("ix_ai_outputs_kind_location_name_created_at"), table_name="ai_outputs")
    op.drop_index(op.f("ix_ai_outputs_kind_assessment_id"), table_name="ai_outputs")
    op.drop_table("ai_outputs")
