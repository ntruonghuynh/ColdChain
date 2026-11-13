"""Shipments, sensors and sensor assignments."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, str_enum, uuid_pk
from app.db.models.enums import DataOrigin, ShipmentStatus
from app.db.types import UTCDateTime


class Shipment(Base):
    __tablename__ = "shipment"

    shipment_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("product.product_id"), nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    shipper_org_id: Mapped[str] = mapped_column(ForeignKey("organization.org_id"), nullable=False)
    carrier_org_id: Mapped[str] = mapped_column(ForeignKey("organization.org_id"), nullable=False)
    receiver_org_id: Mapped[str] = mapped_column(ForeignKey("organization.org_id"), nullable=False)
    origin: Mapped[str | None] = mapped_column(String(200))
    destination: Mapped[str | None] = mapped_column(String(200))
    # State transitions are implemented in Milestone 5; here only the allowed values.
    status: Mapped[ShipmentStatus] = mapped_column(
        str_enum(ShipmentStatus, "shipment_status"), nullable=False, server_default=ShipmentStatus.CREATED.value
    )
    data_origin: Mapped[DataOrigin] = mapped_column(str_enum(DataOrigin, "data_origin"), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        # The shipment's policy must belong to the shipment's product.
        ForeignKeyConstraint(
            ["policy_id", "product_id"], ["policy.policy_id", "policy.product_id"],
            name="fk_shipment_policy_product",
        ),
    )


class Sensor(Base):
    __tablename__ = "sensor"

    sensor_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    sensor_type: Mapped[str] = mapped_column(String(60), nullable=False)
    owner_org_id: Mapped[str | None] = mapped_column(ForeignKey("organization.org_id"))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()


class SensorAssignment(Base):
    """Which sensor travelled with which shipment, and when."""

    __tablename__ = "sensor_assignment"

    assignment_id: Mapped[uuid.UUID] = uuid_pk()
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id"), nullable=False)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    assigned_from: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    assigned_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("sensor_id", "shipment_id", "assigned_from"),
        CheckConstraint("assigned_to IS NULL OR assigned_to > assigned_from", name="assignment_interval"),
    )
