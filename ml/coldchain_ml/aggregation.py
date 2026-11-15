"""Deterministic consecutive-window to advisory event aggregation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

def aggregate_events(rows: list[dict], probabilities: list[float], threshold: float, min_consecutive: int) -> list[dict]:
    grouped: dict[str, list[tuple[datetime, float, bool, dict]]] = defaultdict(list)
    for meta, probability in zip(rows, probabilities, strict=True):
        at = datetime.fromisoformat(meta["prediction_at"])
        grouped[meta["journey_id"]].append((at, probability, meta["sufficient_evidence"], meta))
    events = []
    for journey, points in sorted(grouped.items()):
        points.sort(key=lambda item: item[0])
        active: list[tuple[datetime, float, bool, dict]] = []
        for point in points + [(datetime.max.replace(tzinfo=points[0][0].tzinfo), 0.0, False, {})]:
            qualifies = point[2] and point[1] >= threshold
            contiguous = bool(active) and point[0] - active[-1][0] == timedelta(minutes=5)
            if active and (not qualifies or not contiguous):
                if len(active) >= min_consecutive:
                    # Advisory direction derives only from observable feature summaries.
                    direction = active[-1][3]["event_type"]
                    events.append({"journey_id": journey, "event_type": direction,
                                   "start": active[0][0], "end": active[-1][0],
                                   "raised_at": active[min_consecutive - 1][0],
                                   "score": max(p[1] for p in active)})
                active = []
            if qualifies:
                active.append(point)
    return events


def score_direction(features: dict[str, float]) -> str:
    high = max(0.0, features["temperature_max_c"] - 8.0)
    low = max(0.0, 2.0 - features["temperature_min_c"])
    return "HIGH" if high >= low else "LOW"
