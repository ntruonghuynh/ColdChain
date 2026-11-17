"""Append-only M6 explanation request and audit metadata."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk
from app.db.types import UTCDateTime


class LLMExplanation(Base):
    __tablename__ = "llm_explanation"

    explanation_id: Mapped[uuid.UUID] = uuid_pk()
    request_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident.incident_id"), nullable=False)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.user_id"), nullable=False)
    explained_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    evidence_cutoff_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str | None] = mapped_column(String(160))
    provider_api_version: Mapped[str | None] = mapped_column(String(80))
    explanation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    procedure_version: Mapped[str] = mapped_column(String(40), nullable=False)
    sensor_interval_start_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    sensor_interval_end_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    evidence_references: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    document_versions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    citation_verification: Mapped[str] = mapped_column(String(24), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 8))
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("requested_by_user_id", "request_ref", name="uq_llm_explanation_request_user_ref"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_sha256_hex"),
        CheckConstraint("prompt_sha256 ~ '^[0-9a-f]{64}$'", name="prompt_sha256_hex"),
        CheckConstraint("explanation_status IN ('DRAFT','INSUFFICIENT_EVIDENCE','NOT_CONFIGURED','PROVIDER_ERROR','FALLBACK')",
                        name="explanation_status_allowed"),
        CheckConstraint("source_mode IN ('LLM','DETERMINISTIC_FALLBACK','NONE')", name="source_mode_allowed"),
        CheckConstraint("citation_verification IN ('PASSED','FAILED','NOT_APPLICABLE')",
                        name="citation_verification_allowed"),
        CheckConstraint("input_tokens IS NULL OR input_tokens >= 0", name="input_tokens_nonnegative"),
        CheckConstraint("output_tokens IS NULL OR output_tokens >= 0", name="output_tokens_nonnegative"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_nonnegative"),
        CheckConstraint("cost_usd IS NULL OR cost_usd >= 0", name="cost_nonnegative"),
        CheckConstraint("sensor_interval_end_at >= sensor_interval_start_at", name="sensor_interval_ordered"),
        Index("ix_llm_explanation_incident_created", "incident_id", "created_at"),
    )

