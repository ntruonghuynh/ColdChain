"""Monitoring read API: telemetry timeline, sensor status, missing and delayed data, detections,
warnings, incidents (excursion queue) and summaries. Read-only, no business logic.

Every endpoint that takes ``as_of`` is causal: it shows only what had been received and
raised by that processing time (default: now). Nothing from the simulator's labels is exposed.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.monitoring_schemas import (
    DeliveriesOut,
    DetectorConfigOut,
    GapOut,
    IncidentDetailOut,
    IncidentOut,
    MonitoringSummaryOut,
    RunOut,
    SensorStatusOut,
    TelemetryOut,
    WarningOut,
)
from app.api.schemas import Envelope, ListEnvelope, ListMeta
from app.core.errors import AppError, NotFoundError
from app.db.models import (
    DataGap,
    DataQualityWarning,
    Detection,
    DetectorConfigVersion,
    SensorAssignment,
)
from app.db.models.enums import IncidentCategory, IncidentStatus
from app.db.session import get_db
from app.services import queries

router = APIRouter(tags=["monitoring"])

AS_OF = Query(
    default=None,
    description="Processing time to view (ISO 8601 with time zone). Default: now. "
    "Only data received and results raised by then are shown.",
)


def _as_of(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        raise AppError(
            "as_of must include a time zone (for example 2026-09-10T12:00:00Z).",
            code="validation_error",
            status_code=422,
        )
    return value.astimezone(UTC)


@router.get(
    "/shipments/{shipment_id}/telemetry",
    response_model=Envelope[TelemetryOut],
    summary="Temperature timeline with confirmed gaps, runs and monitoring status",
)
def get_telemetry(
    shipment_id: str, as_of: datetime | None = AS_OF, db: Session = Depends(get_db)
) -> Envelope[TelemetryOut]:
    return Envelope(data=TelemetryOut.model_validate(queries.telemetry(db, shipment_id, _as_of(as_of))))


@router.get(
    "/shipments/{shipment_id}/monitoring",
    response_model=Envelope[list[SensorStatusOut]],
    summary="Monitoring state (CURRENT / STALE / UNKNOWN) of each sensor of a shipment",
)
def get_shipment_monitoring(
    shipment_id: str, as_of: datetime | None = AS_OF, db: Session = Depends(get_db)
) -> Envelope[list[SensorStatusOut]]:
    at = _as_of(as_of)
    _, policy, config = queries.shipment_context(db, shipment_id)
    sensors = sorted(
        set(db.scalars(select(SensorAssignment.sensor_id).where(SensorAssignment.shipment_id == shipment_id)).all())
    )
    return Envelope(
        data=[
            SensorStatusOut.model_validate(queries.sensor_status(db, shipment_id, s, at, policy, config))
            for s in sensors
        ]
    )


@router.get(
    "/sensors/{sensor_id}/status",
    response_model=Envelope[list[SensorStatusOut]],
    summary="Monitoring state of one sensor on each shipment it is assigned to",
)
def get_sensor_status(
    sensor_id: str, as_of: datetime | None = AS_OF, db: Session = Depends(get_db)
) -> Envelope[list[SensorStatusOut]]:
    at = _as_of(as_of)
    shipments = sorted(
        set(db.scalars(select(SensorAssignment.shipment_id).where(SensorAssignment.sensor_id == sensor_id)).all())
    )
    if not shipments:
        raise NotFoundError(f"Sensor {sensor_id} has no monitoring assignment.")
    out = []
    for sid in shipments:
        _, policy, config = queries.shipment_context(db, sid)
        out.append(SensorStatusOut.model_validate(queries.sensor_status(db, sid, sensor_id, at, policy, config)))
    return Envelope(data=out)


@router.get(
    "/shipments/{shipment_id}/deliveries",
    response_model=Envelope[DeliveriesOut],
    summary="Missing and delayed data: received batches, delivery lag, gaps reconciled by late data",
)
def get_deliveries(shipment_id: str, db: Session = Depends(get_db)) -> Envelope[DeliveriesOut]:
    return Envelope(data=DeliveriesOut.model_validate(queries.deliveries(db, shipment_id)))


@router.get(
    "/shipments/{shipment_id}/data-gaps",
    response_model=Envelope[list[GapOut]],
    summary="Confirmed missing-reading gaps (current at as_of, or full history)",
)
def get_gaps(
    shipment_id: str,
    as_of: datetime | None = AS_OF,
    include_superseded: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Envelope[list[GapOut]]:
    at = _as_of(as_of)
    queries.shipment_context(db, shipment_id)
    stmt = select(DataGap).where(DataGap.shipment_id == shipment_id, DataGap.raised_at <= at)
    if not include_superseded:
        stmt = stmt.where(queries.visible_at(DataGap, at))
    rows = db.scalars(stmt.order_by(DataGap.start_at, DataGap.raised_at)).all()
    return Envelope(data=[GapOut.model_validate(queries.gap_dict(g, at)) for g in rows])


@router.get(
    "/shipments/{shipment_id}/detections",
    response_model=Envelope[list[RunOut]],
    summary="Observed temperature runs of the policy baseline (confirmed excursions and near misses)",
)
def get_detections(
    shipment_id: str,
    as_of: datetime | None = AS_OF,
    meets_policy_duration: bool | None = Query(default=None),
    include_superseded: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Envelope[list[RunOut]]:
    at = _as_of(as_of)
    queries.shipment_context(db, shipment_id)
    stmt = select(Detection).where(Detection.shipment_id == shipment_id, Detection.raised_at <= at)
    if not include_superseded:
        stmt = stmt.where(queries.visible_at(Detection, at))
    if meets_policy_duration is not None:
        stmt = stmt.where(Detection.meets_policy_duration.is_(meets_policy_duration))
    rows = db.scalars(stmt.order_by(Detection.first_event_at, Detection.raised_at)).all()
    return Envelope(data=[RunOut.model_validate(queries.run_dict(d, at)) for d in rows])


@router.get(
    "/shipments/{shipment_id}/warnings",
    response_model=Envelope[list[WarningOut]],
    summary="Data-quality warnings (persisted; not incidents)",
)
def get_warnings(
    shipment_id: str,
    as_of: datetime | None = AS_OF,
    evidence_only: bool = Query(
        default=False, description="Only warnings that belong in the quality evidence package (C-03)"
    ),
    include_superseded: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Envelope[list[WarningOut]]:
    at = _as_of(as_of)
    queries.shipment_context(db, shipment_id)
    stmt = select(DataQualityWarning).where(
        DataQualityWarning.shipment_id == shipment_id, DataQualityWarning.raised_at <= at
    )
    if not include_superseded:
        stmt = stmt.where(queries.visible_at(DataQualityWarning, at))
    if evidence_only:
        stmt = stmt.where(DataQualityWarning.affects_quality_evidence.is_(True))
    rows = db.scalars(stmt.order_by(DataQualityWarning.interval_start_at, DataQualityWarning.raised_at)).all()
    return Envelope(data=[WarningOut.model_validate(queries.warning_dict(w, at)) for w in rows])


@router.get(
    "/incidents",
    response_model=ListEnvelope[IncidentOut],
    summary="Incidents; with status=OPEN this is the excursion queue (FR-20)",
)
def list_incidents(
    status: IncidentStatus | None = Query(default=None),
    category: IncidentCategory | None = Query(default=None),
    shipment_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ListEnvelope[IncidentOut]:
    rows, total = queries.list_incidents(
        db,
        status=status.value if status else None,
        category=category.value if category else None,
        shipment_id=shipment_id,
        limit=limit,
        offset=offset,
    )
    return ListEnvelope(
        data=[IncidentOut.model_validate(r) for r in rows], meta=ListMeta(total=total, limit=limit, offset=offset)
    )


@router.get(
    "/incidents/{incident_id}",
    response_model=Envelope[IncidentDetailOut],
    summary="Incident with its revisions, evidence, policy and detector references",
)
def get_incident(incident_id: uuid.UUID, db: Session = Depends(get_db)) -> Envelope[IncidentDetailOut]:
    return Envelope(data=IncidentDetailOut.model_validate(queries.incident_detail(db, incident_id)))


@router.get(
    "/monitoring/summary",
    response_model=Envelope[MonitoringSummaryOut],
    summary="Monitoring summary: sensor states, open incidents, warnings, ingestion totals",
)
def get_summary(as_of: datetime | None = AS_OF, db: Session = Depends(get_db)) -> Envelope[MonitoringSummaryOut]:
    return Envelope(data=MonitoringSummaryOut.model_validate(queries.monitoring_summary(db, _as_of(as_of))))


@router.get(
    "/detector-configs",
    response_model=Envelope[list[DetectorConfigOut]],
    summary="Detector configuration versions (nominal sampling interval, continuity limit)",
)
def list_detector_configs(db: Session = Depends(get_db)) -> Envelope[list[DetectorConfigOut]]:
    rows = db.scalars(
        select(DetectorConfigVersion).order_by(
            DetectorConfigVersion.detector_code, DetectorConfigVersion.config_version
        )
    ).all()
    return Envelope(
        data=[
            DetectorConfigOut(
                detector_config_id=r.detector_config_id,
                detector_code=r.detector_code,
                config_version=r.config_version,
                content_sha256=r.content_sha256,
                nominal_sampling_interval_s=r.nominal_sampling_interval_s,
                max_continuous_interval_s=r.max_continuous_interval_s,
            )
            for r in rows
        ]
    )
