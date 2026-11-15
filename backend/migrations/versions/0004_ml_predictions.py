"""Add append-only, advisory ML prediction records.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_prediction",
        sa.Column("prediction_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("shipment_id", sa.String(length=60), sa.ForeignKey("shipment.shipment_id"), nullable=False),
        sa.Column("sensor_id", sa.String(length=60), sa.ForeignKey("sensor.sensor_id"), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk_probability", sa.Numeric(9, 8), nullable=True),
        sa.Column("threshold", sa.Numeric(9, 8), nullable=True),
        sa.Column("alert", sa.Boolean(), nullable=False),
        sa.Column("advisory_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('SCORED', 'INSUFFICIENT_EVIDENCE')", name="ck_ml_prediction_status_allowed"),
        sa.CheckConstraint("risk_probability IS NULL OR (risk_probability >= 0 AND risk_probability <= 1)",
                           name="ck_ml_prediction_score_range"),
        sa.CheckConstraint("threshold IS NULL OR (threshold >= 0 AND threshold <= 1)",
                           name="ck_ml_prediction_threshold_range"),
        sa.CheckConstraint("advisory_only IS TRUE", name="ck_ml_prediction_always_advisory"),
    )
    op.create_index("ix_ml_prediction_shipment_asof", "ml_prediction", ["shipment_id", "as_of"])
    op.execute("""
        CREATE FUNCTION reject_ml_prediction_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ml_prediction is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_ml_prediction_append_only
        BEFORE UPDATE OR DELETE ON ml_prediction
        FOR EACH ROW EXECUTE FUNCTION reject_ml_prediction_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ml_prediction_append_only ON ml_prediction")
    op.execute("DROP FUNCTION IF EXISTS reject_ml_prediction_mutation()")
    op.drop_index("ix_ml_prediction_shipment_asof", table_name="ml_prediction")
    op.drop_table("ml_prediction")
