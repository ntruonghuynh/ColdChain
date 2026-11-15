"""Append-only advisory predictions emitted by a frozen ML model (Milestone 4)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk
from app.db.types import UTCDateTime


class MLPrediction(Base):
    __tablename__ = "ml_prediction"

    prediction_id: Mapped[uuid.UUID] = uuid_pk()
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id"), nullable=False)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_probability: Mapped[Decimal | None] = mapped_column(Numeric(9, 8))
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(9, 8))
    alert: Mapped[bool] = mapped_column(Boolean, nullable=False)
    advisory_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("status IN ('SCORED', 'INSUFFICIENT_EVIDENCE')", name="status_allowed"),
        CheckConstraint("risk_probability IS NULL OR (risk_probability >= 0 AND risk_probability <= 1)",
                        name="score_range"),
        CheckConstraint("threshold IS NULL OR (threshold >= 0 AND threshold <= 1)", name="threshold_range"),
        CheckConstraint("advisory_only IS TRUE", name="always_advisory"),
        Index("ix_ml_prediction_shipment_asof", "shipment_id", "as_of"),
    )
