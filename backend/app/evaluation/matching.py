"""Deterministic one-to-one event matching for offline evaluation (U-06, A-01).

A detection and a reference event are *compatible* when they belong to the same journey, have
the same event type (HIGH with EXCURSION_HIGH, LOW with EXCURSION_LOW) and their event-time
intervals overlap: the detection's closed interval ``[start, end]`` (first to last observed
reading) intersects the reference's half-open interval ``[start, end)``.

Compatible pairs are ranked by a total order and accepted greedily, each detection and each
reference at most once:

1. larger overlap duration first;
2. smaller distance between the two start times;
3. earlier detection ``raised_at``;
4. detection id (lexicographic);
5. reference id (lexicographic).

Ids are unique, so the order is total and the result never depends on input order.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_EARLIEST = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Interval:
    item_id: str
    journey_id: str
    event_type: str  # "HIGH" | "LOW"
    start: datetime
    end: datetime
    raised_at: datetime | None = None  # detections only


def compatible(det: Interval, ref: Interval) -> bool:
    return (
        det.journey_id == ref.journey_id
        and det.event_type == ref.event_type
        and det.start < ref.end
        and det.end >= ref.start
    )


def overlap(det: Interval, ref: Interval) -> timedelta:
    return max(timedelta(0), min(det.end, ref.end) - max(det.start, ref.start))


def match_one_to_one(detections: Sequence[Interval], references: Sequence[Interval]) -> list[tuple[str, str]]:
    by_journey: dict[str, list[Interval]] = {}
    for ref in references:
        by_journey.setdefault(ref.journey_id, []).append(ref)
    pairs = []
    for det in detections:
        for ref in by_journey.get(det.journey_id, ()):
            if compatible(det, ref):
                pairs.append(
                    (
                        -overlap(det, ref),
                        abs(det.start - ref.start),
                        det.raised_at or _EARLIEST,
                        det.item_id,
                        ref.item_id,
                    )
                )
    pairs.sort()
    used_det: set[str] = set()
    used_ref: set[str] = set()
    out = []
    for *_, det_id, ref_id in pairs:
        if det_id in used_det or ref_id in used_ref:
            continue
        used_det.add(det_id)
        used_ref.add(ref_id)
        out.append((det_id, ref_id))
    return sorted(out)
