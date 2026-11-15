"""Fixtures for the simulator tests (no database needed).

Run inside Docker together with the backend tests:
``docker compose --profile test run --rm --build backend-tests``.
"""

import json
import os
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

import pytest

from coldchain_sim.config import find_repo_root
from coldchain_sim.dataset import generate_dataset
from coldchain_sim.fileio import read_csv_rows

REPO_ROOT = Path(os.environ["COLDCHAIN_REPO_DIR"]) if os.environ.get("COLDCHAIN_REPO_DIR") \
    else find_repo_root(Path(__file__))
CONFIG = REPO_ROOT / "data" / "generator" / "config" / "coldchain-sim-v1.yaml"
POLICY_FILE = REPO_ROOT / "backend" / "app" / "seed" / "data" / "policies" / "POL-CHILL-01_v1.0.json"
RELEASE_DIR = REPO_ROOT / "data" / "release" / "coldchain-sim-v1.0.0-seed11"
SEED_MANIFEST_DIR = REPO_ROOT / "data" / "release" / "seed-manifests"
# A-13 (approved 2026-11-15): seed 11 is the canonical DEVELOPMENT dataset (committed in full).
# Seeds 22, 33, 44, 55, 66 are RESERVED for operational simulation evaluation (EVAL-10, M9):
# only their manifests are committed; their data is regenerated when needed.
CANONICAL_SEED = 11
EVALUATION_SEEDS = (22, 33, 44, 55, 66)
SMALL_SEED = 101
SMALL_JOURNEYS = 40


@dataclass
class Data:
    path: Path
    manifest: dict[str, Any]

    def table(self, rel: str) -> list[dict[str, str]]:
        return read_csv_rows(self.path / rel)

    @cached_property
    def shipments(self) -> list[dict[str, str]]:
        return self.table("observed/shipments.csv")

    @cached_property
    def uploads(self) -> list[dict[str, str]]:
        return self.table("observed/uploads.csv.gz")

    @cached_property
    def readings(self) -> list[dict[str, str]]:
        return self.table("observed/readings.csv.gz")

    @cached_property
    def context(self) -> list[dict[str, str]]:
        return self.table("observed/context.csv.gz")

    @cached_property
    def journeys(self) -> list[dict[str, str]]:
        return self.table("ground_truth/journeys.csv")

    @cached_property
    def events(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = self.table("ground_truth/events.csv.gz")
        for r in rows:
            r["attributes"] = json.loads(r["attributes"])
            r["duration_min"] = int(r["duration_min"])
        return rows

    @cached_property
    def slots(self) -> list[dict[str, str]]:
        return self.table("ground_truth/slots.csv.gz")

    @cached_property
    def split(self) -> list[dict[str, str]]:
        return self.table("splits/journey_split.csv")

    @cached_property
    def journey_by_id(self) -> dict[str, dict[str, str]]:
        return {j["journey_id"]: j for j in self.journeys}

    @cached_property
    def slot_index(self) -> dict[tuple[str, str], dict[str, str]]:
        return {(s["journey_id"], s["slot_at"]): s for s in self.slots}


def _generate(tmp_path_factory: pytest.TempPathFactory, seed: int, journeys: int | None, name: str) -> Data:
    out = tmp_path_factory.mktemp(name) / "dataset"
    manifest = generate_dataset(CONFIG, seed, out, journey_count=journeys, repo_root=REPO_ROOT)
    return Data(out, manifest)


@pytest.fixture(scope="session")
def small(tmp_path_factory: pytest.TempPathFactory) -> Data:
    """40 journeys (every primary scenario present), seed 101."""
    return _generate(tmp_path_factory, SMALL_SEED, SMALL_JOURNEYS, "small")


@pytest.fixture(scope="session")
def full(tmp_path_factory: pytest.TempPathFactory) -> Data:
    """Full-size dataset for the canonical seed, generated fresh (not read from the release)."""
    return _generate(tmp_path_factory, CANONICAL_SEED, None, "full")
