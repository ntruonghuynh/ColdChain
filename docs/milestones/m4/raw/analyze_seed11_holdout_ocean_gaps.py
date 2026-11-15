"""Trace frozen ML scores, causal observation availability, and M3 matches for holdout ocean events."""

from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml"))

from app.evaluation import baseline as m3  # noqa: E402
from coldchain_ml.labels import load_scenario_strata  # noqa: E402

DATA = ROOT / "data/release/coldchain-sim-v1.0.0-seed11"
OUT = ROOT / "docs/milestones/m4/raw/internal-test-baseline"


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def csv_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as stream:
        yield from csv.DictReader(stream)


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


split = {row["journey_id"]: row["partition"] for row in csv_rows(DATA / "splits/journey_split.csv")}
scenario = load_scenario_strata(DATA, {journey for journey, part in split.items() if part == "test"})
events = []
for row in m3._csv(DATA / "ground_truth/events.csv.gz"):
    if (row["event_type"].startswith("EXCURSION_") and split[row["journey_id"]] == "test"
            and scenario.get(row["journey_id"]) == "OCEAN_COVERAGE_GAP"):
        events.append({**row, "start": dt(row["start_at"]), "end": dt(row["end_at"]),
                       "attributes": json.loads(row["attributes"]) if row["attributes"] else {}})

predictions: dict[str, list[dict]] = defaultdict(list)
for row in csv_rows(ROOT / "ml/evaluation/internal-test-seed11/predictions.csv"):
    row["at"] = dt(row["prediction_at"])
    row["sufficient"] = row["sufficient_evidence"].lower() == "true"
    row["probability"] = float(row["risk_probability"])
    predictions[row["journey_id"]].append(row)

readings: dict[str, list[dict]] = defaultdict(list)
with gzip.open(DATA / "observed/readings.csv.gz", "rt", newline="", encoding="utf-8") as stream:
    for row in csv.DictReader(stream):
        journey = row["shipment_id"]
        if journey in {event["journey_id"] for event in events}:
            readings[journey].append({"event_at": dt(row["event_at"]), "received_at": dt(row["received_at"]),
                                      "temperature_c": float(row["temperature_c"])})

ml_events = list(csv_rows(ROOT / "ml/evaluation/internal-test-seed11/events.csv"))
baseline_matches = {row["reference_id"]: row for row in csv_rows(OUT / "matches.csv")}
summaries, traces = [], []
for event in events:
    journey, start, end = event["journey_id"], event["start"], event["end"]
    matching_ml = [row for row in ml_events if row["journey_id"] == journey and row["event_type"] == event["event_type"].removeprefix("EXCURSION_")
                   and dt(row["start"]) < end and dt(row["end"]) >= start]
    baseline = baseline_matches.get(event["event_id"], {})
    event_predictions = [row for row in predictions[journey] if start <= row["at"] < end]
    max_run = run = 0
    prev = None
    for row in predictions[journey]:
        positive = row["sufficient"] and row["probability"] >= 0.7
        if positive and prev is not None and row["at"] - prev == timedelta(minutes=5):
            run += 1
        elif positive:
            run = 1
        else:
            run = 0
        if start - timedelta(minutes=10) <= row["at"] < end:
            max_run = max(max_run, run)
        prev = row["at"]

    for row in predictions[journey]:
        if not start - timedelta(minutes=60) <= row["at"] < end:
            continue
        asof = row["at"]
        window_start = asof - timedelta(minutes=60)
        in_window = [r for r in readings[journey] if window_start <= r["event_at"] <= asof]
        available = [r for r in in_window if r["received_at"] <= asof]
        pending = [r for r in in_window if r["received_at"] > asof]
        qualifies = row["sufficient"] and row["probability"] >= 0.7
        traces.append({"reference_id": event["event_id"], "journey_id": journey,
            "prediction_at": asof.isoformat(), "inside_reference_excursion": start <= asof < end,
            "sufficient_evidence": row["sufficient"],
            "operational_score_available": row["sufficient"],
            "risk_score_if_sufficient": f"{row['probability']:.8f}" if row["sufficient"] else "",
            "threshold_positive_if_sufficient": qualifies, "observed_readings_in_60m_available_by_asof": len(available),
            "event_time_readings_not_yet_received": len(pending),
            "latest_pending_received_at": max((r["received_at"] for r in pending), default=None).isoformat()
                if pending else ""})

    late_in_event = [r for r in readings[journey] if start <= r["event_at"] < end and r["received_at"] > r["event_at"]]
    delayed_after_end = [r for r in late_in_event if r["received_at"] >= end]
    summaries.append({"reference_id": event["event_id"], "journey_id": journey,
        "scenario_reporting_only": scenario[journey], "reference_start": start.isoformat(), "reference_end": end.isoformat(),
        "event_readings": event["attributes"].get("readings_in_interval"),
        "delayed_readings_label_count": event["attributes"].get("delayed_readings_in_interval"),
        "missing_readings_label_count": event["attributes"].get("missing_readings_in_interval"),
        "delayed_observed_readings_in_interval": len(late_in_event),
        "readings_received_at_or_after_excursion_end": len(delayed_after_end),
        "prediction_windows_during_excursion": len(event_predictions),
        "scored_windows_during_excursion": sum(row["sufficient"] for row in event_predictions),
        "insufficient_evidence_windows_during_excursion": sum(not row["sufficient"] for row in event_predictions),
        "threshold_positive_windows_during_excursion": sum(row["sufficient"] and row["probability"] >= 0.7
                                                           for row in event_predictions),
        "max_consecutive_threshold_positive_windows_near_event": max_run,
        "required_consecutive_for_alert": 3,
        "ml_event_overlap_count": len(matching_ml), "m3_baseline_matched": baseline.get("matched", "False"),
        "m3_baseline_detection_ref": baseline.get("detection_ref", "")})

OUT.mkdir(parents=True, exist_ok=True)
write_csv(OUT / "ocean-gap-event-diagnostics.csv", summaries)
write_csv(OUT / "ocean-gap-window-trace.csv", traces)
payload = {"purpose": "diagnostic only; frozen ML scores and thresholds unchanged",
    "event_count": len(summaries), "events": summaries,
    "interpretation": "A score is operationally available only when the frozen sufficient-evidence flag is true. Raw offline probability values on abstaining windows are not scores. Window trace includes only readings with event_at in the prior 60 minutes, and separately counts those whose received_at exceeds as_of."}
(OUT / "ocean-gap-diagnostics.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(json.dumps(payload, indent=2, sort_keys=True))
