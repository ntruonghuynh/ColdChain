"""Telemetry: ingest batches, temperature readings, context readings, rejected records.

Every reading keeps both ``event_at`` (sensor time) and ``received_at``
(system time) unchanged (FR-03). Validation rules are implemented in Milestone 3.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, str_enum, uuid_pk
from app.db.models.enums import DataOrigin, DoorState, IngestMode, IngestSource, RecordKind
from app.db.types import UTCDateTime


class IngestBatch(Base):
    """One upload as received (for example a buffered upload after a coverage gap).

    ``content_sha256`` is the hash later anchored on chain (BC-01).
    """

    __tablename__ = "ingest_batch"

    batch_id: Mapped[uuid.UUID] = uuid_pk()
    business_ref: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    submitted_by_org_id: Mapped[str] = mapped_column(ForeignKey("organization.org_id"), nullable=False)
    source: Mapped[IngestSource] = mapped_column(str_enum(IngestSource, "ingest_source"), nullable=False)
    data_origin: Mapped[DataOrigin] = mapped_column(str_enum(DataOrigin, "data_origin"), nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    first_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # BR-07: identical duplicates are ignored (no business effect), counted here, not rejected.
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # C-09: IMPORT (M2 dataset import), LIVE (server receipt time), REPLAY (trusted recorded receipt time).
    ingest_mode: Mapped[IngestMode] = mapped_column(
        str_enum(IngestMode, "ingest_mode"), nullable=False, server_default=IngestMode.IMPORT.value
    )
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    canonicalization_version: Mapped[str | None] = mapped_column(String(20))
    business_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_event.event_id"), unique=True
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(
            "record_count >= 0 AND accepted_count >= 0 AND rejected_count >= 0 AND duplicate_count >= 0 "
            "AND accepted_count + rejected_count + duplicate_count <= record_count",
            name="counts_consistent",
        ),
        CheckConstraint(
            "first_event_at IS NULL OR last_event_at IS NULL OR last_event_at >= first_event_at",
            name="event_range_ordered",
        ),
        CheckConstraint("content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'", name="content_sha256_hex"),
    )


class Reading(Base):
    """Temperature reading (DATA-01). Unique per sensor and event time (duplicates handled in M3)."""

    __tablename__ = "reading"

    reading_id: Mapped[uuid.UUID] = uuid_pk()
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id"), nullable=False)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    ingest_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingest_batch.batch_id"), nullable=False)
    event_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    temperature_c: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("sensor_id", "event_at"),
        Index("ix_reading_shipment_id_event_at", "shipment_id", "event_at"),
        Index("ix_reading_ingest_batch_id", "ingest_batch_id"),
    )


class ContextReading(Base):
    """Context record (DATA-02). NULL means "not reported", never a default value."""

    __tablename__ = "context_reading"

    context_id: Mapped[uuid.UUID] = uuid_pk()
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id"), nullable=False)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    ingest_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingest_batch.batch_id"), nullable=False)
    event_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    door_state: Mapped[DoorState | None] = mapped_column(str_enum(DoorState, "door_state"))
    battery_level_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ambient_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("sensor_id", "event_at"),
        Index("ix_context_reading_shipment_id_event_at", "shipment_id", "event_at"),
        CheckConstraint(
            "battery_level_pct IS NULL OR (battery_level_pct >= 0 AND battery_level_pct <= 100)",
            name="battery_pct_range",
        ),
    )


class RejectedRecord(Base):
    """A record that failed validation, kept with its reason (FR-01: never silently dropped)."""

    __tablename__ = "rejected_record"

    rejected_id: Mapped[uuid.UUID] = uuid_pk()
    ingest_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingest_batch.batch_id"), nullable=False)
    record_index: Mapped[int] = mapped_column(Integer, nullable=False)
    record_kind: Mapped[RecordKind] = mapped_column(str_enum(RecordKind, "record_kind"), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(60), nullable=False)
    reason_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (UniqueConstraint("ingest_batch_id", "record_kind", "record_index"),)
