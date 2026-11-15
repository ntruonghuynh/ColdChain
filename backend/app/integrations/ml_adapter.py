"""Read-only adapter for the frozen M4 advisory model; never imports training labels."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import joblib
import numpy
import sklearn
from coldchain_ml.features import FEATURE_NAMES, extract_features, has_sufficient_evidence, validate_feature_row
from coldchain_ml.freeze import load_verified


MODEL_VERSION = "coldchain-rf-v1.0.0"


def model_directory() -> Path:
    configured = os.environ.get("ML_MODEL_DIR")
    if configured:
        return Path(configured)
    backend_root = Path(__file__).resolve().parents[2]
    candidate = backend_root / "ml" / "registry" / MODEL_VERSION
    if candidate.exists():
        return candidate
    return backend_root.parent / "ml" / "registry" / MODEL_VERSION


@lru_cache(maxsize=1)
def load_model():
    model, manifest = load_verified(model_directory())
    if manifest.get("model_version") != MODEL_VERSION:
        raise ValueError("Configured model version does not match the frozen bundle")
    versions = manifest["libraries"]
    actual = {"scikit_learn": sklearn.__version__, "numpy": numpy.__version__, "joblib": joblib.__version__}
    if actual != {key: versions[key] for key in actual}:
        raise ValueError("Frozen model library versions do not match this runtime")
    return model, manifest


def predict(readings, as_of, *, min_temp_c: float = 2.0, max_temp_c: float = 8.0,
            policy_sha256: str | None = None) -> dict:
    model, manifest = load_model()
    if policy_sha256 is not None and policy_sha256 != manifest["policy_sha256"]:
        raise ValueError("Shipment policy is incompatible with the frozen model")
    import json
    feature_spec = json.loads((model_directory() / "feature_spec.json").read_text(encoding="utf-8"))
    if feature_spec.get("schema_version") != manifest["feature_schema_version"] \
            or tuple(feature_spec["feature_names"]) != FEATURE_NAMES:
        raise ValueError("Frozen feature schema is incompatible with inference code")
    if feature_spec["min_temperature_c"] != min_temp_c or feature_spec["max_temperature_c"] != max_temp_c:
        raise ValueError("Frozen feature policy limits are incompatible with the shipment policy")
    features = extract_features(readings, as_of, min_temp_c=min_temp_c, max_temp_c=max_temp_c)
    validate_feature_row(features)
    base = {"as_of": as_of, "model_version": manifest["model_version"],
            "feature_schema_version": manifest["feature_schema_version"],
            "advisory_only": True, "temperature_safety_established": False}
    if not has_sufficient_evidence(features):
        return {**base, "status": "INSUFFICIENT_EVIDENCE", "risk_probability": None,
                "alert": False, "message": "Insufficient recent observations; temperature risk is unknown."}
    values = [[features[name] for name in FEATURE_NAMES]]
    risk_index = list(model.named_steps["model"].classes_).index(1)
    probability = float(model.predict_proba(values)[0][risk_index])
    return {**base, "status": "SCORED", "risk_probability": probability,
            "threshold": manifest["selected_threshold"],
            "alert": probability >= manifest["selected_threshold"],
            "interpretation": "ADVISORY_RISK_REVIEW" if probability >= manifest["selected_threshold"]
            else "NO_MODEL_ALERT; this does not establish product safety",
            "evidence": {"observed_reading_count": int(features["observed_reading_count"]),
                         "coverage_ratio": features["coverage_ratio"],
                         "latest_received_age_minutes": features["latest_received_age_minutes"]}}
