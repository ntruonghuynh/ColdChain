"""Causal, read-only evidence adapter for M6 incident explanations."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import (
    BusinessEvent, ChainRecord, ContextReading, DataGap, DataQualityWarning, Detection,
    Disposition, DispositionIncident, Incident, IncidentRevision, MLPrediction, Policy,
    Product, Reading, Shipment,
)
from coldchain_llm.temporal import build_temporal_facts


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def build_evidence_package(db: Session, incident_id: uuid.UUID, cutoff: datetime) -> dict[str, Any]:
    """Build only facts available by cutoff; return source strings for citation checking."""
    if cutoff.tzinfo is None:
        raise ValueError("evidence cutoff must include timezone")
    cutoff = cutoff.astimezone(UTC)
    incident = db.get(Incident, incident_id)
    if incident is None or incident.opened_at > cutoff or incident.created_at > cutoff:
        raise NotFoundError("Incident was not available at the requested evidence cutoff.")
    shipment = db.get(Shipment, incident.shipment_id)
    policy = db.get(Policy, incident.policy_id)
    product = db.get(Product, shipment.product_id) if shipment else None
    if shipment is None or policy is None or product is None or policy.effective_from > cutoff:
        raise NotFoundError("Applicable shipment policy is unavailable at the evidence cutoff.")

    revisions = list(db.scalars(select(IncidentRevision).where(
        IncidentRevision.incident_id == incident_id,
        IncidentRevision.raised_at <= cutoff,
        IncidentRevision.created_at <= cutoff,
    ).order_by(IncidentRevision.revision)).all())
    revision = revisions[-1] if revisions else None
    interval_start = revision.extent_start_at if revision else incident.interval_start
    interval_end = revision.extent_end_at if revision else (incident.interval_end or incident.interval_start)
    interval_start = min(interval_start, incident.interval_start)
    if incident.interval_end and incident.interval_end <= cutoff:
        interval_end = max(interval_end, incident.interval_end)
    pad = timedelta(minutes=30)
    window_start, window_end = interval_start - pad, min(interval_end + pad, cutoff)
    sensor_id = incident.sensor_id

    sources: dict[str, str] = {}
    incident_value = {
        "incident_id": str(incident.incident_id), "incident_ref": incident.business_ref,
        "shipment_id": incident.shipment_id, "category": incident.category.value,
        "opened_at": incident.opened_at.isoformat(), "status_at_cutoff": (
            revision.incident_status_at_revision if revision else "UNKNOWN"
        ),
        "sensor_id": sensor_id, "revision": revision.revision if revision else None,
        "revision_raised_at": revision.raised_at.isoformat() if revision else None,
        "extent_start_at": interval_start.isoformat(), "extent_end_at": interval_end.isoformat(),
    }
    incident_ref = f"SYS:incident/{incident.incident_id}"
    sources[f"{incident_ref}:revision/{revision.revision if revision else 0}"] = json.dumps(
        incident_value, ensure_ascii=False, sort_keys=True
    )

    policy_value = {
        "policy_code": policy.policy_code, "policy_version": policy.policy_version,
        "policy_sha256": policy.content_sha256, "product_category": product.category,
        "procedure_version": policy.procedure_version, "min_temp_c": _scalar(policy.min_temp_c),
        "max_temp_c": _scalar(policy.max_temp_c),
        "high_excursion_min_duration_min": policy.high_excursion_min_duration_min,
        "low_excursion_min_duration_min": policy.low_excursion_min_duration_min,
        "gap_unknown_after_min": policy.gap_unknown_after_min,
        "gap_review_at_min": policy.gap_review_at_min,
        "disclaimer": policy.disclaimer,
    }
    policy_ref = f"SYS:policy/{policy.policy_code}@{policy.policy_version}"
    sources[policy_ref] = json.dumps(policy_value, ensure_ascii=False, sort_keys=True)

    readings: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    detections: list[dict[str, Any]] = []
    ml_predictions: list[dict[str, Any]] = []
    if sensor_id:
        rows = db.execute(select(Reading, ContextReading).outerjoin(
            ContextReading,
            and_(ContextReading.sensor_id == Reading.sensor_id,
                 ContextReading.shipment_id == Reading.shipment_id,
                 ContextReading.event_at == Reading.event_at,
                 ContextReading.received_at <= cutoff),
        ).where(
            Reading.shipment_id == shipment.shipment_id, Reading.sensor_id == sensor_id,
            Reading.event_at >= window_start, Reading.event_at <= window_end,
            Reading.event_at <= cutoff, Reading.received_at <= cutoff,
        ).order_by(Reading.event_at).limit(1000)).all()
        for reading, context in rows:
            readings.append({
                "reading_id": str(reading.reading_id), "event_at": reading.event_at.isoformat(),
                "received_at": reading.received_at.isoformat(), "temperature_c": _scalar(reading.temperature_c),
                "ambient_temperature_c": _scalar(context.ambient_temperature_c) if context and context.ambient_temperature_c is not None else None,
                "door_state": context.door_state.value if context and context.door_state else None,
                "battery_level_pct": _scalar(context.battery_level_pct) if context and context.battery_level_pct is not None else None,
            })
        gap_rows = db.scalars(select(DataGap).where(
            DataGap.shipment_id == shipment.shipment_id, DataGap.sensor_id == sensor_id,
            DataGap.start_at <= window_end, DataGap.end_at >= window_start,
            DataGap.raised_at <= cutoff, DataGap.created_at <= cutoff,
            or_(DataGap.superseded_at.is_(None), DataGap.superseded_at > cutoff),
        ).order_by(DataGap.start_at, DataGap.raised_at)).all()
        for item in gap_rows:
            gaps.append({"gap_revision_id": str(item.gap_revision_id), "start_at": item.start_at.isoformat(),
                         "end_at": item.end_at.isoformat(), "status": item.gap_status.value,
                         "bracketing_span_s": _scalar(item.bracketing_span_s), "raised_at": item.raised_at.isoformat()})
        warning_rows = db.scalars(select(DataQualityWarning).where(
            DataQualityWarning.shipment_id == shipment.shipment_id,
            DataQualityWarning.sensor_id == sensor_id,
            DataQualityWarning.interval_start_at <= window_end,
            DataQualityWarning.interval_end_at >= window_start,
            DataQualityWarning.raised_at <= cutoff,
            DataQualityWarning.created_at <= cutoff,
            or_(DataQualityWarning.superseded_at.is_(None), DataQualityWarning.superseded_at > cutoff),
        ).order_by(DataQualityWarning.raised_at)).all()
        for item in warning_rows:
            warnings.append({"warning_id": str(item.warning_revision_id), "kind": item.kind.value,
                             "interval_start_at": item.interval_start_at.isoformat(),
                             "interval_end_at": item.interval_end_at.isoformat(), "message": item.message,
                             "raised_at": item.raised_at.isoformat()})
        detection_rows = db.scalars(select(Detection).where(
            Detection.shipment_id == shipment.shipment_id, Detection.sensor_id == sensor_id,
            Detection.first_event_at <= window_end, Detection.last_event_at >= window_start,
            Detection.raised_at <= cutoff, Detection.created_at <= cutoff,
            or_(Detection.superseded_at.is_(None), Detection.superseded_at > cutoff),
        ).order_by(Detection.raised_at)).all()
        for item in detection_rows:
            detections.append({"detection_id": str(item.detection_id), "direction": item.direction.value,
                               "first_event_at": item.first_event_at.isoformat(),
                               "last_event_at": item.last_event_at.isoformat(),
                               "reading_count": item.reading_count, "peak_c": _scalar(item.peak_c),
                               "meets_policy_duration": item.meets_policy_duration,
                               "raised_at": item.raised_at.isoformat(), "source": item.source.value})
        ml_rows = db.scalars(select(MLPrediction).where(
            MLPrediction.shipment_id == shipment.shipment_id, MLPrediction.sensor_id == sensor_id,
            MLPrediction.as_of <= cutoff, MLPrediction.created_at <= cutoff,
        ).order_by(MLPrediction.as_of).limit(50)).all()
        for item in ml_rows:
            ml_predictions.append({"prediction_id": str(item.prediction_id), "as_of": item.as_of.isoformat(),
                                   "model_version": item.model_version,
                                   "feature_schema_version": item.feature_schema_version,
                                   "status": item.status, "risk_probability": _scalar(item.risk_probability),
                                   "threshold": _scalar(item.threshold), "alert": item.alert,
                                   "advisory_only": item.advisory_only, "evidence": item.evidence})

    def add_sources(prefix: str, items: list[dict[str, Any]], key: str) -> None:
        for item in items:
            source_id = f"SYS:{prefix}/{item[key]}"
            sources[source_id] = json.dumps(item, ensure_ascii=False, sort_keys=True)

    add_sources("reading", readings, "reading_id")
    add_sources("gap", gaps, "gap_revision_id")
    add_sources("warning", warnings, "warning_id")
    add_sources("m3-detection", detections, "detection_id")
    add_sources("m4-prediction", ml_predictions, "prediction_id")

    dispositions: list[dict[str, Any]] = []
    rows = db.execute(select(Disposition, BusinessEvent, ChainRecord).join(
        DispositionIncident, DispositionIncident.disposition_id == Disposition.disposition_id
    ).outerjoin(BusinessEvent, BusinessEvent.event_id == Disposition.business_event_id)
      .outerjoin(ChainRecord, ChainRecord.event_id == Disposition.business_event_id)
      .where(DispositionIncident.incident_id == incident_id, Disposition.decided_at <= cutoff,
             Disposition.created_at <= cutoff))
    for disposition, event, chain_record in rows:
        value = {"disposition_id": str(disposition.disposition_id), "decision": disposition.decision.value,
                 "decided_at": disposition.decided_at.isoformat(), "decided_by_role": disposition.decided_by_role.value,
                 "business_ref": disposition.business_ref,
                 "chain_confirmed_at": chain_record.confirmed_at.isoformat()
                 if chain_record and chain_record.confirmed_at <= cutoff else None,
                 "policy_version": policy.policy_version}
        dispositions.append(value)
        sources[f"SYS:m5-disposition/{disposition.disposition_id}"] = json.dumps(value, ensure_ascii=False, sort_keys=True)

    if readings:
        temps = [item["temperature_c"] for item in readings]
        reading_summary = {
            "count": len(readings), "first_event_at": readings[0]["event_at"],
            "last_event_at": readings[-1]["event_at"], "min_temperature_c": min(temps),
            "max_temperature_c": max(temps),
            "delayed_count": sum(1 for item in readings if item["received_at"] > item["event_at"]),
        }
    else:
        reading_summary = {"count": 0, "note": "Không có số đo khả dụng trước evidence cutoff."}
    insufficient_reasons = []
    if revision is None:
        insufficient_reasons.append("Không có revision incident khả dụng tại cutoff.")
    if not readings and not gaps and not warnings:
        insufficient_reasons.append("Không có số đo, khoảng trống hoặc cảnh báo chất lượng khả dụng.")

    evidence = {
        "shipment_id": shipment.shipment_id,
        "data_origin": shipment.data_origin.value, "product_category": product.category,
        "incident": incident_value, "policy": policy_value, "reading_summary": reading_summary,
        "readings": readings, "gaps": gaps, "warnings": warnings, "m3_detections": detections,
        "m4_predictions_advisory_only": ml_predictions, "m5_dispositions_available_by_cutoff": dispositions,
        "evidence_cutoff_at": cutoff.isoformat(), "sensor_interval_start_at": window_start.isoformat(),
        "sensor_interval_end_at": window_end.isoformat(),
        "missing_or_uncertain_evidence": insufficient_reasons,
    }
    refs = sorted(sources)
    return {
        "evidence": evidence, "sources": sources, "evidence_references": refs,
        "policy": policy, "procedure_version": policy.procedure_version,
        "product_category": product.category, "incident": incident_value,
        "interval_start_at": window_start, "interval_end_at": window_end,
        "sufficient": not insufficient_reasons, "insufficient_reasons": insufficient_reasons,
        "evidence_sha256": _digest(evidence),
        "temporal_facts": build_temporal_facts(evidence, cutoff),
    }

