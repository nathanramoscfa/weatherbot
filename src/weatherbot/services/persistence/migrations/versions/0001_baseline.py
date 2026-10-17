# src/weatherbot/services/persistence/migrations/versions/0001_baseline.py
"""The Phase 2 baseline: the tables Phase 2 code writes and reads.

Assessments and evidence (Phase 3), notifications and the heartbeat (Phase 4), and
briefings and the Claude ledger (Phase 6) arrive as later revisions with their writers.
A revision is frozen once merged, so it names plain SQLAlchemy types, never the
application's table classes.

Revision ID: 0001
Revises:
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the Phase 2 tables."""
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Text(), nullable=False),
        sa.Column("sent", sa.DateTime(), nullable=False),
        sa.Column("effective", sa.DateTime(), nullable=False),
        sa.Column("expires", sa.DateTime(), nullable=False),
        sa.Column("ends", sa.DateTime(), nullable=True),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("alert", sa.JSON(), nullable=False, comment="NwsAlert JSON, as first seen"),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
        sa.UniqueConstraint("alert_id", name=op.f("uq_alerts_alert_id")),
    )
    op.create_table(
        "feed_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guid", sa.Text(), nullable=False),
        sa.Column("feed", sa.String(length=2), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("is_placeholder", sa.Boolean(), nullable=False),
        sa.Column("atcf_id", sa.String(length=8), nullable=True),
        sa.Column("slot", sa.String(length=3), nullable=True),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feed_items")),
        sa.UniqueConstraint("feed", "guid", name=op.f("uq_feed_items_feed_guid")),
    )
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("latitude", sa.Double[float](), nullable=False),
        sa.Column("longitude", sa.Double[float](), nullable=False),
        sa.Column("polygon", sa.JSON(), nullable=True, comment="GeoJSON geometry"),
        sa.Column("polygon_crs", sa.Text(), nullable=True, comment="EPSG:4326 or the WKT"),
        sa.Column("polygon_crs_datum", sa.Text(), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("nws_forecast_zone", sa.String(length=6), nullable=True),
        sa.Column("nws_county_zone", sa.String(length=6), nullable=True),
        sa.Column("nws_cwa", sa.String(length=3), nullable=True),
        sa.Column("nws_time_zone", sa.Text(), nullable=True),
        sa.Column("nws_city", sa.Text(), nullable=True),
        sa.Column("nws_state", sa.Text(), nullable=True),
        sa.Column("breakpoint_span", sa.JSON(), nullable=True),
        sa.Column(
            "evacuation_order_in_effect", sa.Boolean(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("geocoding", sa.JSON(), nullable=True, comment="Provenance JSON"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            (
                "(nws_forecast_zone IS NULL) = (nws_county_zone IS NULL)"
                " AND (nws_forecast_zone IS NULL) = (nws_cwa IS NULL)"
                " AND (nws_forecast_zone IS NULL) = (nws_time_zone IS NULL)"
                " AND (nws_forecast_zone IS NULL) = (nws_city IS NULL)"
                " AND (nws_forecast_zone IS NULL) = (nws_state IS NULL)"
            ),
            name=op.f("ck_locations_nws_coverage_whole"),
        ),
        sa.CheckConstraint(
            "(polygon IS NULL) = (polygon_crs IS NULL)", name=op.f("ck_locations_polygon_has_crs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
        sa.UniqueConstraint("name", name=op.f("uq_locations_name")),
    )
    op.create_table(
        "response_bodies",
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, comment="Bytes before compression"),
        sa.Column("body", sa.LargeBinary(), nullable=False, comment="zlib-compressed"),
        sa.PrimaryKeyConstraint("sha256", name=op.f("pk_response_bodies")),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False, comment="Any JSON value"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
    )
    op.create_table(
        "snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.CheckConstraint(
            "status IN ('complete', 'partial', 'failed')", name=op.f("ck_snapshots_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshots")),
    )
    with op.batch_alter_table("snapshots", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_snapshots_completed_at"), ["completed_at"], unique=False
        )

    op.create_table(
        "storms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("atcf_id", sa.String(length=8), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("basin", sa.String(length=2), nullable=False),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storms")),
        sa.UniqueConstraint("atcf_id", name=op.f("uq_storms_atcf_id")),
    )
    op.create_table(
        "text_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("location", sa.String(length=3), nullable=False),
        sa.Column("wmo_collective_id", sa.Text(), nullable=False),
        sa.Column("issuing_office", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("atcf_id", sa.String(length=8), nullable=True),
        sa.Column("advisory", sa.String(length=4), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_text_products")),
        sa.UniqueConstraint("product_id", name=op.f("uq_text_products_product_id")),
    )
    op.create_table(
        "advisories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("storm_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=4), nullable=False, comment="Such as 22A"),
        sa.Column("issued_at", sa.DateTime(), nullable=True),
        sa.Column("local_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["storm_id"], ["storms.id"], name=op.f("fk_advisories_storm_id_storms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_advisories")),
        sa.UniqueConstraint("storm_id", "number", name=op.f("uq_advisories_storm_id_number")),
    )
    op.create_table(
        "alert_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("found_by", sa.JSON(), nullable=True, comment="AlertQuery JSON list"),
        sa.CheckConstraint(
            "(alert_id IS NULL) = (found_by IS NULL)", name=op.f("ck_alert_observations_found_by")
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"], ["alerts.id"], name=op.f("fk_alert_observations_alert_id_alerts")
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_alert_observations_location_id_locations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.id"],
            name=op.f("fk_alert_observations_snapshot_id_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_observations")),
        sa.UniqueConstraint(
            "snapshot_id",
            "location_id",
            "alert_id",
            name=op.f("uq_alert_observations_snapshot_id_location_id_alert_id"),
        ),
    )
    with op.batch_alter_table("alert_observations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_alert_observations_alert_id"), ["alert_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_alert_observations_location_id"), ["location_id"], unique=False
        )

    op.create_table(
        "feed_item_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("feed_item_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("item", sa.JSON(), nullable=False, comment="GisFeedItem JSON"),
        sa.ForeignKeyConstraint(
            ["feed_item_id"],
            ["feed_items.id"],
            name=op.f("fk_feed_item_observations_feed_item_id_feed_items"),
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.id"],
            name=op.f("fk_feed_item_observations_snapshot_id_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feed_item_observations")),
        sa.UniqueConstraint(
            "snapshot_id",
            "feed_item_id",
            name=op.f("uq_feed_item_observations_snapshot_id_feed_item_id"),
        ),
    )
    with op.batch_alter_table("feed_item_observations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_feed_item_observations_feed_item_id"), ["feed_item_id"], unique=False
        )

    op.create_table(
        "raw_responses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("product_key", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["sha256"],
            ["response_bodies.sha256"],
            name=op.f("fk_raw_responses_sha256_response_bodies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_responses")),
        sa.UniqueConstraint(
            "source_id",
            "product_key",
            "issued_at",
            "sha256",
            name=op.f("uq_raw_responses_source_id_product_key_issued_at_sha256"),
        ),
    )
    with op.batch_alter_table("raw_responses", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_raw_responses_url_fetched_at"), ["url", "fetched_at"], unique=False
        )

    op.create_table(
        "source_outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("error_kind", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=True, comment="Its latest answer's"),
        sa.CheckConstraint(
            "(status = 'failed') = (error_kind IS NOT NULL)",
            name=op.f("ck_source_outcomes_error_kind"),
        ),
        sa.CheckConstraint(
            "(status = 'skipped') = (reason IS NOT NULL)", name=op.f("ck_source_outcomes_reason")
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'not_modified', 'failed', 'skipped')",
            name=op.f("ck_source_outcomes_status"),
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.id"],
            name=op.f("fk_source_outcomes_snapshot_id_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_outcomes")),
        sa.UniqueConstraint(
            "snapshot_id", "source_id", name=op.f("uq_source_outcomes_snapshot_id_source_id")
        ),
    )
    op.create_table(
        "storm_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("storm_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False, comment="StormSummary JSON"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.id"],
            name=op.f("fk_storm_observations_snapshot_id_snapshots"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["storm_id"], ["storms.id"], name=op.f("fk_storm_observations_storm_id_storms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storm_observations")),
        sa.UniqueConstraint(
            "snapshot_id", "storm_id", name=op.f("uq_storm_observations_snapshot_id_storm_id")
        ),
    )
    with op.batch_alter_table("storm_observations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_storm_observations_storm_id"), ["storm_id"], unique=False
        )

    op.create_table(
        "text_product_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("text_product_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.id"],
            name=op.f("fk_text_product_observations_snapshot_id_snapshots"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["text_product_id"],
            ["text_products.id"],
            name=op.f("fk_text_product_observations_text_product_id_text_products"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_text_product_observations")),
        sa.UniqueConstraint(
            "snapshot_id",
            "text_product_id",
            name=op.f("uq_text_product_observations_snapshot_id_text_product_id"),
        ),
    )
    with op.batch_alter_table("text_product_observations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_text_product_observations_text_product_id"),
            ["text_product_id"],
            unique=False,
        )

    op.create_table(
        "outcome_responses",
        sa.Column("outcome_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("raw_response_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["outcome_id"],
            ["source_outcomes.id"],
            name=op.f("fk_outcome_responses_outcome_id_source_outcomes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["raw_response_id"],
            ["raw_responses.id"],
            name=op.f("fk_outcome_responses_raw_response_id_raw_responses"),
        ),
        sa.PrimaryKeyConstraint("outcome_id", "position", name=op.f("pk_outcome_responses")),
    )
    with op.batch_alter_table("outcome_responses", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_outcome_responses_raw_response_id"), ["raw_response_id"], unique=False
        )

    op.create_table(
        "product_geometries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("advisory_id", sa.Integer(), nullable=True),
        sa.Column("product_kind", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("crs", sa.Text(), nullable=True, comment="EPSG:4326 or the verbatim WKT"),
        sa.Column("crs_datum", sa.Text(), nullable=True),
        sa.Column("geojson", sa.JSON(), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            (
                "product_kind IN ('cone', 'track_point', 'track', 'watch_warning', 'wind_radii',"
                " 'arrival_time', 'outlook_area', 'wind_probability', 'breakpoint',"
                " 'display_layer', 'outlook_graphic')"
            ),
            name=op.f("ck_product_geometries_product_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["advisory_id"],
            ["advisories.id"],
            name=op.f("fk_product_geometries_advisory_id_advisories"),
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.id"],
            name=op.f("fk_product_geometries_snapshot_id_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_geometries")),
    )
    with op.batch_alter_table("product_geometries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_product_geometries_advisory_id"), ["advisory_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_product_geometries_snapshot_id_product_kind_position"),
            ["snapshot_id", "product_kind", "position"],
            unique=False,
        )


def downgrade() -> None:
    """Drop every Phase 2 table."""
    with op.batch_alter_table("product_geometries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_product_geometries_snapshot_id_product_kind_position"))
        batch_op.drop_index(batch_op.f("ix_product_geometries_advisory_id"))

    op.drop_table("product_geometries")
    with op.batch_alter_table("outcome_responses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_outcome_responses_raw_response_id"))

    op.drop_table("outcome_responses")
    with op.batch_alter_table("text_product_observations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_text_product_observations_text_product_id"))

    op.drop_table("text_product_observations")
    with op.batch_alter_table("storm_observations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_storm_observations_storm_id"))

    op.drop_table("storm_observations")
    op.drop_table("source_outcomes")
    with op.batch_alter_table("raw_responses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_raw_responses_url_fetched_at"))

    op.drop_table("raw_responses")
    with op.batch_alter_table("feed_item_observations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_feed_item_observations_feed_item_id"))

    op.drop_table("feed_item_observations")
    with op.batch_alter_table("alert_observations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_alert_observations_location_id"))
        batch_op.drop_index(batch_op.f("ix_alert_observations_alert_id"))

    op.drop_table("alert_observations")
    op.drop_table("advisories")
    op.drop_table("text_products")
    op.drop_table("storms")
    with op.batch_alter_table("snapshots", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_snapshots_completed_at"))

    op.drop_table("snapshots")
    op.drop_table("settings")
    op.drop_table("response_bodies")
    op.drop_table("locations")
    op.drop_table("feed_items")
    op.drop_table("alerts")
