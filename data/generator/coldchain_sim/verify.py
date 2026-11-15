"""Verify a generated dataset against its manifest, optionally by regenerating it."""

import json
import tempfile
from pathlib import Path
from typing import Any

from coldchain_sim.fileio import read_content, sha256_hex


def load_manifest(dataset_dir: Path) -> dict[str, Any]:
    return json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))


def verify_files(dataset_dir: Path) -> list[str]:
    """Return a list of problems (empty = every file matches the manifest)."""
    from coldchain_sim.dataset import fingerprint

    manifest = load_manifest(dataset_dir)
    problems: list[str] = []
    for entry in manifest["files"]:
        path = dataset_dir / entry["path"]
        if not path.is_file():
            problems.append(f"missing file: {entry['path']}")
            continue
        stored = path.read_bytes()
        if len(stored) != entry["bytes"] or sha256_hex(stored) != entry["sha256"]:
            problems.append(f"stored bytes differ from manifest: {entry['path']}")
        content = read_content(path)
        if sha256_hex(content) != entry["content_sha256"]:
            problems.append(f"content differs from manifest: {entry['path']}")
        if entry.get("rows") is not None:
            rows = content.count(b"\n") - 1
            if rows != entry["rows"]:
                problems.append(f"row count {rows} != manifest {entry['rows']}: {entry['path']}")
    if fingerprint(manifest["files"]) != manifest["dataset_fingerprint"]:
        problems.append("dataset_fingerprint does not match the file list")
    return problems


def verify_by_regeneration(dataset_dir: Path, repo_root: Path) -> list[str]:
    """Regenerate from the dataset's own config copy and seed; compare content hashes."""
    from coldchain_sim.dataset import generate_dataset

    manifest = load_manifest(dataset_dir)
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="coldchain-sim-verify-") as tmp:
        regenerated = generate_dataset(dataset_dir / "config.yaml", int(manifest["seed"]), Path(tmp) / "out",
                                       journey_count=int(manifest["journey_count"]), repo_root=repo_root)
    expected = {f["path"]: f["content_sha256"] for f in manifest["files"]}
    actual = {f["path"]: f["content_sha256"] for f in regenerated["files"]}
    for path in sorted(set(expected) | set(actual)):
        if expected.get(path) != actual.get(path):
            problems.append(f"regenerated content differs: {path}")
    if regenerated["dataset_fingerprint"] != manifest["dataset_fingerprint"]:
        problems.append("regenerated dataset_fingerprint differs")
    return problems
