"""Causal evaluation of one sensor on one shipment (pure).

Used by live ingestion, by replay of stored data and by the offline evaluation, so all
three produce identical results for identical inputs (contract §5.4, C-07, C-09):

* An evaluation at processing time ``as_of`` sees only readings with ``received_at <= as_of``
  and only the monitoring boundaries that have been reached by ``as_of``.
* An evaluation whose input fingerprint equals the previous one is a no-op.
"""

import bisect
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.detector import Obs, Snapshot, evaluate, input_fingerprint
from app.domain.reconcile import Changes, SensorState, reconcile, stable_id
from app.domain.rules import DETECTOR_CODE_VERSION, DetectorConfig, PolicyRules


class StepKind(StrEnum):
    MONITORING_START = "MONITORING_START"
    BATCH = "BATCH"
    MONITORING_END = "MONITORING_END"


_KIND_ORDER = {StepKind.MONITORING_START: 0, StepKind.BATCH: 1, StepKind.MONITORING_END: 2}


@dataclass(frozen=True, slots=True)
class TimelineStep:
    at: datetime
    kind: StepKind
    batch_ref: str | None = None


def build_timeline(
    assigned_from: datetime | None, assigned_to: datetime | None, batches: Iterable[tuple[datetime, str]]
) -> list[TimelineStep]:
    """Replay order (contract §5.4): by time; ties: start boundary, batches by reference, end boundary."""
    steps = [TimelineStep(at, StepKind.BATCH, ref) for at, ref in batches]
    if assigned_from is not None:
        steps.append(TimelineStep(assigned_from, StepKind.MONITORING_START))
    if assigned_to is not None:
        steps.append(TimelineStep(assigned_to, StepKind.MONITORING_END))
    return sorted(steps, key=lambda s: (s.at, _KIND_ORDER[s.kind], s.batch_ref or ""))


@dataclass(frozen=True, slots=True)
class Outcome:
    evaluation_id: uuid.UUID
    as_of: datetime
    trigger: str
    fingerprint: str
    snapshot: Snapshot
    changes: Changes
    visible_reading_count: int
    affected_from_at: datetime | None
    affected_to_at: datetime | None


class SensorEvaluator:
    """Holds the known readings and the current results of one sensor on one shipment."""

    def __init__(
        self,
        *,
        shipment_id: str,
        sensor_id: str,
        mode: str,
        policy: PolicyRules,
        config: DetectorConfig,
        assigned_from: datetime | None,
        assigned_to: datetime | None,
        state: SensorState | None = None,
        code_version: str = DETECTOR_CODE_VERSION,
    ) -> None:
        self.shipment_id, self.sensor_id, self.mode = shipment_id, sensor_id, mode
        self.policy, self.config, self.code_version = policy, config, code_version
        self.assigned_from, self.assigned_to = assigned_from, assigned_to
        self.state = state if state is not None else SensorState()
        self._readings: list[Obs] = []  # sorted by event_at
        self._keys: list[datetime] = []
        self._pending: list[Obs] = []  # readings added but not yet seen by an evaluation

    def add(self, readings: Iterable[Obs]) -> None:
        for r in readings:
            i = bisect.bisect_left(self._keys, r.event_at)
            if i < len(self._keys) and self._keys[i] == r.event_at:
                continue  # one reading per (sensor, event_at); duplicates never reach detection (BR-07)
            self._keys.insert(i, r.event_at)
            self._readings.insert(i, r)
            self._pending.append(r)

    def evaluate(self, as_of: datetime, trigger: str) -> Outcome | None:
        visible = [r for r in self._readings if r.received_at <= as_of]  # causal (C-09)
        start = self.assigned_from if self.assigned_from is not None and as_of >= self.assigned_from else None
        end = self.assigned_to if self.assigned_to is not None and as_of >= self.assigned_to else None
        fingerprint = input_fingerprint(
            visible, start=start, end=end, policy=self.policy, config=self.config, code_version=self.code_version
        )
        if fingerprint == self.state.last_fingerprint:
            return None
        pending = [r.event_at for r in self._pending if r.received_at <= as_of]
        self._pending = [r for r in self._pending if r.received_at > as_of]
        evaluation_id = stable_id(
            "evaluation", self.shipment_id, self.sensor_id, self.mode, trigger, as_of.isoformat(), fingerprint
        )
        snapshot = evaluate(visible, start=start, end=end, policy=self.policy, config=self.config)
        changes = reconcile(
            self.state,
            snapshot,
            shipment_id=self.shipment_id,
            sensor_id=self.sensor_id,
            evaluation_id=evaluation_id,
            as_of=as_of,
        )
        self.state.last_fingerprint = fingerprint
        return Outcome(
            evaluation_id,
            as_of,
            trigger,
            fingerprint,
            snapshot,
            changes,
            len(visible),
            min(pending) if pending else None,
            max(pending) if pending else None,
        )
