"""Read models for the monitoring API: causal "as of" views of the append-only results.

A result is visible at ``as_of`` when it was raised by then and not superseded by then:
``raised_at <= as_of AND (superseded_at IS NULL OR superseded_at > as_of)``. Readings are
visible when ``received_at <= as_of``. So the API can show what the system knew at any
past processing time (for example during an ocean outage), never using later data.
"""

import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    DataGap,
    DataQualityWarning,
    DecisionReassessment,
    Detection,
    DetectorConfigVersion,
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
)
from app.domain.detector import MonitoringStateName, classify, monitoring_state, seconds
from app.domain.reconcile import EVIDENCE_WARNING_KINDS
from app.domain.rules import DetectorConfig, PolicyRules
from app.services.communication import communication_view
from app.services.detection import active_detector_config, boundaries, monitoring_windows, policy_rules_for

FAR_FUTURE = datetime(9999, 12, 31, tzinfo=UTC)  # "as of the end of time": shows full history state


def visible_at(model: Any, as_of: datetime) -> ColumnElement[bool]:
    return and_(model.raised_at <= as_of, or_(model.superseded_at.is_(None), model.superseded_at > as_of))


def _minutes(value: Any) -> float | None:
    return None if value is None else round(float(value) / 60, 4)


# ------------------------------------------------------------------ serializers


def gap_dict(g: DataGap, as_of: datetime) -> dict[str, Any]:
    return dict(
        gap_key=g.gap_key,
        sensor_id=g.sensor_id,
        start_at=g.start_at,
        end_at=g.end_at,
        start_bound=g.start_bound,
        end_bound=g.end_bound,
        bracketing_span_s=g.bracketing_span_s,
        bracketing_span_min=_minutes(g.bracketing_span_s),
        estimated_missing_samples=g.estimated_missing_samples,
        estimated_missing_duration_s=g.estimated_missing_duration_s,
        gap_status=g.gap_status,
        out_of_range_before=g.out_of_range_before,
        out_of_range_after=g.out_of_range_after,
        raised_at=g.raised_at,
        superseded_at=g.superseded_at,
        state="SUPERSEDED" if g.superseded_at is not None and g.superseded_at <= as_of else "CURRENT",
    )


def run_dict(d: Detection, as_of: datetime) -> dict[str, Any]:
    return dict(
        run_key=d.run_key,
        sensor_id=d.sensor_id,
        source=d.source,
        direction=d.direction,
        first_event_at=d.first_event_at,
        last_event_at=d.last_event_at,
        reading_count=d.reading_count,
        observed_duration_s=d.observed_duration_s,
        observed_duration_min=_minutes(d.observed_duration_s),
        threshold_min=d.threshold_min,
        meets_policy_duration=d.meets_policy_duration,
        confirmed_event_at=d.confirmed_event_at,
        evidence_received_at=d.evidence_received_at,
        peak_c=d.peak_c,
        run_open=d.run_open,
        preceded_by_gap_key=d.preceded_by_gap_key,
        followed_by_gap_key=d.followed_by_gap_key,
        raised_at=d.raised_at,
        superseded_at=d.superseded_at,
        state="SUPERSEDED" if d.superseded_at is not None and d.superseded_at <= as_of else "CURRENT",
    )


def warning_dict(w: DataQualityWarning, as_of: datetime) -> dict[str, Any]:
    return dict(
        warning_key=w.warning_key,
        kind=w.kind,
        affects_quality_evidence=w.affects_quality_evidence,
        sensor_id=w.sensor_id,
        interval_start_at=w.interval_start_at,
        interval_end_at=w.interval_end_at,
        linked_incident_id=w.linked_incident_id,
        message=w.message,
        details=w.details,
        raised_at=w.raised_at,
        superseded_at=w.superseded_at,
        state="SUPERSEDED" if w.superseded_at is not None and w.superseded_at <= as_of else "CURRENT",
    )


def policy_ref(p: PolicyRules) -> dict[str, Any]:
    return dict(
        policy_id=p.policy_id,
        policy_code=p.policy_code,
        policy_version=p.policy_version,
        content_sha256=p.content_sha256,
        min_temp_c=p.min_temp_c,
        max_temp_c=p.max_temp_c,
        high_excursion_min_duration_min=int(p.high_min_duration.total_seconds() // 60),
        low_excursion_min_duration_min=int(p.low_min_duration.total_seconds() // 60),
        gap_unknown_after_min=int(p.gap_unknown_after.total_seconds() // 60),
        gap_review_at_min=int(p.gap_review_at.total_seconds() // 60),
    )


def config_ref(c: DetectorConfig) -> dict[str, Any]:
    return dict(
        detector_config_id=c.detector_config_id,
        detector_code=c.detector_code,
        config_version=c.config_version,
        content_sha256=c.content_sha256,
        nominal_sampling_interval_s=int(c.nominal_interval.total_seconds()),
        max_continuous_interval_s=int(c.max_continuous_interval.total_seconds()),
    )


# ------------------------------------------------------------------ monitoring status


def sensor_status(
    session: Session, shipment_id: str, sensor_id: str, as_of: datetime, policy: PolicyRules, config: DetectorConfig
) -> dict[str, Any]:
    windows = monitoring_windows(session, shipment_id).get(sensor_id, [])
    start, end = boundaries(windows)
    newest_event, newest_received, count = session.execute(
        select(func.max(Reading.event_at), func.max(Reading.received_at), func.count()).where(
            Reading.shipment_id == shipment_id, Reading.sensor_id == sensor_id, Reading.received_at <= as_of
        )
    ).one()
    st = monitoring_state(
        newest_event_at=newest_event, assigned_from=start, assigned_to=end, as_of=as_of, policy=policy, config=config
    )
    gaps = session.scalars(
        select(DataGap).where(
            DataGap.shipment_id == shipment_id, DataGap.sensor_id == sensor_id, visible_at(DataGap, as_of)
        )
    ).all()
    by_status = Counter(str(g.gap_status) for g in gaps)
    unobserved = sum((timedelta(microseconds=int(g.bracketing_span_s * 1_000_000)) for g in gaps), timedelta())
    last = session.execute(
        select(Reading.event_at, Reading.temperature_c)
        .where(Reading.shipment_id == shipment_id, Reading.sensor_id == sensor_id, Reading.received_at <= as_of)
        .order_by(Reading.event_at.desc())
        .limit(1)
    ).first()
    uploads = session.scalars(
        select(IngestBatch.received_at)
        .where(
            IngestBatch.batch_id.in_(
                select(Reading.ingest_batch_id).where(
                    Reading.shipment_id == shipment_id, Reading.sensor_id == sensor_id
                )
            ),
            IngestBatch.received_at <= as_of,
        )
        .order_by(IngestBatch.received_at.desc())
        .limit(12)
    ).all()
    comm = communication_view(uploads, as_of, st.state)
    open_incidents = Counter(
        str(c)
        for (c,) in session.execute(
            select(Incident.category).where(
                Incident.shipment_id == shipment_id,
                Incident.sensor_id == sensor_id,
                Incident.opened_at <= as_of,
                or_(Incident.closed_at.is_(None), Incident.closed_at > as_of),
            )
        ).all()
    )
    return dict(
        shipment_id=shipment_id,
        sensor_id=sensor_id,
        as_of=as_of,
        state=st.state.value,
        newest_event_at=newest_event,
        newest_received_at=newest_received,
        visible_reading_count=count,
        unobserved_since_at=st.unobserved_since_at,
        unobserved_duration_s=seconds(st.unobserved_duration) if st.unobserved_duration is not None else None,
        provisional_review_threshold_reached=st.provisional_review_threshold_reached,
        end_boundary_established=st.end_boundary_established,
        monitoring_window=dict(assigned_from=start, assigned_to=end),
        confirmed_gaps=dict(
            SHORT_GAP=by_status.get("SHORT_GAP", 0),
            UNKNOWN=by_status.get("UNKNOWN", 0),
            UNKNOWN_REVIEW_REQUIRED=by_status.get("UNKNOWN_REVIEW_REQUIRED", 0),
        ),
        confirmed_gap_span_s=seconds(unobserved),
        note=_state_note(st.state),
        last_observed_temperature_c=last[1] if last else None,
        last_observed_event_at=last[0] if last else None,
        last_observed_temperature_state=classify(last[1], policy).value if last else None,
        communication=dict(
            status=comm.status.value,
            last_upload_received_at=comm.last_upload_received_at,
            since_last_upload_s=seconds(comm.since_last_upload) if comm.since_last_upload is not None else None,
            observed_upload_interval_s=seconds(comm.observed_upload_interval)
            if comm.observed_upload_interval is not None
            else None,
            longest_recent_upload_interval_s=seconds(comm.longest_recent_upload_interval)
            if comm.longest_recent_upload_interval is not None
            else None,
            recent_intervals_used=comm.recent_intervals_used,
            expected_schedule_configured=comm.expected_schedule_configured,
        ),
        open_incidents_as_of=dict(
            TEMPERATURE_EXCURSION=open_incidents.get("TEMPERATURE_EXCURSION", 0),
            DATA_GAP=open_incidents.get("DATA_GAP", 0),
        ),
    )


def _state_note(state: MonitoringStateName) -> str:
    return {
        MonitoringStateName.CURRENT: "Telemetry is current. The time after the newest reading is not yet received.",
        MonitoringStateName.STALE: "No new reading for more than 7 min 30 s. Not an incident; never shown as in range.",
        MonitoringStateName.UNKNOWN: (
            "No reading for more than 15 min: temperature UNKNOWN. A data-gap incident "
            "opens only when a missing-data interval of at least 30 min is confirmed."
        ),
        MonitoringStateName.NOT_STARTED: "Monitoring window has not started.",
        MonitoringStateName.ENDED: "Documented monitoring window has ended; coverage is given by confirmed gaps.",
    }[state]


def shipment_context(session: Session, shipment_id: str) -> tuple[Shipment, PolicyRules, DetectorConfig]:
    shipment = session.get(Shipment, shipment_id)
    if shipment is None:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"Shipment {shipment_id} not found.")
    return shipment, policy_rules_for(session, shipment), active_detector_config(session)


def telemetry(session: Session, shipment_id: str, as_of: datetime) -> dict[str, Any]:
    shipment, policy, config = shipment_context(session, shipment_id)
    sensors = []
    for sensor_id in sorted(monitoring_windows(session, shipment_id)):
        readings = session.execute(
            select(Reading.event_at, Reading.received_at, Reading.temperature_c, IngestBatch.business_ref)
            .join(IngestBatch, IngestBatch.batch_id == Reading.ingest_batch_id)
            .where(Reading.shipment_id == shipment_id, Reading.sensor_id == sensor_id, Reading.received_at <= as_of)
            .order_by(Reading.event_at)
        ).all()
        points = [
            dict(
                event_at=e,
                received_at=r,
                temperature_c=t,
                batch_ref=b,
                delivery_lag_s=seconds(r - e),
                temperature_state=classify(t, policy).value,
            )
            for e, r, t, b in readings
        ]
        gaps = session.scalars(
            select(DataGap)
            .where(DataGap.shipment_id == shipment_id, DataGap.sensor_id == sensor_id, visible_at(DataGap, as_of))
            .order_by(DataGap.start_at)
        ).all()
        runs = session.scalars(
            select(Detection)
            .where(Detection.shipment_id == shipment_id, Detection.sensor_id == sensor_id, visible_at(Detection, as_of))
            .order_by(Detection.first_event_at)
        ).all()
        status = sensor_status(session, shipment_id, sensor_id, as_of, policy, config)
        sensors.append(
            dict(
                sensor_id=sensor_id,
                status=status,
                readings=points,
                gaps=[gap_dict(g, as_of) for g in gaps],
                runs=[run_dict(d, as_of) for d in runs],
            )
        )
    return dict(
        shipment_id=shipment_id,
        data_origin=shipment.data_origin,
        as_of=as_of,
        policy=policy_ref(policy),
        detector_config=config_ref(config),
        sensors=sensors,
    )


def deliveries(session: Session, shipment_id: str) -> dict[str, Any]:
    """Missing and delayed data: each received batch, how late it was and what it reconciled."""
    shipment, policy, config = shipment_context(session, shipment_id)
    windows = monitoring_windows(session, shipment_id)
    batches = session.scalars(
        select(IngestBatch)
        .where(IngestBatch.shipment_id == shipment_id)
        .order_by(IngestBatch.received_at, IngestBatch.business_ref)
    ).all()
    stats = {
        bid: (n, lo, hi, s)
        for bid, n, lo, hi, s in session.execute(
            select(
                Reading.ingest_batch_id,
                func.count(),
                func.min(Reading.event_at),
                func.max(Reading.event_at),
                func.min(Reading.sensor_id),
            )
            .where(Reading.shipment_id == shipment_id)
            .group_by(Reading.ingest_batch_id)
        ).all()
    }
    reconciled = Counter(
        bid
        for (bid,) in session.execute(
            select(DetectorEvaluation.trigger_batch_id)
            .join(DataGap, DataGap.superseded_by_evaluation_id == DetectorEvaluation.evaluation_id)
            .where(DetectorEvaluation.shipment_id == shipment_id)
        ).all()
    )
    newest: dict[str, datetime] = {}
    out = []
    for b in batches:
        n, lo, hi, sensor = stats.get(b.batch_id, (0, None, None, None))
        before = newest.get(sensor) if sensor else None
        state_before = None
        unobserved_before = None
        if sensor is not None:
            start, end = boundaries(windows.get(sensor, []))
            st = monitoring_state(
                newest_event_at=before,
                assigned_from=start,
                assigned_to=end,
                as_of=b.received_at,
                policy=policy,
                config=config,
            )
            state_before, unobserved_before = st.state.value, st.unobserved_duration
        out.append(
            dict(
                batch_id=b.batch_id,
                business_ref=b.business_ref,
                ingest_mode=b.ingest_mode,
                received_at=b.received_at,
                reading_count=n,
                first_event_at=lo,
                last_event_at=hi,
                max_delivery_lag_s=seconds(b.received_at - lo) if lo is not None else None,
                monitoring_state_before_receipt=state_before,
                unobserved_before_receipt_s=seconds(unobserved_before) if unobserved_before is not None else None,
                # Late backfill: the span this batch fills had already reached the policy review
                # threshold (approved value, no new threshold) before the batch arrived.
                late_backfill=unobserved_before is not None
                and unobserved_before >= policy.gap_review_at
                and hi is not None
                and (before is None or hi > before),
                out_of_order=before is not None and lo is not None and lo < before,
                gap_revisions_superseded=reconciled.get(b.batch_id, 0),
                accepted_count=b.accepted_count,
                rejected_count=b.rejected_count,
                duplicate_count=b.duplicate_count,
            )
        )
        if sensor is not None and hi is not None:
            newest[sensor] = max(hi, before) if before else hi
    gaps = session.scalars(
        select(DataGap).where(DataGap.shipment_id == shipment_id).order_by(DataGap.start_at, DataGap.raised_at)
    ).all()
    return dict(
        shipment_id=shipment_id,
        data_origin=shipment.data_origin,
        batches=out,
        gap_history=[gap_dict(g, FAR_FUTURE) for g in gaps],
    )


# ------------------------------------------------------------------ incidents


def _latest_revisions(session: Session, incident_ids: list[uuid.UUID]) -> dict[uuid.UUID, IncidentRevision]:
    if not incident_ids:
        return {}
    sub = (
        select(IncidentRevision.incident_id, func.max(IncidentRevision.revision).label("rev"))
        .where(IncidentRevision.incident_id.in_(incident_ids))
        .group_by(IncidentRevision.incident_id)
        .subquery()
    )
    rows = session.scalars(
        select(IncidentRevision).join(
            sub, and_(sub.c.incident_id == IncidentRevision.incident_id, sub.c.rev == IncidentRevision.revision)
        )
    ).all()
    return {r.incident_id: r for r in rows}


def revision_dict(r: IncidentRevision) -> dict[str, Any]:
    return dict(
        revision=r.revision,
        extent_start_at=r.extent_start_at,
        extent_end_at=r.extent_end_at,
        extent_open=r.extent_open,
        direction=r.direction,
        observed_duration_s=r.observed_duration_s,
        observed_duration_min=_minutes(r.observed_duration_s),
        bracketing_span_s=r.bracketing_span_s,
        bracketing_span_min=_minutes(r.bracketing_span_s),
        gap_status=r.gap_status,
        peak_c=r.peak_c,
        confirmed_event_at=r.confirmed_event_at,
        evidence_received_at=r.evidence_received_at,
        gap_continuity_warning=r.gap_continuity_warning,
        basis=r.basis,
        merged_into_incident_id=r.merged_into_incident_id,
        incident_status_at_revision=r.incident_status_at_revision,
        evaluation_id=r.evaluation_id,
        raised_at=r.raised_at,
    )


def incident_item(
    inc: Incident, latest: IncidentRevision | None, policy: Policy | None, data_origin: str | None
) -> dict[str, Any]:
    return dict(
        incident_id=inc.incident_id,
        business_ref=inc.business_ref,
        shipment_id=inc.shipment_id,
        sensor_id=inc.sensor_id,
        category=inc.category,
        status=inc.status,
        opened_at=inc.opened_at,
        closed_at=inc.closed_at,
        detected_by=inc.detected_by,
        detector_version=inc.detector_version,
        summary=inc.summary,
        data_origin=data_origin,
        policy_code=policy.policy_code if policy else None,
        policy_version=policy.policy_version if policy else None,
        latest=revision_dict(latest) if latest is not None else None,
        review_state="PENDING_QUALITY_REVIEW" if inc.status == "OPEN" else "CLOSED_BY_QUALITY_DISPOSITION",
    )


def list_incidents(
    session: Session, *, status: str | None, category: str | None, shipment_id: str | None, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(Incident)
    if status:
        stmt = stmt.where(Incident.status == status)
    if category:
        stmt = stmt.where(Incident.category == category)
    if shipment_id:
        stmt = stmt.where(Incident.shipment_id == shipment_id)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.order_by(Incident.opened_at.desc(), Incident.business_ref).limit(limit).offset(offset)
    ).all()
    latest = _latest_revisions(session, [r.incident_id for r in rows])
    policies = {p.policy_id: p for p in session.scalars(select(Policy)).all()}
    origins = (
        dict(
            session.execute(
                select(Shipment.shipment_id, Shipment.data_origin).where(
                    Shipment.shipment_id.in_({r.shipment_id for r in rows})
                )
            ).all()
        )
        if rows
        else {}
    )
    return [
        incident_item(r, latest.get(r.incident_id), policies.get(r.policy_id), origins.get(r.shipment_id)) for r in rows
    ], total


def incident_detail(session: Session, incident_id: uuid.UUID) -> dict[str, Any]:
    from app.core.errors import NotFoundError

    inc = session.get(Incident, incident_id)
    if inc is None:
        raise NotFoundError(f"Incident {incident_id} not found.")
    shipment = session.get(Shipment, inc.shipment_id)
    policy_row = session.get(Policy, inc.policy_id)
    revisions = session.scalars(
        select(IncidentRevision).where(IncidentRevision.incident_id == incident_id).order_by(IncidentRevision.revision)
    ).all()
    latest = revisions[-1] if revisions else None
    config_row = session.get(DetectorConfigVersion, inc.detector_config_id) if inc.detector_config_id else None
    opening = session.get(DetectorEvaluation, inc.opened_by_evaluation_id) if inc.opened_by_evaluation_id else None
    evidence: dict[str, Any] = {"readings": [], "gaps": [], "warnings": []}
    if latest is not None and inc.sensor_id is not None:
        pad = timedelta(minutes=30)
        rows = session.execute(
            select(Reading.event_at, Reading.received_at, Reading.temperature_c, IngestBatch.business_ref)
            .join(IngestBatch, IngestBatch.batch_id == Reading.ingest_batch_id)
            .where(
                Reading.shipment_id == inc.shipment_id,
                Reading.sensor_id == inc.sensor_id,
                Reading.event_at >= latest.extent_start_at - pad,
                Reading.event_at <= latest.extent_end_at + pad,
            )
            .order_by(Reading.event_at)
        ).all()
        rules = PolicyRules.from_row(policy_row) if policy_row else None
        evidence["readings"] = [
            dict(
                event_at=e,
                received_at=r,
                temperature_c=t,
                batch_ref=b,
                delivery_lag_s=seconds(r - e),
                temperature_state=classify(t, rules).value if rules else None,
                inside_extent=latest.extent_start_at <= e <= latest.extent_end_at,
            )
            for e, r, t, b in rows
        ]
        gaps = session.scalars(
            select(DataGap)
            .where(
                DataGap.shipment_id == inc.shipment_id,
                DataGap.sensor_id == inc.sensor_id,
                DataGap.start_at <= latest.extent_end_at + pad,
                DataGap.end_at >= latest.extent_start_at - pad,
            )
            .order_by(DataGap.start_at, DataGap.raised_at)
        ).all()
        evidence["gaps"] = [gap_dict(g, FAR_FUTURE) for g in gaps]
        warns = session.scalars(
            select(DataQualityWarning)
            .where(
                DataQualityWarning.shipment_id == inc.shipment_id,
                DataQualityWarning.sensor_id == inc.sensor_id,
                DataQualityWarning.affects_quality_evidence.is_(True),
                or_(
                    DataQualityWarning.linked_incident_id == incident_id,
                    and_(
                        DataQualityWarning.interval_start_at <= latest.extent_end_at + pad,
                        DataQualityWarning.interval_end_at >= latest.extent_start_at - pad,
                    ),
                ),
            )
            .order_by(DataQualityWarning.interval_start_at, DataQualityWarning.raised_at)
        ).all()
        evidence["warnings"] = [warning_dict(w, FAR_FUTURE) for w in warns]
    dispositions = session.scalars(
        select(Disposition)
        .join(DispositionIncident, DispositionIncident.disposition_id == Disposition.disposition_id)
        .where(DispositionIncident.incident_id == incident_id)
    ).all()
    reassess = session.scalars(
        select(DecisionReassessment)
        .where(DecisionReassessment.incident_id == incident_id)
        .order_by(DecisionReassessment.raised_at)
    ).all()
    detail = incident_item(inc, latest, policy_row, shipment.data_origin if shipment else None)
    detail.update(
        revisions=[revision_dict(r) for r in revisions],
        evidence=evidence,
        policy=policy_ref(PolicyRules.from_row(policy_row)) if policy_row else None,
        detector_config=dict(
            detector_config_id=config_row.detector_config_id,
            detector_code=config_row.detector_code,
            config_version=config_row.config_version,
            content_sha256=config_row.content_sha256,
            nominal_sampling_interval_s=config_row.nominal_sampling_interval_s,
            max_continuous_interval_s=config_row.max_continuous_interval_s,
        )
        if config_row
        else None,
        opening_evaluation=dict(
            evaluation_id=opening.evaluation_id,
            mode=opening.mode,
            trigger=opening.trigger,
            as_of=opening.as_of,
            input_fingerprint=opening.input_fingerprint,
            detector_code_version=opening.detector_code_version,
            visible_reading_count=opening.visible_reading_count,
        )
        if opening
        else None,
        dispositions=[
            dict(
                disposition_id=d.disposition_id,
                business_ref=d.business_ref,
                decision=d.decision,
                decided_at=d.decided_at,
            )
            for d in dispositions
        ],
        reassessments=[
            dict(
                reassessment_id=r.reassessment_id,
                disposition_id=r.disposition_id,
                reason=r.reason,
                incident_revision_id=r.incident_revision_id,
                warehouse_release_id=r.warehouse_release_id,
                raised_at=r.raised_at,
            )
            for r in reassess
        ],
    )
    return detail


# ------------------------------------------------------------------ summary


def monitoring_summary(session: Session, as_of: datetime) -> dict[str, Any]:
    states: Counter[str] = Counter()
    policies: dict[uuid.UUID, PolicyRules] = {}
    try:
        config = active_detector_config(session)
    except Exception:  # not seeded: report honestly
        config = None
    newest = {
        (s, sen): (e)
        for s, sen, e in session.execute(
            select(Reading.shipment_id, Reading.sensor_id, func.max(Reading.event_at))
            .where(Reading.received_at <= as_of)
            .group_by(Reading.shipment_id, Reading.sensor_id)
        ).all()
    }
    assignments: dict[tuple[str, str], list[tuple[datetime, datetime | None]]] = defaultdict(list)
    for sid, sen, a, b in session.execute(
        select(
            SensorAssignment.shipment_id,
            SensorAssignment.sensor_id,
            SensorAssignment.assigned_from,
            SensorAssignment.assigned_to,
        )
    ).all():
        assignments[(sid, sen)].append((a, b))
    shipments = dict(session.execute(select(Shipment.shipment_id, Shipment.policy_id)).all())
    if config is not None:
        for (sid, sen), wins in assignments.items():
            pid = shipments.get(sid)
            if pid is None:
                continue
            if pid not in policies:
                row = session.get(Policy, pid)
                if row is None:
                    continue
                policies[pid] = PolicyRules.from_row(row)
            start = min(w[0] for w in wins)
            end = None if any(w[1] is None for w in wins) else max(w[1] for w in wins)  # type: ignore[type-var]
            st = monitoring_state(
                newest_event_at=newest.get((sid, sen)),
                assigned_from=start,
                assigned_to=end,
                as_of=as_of,
                policy=policies[pid],
                config=config,
            )
            states[st.state.value] += 1
    open_by_cat = dict(
        session.execute(
            select(Incident.category, func.count()).where(Incident.status == "OPEN").group_by(Incident.category)
        ).all()
    )
    latest_basis = Counter(
        r.basis
        for r in _latest_revisions(
            session, list(session.scalars(select(Incident.incident_id).where(Incident.status == "OPEN")).all())
        ).values()
    )
    warnings = dict(
        session.execute(
            select(DataQualityWarning.kind, func.count())
            .where(visible_at(DataQualityWarning, as_of))
            .group_by(DataQualityWarning.kind)
        ).all()
    )
    evidence_warnings = session.scalar(
        select(func.count())
        .select_from(DataQualityWarning)
        .where(
            visible_at(DataQualityWarning, as_of),
            DataQualityWarning.kind.in_([k.value for k in EVIDENCE_WARNING_KINDS]),
        )
    )
    evaluated = session.scalar(select(func.count(func.distinct(DetectorEvaluation.shipment_id)))) or 0
    totals = session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(IngestBatch.rejected_count), 0),
            func.coalesce(func.sum(IngestBatch.duplicate_count), 0),
        ).select_from(IngestBatch)
    ).one()
    return dict(
        as_of=as_of,
        shipments_total=len(shipments),
        shipments_evaluated=evaluated,
        sensors_by_monitoring_state={k: states.get(k, 0) for k in [s.value for s in MonitoringStateName]},
        open_incidents_by_category={
            k: int(open_by_cat.get(k, 0)) for k in ("TEMPERATURE_EXCURSION", "DATA_GAP", "SENSOR_FAULT_SUSPECTED")
        },
        open_incidents_by_basis={k: latest_basis.get(k, 0) for k in ("CURRENT", "SUPERSEDED_BY_DATA", "MERGED_INTO")},
        current_warnings_by_kind={str(k): int(v) for k, v in warnings.items()},
        current_evidence_warnings=int(evidence_warnings or 0),
        batches_total=int(totals[0]),
        rejected_records_total=int(totals[1]),
        duplicates_ignored_total=int(totals[2]),
        readings_total=int(session.scalar(select(func.count()).select_from(Reading)) or 0),
        detector_config=config_ref(config) if config else None,
    )
