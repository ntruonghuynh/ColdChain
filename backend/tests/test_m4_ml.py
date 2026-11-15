from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from coldchain_ml.aggregation import aggregate_events
from coldchain_ml.features import FEATURE_NAMES, extract_features, has_sufficient_evidence, validate_feature_row
from coldchain_ml.freeze import freeze_bundle, load_verified
from coldchain_ml.splits import assert_partition_isolation, journeys_for_partition, load_split
from coldchain_ml.windows import Reading

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def obs(minute: int, temp: float, *, received_minute: int | None = None, **context) -> Reading:
    return Reading(T0 + timedelta(minutes=minute),
                   T0 + timedelta(minutes=received_minute if received_minute is not None else minute),
                   temp, **context)


def test_features_use_event_and_receipt_clocks_and_hide_future_context() -> None:
    rows = [obs(0, 4, received_minute=0, ambient_temperature_c=20, context_received_at=T0),
            obs(5, 5, received_minute=35, ambient_temperature_c=30, context_received_at=T0 + timedelta(minutes=35)),
            obs(10, 6, received_minute=10, ambient_temperature_c=21, context_received_at=T0 + timedelta(minutes=10)),
            obs(15, 20, received_minute=15, ambient_temperature_c=22, context_received_at=T0 + timedelta(minutes=15)),
            obs(20, 7, received_minute=20), obs(25, 100, received_minute=25)]
    x = extract_features(rows, T0 + timedelta(minutes=20))
    assert x["observed_reading_count"] == 4  # future event is excluded; delayed event was not yet received
    assert x["temperature_max_c"] == 20
    assert x["ambient_mean_c"] == 21.0  # late context for the five-minute row is excluded
    assert tuple(x) == FEATURE_NAMES
    validate_feature_row(x)


def test_missing_slots_are_not_interpolated_or_counted_as_safe() -> None:
    rows = [obs(0, 5), obs(5, 5), obs(55, 5), obs(60, 5)]
    x = extract_features(rows, T0 + timedelta(minutes=60))
    assert x["observed_reading_count"] == 4
    assert x["missing_fraction"] == pytest.approx(9 / 13)
    assert x["coverage_ratio"] == pytest.approx(4 / 13)
    assert not has_sufficient_evidence(x)
    assert x["observed_above_max_sample_minutes"] == 0


def test_window_start_is_inclusive_and_isolated_spike_has_larger_residual_than_ramp() -> None:
    spike = [obs(i * 5, temp) for i, temp in enumerate([4, 4.2, 4.1, 12, 4.3, 4.2, 4.1, 4])]
    ramp = [obs(i * 5, temp) for i, temp in enumerate([4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5])]
    at = T0 + timedelta(minutes=60)
    spike_x = extract_features(spike, at)
    ramp_x = extract_features(ramp, at)
    assert spike_x["observed_reading_count"] == 8  # the 0-minute boundary is included
    assert spike_x["spike_score_c"] > ramp_x["spike_score_c"]
    assert ramp_x["temperature_slope_c_per_hour"] > spike_x["temperature_slope_c_per_hour"]


def test_split_is_journey_disjoint_and_canonical_counts_are_expected() -> None:
    repo = Path(os.environ.get("COLDCHAIN_REPO_DIR", Path(__file__).resolve().parents[2]))
    split = load_split(repo / "data/release/coldchain-sim-v1.0.0-seed11")
    assert_partition_isolation(split)
    assert {p: len(journeys_for_partition(split, p)) for p in ("train", "validation", "test")} == {
        "train": 140, "validation": 30, "test": 30}


def test_aggregation_requires_consecutive_positive_evidence_and_is_advisory_only() -> None:
    rows = [{"journey_id": "J1", "prediction_at": (T0 + timedelta(minutes=5 * i)).isoformat(),
             "sufficient_evidence": True, "event_type": "HIGH"} for i in range(5)]
    events = aggregate_events(rows, [0.8, 0.8, 0.1, 0.9, 0.9], 0.7, 2)
    assert len(events) == 2
    assert events[0]["start"] == T0
    assert events[0]["raised_at"] == T0 + timedelta(minutes=5)
    assert all("decision" not in event and "release" not in event for event in events)


def test_frozen_bundle_checksum_verification_and_tamper_detection(tmp_path) -> None:
    model = Pipeline([("imputer", SimpleImputer()),
                      ("model", RandomForestClassifier(n_estimators=8, random_state=11))])
    model.fit(np.array([[0.0], [1.0], [2.0], [3.0]]), np.array([0, 0, 1, 1]))
    directory = tmp_path / "bundle"
    freeze_bundle(directory, model, {"model_version": "test-v1", "feature_schema_version": "test"},
                  {"feature_names": ["x"]}, "test model")
    loaded, manifest = load_verified(directory)
    assert manifest["model_version"] == "test-v1"
    assert loaded.predict([[0.1]]).tolist() == model.predict([[0.1]]).tolist()
    (directory / "feature_spec.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        load_verified(directory)


def test_fixed_seed_training_is_deterministic() -> None:
    X = np.asarray([[0.0], [0.5], [1.0], [1.5], [2.0], [2.5]])
    y = np.asarray([0, 0, 0, 1, 1, 1])
    model_a = RandomForestClassifier(n_estimators=24, max_depth=4, random_state=11, n_jobs=1).fit(X, y)
    model_b = RandomForestClassifier(n_estimators=24, max_depth=4, random_state=11, n_jobs=1).fit(X, y)
    assert np.array_equal(model_a.predict_proba(X), model_b.predict_proba(X))


def test_frozen_inference_returns_advisory_score_without_safety_claim() -> None:
    from app.integrations.ml_adapter import MODEL_VERSION, predict

    readings = [obs(i * 5, 4.0) for i in range(13)]
    result = predict(readings, T0 + timedelta(minutes=60))
    assert result["status"] == "SCORED"
    assert result["model_version"] == MODEL_VERSION
    assert 0.0 <= result["risk_probability"] <= 1.0
    assert result["advisory_only"] is True
    assert result["temperature_safety_established"] is False

