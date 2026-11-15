"""Turn a detector snapshot into append-only revisions and incident actions (pure).

Specification: contract §5.10 to §5.12. Rules:

* Results are compared with the current ones. Unchanged results produce nothing; changed
  ones produce a new revision and the old one is marked superseded. Nothing is deleted.
* Gap identity = opening bound. Run identity = same direction and overlapping
  ``[first, last]`` with a current run (the earliest one wins on a merge).
* ``TEMPERATURE_EXCURSION`` incidents follow qualifying runs, ``DATA_GAP`` incidents follow
  confirmed gaps with status ``UNKNOWN_REVIEW_REQUIRED`` (C-02). An incident whose basis
  disappears gets ``basis = SUPERSEDED_BY_DATA``; merged incidents get ``MERGED_INTO``.
  The incident ``status`` is never touched here: only a quality disposition closes an
  incident (BR-09, C-08).
* Identifiers are UUIDv5 values of stable keys, so the same inputs always give the same rows.
"""

import hashlib
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from app.domain.detector import Gap, GapStatus, Run, Snapshot, TempClass, seconds

ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:coldchain:detector")


class IncidentCategoryName(StrEnum):
    TEMPERATURE_EXCURSION = "TEMPERATURE_EXCURSION"
    DATA_GAP = "DATA_GAP"


class IncidentBasis(StrEnum):
    CURRENT = "CURRENT"
    SUPERSEDED_BY_DATA = "SUPERSEDED_BY_DATA"
    MERGED_INTO = "MERGED_INTO"


class WarningKind(StrEnum):
    GAP_ADJACENT_OUT_OF_RANGE = "GAP_ADJACENT_OUT_OF_RANGE"  # BR-05 point 10
    MISSING_READINGS = "MISSING_READINGS"  # one per confirmed gap
    READING_CONFLICT = "READING_CONFLICT"  # BR-07 (ingestion)
    CONTEXT_CONFLICT = "CONTEXT_CONFLICT"  # BR-07 on context records (U-05)


DETECTOR_WARNING_KINDS = (WarningKind.GAP_ADJACENT_OUT_OF_RANGE, WarningKind.MISSING_READINGS)

# C-03: which warnings belong in the Quality Officer's evidence package.
EVIDENCE_WARNING_KINDS = frozenset({WarningKind.GAP_ADJACENT_OUT_OF_RANGE, WarningKind.READING_CONFLICT})


def stable_id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(ID_NAMESPACE, "|".join(parts))


# ------------------------------------------------------------------ state records


@dataclass(frozen=True, slots=True)
class GapRecord:
    row_id: uuid.UUID
    key: str
    gap: Gap


@dataclass(frozen=True, slots=True)
class RunRecord:
    row_id: uuid.UUID
    key: str
    run: Run


@dataclass(frozen=True, slots=True)
class WarningSpec:
    key: str
    kind: WarningKind
    affects_quality_evidence: bool
    run_key: str | None
    gap_key: str | None
    interval_start_at: datetime
    interval_end_at: datetime
    linked_incident_ref: str | None
    message: str


@dataclass(frozen=True, slots=True)
class WarningRecord:
    row_id: uuid.UUID
    spec: WarningSpec


@dataclass(frozen=True, slots=True)
class IncidentValues:
    extent_start_at: datetime
    extent_end_at: datetime
    extent_open: bool
    direction: TempClass | None
    observed_duration: timedelta | None
    bracketing_span: timedelta | None
    gap_status: GapStatus | None
    peak_c: Decimal | None
    confirmed_event_at: datetime | None
    evidence_received_at: datetime | None
    gap_continuity_warning: bool
    basis: IncidentBasis
    merged_into_ref: str | None
    basis_key: str


@dataclass(frozen=True, slots=True)
class IncidentRecord:
    incident_id: uuid.UUID
    business_ref: str
    category: IncidentCategoryName
    status: str  # OPEN | CLOSED (read only here)
    opened_at: datetime
    revision: int
    values: IncidentValues


@dataclass
class SensorState:
    gaps: dict[str, GapRecord] = field(default_factory=dict)
    runs: dict[str, RunRecord] = field(default_factory=dict)
    warnings: dict[str, WarningRecord] = field(default_factory=dict)
    incidents: dict[str, IncidentRecord] = field(default_factory=dict)
    last_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class IncidentRevisionChange:
    revision_id: uuid.UUID
    record: IncidentRecord  # state after the change (record.revision is the new number)
    opened: bool  # True for revision 1 of a new incident
    was_closed: bool  # the incident was CLOSED by a disposition before this revision (U-04)
    basis_row_id: uuid.UUID | None


@dataclass
class Changes:
    new_gaps: list[GapRecord] = field(default_factory=list)
    superseded_gaps: list[uuid.UUID] = field(default_factory=list)
    new_runs: list[RunRecord] = field(default_factory=list)
    superseded_runs: list[uuid.UUID] = field(default_factory=list)
    new_warnings: list[WarningRecord] = field(default_factory=list)
    superseded_warnings: list[uuid.UUID] = field(default_factory=list)
    incident_changes: list[IncidentRevisionChange] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (
            self.new_gaps
            or self.superseded_gaps
            or self.new_runs
            or self.superseded_runs
            or self.new_warnings
            or self.superseded_warnings
            or self.incident_changes
        )


# ------------------------------------------------------------------ helpers


def _closed_overlap(a1: datetime, a2: datetime, b1: datetime, b2: datetime) -> bool:
    return a1 <= b2 and b1 <= a2


def _open_overlap(a1: datetime, a2: datetime, b1: datetime, b2: datetime) -> bool:
    return a1 < b2 and b1 < a2


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S") + (f"{value.microsecond:06d}" if value.microsecond else "") + "Z"


def incident_business_ref(
    shipment_id: str, sensor_id: str, category: IncidentCategoryName, direction: TempClass | None, start: datetime
) -> str:
    kind = (
        "TEX-" + ("H" if direction == TempClass.HIGH else "L")
        if category == IncidentCategoryName.TEMPERATURE_EXCURSION
        else "GAP"
    )
    ref = f"INC-{shipment_id}-{sensor_id}-{kind}-{_stamp(start)}"
    if len(ref) > 120:  # column limit; keep it deterministic
        ref = "INC-" + hashlib.sha256(ref.encode()).hexdigest()[:40]
    return ref


def _fmt_min(value: timedelta) -> str:
    return f"{seconds(value) / 60:.2f}".rstrip("0").rstrip(".")


# ------------------------------------------------------------------ reconciliation


def reconcile(
    state: SensorState,
    snapshot: Snapshot,
    *,
    shipment_id: str,
    sensor_id: str,
    evaluation_id: uuid.UUID,
    as_of: datetime,
) -> Changes:
    """Compare ``snapshot`` with ``state``; mutate ``state`` to the new current results."""
    ch = Changes()
    ev = str(evaluation_id)

    # ---- gaps (identity = opening bound)
    new_gaps: dict[str, GapRecord] = {}
    for gap in snapshot.gaps:
        old = state.gaps.get(gap.key)
        if old is not None and old.gap == gap:
            new_gaps[gap.key] = old
            continue
        rec = GapRecord(stable_id("gap", shipment_id, sensor_id, gap.key, ev), gap.key, gap)
        new_gaps[gap.key] = rec
        ch.new_gaps.append(rec)
        if old is not None:
            ch.superseded_gaps.append(old.row_id)
    ch.superseded_gaps += [old.row_id for key, old in state.gaps.items() if key not in new_gaps]
    state.gaps = new_gaps

    # ---- runs (identity = overlap, earliest current run wins)
    new_runs: dict[str, RunRecord] = {}
    claimed: set[str] = set()
    previous = sorted(state.runs.values(), key=lambda r: (r.run.first_event_at, r.key))
    for run in sorted(snapshot.runs, key=lambda r: r.first_event_at):
        match = next(
            (
                p
                for p in previous
                if p.key not in claimed
                and p.run.direction == run.direction
                and _closed_overlap(p.run.first_event_at, p.run.last_event_at, run.first_event_at, run.last_event_at)
            ),
            None,
        )
        if match is not None:
            claimed.add(match.key)
            key = match.key
            if match.run == run:
                new_runs[key] = match
                continue
            ch.superseded_runs.append(match.row_id)
        else:
            key = f"{run.direction}|{run.first_event_at.isoformat()}"
            n = 2
            while key in new_runs or (key in state.runs and key not in claimed):
                key = f"{run.direction}|{run.first_event_at.isoformat()}#{n}"
                n += 1
        rec = RunRecord(stable_id("run", shipment_id, sensor_id, key, ev), key, run)
        new_runs[key] = rec
        ch.new_runs.append(rec)
    ch.superseded_runs += [p.row_id for p in previous if p.key not in claimed]
    state.runs = new_runs

    # ---- incidents
    gap_incident: dict[str, str] = {}
    _reconcile_incidents(
        state,
        ch,
        shipment_id,
        sensor_id,
        ev,
        as_of,
        IncidentCategoryName.TEMPERATURE_EXCURSION,
        [
            (r.key, r.run.first_event_at, r.run.last_event_at, _tex_values(r))
            for r in new_runs.values()
            if r.run.meets_policy_duration
        ],
        closed_overlap=True,
        basis_rows={k: r.row_id for k, r in new_runs.items()},
    )
    _reconcile_incidents(
        state,
        ch,
        shipment_id,
        sensor_id,
        ev,
        as_of,
        IncidentCategoryName.DATA_GAP,
        [
            (g.key, g.gap.start_at, g.gap.end_at, _gap_values(g))
            for g in new_gaps.values()
            if g.gap.status == GapStatus.UNKNOWN_REVIEW_REQUIRED
        ],
        closed_overlap=False,
        basis_rows={k: g.row_id for k, g in new_gaps.items()},
    )
    for inc in state.incidents.values():
        if inc.category == IncidentCategoryName.DATA_GAP and inc.values.basis == IncidentBasis.CURRENT:
            gap_incident[inc.values.basis_key] = inc.business_ref

    # ---- detector warnings (C-03)
    specs: dict[str, WarningSpec] = {}
    for rec in new_runs.values():
        run = rec.run
        if run.meets_policy_duration:
            continue
        for gkey in run.adjacent_gaps():
            key = f"{WarningKind.GAP_ADJACENT_OUT_OF_RANGE}|{rec.key}|{gkey}"
            specs[key] = WarningSpec(
                key=key,
                kind=WarningKind.GAP_ADJACENT_OUT_OF_RANGE,
                affects_quality_evidence=True,
                run_key=rec.key,
                gap_key=gkey,
                interval_start_at=run.first_event_at,
                interval_end_at=run.last_event_at,
                linked_incident_ref=gap_incident.get(gkey),
                message=(
                    f"{run.reading_count} reading(s) {'above' if run.direction == TempClass.HIGH else 'below'} "
                    f"the policy limit next to a data gap, observed for {_fmt_min(run.observed_duration)} min "
                    f"(policy needs {_fmt_min(run.threshold)} min). Exposure during the gap is unknown; "
                    "no excursion is confirmed from unobserved time."
                ),
            )
    for grec in new_gaps.values():
        gap = grec.gap
        key = f"{WarningKind.MISSING_READINGS}|{grec.key}"
        specs[key] = WarningSpec(
            key=key,
            kind=WarningKind.MISSING_READINGS,
            affects_quality_evidence=gap.status != GapStatus.SHORT_GAP,
            run_key=None,
            gap_key=grec.key,
            interval_start_at=gap.start_at,
            interval_end_at=gap.end_at,
            linked_incident_ref=gap_incident.get(grec.key),
            message=(
                f"No readings for a bracketing span of {_fmt_min(gap.bracketing_span)} min "
                f"(about {gap.estimated_missing_samples} scheduled sample(s) missing); status {gap.status}. "
                "This time is never counted as in range."
            ),
        )
    new_warnings: dict[str, WarningRecord] = {}
    for key, spec in specs.items():
        old = state.warnings.get(key)
        if old is not None and old.spec == spec:
            new_warnings[key] = old
            continue
        rec_w = WarningRecord(stable_id("warning", shipment_id, sensor_id, key, ev), spec)
        new_warnings[key] = rec_w
        ch.new_warnings.append(rec_w)
        if old is not None:
            ch.superseded_warnings.append(old.row_id)
    ch.superseded_warnings += [old.row_id for key, old in state.warnings.items() if key not in new_warnings]
    state.warnings = new_warnings
    return ch


def _tex_values(rec: RunRecord) -> IncidentValues:
    run = rec.run
    return IncidentValues(
        extent_start_at=run.first_event_at,
        extent_end_at=run.last_event_at,
        extent_open=run.run_open,
        direction=run.direction,
        observed_duration=run.observed_duration,
        bracketing_span=None,
        gap_status=None,
        peak_c=run.peak_c,
        confirmed_event_at=run.confirmed_event_at,
        evidence_received_at=run.evidence_received_at,
        gap_continuity_warning=run.gap_adjacent,
        basis=IncidentBasis.CURRENT,
        merged_into_ref=None,
        basis_key=rec.key,
    )


def _gap_values(rec: GapRecord) -> IncidentValues:
    gap = rec.gap
    return IncidentValues(
        extent_start_at=gap.start_at,
        extent_end_at=gap.end_at,
        extent_open=False,
        direction=None,
        observed_duration=None,
        bracketing_span=gap.bracketing_span,
        gap_status=gap.status,
        peak_c=None,
        confirmed_event_at=None,
        evidence_received_at=None,
        gap_continuity_warning=False,
        basis=IncidentBasis.CURRENT,
        merged_into_ref=None,
        basis_key=rec.key,
    )


def _reconcile_incidents(
    state: SensorState,
    ch: Changes,
    shipment_id: str,
    sensor_id: str,
    ev: str,
    as_of: datetime,
    category: IncidentCategoryName,
    candidates: list[tuple[str, datetime, datetime, IncidentValues]],
    *,
    closed_overlap: bool,
    basis_rows: dict[str, uuid.UUID],
) -> None:
    overlap = _closed_overlap if closed_overlap else _open_overlap
    claimed: set[str] = set()

    def revise(inc: IncidentRecord, values: IncidentValues, basis_row: uuid.UUID | None) -> None:
        if inc.values == values:
            return
        new = replace(inc, revision=inc.revision + 1, values=values)
        state.incidents[inc.business_ref] = new
        ch.incident_changes.append(
            IncidentRevisionChange(
                stable_id("incident_revision", new.business_ref, str(new.revision), ev),
                new,
                False,
                inc.status == "CLOSED",
                basis_row,
            )
        )

    for basis_key, start, end, values in sorted(candidates, key=lambda c: (c[1], c[0])):
        existing = sorted(
            (
                i
                for i in state.incidents.values()
                if i.category == category
                and i.business_ref not in claimed
                and (category != IncidentCategoryName.TEMPERATURE_EXCURSION or i.values.direction == values.direction)
                and overlap(i.values.extent_start_at, i.values.extent_end_at, start, end)
            ),
            key=lambda i: (i.opened_at, i.business_ref),
        )
        if existing:
            carrier, others = existing[0], existing[1:]
            claimed.update(i.business_ref for i in existing)
            revise(carrier, values, basis_rows.get(basis_key))
            for other in others:
                if (
                    other.values.basis != IncidentBasis.MERGED_INTO
                    or other.values.merged_into_ref != carrier.business_ref
                ):
                    revise(
                        other,
                        replace(other.values, basis=IncidentBasis.MERGED_INTO, merged_into_ref=carrier.business_ref),
                        None,
                    )
            continue
        ref = incident_business_ref(shipment_id, sensor_id, category, values.direction, start)
        base, n = ref, 2
        while ref in state.incidents:
            ref, n = f"{base}-{n}", n + 1
        rec = IncidentRecord(stable_id("incident", ref), ref, category, "OPEN", as_of, 1, values)
        state.incidents[ref] = rec
        claimed.add(ref)
        ch.incident_changes.append(
            IncidentRevisionChange(
                stable_id("incident_revision", ref, "1", ev), rec, True, False, basis_rows.get(basis_key)
            )
        )

    for inc in sorted(state.incidents.values(), key=lambda i: i.business_ref):
        if inc.category == category and inc.business_ref not in claimed and inc.values.basis == IncidentBasis.CURRENT:
            revise(inc, replace(inc.values, basis=IncidentBasis.SUPERSEDED_BY_DATA), None)
