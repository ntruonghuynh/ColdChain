"""Milestone 3 detection persisted in PostgreSQL: replay causality, incident history, U-04, versions.

Contract §7.6, §7.7, §7.10, §7.11, §7.13, §7.14.
"""

import ast
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    DataGap,
    DecisionReassessment,
    Detection,
    DetectorEvaluation,
    Disposition,
    DispositionIncident,
    Incident,
    IncidentRevision,
    IngestBatch,
    Policy,
    Reading,
    SensorAssignment,
    Shipment,
    WarehouseRelease,
)
from app.db.models.enums import DataOrigin, Decision, IngestMode, IngestSource, PolicyStatus
from app.services.detection import load_state, replay_shipment
from app.services.ingest import ingest_batch
from app.services.queries import sensor_status, shipment_context
from tests.factories import active_policy, make_sensor, make_shipment, user

T = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
APP_DIR = Path(__file__).resolve().parents[1] / "app"


def m(minutes: float) -> datetime:
    return T + timedelta(minutes=minutes)


def setup(db: Session, start: datetime = T, end: datetime | None = None) -> tuple[str, str]:
    shipment, sensor = make_shipment(db), make_sensor(db)
    db.add(
        SensorAssignment(
            sensor_id=sensor.sensor_id, shipment_id=shipment.shipment_id, assigned_from=start, assigned_to=end
        )
    )
    db.flush()
    return shipment.shipment_id, sensor.sensor_id


def recs(sensor: str, minutes: list[float], value: float | str) -> list[dict[str, Any]]:
    return [{"sensor_id": sensor, "event_at": m(x).isoformat(), "temperature_c": Decimal(str(value))} for x in minutes]


def send(db: Session, sid: str, readings: list[dict[str, Any]], received_min: float, ref: str | None = None) -> Any:
    return ingest_batch(
        db,
        business_ref=ref or f"T-{uuid.uuid4().hex[:10]}",
        shipment_id=sid,
        readings=readings,
        context_records=[],
        mode=IngestMode.REPLAY,
        received_at=m(received_min),
    )


def incidents(db: Session, sid: str, category: str | None = None) -> list[Incident]:
    stmt = select(Incident).where(Incident.shipment_id == sid)
    if category:
        stmt = stmt.where(Incident.category == category)
    return list(db.scalars(stmt.order_by(Incident.opened_at, Incident.business_ref)).all())


def latest_revision(db: Session, incident_id: uuid.UUID) -> IncidentRevision:
    return db.scalars(
        select(IncidentRevision)
        .where(IncidentRevision.incident_id == incident_id)
        .order_by(IncidentRevision.revision.desc())
        .limit(1)
    ).one()


def status(db: Session, sid: str, sensor: str, as_of: datetime) -> dict[str, Any]:
    _, policy, config = shipment_context(db, sid)
    return sensor_status(db, sid, sensor, as_of, policy, config)


# ------------------------------------------------------------------ ocean outage (B28, DEMO-01)


def test_b28_ocean_outage_visible_as_stale_unknown_then_backfill_detects_excursion(db_session: Session) -> None:
    sid, sensor = setup(db_session, T, m(600))
    send(db_session, sid, recs(sensor, [0, 5, 10, 15], 5.0), 16)
    assert status(db_session, sid, sensor, m(20))["state"] == "CURRENT"
    assert status(db_session, sid, sensor, m(25))["state"] == "STALE"
    mid = status(db_session, sid, sensor, m(200))
    assert mid["state"] == "UNKNOWN" and mid["provisional_review_threshold_reached"]
    assert incidents(db_session, sid) == []  # visible, but no incident (C-02)
    buffered = (
        recs(sensor, [20 + 5 * i for i in range(30)], 5.0)
        + recs(sensor, [170 + 5 * i for i in range(13)], 10.5)
        + recs(sensor, [235 + 5 * i for i in range(30)], 5.0)
    )
    result = send(db_session, sid, buffered, 400)
    [tex] = incidents(db_session, sid)
    assert (tex.category, tex.status, tex.opened_at, tex.interval_start) == (
        "TEMPERATURE_EXCURSION",
        "OPEN",
        m(400),
        m(170),
    )
    assert tex.sensor_id == sensor and result.evaluations[0].incidents_opened == [tex.business_ref]
    stored = db_session.scalars(
        select(
            Reading.event_at,
        ).where(Reading.sensor_id == sensor, Reading.event_at == m(170))
    ).one()
    assert stored == m(170)  # original event time preserved
    assert db_session.scalar(select(func.count()).select_from(DataGap).where(DataGap.shipment_id == sid)) == 0
    assert status(db_session, sid, sensor, m(200))["state"] == "UNKNOWN"  # history is causal: still unknown then


# ------------------------------------------------------------------ persisted replay = live path (B66, B68)


def _import_like(db: Session, sid: str, sensor: str, uploads: list[tuple[float, list[float], float]]) -> None:
    """Store batches directly, as the M2 importer does (no detection)."""
    shipment = db.get(Shipment, sid)
    for i, (received, minutes, value) in enumerate(uploads):
        bid = uuid.uuid4()
        db.add(
            IngestBatch(
                batch_id=bid,
                business_ref=f"{sid}-U{i:04d}",
                shipment_id=sid,
                submitted_by_org_id=shipment.carrier_org_id,
                source=IngestSource.SIMULATOR,
                data_origin=DataOrigin.SIMULATED,
                received_at=m(received),
                record_count=len(minutes),
                accepted_count=len(minutes),
            )
        )
        db.flush()
        for x in minutes:
            db.add(
                Reading(
                    sensor_id=sensor,
                    shipment_id=sid,
                    ingest_batch_id=bid,
                    event_at=m(x),
                    received_at=m(received),
                    temperature_c=Decimal(str(value)),
                )
            )
    db.flush()


UPLOADS = [
    (16, [0, 5, 10, 15], 5.0),
    (31, [20, 25, 30], 9.0),
    (200, [35, 40, 45, 50, 55, 60], 9.0),
    (210, [65, 70], 5.0),
    (230, [120, 125, 130], 1.0),
    (245, [135, 140], 5.0),
]


def _current(db: Session, sid: str, sensor: str) -> tuple:
    st = load_state(db, sid, sensor)
    return (
        sorted((k, g.gap) for k, g in st.gaps.items()),
        sorted((r.run.first_event_at, r.run) for r in st.runs.values()),
        sorted(w.spec.key for w in st.warnings.values()),
        sorted(
            (i.category, i.values.extent_start_at, i.values.extent_end_at, i.values.basis, i.opened_at)
            for i in st.incidents.values()
        ),
    )


def test_b66_b68_c09_persisted_replay_equals_ingestion_replay(db_session: Session) -> None:
    sid_a, sensor_a = setup(db_session, T, m(150))
    _import_like(db_session, sid_a, sensor_a, UPLOADS)
    [summary] = replay_shipment(db_session, sid_a)
    assert summary.status == "replayed" and summary.evaluations > 0
    assert replay_shipment(db_session, sid_a)[0].status == "already_evaluated"  # runs once
    sid_b, sensor_b = setup(db_session, T, m(150))
    from app.domain.replay import StepKind, build_timeline
    from app.services.detection import evaluate_sensor
    from app.db.models.enums import EvaluationMode, EvaluationTrigger

    steps = build_timeline(T, m(150), [(m(r), f"U{i}") for i, (r, _, _) in enumerate(UPLOADS)])
    for step in steps:
        if step.kind == StepKind.BATCH:
            received, minutes, value = UPLOADS[int((step.batch_ref or "U0")[1:])]
            send(db_session, sid_b, recs(sensor_b, minutes, value), received)
        else:
            evaluate_sensor(
                db_session,
                sid_b,
                sensor_b,
                as_of=step.at,
                mode=EvaluationMode.REPLAY,
                trigger=EvaluationTrigger(step.kind.value),
            )
    a, b = _current(db_session, sid_a, sensor_a), _current(db_session, sid_b, sensor_b)
    assert a[0] == b[0] and a[1] == b[1]
    assert [x[0:4] for x in a[3]] == [x[0:4] for x in b[3]]
    assert [x[4] for x in a[3]] == [x[4] for x in b[3]]  # same raised (opened) times


def test_b65_c09_status_and_results_as_of_ignore_later_receipts(db_session: Session) -> None:
    sid, sensor = setup(db_session, T, m(150))
    _import_like(db_session, sid, sensor, UPLOADS)
    replay_shipment(db_session, sid)
    early = status(db_session, sid, sensor, m(100))
    assert early["newest_event_at"] == m(30) and early["state"] == "UNKNOWN"  # batch received at 200 not yet known
    from app.services.queries import telemetry

    view = telemetry(db_session, sid, m(100))["sensors"][0]
    assert max(p["event_at"] for p in view["readings"]) == m(30)
    assert all(r["raised_at"] <= m(100) for r in view["runs"])


# ------------------------------------------------------------------ incident history and U-04 (B62, B63)


def _close_with_disposition(db: Session, inc: Incident, decision: Decision, release: bool) -> Disposition:
    """Test stand-in for the M5 quality workflow (not part of the application)."""
    quality = user(db, "quality.demo")
    disp = Disposition(
        business_ref=f"DISP-{uuid.uuid4().hex[:8]}",
        shipment_id=inc.shipment_id,
        decision=decision,
        decided_by_user_id=quality.user_id,
        decided_at=m(500),
        rationale="test disposition",
        policy_id=inc.policy_id,
    )
    db.add(disp)
    db.flush()
    db.add(
        DispositionIncident(
            disposition_id=disp.disposition_id, incident_id=inc.incident_id, shipment_id=inc.shipment_id
        )
    )
    inc.status, inc.closed_at = "CLOSED", m(500)
    if release:
        db.add(
            WarehouseRelease(
                business_ref=f"REL-{uuid.uuid4().hex[:8]}",
                shipment_id=inc.shipment_id,
                disposition_id=disp.disposition_id,
                released_by_user_id=user(db, "warehouse.demo").user_id,
                released_at=m(510),
            )
        )
    db.flush()
    return disp


def test_b62_u04_late_evidence_never_changes_a_disposition_or_release(db_session: Session) -> None:
    sid, sensor = setup(db_session)
    send(db_session, sid, recs(sensor, [0, 5, 10, 15, 20, 25, 30], 9.0), 31)
    [inc] = incidents(db_session, sid)
    disp = _close_with_disposition(db_session, inc, Decision.RELEASE, release=True)
    release = db_session.scalars(select(WarehouseRelease).where(WarehouseRelease.shipment_id == sid)).one()
    send(db_session, sid, recs(sensor, [35, 40, 45], 9.5), 600)  # late data extends the excursion
    db_session.refresh(inc)
    assert inc.status == "CLOSED" and inc.closed_at == m(500)  # detector never reopens or edits
    rev = latest_revision(db_session, inc.incident_id)
    assert rev.revision == 2 and rev.extent_end_at == m(45) and rev.incident_status_at_revision == "CLOSED"
    flag = db_session.scalars(
        select(DecisionReassessment).where(DecisionReassessment.incident_id == inc.incident_id)
    ).one()
    assert (flag.disposition_id, flag.reason, flag.warehouse_release_id) == (
        disp.disposition_id,
        "INCIDENT_EVIDENCE_REVISED",
        release.release_id,
    )
    db_session.refresh(disp)
    assert disp.decision == "RELEASE" and db_session.get(WarehouseRelease, release.release_id) is not None


def test_u04_new_incident_after_a_disposition_flags_the_decision(db_session: Session) -> None:
    sid, sensor = setup(db_session)
    send(db_session, sid, recs(sensor, [0, 5, 10, 15, 20, 25, 30], 9.0), 31)
    [inc] = incidents(db_session, sid)
    disp = _close_with_disposition(db_session, inc, Decision.QUARANTINE, release=False)
    send(db_session, sid, recs(sensor, [35, 40] + [80, 85, 90, 95], 5.0) + recs(sensor, [45, 50, 55, 60], 1.0), 700)
    new = [i for i in incidents(db_session, sid) if i.incident_id != inc.incident_id]
    assert [i.category for i in new] == ["TEMPERATURE_EXCURSION"]
    flags = db_session.scalars(
        select(DecisionReassessment).where(DecisionReassessment.disposition_id == disp.disposition_id)
    ).all()
    assert "NEW_INCIDENT_AFTER_DISPOSITION" in [f.reason for f in flags]
    db_session.refresh(disp)
    assert disp.decision == "QUARANTINE"


def test_b63_br09_only_a_quality_workflow_may_close_an_incident() -> None:
    """Static guard: no application module writes status CLOSED or closed_at on incidents (M5 adds the
    disposition service, which must be added here explicitly with a reason)."""
    allowed: set[str] = set()
    problems = []
    for path in sorted(APP_DIR.rglob("*.py")):
        rel = path.relative_to(APP_DIR.parent).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.keyword)
                and node.arg in ("status", "closed_at")
                and isinstance(node.value, ast.Constant)
                and node.value.value == "CLOSED"
            ):
                problems.append(f"{rel}: {node.arg}='CLOSED'")
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "CLOSED"
                and isinstance(node.value, ast.Name)
                and node.value.id == "IncidentStatus"
            ):
                problems.append(f"{rel}: IncidentStatus.CLOSED")
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "update"
                and node.args
                and getattr(node.args[0], "id", None) == "Incident"
            ):
                problems.append(f"{rel}: update(Incident)")
    assert [p for p in problems if p.split(":")[0] not in allowed] == []


def test_b63_superseded_and_closed_are_distinguishable(db_session: Session) -> None:
    sid, sensor = setup(db_session)
    send(db_session, sid, recs(sensor, [0, 5, 10], 5.0), 11)
    send(db_session, sid, recs(sensor, [50, 55], 5.0), 56)
    [gap] = incidents(db_session, sid, "DATA_GAP")
    send(db_session, sid, recs(sensor, [15, 20, 25, 30, 35, 40, 45], 5.0), 90)
    db_session.refresh(gap)
    rev = latest_revision(db_session, gap.incident_id)
    assert (gap.status, rev.basis) == ("OPEN", "SUPERSEDED_BY_DATA")


# ------------------------------------------------------------------ versions and delay fields (B36, B77, B40)


def test_b36_shipment_keeps_its_own_policy_version(db_session: Session) -> None:
    v1 = active_policy(db_session)
    sid, sensor = setup(db_session)
    v1.status = PolicyStatus.RETIRED
    db_session.flush()
    db_session.add(
        Policy(
            **{
                c.name: getattr(v1, c.name)
                for c in Policy.__table__.columns
                if c.name not in ("policy_id", "created_at", "policy_version", "status", "max_temp_c", "content_sha256")
            },
            policy_version="9.9-test",
            status=PolicyStatus.ACTIVE,
            max_temp_c=Decimal("10.0"),
            content_sha256="f" * 64,
        )
    )
    db_session.flush()
    send(db_session, sid, recs(sensor, [0, 5, 10, 15, 20, 25, 30], 9.0), 31)  # 9.0 > 8.0 only under v1.0
    [inc] = incidents(db_session, sid)
    assert inc.policy_id == v1.policy_id


def test_b77_every_result_carries_policy_and_detector_versions(db_session: Session) -> None:
    sid, sensor = setup(db_session)
    send(db_session, sid, recs(sensor, [0, 5, 10, 15, 20, 25, 30], 9.0), 31)
    evals = db_session.scalars(select(DetectorEvaluation).where(DetectorEvaluation.shipment_id == sid)).all()
    assert evals and all(e.policy_id and e.detector_config_id and e.detector_code_version for e in evals)
    [inc] = incidents(db_session, sid)
    assert inc.detector_config_id and inc.opened_by_evaluation_id and inc.detector_version == "DET-BASELINE v1.0.0"
    det = db_session.scalars(select(Detection).where(Detection.shipment_id == sid)).one()
    assert det.raised_at == m(31) and det.created_at is not None  # processing clock vs DB clock (U-02)


def test_b40_delay_fields_for_a_run_received_in_three_batches(db_session: Session) -> None:
    sid, sensor = setup(db_session)
    send(db_session, sid, recs(sensor, [0, 5], 9.0), 6)
    send(db_session, sid, recs(sensor, [10, 15, 20], 9.0), 40)
    send(db_session, sid, recs(sensor, [25, 30, 35], 9.0), 90)
    [inc] = incidents(db_session, sid)
    first = db_session.scalars(
        select(IncidentRevision).where(IncidentRevision.incident_id == inc.incident_id, IncidentRevision.revision == 1)
    ).one()
    assert (first.extent_start_at, first.confirmed_event_at, first.evidence_received_at, first.raised_at) == (
        m(0),
        m(30),
        m(90),
        m(90),
    )


# ------------------------------------------------------------------ B35, B49, B50


def test_b35_br08_rejected_reading_inside_a_run_counts_as_missing(db_session: Session) -> None:
    sid, sensor = setup(db_session)
    readings = recs(sensor, [0, 5, 10, 20, 25, 30], 9.0) + [
        {"sensor_id": sensor, "event_at": m(15).isoformat(), "temperature_c": Decimal("61.0")}
    ]
    result = send(db_session, sid, readings, 31)
    assert [r.reason_code for r in result.records if r.outcome == "REJECTED"] == ["OUT_OF_PHYSICAL_RANGE"]
    gap = db_session.scalars(select(DataGap).where(DataGap.shipment_id == sid)).one()
    assert (gap.start_at, gap.end_at, gap.gap_status) == (m(10), m(20), "SHORT_GAP")
    assert incidents(db_session, sid, "TEMPERATURE_EXCURSION") == []  # 10 + 10 min observed, never bridged


def test_b49_c02_delayed_readings_fill_the_unknown_span_without_gap_or_incident(db_session: Session) -> None:
    sid, sensor = setup(db_session)
    send(db_session, sid, recs(sensor, [0], 5.0), 1)
    assert status(db_session, sid, sensor, m(45))["state"] == "UNKNOWN"
    send(db_session, sid, recs(sensor, [5 * i for i in range(1, 10)], 5.0), 46)
    assert status(db_session, sid, sensor, m(46))["state"] == "CURRENT"
    assert db_session.scalar(select(func.count()).select_from(DataGap).where(DataGap.shipment_id == sid)) == 0
    assert incidents(db_session, sid) == []


def test_b50_c02_confirmed_40_min_gap_opens_data_gap_incident_at_receipt(db_session: Session) -> None:
    sid, sensor = setup(db_session)
    send(db_session, sid, recs(sensor, [0], 5.0), 1)
    send(db_session, sid, recs(sensor, [40], 5.0), 46)
    [gap_incident] = incidents(db_session, sid, "DATA_GAP")
    assert (gap_incident.opened_at, gap_incident.interval_start, gap_incident.interval_end) == (m(46), m(0), m(40))
    rev = latest_revision(db_session, gap_incident.incident_id)
    assert rev.gap_status == "UNKNOWN_REVIEW_REQUIRED" and rev.bracketing_span_s == Decimal("2400")
