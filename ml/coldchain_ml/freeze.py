"""Write and verify immutable-by-convention model bundles with file checksums."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_bundle(directory: Path, model, manifest: dict, feature_spec: dict, model_card: str,
                  training_config: dict | None = None) -> None:
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Frozen model directory already exists: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, directory / "model.joblib", compress=3)
    (directory / "feature_spec.json").write_text(json.dumps(feature_spec, indent=2, sort_keys=True) + "\n")
    (directory / "model_card.md").write_text(model_card)
    if training_config is not None:
        (directory / "training_config.json").write_text(json.dumps(training_config, indent=2, sort_keys=True) + "\n")
    artifact_names = ["model.joblib", "feature_spec.json", "model_card.md"]
    if training_config is not None:
        artifact_names.append("training_config.json")
    manifest["artifacts"] = {name: sha256(directory / name) for name in artifact_names}
    (directory / "model_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    entries = [f"{sha256(directory / name)}  {name}" for name in artifact_names + ["model_manifest.json"]]
    (directory / "SHA256SUMS").write_text("\n".join(entries) + "\n")


def load_verified(directory: Path):
    manifest = json.loads((directory / "model_manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["artifacts"].items():
        actual = sha256(directory / name)
        if actual != expected:
            raise ValueError(f"Frozen model checksum mismatch for {name}")
    for line in (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split(maxsplit=1)
        name = name.strip()
        if Path(name).name != name:
            raise ValueError("Frozen model checksum contains an invalid path")
        if sha256(directory / name) != expected:
            raise ValueError(f"Frozen model checksum list mismatch for {name}")
    return joblib.load(directory / "model.joblib"), manifest
