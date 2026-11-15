"""Causal ocean-coverage demonstration (DEMO-01 steps 1-8 for Milestone 3).

A new demo shipment receives, through the normal ingestion service in trusted REPLAY mode,
exactly the batches an imported journey received, at their recorded ``received_at`` times,
plus the documented monitoring boundaries. The monitoring state is captured at checkpoints
*while* the replay runs, so each checkpoint only knows data received by then. Afterwards the
same checkpoints are recomputed from the finished database with ``as_of`` filters; both must
be identical (causality check).

The source journey is chosen from observed data only: the imported journey with the longest
silence between two received batches whose restoring batch carries out-of-range readings.
The canonical dataset files are not touched; the demo writes new rows for a new shipment.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ContextReading,
    DataGap,
    DetectorEvaluation,
    Incident,
    IncidentRevision,
    IngestBatch,
    Policy,
    Reading,
    Sensor,
    SensorAssignment,
    Shipment,
)
from app.db.models.enums import DataOrigin, EvaluationMode, EvaluationTrigger, IngestMode, IngestSource
from app.domain.replay import StepKind, build_timeline
from app.services.detection import evaluate_sensor
from app.services.ingest import ingest_batch
from app.services.queries import sensor_status, shipment_context, visible_at

MIN_OUT_OF_RANGE_IN_RESTORE = 7  # enough readings that an excursion is plausible (selection only)


@dataclass
class Checkpoint:
    label: str
    at: datetime
    snapshot: dict[str, Any] | None = None


@dataclass
class DemoReport:
    source_shipment_id: str
    demo_shipment_id: str
    outage_from: datetime
    outage_to: datetime
    batches_replayed: int = 0
    already_existed: bool = False
    checkpoints: list[Checkpoint] = field(default_factory=list)
    causal_recheck_identical: bool | None = None


def choose_source(session: Session) -> tuple[str, datetime, datetime]:
    rows = session.execute(
        select(IngestBatch.shipment_id, IngestBatch.received_at, IngestBatch.batch_id)
        .where(IngestBatch.ingest_mode == IngestMode.IMPORT)
        .order_by(IngestBatch.shipment_id, IngestBatch.received_at)
    ).all()
    silences: list[tuple[timedelta, str, datetime, datetime, Any]] = []
    previous: tuple[str, datetime] | None = None
    for shipment_id, received_at, batch_id in rows:
        if previous is not None and previous[0] == shipment_id:
            silences.append((received_at - previous[1], shipment_id, previous[1], received_at, batch_id))
        previous = (shipment_id, received_at)
    silences.sort(key=lambda s: (-s[0], s[1]))
    for _, shipment_id, start, end, batch_id in silences[:40]:
        policy = session.scalar(
            select(Policy)
            .join(Shipment, Shipment.policy_id == Policy.policy_id)
            .where(Shipment.shipment_id == shipment_id)
        )
        temps = session.scalars(select(Reading.temperature_c).where(Reading.ingest_batch_id == batch_id)).all()
        if (
            policy
            and sum(1 for t in temps if t > policy.max_temp_c or t < policy.min_temp_c) >= MIN_OUT_OF_RANGE_IN_RESTORE
        ):
            return shipment_id, start, end
    if not silences:
        raise RuntimeError("No imported journeys found. Import the dataset first (python -m app.dataset import ...).")
    return silences[0][1], silences[0][2], silences[0][3]


def _capture(session: Session, shipment_id: str, sensor_id: str, at: datetime) -> dict[str, Any]:
    _, policy, config = shipment_context(session, shipment_id)
    status = sensor_status(session, shipment_id, sensor_id, at, policy, config)
    gaps = session.scalars(select(DataGap).where(DataGap.shipment_id == shipment_id, visible_at(DataGap, at))).all()
    incidents = []
    for inc in session.scalars(
        select(Incident)
        .where(Incident.shipment_id == shipment_id, Incident.opened_at <= at)
        .order_by(Incident.opened_at, Incident.business_ref)
    ).all():
        rev = session.scalar(
            select(IncidentRevision)
            .where(IncidentRevision.incident_id == inc.incident_id, IncidentRevision.raised_at <= at)
            .order_by(IncidentRevision.revision.desc())
            .limit(1)
        )
        incidents.append(
            dict(
                business_ref=inc.business_ref,
                category=str(inc.category),
                status=str(inc.status),
                basis=str(rev.basis) if rev else None,
                extent=(rev.extent_start_at.isoformat(), rev.extent_end_at.isoformat()) if rev else None,
                gap_continuity_warning=rev.gap_continuity_warning if rev else None,
                raised_at=inc.opened_at.isoformat(),
            )
        )
    return dict(
        state=status["state"],
        newest_event_at=status["newest_event_at"].isoformat() if status["newest_event_at"] else None,
        unobserved_min=round(float(status["unobserved_duration_s"]) / 60, 2)
        if status["unobserved_duration_s"] is not None
        else None,
        visible_readings=status["visible_reading_count"],
        confirmed_gaps=sorted((g.start_at.isoformat(), g.end_at.isoformat(), str(g.gap_status)) for g in gaps),
        incidents=incidents,
    )


def run_ocean_demo(
    session: Session, source_shipment_id: str | None = None, log: Callable[[str], None] = print
) -> DemoReport:
    if source_shipment_id is None:
        source_shipment_id, outage_from, outage_to = choose_source(session)
    else:
        times = session.scalars(
            select(IngestBatch.received_at)
            .where(IngestBatch.shipment_id == source_shipment_id)
            .order_by(IngestBatch.received_at)
        ).all()
        if len(times) < 2:
            raise RuntimeError(f"{source_shipment_id} has fewer than two received batches")
        outage_from, outage_to = max(zip(times, times[1:], strict=False), key=lambda p: p[1] - p[0])
    source = session.get(Shipment, source_shipment_id)
    if source is None:
        raise RuntimeError(f"source shipment {source_shipment_id} not found")
    assignment = session.scalars(
        select(SensorAssignment).where(SensorAssignment.shipment_id == source_shipment_id)
    ).one()
    demo_id = f"DEMO-OCEAN-{source_shipment_id}"[:60]
    demo_sensor = f"DEMO-{assignment.sensor_id}"[:60]
    report = DemoReport(source_shipment_id, demo_id, outage_from, outage_to)

    newest_before = (
        session.scalar(
            select(Reading.event_at)
            .where(Reading.shipment_id == source_shipment_id, Reading.received_at <= outage_from)
            .order_by(Reading.event_at.desc())
            .limit(1)
        )
        or outage_from
    )
    report.checkpoints = [
        Checkpoint("1 normal telemetry (last batch before the outage)", outage_from),
        Checkpoint(
            "3a connectivity lost: just over 7 min 30 s without a new reading",
            max(outage_from, newest_before + timedelta(minutes=7, seconds=30)) + timedelta(seconds=1),
        ),
        Checkpoint(
            "3b connectivity lost: just over 15 min without a new reading",
            max(outage_from, newest_before + timedelta(minutes=15)) + timedelta(seconds=1),
        ),
        Checkpoint(
            "3c connectivity lost: 45 min without a new reading",
            max(outage_from, newest_before + timedelta(minutes=45)),
        ),
        Checkpoint(
            "4 mid-outage (readings buffered on the logger, not received)", outage_from + (outage_to - outage_from) / 2
        ),
        Checkpoint("4 one second before link restoration", outage_to - timedelta(seconds=1)),
        Checkpoint("5-7 link restored: buffered backfill received and re-evaluated", outage_to),
    ]

    if session.get(Shipment, demo_id) is not None:
        report.already_existed = True
        log(f"Demo shipment {demo_id} already exists; not replaying again (idempotent). Showing causal views.")
    else:
        if session.get(Sensor, demo_sensor) is None:
            session.add(
                Sensor(
                    sensor_id=demo_sensor,
                    sensor_type="TEMPERATURE_LOGGER",
                    description=f"Demo copy of {assignment.sensor_id} (ocean coverage demo, simulated)",
                )
            )
        session.add(
            Shipment(
                shipment_id=demo_id,
                product_id=source.product_id,
                policy_id=source.policy_id,
                shipper_org_id=source.shipper_org_id,
                carrier_org_id=source.carrier_org_id,
                receiver_org_id=source.receiver_org_id,
                origin=source.origin,
                destination=source.destination,
                data_origin=DataOrigin.SIMULATED,
            )
        )
        session.flush()
        session.add(
            SensorAssignment(
                sensor_id=demo_sensor,
                shipment_id=demo_id,
                assigned_from=assignment.assigned_from,
                assigned_to=assignment.assigned_to,
            )
        )
        session.flush()
        batches = session.execute(
            select(IngestBatch.received_at, IngestBatch.business_ref, IngestBatch.batch_id).where(
                IngestBatch.shipment_id == source_shipment_id
            )
        ).all()
        batch_ids = {ref: bid for _, ref, bid in batches}
        pending = sorted(report.checkpoints, key=lambda c: c.at)
        for step in build_timeline(
            assignment.assigned_from, assignment.assigned_to, [(at, ref) for at, ref, _ in batches]
        ):
            while pending and pending[0].at < step.at:
                cp = pending.pop(0)
                cp.snapshot = _capture(session, demo_id, demo_sensor, cp.at)
            if step.kind == StepKind.BATCH:
                bid = batch_ids[step.batch_ref or ""]
                readings = [
                    dict(sensor_id=demo_sensor, event_at=e.isoformat(), temperature_c=t)
                    for e, t in session.execute(
                        select(Reading.event_at, Reading.temperature_c)
                        .where(Reading.ingest_batch_id == bid)
                        .order_by(Reading.event_at)
                    ).all()
                ]
                contexts = [
                    dict(
                        sensor_id=demo_sensor,
                        event_at=e.isoformat(),
                        door_state=str(d) if d else None,
                        battery_level_pct=b,
                        ambient_temperature_c=a,
                    )
                    for e, d, b, a in session.execute(
                        select(
                            ContextReading.event_at,
                            ContextReading.door_state,
                            ContextReading.battery_level_pct,
                            ContextReading.ambient_temperature_c,
                        )
                        .where(ContextReading.ingest_batch_id == bid)
                        .order_by(ContextReading.event_at)
                    ).all()
                ]
                ingest_batch(
                    session,
                    business_ref=f"DEMO-{step.batch_ref}"[:120],
                    shipment_id=demo_id,
                    readings=readings,
                    context_records=contexts,
                    mode=IngestMode.REPLAY,
                    received_at=step.at,
                    source=IngestSource.SIMULATOR,
                    data_origin=DataOrigin.SIMULATED,
                )
                report.batches_replayed += 1
            else:
                evaluate_sensor(
                    session,
                    demo_id,
                    demo_sensor,
                    as_of=step.at,
                    mode=EvaluationMode.REPLAY,
                    trigger=EvaluationTrigger(step.kind.value),
                )
        for cp in pending:
            cp.snapshot = _capture(session, demo_id, demo_sensor, cp.at)
    end_at = (
        session.scalar(
            select(DetectorEvaluation.as_of)
            .where(DetectorEvaluation.shipment_id == demo_id)
            .order_by(DetectorEvaluation.as_of.desc())
            .limit(1)
        )
        or outage_to
    )
    final = Checkpoint("8 end of replay: incidents pending human review", end_at)
    final.snapshot = _capture(session, demo_id, demo_sensor, end_at)
    report.checkpoints.append(final)

    recheck = [_capture(session, demo_id, demo_sensor, cp.at) for cp in report.checkpoints]
    if not report.already_existed:
        report.causal_recheck_identical = all(
            cp.snapshot == again for cp, again in zip(report.checkpoints, recheck, strict=True)
        )
    else:
        for cp, again in zip(report.checkpoints, recheck, strict=True):
            cp.snapshot = again
    return report


def format_report(report: DemoReport) -> list[str]:
    lines = [
        "SIMULATED DATA - ocean coverage demonstration (Milestone 3, causal replay)",
        f"source journey (observed data only) : {report.source_shipment_id}",
        f"demo shipment                       : {report.demo_shipment_id}",
        f"longest silence between batches     : {report.outage_from.isoformat()} -> {report.outage_to.isoformat()} "
        f"({(report.outage_to - report.outage_from).total_seconds() / 3600:.2f} h)",
        f"batches replayed through ingestion  : {report.batches_replayed}"
        + (" (demo already existed; nothing replayed)" if report.already_existed else ""),
        "",
    ]
    for cp in report.checkpoints:
        s = cp.snapshot or {}
        lines.append(f"[{cp.at.isoformat()}] {cp.label}")
        lines.append(
            f"    monitoring state  : {s.get('state')}   newest event_at: {s.get('newest_event_at')}   "
            f"unobserved: {s.get('unobserved_min')} min   visible readings: {s.get('visible_readings')}"
        )
        gaps = s.get("confirmed_gaps", [])
        review = [g for g in gaps if g[2] == "UNKNOWN_REVIEW_REQUIRED"]
        lines.append(f"    confirmed gaps    : {len(gaps)} (review required: {len(review)})")
        for inc in s.get("incidents", []):
            lines.append(
                f"    incident          : {inc['business_ref']} {inc['category']} status={inc['status']} "
                f"basis={inc['basis']} extent={inc['extent']} gap_continuity_warning="
                f"{inc['gap_continuity_warning']} raised_at={inc['raised_at']}"
            )
        if not s.get("incidents"):
            lines.append("    incident          : none")
    lines.append("")
    if report.causal_recheck_identical is not None:
        lines.append(
            "causal re-check (checkpoints recomputed from the final database with as_of filters): "
            + ("IDENTICAL" if report.causal_recheck_identical else "DIFFERENT")
        )
    lines.append(
        "No disposition is recorded: every incident stays OPEN, pending human quality review (M5). "
        "No warehouse release is possible or attempted."
    )
    return lines
