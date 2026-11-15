from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
import pytest

from app.db.models import Disposition, Incident, MLPrediction, Reading, SensorAssignment, WarehouseRelease
from tests.factories import T0, make_sensor, make_shipment


def test_prediction_contract_rejects_unknown_fields_and_requires_timestamp(client) -> None:
    response = client.post("/api/predictions", json={"shipment_id": "X", "ground_truth": True})
    assert response.status_code == 422
    assert "/api/predictions" in client.get("/api/openapi.json").json()["paths"]
    spec = client.get("/api/openapi.json").text
    assert "ground_truth" not in spec
    assert "EXCURSION_HIGH" not in spec


def test_prediction_appends_advisory_record_without_operational_writes(client, db_session: Session, monkeypatch) -> None:
    from app.integrations import ml_adapter

    shipment = make_shipment(db_session)
    sensor = make_sensor(db_session)
    db_session.add(SensorAssignment(sensor_id=sensor.sensor_id, shipment_id=shipment.shipment_id,
                                    assigned_from=T0, assigned_to=None))
    db_session.flush()
    before = db_session.scalar(select(func.count()).select_from(Reading))
    prediction_count = db_session.scalar(select(func.count()).select_from(MLPrediction))
    operational_counts = [db_session.scalar(select(func.count()).select_from(model))
                          for model in (Incident, Disposition, WarehouseRelease)]
    shipment_status = shipment.status
    monkeypatch.setattr(ml_adapter, "predict", lambda readings, as_of, **kwargs: {
        "status": "INSUFFICIENT_EVIDENCE", "as_of": as_of, "model_version": ml_adapter.MODEL_VERSION,
        "feature_schema_version": "coldchain-window-v1", "advisory_only": True,
        "temperature_safety_established": False, "risk_probability": None, "alert": False,
        "message": "Insufficient recent observations; temperature risk is unknown."})
    response = client.post("/api/predictions", json={"shipment_id": shipment.shipment_id,
        "sensor_id": sensor.sensor_id, "as_of": datetime(2026, 1, 1, 1, tzinfo=UTC).isoformat()})
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "INSUFFICIENT_EVIDENCE"
    assert body["risk_probability"] is None and body["alert"] is False
    assert body["temperature_safety_established"] is False
    assert db_session.scalar(select(func.count()).select_from(Reading)) == before
    prediction = db_session.scalar(select(MLPrediction).where(MLPrediction.prediction_id == body["prediction_id"]))
    assert prediction is not None and prediction.model_version == ml_adapter.MODEL_VERSION
    assert prediction.advisory_only is True and prediction.status == "INSUFFICIENT_EVIDENCE"
    assert db_session.scalar(select(func.count()).select_from(MLPrediction)) == prediction_count + 1
    assert [db_session.scalar(select(func.count()).select_from(model))
            for model in (Incident, Disposition, WarehouseRelease)] == operational_counts
    assert shipment.status == shipment_status
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.execute(update(MLPrediction).where(MLPrediction.prediction_id == prediction.prediction_id)
                           .values(alert=True))
    db_session.rollback()
