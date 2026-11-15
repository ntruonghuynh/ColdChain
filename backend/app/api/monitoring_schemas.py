"""Schemas of the Milestone 3 monitoring API (ingestion, telemetry, gaps, runs, incidents).

Names match the database and the contract (``docs/design/m3-baseline-detector-contract.md``):
``bracketing_span_*`` is the exact time between a gap's two bounds (compared with the policy
thresholds); ``estimated_missing_samples`` / ``estimated_missing_duration_s`` describe the
scheduled samples that are missing (information only). No simulator label is exposed.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------- ingestion ----------


class IngestBatchIn(BaseModel):
    """Live ingestion request. ``received_at`` is set by the server and must not be sent (C-09)."""

    model_config = ConfigDict(extra="forbid")

    business_ref: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="Unique batch reference (BR-13). Re-sending the same reference and "
        "payload returns the original result.",
    )
    shipment_id: str = Field(min_length=1, max_length=60)
    readings: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=5000,
        description="Each: sensor_id, event_at (ISO 8601 with time zone), temperature_c (number, at most "
        "2 decimals, -40 to 60), optional shipment_id. Validated per record.",
    )
    context_records: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=5000,
        description="Each: sensor_id, event_at (must match a reading), door_state OPEN|CLOSED|null, "
        "battery_level_pct (0-100) or null, ambient_temperature_c or null (null = not reported).",
    )


class RecordResultOut(BaseModel):
    index: int
    record_kind: str
    outcome: Literal["ACCEPTED", "DUPLICATE_IGNORED", "REJECTED"]
    reason_code: str | None = None
    detail: str | None = None


class EvaluationSummaryOut(BaseModel):
    evaluation_id: uuid.UUID
    as_of: datetime
    trigger: str
    gaps_confirmed: int
    runs_changed: int
    warnings_raised: int
    incidents_opened: list[str]
    incidents_revised: list[str]
    reassessments_flagged: int


class IngestResultOut(BaseModel):
    batch_id: uuid.UUID
    business_ref: str
    shipment_id: str
    received_at: datetime
    ingest_mode: str
    idempotent_replay: bool
    record_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    records: list[RecordResultOut]
    evaluations: list[EvaluationSummaryOut]


# ---------- monitoring ----------


class PolicyRefOut(BaseModel):
    policy_id: uuid.UUID | None
    policy_code: str
    policy_version: str
    content_sha256: str
    min_temp_c: Decimal
    max_temp_c: Decimal
    high_excursion_min_duration_min: int
    low_excursion_min_duration_min: int
    gap_unknown_after_min: int
    gap_review_at_min: int


class DetectorConfigOut(BaseModel):
    detector_config_id: uuid.UUID | None
    detector_code: str
    config_version: str
    content_sha256: str
    nominal_sampling_interval_s: int
    max_continuous_interval_s: int


class MonitoringWindowOut(BaseModel):
    assigned_from: datetime | None
    assigned_to: datetime | None


class CommunicationOut(BaseModel):
    """Presentation only (not a detector rule): facts about received uploads at ``as_of``."""

    status: Literal[
        "NOT_STARTED",
        "ENDED",
        "NO_UPLOAD_YET",
        "PATTERN_NOT_ESTABLISHED",
        "WITHIN_RECENT_UPLOAD_INTERVALS",
        "LONGER_THAN_RECENT_UPLOAD_INTERVALS",
    ]
    last_upload_received_at: datetime | None
    since_last_upload_s: Decimal | None
    observed_upload_interval_s: Decimal | None = Field(description="Median of the recent upload intervals (observed)")
    longest_recent_upload_interval_s: Decimal | None
    recent_intervals_used: int
    expected_schedule_configured: bool = Field(
        description="False in DET-BASELINE v1.0.0: no gateway schedule is configured, so no upload is called overdue"
    )


class SensorStatusOut(BaseModel):
    shipment_id: str
    sensor_id: str
    as_of: datetime
    state: Literal["NOT_STARTED", "CURRENT", "STALE", "UNKNOWN", "ENDED"]
    newest_event_at: datetime | None
    newest_received_at: datetime | None
    visible_reading_count: int
    unobserved_since_at: datetime | None
    unobserved_duration_s: Decimal | None
    provisional_review_threshold_reached: bool
    end_boundary_established: bool
    monitoring_window: MonitoringWindowOut
    confirmed_gaps: dict[str, int]
    confirmed_gap_span_s: Decimal
    note: str
    last_observed_temperature_c: Decimal | None
    last_observed_event_at: datetime | None
    last_observed_temperature_state: str | None
    communication: CommunicationOut
    open_incidents_as_of: dict[str, int]


class ReadingPointOut(BaseModel):
    event_at: datetime
    received_at: datetime
    temperature_c: Decimal
    batch_ref: str
    delivery_lag_s: Decimal
    temperature_state: str | None
    inside_extent: bool | None = None


class GapOut(BaseModel):
    gap_key: str
    sensor_id: str
    start_at: datetime
    end_at: datetime
    start_bound: str
    end_bound: str
    bracketing_span_s: Decimal
    bracketing_span_min: float
    estimated_missing_samples: int
    estimated_missing_duration_s: int
    gap_status: str
    out_of_range_before: bool
    out_of_range_after: bool
    raised_at: datetime
    superseded_at: datetime | None
    state: Literal["CURRENT", "SUPERSEDED"]


class RunOut(BaseModel):
    run_key: str
    sensor_id: str
    source: str
    direction: str
    first_event_at: datetime
    last_event_at: datetime
    reading_count: int
    observed_duration_s: Decimal
    observed_duration_min: float
    threshold_min: int
    meets_policy_duration: bool
    confirmed_event_at: datetime | None
    evidence_received_at: datetime | None
    peak_c: Decimal
    run_open: bool
    preceded_by_gap_key: str | None
    followed_by_gap_key: str | None
    raised_at: datetime
    superseded_at: datetime | None
    state: Literal["CURRENT", "SUPERSEDED"]


class WarningOut(BaseModel):
    warning_key: str
    kind: str
    affects_quality_evidence: bool
    sensor_id: str
    interval_start_at: datetime
    interval_end_at: datetime
    linked_incident_id: uuid.UUID | None
    message: str
    details: dict[str, Any] | None
    raised_at: datetime
    superseded_at: datetime | None
    state: Literal["CURRENT", "SUPERSEDED"]


class SensorTelemetryOut(BaseModel):
    sensor_id: str
    status: SensorStatusOut
    readings: list[ReadingPointOut]
    gaps: list[GapOut]
    runs: list[RunOut]


class TelemetryOut(BaseModel):
    shipment_id: str
    data_origin: str
    as_of: datetime
    policy: PolicyRefOut
    detector_config: DetectorConfigOut
    sensors: list[SensorTelemetryOut]


class DeliveryBatchOut(BaseModel):
    batch_id: uuid.UUID
    business_ref: str
    ingest_mode: str
    received_at: datetime
    reading_count: int
    first_event_at: datetime | None
    last_event_at: datetime | None
    max_delivery_lag_s: Decimal | None
    monitoring_state_before_receipt: str | None
    unobserved_before_receipt_s: Decimal | None
    late_backfill: bool
    out_of_order: bool
    gap_revisions_superseded: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int


class DeliveriesOut(BaseModel):
    shipment_id: str
    data_origin: str
    batches: list[DeliveryBatchOut]
    gap_history: list[GapOut]


# ---------- incidents ----------


class IncidentRevisionOut(BaseModel):
    revision: int
    extent_start_at: datetime
    extent_end_at: datetime
    extent_open: bool
    direction: str | None
    observed_duration_s: Decimal | None
    observed_duration_min: float | None
    bracketing_span_s: Decimal | None
    bracketing_span_min: float | None
    gap_status: str | None
    peak_c: Decimal | None
    confirmed_event_at: datetime | None
    evidence_received_at: datetime | None
    gap_continuity_warning: bool
    basis: str
    merged_into_incident_id: uuid.UUID | None
    incident_status_at_revision: str
    evaluation_id: uuid.UUID
    raised_at: datetime


class IncidentOut(BaseModel):
    incident_id: uuid.UUID
    business_ref: str
    shipment_id: str
    sensor_id: str | None
    category: str
    status: str
    opened_at: datetime
    closed_at: datetime | None
    detected_by: str
    detector_version: str | None
    summary: str | None
    data_origin: str | None
    policy_code: str | None
    policy_version: str | None
    latest: IncidentRevisionOut | None
    review_state: Literal["PENDING_QUALITY_REVIEW", "CLOSED_BY_QUALITY_DISPOSITION"]


class OpeningEvaluationOut(BaseModel):
    evaluation_id: uuid.UUID
    mode: str
    trigger: str
    as_of: datetime
    input_fingerprint: str
    detector_code_version: str
    visible_reading_count: int


class EvidenceOut(BaseModel):
    readings: list[ReadingPointOut]
    gaps: list[GapOut]
    warnings: list[WarningOut]


class DispositionRefOut(BaseModel):
    disposition_id: uuid.UUID
    business_ref: str
    decision: str
    decided_at: datetime


class ReassessmentOut(BaseModel):
    reassessment_id: uuid.UUID
    disposition_id: uuid.UUID
    reason: str
    incident_revision_id: uuid.UUID
    warehouse_release_id: uuid.UUID | None
    raised_at: datetime


class IncidentDetailOut(IncidentOut):
    revisions: list[IncidentRevisionOut]
    evidence: EvidenceOut
    policy: PolicyRefOut | None
    detector_config: DetectorConfigOut | None
    opening_evaluation: OpeningEvaluationOut | None
    dispositions: list[DispositionRefOut]
    reassessments: list[ReassessmentOut]


class MonitoringSummaryOut(BaseModel):
    as_of: datetime
    shipments_total: int
    shipments_evaluated: int
    sensors_by_monitoring_state: dict[str, int]
    open_incidents_by_category: dict[str, int]
    open_incidents_by_basis: dict[str, int]
    current_warnings_by_kind: dict[str, int]
    current_evidence_warnings: int
    batches_total: int
    rejected_records_total: int
    duplicates_ignored_total: int
    readings_total: int
    detector_config: DetectorConfigOut | None
