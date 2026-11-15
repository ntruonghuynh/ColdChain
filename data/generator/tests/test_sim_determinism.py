"""Deterministic generation and independent journeys (NFR-03, EVAL-10)."""

import json
import re
from pathlib import Path

import pytest
from conftest import (
    CANONICAL_SEED,
    CONFIG,
    EVALUATION_SEEDS,
    RELEASE_DIR,
    REPO_ROOT,
    SEED_MANIFEST_DIR,
    SMALL_JOURNEYS,
    SMALL_SEED,
    Data,
)

from coldchain_sim.config import PRIMARY_SCENARIOS, load_config
from coldchain_sim.dataset import OUTPUT_FILES, generate_dataset, plan_journeys
from coldchain_sim.journey import simulate_journey
from coldchain_sim.policy import load_policy


def test_same_seed_and_config_give_byte_identical_files(small: Data, tmp_path: Path) -> None:
    again = generate_dataset(CONFIG, SMALL_SEED, tmp_path / "again", journey_count=SMALL_JOURNEYS,
                             repo_root=REPO_ROOT)
    assert again["dataset_fingerprint"] == small.manifest["dataset_fingerprint"]
    for rel in OUTPUT_FILES:
        assert (tmp_path / "again" / rel).read_bytes() == (small.path / rel).read_bytes(), rel


def test_different_seed_gives_different_data(small: Data, tmp_path: Path) -> None:
    other = generate_dataset(CONFIG, SMALL_SEED + 1, tmp_path / "other", journey_count=SMALL_JOURNEYS,
                             repo_root=REPO_ROOT)
    assert other["dataset_fingerprint"] != small.manifest["dataset_fingerprint"]
    readings = {f["path"]: f["content_sha256"] for f in other["files"]}
    assert readings["observed/readings.csv.gz"] != {
        f["path"]: f["content_sha256"] for f in small.manifest["files"]}["observed/readings.csv.gz"]


def test_manifest_records_seed_config_and_generator(small: Data) -> None:
    m = small.manifest
    assert m["seed"] == SMALL_SEED and m["split_seed"] == SMALL_SEED
    assert m["journey_count"] == SMALL_JOURNEYS
    assert m["config"]["config_version"] == "1.0.0"
    assert m["generator"] == {"name": "coldchain_sim", "version": "1.0.0"}
    assert (small.path / "config.yaml").read_bytes() == CONFIG.read_bytes()
    assert m["synthetic"] is True and m["data_origin"] == "SIMULATED"


def test_a_journey_depends_only_on_its_own_seed(small: Data) -> None:
    """Independent journeys: simulating one journey alone reproduces its rows in the dataset."""
    cfg = load_config(CONFIG)
    policy = load_policy(REPO_ROOT / cfg.raw["policy"]["file"], cfg.raw["policy"]["file"])
    spec = plan_journeys(cfg, SMALL_SEED, SMALL_JOURNEYS)[6]
    alone = simulate_journey(spec, cfg, policy)
    in_dataset = [r for r in small.readings if r["shipment_id"] == spec.shipment_id]
    assert alone.readings == in_dataset
    assert simulate_journey(spec, cfg, policy).readings == alone.readings


def test_journey_ids_are_unique_and_carry_no_label_information(full: Data) -> None:
    ids = [j["journey_id"] for j in full.journeys]
    assert len(ids) == len(set(ids)) == 200
    assert all(re.fullmatch(rf"SIM-S{CANONICAL_SEED}-J\d{{4}}", i) for i in ids)
    assert len({j["journey_seed"] for j in full.journeys}) == 200
    # The scenario order is shuffled: consecutive IDs do not share a scenario block.
    first_twenty = {full.journey_by_id[i]["primary_scenario"] for i in sorted(ids)[:20]}
    assert len(first_twenty) >= 4


def _committed_fingerprint(seed: int) -> str:
    path = RELEASE_DIR / "manifest.json" if seed == CANONICAL_SEED else \
        SEED_MANIFEST_DIR / f"coldchain-sim-v1.0.0-seed{seed}.manifest.json"
    return json.loads(path.read_text())["dataset_fingerprint"]


@pytest.mark.parametrize("seed", (CANONICAL_SEED, *EVALUATION_SEEDS))
def test_eval10_canonical_and_reserved_seeds_generate_200_journeys_reproducibly(seed: int, tmp_path: Path) -> None:
    """Seed 11 (development) and the five reserved evaluation seeds regenerate to their committed fingerprints."""
    manifest = generate_dataset(CONFIG, seed, tmp_path / f"seed{seed}", repo_root=REPO_ROOT)
    assert manifest["journey_count"] >= 200
    stats = json.loads((tmp_path / f"seed{seed}" / "statistics.json").read_text())
    assert set(stats["journeys"]["by_primary_scenario"]) == set(PRIMARY_SCENARIOS)
    assert manifest["dataset_fingerprint"] == _committed_fingerprint(seed)
