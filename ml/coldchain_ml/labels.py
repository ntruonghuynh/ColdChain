"""The single D-12 offline boundary for supervised target labels.

This module reads only reference excursion event intervals. Scenario names, sensor causes,
physical sample values and evaluation metadata are never returned as features or inputs.
"""

from __future__ import annotations

import csv
import gzip
from datetime import UTC, datetime
from pathlib import Path


def load_excursion_labels(dataset_dir: Path, journey_ids: set[str]) -> dict[str, list[tuple[datetime, datetime, str]]]:
    path = dataset_dir / "ground_truth" / "events.csv.gz"
    labels: dict[str, list[tuple[datetime, datetime, str]]] = {journey: [] for journey in journey_ids}
    with gzip.open(path, "rt", newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if row["journey_id"] not in journey_ids or row["event_type"] not in {"EXCURSION_HIGH", "EXCURSION_LOW"}:
                continue
            start = datetime.fromisoformat(row["start_at"].replace("Z", "+00:00")).astimezone(UTC)
            end = datetime.fromisoformat(row["end_at"].replace("Z", "+00:00")).astimezone(UTC)
            labels[row["journey_id"]].append((start, end, row["event_type"].removeprefix("EXCURSION_")))
    return labels


def is_risk_active(labels: list[tuple[datetime, datetime, str]], at: datetime) -> bool:
    return any(start <= at < end for start, end, _ in labels)


def load_scenario_strata(dataset_dir: Path, journey_ids: set[str]) -> dict[str, str]:
    """Offline reporting only; scenario values are never returned to training or serving."""
    path = dataset_dir / "ground_truth" / "journeys.csv"
    with path.open(newline="", encoding="utf-8") as source:
        return {row["journey_id"]: row["primary_scenario"] for row in csv.DictReader(source)
                if row["journey_id"] in journey_ids}
