"""Read a dataset folder and verify it against its ``manifest.json`` before any use (interface I-9).

This is an independent re-implementation of the generator's checksum rules, so the
backend does not depend on the generator package to trust a dataset.
"""

import csv
import gzip
import hashlib
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_FILES = (
    "observed/shipments.csv",
    "observed/uploads.csv.gz",
    "observed/readings.csv.gz",
    "observed/context.csv.gz",
    "ground_truth/journeys.csv",
    "ground_truth/events.csv.gz",
)


class DatasetIntegrityError(ValueError):
    """The dataset folder does not match its manifest, or a record is invalid."""


@dataclass(frozen=True)
class VerifiedDataset:
    path: Path
    manifest: dict[str, Any]

    @property
    def dataset_id(self) -> str:
        return str(self.manifest["dataset_id"])

    def rows_expected(self, rel_path: str) -> int:
        return int(next(f["rows"] for f in self.manifest["files"] if f["path"] == rel_path))

    def rows(self, rel_path: str) -> Iterator[dict[str, str]]:
        yield from csv.DictReader(io.StringIO(_content(self.path / rel_path).decode("utf-8")))


def _content(path: Path) -> bytes:
    data = path.read_bytes()
    return gzip.decompress(data) if path.name.endswith(".gz") else data


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_and_verify(dataset_dir: Path) -> VerifiedDataset:
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.is_file():
        raise DatasetIntegrityError(f"No manifest.json in {dataset_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("dataset_id", "dataset_fingerprint", "files", "policy", "seed", "journey_count", "generator", "config"):
        if key not in manifest:
            raise DatasetIntegrityError(f"manifest.json has no {key!r}")
    if manifest.get("synthetic") is not True or manifest.get("data_origin") != "SIMULATED":
        raise DatasetIntegrityError("Only datasets marked synthetic / SIMULATED can be imported by this loader")

    listed = {f["path"]: f for f in manifest["files"]}
    for required in REQUIRED_FILES:
        if required not in listed:
            raise DatasetIntegrityError(f"manifest.json does not list {required}")
    problems = []
    for rel, entry in sorted(listed.items()):
        path = dataset_dir / rel
        if not path.is_file():
            problems.append(f"missing file {rel}")
            continue
        stored = path.read_bytes()
        if _sha(stored) != entry["sha256"]:
            problems.append(f"checksum mismatch {rel}")
            continue
        if _sha(_content(path)) != entry["content_sha256"]:
            problems.append(f"content checksum mismatch {rel}")
    text = "\n".join(f"{p} {listed[p]['content_sha256']}" for p in sorted(listed))
    if _sha(text.encode("utf-8")) != manifest["dataset_fingerprint"]:
        problems.append("dataset_fingerprint does not match the listed files")
    if problems:
        raise DatasetIntegrityError("Dataset failed verification: " + "; ".join(problems))
    return VerifiedDataset(dataset_dir, manifest)
