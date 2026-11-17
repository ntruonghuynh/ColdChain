"""Add append-only, advisory M6 explanation records.

Revision ID: 0006
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_explanation",
        sa.Column("explanation_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_ref", sa.String(120), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incident.incident_id"), nullable=False),
        sa.Column("shipment_id", sa.String(60), sa.ForeignKey("shipment.shipment_id"), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.user_id"), nullable=False),
        sa.Column("explained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(160)),
        sa.Column("provider_api_version", sa.String(80)),
        sa.Column("explanation_status", sa.String(32), nullable=False),
        sa.Column("source_mode", sa.String(32), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("procedure_version", sa.String(40), nullable=False),
        sa.Column("sensor_interval_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sensor_interval_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_references", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("document_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("citation_verification", sa.String(24), nullable=False),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("cost_usd", sa.Numeric(12, 8)),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("requested_by_user_id", "request_ref", name="uq_llm_explanation_request_user_ref"),
        sa.CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="ck_llm_explanation_request_sha256_hex"),
        sa.CheckConstraint("prompt_sha256 ~ '^[0-9a-f]{64}$'", name="ck_llm_explanation_prompt_sha256_hex"),
        sa.CheckConstraint("explanation_status IN ('DRAFT','INSUFFICIENT_EVIDENCE','NOT_CONFIGURED','PROVIDER_ERROR','FALLBACK')",
                           name="ck_llm_explanation_status_allowed"),
        sa.CheckConstraint("source_mode IN ('LLM','DETERMINISTIC_FALLBACK','NONE')",
                           name="ck_llm_explanation_source_mode_allowed"),
        sa.CheckConstraint("citation_verification IN ('PASSED','FAILED','NOT_APPLICABLE')",
                           name="ck_llm_explanation_citation_verification_allowed"),
        sa.CheckConstraint("input_tokens IS NULL OR input_tokens >= 0", name="ck_llm_explanation_input_tokens_nonnegative"),
        sa.CheckConstraint("output_tokens IS NULL OR output_tokens >= 0", name="ck_llm_explanation_output_tokens_nonnegative"),
        sa.CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_llm_explanation_latency_nonnegative"),
        sa.CheckConstraint("cost_usd IS NULL OR cost_usd >= 0", name="ck_llm_explanation_cost_nonnegative"),
        sa.CheckConstraint("sensor_interval_end_at >= sensor_interval_start_at",
                           name="ck_llm_explanation_sensor_interval_ordered"),
    )
    op.create_index("ix_llm_explanation_incident_created", "llm_explanation", ["incident_id", "created_at"])
    op.execute("""
        CREATE FUNCTION reject_llm_explanation_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'llm_explanation is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_llm_explanation_append_only
        BEFORE UPDATE OR DELETE ON llm_explanation
        FOR EACH ROW EXECUTE FUNCTION reject_llm_explanation_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_llm_explanation_append_only ON llm_explanation")
    op.execute("DROP FUNCTION IF EXISTS reject_llm_explanation_mutation()")
    op.drop_index("ix_llm_explanation_incident_created", table_name="llm_explanation")
    op.drop_table("llm_explanation")
