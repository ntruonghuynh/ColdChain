"""Observed-data inference plus append-only advisory output recording."""

from datetime import UTC, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.prediction_schemas import ModelReadiness, PredictionRequest, PredictionResponse
from app.api.schemas import Envelope
from app.core.errors import AppError, NotFoundError
from app.db.models import ContextReading, Policy, Reading, SensorAssignment, Shipment
from app.db.session import get_db
from app.integrations import ml_adapter
from app.services.ml_predictions import append_prediction
from coldchain_ml.windows import Reading as MLReading

router = APIRouter(prefix="/predictions", tags=["ML advisory predictions"])


@router.get("/model", response_model=Envelope[ModelReadiness], summary="Frozen ML model readiness and version")
def model_readiness() -> Envelope[ModelReadiness]:
    try:
        _, manifest = ml_adapter.load_model()
        return Envelope(data=ModelReadiness(status="ready", model_version=manifest["model_version"]))
    except Exception as exc:
        return Envelope(data=ModelReadiness(status="unavailable", model_version=ml_adapter.MODEL_VERSION,
                                            detail=exc.__class__.__name__))


@router.post("", response_model=Envelope[PredictionResponse], summary="Score the latest causal telemetry window")
def create_prediction(request: PredictionRequest, db: Session = Depends(get_db)) -> Envelope[PredictionResponse]:
    if request.as_of.tzinfo is None:
        raise AppError("as_of must include a time zone.", code="validation_error", status_code=422)
    as_of = request.as_of.astimezone(UTC)
    shipment = db.get(Shipment, request.shipment_id)
    if shipment is None:
        raise NotFoundError(f"Shipment {request.shipment_id} not found.")
    assignments = list(db.scalars(select(SensorAssignment).where(
        SensorAssignment.shipment_id == request.shipment_id,
        SensorAssignment.assigned_from <= as_of,
        (SensorAssignment.assigned_to.is_(None) | (SensorAssignment.assigned_to >= as_of)),
    )).all())
    selected = request.sensor_id or (assignments[0].sensor_id if len(assignments) == 1 else None)
    if selected is None or selected not in {item.sensor_id for item in assignments}:
        raise AppError("sensor_id must identify one sensor assigned to the shipment at as_of.",
                       code="validation_error", status_code=422)
    cutoff = as_of.replace()  # preserve the caller's exact UTC processing timestamp
    start = cutoff - timedelta(minutes=60)
    rows = db.scalars(select(Reading).where(
        Reading.shipment_id == request.shipment_id,
        Reading.sensor_id == selected,
        Reading.event_at >= start,
        Reading.event_at <= cutoff,
        Reading.received_at <= cutoff,
    ).order_by(Reading.event_at)).all()
    contexts = db.scalars(select(ContextReading).where(
        ContextReading.shipment_id == request.shipment_id,
        ContextReading.sensor_id == selected,
        ContextReading.event_at >= start,
        ContextReading.event_at <= cutoff,
        ContextReading.received_at <= cutoff,
    )).all()
    context_by_event = {c.event_at: c for c in contexts}
    ml_rows = []
    for row in rows:
        context = context_by_event.get(row.event_at)
        ml_rows.append(MLReading(
            event_at=row.event_at, received_at=row.received_at, temperature_c=float(row.temperature_c),
            ambient_temperature_c=float(context.ambient_temperature_c) if context and context.ambient_temperature_c is not None else None,
            door_open=(context.door_state.value == "OPEN") if context and context.door_state is not None else None,
            battery_level_pct=float(context.battery_level_pct) if context and context.battery_level_pct is not None else None,
            context_received_at=context.received_at if context else None,
        ))
    policy = db.get(Policy, shipment.policy_id)
    if policy is None:
        raise AppError("Shipment policy could not be resolved.", code="model_input_unavailable", status_code=409)
    try:
        prediction = ml_adapter.predict(ml_rows, as_of, min_temp_c=float(policy.min_temp_c),
                                       max_temp_c=float(policy.max_temp_c), policy_sha256=policy.content_sha256)
    except Exception as exc:
        raise AppError("Frozen ML model is unavailable or incompatible.", code="model_unavailable", status_code=503) from exc
    stored = append_prediction(db, shipment_id=request.shipment_id, sensor_id=selected, output=prediction)
    prediction["prediction_id"] = stored.prediction_id
    return Envelope(data=PredictionResponse.model_validate(prediction))
