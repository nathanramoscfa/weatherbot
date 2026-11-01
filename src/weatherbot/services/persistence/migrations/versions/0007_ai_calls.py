# src/weatherbot/services/persistence/migrations/versions/0007_ai_calls.py
"""The Claude ledger: one row per Messages request and per control of the AI's spend.

The table arrives with its writer, the AI package's ledger (Phase 6 Step 1): a request is
reserved at its ceiling under ``BEGIN IMMEDIATE`` before it is sent and settled from the
SDK's usage after it, so every process shares one daily cap. The revision only expands:
one new table with indexes on ``day`` and ``started_at``, no foreign key (a removed
location keeps its spend history), and no CHECK constraint on a value list a later phase
may extend (``kind``, ``status``), because changing a CHECK in SQLite needs a batch
rebuild, which cascades. The downgrade drops the table. A revision is frozen once merged,
so it names plain SQLAlchemy types, never the application's table classes.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``ai_calls``."""
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            comment="briefing, summary, chat, narration, allowance, pause, or resume",
        ),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("location_name", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            comment="reserved, ok, failed, incomplete, declined, abandoned, or control",
        ),
        sa.Column("day", sa.String(length=10), nullable=False, comment="Local YYYY-MM-DD"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("ceiling_micro_usd", sa.Integer(), nullable=False),
        sa.Column("cost_micro_usd", sa.Integer(), nullable=True),
        sa.Column("allowance_micro_usd", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "cache_write_5m_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "cache_write_1h_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("cache_read_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("stop_reason", sa.String(length=32), nullable=True),
        sa.Column("refusal_category", sa.String(length=32), nullable=True),
        sa.Column(
            "error_kind",
            sa.String(length=32),
            nullable=True,
            comment="A fixed reason, never an SDK message",
        ),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("prices_as_of", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_calls")),
    )
    op.create_index(op.f("ix_ai_calls_day"), "ai_calls", ["day"], unique=False)
    op.create_index(op.f("ix_ai_calls_started_at"), "ai_calls", ["started_at"], unique=False)


def downgrade() -> None:
    """Drop ``ai_calls``."""
    op.drop_index(op.f("ix_ai_calls_started_at"), table_name="ai_calls")
    op.drop_index(op.f("ix_ai_calls_day"), table_name="ai_calls")
    op.drop_table("ai_calls")
