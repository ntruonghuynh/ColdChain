"""Business events, outbox delivery state and chain records (for reconciliation, BC-10).

* ``business_event`` is an immutable fact with a globally unique business reference (BR-13).
* ``outbox_entry`` holds the mutable delivery state used by the Milestone 5 worker.
* ``chain_record`` stores the on-chain confirmation for an event.

No blockchain logic exists in Milestone 1; these tables only define the relationships.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, str_enum, uuid_pk
from app.db.models.enums import BusinessEventType, OutboxStatus
from app.db.types import UTCDateTime


class BusinessEvent(Base):
    __tablename__ = "business_event"

    event_id: Mapped[uuid.UUID] = uuid_pk()
    business_ref: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    event_type: Mapped[BusinessEventType] = mapped_column(
        str_enum(BusinessEventType, "business_event_type"), nullable=False
    )
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    actor_org_id: Mapped[str] = mapped_column(ForeignKey("organization.org_id"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.user_id"))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("payload_sha256 ~ '^[0-9a-f]{64}$'", name="payload_sha256_hex"),
        Index("ix_business_event_shipment_id_occurred_at", "shipment_id", "occurred_at"),
    )


class OutboxEntry(Base):
    __tablename__ = "outbox_entry"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_event.event_id"), primary_key=True)
    status: Mapped[OutboxStatus] = mapped_column(
        str_enum(OutboxStatus, "outbox_status"), nullable=False, server_default=OutboxStatus.PENDING.value
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_outbox_entry_status_next_attempt_at", "status", "next_attempt_at"),
    )


class ChainRecord(Base):
    __tablename__ = "chain_record"

    chain_record_id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business_event.event_id"), nullable=False, unique=True
    )
    chain_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    contract_address: Mapped[str] = mapped_column(String(42), nullable=False)
    onchain_ref: Mapped[str] = mapped_column(String(66), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index"),
        UniqueConstraint("chain_id", "contract_address", "onchain_ref"),
        CheckConstraint("tx_hash ~ '^0x[0-9a-f]{64}$'", name="tx_hash_hex"),
        CheckConstraint("onchain_ref ~ '^0x[0-9a-f]{64}$'", name="onchain_ref_hex"),
    )
