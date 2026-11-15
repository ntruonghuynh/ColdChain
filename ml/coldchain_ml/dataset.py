"""Observed-only canonical seed-11 dataset loading for the offline pipeline."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from coldchain_ml.features import extract_features, has_sufficient_evidence
from coldchain_ml.labels import is_risk_active, load_excursion_labels
from coldchain_ml.splits import journeys_for_partition, load_split
from coldchain_ml.windows import Reading


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def verify_release(dataset_dir: Path) -> dict:
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("seed") != 11 or manifest.get("dataset_id") != "coldchain-sim-v1.0.0-seed11":
        raise ValueError("M4 development commands accept only the canonical seed-11 dataset")
    for details in manifest["files"]:
        rel = details["path"]
        path = dataset_dir / rel
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != details["sha256"]:
            raise ValueError(f"Dataset checksum mismatch: {rel}")
    return manifest


def build_partition(dataset_dir: Path, partition: str, *, min_temp_c: float = 2.0,
                    max_temp_c: float = 8.0) -> tuple[list[dict[str, float]], list[int], list[dict]]:
    """Build one row per five-minute as-of time, filtering each record by both clocks."""
    split = load_split(dataset_dir)
    selected = journeys_for_partition(split, partition)
    shipments = {}
    with (dataset_dir / "observed" / "shipments.csv").open(newline="", encoding="utf-8") as src:
        for row in csv.DictReader(src):
            if row["shipment_id"] in selected:
                shipments[row["shipment_id"]] = row
    readings: dict[str, list[Reading]] = defaultdict(list)
    with gzip.open(dataset_dir / "observed" / "readings.csv.gz", "rt", newline="", encoding="utf-8") as src:
        for row in csv.DictReader(src):
            if row["shipment_id"] in selected:
                readings[row["shipment_id"]].append(Reading(utc(row["event_at"]), utc(row["received_at"]),
                                                               float(row["temperature_c"])))
    context = {}
    with gzip.open(dataset_dir / "observed" / "context.csv.gz", "rt", newline="", encoding="utf-8") as src:
        for row in csv.DictReader(src):
            if row["shipment_id"] not in selected:
                continue
            key = (row["shipment_id"], utc(row["event_at"]))
            context[key] = row
    enriched = {}
    for journey, rows in readings.items():
        enriched[journey] = []
        for r in rows:
            c = context.get((journey, r.event_at))
            enriched[journey].append(Reading(
                r.event_at, r.received_at, r.temperature_c,
                float(c["ambient_temperature_c"]) if c and c["ambient_temperature_c"] else None,
                c["door_state"] == "OPEN" if c else None,
                float(c["battery_level_pct"]) if c and c["battery_level_pct"] else None,
                utc(c["received_at"]) if c else None,
            ))
    labels = load_excursion_labels(dataset_dir, selected)
    features: list[dict[str, float]] = []
    targets: list[int] = []
    meta: list[dict] = []
    for journey in sorted(selected):
        shipment = shipments[journey]
        departure, arrival = utc(shipment["departure_at"]), utc(shipment["arrival_at"])
        at = departure
        while at <= arrival:
            x = extract_features(enriched.get(journey, []), at, min_temp_c=min_temp_c, max_temp_c=max_temp_c)
            features.append(x)
            targets.append(int(is_risk_active(labels.get(journey, []), at)))
            meta.append({"journey_id": journey, "prediction_at": at.isoformat(),
                         "sufficient_evidence": has_sufficient_evidence(x),
                         "event_type": "HIGH" if max(0, x["temperature_max_c"] - 8)
                         >= max(0, 2 - x["temperature_min_c"]) else "LOW"})
            at += timedelta(minutes=5)
    return features, targets, meta
