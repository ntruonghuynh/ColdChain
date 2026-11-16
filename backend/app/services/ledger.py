"""Atomic business-event, outbox and signed-audit creation."""

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import AppUser, BusinessEvent, Incident, IncidentRevision, OutboxEntry, Policy, UserRole
from app.db.models.enums import BusinessEventType, OutboxStatus, Role
from app.integrations.audit_log import append_audit_entry


class BusinessReferenceConflict(AppError):
    status_code = 409
    code = "business_reference_conflict"


def canonical_payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def enqueue_business_event(
    session: Session, *, business_ref: str, event_type: BusinessEventType, shipment_id: str,
    actor_org_id: str, actor_user_id: uuid.UUID | None, payload: dict, occurred_at: datetime | None = None,
) -> tuple[BusinessEvent, bool]:
    """Create immutable event and outbox intent atomically; same ref/payload is idempotent."""
    digest = canonical_payload_hash(payload)
    existing = session.scalar(select(BusinessEvent).where(BusinessEvent.business_ref == business_ref))
    if existing is not None:
        if existing.payload_sha256 != digest or existing.event_type != event_type or existing.shipment_id != shipment_id:
            raise BusinessReferenceConflict("Business reference already exists with different event content")
        return existing, True
    event = BusinessEvent(
        event_id=uuid.uuid4(), business_ref=business_ref, event_type=event_type,
        shipment_id=shipment_id, actor_org_id=actor_org_id, actor_user_id=actor_user_id,
        occurred_at=occurred_at or datetime.now(UTC), payload=payload, payload_sha256=digest,
    )
    session.add(event)
    session.flush()
    session.add(OutboxEntry(event_id=event.event_id, status=OutboxStatus.PENDING, attempts=0))
    append_audit_entry(session, business_ref=business_ref, actor_user_id=actor_user_id,
                       actor_org_id=actor_org_id, action=event_type.value,
                       record={"event_id": str(event.event_id), "shipment_id": shipment_id,
                               "payload_sha256": digest, "payload": payload})
    session.flush()
    return event, False


def capture_unanchored_incidents(session: Session, *, limit: int = 50) -> int:
    """Recovery sweep for M3 incidents created by internal replay/detection paths.

    It does not alter detector outputs or revisions. The event, outbox intent, signed log entry,
    and one-time incident link are committed together by the caller.
    """
    from sqlalchemy import select

    monitor = session.scalar(select(AppUser).where(AppUser.username == "monitor.service"))
    monitor_role = (session.scalar(select(UserRole.user_id).where(
        UserRole.user_id == monitor.user_id, UserRole.role == Role.MONITOR,
        UserRole.revoked_at.is_(None),
    )) if monitor else None)
    if monitor is None or monitor_role is None:
        return 0
    incidents = session.scalars(select(Incident).where(Incident.business_event_id.is_(None))
                                .order_by(Incident.opened_at).with_for_update(skip_locked=True).limit(limit)).all()
    count = 0
    for incident in incidents:
        policy = session.get(Policy, incident.policy_id)
        revision = session.scalar(select(IncidentRevision).where(
            IncidentRevision.incident_id == incident.incident_id,
            IncidentRevision.revision == 1,
        ).limit(1))
        payload = {
            "incident_id": str(incident.incident_id), "category": incident.category.value,
            "sensor_id": incident.sensor_id, "interval_start": incident.interval_start.isoformat(),
            "interval_end": incident.interval_end.isoformat() if incident.interval_end else None,
            "policy_sha256": policy.content_sha256 if policy else None,
            "revision_id": str(revision.incident_revision_id) if revision else None,
            "revision": revision.revision if revision else None,
        }
        event, _ = enqueue_business_event(
            session, business_ref=incident.business_ref, event_type=BusinessEventType.INCIDENT_OPENED,
            shipment_id=incident.shipment_id, actor_org_id=monitor.org_id,
            actor_user_id=monitor.user_id, payload=payload, occurred_at=incident.opened_at,
        )
        incident.business_event_id = event.event_id
        count += 1
    session.flush()
    return count
