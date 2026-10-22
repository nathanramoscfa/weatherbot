# src/weatherbot/services/persistence/migrations/versions/0004_shared_geometry.py
"""Each product's content stored once, and each provenance once per snapshot.

The snapshot repository stored every product of every snapshot again, 2.0 MiB a cycle
over unchanged answers (measured on 2026-10-21), so from this revision it writes a
product's content, everything but its provenance, once by its SHA-256 into
``geometry_contents``, each distinct provenance once per snapshot into
``snapshot_provenances``, and one narrow link per product into ``snapshot_geometries``
(Phase 4 Step 1). The upgrade only expands: it creates the three tables and moves no row,
so a snapshot stored before keeps its products in ``product_geometries``. The downgrade
first copies every linked product back into ``product_geometries``, so no stored snapshot
is lost either way. A revision is frozen once merged, so it names plain SQLAlchemy types
and SQL, never the application's table classes.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21
"""

import json
import zlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_KINDS = (
    "product_kind IN ('cone', 'track_point', 'track', 'watch_warning', 'wind_radii',"
    " 'arrival_time', 'outlook_area', 'wind_probability', 'breakpoint',"
    " 'display_layer', 'outlook_graphic')"
)
LINKED_SNAPSHOTS = sa.text("SELECT DISTINCT snapshot_id FROM snapshot_provenances")
LINKED_PRODUCTS = sa.text(
    "SELECT g.advisory_id, g.product_kind, g.position, c.sha256, c.size, c.body, "
    "p.provenance FROM snapshot_geometries AS g "
    "JOIN snapshot_provenances AS p ON p.id = g.provenance_id "
    "JOIN geometry_contents AS c ON c.id = g.content_id "
    "WHERE p.snapshot_id = :snapshot_id ORDER BY g.id"
)
COPY_BACK = sa.text(
    "INSERT INTO product_geometries (snapshot_id, advisory_id, product_kind, position, crs, "
    "crs_datum, geojson, properties, provenance) VALUES (:snapshot_id, :advisory_id, "
    ":product_kind, :position, :crs, :crs_datum, :geojson, :properties, :provenance)"
)


def upgrade() -> None:
    """Create ``geometry_contents``, ``snapshot_provenances``, and ``snapshot_geometries``."""
    op.create_table(
        "geometry_contents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("product_kind", sa.String(length=20), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, comment="Bytes of the canonical JSON"),
        sa.Column(
            "body", sa.LargeBinary(), nullable=False, comment="zlib-compressed canonical JSON"
        ),
        sa.CheckConstraint(PRODUCT_KINDS, name=op.f("ck_geometry_contents_product_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geometry_contents")),
        sa.UniqueConstraint("sha256", name=op.f("uq_geometry_contents_sha256")),
    )
    op.create_table(
        "snapshot_provenances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False, comment="Provenance JSON"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.id"],
            name=op.f("fk_snapshot_provenances_snapshot_id_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshot_provenances")),
        sa.UniqueConstraint(
            "snapshot_id", "position", name=op.f("uq_snapshot_provenances_snapshot_id_position")
        ),
    )
    op.create_table(
        "snapshot_geometries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provenance_id", sa.Integer(), nullable=False),
        sa.Column("advisory_id", sa.Integer(), nullable=True),
        sa.Column("product_kind", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(PRODUCT_KINDS, name=op.f("ck_snapshot_geometries_product_kind")),
        sa.ForeignKeyConstraint(
            ["advisory_id"],
            ["advisories.id"],
            name=op.f("fk_snapshot_geometries_advisory_id_advisories"),
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["geometry_contents.id"],
            name=op.f("fk_snapshot_geometries_content_id_geometry_contents"),
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["snapshot_provenances.id"],
            name=op.f("fk_snapshot_geometries_provenance_id_snapshot_provenances"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshot_geometries")),
    )
    with op.batch_alter_table("snapshot_geometries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_snapshot_geometries_advisory_id"), ["advisory_id"], unique=False
        )
        # Not unique: positions restart for each storm, so two storms share them.
        batch_op.create_index(
            batch_op.f("ix_snapshot_geometries_provenance_id_product_kind_position"),
            ["provenance_id", "product_kind", "position"],
            unique=False,
        )


def _copy_back(connection: sa.Connection) -> None:
    """Write every linked product back as a ``product_geometries`` row, a snapshot at a time.

    The content is decompressed and read as JSON; the provenance's stored JSON is copied as
    it is.
    """
    for (snapshot_id,) in connection.execute(LINKED_SNAPSHOTS).all():
        rows: list[dict[str, object]] = []
        linked = connection.execute(LINKED_PRODUCTS, {"snapshot_id": snapshot_id}).all()
        for advisory_id, kind, position, sha256, size, body, provenance in linked:
            text = zlib.decompress(body)
            if len(text) != size:
                message = f"the stored content {sha256[:12]} is corrupt"
                raise ValueError(message)
            content = json.loads(text)
            shape = content["geojson"]
            rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "advisory_id": advisory_id,
                    "product_kind": kind,
                    "position": position,
                    "crs": content["crs"],
                    "crs_datum": content["crs_datum"],
                    "geojson": json.dumps(shape) if shape is not None else None,
                    "properties": json.dumps(content["properties"]),
                    "provenance": provenance,
                }
            )
        connection.execute(COPY_BACK, rows)


def downgrade() -> None:
    """Copy every linked product back into ``product_geometries``, then drop the tables."""
    _copy_back(op.get_bind())
    with op.batch_alter_table("snapshot_geometries", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_snapshot_geometries_provenance_id_product_kind_position")
        )
        batch_op.drop_index(batch_op.f("ix_snapshot_geometries_advisory_id"))

    op.drop_table("snapshot_geometries")
    op.drop_table("snapshot_provenances")
    op.drop_table("geometry_contents")
