"""DATA-09 / ML-09 / A-12 / D-12: ground-truth labels must not reach detection, features, inference, the API or the frontend.

Static check over application code. In addition to ground-truth model definitions and dataset
import, only M3 offline evaluation and the explicitly allow-listed M4 target loader may read the
labels. Features, prediction, detection, LLM code and API routes are scanned and forbidden.

D-12 (approved 2026-11-15): ground truth may be used as supervised *targets* for training and
evaluation. The M4 label-builder module that reads them must be added to ``ALLOWED`` explicitly,
with a reason. Feature extraction, inference, operational APIs and the frontend stay forbidden.
These are regression tests: do not weaken or remove them to make code pass.
"""

import ast
import os
from pathlib import Path

from fastapi.testclient import TestClient

APP_DIR = Path(__file__).resolve().parents[1] / "app"
REPO_DIR = Path(os.environ.get("COLDCHAIN_REPO_DIR", Path(__file__).resolve().parents[2]))
SCAN_ROOTS = {"app": APP_DIR, "ml": REPO_DIR / "ml", "llm": REPO_DIR / "llm"}
ALLOWED = {
    "app/db/models/ground_truth.py",  # defines the tables
    "app/db/models/__init__.py",      # registers every table for Alembic
    "app/dataset/importer.py",        # writes the labels into schema ground_truth
    "app/dataset/manifest.py",        # verifies checksums of every dataset file, reads no rows
    # Offline evaluation only (contract §6.3, D-12): joins replayed detector outputs with reference
    # labels from the files. Never imported by operational code (test below), no database access.
    "app/evaluation/baseline.py",
    # Explicitly isolated M4 D-12 supervised-target loader; no feature or serving code imports it.
    "ml/coldchain_ml/labels.py",
}
OPERATIONAL_PACKAGES = ("app/api/", "app/domain/", "app/services/", "app/monitoring/", "app/main.py")
FORBIDDEN_NAMES = {"GroundTruthJourney", "GroundTruthEvent", "GROUND_TRUTH_SCHEMA"}
FORBIDDEN_MODULE = "app.db.models.ground_truth"
FORBIDDEN_TEXT = ("ground_truth.", "ground_truth/")  # DB schema-qualified names, dataset label files


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == FORBIDDEN_MODULE:
                found.append(f"imports {FORBIDDEN_MODULE}")
            found += [f"imports {a.name}" for a in node.names if a.name in FORBIDDEN_NAMES]
        elif isinstance(node, ast.Import):
            found += [f"imports {a.name}" for a in node.names if a.name == FORBIDDEN_MODULE]
        elif isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in FORBIDDEN_NAMES:
                found.append(f"uses {name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and any(t in node.value for t in FORBIDDEN_TEXT):
            found.append(f"references {node.value!r}")
    return found


def _python_files() -> list[tuple[str, Path]]:
    files = []
    for label, root in SCAN_ROOTS.items():
        if root.is_dir():
            files += [(f"{label}/{p.relative_to(root).as_posix()}", p) for p in sorted(root.rglob("*.py"))]
    return files


def test_application_code_is_scanned() -> None:
    """The check must actually look at the application package (guards against a wrong path)."""
    scanned = {rel for rel, _ in _python_files()}
    assert "app/main.py" in scanned and "app/api/shipments.py" in scanned


def test_only_the_dataset_loader_touches_ground_truth() -> None:
    problems = {rel: found for rel, path in _python_files()
                if rel not in ALLOWED and (found := _violations(path))}
    assert problems == {}, f"Ground truth used outside the allowed modules: {problems}"


def test_the_boundary_check_detects_a_violation(tmp_path: Path) -> None:
    """The check must be able to fail, for DB access and for reading label files."""
    bad = tmp_path / "features.py"
    bad.write_text("from app.db.models import GroundTruthEvent\n"
                   "rows = 'SELECT * FROM ground_truth.event'\n"
                   "labels = open('data/release/x/ground_truth/events.csv.gz')\n")
    assert len(_violations(bad)) == 3


# ---------------------------------------------------------------- D-12: API and frontend

FRONTEND_SRC = REPO_DIR / "frontend" / "src"
LABEL_TOKENS = ("ground_truth", "groundTruth", "GroundTruth", "primary_scenario", "true_product_temperature",
                "in_policy_excursion", "journey_split", "EXCURSION_HIGH", "EXCURSION_LOW")


def test_d12_operational_api_exposes_no_ground_truth(client: TestClient) -> None:
    """No route, request or response schema of the operational API carries ground-truth labels."""
    spec = client.get("/api/openapi.json").text
    assert not [t for t in LABEL_TOKENS if t in spec]
    assert not [path for path in client.get("/api/openapi.json").json()["paths"] if "ground" in path.lower()]


def test_d12_frontend_never_references_ground_truth() -> None:
    files = sorted(p for p in FRONTEND_SRC.rglob("*") if p.suffix in {".ts", ".tsx", ".js", ".jsx"})
    assert files, f"frontend sources not found under {FRONTEND_SRC} (is the repository mounted?)"
    hits = {p.relative_to(FRONTEND_SRC).as_posix(): [t for t in LABEL_TOKENS if t in p.read_text(encoding="utf-8")]
            for p in files}
    assert {k: v for k, v in hits.items() if v} == {}


def test_operational_code_never_imports_the_evaluation_package() -> None:
    """D-12 / contract §6.3: ground truth is used only by isolated evaluation code."""
    problems = {}
    for rel, path in _python_files():
        if not rel.startswith(OPERATIONAL_PACKAGES):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bad = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
               and n.module.startswith("app.evaluation")]
        bad += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
                if a.name.startswith("app.evaluation")]
        if bad:
            problems[rel] = bad
    assert problems == {}


def test_b78_detector_modules_are_scanned_and_not_allow_listed() -> None:
    """B78: the M3 detector code is checked like any other operational module."""
    scanned = {rel for rel, _ in _python_files()}
    for module in ("app/domain/detector.py", "app/domain/reconcile.py", "app/services/detection.py",
                   "app/services/ingest.py", "app/api/monitoring.py"):
        assert module in scanned and module not in ALLOWED


def test_m4_label_boundary_is_scanned_and_only_its_loader_is_allow_listed() -> None:
    scanned = {rel for rel, _ in _python_files()}
    assert "ml/coldchain_ml/labels.py" in scanned
    assert "ml/coldchain_ml/features.py" in scanned and "ml/coldchain_ml/features.py" not in ALLOWED
