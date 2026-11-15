"""Milestone 3 read API: telemetry, status, deliveries, gaps, detections, warnings, queue, incident detail."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import SensorAssignment
from app.db.models.enums import IngestMode
from app.services.ingest import ingest_batch
from tests.factories import make_sensor, make_shipment

T = datetime(2026, 9, 2, 0, 0, tzinfo=UTC)


def m(x: float) -> datetime:
    return T + timedelta(minutes=x)


def z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def scenario(db: Session) -> tuple[str, str]:
    """Normal start, silence, buffered backfill with an excursion and a real 40-min logger hole."""
    shipment, sensor = make_shipment(db), make_sensor(db)
    db.add(
        SensorAssignment(
            sensor_id=sensor.sensor_id, shipment_id=shipment.shipment_id, assigned_from=T, assigned_to=m(300)
        )
    )
    db.flush()

    def send(minutes: list[float], value: float, received: float) -> None:
        ingest_batch(
            db,
            business_ref=f"API-{uuid.uuid4().hex[:8]}",
            shipment_id=shipment.shipment_id,
            readings=[
                {"sensor_id": sensor.sensor_id, "event_at": z(m(x)), "temperature_c": Decimal(str(value))}
                for x in minutes
            ],
            context_records=[],
            mode=IngestMode.REPLAY,
            received_at=m(received),
        )

    send([0, 5], 5.0, 6)
    send([10 + 5 * i for i in range(12)], 5.0, 200)  # 10..65, delivered into UNKNOWN
    send([70 + 5 * i for i in range(8)], 10.0, 200.5)  # 70..105: 35-min excursion, delivered late
    send([145 + 5 * i for i in range(10)], 5.0, 250)  # real 40-min logger hole 105 -> 145
    return shipment.shipment_id, sensor.sensor_id


def get(client: TestClient, path: str) -> Any:
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_telemetry_monitoring_and_causal_as_of(client: TestClient, db_session: Session) -> None:
    sid, sensor = scenario(db_session)
    view = get(client, f"/api/shipments/{sid}/telemetry?as_of={z(m(120))}")
    s = view["sensors"][0]
    assert view["data_origin"] == "SIMULATED" and view["policy"]["policy_version"] == "1.0"
    assert view["detector_config"]["max_continuous_interval_s"] == 450
    assert s["status"]["state"] == "UNKNOWN" and len(s["readings"]) == 2 and s["runs"] == []
    later = get(client, f"/api/shipments/{sid}/telemetry?as_of={z(m(260))}")["sensors"][0]
    assert any(r["meets_policy_duration"] for r in later["runs"])
    gap = next(g for g in later["gaps"] if g["gap_status"] == "UNKNOWN_REVIEW_REQUIRED")
    assert gap["bracketing_span_min"] == 40 and gap["estimated_missing_samples"] == 7
    assert gap["estimated_missing_duration_s"] == 7 * 300  # different measurement from the span
    status = get(client, f"/api/shipments/{sid}/monitoring?as_of={z(m(13))}")[0]
    assert status["state"] == "STALE" and status["monitoring_window"]["assigned_to"] is not None
    assert get(client, f"/api/sensors/{sensor}/status?as_of={z(m(7))}")[0]["state"] == "CURRENT"


def test_deliveries_report_delayed_backfill_and_gaps(client: TestClient, db_session: Session) -> None:
    sid, _ = scenario(db_session)
    data = get(client, f"/api/shipments/{sid}/deliveries")
    batches = data["batches"]
    assert [b["monitoring_state_before_receipt"] for b in batches][:2] == ["CURRENT", "UNKNOWN"]
    assert batches[1]["late_backfill"] is True and Decimal(batches[1]["max_delivery_lag_s"]) == 190 * 60
    assert Decimal(batches[1]["unobserved_before_receipt_s"]) == 195 * 60      # newest event 5 -> receipt 200
    assert batches[0]["late_backfill"] is False


def test_gaps_detections_warnings_and_queue(client: TestClient, db_session: Session) -> None:
    sid, _ = scenario(db_session)
    gaps = get(client, f"/api/shipments/{sid}/data-gaps")
    assert [g["gap_status"] for g in gaps] == ["UNKNOWN_REVIEW_REQUIRED"]
    history = get(client, f"/api/shipments/{sid}/data-gaps?include_superseded=true")
    assert len(history) >= len(gaps)
    runs = get(client, f"/api/shipments/{sid}/detections?meets_policy_duration=true")
    assert [r["direction"] for r in runs] == ["HIGH"] and runs[0]["observed_duration_min"] == 35
    warnings = get(client, f"/api/shipments/{sid}/warnings?evidence_only=true")
    assert all(w["affects_quality_evidence"] for w in warnings)
    queue = client.get(f"/api/incidents?status=OPEN&shipment_id={sid}").json()
    cats = sorted(i["category"] for i in queue["data"])
    assert cats == ["DATA_GAP", "TEMPERATURE_EXCURSION"] and queue["meta"]["total"] == 2
    assert all(i["review_state"] == "PENDING_QUALITY_REVIEW" for i in queue["data"])
    only = client.get(f"/api/incidents?status=OPEN&category=DATA_GAP&shipment_id={sid}").json()["data"]
    assert [i["category"] for i in only] == ["DATA_GAP"]


def test_incident_detail_has_evidence_versions_and_revisions(client: TestClient, db_session: Session) -> None:
    sid, _ = scenario(db_session)
    queue = client.get(f"/api/incidents?status=OPEN&category=TEMPERATURE_EXCURSION&shipment_id={sid}").json()["data"]
    detail = get(client, f"/api/incidents/{queue[0]['incident_id']}")
    assert (
        detail["policy"]["policy_code"] == "POL-CHILL-01"
        and detail["detector_config"]["detector_code"] == "DET-BASELINE"
    )
    assert detail["opening_evaluation"]["mode"] == "REPLAY" and detail["revisions"][0]["revision"] == 1
    assert any(r["inside_extent"] for r in detail["evidence"]["readings"])
    assert detail["dispositions"] == [] and detail["review_state"] == "PENDING_QUALITY_REVIEW"
    assert detail["latest"]["evidence_received_at"] is not None


def test_summary_configs_and_errors(client: TestClient, db_session: Session) -> None:
    scenario(db_session)
    summary = get(client, f"/api/monitoring/summary?as_of={z(m(260))}")
    assert summary["open_incidents_by_category"]["TEMPERATURE_EXCURSION"] >= 1
    assert set(summary["sensors_by_monitoring_state"]) == {"NOT_STARTED", "CURRENT", "STALE", "UNKNOWN", "ENDED"}
    configs = get(client, "/api/detector-configs")
    assert [(c["detector_code"], c["config_version"]) for c in configs] == [("DET-BASELINE", "1.0.0")]
    assert client.get("/api/shipments/NO-SUCH/telemetry").status_code == 404
    assert client.get(f"/api/incidents/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/monitoring/summary?as_of=2026-09-01T00:00:00").status_code == 422
