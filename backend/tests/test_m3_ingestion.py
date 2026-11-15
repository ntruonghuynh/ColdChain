"""Milestone 3 ingestion: FR-01 to FR-04, BR-07, BR-08, BR-13, U-03, U-05, C-09 (contract §7.8, §7.9)."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ContextReading,
    DataQualityWarning,
    Incident,
    IngestBatch,
    Reading,
    RejectedRecord,
    SensorAssignment,
)
from app.db.models.enums import IngestMode
from app.services.ingest import BatchConflictError, ingest_batch
from tests.factories import make_sensor, make_shipment


def setup(db: Session, start: datetime, end: datetime | None = None) -> tuple[str, str]:
    shipment, sensor = make_shipment(db), make_sensor(db)
    db.add(
        SensorAssignment(
            sensor_id=sensor.sensor_id, shipment_id=shipment.shipment_id, assigned_from=start, assigned_to=end
        )
    )
    db.flush()
    return shipment.shipment_id, sensor.sensor_id


def iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def post(client: TestClient, body: dict[str, Any] | str) -> Any:
    raw = body if isinstance(body, str) else json.dumps(body)
    return client.post("/api/ingest/batches", content=raw, headers={"Content-Type": "application/json"})


def replay(
    db: Session,
    shipment_id: str,
    readings: list[dict[str, Any]],
    received_at: datetime,
    ref: str | None = None,
    contexts: list[dict[str, Any]] | None = None,
) -> Any:
    return ingest_batch(
        db,
        business_ref=ref or f"T-{uuid.uuid4().hex[:10]}",
        shipment_id=shipment_id,
        readings=readings,
        context_records=contexts or [],
        mode=IngestMode.REPLAY,
        received_at=received_at,
    )


def outcomes(result: Any) -> list[tuple[str, str, str | None]]:
    return [(r.record_kind, r.outcome, r.reason_code) for r in result.records]


# ------------------------------------------------------------------ live API


def test_fr03_c09_live_batch_uses_server_receipt_time_and_keeps_event_at(
    client: TestClient, db_session: Session
) -> None:
    now = datetime.now(UTC)
    sid, sensor = setup(db_session, now - timedelta(hours=2))
    event = now - timedelta(minutes=3, microseconds=123)
    before = datetime.now(UTC)
    resp = post(
        client,
        {
            "business_ref": "LIVE-1",
            "shipment_id": sid,
            "readings": [{"sensor_id": sensor, "event_at": iso(event), "temperature_c": 5.25}],
        },
    )
    after = datetime.now(UTC)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["ingest_mode"] == "LIVE" and data["accepted_count"] == 1 and data["idempotent_replay"] is False
    row = db_session.scalars(select(Reading).where(Reading.sensor_id == sensor)).one()
    assert row.event_at == event and before <= row.received_at <= after
    assert row.temperature_c == Decimal("5.25")


def test_b32_br13_same_reference_and_payload_returns_original_result(client: TestClient, db_session: Session) -> None:
    now = datetime.now(UTC)
    sid, sensor = setup(db_session, now - timedelta(hours=2))
    body = {
        "business_ref": "LIVE-IDEM",
        "shipment_id": sid,
        "readings": [{"sensor_id": sensor, "event_at": iso(now - timedelta(minutes=5)), "temperature_c": 4}],
    }
    first, second = post(client, body), post(client, body)
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["data"]["idempotent_replay"] is True
    assert second.json()["data"]["batch_id"] == first.json()["data"]["batch_id"]
    assert db_session.scalar(select(func.count()).select_from(Reading).where(Reading.sensor_id == sensor)) == 1


def test_br13_same_reference_different_payload_is_a_conflict(client: TestClient, db_session: Session) -> None:
    now = datetime.now(UTC)
    sid, sensor = setup(db_session, now - timedelta(hours=2))
    reading = {"sensor_id": sensor, "event_at": iso(now - timedelta(minutes=5)), "temperature_c": 4}
    assert post(client, {"business_ref": "LIVE-C", "shipment_id": sid, "readings": [reading]}).status_code == 201
    resp = post(client, {"business_ref": "LIVE-C", "shipment_id": sid, "readings": [{**reading, "temperature_c": 5}]})
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "batch_conflict"


def test_b60_c09_client_cannot_supply_received_at(client: TestClient, db_session: Session) -> None:
    now = datetime.now(UTC)
    sid, sensor = setup(db_session, now - timedelta(hours=2))
    resp = post(client, {"business_ref": "LIVE-R", "shipment_id": sid, "received_at": iso(now), "readings": []})
    assert resp.status_code == 422
    resp = post(
        client,
        {
            "business_ref": "LIVE-R2",
            "shipment_id": sid,
            "readings": [
                {
                    "sensor_id": sensor,
                    "event_at": iso(now - timedelta(minutes=1)),
                    "temperature_c": 4,
                    "received_at": iso(now - timedelta(days=1)),
                }
            ],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["records"][0]["reason_code"] == "UNEXPECTED_FIELD"


def test_b39_br08_precision_is_checked_on_the_exact_json_number(client: TestClient, db_session: Session) -> None:
    now = datetime.now(UTC)
    sid, sensor = setup(db_session, now - timedelta(hours=2))
    t = [iso(now - timedelta(minutes=m)) for m in (1, 2, 3)]
    raw = (
        '{"business_ref":"LIVE-P","shipment_id":"%s","readings":['
        '{"sensor_id":"%s","event_at":"%s","temperature_c":8.004},'
        '{"sensor_id":"%s","event_at":"%s","temperature_c":8.1000000000000001},'
        '{"sensor_id":"%s","event_at":"%s","temperature_c":8.100}]}'
    ) % (sid, sensor, t[0], sensor, t[1], sensor, t[2])
    data = post(client, raw).json()["data"]
    assert [r["reason_code"] for r in data["records"]] == ["PRECISION_EXCEEDED", "PRECISION_EXCEEDED", None]
    assert db_session.scalars(select(Reading.temperature_c).where(Reading.sensor_id == sensor)).all() == [
        Decimal("8.10")
    ]


def test_unknown_shipment_404_and_invalid_json_422(client: TestClient) -> None:
    assert post(client, {"business_ref": "X-1", "shipment_id": "NO-SUCH", "readings": []}).status_code == 404
    assert post(client, "{not json").status_code == 422


# ------------------------------------------------------------------ validation (service, controlled received_at)

T = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("-40.00", None),
        ("60.00", None),
        ("-40.01", "OUT_OF_PHYSICAL_RANGE"),
        ("60.01", "OUT_OF_PHYSICAL_RANGE"),
        ("NaN", "NOT_A_NUMBER"),
        ("abc", "NOT_A_NUMBER"),
        (True, "NOT_A_NUMBER"),
        ("8.004", "PRECISION_EXCEEDED"),
    ],
)
def test_b58_br08_measurement_validation(db_session: Session, value: Any, reason: str | None) -> None:
    sid, sensor = setup(db_session, T - timedelta(hours=1))
    v = Decimal(value) if isinstance(value, str) and value not in ("NaN", "abc") else value
    res = replay(
        db_session, sid, [{"sensor_id": sensor, "event_at": iso(T - timedelta(minutes=5)), "temperature_c": v}], T
    )
    assert res.records[0].reason_code == reason


@pytest.mark.parametrize(
    ("offset", "reason"),
    [
        (timedelta(minutes=5), None),
        (timedelta(minutes=5, milliseconds=1), "CLOCK_SKEW"),
        (timedelta(hours=-14), None),  # delayed data is never rejected for lateness
    ],
)
def test_b59_br08_future_skew_limit_and_delayed_data(
    db_session: Session, offset: timedelta, reason: str | None
) -> None:
    sid, sensor = setup(db_session, T - timedelta(days=1))
    res = replay(db_session, sid, [{"sensor_id": sensor, "event_at": iso(T + offset), "temperature_c": 5}], T)
    assert res.records[0].reason_code == reason


def test_timestamps_without_zone_and_missing_fields_are_rejected_with_reasons(db_session: Session) -> None:
    sid, sensor = setup(db_session, T - timedelta(hours=1))
    res = replay(
        db_session,
        sid,
        [
            {"sensor_id": sensor, "event_at": "2026-09-01T11:00:00", "temperature_c": 5},
            {"sensor_id": sensor, "temperature_c": 5},
            "not an object",
        ],
        T,
    )
    assert [r.reason_code for r in res.records] == ["NAIVE_TIMESTAMP", "MISSING_FIELD", "NOT_AN_OBJECT"]
    stored = db_session.scalars(
        select(RejectedRecord)
        .where(RejectedRecord.ingest_batch_id == res.batch_id)
        .order_by(RejectedRecord.record_index)
    ).all()
    assert [r.reason_code for r in stored] == ["NAIVE_TIMESTAMP", "MISSING_FIELD", "NOT_AN_OBJECT"]
    assert stored[0].raw_payload["event_at"] == "2026-09-01T11:00:00"  # audit evidence kept (FR-01)


def test_b75_u03_unassigned_unknown_and_out_of_window_readings_never_reach_detection(db_session: Session) -> None:
    sid, sensor = setup(db_session, T - timedelta(hours=1), T + timedelta(hours=1))
    other = make_sensor(db_session).sensor_id
    res = replay(
        db_session,
        sid,
        [
            {"sensor_id": "NO-SUCH-SENSOR", "event_at": iso(T), "temperature_c": 5},
            {"sensor_id": other, "event_at": iso(T), "temperature_c": 5},
            {"sensor_id": sensor, "event_at": iso(T - timedelta(hours=2)), "temperature_c": 9},
            {"sensor_id": sensor, "event_at": iso(T - timedelta(minutes=5)), "temperature_c": 5},
        ],
        T,
    )
    assert [r.reason_code for r in res.records] == [
        "UNKNOWN_SENSOR",
        "SENSOR_NOT_ASSIGNED",
        "OUTSIDE_MONITORING_WINDOW",
        None,
    ]
    assert db_session.scalar(select(func.count()).select_from(Reading).where(Reading.shipment_id == sid)) == 1


# ------------------------------------------------------------------ duplicates (BR-07) and context (U-05)


def test_b34_b54_br07_identical_duplicate_has_no_business_effect(db_session: Session) -> None:
    sid, sensor = setup(db_session, T - timedelta(hours=1))
    e = iso(T - timedelta(minutes=10))
    first = replay(db_session, sid, [{"sensor_id": sensor, "event_at": e, "temperature_c": Decimal("8.0")}], T)
    second = replay(
        db_session,
        sid,
        [{"sensor_id": sensor, "event_at": e, "temperature_c": Decimal("8.00")}],
        T + timedelta(minutes=30),
    )
    assert outcomes(second) == [("READING", "DUPLICATE_IGNORED", None)] and second.duplicate_count == 1
    assert second.evaluations == []  # nothing changed, nothing re-evaluated
    row = db_session.scalars(select(Reading).where(Reading.sensor_id == sensor)).one()
    assert row.received_at == first.received_at  # original receipt time unchanged
    assert (
        db_session.scalar(
            select(func.count()).select_from(RejectedRecord).where(RejectedRecord.ingest_batch_id == second.batch_id)
        )
        == 0
    )


def test_b55_u01_conflict_is_rejected_kept_for_review_and_opens_no_sensor_fault_incident(db_session: Session) -> None:
    sid, sensor = setup(db_session, T - timedelta(hours=1))
    e = iso(T - timedelta(minutes=10))
    replay(db_session, sid, [{"sensor_id": sensor, "event_at": e, "temperature_c": Decimal("8.4")}], T)
    res = replay(
        db_session,
        sid,
        [{"sensor_id": sensor, "event_at": e, "temperature_c": Decimal("9.1")}],
        T + timedelta(minutes=1),
    )
    assert outcomes(res) == [("READING", "REJECTED", "DUPLICATE_CONFLICT")]
    assert db_session.scalars(select(Reading.temperature_c).where(Reading.sensor_id == sensor)).one() == Decimal("8.40")
    warning = db_session.scalars(
        select(DataQualityWarning).where(
            DataQualityWarning.sensor_id == sensor, DataQualityWarning.kind == "READING_CONFLICT"
        )
    ).one()
    assert (warning.kind, warning.affects_quality_evidence) == ("READING_CONFLICT", True)
    assert warning.details["submitted_temperature_c"] == "9.1" and warning.ingest_batch_id == res.batch_id
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Incident)
            .where(Incident.shipment_id == sid, Incident.category == "SENSOR_FAULT_SUSPECTED")
        )
        == 0
    )


def test_b56_br07_duplicates_inside_one_batch(db_session: Session) -> None:
    sid, sensor = setup(db_session, T - timedelta(hours=1))
    e = iso(T - timedelta(minutes=10))
    res = replay(
        db_session,
        sid,
        [
            {"sensor_id": sensor, "event_at": e, "temperature_c": 5},
            {"sensor_id": sensor, "event_at": e, "temperature_c": 5},
            {"sensor_id": sensor, "event_at": e, "temperature_c": 6},
        ],
        T,
    )
    assert [r.outcome for r in res.records] == ["ACCEPTED", "DUPLICATE_IGNORED", "REJECTED"]
    batch = db_session.get(IngestBatch, res.batch_id)
    assert (batch.accepted_count, batch.duplicate_count, batch.rejected_count, batch.record_count) == (1, 1, 1, 3)


def test_b57_br07_same_key_from_another_shipment_is_a_conflict(db_session: Session) -> None:
    sid, sensor = setup(db_session, T - timedelta(hours=1))
    other = make_shipment(db_session).shipment_id
    db_session.add(SensorAssignment(sensor_id=sensor, shipment_id=other, assigned_from=T - timedelta(hours=1)))
    db_session.flush()
    e = iso(T - timedelta(minutes=10))
    replay(db_session, sid, [{"sensor_id": sensor, "event_at": e, "temperature_c": 5}], T)
    res = replay(db_session, other, [{"sensor_id": sensor, "event_at": e, "temperature_c": 5}], T)
    assert res.records[0].reason_code == "DUPLICATE_CONFLICT"


def test_u05_context_records_are_linked_deduplicated_and_conflict_checked(db_session: Session) -> None:
    sid, sensor = setup(db_session, T - timedelta(hours=1))
    e, e2 = iso(T - timedelta(minutes=10)), iso(T - timedelta(minutes=5))
    ctx = {
        "sensor_id": sensor,
        "event_at": e,
        "door_state": "CLOSED",
        "battery_level_pct": Decimal("63.3"),
        "ambient_temperature_c": None,
    }
    first = replay(
        db_session,
        sid,
        [{"sensor_id": sensor, "event_at": e, "temperature_c": 5}],
        T,
        contexts=[
            ctx,
            {"sensor_id": sensor, "event_at": e2, "door_state": "OPEN"},
            {"sensor_id": sensor, "event_at": e, "door_state": "AJAR"},
            {"sensor_id": sensor, "event_at": e, "battery_level_pct": Decimal("100.5")},
        ],
    )
    assert [(r.outcome, r.reason_code) for r in first.records if r.record_kind == "CONTEXT"] == [
        ("ACCEPTED", None),
        ("REJECTED", "CONTEXT_WITHOUT_READING"),
        ("REJECTED", "INVALID_VALUE"),
        ("REJECTED", "OUT_OF_RANGE"),
    ]
    again = replay(
        db_session,
        sid,
        [],
        T + timedelta(minutes=1),
        contexts=[{**ctx, "battery_level_pct": Decimal("63.30")}, {**ctx, "door_state": "OPEN"}],
    )
    assert [(r.outcome, r.reason_code) for r in again.records] == [
        ("DUPLICATE_IGNORED", None),
        ("REJECTED", "CONTEXT_CONFLICT"),
    ]
    stored = db_session.scalars(select(ContextReading).where(ContextReading.sensor_id == sensor)).one()
    assert stored.door_state == "CLOSED" and stored.ambient_temperature_c is None  # NULL = not reported
    warning = db_session.scalars(
        select(DataQualityWarning).where(
            DataQualityWarning.kind == "CONTEXT_CONFLICT", DataQualityWarning.sensor_id == sensor
        )
    ).one()
    assert warning.affects_quality_evidence is False  # ordinary warning (C-03)


def test_replay_mode_requires_a_recorded_receipt_time_and_live_refuses_one(db_session: Session) -> None:
    sid, _ = setup(db_session, T - timedelta(hours=1))
    with pytest.raises(ValueError):
        ingest_batch(
            db_session, business_ref="X", shipment_id=sid, readings=[], context_records=[], mode=IngestMode.REPLAY
        )
    with pytest.raises(ValueError):
        ingest_batch(
            db_session,
            business_ref="X",
            shipment_id=sid,
            readings=[],
            context_records=[],
            mode=IngestMode.LIVE,
            received_at=T,
        )


def test_br13_service_level_conflict(db_session: Session) -> None:
    sid, sensor = setup(db_session, T - timedelta(hours=1))
    replay(db_session, sid, [{"sensor_id": sensor, "event_at": iso(T), "temperature_c": 5}], T, ref="SVC-1")
    with pytest.raises(BatchConflictError):
        replay(db_session, sid, [{"sensor_id": sensor, "event_at": iso(T), "temperature_c": 6}], T, ref="SVC-1")
