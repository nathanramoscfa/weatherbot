# src/weatherbot/services/persistence/migrations/versions/0003_assessments.py
"""The stored assessments, their evidence and changes, and when the toggle was set.

The tables arrive with their writer, the assessment service behind ``weatherbot status``
(Phase 3 Step 6). The revision only expands: three new tables, and one nullable column on
``locations``. A revision is frozen once merged, so it names plain SQLAlchemy types, never
the application's table classes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the assessment tables and add ``locations.evacuation_order_set_at``."""
    op.create_table(
        "assessments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column(
            "ruleset", sa.String(length=64), nullable=False, comment="Thresholds and rule order"
        ),
        sa.Column("as_of", sa.DateTime(), nullable=False, comment="The snapshot's instant"),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("rule", sa.String(length=40), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False, comment="Thresholds JSON"),
        sa.Column("assessment", sa.JSON(), nullable=False, comment="Assessment JSON"),
        sa.Column("stored_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("level BETWEEN 1 AND 5", name=op.f("ck_assessments_level")),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_assessments_location_id_locations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.id"],
            name=op.f("fk_assessments_snapshot_id_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessments")),
        sa.UniqueConstraint(
            "location_id",
            "snapshot_id",
            "ruleset",
            name=op.f("uq_assessments_location_id_snapshot_id_ruleset"),
        ),
    )
    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_assessments_location_id_as_of"), ["location_id", "as_of"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_assessments_snapshot_id"), ["snapshot_id"], unique=False
        )

    op.create_table(
        "assessment_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("event", sa.JSON(), nullable=False, comment="ChangeEvent JSON"),
        sa.CheckConstraint(
            "kind IN ('level_changed', 'advisory_issued', 'official_added', "
            "'official_changed', 'official_removed', 'cone_entered', 'cone_left')",
            name=op.f("ck_assessment_changes_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_assessment_changes_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_changes")),
        sa.UniqueConstraint(
            "assessment_id",
            "position",
            name=op.f("uq_assessment_changes_assessment_id_position"),
        ),
    )
    op.create_table(
        "assessment_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=8), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False, comment="The product's kind"),
        sa.Column("rule", sa.String(length=40), nullable=True),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.Column("code", sa.Text(), nullable=True, comment="The NWS event or the NHC code"),
        sa.Column("distance_km", sa.Double[float](), nullable=True),
        sa.Column("covers", sa.Boolean(), nullable=True, comment="An official product's coverage"),
        sa.CheckConstraint(
            "role IN ('evidence', 'official')", name=op.f("ck_assessment_evidence_role")
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_assessment_evidence_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_evidence")),
        sa.UniqueConstraint(
            "assessment_id",
            "role",
            "position",
            name=op.f("uq_assessment_evidence_assessment_id_role_position"),
        ),
    )
    # Not in batch mode: a batch alteration rebuilds ``locations``, and dropping the old
    # table with foreign keys on deletes every row that cascades from it. SQLite adds and
    # drops a plain nullable column in place.
    op.add_column(
        "locations",
        sa.Column(
            "evacuation_order_set_at",
            sa.DateTime(),
            nullable=True,
            comment="When the toggle was last turned on or off (revision 0003)",
        ),
    )


def downgrade() -> None:
    """Drop the assessment tables and ``locations.evacuation_order_set_at``."""
    op.drop_table("assessment_evidence")
    op.drop_table("assessment_changes")
    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_assessments_snapshot_id"))
        batch_op.drop_index(batch_op.f("ix_assessments_location_id_as_of"))

    op.drop_table("assessments")
    op.drop_column("locations", "evacuation_order_set_at")
