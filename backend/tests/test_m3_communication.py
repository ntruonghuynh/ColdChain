"""M3 acceptance review: communication status is presentation only and never implies safety.

The approved monitoring states (CURRENT / STALE / UNKNOWN, C-02) are unchanged; the communication
view adds observed upload facts so that "waiting for the next scheduled upload" can be told apart
from "longer silence than any recent upload interval".
"""

import ast
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import SensorAssignment
from app.db.models.enums import IngestMode
from app.domain.detector import MonitoringStateName, monitoring_state
from app.services.communication import CommunicationStatus, communication_view
from app.services.ingest import ingest_batch
from tests.factories import make_sensor, make_shipment
from tests.m3_helpers import CONFIG, POLICY

T = datetime(2026, 9, 3, 0, 0, tzinfo=UTC)
APP_DIR = Path(__file__).resolve().parents[1] / "app"


def m(x: float) -> datetime:
    return T + timedelta(minutes=x)


UPLOADS = [m(1 + 15 * i) for i in range(6)]  # 00:01, 00:16, ..., 01:16 (every 15 min)


def state_at(newest: datetime, as_of: datetime) -> MonitoringStateName:
    return monitoring_state(
        newest_event_at=newest, assigned_from=T, assigned_to=None, as_of=as_of, policy=POLICY, config=CONFIG
    ).state


def test_waiting_for_a_scheduled_upload_keeps_the_temperature_unknown() -> None:
    """Just before an on-schedule upload the temperature is UNKNOWN, but communication is normal."""
    as_of = m(90.5)  # 14.5 min after the last upload; newest reading at 75 min (15.5 min old)
    state = state_at(m(75), as_of)
    view = communication_view(UPLOADS, as_of, state)
    assert state == MonitoringStateName.UNKNOWN  # approved semantics unchanged
    assert view.status == CommunicationStatus.WITHIN_RECENT_UPLOAD_INTERVALS
    assert view.observed_upload_interval == view.longest_recent_upload_interval == timedelta(minutes=15)
    assert view.since_last_upload == timedelta(minutes=14.5) and view.expected_schedule_configured is False


def test_silence_longer_than_every_recent_interval_is_reported_as_possible_outage() -> None:
    as_of = m(76 + 45)
    view = communication_view(UPLOADS, as_of, state_at(m(75), as_of))
    assert view.status == CommunicationStatus.LONGER_THAN_RECENT_UPLOAD_INTERVALS
    exactly = communication_view(UPLOADS, m(91), state_at(m(75), m(91)))  # silence == longest interval
    assert exactly.status == CommunicationStatus.WITHIN_RECENT_UPLOAD_INTERVALS


def test_communication_view_is_causal_and_honest_without_history() -> None:
    later = [*UPLOADS, m(200)]
    assert communication_view(later, m(90), MonitoringStateName.UNKNOWN) == communication_view(
        UPLOADS, m(90), MonitoringStateName.UNKNOWN
    )
    assert communication_view([], m(5), MonitoringStateName.STALE).status == CommunicationStatus.NO_UPLOAD_YET
    few = communication_view(UPLOADS[:3], m(40), MonitoringStateName.UNKNOWN)
    assert few.status == CommunicationStatus.PATTERN_NOT_ESTABLISHED and few.recent_intervals_used == 2
    assert communication_view(UPLOADS, m(500), MonitoringStateName.ENDED).status == CommunicationStatus.ENDED
    assert communication_view([], m(-5), MonitoringStateName.NOT_STARTED).status == CommunicationStatus.NOT_STARTED


def test_communication_view_never_feeds_detection() -> None:
    """Static guard: the detector, reconciliation, replay and persistence never import it."""
    for rel in (
        "domain/detector.py",
        "domain/reconcile.py",
        "domain/replay.py",
        "services/detection.py",
        "services/ingest.py",
    ):
        tree = ast.parse((APP_DIR / rel).read_text(encoding="utf-8"))
        modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert "app.services.communication" not in modules, rel


def _scenario(db: Session) -> tuple[str, str]:
    shipment, sensor = make_shipment(db), make_sensor(db)
    db.add(SensorAssignment(sensor_id=sensor.sensor_id, shipment_id=shipment.shipment_id, assigned_from=T))
    db.flush()
    for i in range(6):  # readings every 5 min, uploaded every 15 min (like the dataset gateways)
        minutes = [15 * i - 10, 15 * i - 5, 15 * i] if i else [0]
        ingest_batch(
            db,
            business_ref=f"COMM-{uuid.uuid4().hex[:8]}",
            shipment_id=shipment.shipment_id,
            readings=[
                {"sensor_id": sensor.sensor_id, "event_at": m(x).isoformat(), "temperature_c": Decimal("5.0")}
                for x in minutes
            ],
            context_records=[],
            mode=IngestMode.REPLAY,
            received_at=m(15 * i + 1),
        )
    return shipment.shipment_id, sensor.sensor_id


def status(client: TestClient, sid: str, at: datetime) -> dict[str, Any]:
    resp = client.get(f"/api/shipments/{sid}/monitoring?as_of={at.isoformat().replace('+00:00', 'Z')}")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"][0]


def test_api_separates_freshness_communication_gaps_and_incidents(client: TestClient, db_session: Session) -> None:
    sid, _ = _scenario(db_session)
    before_upload = status(client, sid, m(90.5))  # last upload 76, newest reading 75 (in range)
    assert before_upload["state"] == "UNKNOWN"  # the product is not "currently safe"
    assert before_upload["last_observed_temperature_state"] == "IN_RANGE"  # a past fact, labelled as such
    assert before_upload["last_observed_event_at"].startswith("2026-09-03T01:15")
    comm = before_upload["communication"]
    assert comm["status"] == "WITHIN_RECENT_UPLOAD_INTERVALS" and comm["expected_schedule_configured"] is False
    assert Decimal(comm["observed_upload_interval_s"]) == 900 and Decimal(comm["since_last_upload_s"]) == 870
    assert before_upload["confirmed_gaps"] == {"SHORT_GAP": 0, "UNKNOWN": 0, "UNKNOWN_REVIEW_REQUIRED": 0}
    assert before_upload["open_incidents_as_of"] == {"TEMPERATURE_EXCURSION": 0, "DATA_GAP": 0}
    outage = status(client, sid, m(150))
    assert outage["state"] == "UNKNOWN" and outage["communication"]["status"] == "LONGER_THAN_RECENT_UPLOAD_INTERVALS"
    assert outage["open_incidents_as_of"]["DATA_GAP"] == 0  # silence alone never opens an incident (C-02)
