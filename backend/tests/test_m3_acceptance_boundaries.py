"""M3 acceptance review: direct assertions for boundary cases B33, B62, B64, B66, B79 and B80.

Each test states the contract requirement it checks (docs/design/m3-baseline-detector-contract.md §7).
"""

import itertools
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    DataGap,
    DataQualityWarning,
    Detection,
    DetectorConfigVersion,
    DetectorEvaluation,
    Disposition,
    DispositionIncident,
    Incident,
    IncidentRevision,
    IngestBatch,
    Reading,
    SensorAssignment,
    Shipment,
    WarehouseRelease,
)
from app.db.models.enums import DataOrigin, Decision, IngestMode, IngestSource
from app.domain.detector import Obs, evaluate
from app.domain.reconcile import IncidentBasis
from app.domain.replay import SensorEvaluator, StepKind, build_timeline
from app.evaluation.baseline import DetectedIncident, run_baseline_evaluation, summarize
from app.services.detection import load_state, replay_shipment
from app.services.ingest import ingest_batch
from app.services.queries import visible_at
from tests.factories import make_sensor, make_shipment, user
from tests.m3_helpers import CONFIG, POLICY

T = datetime(2026, 9, 5, 0, 0, tzinfo=UTC)
REPO_DIR = Path(os.environ.get("COLDCHAIN_REPO_DIR", Path(__file__).resolve().parents[2]))
APP_DIR = Path(__file__).resolve().parents[1] / "app"


def m(x: float) -> datetime:
    return T + timedelta(minutes=x)


# A journey with normal data, an excursion split across batches, a real logger hole, an out-of-order
# batch and an end boundary. (received_minute, event minutes, value)
BATCHES: list[tuple[float, list[float], float]] = [
    (16, [0, 5, 10, 15], 5.0),
    (31, [20, 25, 30], 9.5),
    (95, [65, 70, 75, 80, 85, 90], 5.0),  # arrives before the batch below (out of order)
    (100, [35, 40, 45, 50], 9.5),  # fills part of the hole; 55 and 60 never arrive
    (130, [95, 100, 105, 110, 115, 120], 1.0),
    (140, [125, 130, 135], 5.0),
]
END = m(160)


def _obs(received: float, minutes: list[float], value: float) -> list[Obs]:
    return [Obs(m(x), Decimal(str(value)), m(received)) for x in minutes]


def _event_time_content(ev: SensorEvaluator) -> tuple:
    """Current results in event time (identity keys and processing times excluded)."""
    st = ev.state
    return (
        sorted((g.gap.start_at, g.gap) for g in st.gaps.values()),
        sorted((r.run.first_event_at, r.run) for r in st.runs.values()),
        sorted(
            (w.spec.kind, w.spec.gap_key, w.spec.interval_start_at, w.spec.interval_end_at, w.spec.message)
            for w in st.warnings.values()
        ),
        sorted(
            (i.category, i.values.extent_start_at, i.values.extent_end_at, i.values.extent_open)
            for i in st.incidents.values()
            if i.values.basis == IncidentBasis.CURRENT
        ),
    )


def _evaluator() -> SensorEvaluator:
    return SensorEvaluator(
        shipment_id="SHP", sensor_id="SNS", mode="TEST", policy=POLICY, config=CONFIG, assigned_from=T, assigned_to=END
    )


# ------------------------------------------------------------------ B33 (BR-06, C-07)


def test_b33_final_event_time_results_and_current_incident_extents_are_order_independent() -> None:
    """Contract B33: every arrival order of the same batches gives identical final current gaps, runs,
    warnings and incident extents. Receipt-time fields, identity keys and history may differ."""
    results = []
    for order in itertools.permutations(range(len(BATCHES)), 4):
        rest = [i for i in range(len(BATCHES)) if i not in order]
        ev = _evaluator()
        for step, idx in enumerate([*order, *rest]):
            at = m(200 + step)  # every batch received after the end boundary, in this order
            _, minutes, value = BATCHES[idx]
            ev.add([Obs(o.event_at, o.temperature_c, at) for o in _obs(0, minutes, value)])
            ev.evaluate(at, "BATCH")
        content = _event_time_content(ev)
        runs_without_receipt = [
            (k, r.__class__(*[getattr(r, f) if f != "evidence_received_at" else None for f in r.__slots__]))
            for k, r in content[1]
        ]
        results.append((content[0], runs_without_receipt, content[2], content[3]))
    assert len(results) == 360 and all(r == results[0] for r in results)


def test_b33_documented_exception_conflicting_duplicates_depend_on_arrival_order(db_session: Session) -> None:
    """BR-07: the first accepted value wins, so with a conflict the stored value depends on order."""
    stored = []
    for first, second in ((Decimal("8.4"), Decimal("9.1")), (Decimal("9.1"), Decimal("8.4"))):
        shipment, sensor = make_shipment(db_session), make_sensor(db_session)
        db_session.add(SensorAssignment(sensor_id=sensor.sensor_id, shipment_id=shipment.shipment_id, assigned_from=T))
        db_session.flush()
        for i, value in enumerate((first, second)):
            ingest_batch(
                db_session,
                business_ref=f"B33-{uuid.uuid4().hex[:8]}",
                shipment_id=shipment.shipment_id,
                readings=[{"sensor_id": sensor.sensor_id, "event_at": m(5).isoformat(), "temperature_c": value}],
                context_records=[],
                mode=IngestMode.REPLAY,
                received_at=m(10 + i),
            )
        stored.append(
            db_session.scalars(select(Reading.temperature_c).where(Reading.sensor_id == sensor.sensor_id)).one()
        )
    assert stored == [Decimal("8.40"), Decimal("9.10")]


# ------------------------------------------------------------------ B66 (C-09)


def test_b66_every_incremental_step_equals_a_fresh_causal_recalculation() -> None:
    """Contract B66: at every replay step the incrementally maintained results equal a fresh evaluation
    of the readings received by that step."""
    incremental = _evaluator()
    for b in BATCHES:
        incremental.add(_obs(*b))
    steps = build_timeline(T, END, [(m(r), f"U{i}") for i, (r, _, _) in enumerate(BATCHES)])
    checked = 0
    for step in steps:
        incremental.evaluate(step.at, step.kind.value)
        fresh = _evaluator()
        for b in BATCHES:
            fresh.add(_obs(*b))
        fresh.evaluate(step.at, step.kind.value)
        assert _event_time_content(incremental) == _event_time_content(fresh), step
        checked += 1
    assert checked == len(BATCHES) + 2


def _store_like_import(db: Session) -> tuple[str, str]:
    shipment, sensor = make_shipment(db), make_sensor(db)
    db.add(
        SensorAssignment(sensor_id=sensor.sensor_id, shipment_id=shipment.shipment_id, assigned_from=T, assigned_to=END)
    )
    db.flush()
    for i, (received, minutes, value) in enumerate(BATCHES):
        bid = uuid.uuid4()
        db.add(
            IngestBatch(
                batch_id=bid,
                business_ref=f"{shipment.shipment_id}-U{i}",
                shipment_id=shipment.shipment_id,
                submitted_by_org_id="ORG-CARRIER",
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
                    sensor_id=sensor.sensor_id,
                    shipment_id=shipment.shipment_id,
                    ingest_batch_id=bid,
                    event_at=m(x),
                    received_at=m(received),
                    temperature_c=Decimal(str(value)),
                )
            )
    db.flush()
    return shipment.shipment_id, sensor.sensor_id


def test_b66_stored_history_viewed_as_of_each_step_equals_fresh_evaluation(db_session: Session) -> None:
    """The persisted revisions, viewed causally at each step's ``as_of``, equal a fresh pure evaluation."""
    sid, sensor = _store_like_import(db_session)
    replay_shipment(db_session, sid)
    all_obs = [o for b in BATCHES for o in _obs(*b)]
    for step in build_timeline(T, END, [(m(r), f"U{i}") for i, (r, _, _) in enumerate(BATCHES)]):
        at = step.at
        visible = sorted((o for o in all_obs if o.received_at <= at), key=lambda o: o.event_at)
        snap = evaluate(visible, start=T, end=END if at >= END else None, policy=POLICY, config=CONFIG)
        gaps = db_session.scalars(select(DataGap).where(DataGap.shipment_id == sid, visible_at(DataGap, at))).all()
        runs = db_session.scalars(
            select(Detection).where(Detection.shipment_id == sid, visible_at(Detection, at))
        ).all()
        assert sorted((g.start_at, g.end_at, str(g.gap_status)) for g in gaps) == sorted(
            (g.start_at, g.end_at, g.status.value) for g in snap.gaps
        ), at
        assert sorted((r.first_event_at, r.last_event_at, r.meets_policy_duration, r.run_open) for r in runs) == sorted(
            (r.first_event_at, r.last_event_at, r.meets_policy_duration, r.run_open) for r in snap.runs
        ), at
    assert (
        db_session.scalar(
            select(func.count()).select_from(DetectorEvaluation).where(DetectorEvaluation.shipment_id == sid)
        )
        == len(BATCHES) + 2
    )


# ------------------------------------------------------------------ B62 (U-04, C-08)


def _row(db: Session, model: type, pk: Any) -> dict[str, Any]:
    obj = db.get(model, pk)
    db.refresh(obj)
    return {c.name: getattr(obj, c.name) for c in model.__table__.columns}  # type: ignore[attr-defined]


def test_b62_late_evidence_leaves_every_decision_record_byte_identical(db_session: Session) -> None:
    """U-04: a disposition, its incident links, the incident row, earlier revisions and an executed
    warehouse release are unchanged field by field; only new rows are appended.
    Deferred to M5: the real disposition and reassessment workflow (here a test stand-in writes the
    disposition and release directly)."""
    shipment, sensor = make_shipment(db_session), make_sensor(db_session)
    db_session.add(SensorAssignment(sensor_id=sensor.sensor_id, shipment_id=shipment.shipment_id, assigned_from=T))
    db_session.flush()

    def send(minutes: list[float], value: str, received: float) -> None:
        ingest_batch(
            db_session,
            business_ref=f"B62-{uuid.uuid4().hex[:8]}",
            shipment_id=shipment.shipment_id,
            readings=[
                {"sensor_id": sensor.sensor_id, "event_at": m(x).isoformat(), "temperature_c": Decimal(value)}
                for x in minutes
            ],
            context_records=[],
            mode=IngestMode.REPLAY,
            received_at=m(received),
        )

    send([0, 5, 10, 15, 20, 25, 30], "9.0", 31)
    inc = db_session.scalars(select(Incident).where(Incident.shipment_id == shipment.shipment_id)).one()
    disp = Disposition(
        business_ref=f"D-{uuid.uuid4().hex[:8]}",
        shipment_id=shipment.shipment_id,
        decision=Decision.RELEASE,
        decided_by_user_id=user(db_session, "quality.demo").user_id,
        decided_at=m(60),
        rationale="test stand-in for the M5 workflow",
        policy_id=inc.policy_id,
    )
    db_session.add(disp)
    db_session.flush()
    db_session.add(
        DispositionIncident(
            disposition_id=disp.disposition_id, incident_id=inc.incident_id, shipment_id=shipment.shipment_id
        )
    )
    inc.status, inc.closed_at = "CLOSED", m(60)
    release = WarehouseRelease(
        business_ref=f"R-{uuid.uuid4().hex[:8]}",
        shipment_id=shipment.shipment_id,
        disposition_id=disp.disposition_id,
        released_by_user_id=user(db_session, "warehouse.demo").user_id,
        released_at=m(70),
    )
    db_session.add(release)
    db_session.flush()
    rev1 = db_session.scalars(select(IncidentRevision).where(IncidentRevision.incident_id == inc.incident_id)).one()
    before = (
        _row(db_session, Disposition, disp.disposition_id),
        _row(db_session, Incident, inc.incident_id),
        _row(db_session, WarehouseRelease, release.release_id),
        _row(db_session, IncidentRevision, rev1.incident_revision_id),
    )
    links_before = db_session.scalar(select(func.count()).select_from(DispositionIncident))
    send([35, 40, 45], "9.5", 600)  # extends the closed incident
    send([50, 55, 60, 65], "1.0", 700)  # opens a new LOW incident after the decision
    after = (
        _row(db_session, Disposition, disp.disposition_id),
        _row(db_session, Incident, inc.incident_id),
        _row(db_session, WarehouseRelease, release.release_id),
        _row(db_session, IncidentRevision, rev1.incident_revision_id),
    )
    assert after == before
    assert db_session.scalar(select(func.count()).select_from(DispositionIncident)) == links_before
    revisions = db_session.scalars(
        select(IncidentRevision.revision)
        .where(IncidentRevision.incident_id == inc.incident_id)
        .order_by(IncidentRevision.revision)
    ).all()
    assert revisions[0] == 1 and len(revisions) >= 2


# ------------------------------------------------------------------ B64 (C-10)

TABLES = (
    Reading,
    IngestBatch,
    DetectorEvaluation,
    DataGap,
    Detection,
    DataQualityWarning,
    Incident,
    IncidentRevision,
    DetectorConfigVersion,
    Shipment,
)


def test_b64_offline_reprocessing_with_another_configuration_never_touches_live_tables(
    db_session: Session, tmp_path: Path
) -> None:
    """C-10: reprocessing under a different detector configuration is an offline, versioned run whose
    outputs exist only in its run folder; live tables keep the same row counts."""
    counts = {t.__tablename__: db_session.scalar(select(func.count()).select_from(t)) for t in TABLES}
    config = json.loads((APP_DIR / "seed/data/detector/DET-BASELINE_v1.0.0.json").read_text())
    config.update(config_version="9.9.9-offline-test", max_continuous_interval_s=400)
    config_file = tmp_path / "alt-config.json"
    config_file.write_text(json.dumps(config))
    out = tmp_path / "run"
    result = run_baseline_evaluation(
        REPO_DIR / "data/release/coldchain-sim-v1.0.0-seed11",
        APP_DIR / "seed/data/policies/POL-CHILL-01_v1.0.json",
        config_file,
        out,
        partitions=("validation",),
    )
    assert result["run_config"]["detector_config"]["version"] == "9.9.9-offline-test"
    assert result["run_config"]["detector_config"]["max_continuous_interval_s"] == 400
    assert sorted(p.name for p in tmp_path.iterdir()) == ["alt-config.json", "run"]
    assert {t.__tablename__: db_session.scalar(select(func.count()).select_from(t)) for t in TABLES} == counts


# ------------------------------------------------------------------ B79, B80 (A-01, A-02, U-06)


def _det(ref: str, journey: str, revisions: list[tuple[float, float, float, float | None, str]]) -> DetectedIncident:
    d = DetectedIncident(journey, ref, "TEMPERATURE_EXCURSION", "HIGH")
    for n, (raised, start, end, confirmed, basis) in enumerate(revisions, start=1):
        d.revisions.append(
            dict(
                revision=n,
                raised_at=m(raised),
                start=m(start),
                end=m(end),
                confirmed_event_at=m(confirmed) if confirmed is not None else None,
                first_event_at=m(start),
                basis=basis,
                gap_continuity_warning=False,
                gap_status=None,
            )
        )
    return d


def test_b79_b80_metrics_on_a_hand_made_fixture() -> None:
    """One matched event (later extended by backfill), one missed event, one false alarm and one false
    alarm later superseded by data. Delay uses the earliest raised revision overlapping the reference."""
    detections = [
        # matched; revision 1 raised at 40 (confirmed at 35), revision 2 after backfill at 300
        _det("D-match", "J1", [(40, 5, 35, 35, "CURRENT"), (300, 0, 55, 30, "CURRENT")]),
        _det("D-false", "J1", [(500, 400, 440, 430, "CURRENT")]),
        _det("D-false-superseded", "J2", [(90, 60, 95, 90, "CURRENT"), (200, 60, 95, 90, "SUPERSEDED_BY_DATA")]),
    ]
    references = [
        dict(
            event_id="R-hit",
            journey_id="J1",
            event_type="EXCURSION_HIGH",
            start=m(0),
            end=m(60),
            attributes={"missing_readings_in_interval": 1, "delayed_readings_in_interval": 0},
        ),
        dict(
            event_id="R-missed",
            journey_id="J2",
            event_type="EXCURSION_HIGH",
            start=m(200),
            end=m(260),
            attributes={"missing_readings_in_interval": 0, "delayed_readings_in_interval": 2},
        ),
    ]
    summary, match_rows, _, matched = summarize(["J1", "J2"], detections, {}, references, [], 0, 0)
    ex = summary["excursion_detection"]
    assert matched == {"D-match"}
    assert (ex["reference_events"], ex["detections_raised"], ex["matched"]) == (2, 3, 1)
    assert (ex["precision"], ex["recall"]) == (round(1 / 3, 4), 0.5)
    assert (ex["false_alarms"], ex["false_alarms_later_superseded_or_merged"]) == (2, 1)
    assert ex["false_alarms_per_journey"] == 1.0
    delay = summary["detection_delay_min"]
    assert delay["event_time_delay_Ea_minus_T0"] == {
        "n": 1,
        "mean": 35.0,
        "median": 35.0,
        "p90_nearest_rank": 35.0,
        "min": 35.0,
        "max": 35.0,
    }
    assert delay["emission_delay_Te_minus_T0"]["median"] == 40.0  # revision 1, not the backfill revision (B80)
    assert delay["missed_events_without_delay"] == 1
    hit = next(r for r in match_rows if r["reference_id"] == "R-hit")
    assert hit["raised_at"] == m(40).isoformat() and hit["detection_ref"] == "D-match"
    missing = summary["missing_readings_behaviour"]
    assert missing["recall_reference_excursions_with_missing_readings"] == {
        "reference_events": 1,
        "detected": 1,
        "recall": 1.0,
    }
    assert missing["recall_reference_excursions_without_missing_readings"]["recall"] == 0.0
