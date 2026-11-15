"""Provenance of imported datasets (DATA-07, NFR-03).

One row per imported dataset release. Shipments created by the import point to it
through ``shipment.source_dataset_id``, so every simulated record can be traced to the
generator version, configuration, seed and policy that produced it.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, str_enum
from app.db.models.enums import DataOrigin
from app.db.types import UTCDateTime


class DatasetRelease(Base):
    __tablename__ = "dataset_release"

    dataset_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    dataset_name: Mapped[str] = mapped_column(String(60), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(20), nullable=False)
    data_origin: Mapped[DataOrigin] = mapped_column(str_enum(DataOrigin, "data_origin"), nullable=False)
    generator_name: Mapped[str] = mapped_column(String(60), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(20), nullable=False)
    config_version: Mapped[str] = mapped_column(String(20), nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    split_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    journey_count: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy.policy_id"), nullable=False)
    policy_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # SHA-256 over (path, uncompressed content SHA-256) of every data file; identifies the content.
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("journey_count > 0", name="journey_count_positive"),
        CheckConstraint("config_sha256 ~ '^[0-9a-f]{64}$'", name="config_sha256_hex"),
        CheckConstraint("policy_content_sha256 ~ '^[0-9a-f]{64}$'", name="policy_content_sha256_hex"),
        CheckConstraint("dataset_fingerprint ~ '^[0-9a-f]{64}$'", name="dataset_fingerprint_hex"),
    )
