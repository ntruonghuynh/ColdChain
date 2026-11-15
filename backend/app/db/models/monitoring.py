"""Milestone 3: detector configuration, evaluations, gaps, runs, warnings, incident revisions.

Append-only by design (C-07, C-08): rows are never deleted and their measured values never
change. A revision that is replaced gets ``superseded_by_evaluation_id`` / ``superseded_at``
set once; the "current" result is the revision with ``superseded_at IS NULL``. Names of the
gap measurements (contract §5.6): ``bracketing_span_s`` is the exact time between the two
bounds (used for the policy thresholds); ``estimated_missing_samples`` and
``estimated_missing_duration_s`` describe the scheduled samples that are missing (information
only, never compared with a policy threshold).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, str_enum, uuid_pk
from app.db.models.enums import (
    DetectionSource,
    EvaluationMode,
    EvaluationTrigger,
    ReassessmentReason,
    TemperatureDirection,
)
from app.db.types import UTCDateTime
from app.domain.detector import GapBound, GapStatus
from app.domain.reconcile import IncidentBasis, WarningKind


class DetectorConfigVersion(Base):
    """Immutable detector configuration version (nominal sampling interval, continuity limit)."""

    __tablename__ = "detector_config"

    detector_config_id: Mapped[uuid.UUID] = uuid_pk()
    detector_code: Mapped[str] = mapped_column(String(40), nullable=False)
    config_version: Mapped[str] = mapped_column(String(20), nullable=False)
    nominal_sampling_interval_s: Mapped[int] = mapped_column(Integer, nullable=False)
    max_continuous_interval_s: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("detector_code", "config_version"),
        CheckConstraint("nominal_sampling_interval_s > 0", name="nominal_positive"),
        CheckConstraint(
            "max_continuous_interval_s > nominal_sampling_interval_s "
            "AND max_continuous_interval_s < 2 * nominal_sampling_interval_s",
            name="continuity_between_one_and_two_intervals",
        ),
    )


class DetectorEvaluation(Base):
    """One evaluation of one sensor on one shipment at processing time ``as_of``."""

    __tablename__ = "detector_evaluation"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id"), nullable=False)
    mode: Mapped[EvaluationMode] = mapped_column(str_enum(EvaluationMode, "evaluation_mode"), nullable=False)
    trigger: Mapped[EvaluationTrigger] = mapped_column(
        str_enum(EvaluationTrigger, "evaluation_trigger"), nullable=False
    )
    trigger_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingest_batch.batch_id"))
    as_of: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    affected_from_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    affected_to_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    visible_reading_count: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy.policy_id"), nullable=False)
    detector_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("detector_config.detector_config_id"), nullable=False
    )
    detector_code_version: Mapped[str] = mapped_column(String(40), nullable=False)
    start_boundary_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    end_boundary_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_detector_evaluation_shipment_id_sensor_id_as_of", "shipment_id", "sensor_id", "as_of"),)


class DataGap(Base):
    """Confirmed missing-reading gap, one row per revision (BR-03, BR-04, C-02)."""

    __tablename__ = "data_gap"

    gap_revision_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    gap_key: Mapped[str] = mapped_column(String(64), nullable=False)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id"), nullable=False)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    start_bound: Mapped[GapBound] = mapped_column(str_enum(GapBound, "gap_start_bound"), nullable=False)
    end_bound: Mapped[GapBound] = mapped_column(str_enum(GapBound, "gap_end_bound"), nullable=False)
    bracketing_span_s: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    estimated_missing_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_missing_duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    gap_status: Mapped[GapStatus] = mapped_column(str_enum(GapStatus, "gap_status"), nullable=False)
    out_of_range_before: Mapped[bool] = mapped_column(Boolean, nullable=False)
    out_of_range_after: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("detector_evaluation.evaluation_id"), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    superseded_by_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detector_evaluation.evaluation_id")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("end_at > start_at", name="interval_ordered"),
        CheckConstraint("estimated_missing_samples >= 0", name="samples_not_negative"),
        CheckConstraint("(superseded_at IS NULL) = (superseded_by_evaluation_id IS NULL)", name="supersession_pair"),
        Index("ix_data_gap_shipment_id_sensor_id_start_at", "shipment_id", "sensor_id", "start_at"),
    )


class Detection(Base):
    """Observed out-of-range run (policy baseline), one row per revision (BR-02, BR-05)."""

    __tablename__ = "detection"

    detection_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    run_key: Mapped[str] = mapped_column(String(80), nullable=False)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id"), nullable=False)
    source: Mapped[DetectionSource] = mapped_column(str_enum(DetectionSource, "detection_source"), nullable=False)
    direction: Mapped[TemperatureDirection] = mapped_column(
        str_enum(TemperatureDirection, "temperature_direction"), nullable=False
    )
    first_event_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_event_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    reading_count: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_duration_s: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    threshold_min: Mapped[int] = mapped_column(Integer, nullable=False)
    meets_policy_duration: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confirmed_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    evidence_received_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    peak_c: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    run_open: Mapped[bool] = mapped_column(Boolean, nullable=False)
    preceded_by_gap_key: Mapped[str | None] = mapped_column(String(64))
    followed_by_gap_key: Mapped[str | None] = mapped_column(String(64))
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("detector_evaluation.evaluation_id"), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    superseded_by_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detector_evaluation.evaluation_id")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("last_event_at >= first_event_at", name="interval_ordered"),
        CheckConstraint("reading_count >= 1", name="reading_count_positive"),
        CheckConstraint("(superseded_at IS NULL) = (superseded_by_evaluation_id IS NULL)", name="supersession_pair"),
        Index("ix_detection_shipment_id_sensor_id_first_event_at", "shipment_id", "sensor_id", "first_event_at"),
    )


class DataQualityWarning(Base):
    """Persisted, auditable data-quality warning (C-03, U-01). Not an incident."""

    __tablename__ = "data_quality_warning"

    warning_revision_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    warning_key: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[WarningKind] = mapped_column(str_enum(WarningKind, "warning_kind"), nullable=False)
    affects_quality_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id"), nullable=False)
    run_key: Mapped[str | None] = mapped_column(String(80))
    gap_key: Mapped[str | None] = mapped_column(String(64))
    interval_start_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    interval_end_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    linked_incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incident.incident_id"))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    evaluation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("detector_evaluation.evaluation_id"))
    ingest_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingest_batch.batch_id"))
    raised_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    superseded_by_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detector_evaluation.evaluation_id")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("interval_end_at >= interval_start_at", name="interval_ordered"),
        CheckConstraint("evaluation_id IS NOT NULL OR ingest_batch_id IS NOT NULL", name="has_origin"),
        CheckConstraint("(superseded_at IS NULL) = (superseded_by_evaluation_id IS NULL)", name="supersession_pair"),
        Index("ix_data_quality_warning_shipment_id_sensor_id", "shipment_id", "sensor_id"),
    )


class IncidentRevision(Base):
    """Append-only evidence revision of an incident (C-08). Revision 1 is the opening state."""

    __tablename__ = "incident_revision"

    incident_revision_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident.incident_id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    extent_start_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    extent_end_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    extent_open: Mapped[bool] = mapped_column(Boolean, nullable=False)
    direction: Mapped[TemperatureDirection | None] = mapped_column(str_enum(TemperatureDirection, "incident_direction"))
    observed_duration_s: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    bracketing_span_s: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    gap_status: Mapped[GapStatus | None] = mapped_column(str_enum(GapStatus, "incident_gap_status"))
    peak_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    confirmed_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    evidence_received_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    gap_continuity_warning: Mapped[bool] = mapped_column(Boolean, nullable=False)
    basis: Mapped[IncidentBasis] = mapped_column(str_enum(IncidentBasis, "incident_basis"), nullable=False)
    merged_into_incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incident.incident_id"))
    basis_key: Mapped[str] = mapped_column(String(80), nullable=False)
    detection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("detection.detection_id"))
    gap_revision_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_gap.gap_revision_id"))
    incident_status_at_revision: Mapped[str] = mapped_column(String(10), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("detector_evaluation.evaluation_id"), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("incident_id", "revision"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("extent_end_at >= extent_start_at", name="extent_ordered"),
        CheckConstraint("(basis = 'MERGED_INTO') = (merged_into_incident_id IS NOT NULL)", name="merge_target"),
    )


class DecisionReassessment(Base):
    """U-04: late evidence touched an incident or shipment that already has a quality decision.

    The disposition and any executed warehouse release are never changed; this row flags
    the decision for human reassessment (BR-12: a change needs a new disposition).
    """

    __tablename__ = "decision_reassessment"

    reassessment_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    disposition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disposition.disposition_id"), nullable=False)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident.incident_id"), nullable=False)
    incident_revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incident_revision.incident_revision_id"), nullable=False
    )
    reason: Mapped[ReassessmentReason] = mapped_column(
        str_enum(ReassessmentReason, "reassessment_reason"), nullable=False
    )
    warehouse_release_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("warehouse_release.release_id"))
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("detector_evaluation.evaluation_id"), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (UniqueConstraint("disposition_id", "incident_revision_id"),)
