"""Approved policy values and the policy rules used to derive ground-truth labels.

The values are read from the same JSON file the backend seeds into the ``policy``
table (``backend/app/seed/data/policies/POL-CHILL-01_v1.0.json``). Nothing is
hard-coded here. The canonical SHA-256 is computed exactly like
``app.seed.loader.canonical_sha256`` so the importer can check that the labels
were derived from the policy stored in the database.

Rules (approved 2026-11-14, requirements analysis §13.1):

* BR-02 high excursion: temperature strictly above ``max_temp_c`` for at least
  ``high_excursion_min_duration_min`` minutes; low excursion: strictly below
  ``min_temp_c`` for at least ``low_excursion_min_duration_min`` minutes.
* BR-03 a gap between consecutive readings longer than ``gap_unknown_after_min`` is UNKNOWN.
* BR-04 a gap of at least ``gap_review_at_min`` requires quality review.

These functions label the SIMULATED TRUTH. They are not the Milestone 3 detector,
which applies the same policy to observed readings inside the backend.
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GAP_SHORT = "SHORT_GAP"
GAP_UNKNOWN = "UNKNOWN"
GAP_UNKNOWN_REVIEW = "UNKNOWN_REVIEW_REQUIRED"


def canonical_sha256(document: Any) -> str:
    raw = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Policy:
    product_id: str
    policy_code: str
    policy_version: str
    procedure_version: str
    min_temp_c: float
    max_temp_c: float
    high_excursion_min_duration_min: int
    low_excursion_min_duration_min: int
    gap_unknown_after_min: int
    gap_review_at_min: int
    content_sha256: str
    source_file: str

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "policy_code": self.policy_code,
            "policy_version": self.policy_version,
            "procedure_version": self.procedure_version,
            "min_temp_c": self.min_temp_c,
            "max_temp_c": self.max_temp_c,
            "high_excursion_min_duration_min": self.high_excursion_min_duration_min,
            "low_excursion_min_duration_min": self.low_excursion_min_duration_min,
            "gap_unknown_after_min": self.gap_unknown_after_min,
            "gap_review_at_min": self.gap_review_at_min,
            "content_sha256": self.content_sha256,
            "source_file": self.source_file,
        }


def load_policy(path: Path, source_label: str) -> Policy:
    document = json.loads(path.read_text(encoding="utf-8"))
    pol = document["policy"]
    return Policy(
        product_id=document["product"]["product_id"],
        policy_code=pol["policy_code"],
        policy_version=pol["policy_version"],
        procedure_version=pol["procedure_version"],
        min_temp_c=float(pol["limits"]["min_temp_c"]),
        max_temp_c=float(pol["limits"]["max_temp_c"]),
        high_excursion_min_duration_min=int(pol["duration_rule"]["high_excursion_min_duration_min"]),
        low_excursion_min_duration_min=int(pol["duration_rule"]["low_excursion_min_duration_min"]),
        gap_unknown_after_min=int(pol["missing_data_rule"]["gap_unknown_after_min"]),
        gap_review_at_min=int(pol["missing_data_rule"]["gap_review_at_min"]),
        content_sha256=canonical_sha256(document),
        source_file=source_label,
    )


# ---------------------------------------------------------------- run detection

def runs(values: Sequence[float], predicate: Callable[[float], bool]) -> list[tuple[int, int]]:
    """Maximal runs ``[start, end)`` of consecutive indices where ``predicate`` holds."""
    result: list[tuple[int, int]] = []
    start: int | None = None
    for i, v in enumerate(values):
        if predicate(v):
            if start is None:
                start = i
        elif start is not None:
            result.append((start, i))
            start = None
    if start is not None:
        result.append((start, len(values)))
    return result


@dataclass(frozen=True)
class OutOfRangeRun:
    direction: str          # "HIGH" or "LOW"
    start_min: int          # first minute out of range
    end_min: int            # first minute back in range (or journey end)
    peak_c: float           # max (HIGH) or min (LOW) true temperature in the run
    meets_policy_duration: bool

    @property
    def duration_min(self) -> int:
        return self.end_min - self.start_min


def out_of_range_runs(true_temp_c: Sequence[float], step_min: int, policy: Policy) -> list[OutOfRangeRun]:
    """BR-02 applied to the simulated true product temperature sampled every ``step_min``.

    A sample at minute ``m`` represents ``[m, m + step_min)``. "Above" and "below" are
    strict: exactly ``max_temp_c`` or ``min_temp_c`` is in range.
    """
    found: list[OutOfRangeRun] = []
    for direction, pred, threshold in (
        ("HIGH", lambda v: v > policy.max_temp_c, policy.high_excursion_min_duration_min),
        ("LOW", lambda v: v < policy.min_temp_c, policy.low_excursion_min_duration_min),
    ):
        for s, e in runs(true_temp_c, pred):
            segment = true_temp_c[s:e]
            peak = max(segment) if direction == "HIGH" else min(segment)
            duration = (e - s) * step_min
            found.append(OutOfRangeRun(direction, s * step_min, e * step_min, peak, duration >= threshold))
    found.sort(key=lambda r: (r.start_min, r.direction))
    return found


def classify_gap(gap_min: float, policy: Policy) -> str:
    """BR-03 / BR-04 for a gap between consecutive readings (by ``event_at``).

    ``> gap_unknown_after_min`` -> UNKNOWN; ``>= gap_review_at_min`` -> UNKNOWN and review required.
    """
    if gap_min >= policy.gap_review_at_min and gap_min > policy.gap_unknown_after_min:
        return GAP_UNKNOWN_REVIEW
    if gap_min > policy.gap_unknown_after_min:
        return GAP_UNKNOWN
    return GAP_SHORT
