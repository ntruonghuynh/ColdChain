"""The committed canonical dataset is intact, synthetic, small and reproducible (SUB-02, D-05)."""

import json
import pytest

from conftest import CANONICAL_SEED, EVALUATION_SEEDS, RELEASE_DIR, REPO_ROOT, SEED_MANIFEST_DIR

from coldchain_sim.verify import load_manifest, verify_by_regeneration, verify_files


def test_committed_release_matches_its_manifest() -> None:
    assert verify_files(RELEASE_DIR) == []


def test_committed_release_is_the_canonical_synthetic_dataset() -> None:
    m = load_manifest(RELEASE_DIR)
    assert m["dataset_id"] == "coldchain-sim-v1.0.0-seed11"
    assert m["seed"] == CANONICAL_SEED and m["journey_count"] == 200
    assert m["synthetic"] is True and m["data_origin"] == "SIMULATED"
    assert "SYNTHETIC DATASET" in (RELEASE_DIR / "README.md").read_text()
    total = sum(p.stat().st_size for p in RELEASE_DIR.rglob("*") if p.is_file())
    assert total < 10 * 1024 * 1024, f"release is {total} bytes; keep it small"


def test_committed_release_regenerates_to_identical_content() -> None:
    assert verify_by_regeneration(RELEASE_DIR, REPO_ROOT) == []


def test_a13_five_reserved_evaluation_seeds_are_independent_of_the_development_seed() -> None:
    """A-13: 22, 33, 44, 55, 66 are reserved for evaluation; the canonical seed 11 is not among them."""
    assert len(set(EVALUATION_SEEDS)) == len(EVALUATION_SEEDS) >= 5  # EVAL-10: at least five independent seeds
    assert CANONICAL_SEED not in EVALUATION_SEEDS
    assert EVALUATION_SEEDS == (22, 33, 44, 55, 66)


@pytest.mark.m9_evaluation
def test_reserved_seed_manifests_are_committed_complete_and_distinct() -> None:
    committed = sorted(p.name for p in SEED_MANIFEST_DIR.glob("*.manifest.json"))
    assert committed == [f"coldchain-sim-v1.0.0-seed{s}.manifest.json" for s in EVALUATION_SEEDS]
    # D-13: final evaluation data is never committed next to the development dataset
    assert not [s for s in EVALUATION_SEEDS if (RELEASE_DIR.parent / f"coldchain-sim-v1.0.0-seed{s}").exists()]
    fingerprints = {load_manifest(RELEASE_DIR)["dataset_fingerprint"]}
    for seed in EVALUATION_SEEDS:
        m = json.loads((SEED_MANIFEST_DIR / f"coldchain-sim-v1.0.0-seed{seed}.manifest.json").read_text())
        assert m["seed"] == seed and m["split_seed"] == seed and m["journey_count"] == 200
        assert m["dataset_id"] == f"coldchain-sim-v1.0.0-seed{seed}"
        assert m["config"]["sha256"] == load_manifest(RELEASE_DIR)["config"]["sha256"]  # same config as seed 11
        fingerprints.add(m["dataset_fingerprint"])
    assert len(fingerprints) == 1 + len(EVALUATION_SEEDS)
