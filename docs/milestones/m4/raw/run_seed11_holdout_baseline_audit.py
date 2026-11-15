"""Reproduce the post-freeze seed-11 baseline and paired-delay audit.

This wrapper calls the unchanged M3 SensorEvaluator replay and summarize/matcher
functions. It deliberately bypasses only the development evaluator's D-13 guard
that prevents its ordinary train/validation command from reading the test split.
It is restricted to the canonical seed-11 test partition and writes a labeled
post-freeze internal comparison. It does not tune or change either model.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml"))

from app.dataset.manifest import load_and_verify  # noqa: E402
from app.domain.detector import Obs  # noqa: E402
from app.domain.rules import DETECTOR_CODE_VERSION, PolicyRules, parse_detector_config  # noqa: E402
from app.evaluation import baseline as m3  # noqa: E402
from app.evaluation.matching import Interval, match_one_to_one  # noqa: E402
from coldchain_ml.splits import load_split  # noqa: E402


DATASET = ROOT / "data/release/coldchain-sim-v1.0.0-seed11"
POLICY = ROOT / "backend/app/seed/data/policies/POL-CHILL-01_v1.0.json"
DETECTOR = ROOT / "backend/app/seed/data/detector/DET-BASELINE_v1.0.0.json"
OUT = ROOT / "docs/milestones/m4/raw/internal-test-baseline"


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        fields.extend(key for key in row if key not in fields)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or ["empty"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_baseline() -> tuple[dict, list[dict], list[dict], list[dict]]:
    verified = load_and_verify(DATASET)
    manifest = verified.manifest
    if manifest["dataset_id"] != "coldchain-sim-v1.0.0-seed11" or int(manifest["seed"]) != 11:
        raise RuntimeError("Audit accepts only canonical seed 11")
    split = load_split(DATASET)
    journeys = sorted(journey for journey, part in split.items() if part == "test")
    if len(journeys) != 30:
        raise RuntimeError(f"Expected the existing 30-journey test split, got {len(journeys)}")

    policy_doc = json.loads(POLICY.read_text(encoding="utf-8"))
    detector_doc = json.loads(DETECTOR.read_text(encoding="utf-8"))
    policy = PolicyRules.from_document(policy_doc, m3.canonical_sha256(policy_doc))
    config = parse_detector_config(detector_doc, m3.canonical_sha256(detector_doc))
    selected = set(journeys)
    shipments = {row["shipment_id"]: row for row in m3._csv(DATASET / "observed/shipments.csv")
                 if row["shipment_id"] in selected}
    uploads: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for row in m3._csv(DATASET / "observed/uploads.csv.gz"):
        if row["shipment_id"] in selected:
            uploads[row["shipment_id"]].append((utc(row["received_at"]), row["upload_id"]))
    readings: dict[str, list[Obs]] = defaultdict(list)
    for row in m3._csv(DATASET / "observed/readings.csv.gz"):
        if row["shipment_id"] in selected:
            readings[row["shipment_id"]].append(
                Obs(utc(row["event_at"]), Decimal(row["temperature_c"]), utc(row["received_at"]))
            )

    detected, final_gaps, evaluations, end_gap_revisions = [], {}, 0, 0
    for journey in journeys:
        shipment = shipments[journey]
        incidents, state, count, end_gaps = m3._replay_journey(
            journey, shipment["sensor_id"], utc(shipment["departure_at"]), utc(shipment["arrival_at"]),
            uploads[journey], readings[journey], policy, config,
        )
        detected.extend(incidents.values())
        final_gaps[journey] = sorted(state.gaps.values(), key=lambda gap: gap.gap.start_at)
        evaluations += count
        end_gap_revisions += end_gaps

    reference_excursions, reference_missing = [], []
    for row in m3._csv(DATASET / "ground_truth/events.csv.gz"):
        if row["journey_id"] not in selected:
            continue
        reference = {
            "event_id": row["event_id"], "journey_id": row["journey_id"],
            "event_type": row["event_type"], "start": utc(row["start_at"]), "end": utc(row["end_at"]),
            "attributes": json.loads(row["attributes"]) if row["attributes"] else {},
        }
        if row["event_type"] in {"EXCURSION_HIGH", "EXCURSION_LOW"}:
            reference_excursions.append(reference)
        elif row["event_type"] == "MISSING_DATA":
            reference_missing.append(reference)

    summary, matches, gaps, matched_dets = m3.summarize(
        journeys, detected, final_gaps, reference_excursions, reference_missing, evaluations, end_gap_revisions,
    )
    summary["label"] = "POST-FREEZE internal holdout comparison on seed-11 test; not model selection or M9"
    matched_ref_ids = {row["reference_id"] for row in matches if row.get("matched")}
    detections = [
        {"detection_ref": incident.business_ref, "journey_id": incident.journey_id,
         "category": incident.category, "direction": incident.direction or "",
         "first_raised_at": incident.revisions[0]["raised_at"].isoformat(),
         "final_start": incident.final["start"].isoformat(), "final_end": incident.final["end"].isoformat(),
         "final_basis": incident.final["basis"], "matched": incident.business_ref in matched_dets}
        for incident in sorted(detected, key=lambda item: item.business_ref)
    ]
    run_config = {
        "label": summary["label"], "protocol_version": m3.PROTOCOL_VERSION,
        "m3_detector_code_version": DETECTOR_CODE_VERSION, "dataset_id": manifest["dataset_id"],
        "dataset_fingerprint": manifest["dataset_fingerprint"], "seed": 11, "partitions": ["test"],
        "journey_count": len(journeys), "journeys": journeys,
        "policy_sha256": policy.content_sha256, "detector_config_sha256": config.content_sha256,
        "tuned_parameters": "none; unchanged approved policy and M3 detector",
        "matching": "unchanged app.evaluation.matching one-to-one protocol",
        "scope_note": "The ordinary M3 evaluator rejects test; this audit wrapper invoked the same replay and summarize functions only after the frozen M4 internal test existed.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "run_config.json").write_text(json.dumps(run_config, indent=2, sort_keys=True) + "\n")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
    write_csv(OUT / "matches.csv", matches)
    write_csv(OUT / "detections.csv", detections)
    write_csv(OUT / "missing_data_intervals.csv", gaps)
    return summary, matches, reference_excursions, detections


def paired_validation_delays() -> dict:
    baseline_file = ROOT / "ml/evaluation/dev/baseline-validation/matches.csv"
    ml_file = ROOT / "ml/evaluation/dev/seed11-train-validation/validation-events-rf_deeper.csv"
    refs_by_key: dict[tuple[str, str, str], Interval] = {}
    # Load exact reference intervals so matching preserves the M3 overlap rule.
    baseline_rows = list(csv.DictReader(baseline_file.open(newline="", encoding="utf-8")))
    validation_journeys = {row["journey_id"] for row in baseline_rows}
    for row in m3._csv(DATASET / "ground_truth/events.csv.gz"):
        if row["journey_id"] not in validation_journeys or row["event_type"] not in {
            "EXCURSION_HIGH", "EXCURSION_LOW"
        }:
            continue
        key = (row["journey_id"], row["event_type"], utc(row["start_at"]).isoformat())
        refs_by_key[key] = Interval(row["event_id"], row["journey_id"],
            "HIGH" if row["event_type"] == "EXCURSION_HIGH" else "LOW",
            utc(row["start_at"]), utc(row["end_at"]))
    baseline_delays = { (row["journey_id"], row["reference_type"], row["reference_start"]):
        float(row["delay_emit_min"]) for row in baseline_rows if row.get("matched") == "True" }

    ml_rows = list(csv.DictReader(ml_file.open(newline="", encoding="utf-8")))
    detections = [Interval(f"ml-{i}", row["journey_id"], row["event_type"], utc(row["start"]),
                           utc(row["end"]), utc(row["raised_at"])) for i, row in enumerate(ml_rows)]
    pairs = match_one_to_one(detections, list(refs_by_key.values()))
    ref_by_id = {ref.item_id: ref for ref in refs_by_key.values()}
    ml_delay_by_key = {}
    for detection_id, reference_id in pairs:
        det = next(d for d in detections if d.item_id == detection_id)
        ref_interval = ref_by_id[reference_id]
        key = (ref_interval.journey_id,
               "EXCURSION_HIGH" if ref_interval.event_type == "HIGH" else "EXCURSION_LOW",
               ref_interval.start.isoformat())
        ml_delay_by_key[key] = max(0.0, (det.raised_at - ref_interval.start).total_seconds() / 60)
    baseline_keys, ml_keys = set(baseline_delays), set(ml_delay_by_key)
    shared = sorted(baseline_keys & ml_keys)
    rows = []
    for key in shared:
        b, ml = baseline_delays[key], ml_delay_by_key[key]
        rows.append({"journey_id": key[0], "reference_type": key[1], "reference_start": key[2],
                     "baseline_delay_min": b, "ml_delay_min": ml, "ml_minus_baseline_min": ml - b})
    write_csv(OUT / "paired-validation-delays.csv", rows)
    import statistics
    bmed = statistics.median(row["baseline_delay_min"] for row in rows)
    mmed = statistics.median(row["ml_delay_min"] for row in rows)
    paired_delta_median = statistics.median(row["ml_minus_baseline_min"] for row in rows)
    return {"scope": "seed-11 validation; post-hoc paired analysis, not model selection",
        "matched_by_both_count": len(shared), "baseline_only_reference_count": len(baseline_keys - ml_keys),
        "ml_only_reference_count": len(ml_keys - baseline_keys), "baseline_only_reference_keys": sorted(baseline_keys - ml_keys),
        "ml_only_reference_keys": sorted(ml_keys - baseline_keys), "shared_baseline_median_delay_min": bmed,
        "shared_ml_median_delay_min": mmed, "difference_between_shared_medians_ml_minus_baseline_min": mmed - bmed,
        "median_of_paired_differences_ml_minus_baseline_min": paired_delta_median,
        "paired_event_rows": rows, "limitations": "Small matched-event intersection; no uncertainty interval; delays are causal emission delay to matched reference onset."}


def holdout_missing_reading_comparison(reference_rows: list[dict], baseline_match_rows: list[dict]) -> dict:
    """Compare matched-reference recall for label attributes describing missing/delayed readings."""
    ml_path = ROOT / "ml/evaluation/internal-test-seed11/events.csv"
    ml_rows = list(csv.DictReader(ml_path.open(newline="", encoding="utf-8")))
    ml_detections = [Interval(f"ml-{i}", row["journey_id"], row["event_type"], utc(row["start"]),
                              utc(row["end"]), utc(row["raised_at"])) for i, row in enumerate(ml_rows)]
    ml_refs = [Interval(row["event_id"], row["journey_id"],
                        "HIGH" if row["event_type"] == "EXCURSION_HIGH" else "LOW",
                        row["start"], row["end"]) for row in reference_rows]
    ml_matched_ref_ids = {ref for _, ref in match_one_to_one(ml_detections, ml_refs)}
    baseline_matched_ref_ids = {row["reference_id"] for row in baseline_match_rows
                                if row.get("matched") in (True, "True")}
    result = {}
    for label, predicate in (
        ("reference_events_with_missing_readings", lambda attrs: (attrs.get("missing_readings_in_interval") or 0) > 0),
        ("reference_events_with_delayed_readings", lambda attrs: (attrs.get("delayed_readings_in_interval") or 0) > 0),
        ("reference_events_without_missing_or_delayed_readings", lambda attrs:
            (attrs.get("missing_readings_in_interval") or 0) == 0
            and (attrs.get("delayed_readings_in_interval") or 0) == 0),
    ):
        refs = [row for row in reference_rows if predicate(row["attributes"])]
        base_hits = sum(row["event_id"] in baseline_matched_ref_ids for row in refs)
        ml_hits = sum(row["event_id"] in ml_matched_ref_ids for row in refs)
        result[label] = {"reference_events": len(refs), "baseline_matched": base_hits,
                         "baseline_recall": base_hits / len(refs) if refs else None,
                         "ml_matched": ml_hits, "ml_recall": ml_hits / len(refs) if refs else None}
    return result


if __name__ == "__main__":
    baseline_summary, baseline_matches, refs, baseline_detections = run_baseline()
    paired = paired_validation_delays()
    (OUT / "paired-validation-summary.json").write_text(json.dumps(paired, indent=2, sort_keys=True) + "\n")
    missing_readings = holdout_missing_reading_comparison(refs, baseline_matches)
    (OUT / "missing-reading-comparison.json").write_text(
        json.dumps(missing_readings, indent=2, sort_keys=True) + "\n")
    frozen_ml = json.loads((ROOT / "ml/evaluation/internal-test-seed11/metrics.json")
                           .read_text(encoding="utf-8"))
    comparison = {
        "scope": "post-freeze internal holdout comparison; seed-11 test; not model selection",
        "journeys": 30,
        "baseline": {
            "reference_events": baseline_summary["excursion_detection"]["reference_events"],
            "detections": baseline_summary["excursion_detection"]["detections_raised"],
            "true_positives": baseline_summary["excursion_detection"]["matched"],
            "false_positives": baseline_summary["excursion_detection"]["false_alarms"],
            "precision": baseline_summary["excursion_detection"]["precision"],
            "recall": baseline_summary["excursion_detection"]["recall"],
            "false_alarms_per_journey": baseline_summary["excursion_detection"]["false_alarms_per_journey"],
            "median_causal_emission_delay_minutes": baseline_summary["detection_delay_min"]
                ["emission_delay_Te_minus_T0"]["median"],
            "matched_delay_n": baseline_summary["detection_delay_min"]["emission_delay_Te_minus_T0"]["n"],
        },
        "frozen_random_forest": {
            "reference_events": frozen_ml["event_reference_count"],
            "detections": frozen_ml["event_detection_count"],
            "true_positives": frozen_ml["event_matched_count"],
            "false_positives": frozen_ml["event_detection_count"] - frozen_ml["event_matched_count"],
            "precision": frozen_ml["event_precision"], "recall": frozen_ml["event_recall"],
            "false_alarms_per_journey": frozen_ml["false_alarms_per_journey"],
            "median_causal_emission_delay_minutes": frozen_ml["matched_detection_delay_minutes"]["median"],
            "matched_delay_n": frozen_ml["matched_detection_delay_minutes"]["n"],
            "artifact_sha256": json.loads((ROOT / "ml/registry/coldchain-rf-v1.0.0/model_manifest.json")
                                           .read_text(encoding="utf-8"))["artifacts"]["model.joblib"],
        },
        "missing_reading_subgroups": missing_readings,
        "validation_paired_delay_analysis": paired,
        "baseline_missing_data_behavior": baseline_summary["missing_readings_behaviour"],
    }
    (OUT / "comparison-summary.json").write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"internal_test_baseline": baseline_summary["excursion_detection"],
        "internal_test_delays": baseline_summary["detection_delay_min"]["emission_delay_Te_minus_T0"],
        "internal_test_missing": baseline_summary["missing_readings_behaviour"],
        "internal_test_missing_reading_subgroups": missing_readings,
        "validation_paired_delays": paired}, indent=2, sort_keys=True))
