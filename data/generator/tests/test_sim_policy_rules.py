"""Policy rules used to derive ground-truth labels: exact boundaries (BR-02, BR-03, BR-04)."""

import hashlib
import json

import pytest
from conftest import POLICY_FILE, RELEASE_DIR

from coldchain_sim.policy import (
    GAP_SHORT,
    GAP_UNKNOWN,
    GAP_UNKNOWN_REVIEW,
    classify_gap,
    load_policy,
    out_of_range_runs,
)

POLICY = load_policy(POLICY_FILE, "backend/app/seed/data/policies/POL-CHILL-01_v1.0.json")


def series(*parts: tuple[float, int]) -> list[float]:
    """Build a 1-minute series from (value, minutes) parts."""
    return [v for value, minutes in parts for v in [value] * minutes]


def test_policy_values_are_read_from_the_approved_policy_file() -> None:
    """Approved 2026-11-14: 2-8 C, >8 C for >=30 min, <2 C for >=15 min, gap >15 UNKNOWN, >=30 review."""
    assert (POLICY.min_temp_c, POLICY.max_temp_c) == (2.0, 8.0)
    assert POLICY.high_excursion_min_duration_min == 30
    assert POLICY.low_excursion_min_duration_min == 15
    assert POLICY.gap_unknown_after_min == 15
    assert POLICY.gap_review_at_min == 30
    assert (POLICY.policy_code, POLICY.policy_version) == ("POL-CHILL-01", "1.0")


def test_policy_hash_uses_the_seed_loader_canonical_form() -> None:
    """Same rule as app.seed.loader.canonical_sha256, so the importer can compare it with the DB."""
    document = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    raw = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert POLICY.content_sha256 == hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_br02_exactly_max_temperature_is_in_range() -> None:
    assert out_of_range_runs(series((5.0, 10), (8.0, 120), (5.0, 10)), 1, POLICY) == []


def test_br02_exactly_min_temperature_is_in_range() -> None:
    assert out_of_range_runs(series((5.0, 10), (2.0, 120), (5.0, 10)), 1, POLICY) == []


@pytest.mark.parametrize(("minutes", "is_excursion"), [(29, False), (30, True), (31, True)])
def test_br02_high_excursion_needs_at_least_30_minutes_above_8c(minutes: int, is_excursion: bool) -> None:
    runs = out_of_range_runs(series((5.0, 10), (8.01, minutes), (5.0, 10)), 1, POLICY)
    assert len(runs) == 1
    assert runs[0].direction == "HIGH"
    assert (runs[0].start_min, runs[0].end_min, runs[0].duration_min) == (10, 10 + minutes, minutes)
    assert runs[0].meets_policy_duration is is_excursion


@pytest.mark.parametrize(("minutes", "is_excursion"), [(14, False), (15, True), (16, True)])
def test_br02_low_excursion_needs_at_least_15_minutes_below_2c(minutes: int, is_excursion: bool) -> None:
    runs = out_of_range_runs(series((5.0, 10), (1.99, minutes), (5.0, 10)), 1, POLICY)
    assert len(runs) == 1
    assert runs[0].direction == "LOW"
    assert runs[0].duration_min == minutes
    assert runs[0].meets_policy_duration is is_excursion


def test_br02_continuity_a_single_in_range_minute_splits_the_run() -> None:
    runs = out_of_range_runs(series((9.0, 20), (7.9, 1), (9.0, 20)), 1, POLICY)
    assert [r.duration_min for r in runs] == [20, 20]
    assert not any(r.meets_policy_duration for r in runs)


def test_br02_run_reaching_the_end_of_the_series_is_closed_there() -> None:
    runs = out_of_range_runs(series((5.0, 10), (9.0, 40)), 1, POLICY)
    assert (runs[0].start_min, runs[0].end_min, runs[0].peak_c) == (10, 50, 9.0)


def test_br02_sample_step_is_respected() -> None:
    # 6 samples 5 minutes apart cover 30 minutes.
    runs = out_of_range_runs([5.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 5.0], 5, POLICY)
    assert (runs[0].start_min, runs[0].duration_min, runs[0].meets_policy_duration) == (5, 30, True)


@pytest.mark.parametrize(("gap_min", "status"), [
    (5, GAP_SHORT), (10, GAP_SHORT), (15, GAP_SHORT),        # exactly 15 is not "longer than 15"
    (15.5, GAP_UNKNOWN), (20, GAP_UNKNOWN), (29.9, GAP_UNKNOWN),
    (30, GAP_UNKNOWN_REVIEW), (185, GAP_UNKNOWN_REVIEW),     # 30 or more requires quality review
])
def test_br03_br04_gap_classification_boundaries(gap_min: float, status: str) -> None:
    assert classify_gap(gap_min, POLICY) == status


def test_policy_file_is_unchanged_since_the_labels_were_derived() -> None:
    """CLAUDE.md rule 3: the canonical labels were derived from this exact policy content."""
    manifest = json.loads((RELEASE_DIR / "manifest.json").read_text())
    assert POLICY.content_sha256 == manifest["policy"]["content_sha256"]


def test_sampling_interval_is_configuration_not_policy() -> None:
    """2026-11-15: the 5-minute interval describes the logger, not the product; it is not a policy field."""
    text = POLICY_FILE.read_text(encoding="utf-8").lower()
    assert "sampling" not in text and "interval" not in text
