"""Regression guard: M6 Compose must not fall back to shared M5 :local/:test tags."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import yaml


def _repo_root() -> Path:
    configured = os.getenv("COLDCHAIN_REPO_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2]


def test_m6_compose_uses_explicit_project_specific_image_variables() -> None:
    root = _repo_root()
    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    expected = {
        "migrate": "BACKEND_IMAGE",
        "backend": "BACKEND_IMAGE",
        "worker": "BACKEND_IMAGE",
        "data-tools": "BACKEND_IMAGE",
        "backend-tests": "BACKEND_TEST_IMAGE",
        "chain": "CHAIN_IMAGE",
        "chain-deploy": "CHAIN_IMAGE",
        "frontend": "FRONTEND_IMAGE",
    }
    for service, variable in expected.items():
        image = compose["services"][service]["image"]
        assert isinstance(image, str)
        assert image.startswith("${" + variable + ":?"), (service, image)
        assert not image.endswith(":local")
        assert not image.endswith(":test")
        assert "container_name" not in compose["services"][service], service
    assert compose["name"] == "${COMPOSE_PROJECT_NAME:?Run the local environment setup script to create a unique project name}"
    assert all(not (volume or {}).get("external", False)
               for volume in compose.get("volumes", {}).values())


def test_m6_example_images_are_distinct_from_historical_m5_tags() -> None:
    root = _repo_root()
    values = {}
    for line in (root / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    assert values["COMPOSE_PROJECT_NAME"] == "coldchain-demo-template"
    image_keys = ("BACKEND_IMAGE", "BACKEND_TEST_IMAGE", "CHAIN_IMAGE", "FRONTEND_IMAGE")
    image_tags = [values[key] for key in image_keys]
    historical_m5_tags = {
        "coldchain-backend:local", "coldchain-backend:test",
        "coldchain-chain:local", "coldchain-frontend:local",
    }
    assert len(set(image_tags)) == len(image_tags)
    assert all("demo-template" in tag for tag in image_tags)
    assert not historical_m5_tags.intersection(image_tags)


def test_local_setup_makes_project_and_image_tags_unique_and_is_idempotent() -> None:
    root = _repo_root()
    sys.path.insert(0, str(root / "scripts"))
    try:
        from setup_local_env import ensure_installation_namespace
    finally:
        sys.path.pop(0)

    lines = (root / ".env.example").read_text(encoding="utf-8").splitlines()
    ensure_installation_namespace(lines)
    configured = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in lines if "=" in line}
    project = configured["COMPOSE_PROJECT_NAME"]
    suffix = project.removeprefix("coldchain-demo-")
    assert project.startswith("coldchain-demo-") and suffix != "template"
    assert configured["BACKEND_IMAGE"] == f"coldchain-backend:{suffix}"
    assert configured["BACKEND_TEST_IMAGE"] == f"coldchain-backend:test-{suffix}"
    assert configured["CHAIN_IMAGE"] == f"coldchain-chain:{suffix}"
    assert configured["FRONTEND_IMAGE"] == f"coldchain-frontend:{suffix}"
    first_run = list(lines)
    ensure_installation_namespace(lines)
    assert lines == first_run
