"""Workflow records: incidents, quality dispositions, custody events, warehouse releases.

Authorization relationships are enforced by the database, not only by code:

* ``disposition`` has a composite foreign key ``(decided_by_user_id, decided_by_role)``
  to ``user_role`` and a CHECK that the role is QUALITY, so a disposition can only
  exist for a user who was granted the QUALITY role (approved rule: only the
  authorized Quality Officer can approve shipment release; BC-05).
* ``warehouse_release`` references ``(disposition_id, shipment_id, decision)`` with a
  CHECK that the decision is RELEASE, so a release can never point at a quarantine
  decision or at another shipment's decision.

Workflow logic (state transitions, chain confirmation checks) is Milestone 5.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, str_enum, uuid_pk
from app.db.models.enums import CustodyStage, Decision, DetectionSource, IncidentCategory, IncidentStatus, Role
from app.db.types import UTCDateTime


class Incident(Base):
    __tablename__ = "incident"

    incident_id: Mapped[uuid.UUID] = uuid_pk()
    business_ref: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    category: Mapped[IncidentCategory] = mapped_column(
        str_enum(IncidentCategory, "incident_category"), nullable=False
    )
    status: Mapped[IncidentStatus] = mapped_column(
        str_enum(IncidentStatus, "incident_status"), nullable=False, server_default=IncidentStatus.OPEN.value
    )
    interval_start: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    interval_end: Mapped[datetime | None] = mapped_column(UTCDateTime())
    detected_by: Mapped[DetectionSource] = mapped_column(
        str_enum(DetectionSource, "detection_source"), nullable=False
    )
    detector_version: Mapped[str | None] = mapped_column(String(60))
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy.policy_id"), nullable=False)
    # Milestone 3 (detector-created incidents): sensor, detector configuration and the evaluation
    # that opened the incident. Facts recorded at opening are never edited (C-08).
    sensor_id: Mapped[str | None] = mapped_column(ForeignKey("sensor.sensor_id"))
    detector_config_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("detector_config.detector_config_id"))
    opened_by_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detector_evaluation.evaluation_id")
    )
    summary: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    business_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_event.event_id"), unique=True
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("incident_id", "shipment_id"),
        CheckConstraint("interval_end IS NULL OR interval_end >= interval_start", name="interval_ordered"),
        CheckConstraint(
            "(status = 'OPEN' AND closed_at IS NULL) OR (status = 'CLOSED' AND closed_at IS NOT NULL)",
            name="closed_at_matches_status",
        ),
        Index("ix_incident_status_category", "status", "category"),
        Index("ix_incident_shipment_id", "shipment_id"),
    )


class Disposition(Base):
    """Quality decision (RELEASE or QUARANTINE) made by a user holding the QUALITY role."""

    __tablename__ = "disposition"

    disposition_id: Mapped[uuid.UUID] = uuid_pk()
    business_ref: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    decision: Mapped[Decision] = mapped_column(str_enum(Decision, "decision"), nullable=False)
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    decided_by_role: Mapped[Role] = mapped_column(
        str_enum(Role, "decided_by_role"), nullable=False, server_default=Role.QUALITY.value
    )
    decided_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_sha256: Mapped[str | None] = mapped_column(String(64))
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy.policy_id"), nullable=False)
    business_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_event.event_id"), unique=True
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        ForeignKeyConstraint(
            ["decided_by_user_id", "decided_by_role"], ["user_role.user_id", "user_role.role"],
            name="fk_disposition_decider_role",
        ),
        CheckConstraint("decided_by_role = 'QUALITY'", name="decider_is_quality"),
        CheckConstraint("length(trim(rationale)) > 0", name="rationale_not_blank"),
        CheckConstraint("evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{64}$'", name="evidence_sha256_hex"),
        UniqueConstraint("disposition_id", "shipment_id"),
        UniqueConstraint("disposition_id", "shipment_id", "decision"),
    )


class DispositionIncident(Base):
    """Which incidents a disposition addresses. Both must belong to the same shipment."""

    __tablename__ = "disposition_incident"

    disposition_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    shipment_id: Mapped[str] = mapped_column(String(60), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["disposition_id", "shipment_id"], ["disposition.disposition_id", "disposition.shipment_id"],
            name="fk_disposition_incident_disposition",
        ),
        ForeignKeyConstraint(
            ["incident_id", "shipment_id"], ["incident.incident_id", "incident.shipment_id"],
            name="fk_disposition_incident_incident",
        ),
    )


class CustodyEvent(Base):
    __tablename__ = "custody_event"

    custody_event_id: Mapped[uuid.UUID] = uuid_pk()
    business_ref: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    stage: Mapped[CustodyStage] = mapped_column(str_enum(CustodyStage, "custody_stage"), nullable=False)
    from_org_id: Mapped[str] = mapped_column(ForeignKey("organization.org_id"), nullable=False)
    to_org_id: Mapped[str] = mapped_column(ForeignKey("organization.org_id"), nullable=False)
    accepted_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.user_id"), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    business_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_event.event_id"), unique=True
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (CheckConstraint("from_org_id <> to_org_id", name="different_orgs"),)


class WarehouseRelease(Base):
    """Physical release from the warehouse. Must reference a RELEASE disposition of the same shipment."""

    __tablename__ = "warehouse_release"

    release_id: Mapped[uuid.UUID] = uuid_pk()
    business_ref: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    shipment_id: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    disposition_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    disposition_decision: Mapped[Decision] = mapped_column(
        str_enum(Decision, "disposition_decision"), nullable=False, server_default=text("'RELEASE'")
    )
    released_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.user_id"), nullable=False)
    released_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    business_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_event.event_id"), unique=True
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        ForeignKeyConstraint(
            ["disposition_id", "shipment_id", "disposition_decision"],
            ["disposition.disposition_id", "disposition.shipment_id", "disposition.decision"],
            name="fk_warehouse_release_disposition",
        ),
        CheckConstraint("disposition_decision = 'RELEASE'", name="requires_release_decision"),
    )
