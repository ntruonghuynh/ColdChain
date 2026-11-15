"""Policy-baseline detection on observed readings (pure functions, no I/O).

Specification: ``docs/design/m3-baseline-detector-contract.md`` §5.5 to §5.8.

* Two consecutive readings are continuous when at most ``max_continuous_interval``
  (7 min 30 s, C-01) apart. Otherwise the interval between them is a confirmed
  missing-reading gap. Timestamps are used exactly as received; nothing is snapped,
  interpolated or filled (C-06).
* A gap's **bracketing span** is the exact time between its two bounds (readings or
  documented monitoring boundaries). The policy thresholds (BR-03, BR-04) are compared
  with the bracketing span, exactly (C-05). The **estimated missing samples** (and the
  duration they represent) is a different measurement, reported for information only.
* A temperature run is a maximal sequence of continuous readings strictly above the
  maximum or strictly below the minimum. Its duration is last minus first ``event_at``
  (BR-05 point 7). A confirmed gap always breaks a run (BR-05 point 1).
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from app.domain.rules import DetectorConfig, PolicyRules

MICROSECOND = timedelta(microseconds=1)
TEMP_QUANTUM = Decimal("0.01")


class TempClass(StrEnum):
    IN_RANGE = "IN_RANGE"
    HIGH = "HIGH"
    LOW = "LOW"


class GapStatus(StrEnum):
    SHORT_GAP = "SHORT_GAP"
    UNKNOWN = "UNKNOWN"
    UNKNOWN_REVIEW_REQUIRED = "UNKNOWN_REVIEW_REQUIRED"


class GapBound(StrEnum):
    READING = "READING"
    MONITORING_START = "MONITORING_START"
    MONITORING_END = "MONITORING_END"


class MonitoringStateName(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    ENDED = "ENDED"


@dataclass(frozen=True, slots=True)
class Obs:
    """One accepted observed reading."""

    event_at: datetime
    temperature_c: Decimal
    received_at: datetime


@dataclass(frozen=True, slots=True)
class Gap:
    start_at: datetime
    end_at: datetime
    start_bound: GapBound
    end_bound: GapBound
    bracketing_span: timedelta
    estimated_missing_samples: int
    estimated_missing_duration: timedelta
    status: GapStatus
    out_of_range_before: bool
    out_of_range_after: bool

    @property
    def key(self) -> str:
        """Identity: the opening bound (contract §5.12)."""
        return self.start_at.isoformat()


@dataclass(frozen=True, slots=True)
class Run:
    direction: TempClass
    first_event_at: datetime
    last_event_at: datetime
    reading_count: int
    observed_duration: timedelta
    threshold: timedelta
    meets_policy_duration: bool
    confirmed_event_at: datetime | None
    evidence_received_at: datetime | None
    peak_c: Decimal
    run_open: bool
    preceded_by_gap: str | None
    followed_by_gap: str | None

    @property
    def gap_adjacent(self) -> bool:
        return self.preceded_by_gap is not None or self.followed_by_gap is not None

    def adjacent_gaps(self) -> list[str]:
        return [g for g in (self.preceded_by_gap, self.followed_by_gap) if g is not None]


@dataclass(frozen=True, slots=True)
class Snapshot:
    gaps: tuple[Gap, ...]
    runs: tuple[Run, ...]
    reading_count: int
    newest_event_at: datetime | None
    start_boundary_at: datetime | None
    end_boundary_at: datetime | None


@dataclass(frozen=True, slots=True)
class MonitoringState:
    state: MonitoringStateName
    as_of: datetime
    newest_event_at: datetime | None
    unobserved_since_at: datetime | None
    unobserved_duration: timedelta | None
    provisional_review_threshold_reached: bool
    end_boundary_established: bool


# ------------------------------------------------------------------ single measurements


def classify(temperature_c: Decimal, policy: PolicyRules) -> TempClass:
    """BR-01/BR-02: the limits themselves are in range; no extra tolerance (C-05)."""
    if temperature_c > policy.max_temp_c:
        return TempClass.HIGH
    if temperature_c < policy.min_temp_c:
        return TempClass.LOW
    return TempClass.IN_RANGE


def is_continuous(earlier: datetime, later: datetime, config: DetectorConfig) -> bool:
    """C-01: at most 7 min 30 s apart (exact comparison on the original timestamps)."""
    return later - earlier <= config.max_continuous_interval


def classify_gap(bracketing_span: timedelta, policy: PolicyRules) -> GapStatus:
    """BR-03/BR-04 on the bracketing span: > 15 min UNKNOWN, >= 30 min review required."""
    if bracketing_span >= policy.gap_review_at:
        return GapStatus.UNKNOWN_REVIEW_REQUIRED
    if bracketing_span > policy.gap_unknown_after:
        return GapStatus.UNKNOWN
    return GapStatus.SHORT_GAP


def estimated_missing_samples(bracketing_span: timedelta, config: DetectorConfig) -> int:
    """ceil((span - I/2) / I) - 1, in exact integer microseconds. An estimate, never readings."""
    nominal_us = config.nominal_interval // MICROSECOND
    numerator = bracketing_span // MICROSECOND - nominal_us // 2
    if numerator <= 0:
        return 0
    return max(0, -(-numerator // nominal_us) - 1)


def seconds(value: timedelta) -> Decimal:
    """Exact seconds (6 decimals) for storage and display."""
    return Decimal(value // MICROSECOND) / Decimal(1_000_000)


# ------------------------------------------------------------------ evaluation


def _gap(
    start_at: datetime,
    end_at: datetime,
    start_bound: GapBound,
    end_bound: GapBound,
    before: TempClass | None,
    after: TempClass | None,
    policy: PolicyRules,
    config: DetectorConfig,
) -> Gap:
    span = end_at - start_at
    samples = estimated_missing_samples(span, config)
    return Gap(
        start_at=start_at,
        end_at=end_at,
        start_bound=start_bound,
        end_bound=end_bound,
        bracketing_span=span,
        estimated_missing_samples=samples,
        estimated_missing_duration=samples * config.nominal_interval,
        status=classify_gap(span, policy),
        out_of_range_before=before not in (None, TempClass.IN_RANGE),
        out_of_range_after=after not in (None, TempClass.IN_RANGE),
    )


def evaluate(
    readings: Sequence[Obs],
    *,
    start: datetime | None,
    end: datetime | None,
    policy: PolicyRules,
    config: DetectorConfig,
) -> Snapshot:
    """Gaps and runs for one sensor.

    ``readings`` are the visible accepted readings (``received_at <= as_of``), sorted by
    ``event_at`` with unique ``event_at``. ``start`` / ``end`` are the documented monitoring
    boundaries that are *established* at ``as_of`` (``None`` otherwise, C-04).
    """
    n = len(readings)
    classes = [classify(r.temperature_c, policy) for r in readings]
    gaps: list[Gap] = []
    gap_closed_by: dict[int, Gap] = {}  # reading index -> gap that ends at that reading
    gap_opened_by: dict[int, Gap] = {}  # reading index -> gap that starts at that reading

    if n == 0:
        if start is not None and end is not None and not is_continuous(start, end, config):
            gaps.append(
                _gap(start, end, GapBound.MONITORING_START, GapBound.MONITORING_END, None, None, policy, config)
            )
    else:
        if start is not None and not is_continuous(start, readings[0].event_at, config):
            g = _gap(
                start,
                readings[0].event_at,
                GapBound.MONITORING_START,
                GapBound.READING,
                None,
                classes[0],
                policy,
                config,
            )
            gaps.append(g)
            gap_closed_by[0] = g
        for i in range(1, n):
            if not is_continuous(readings[i - 1].event_at, readings[i].event_at, config):
                g = _gap(
                    readings[i - 1].event_at,
                    readings[i].event_at,
                    GapBound.READING,
                    GapBound.READING,
                    classes[i - 1],
                    classes[i],
                    policy,
                    config,
                )
                gaps.append(g)
                gap_opened_by[i - 1] = g
                gap_closed_by[i] = g
        if end is not None and not is_continuous(readings[-1].event_at, end, config):
            g = _gap(
                readings[-1].event_at, end, GapBound.READING, GapBound.MONITORING_END, classes[-1], None, policy, config
            )
            gaps.append(g)
            gap_opened_by[n - 1] = g

    runs: list[Run] = []
    run_start: int | None = None
    for i in range(n + 1):
        cls = classes[i] if i < n else TempClass.IN_RANGE
        continues = run_start is not None and i < n and cls == classes[run_start] and (i - 1) not in gap_opened_by
        if continues:
            continue
        if run_start is not None:
            runs.append(
                _run(
                    readings,
                    run_start,
                    i - 1,
                    classes[run_start],
                    gap_closed_by,
                    gap_opened_by,
                    end is None and i - 1 == n - 1,
                    policy,
                )
            )
            run_start = None
        if i < n and cls != TempClass.IN_RANGE:
            run_start = i

    return Snapshot(
        gaps=tuple(gaps),
        runs=tuple(runs),
        reading_count=n,
        newest_event_at=readings[-1].event_at if n else None,
        start_boundary_at=start,
        end_boundary_at=end,
    )


def _run(
    readings: Sequence[Obs],
    s: int,
    e: int,
    direction: TempClass,
    gap_closed_by: dict[int, Gap],
    gap_opened_by: dict[int, Gap],
    run_open: bool,
    policy: PolicyRules,
) -> Run:
    first, last = readings[s].event_at, readings[e].event_at
    threshold = policy.high_min_duration if direction == TempClass.HIGH else policy.low_min_duration
    confirmed_at: datetime | None = None
    evidence_at: datetime | None = None
    latest_receipt = readings[s].received_at
    for k in range(s, e + 1):
        latest_receipt = max(latest_receipt, readings[k].received_at)
        if readings[k].event_at - first >= threshold:
            confirmed_at, evidence_at = readings[k].event_at, latest_receipt
            break
    temps = [readings[k].temperature_c for k in range(s, e + 1)]
    return Run(
        direction=direction,
        first_event_at=first,
        last_event_at=last,
        reading_count=e - s + 1,
        observed_duration=last - first,
        threshold=threshold,
        meets_policy_duration=last - first >= threshold,
        confirmed_event_at=confirmed_at,
        evidence_received_at=evidence_at,
        peak_c=max(temps) if direction == TempClass.HIGH else min(temps),
        run_open=run_open,
        preceded_by_gap=gap_closed_by[s].key if s in gap_closed_by else None,
        followed_by_gap=gap_opened_by[e].key if e in gap_opened_by else None,
    )


# ------------------------------------------------------------------ monitoring state (C-02)


def monitoring_state(
    *,
    newest_event_at: datetime | None,
    assigned_from: datetime | None,
    assigned_to: datetime | None,
    as_of: datetime,
    policy: PolicyRules,
    config: DetectorConfig,
) -> MonitoringState:
    """Transient freshness of the telemetry at ``as_of``. Never stored, never an incident.

    ``newest_event_at`` must come from readings with ``received_at <= as_of`` (causal).
    """
    end_established = assigned_to is not None and as_of >= assigned_to
    if assigned_from is not None and as_of < assigned_from:
        return MonitoringState(MonitoringStateName.NOT_STARTED, as_of, newest_event_at, None, None, False, False)
    if end_established:
        return MonitoringState(MonitoringStateName.ENDED, as_of, newest_event_at, None, None, False, True)
    since = newest_event_at if newest_event_at is not None else assigned_from
    if since is None:  # no documented start and no reading: nothing can be said (C-04)
        return MonitoringState(MonitoringStateName.UNKNOWN, as_of, None, None, None, False, False)
    age = as_of - since
    if age <= config.max_continuous_interval:
        state = MonitoringStateName.CURRENT
    elif age <= policy.gap_unknown_after:
        state = MonitoringStateName.STALE
    else:
        state = MonitoringStateName.UNKNOWN
    return MonitoringState(state, as_of, newest_event_at, since, age, age >= policy.gap_review_at, False)


# ------------------------------------------------------------------ input fingerprint (C-07)


def input_fingerprint(
    readings: Sequence[Obs],
    *,
    start: datetime | None,
    end: datetime | None,
    policy: PolicyRules,
    config: DetectorConfig,
    code_version: str,
) -> str:
    h = hashlib.sha256()
    h.update(f"policy|{policy.policy_code}|{policy.policy_version}|{policy.content_sha256}\n".encode())
    h.update(f"config|{config.detector_code}|{config.config_version}|{config.content_sha256}\n".encode())
    h.update(
        f"code|{code_version}\nstart|{start.isoformat() if start else ''}\n"
        f"end|{end.isoformat() if end else ''}\n".encode()
    )
    for r in readings:
        h.update(f"{r.event_at.isoformat()}|{r.temperature_c.quantize(TEMP_QUANTUM)}\n".encode())
    return h.hexdigest()
