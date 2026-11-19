"""Load reference data (policy, product, organizations, demo users) from JSON files.

Rules:

* Idempotent: running twice changes nothing.
* A policy version is immutable. If a file's content differs from the stored
  version (by SHA-256), loading fails instead of silently changing a business
  rule (CLAUDE.md rule 3). Publish a new ``policy_version`` instead.
* No shipments, readings or other operational records are seeded.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AppUser, DetectorConfigVersion, Organization, OrganizationChainRole, Policy, Product, UserRole,
)
from app.db.models.enums import OrgType, PolicyStatus, Role
from app.domain.rules import DetectorConfigError, parse_detector_config
from app.core.security import hash_password
from app.core.config import get_settings
from app.local_demo import provision_local_demo_accounts

DATA_DIR = Path(__file__).parent / "data"


class SeedConflictError(RuntimeError):
    """Stored reference data differs from the seed file."""


@dataclass
class SeedReport:
    created: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


def canonical_sha256(document: Any) -> str:
    raw = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp {value!r} in seed data has no timezone")
    return parsed


def load_policy_file(session: Session, path: Path, report: SeedReport) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    digest = canonical_sha256(document)
    p = document["product"]
    pol = document["policy"]

    product = session.get(Product, p["product_id"])
    if product is None:
        session.add(Product(product_id=p["product_id"], name=p["name"], category=p["category"],
                            description=p.get("description")))
        session.flush()  # no ORM relationships: insert the product before the policy that references it
        report.created.append(f"product {p['product_id']}")
    else:
        report.unchanged.append(f"product {p['product_id']}")

    existing = session.scalar(
        select(Policy).where(Policy.policy_code == pol["policy_code"],
                             Policy.policy_version == pol["policy_version"])
    )
    label = f"policy {pol['policy_code']} v{pol['policy_version']}"
    if existing is not None:
        if existing.content_sha256 != digest:
            raise SeedConflictError(
                f"{label} already exists with different content (stored sha256 {existing.content_sha256}, "
                f"file sha256 {digest}). Policy versions are immutable: create a new policy_version."
            )
        report.unchanged.append(label)
        return

    session.add(
        Policy(
            policy_code=pol["policy_code"],
            policy_version=pol["policy_version"],
            product_id=p["product_id"],
            status=PolicyStatus(pol["status"]),
            min_temp_c=Decimal(str(pol["limits"]["min_temp_c"])),
            max_temp_c=Decimal(str(pol["limits"]["max_temp_c"])),
            high_excursion_min_duration_min=int(pol["duration_rule"]["high_excursion_min_duration_min"]),
            low_excursion_min_duration_min=int(pol["duration_rule"]["low_excursion_min_duration_min"]),
            gap_unknown_after_min=int(pol["missing_data_rule"]["gap_unknown_after_min"]),
            gap_review_at_min=int(pol["missing_data_rule"]["gap_review_at_min"]),
            release_authority_role=Role(pol["release_authority_role"]),
            procedure_version=pol["procedure_version"],
            effective_from=_parse_utc(pol["effective_from"]),
            is_teaching_policy=bool(pol["is_teaching_policy"]),
            disclaimer=pol["disclaimer"],
            approval_reference=pol["approval_reference"],
            source_file=f"app/seed/data/policies/{path.name}",
            content_sha256=digest,
        )
    )
    report.created.append(label)


def load_organizations(session: Session, path: Path, report: SeedReport) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    for org in document["organizations"]:
        existing = session.get(Organization, org["org_id"])
        if existing is None:
            session.add(Organization(org_id=org["org_id"], name=org["name"], org_type=OrgType(org["org_type"])))
            report.created.append(f"organization {org['org_id']}")
        elif existing.org_type != OrgType(org["org_type"]):
            raise SeedConflictError(f"organization {org['org_id']} exists with a different org_type")
        else:
            report.unchanged.append(f"organization {org['org_id']}")
    session.flush()

    password_env = {
        "shipper.demo": "SHIPPER_DEMO_PASSWORD", "carrier.demo": "CARRIER_DEMO_PASSWORD",
        "quality.demo": "QUALITY_DEMO_PASSWORD", "warehouse.demo": "WAREHOUSE_DEMO_PASSWORD",
        "platform.admin": "ADMIN_DEMO_PASSWORD",
    }
    def demo_password(username: str) -> str | None:
        value = os.environ.get(password_env.get(username, ""), "")
        return value if value and value != "change-me-local-only" else None

    for u in document["users"]:
        password = demo_password(u["username"])
        user = session.scalar(select(AppUser).where(AppUser.username == u["username"]))
        if user is None:
            user = AppUser(username=u["username"], display_name=u["display_name"], org_id=u["org_id"],
                           is_demo_user=True,
                           password_hash=hash_password(password) if password and u["username"] != "monitor.service" else None)
            session.add(user)
            session.flush()
            report.created.append(f"user {u['username']}")
        elif user.org_id != u["org_id"]:
            raise SeedConflictError(f"user {u['username']} exists in a different organization")
        else:
            report.unchanged.append(f"user {u['username']}")
            if user.password_hash is None and user.username != "monitor.service" and password:
                user.password_hash = hash_password(password)
        for role in u["roles"]:
            if session.get(UserRole, (user.user_id, Role(role))) is None:
                session.add(UserRole(user_id=user.user_id, role=Role(role)))
                report.created.append(f"role {u['username']}:{role}")

    # Deterministic local Hardhat role accounts. The mnemonic is public demo material only.
    from eth_account import Account
    Account.enable_unaudited_hdwallet_features()
    settings = get_settings()
    chain_roles = {
        ("ORG-PLATFORM", Role.ADMIN): 0,
        ("ORG-SHIPPER", Role.SHIPPER): settings.chain_account_index_shipper,
        ("ORG-CARRIER", Role.CARRIER): settings.chain_account_index_carrier,
        ("ORG-RECEIVER", Role.QUALITY): settings.chain_account_index_quality,
        ("ORG-RECEIVER", Role.WAREHOUSE): settings.chain_account_index_warehouse,
        ("ORG-RECEIVER", Role.MONITOR): settings.chain_account_index_monitor,
    }
    for (org_id, role), index in chain_roles.items():
        account = Account.from_mnemonic(
            settings.chain_mnemonic.get_secret_value(), account_path=f"m/44'/60'/0'/0/{index}"
        )
        existing = session.get(OrganizationChainRole, (org_id, role))
        if existing is None:
            session.add(OrganizationChainRole(org_id=org_id, role=role, chain_address=account.address))
            report.created.append(f"chain role {org_id}:{role.value}")
        elif existing.chain_address.lower() != account.address.lower():
            raise SeedConflictError(f"chain role {org_id}:{role.value} differs from configured local account")
        else:
            report.unchanged.append(f"chain role {org_id}:{role.value}")


def load_detector_config_file(session: Session, path: Path, report: SeedReport) -> None:
    """Detector configuration versions are immutable, like policy versions (contract §5.3)."""
    document = json.loads(path.read_text(encoding="utf-8"))
    digest = canonical_sha256(document)
    try:
        parse_detector_config(document, digest)
    except DetectorConfigError as exc:
        raise SeedConflictError(f"{path.name}: invalid detector configuration ({exc})") from exc
    label = f"detector config {document['detector_code']} v{document['config_version']}"
    existing = session.scalar(
        select(DetectorConfigVersion).where(DetectorConfigVersion.detector_code == document["detector_code"],
                                            DetectorConfigVersion.config_version == document["config_version"])
    )
    if existing is not None:
        if existing.content_sha256 != digest:
            raise SeedConflictError(
                f"{label} already exists with different content (stored sha256 {existing.content_sha256}, "
                f"file sha256 {digest}). Detector configuration versions are immutable: create a new version.")
        report.unchanged.append(label)
        return
    session.add(DetectorConfigVersion(
        detector_code=document["detector_code"],
        config_version=document["config_version"],
        nominal_sampling_interval_s=document["nominal_sampling_interval_s"],
        max_continuous_interval_s=document["max_continuous_interval_s"],
        document=document,
        content_sha256=digest,
        source_file=f"app/seed/data/detector/{path.name}",
    ))
    report.created.append(label)


def run_seed(session: Session, data_dir: Path = DATA_DIR) -> SeedReport:
    report = SeedReport()
    settings = get_settings()
    database_was_empty = session.scalar(select(func.count()).select_from(AppUser)) == 0
    load_organizations(session, data_dir / "organizations.json", report)
    for policy_file in sorted((data_dir / "policies").glob("*.json")):
        load_policy_file(session, policy_file, report)
    for config_file in sorted((data_dir / "detector").glob("*.json")):
        load_detector_config_file(session, config_file, report)
    if settings.local_demo_mode:
        try:
            report.created.extend(provision_local_demo_accounts(
                session, database_was_empty=database_was_empty
            ))
        except RuntimeError as exc:
            raise SeedConflictError(str(exc)) from exc
    session.commit()
    return report
