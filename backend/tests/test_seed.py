"""Reference data loading: approved policy values, idempotency, immutability of versions."""

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.seed.loader import DATA_DIR, SeedConflictError, run_seed
from tests.factories import active_policy


def test_seeded_policy_matches_approved_teaching_values(db_session: Session) -> None:
    """Approved 2026-11-14: 2-8 C; >8 C for >=30 min; <2 C for >=15 min; gap >15 min UNKNOWN;
    gap >=30 min quality review; only QUALITY authorizes release."""
    policy = active_policy(db_session)
    assert (policy.min_temp_c, policy.max_temp_c) == (Decimal("2.00"), Decimal("8.00"))
    assert policy.high_excursion_min_duration_min == 30
    assert policy.low_excursion_min_duration_min == 15
    assert policy.gap_unknown_after_min == 15
    assert policy.gap_review_at_min == 30
    assert policy.release_authority_role.value == "QUALITY"
    assert policy.is_teaching_policy is True


def test_policy_values_come_from_config_file(db_session: Session) -> None:
    document = json.loads((DATA_DIR / "policies" / "POL-CHILL-01_v1.0.json").read_text())
    policy = active_policy(db_session)
    assert float(policy.max_temp_c) == document["policy"]["limits"]["max_temp_c"]
    assert policy.source_file.endswith("POL-CHILL-01_v1.0.json")


def test_seed_is_idempotent(db_session: Session) -> None:
    report = run_seed(db_session)
    assert report.created == []
    assert "policy POL-CHILL-01 v1.0" in report.unchanged


def test_changed_policy_content_for_existing_version_is_rejected(db_session: Session, tmp_path: Path) -> None:
    """CLAUDE.md rule 3: business rules never change silently; a new version is required."""
    data_dir = tmp_path / "data"
    shutil.copytree(DATA_DIR, data_dir)
    policy_file = data_dir / "policies" / "POL-CHILL-01_v1.0.json"
    document = json.loads(policy_file.read_text())
    document["policy"]["limits"]["max_temp_c"] = 9.0
    policy_file.write_text(json.dumps(document))
    with pytest.raises(SeedConflictError, match="immutable"):
        run_seed(db_session, data_dir)


def test_detector_config_is_seeded_and_immutable(db_session: Session, tmp_path: Path) -> None:
    """D-01 / C-01: the nominal interval lives in detector configuration, versioned like a policy."""
    report = run_seed(db_session)
    assert "detector config DET-BASELINE v1.0.0" in report.unchanged
    data_dir = tmp_path / "data"
    shutil.copytree(DATA_DIR, data_dir)
    config_file = data_dir / "detector" / "DET-BASELINE_v1.0.0.json"
    document = json.loads(config_file.read_text())
    document["max_continuous_interval_s"] = 400
    config_file.write_text(json.dumps(document))
    with pytest.raises(SeedConflictError, match="immutable"):
        run_seed(db_session, data_dir)
