"""Journey-level split validation for the canonical seed-11 release."""

from __future__ import annotations

import csv
from pathlib import Path


def load_split(dataset_dir: Path) -> dict[str, str]:
    with (dataset_dir / "splits" / "journey_split.csv").open(newline="", encoding="utf-8") as source:
        result = {}
        for row in csv.DictReader(source):
            if row["journey_id"] in result:
                raise ValueError(f"Journey appears more than once in split: {row['journey_id']}")
            result[row["journey_id"]] = row["partition"]
    if set(result.values()) - {"train", "validation", "test"}:
        raise ValueError("Unknown journey partition")
    return result


def journeys_for_partition(split: dict[str, str], partition: str) -> set[str]:
    if partition not in {"train", "validation", "test"}:
        raise ValueError("Unknown partition")
    return {journey for journey, value in split.items() if value == partition}


def assert_partition_isolation(split: dict[str, str]) -> None:
    if set(split.values()) - {"train", "validation", "test"}:
        raise ValueError("Journey has an unknown partition")
