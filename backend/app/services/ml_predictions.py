"""Append-only persistence for advisory prediction outputs; no workflow state writes."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import MLPrediction


def append_prediction(db: Session, *, shipment_id: str, sensor_id: str, output: dict) -> MLPrediction:
    row = MLPrediction(
        shipment_id=shipment_id,
        sensor_id=sensor_id,
        as_of=output["as_of"],
        model_version=output["model_version"],
        feature_schema_version=output["feature_schema_version"],
        status=output["status"],
        risk_probability=Decimal(str(output["risk_probability"])) if output["risk_probability"] is not None else None,
        threshold=Decimal(str(output["threshold"])) if output.get("threshold") is not None else None,
        alert=output["alert"],
        advisory_only=True,
        evidence=output.get("evidence") or {},
    )
    db.add(row)
    db.flush()
    db.commit()
    db.refresh(row)
    return row
