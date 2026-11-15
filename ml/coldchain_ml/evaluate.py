"""Window diagnostics and event-level metrics using the M3 one-to-one matcher."""

from __future__ import annotations

import csv
import statistics
from datetime import datetime
from pathlib import Path

from sklearn.metrics import confusion_matrix, precision_score, recall_score

from app.evaluation.matching import Interval, match_one_to_one
from coldchain_ml.aggregation import aggregate_events
from coldchain_ml.features import has_sufficient_evidence
from coldchain_ml.labels import load_excursion_labels, load_scenario_strata
from coldchain_ml.splits import journeys_for_partition, load_split


def event_reference_intervals(dataset_dir: Path, partition: str) -> tuple[list[Interval], dict[str, list]]:
    split = load_split(dataset_dir)
    journeys = journeys_for_partition(split, partition)
    refs_by_journey = load_excursion_labels(dataset_dir, journeys)
    refs = [Interval(f"{journey}:{i}", journey, kind, start, end)
            for journey, events in refs_by_journey.items()
            for i, (start, end, kind) in enumerate(events)]
    return refs, refs_by_journey


def evaluate_predictions(dataset_dir: Path, partition: str, targets: list[int], meta: list[dict],
                         probabilities: list[float], threshold: float, min_consecutive: int) -> dict:
    predicted = [int(p >= threshold and row["sufficient_evidence"])
                 for p, row in zip(probabilities, meta, strict=True)]
    eligible = [i for i, row in enumerate(meta) if row["sufficient_evidence"]]
    truth = [targets[i] for i in eligible]
    pred = [predicted[i] for i in eligible]
    events = aggregate_events(meta, probabilities, threshold, min_consecutive)
    references, refs_by_journey = event_reference_intervals(dataset_dir, partition)
    det_intervals = [Interval(f"ml-{i:06d}", e["journey_id"], e["event_type"], e["start"], e["end"], e["raised_at"])
                     for i, e in enumerate(events)]
    pairs = match_one_to_one(det_intervals, references)
    matched = {d for d, _ in pairs}
    delays = []
    pair_ref = {d: r for d, r in pairs}
    refs = {r.item_id: r for r in references}
    for det in det_intervals:
        if det.item_id in matched:
            ref = refs[pair_ref[det.item_id]]
            delays.append(max(0.0, (det.raised_at - ref.start).total_seconds() / 60))
    matched_refs = {r for _, r in pairs}
    journey_count = len({r["journey_id"] for r in meta})
    result = {
        "partition": partition,
        "windows_total": len(meta), "windows_with_sufficient_evidence": len(eligible),
        "window_confusion_matrix_labels_0_1": confusion_matrix(truth, pred, labels=[0, 1]).tolist(),
        "window_precision": float(precision_score(truth, pred, zero_division=0)),
        "window_recall": float(recall_score(truth, pred, zero_division=0)),
        "event_reference_count": len(references), "event_detection_count": len(events),
        "event_matched_count": len(pairs),
        "event_precision": len(pairs) / len(events) if events else 0.0,
        "event_recall": len(pairs) / len(references) if references else 0.0,
        "false_alarms_per_journey": (len(events) - len(pairs)) / journey_count if journey_count else 0.0,
        "matched_detection_delay_minutes": {"n": len(delays),
            "median": statistics.median(delays) if delays else None,
            "mean": statistics.fmean(delays) if delays else None},
        "threshold": threshold, "minimum_consecutive_windows": min_consecutive,
        "journey_count": journey_count,
        "unmatched_reference_count": len(references) - len(matched_refs),
    }
    strata = load_scenario_strata(dataset_dir, {row["journey_id"] for row in meta})
    by_scenario = {}
    for scenario in sorted(set(strata.values())):
        ids = {journey for journey, value in strata.items() if value == scenario}
        scenario_dets = [d for d in det_intervals if d.journey_id in ids]
        scenario_refs = [r for r in references if r.journey_id in ids]
        scenario_pairs = match_one_to_one(scenario_dets, scenario_refs)
        by_scenario[scenario] = {"journeys": len(ids), "reference_events": len(scenario_refs),
            "detections": len(scenario_dets), "matched": len(scenario_pairs),
            "event_precision": len(scenario_pairs) / len(scenario_dets) if scenario_dets else 0.0,
            "event_recall": len(scenario_pairs) / len(scenario_refs) if scenario_refs else 0.0}
    result["event_metrics_by_primary_scenario_reporting_only"] = by_scenario
    return result


def write_predictions(path: Path, meta: list[dict], targets: list[int], probabilities: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        fields = ["journey_id", "prediction_at", "target_excursion_active", "risk_probability",
                  "sufficient_evidence", "observable_direction"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row, target, probability in zip(meta, targets, probabilities, strict=True):
            writer.writerow({"journey_id": row["journey_id"], "prediction_at": row["prediction_at"],
                             "target_excursion_active": target,
                             "risk_probability": f"{probability:.8f}",
                             "sufficient_evidence": row["sufficient_evidence"],
                             "observable_direction": row["event_type"]})


def write_event_predictions(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        fields = ["journey_id", "event_type", "start", "end", "raised_at", "score"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for event in events:
            writer.writerow({**event, "start": event["start"].isoformat(), "end": event["end"].isoformat(),
                             "raised_at": event["raised_at"].isoformat(), "score": f"{event['score']:.8f}"})
