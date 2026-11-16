"""M5 outbox attempt history and signed append-only audit log.

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_chain_role",
        sa.Column("org_id", sa.String(length=40), sa.ForeignKey("organization.org_id"), nullable=False),
        sa.Column("role", sa.Enum("SHIPPER", "CARRIER", "QUALITY", "WAREHOUSE", "MONITOR", "ADMIN",
                                  name="chain_role", native_enum=False, create_constraint=True, length=40),
                  nullable=False),
        sa.Column("chain_address", sa.String(length=42), nullable=False),
        sa.CheckConstraint("chain_address ~ '^0x[0-9a-fA-F]{40}$'", name="ck_organization_chain_role_chain_address_hex"),
        sa.PrimaryKeyConstraint("org_id", "role", name="pk_organization_chain_role"),
        sa.UniqueConstraint("chain_address", name="uq_organization_chain_role_chain_address"),
    )
    op.create_table(
        "outbox_attempt",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("outbox_entry.event_id"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("tx_hash", sa.String(length=66)),
        sa.Column("error", sa.Text()),
        sa.CheckConstraint("attempt_number > 0", name="ck_outbox_attempt_attempt_number_positive"),
        sa.CheckConstraint("outcome IN ('STARTED','SUBMITTED','CONFIRMED','RETRY','FAILED','UNCERTAIN')",
                           name="ck_outbox_attempt_outcome_allowed"),
        sa.UniqueConstraint("event_id", "attempt_number", name="uq_outbox_attempt_event_id_attempt_number"),
    )
    op.create_table(
        "audit_log",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("sequence_no", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("business_ref", sa.String(length=120), nullable=False, unique=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.user_id")),
        sa.Column("actor_org_id", sa.String(length=40), sa.ForeignKey("organization.org_id")),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("record", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("previous_hash", sa.String(length=64)),
        sa.Column("entry_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("previous_hash IS NULL OR previous_hash ~ '^[0-9a-f]{64}$'",
                           name="ck_audit_log_previous_hash_hex"),
        sa.CheckConstraint("entry_hash ~ '^[0-9a-f]{64}$'", name="ck_audit_log_entry_hash_hex"),
    )
    op.create_table(
        "reassessment_resolution",
        sa.Column("reassessment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("decision_reassessment.reassessment_id"), primary_key=True),
        sa.Column("disposition_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("disposition.disposition_id"), nullable=False),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("app_user.user_id"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_note_sha256", sa.String(length=64), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.CheckConstraint("review_note_sha256 ~ '^[0-9a-f]{64}$'", name="ck_reassessment_resolution_review_note_sha256_hex"),
        sa.CheckConstraint("length(trim(review_note)) > 0", name="ck_reassessment_resolution_review_note_not_blank"),
    )
    op.create_index("ix_audit_log_business_ref", "audit_log", ["business_ref"])
    op.execute("""
        CREATE FUNCTION reject_m5_audit_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'M5 business evidence is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_audit_log_append_only
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION reject_m5_audit_mutation();
    """)
    op.execute("""
        CREATE TRIGGER trg_outbox_attempt_no_delete
        BEFORE DELETE ON outbox_attempt
        FOR EACH ROW EXECUTE FUNCTION reject_m5_audit_mutation();
    """)
    op.execute("""
        CREATE TRIGGER trg_reassessment_resolution_append_only
        BEFORE UPDATE OR DELETE ON reassessment_resolution
        FOR EACH ROW EXECUTE FUNCTION reject_m5_audit_mutation();
    """)
    for table_name, trigger_name in (("business_event", "trg_business_event_append_only"),
                                     ("chain_record", "trg_chain_record_append_only")):
        op.execute(f"""
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_m5_audit_mutation();
        """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_outbox_attempt_no_delete ON outbox_attempt")
    op.execute("DROP TRIGGER IF EXISTS trg_reassessment_resolution_append_only ON reassessment_resolution")
    op.execute("DROP TRIGGER IF EXISTS trg_chain_record_append_only ON chain_record")
    op.execute("DROP TRIGGER IF EXISTS trg_business_event_append_only ON business_event")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS reject_m5_audit_mutation()")
    op.drop_index("ix_audit_log_business_ref", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("outbox_attempt")
    op.drop_table("reassessment_resolution")
    op.drop_table("organization_chain_role")
