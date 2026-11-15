"""Run the policy-baseline detector and store its results (append-only).

One code path for every mode (contract §5.4):

* live ingestion: ``evaluate_sensor(..., as_of=server time, mode=LIVE)`` after each batch;
* trusted replay of recorded data: ``replay_shipment`` walks the recorded ``received_at``
  timeline and the documented monitoring boundaries, evaluating causally at each step;
* the ocean demo feeds batches through ingestion in REPLAY mode.

Operational detection reads only observed tables (``reading``, ``sensor_assignment``,
``ingest_batch``), the shipment's policy and the detector configuration. It never reads
simulator labels (D-12; enforced by ``tests/test_ground_truth_boundary.py``).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Table, func, select, update
from sqlalchemy.orm import Session, aliased

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
    WarehouseRelease,
)
from app.db.models.enums import (
    DetectionSource,
    EvaluationMode,
    EvaluationTrigger,
    IncidentCategory,
    ReassessmentReason,
    TemperatureDirection,
)
from app.domain.detector import Gap, GapBound, GapStatus, Obs, Run, TempClass, seconds
from app.domain.reconcile import (
    DETECTOR_WARNING_KINDS,
    Changes,
    GapRecord,
    IncidentBasis,
    IncidentCategoryName,
    IncidentRecord,
    IncidentValues,
    RunRecord,
    SensorState,
    WarningKind,
    WarningRecord,
    WarningSpec,
    stable_id,
)
from app.domain.replay import Outcome, SensorEvaluator, StepKind, build_timeline
from app.domain.rules import DETECTOR_CODE_VERSION, DetectorConfig, PolicyRules, parse_detector_config
from app.domain.validation import Window

ACTIVE_DETECTOR_CONFIG = ("DET-BASELINE", "1.0.0")


class DetectionSetupError(RuntimeError):
    """Policy or detector configuration cannot be resolved; nothing is evaluated (contract §5.2)."""


def _td(value: Decimal) -> timedelta:
    return timedelta(microseconds=int(value * 1_000_000))


# ------------------------------------------------------------------ versions and windows


def policy_rules_for(session: Session, shipment: Shipment) -> PolicyRules:
    """The shipment's own policy version, never "whatever is active now" (contract §5.2)."""
    policy = session.get(Policy, shipment.policy_id)
    if policy is None:
        raise DetectionSetupError(f"shipment {shipment.shipment_id}: policy {shipment.policy_id} not found")
    return PolicyRules.from_row(policy)


def active_detector_config(session: Session) -> DetectorConfig:
    code, version = ACTIVE_DETECTOR_CONFIG
    row = session.scalar(
        select(DetectorConfigVersion).where(
            DetectorConfigVersion.detector_code == code, DetectorConfigVersion.config_version == version
        )
    )
    if row is None:
        raise DetectionSetupError(f"detector configuration {code} v{version} is not seeded (run python -m app.seed)")
    return parse_detector_config(row.document, row.content_sha256, row.detector_config_id)


def monitoring_windows(session: Session, shipment_id: str) -> dict[str, list[Window]]:
    rows = session.execute(
        select(SensorAssignment.sensor_id, SensorAssignment.assigned_from, SensorAssignment.assigned_to).where(
            SensorAssignment.shipment_id == shipment_id
        )
    ).all()
    out: dict[str, list[Window]] = defaultdict(list)
    for sensor_id, start, end in rows:
        out[sensor_id].append(Window(start, end))
    return dict(out)


def boundaries(windows: list[Window]) -> tuple[datetime | None, datetime | None]:
    """Documented monitoring start and end of one sensor on one shipment (C-04)."""
    if not windows:
        return None, None
    start = min(w.assigned_from for w in windows)
    end = None if any(w.assigned_to is None for w in windows) else max(w.assigned_to for w in windows)  # type: ignore[type-var]
    return start, end


def load_observations(session: Session, shipment_id: str, sensor_id: str, as_of: datetime | None = None) -> list[Obs]:
    stmt = select(Reading.event_at, Reading.temperature_c, Reading.received_at).where(
        Reading.shipment_id == shipment_id, Reading.sensor_id == sensor_id
    )
    if as_of is not None:
        stmt = stmt.where(Reading.received_at <= as_of)
    return [Obs(e, t, r) for e, t, r in session.execute(stmt.order_by(Reading.event_at)).all()]


# ------------------------------------------------------------------ current state from the database


def load_state(session: Session, shipment_id: str, sensor_id: str) -> SensorState:
    state = SensorState()
    for g in session.scalars(
        select(DataGap).where(
            DataGap.shipment_id == shipment_id, DataGap.sensor_id == sensor_id, DataGap.superseded_at.is_(None)
        )
    ):
        gap = Gap(
            g.start_at,
            g.end_at,
            GapBound(g.start_bound),
            GapBound(g.end_bound),
            _td(g.bracketing_span_s),
            g.estimated_missing_samples,
            timedelta(seconds=g.estimated_missing_duration_s),
            GapStatus(g.gap_status),
            g.out_of_range_before,
            g.out_of_range_after,
        )
        state.gaps[g.gap_key] = GapRecord(g.gap_revision_id, g.gap_key, gap)
    for d in session.scalars(
        select(Detection).where(
            Detection.shipment_id == shipment_id, Detection.sensor_id == sensor_id, Detection.superseded_at.is_(None)
        )
    ):
        run = Run(
            TempClass(d.direction),
            d.first_event_at,
            d.last_event_at,
            d.reading_count,
            _td(d.observed_duration_s),
            timedelta(minutes=d.threshold_min),
            d.meets_policy_duration,
            d.confirmed_event_at,
            d.evidence_received_at,
            d.peak_c,
            d.run_open,
            d.preceded_by_gap_key,
            d.followed_by_gap_key,
        )
        state.runs[d.run_key] = RunRecord(d.detection_id, d.run_key, run)
    linked = aliased(Incident)
    for w, ref in session.execute(
        select(DataQualityWarning, linked.business_ref)
        .outerjoin(linked, linked.incident_id == DataQualityWarning.linked_incident_id)
        .where(
            DataQualityWarning.shipment_id == shipment_id,
            DataQualityWarning.sensor_id == sensor_id,
            DataQualityWarning.superseded_at.is_(None),
            DataQualityWarning.kind.in_([k.value for k in DETECTOR_WARNING_KINDS]),
        )
    ).all():
        spec = WarningSpec(
            w.warning_key,
            WarningKind(w.kind),
            w.affects_quality_evidence,
            w.run_key,
            w.gap_key,
            w.interval_start_at,
            w.interval_end_at,
            ref,
            w.message,
        )
        state.warnings[w.warning_key] = WarningRecord(w.warning_revision_id, spec)
    target = aliased(Incident)
    latest = (
        select(IncidentRevision.incident_id, func.max(IncidentRevision.revision).label("revision"))
        .group_by(IncidentRevision.incident_id)
        .subquery()
    )
    for inc, rev, merged_ref in session.execute(
        select(Incident, IncidentRevision, target.business_ref)
        .join(latest, latest.c.incident_id == Incident.incident_id)
        .join(
            IncidentRevision,
            (IncidentRevision.incident_id == latest.c.incident_id) & (IncidentRevision.revision == latest.c.revision),
        )
        .outerjoin(target, target.incident_id == IncidentRevision.merged_into_incident_id)
        .where(Incident.shipment_id == shipment_id, Incident.sensor_id == sensor_id)
    ).all():
        values = IncidentValues(
            rev.extent_start_at,
            rev.extent_end_at,
            rev.extent_open,
            TempClass(rev.direction) if rev.direction else None,
            _td(rev.observed_duration_s) if rev.observed_duration_s is not None else None,
            _td(rev.bracketing_span_s) if rev.bracketing_span_s is not None else None,
            GapStatus(rev.gap_status) if rev.gap_status else None,
            rev.peak_c,
            rev.confirmed_event_at,
            rev.evidence_received_at,
            rev.gap_continuity_warning,
            IncidentBasis(rev.basis),
            merged_ref,
            rev.basis_key,
        )
        state.incidents[inc.business_ref] = IncidentRecord(
            inc.incident_id,
            inc.business_ref,
            IncidentCategoryName(inc.category),
            str(inc.status),
            inc.opened_at,
            rev.revision,
            values,
        )
    last = session.scalar(
        select(DetectorEvaluation.input_fingerprint)
        .where(DetectorEvaluation.shipment_id == shipment_id, DetectorEvaluation.sensor_id == sensor_id)
        .order_by(DetectorEvaluation.as_of.desc(), DetectorEvaluation.created_at.desc())
        .limit(1)
    )
    state.last_fingerprint = last
    return state


# ------------------------------------------------------------------ persistence


@dataclass
class EvaluationSummary:
    evaluation_id: uuid.UUID
    as_of: datetime
    trigger: str
    gaps_confirmed: int = 0
    runs_changed: int = 0
    warnings_raised: int = 0
    incidents_opened: list[str] = field(default_factory=list)
    incidents_revised: list[str] = field(default_factory=list)
    reassessments_flagged: int = 0


class _Writer:
    """Buffers rows of one or many evaluations and writes them in foreign-key order."""

    ORDER = (
        DetectorEvaluation,
        DataGap,
        Detection,
        Incident,
        IncidentRevision,
        DataQualityWarning,
        DecisionReassessment,
    )

    def __init__(self) -> None:
        self.rows: dict[type, dict[uuid.UUID, dict[str, Any]]] = {m: {} for m in self.ORDER}
        self.supersede: dict[type, list[tuple[uuid.UUID, uuid.UUID, datetime]]] = defaultdict(list)

    def add(self, model: type, pk: uuid.UUID, row: dict[str, Any]) -> None:
        self.rows[model][pk] = row

    def mark_superseded(self, model: type, pk: uuid.UUID, evaluation_id: uuid.UUID, at: datetime) -> None:
        pending = self.rows[model].get(pk)
        if pending is not None:
            pending["superseded_by_evaluation_id"], pending["superseded_at"] = evaluation_id, at
        else:
            self.supersede[model].append((pk, evaluation_id, at))

    def flush(self, session: Session) -> None:
        for model in self.ORDER:
            rows = list(self.rows[model].values())
            table: Table = model.__table__  # type: ignore[attr-defined]
            for i in range(0, len(rows), 2000):
                session.execute(table.insert(), rows[i : i + 2000])
        for model, items in self.supersede.items():
            pk_col = next(iter(model.__table__.primary_key.columns))  # type: ignore[attr-defined]
            for pk, ev, at in items:
                session.execute(
                    update(model)
                    .where(pk_col == pk, model.superseded_at.is_(None))  # type: ignore[attr-defined]
                    .values(superseded_by_evaluation_id=ev, superseded_at=at)
                )
        session.flush()
        self.__init__()  # type: ignore[misc]


def _record_outcome(
    writer: _Writer,
    session: Session,
    outcome: Outcome,
    *,
    shipment_id: str,
    sensor_id: str,
    mode: EvaluationMode,
    trigger_batch_id: uuid.UUID | None,
    policy: PolicyRules,
    config: DetectorConfig,
    start: datetime | None,
    end: datetime | None,
    closed_lookup: bool,
) -> EvaluationSummary:
    ev, at, ch = outcome.evaluation_id, outcome.as_of, outcome.changes
    summary = EvaluationSummary(ev, at, outcome.trigger)
    writer.add(
        DetectorEvaluation,
        ev,
        dict(
            evaluation_id=ev,
            shipment_id=shipment_id,
            sensor_id=sensor_id,
            mode=mode.value,
            trigger=outcome.trigger,
            trigger_batch_id=trigger_batch_id,
            as_of=at,
            affected_from_at=outcome.affected_from_at,
            affected_to_at=outcome.affected_to_at,
            visible_reading_count=outcome.visible_reading_count,
            input_fingerprint=outcome.fingerprint,
            policy_id=policy.policy_id,
            detector_config_id=config.detector_config_id,
            detector_code_version=DETECTOR_CODE_VERSION,
            start_boundary_at=start if start is not None and at >= start else None,
            end_boundary_at=end if end is not None and at >= end else None,
        ),
    )
    _write_changes(writer, ch, ev, at, shipment_id, sensor_id)
    for pk in ch.superseded_gaps:
        writer.mark_superseded(DataGap, pk, ev, at)
    for pk in ch.superseded_runs:
        writer.mark_superseded(Detection, pk, ev, at)
    for pk in ch.superseded_warnings:
        writer.mark_superseded(DataQualityWarning, pk, ev, at)
    summary.gaps_confirmed = len(ch.new_gaps)
    summary.runs_changed = len(ch.new_runs)
    summary.warnings_raised = len(ch.new_warnings)

    for change in ch.incident_changes:
        rec, v = change.record, change.record.values
        is_tex = rec.category == IncidentCategoryName.TEMPERATURE_EXCURSION
        if change.opened:
            summary.incidents_opened.append(rec.business_ref)
            writer.add(
                Incident,
                rec.incident_id,
                dict(
                    incident_id=rec.incident_id,
                    business_ref=rec.business_ref,
                    shipment_id=shipment_id,
                    category=rec.category.value,
                    status="OPEN",
                    interval_start=v.extent_start_at,
                    interval_end=None if v.extent_open else v.extent_end_at,
                    detected_by=(DetectionSource.POLICY_BASELINE if is_tex else DetectionSource.GAP_DETECTOR).value,
                    detector_version=config.label,
                    policy_id=policy.policy_id,
                    sensor_id=sensor_id,
                    detector_config_id=config.detector_config_id,
                    opened_by_evaluation_id=ev,
                    summary=_incident_summary(rec, policy),
                    opened_at=at,
                ),
            )
        else:
            summary.incidents_revised.append(rec.business_ref)
        writer.add(
            IncidentRevision,
            change.revision_id,
            dict(
                incident_revision_id=change.revision_id,
                incident_id=rec.incident_id,
                revision=rec.revision,
                extent_start_at=v.extent_start_at,
                extent_end_at=v.extent_end_at,
                extent_open=v.extent_open,
                direction=v.direction.value if v.direction else None,
                observed_duration_s=seconds(v.observed_duration) if v.observed_duration is not None else None,
                bracketing_span_s=seconds(v.bracketing_span) if v.bracketing_span is not None else None,
                gap_status=v.gap_status.value if v.gap_status else None,
                peak_c=v.peak_c,
                confirmed_event_at=v.confirmed_event_at,
                evidence_received_at=v.evidence_received_at,
                gap_continuity_warning=v.gap_continuity_warning,
                basis=v.basis.value,
                merged_into_incident_id=stable_id("incident", v.merged_into_ref) if v.merged_into_ref else None,
                basis_key=v.basis_key,
                detection_id=change.basis_row_id if is_tex else None,
                gap_revision_id=change.basis_row_id if not is_tex else None,
                incident_status_at_revision=rec.status,
                evaluation_id=ev,
                raised_at=at,
            ),
        )
        if closed_lookup:
            summary.reassessments_flagged += _flag_reassessments(
                writer,
                session,
                shipment_id,
                change.record,
                change.revision_id,
                change.opened,
                change.was_closed,
                ev,
                at,
            )
    return summary


def _write_changes(writer: _Writer, ch: Changes, ev: uuid.UUID, at: datetime, shipment_id: str, sensor_id: str) -> None:
    for g in ch.new_gaps:
        gap = g.gap
        writer.add(
            DataGap,
            g.row_id,
            dict(
                gap_revision_id=g.row_id,
                gap_key=g.key,
                shipment_id=shipment_id,
                sensor_id=sensor_id,
                start_at=gap.start_at,
                end_at=gap.end_at,
                start_bound=gap.start_bound.value,
                end_bound=gap.end_bound.value,
                bracketing_span_s=seconds(gap.bracketing_span),
                estimated_missing_samples=gap.estimated_missing_samples,
                estimated_missing_duration_s=int(gap.estimated_missing_duration.total_seconds()),
                gap_status=gap.status.value,
                out_of_range_before=gap.out_of_range_before,
                out_of_range_after=gap.out_of_range_after,
                evaluation_id=ev,
                raised_at=at,
                superseded_by_evaluation_id=None,
                superseded_at=None,
            ),
        )
    for r in ch.new_runs:
        run = r.run
        writer.add(
            Detection,
            r.row_id,
            dict(
                detection_id=r.row_id,
                run_key=r.key,
                shipment_id=shipment_id,
                sensor_id=sensor_id,
                source=DetectionSource.POLICY_BASELINE.value,
                direction=TemperatureDirection(run.direction.value).value,
                first_event_at=run.first_event_at,
                last_event_at=run.last_event_at,
                reading_count=run.reading_count,
                observed_duration_s=seconds(run.observed_duration),
                threshold_min=int(run.threshold.total_seconds() // 60),
                meets_policy_duration=run.meets_policy_duration,
                confirmed_event_at=run.confirmed_event_at,
                evidence_received_at=run.evidence_received_at,
                peak_c=run.peak_c,
                run_open=run.run_open,
                preceded_by_gap_key=run.preceded_by_gap,
                followed_by_gap_key=run.followed_by_gap,
                evaluation_id=ev,
                raised_at=at,
                superseded_by_evaluation_id=None,
                superseded_at=None,
            ),
        )
    for w in ch.new_warnings:
        s = w.spec
        writer.add(
            DataQualityWarning,
            w.row_id,
            dict(
                warning_revision_id=w.row_id,
                warning_key=s.key,
                kind=s.kind.value,
                affects_quality_evidence=s.affects_quality_evidence,
                shipment_id=shipment_id,
                sensor_id=sensor_id,
                run_key=s.run_key,
                gap_key=s.gap_key,
                interval_start_at=s.interval_start_at,
                interval_end_at=s.interval_end_at,
                linked_incident_id=stable_id("incident", s.linked_incident_ref) if s.linked_incident_ref else None,
                message=s.message,
                details=None,
                evaluation_id=ev,
                ingest_batch_id=None,
                raised_at=at,
                superseded_by_evaluation_id=None,
                superseded_at=None,
            ),
        )


def _incident_summary(rec: IncidentRecord, policy: PolicyRules) -> str:
    v = rec.values
    if rec.category == IncidentCategoryName.TEMPERATURE_EXCURSION:
        side = f"above {policy.max_temp_c} °C" if v.direction == TempClass.HIGH else f"below {policy.min_temp_c} °C"
        threshold = policy.high_min_duration if v.direction == TempClass.HIGH else policy.low_min_duration
        text = (
            f"Observed temperature {side} for at least {int(threshold.total_seconds() // 60)} min "
            f"(policy {policy.policy_code} v{policy.policy_version})."
        )
        if v.gap_continuity_warning:
            text += " Next to a data gap: excursion may have continued during gap."
        return text
    return (
        f"Confirmed missing-data interval of at least {int(policy.gap_review_at.total_seconds() // 60)} min "
        f"(policy {policy.policy_code} v{policy.policy_version}); requires quality review."
    )


def _flag_reassessments(
    writer: _Writer,
    session: Session,
    shipment_id: str,
    rec: IncidentRecord,
    revision_id: uuid.UUID,
    opened: bool,
    was_closed: bool,
    ev: uuid.UUID,
    at: datetime,
) -> int:
    """U-04: never change a disposition or a release; flag the decision for human reassessment."""
    if opened:
        dispositions = session.scalars(
            select(Disposition.disposition_id).where(Disposition.shipment_id == shipment_id)
        ).all()
        reason = ReassessmentReason.NEW_INCIDENT_AFTER_DISPOSITION
    elif was_closed:
        dispositions = session.scalars(
            select(DispositionIncident.disposition_id).where(DispositionIncident.incident_id == rec.incident_id)
        ).all()
        reason = ReassessmentReason.INCIDENT_EVIDENCE_REVISED
    else:
        return 0
    for disposition_id in dispositions:
        release_id = session.scalar(
            select(WarehouseRelease.release_id).where(WarehouseRelease.disposition_id == disposition_id)
        )
        rid = stable_id("reassessment", str(disposition_id), str(revision_id))
        writer.add(
            DecisionReassessment,
            rid,
            dict(
                reassessment_id=rid,
                disposition_id=disposition_id,
                shipment_id=shipment_id,
                incident_id=rec.incident_id,
                incident_revision_id=revision_id,
                reason=reason.value,
                warehouse_release_id=release_id,
                evaluation_id=ev,
                raised_at=at,
            ),
        )
    return len(dispositions)


# ------------------------------------------------------------------ entry points


def _setup(
    session: Session, shipment_id: str, sensor_id: str
) -> tuple[Shipment, PolicyRules, DetectorConfig, datetime | None, datetime | None]:
    shipment = session.get(Shipment, shipment_id)
    if shipment is None:
        raise DetectionSetupError(f"shipment {shipment_id} not found")
    start, end = boundaries(monitoring_windows(session, shipment_id).get(sensor_id, []))
    return shipment, policy_rules_for(session, shipment), active_detector_config(session), start, end


def evaluate_sensor(
    session: Session,
    shipment_id: str,
    sensor_id: str,
    *,
    as_of: datetime,
    mode: EvaluationMode,
    trigger: EvaluationTrigger,
    trigger_batch_id: uuid.UUID | None = None,
) -> EvaluationSummary | None:
    """One causal evaluation at ``as_of`` against the stored current results. ``None`` = no-op."""
    _, policy, config, start, end = _setup(session, shipment_id, sensor_id)
    evaluator = SensorEvaluator(
        shipment_id=shipment_id,
        sensor_id=sensor_id,
        mode=mode.value,
        policy=policy,
        config=config,
        assigned_from=start,
        assigned_to=end,
        state=load_state(session, shipment_id, sensor_id),
    )
    evaluator.add(load_observations(session, shipment_id, sensor_id, as_of))
    outcome = evaluator.evaluate(as_of, trigger.value)
    if outcome is None:
        return None
    writer = _Writer()
    summary = _record_outcome(
        writer,
        session,
        outcome,
        shipment_id=shipment_id,
        sensor_id=sensor_id,
        mode=mode,
        trigger_batch_id=trigger_batch_id,
        policy=policy,
        config=config,
        start=start,
        end=end,
        closed_lookup=True,
    )
    writer.flush(session)
    return summary


@dataclass
class ReplaySummary:
    shipment_id: str
    sensor_id: str
    status: str  # "replayed" | "already_evaluated"
    evaluations: int = 0
    incidents_opened: int = 0
    incident_revisions: int = 0


def replay_shipment(session: Session, shipment_id: str) -> list[ReplaySummary]:
    """Causal replay of stored readings along the recorded ``received_at`` timeline (C-09).

    Runs once per sensor: a sensor that already has evaluations is left as it is (repeating
    a replay would change nothing but would re-walk history). Does not commit.
    """
    out = []
    for sensor_id in sorted(monitoring_windows(session, shipment_id)):
        if session.scalar(
            select(DetectorEvaluation.evaluation_id)
            .where(DetectorEvaluation.shipment_id == shipment_id, DetectorEvaluation.sensor_id == sensor_id)
            .limit(1)
        ):
            out.append(ReplaySummary(shipment_id, sensor_id, "already_evaluated"))
            continue
        _, policy, config, start, end = _setup(session, shipment_id, sensor_id)
        batches = session.execute(
            select(IngestBatch.received_at, IngestBatch.business_ref, IngestBatch.batch_id).where(
                IngestBatch.batch_id.in_(
                    select(Reading.ingest_batch_id).where(
                        Reading.shipment_id == shipment_id, Reading.sensor_id == sensor_id
                    )
                )
            )
        ).all()
        batch_ids = {ref: bid for _, ref, bid in batches}
        evaluator = SensorEvaluator(
            shipment_id=shipment_id,
            sensor_id=sensor_id,
            mode=EvaluationMode.REPLAY.value,
            policy=policy,
            config=config,
            assigned_from=start,
            assigned_to=end,
        )
        evaluator.add(load_observations(session, shipment_id, sensor_id))
        writer = _Writer()
        summary = ReplaySummary(shipment_id, sensor_id, "replayed")
        has_decisions = (
            session.scalar(select(Disposition.disposition_id).where(Disposition.shipment_id == shipment_id).limit(1))
            is not None
        )
        for step in build_timeline(start, end, [(at, ref) for at, ref, _ in batches]):
            trigger = {
                StepKind.BATCH: EvaluationTrigger.BATCH,
                StepKind.MONITORING_START: EvaluationTrigger.MONITORING_START,
                StepKind.MONITORING_END: EvaluationTrigger.MONITORING_END,
            }[step.kind]
            outcome = evaluator.evaluate(step.at, trigger.value)
            if outcome is None:
                continue
            res = _record_outcome(
                writer,
                session,
                outcome,
                shipment_id=shipment_id,
                sensor_id=sensor_id,
                mode=EvaluationMode.REPLAY,
                trigger_batch_id=batch_ids.get(step.batch_ref or ""),
                policy=policy,
                config=config,
                start=start,
                end=end,
                closed_lookup=has_decisions,
            )
            summary.evaluations += 1
            summary.incidents_opened += len(res.incidents_opened)
            summary.incident_revisions += len(res.incidents_opened) + len(res.incidents_revised)
        writer.flush(session)
        out.append(summary)
    return out


def incident_category(name: IncidentCategoryName) -> IncidentCategory:
    return IncidentCategory(name.value)
