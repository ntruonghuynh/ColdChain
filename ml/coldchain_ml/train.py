"""Reproducible train/validation selection; never loads the internal test partition."""

from __future__ import annotations

import json
import hashlib
import platform
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from coldchain_ml import FEATURE_SCHEMA_VERSION, MODEL_VERSION, PROTOCOL_VERSION
from coldchain_ml.aggregation import aggregate_events
from coldchain_ml.dataset import build_partition, verify_release
from coldchain_ml.evaluate import evaluate_predictions, write_event_predictions, write_predictions
from coldchain_ml.features import FEATURE_NAMES, STRIDE_MINUTES, WINDOW_MINUTES
from coldchain_ml.freeze import freeze_bundle
from coldchain_ml.splits import load_split

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "data/release/coldchain-sim-v1.0.0-seed11"
REGISTRY = ROOT / "ml/registry"
OUTPUT = ROOT / "ml/evaluation/dev"
POLICY_FILE = ROOT / "backend/app/seed/data/policies/POL-CHILL-01_v1.0.json"
TRAINING_CONFIG_FILE = ROOT / "ml/configs/training-v1.json"


def _canonical_sha256(document: dict) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=False).encode("utf-8")).hexdigest()


def _pipeline(candidate: str, seed: int, configs: dict):
    settings = configs[candidate]
    if candidate == "logistic":
        return Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                         ("scale", StandardScaler()),
                         ("model", LogisticRegression(class_weight=settings["class_weight"],
                                                       max_iter=settings["max_iter"], random_state=seed))])
    return Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                     ("model", RandomForestClassifier(**settings, n_jobs=1, random_state=seed))])


def select_threshold(dataset: Path, targets: list[int], meta: list[dict], probabilities: list[float],
                     thresholds: list[float], minimum_windows: list[int]) -> dict:
    best = None
    for threshold in thresholds:
        for consecutive in minimum_windows:
            metrics = evaluate_predictions(dataset, "validation", targets, meta, probabilities,
                                           threshold, consecutive)
            p, r = metrics["event_precision"], metrics["event_recall"]
            metrics["event_f1"] = (2 * p * r / (p + r)) if p + r else 0.0
            metrics["selection_score"] = metrics["event_f1"]
            score = (metrics["event_f1"], p, r, -metrics["false_alarms_per_journey"])
            best_score = ((best["event_f1"], best["event_precision"], best["event_recall"],
                           -best["false_alarms_per_journey"]) if best else None)
            if best is None or score > best_score:
                best = metrics
    return best


def run_training(dataset_dir: Path = DEFAULT_DATASET, *, seed: int = 11) -> Path:
    if seed != 11:
        raise ValueError("M4 development training is restricted to canonical seed 11")
    dataset_manifest = verify_release(dataset_dir)
    training_source = json.loads(TRAINING_CONFIG_FILE.read_text(encoding="utf-8"))
    if training_source["allowed_dataset_id"] != dataset_manifest["dataset_id"] or training_source["random_seed"] != seed:
        raise ValueError("Training configuration does not match the canonical data protocol")
    if training_source["window_minutes"] != WINDOW_MINUTES or training_source["stride_minutes"] != STRIDE_MINUTES:
        raise ValueError("Training window configuration does not match the frozen feature implementation")
    policy_doc = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    if _canonical_sha256(policy_doc) != dataset_manifest["policy"]["content_sha256"]:
        raise ValueError("Canonical dataset policy hash does not match the approved policy file")
    policy = policy_doc["policy"]
    min_temp_c, max_temp_c = float(policy["limits"]["min_temp_c"]), float(policy["limits"]["max_temp_c"])
    split = load_split(dataset_dir)
    counts = {partition: sum(value == partition for value in split.values())
              for partition in ("train", "validation", "test")}
    expected_counts = {"train": training_source["partitions"]["train"],
                       "validation": training_source["partitions"]["validation"],
                       "test": training_source["partitions"]["internal_test"]}
    if counts != expected_counts:
        raise ValueError(f"Unexpected canonical journey split: {counts}")
    x_train, y_train, _ = build_partition(dataset_dir, "train", min_temp_c=min_temp_c, max_temp_c=max_temp_c)
    x_val, y_val, val_meta = build_partition(dataset_dir, "validation", min_temp_c=min_temp_c,
                                             max_temp_c=max_temp_c)
    X_train = np.asarray([[r[name] for name in FEATURE_NAMES] for r in x_train], dtype=float)
    X_val = np.asarray([[r[name] for name in FEATURE_NAMES] for r in x_val], dtype=float)
    output = OUTPUT / "seed11-train-validation"
    output.mkdir(parents=True, exist_ok=True)
    candidates = []
    for name, settings in training_source["candidates"].items():
        model = _pipeline(name, seed, training_source["candidates"])
        model.fit(X_train, np.asarray(y_train, dtype=int))
        risk_col = list(model.named_steps["model"].classes_).index(1)
        probabilities = model.predict_proba(X_val)[:, risk_col].tolist()
        metrics = select_threshold(dataset_dir, y_val, val_meta, probabilities,
                                   training_source["validation_thresholds"],
                                   training_source["validation_minimum_consecutive_windows"])
        candidates.append((metrics["event_f1"], metrics["event_precision"], name, model, metrics, probabilities))
        write_predictions(output / f"validation-predictions-{name}.csv", val_meta, y_val, probabilities)
        event_rows = aggregate_events(val_meta, probabilities, metrics["threshold"],
                                      metrics["minimum_consecutive_windows"])
        write_event_predictions(output / f"validation-events-{name}.csv", event_rows)
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    _, _, selected_name, selected, metrics, probabilities = candidates[-1]
    for _, _, name, _, result, _ in candidates:
        result["candidate"] = name
        (output / f"validation-metrics-{name}.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    config = {"config_version": training_source["config_version"],
              "training_config_sha256": hashlib.sha256(TRAINING_CONFIG_FILE.read_bytes()).hexdigest(),
              "protocol_version": PROTOCOL_VERSION, "random_seed": seed, "dataset_id": dataset_manifest["dataset_id"],
              "dataset_fingerprint": dataset_manifest["dataset_fingerprint"],
              "partitions": training_source["partitions"],
              "window_minutes": training_source["window_minutes"], "stride_minutes": training_source["stride_minutes"],
              "candidates": list(training_source["candidates"]),
              "candidate_hyperparameters": training_source["candidates"],
              "selected_candidate": selected_name, "selection_metric": "validation event-level F1; tie-break precision, recall, fewer false alarms",
              "selected_threshold": metrics["threshold"], "minimum_consecutive_windows": metrics["minimum_consecutive_windows"],
              "policy_limits_c": {"minimum": min_temp_c, "maximum": max_temp_c},
              "libraries": {"python": platform.python_version(), "scikit_learn": sklearn.__version__,
                            "numpy": np.__version__, "joblib": joblib.__version__}}
    (output / "training_config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    (output / "candidate-comparison.json").write_text(json.dumps(
        {name: result for _, _, name, _, result, _ in candidates}, indent=2, sort_keys=True) + "\n")
    feature_spec = {"schema_version": FEATURE_SCHEMA_VERSION, "feature_names": list(FEATURE_NAMES),
                    "window_minutes": 60, "stride_minutes": 5, "sample_minutes": 5,
                    "min_temperature_c": min_temp_c, "max_temperature_c": max_temp_c,
                    "minimum_evidence": {"observations": 6, "coverage_ratio": 0.4},
                    "missing_values": "No temperature interpolation; coverage and missing slots are explicit. Missing context is zero encoded with observation count features.",
                    "time_filter": "event_at <= prediction_at AND received_at <= prediction_at"}
    model_card = f"""# {MODEL_VERSION}\n\nSynthetic-data advisory excursion detector. Target: whether a policy-defined true excursion is active at the prediction timestamp. This is current-state classification, not forecasting.\n\nSelected validation candidate: `{selected_name}`. Threshold: `{metrics['threshold']}`; consecutive windows: `{metrics['minimum_consecutive_windows']}`. Validation event precision {metrics['event_precision']:.4f}, recall {metrics['event_recall']:.4f}, false alarms/journey {metrics['false_alarms_per_journey']:.4f}.\n\nThe model only supports review. It cannot establish product safety or authorize quality release, quarantine or warehouse activity. Synthetic simulator behavior may not represent real sensors, routes, products or prevalence.\n"""
    bundle = REGISTRY / MODEL_VERSION
    freeze_bundle(bundle, selected, {**config, "model_version": MODEL_VERSION,
                                   "feature_schema_version": FEATURE_SCHEMA_VERSION,
                                   "policy_sha256": dataset_manifest["policy"]["content_sha256"],
                                   "evaluation_protocol_version": PROTOCOL_VERSION,
                                   "validation_metrics": metrics,
                                   "test_partition_usage": "not evaluated at freeze time"}, feature_spec, model_card,
                  {**training_source, "selected_candidate": selected_name,
                   "selected_threshold": metrics["threshold"],
                   "minimum_consecutive_windows": metrics["minimum_consecutive_windows"]})
    return bundle


def evaluate_internal_test(bundle: Path, dataset_dir: Path = DEFAULT_DATASET) -> dict:
    from coldchain_ml.freeze import load_verified
    from coldchain_ml.features import FEATURE_NAMES
    model, manifest = load_verified(bundle)
    run_dir = ROOT / "ml/evaluation/internal-test-seed11"
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError("Seed-11 internal test evaluation is one-shot; output already exists")
    verify_release(dataset_dir)
    # This is the first and only access to test-partition records in this M4 session.
    policy_limits = manifest["policy_limits_c"]
    x_test, y_test, meta = build_partition(dataset_dir, "test", min_temp_c=policy_limits["minimum"],
                                           max_temp_c=policy_limits["maximum"])
    X = np.asarray([[r[name] for name in FEATURE_NAMES] for r in x_test], dtype=float)
    risk_col = list(model.named_steps["model"].classes_).index(1)
    probabilities = model.predict_proba(X)[:, risk_col].tolist()
    metrics = evaluate_predictions(dataset_dir, "test", y_test, meta, probabilities,
                                   manifest["selected_threshold"], manifest["minimum_consecutive_windows"])
    run_dir.mkdir(parents=True, exist_ok=True)
    write_predictions(run_dir / "predictions.csv", meta, y_test, probabilities)
    from coldchain_ml.aggregation import aggregate_events
    write_event_predictions(run_dir / "events.csv", aggregate_events(meta, probabilities,
        manifest["selected_threshold"], manifest["minimum_consecutive_windows"]))
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    (run_dir / "holdout-use.json").write_text(json.dumps({"model_version": manifest["model_version"],
        "dataset_id": manifest["dataset_id"], "partition": "test", "one_shot": True,
        "purpose": "post-freeze internal holdout check; no tuning permitted", "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "frozen_bundle_sha256": manifest["artifacts"]["model.joblib"]}, indent=2, sort_keys=True) + "\n")
    return metrics
