"""Helpers that build minimal valid rows for constraint tests (test-only data)."""

import hashlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppUser, Disposition, IngestBatch, Policy, Sensor, Shipment
from app.db.models.enums import DataOrigin, Decision, IngestSource

T0 = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def active_policy(session: Session) -> Policy:
    return session.scalars(select(Policy).where(Policy.policy_code == "POL-CHILL-01")).one()


def user(session: Session, username: str) -> AppUser:
    return session.scalars(select(AppUser).where(AppUser.username == username)).one()


def make_shipment(session: Session, shipment_id: str | None = None) -> Shipment:
    policy = active_policy(session)
    shipment = Shipment(
        shipment_id=shipment_id or f"TEST-SHP-{uuid.uuid4().hex[:8]}",
        product_id=policy.product_id,
        policy_id=policy.policy_id,
        shipper_org_id="ORG-SHIPPER",
        carrier_org_id="ORG-CARRIER",
        receiver_org_id="ORG-RECEIVER",
        data_origin=DataOrigin.SIMULATED,
    )
    session.add(shipment)
    session.flush()
    return shipment


def make_sensor(session: Session) -> Sensor:
    sensor = Sensor(sensor_id=f"TEST-SNS-{uuid.uuid4().hex[:8]}", sensor_type="TEMPERATURE_LOGGER")
    session.add(sensor)
    session.flush()
    return sensor


def make_batch(session: Session, shipment: Shipment) -> IngestBatch:
    batch = IngestBatch(
        business_ref=f"TEST-BATCH-{uuid.uuid4().hex[:8]}",
        shipment_id=shipment.shipment_id,
        submitted_by_org_id="ORG-CARRIER",
        source=IngestSource.SIMULATOR,
        data_origin=DataOrigin.SIMULATED,
        received_at=T0,
    )
    session.add(batch)
    session.flush()
    return batch


def make_disposition(session: Session, shipment: Shipment, decision: Decision,
                     username: str = "quality.demo", **overrides: object) -> Disposition:
    disposition = Disposition(
        business_ref=f"TEST-DISP-{uuid.uuid4().hex[:8]}",
        shipment_id=shipment.shipment_id,
        decision=decision,
        decided_by_user_id=user(session, username).user_id,
        decided_at=T0,
        rationale="Test rationale",
        policy_id=shipment.policy_id,
        **overrides,
    )
    session.add(disposition)
    session.flush()
    return disposition


__all__ = ["Decimal", "T0", "active_policy", "make_batch", "make_disposition", "make_sensor",
           "make_shipment", "sha", "user"]
