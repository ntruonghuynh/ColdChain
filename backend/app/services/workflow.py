"""Authenticated custody, quality disposition and warehouse-release commands."""

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import Principal
from app.db.models import (
    BusinessEvent, ChainRecord, CustodyEvent, DecisionReassessment, Disposition,
    DispositionIncident, Incident, IncidentRevision, OutboxEntry, Policy,
    ReassessmentResolution, Shipment, WarehouseRelease,
)
from app.db.models.enums import (
    BusinessEventType, CustodyStage, Decision, OutboxStatus, Role, ShipmentStatus,
)
from app.services.ledger import enqueue_business_event


class WorkflowConflict(AppError):
    status_code = 409
    code = "workflow_conflict"


def _shipment(session: Session, shipment_id: str) -> Shipment:
    shipment = session.get(Shipment, shipment_id)
    if shipment is None:
        raise AppError(f"Shipment {shipment_id} not found", status_code=404, code="not_found")
    return shipment


def _policy_hash(session: Session, shipment: Shipment) -> str:
    policy = session.get(Policy, shipment.policy_id)
    if policy is None:
        raise WorkflowConflict("Shipment policy is missing")
    return policy.content_sha256


def _lock_shipment(session: Session, shipment_id: str) -> None:
    # Share the advisory-lock namespace with live ingestion so late-evidence reassessment
    # and quality actions serialize on the same shipment.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                    {"key": f"coldchain.ingest:{shipment_id}"})


def _response(event: BusinessEvent, replay: bool) -> dict[str, object]:
    return {"business_ref": event.business_ref, "event_id": str(event.event_id),
            "status": "CONFIRMED" if replay else "PENDING_CONFIRMATION", "idempotent_replay": replay}


def register_shipment(session: Session, *, shipment_id: str, business_ref: str,
                      principal: Principal) -> dict[str, object]:
    _lock_shipment(session, shipment_id)
    shipment = _shipment(session, shipment_id)
    if Role.SHIPPER not in principal.roles or shipment.shipper_org_id != principal.user.org_id:
        raise AppError("Only the assigned shipper may register this shipment", status_code=403, code="forbidden")
    payload = {"policy_hash": _policy_hash(session, shipment)}
    existing = session.scalar(select(BusinessEvent).where(BusinessEvent.business_ref == business_ref))
    if existing is not None:
        if (existing.event_type == BusinessEventType.SHIPMENT_REGISTERED and existing.shipment_id == shipment_id
                and existing.payload == payload):
            outbox = session.get(OutboxEntry, existing.event_id)
            return _response(existing, bool(outbox and outbox.status == OutboxStatus.CONFIRMED))
        raise WorkflowConflict("Shipment business reference conflicts with an existing event")
    if shipment.status != ShipmentStatus.CREATED:
        raise WorkflowConflict("Shipment registration is only valid from CREATED")
    event, replay = enqueue_business_event(
        session, business_ref=business_ref, event_type=BusinessEventType.SHIPMENT_REGISTERED,
        shipment_id=shipment_id, actor_org_id=principal.user.org_id,
        actor_user_id=principal.user.user_id, payload=payload,
    )
    return _response(event, replay)


def accept_custody(session: Session, *, shipment_id: str, business_ref: str,
                   stage: CustodyStage, principal: Principal) -> dict[str, object]:
    _lock_shipment(session, shipment_id)
    shipment = _shipment(session, shipment_id)
    if stage == CustodyStage.PICKUP:
        role, expected_org, required_status = Role.CARRIER, shipment.carrier_org_id, ShipmentStatus.CREATED
        from_org, to_org = shipment.shipper_org_id, shipment.carrier_org_id
    else:
        role, expected_org, required_status = Role.WAREHOUSE, shipment.receiver_org_id, ShipmentStatus.IN_TRANSIT
        from_org, to_org = shipment.carrier_org_id, shipment.receiver_org_id
    if role not in principal.roles or principal.user.org_id != expected_org:
        raise AppError("This account cannot accept custody at this stage", status_code=403, code="forbidden")
    payload = {"stage": stage.value, "signing_role": role.value, "from_org": from_org, "to_org": to_org}
    existing = session.scalar(select(CustodyEvent).where(CustodyEvent.business_ref == business_ref))
    if existing is not None:
        event = session.get(BusinessEvent, existing.business_event_id) if existing.business_event_id else None
        if event and event.shipment_id == shipment_id and event.payload == payload:
            outbox = session.get(OutboxEntry, event.event_id)
            return _response(event, bool(outbox and outbox.status == OutboxStatus.CONFIRMED))
        raise WorkflowConflict("Custody business reference conflicts with an existing record")
    if shipment.status != required_status:
        raise WorkflowConflict(f"{stage.value} custody cannot be accepted while shipment is {shipment.status.value}")
    if stage == CustodyStage.PICKUP:
        registered = session.scalar(select(BusinessEvent.event_id).join(OutboxEntry).where(
            BusinessEvent.shipment_id == shipment_id,
            BusinessEvent.event_type == BusinessEventType.SHIPMENT_REGISTERED,
            OutboxEntry.status == OutboxStatus.CONFIRMED,
        ).limit(1))
        if registered is None:
            raise WorkflowConflict("Pickup custody requires confirmed shipment registration")
    already_pending = session.scalar(select(BusinessEvent.event_id).join(OutboxEntry).where(
        BusinessEvent.shipment_id == shipment_id,
        BusinessEvent.event_type == BusinessEventType.CUSTODY_ACCEPTED,
        BusinessEvent.payload["stage"].astext == stage.value,
        OutboxEntry.status != OutboxStatus.FAILED,
    ).limit(1))
    if already_pending:
        raise WorkflowConflict(f"A {stage.value} custody acceptance is already recorded")
    event, replay = enqueue_business_event(
        session, business_ref=business_ref, event_type=BusinessEventType.CUSTODY_ACCEPTED,
        shipment_id=shipment_id, actor_org_id=principal.user.org_id,
        actor_user_id=principal.user.user_id, payload=payload,
    )
    custody = CustodyEvent(
        custody_event_id=uuid.uuid4(), business_ref=business_ref, shipment_id=shipment_id,
        stage=stage, from_org_id=from_org, to_org_id=to_org,
        accepted_by_user_id=principal.user.user_id, accepted_at=datetime.now(UTC),
        business_event_id=event.event_id,
    )
    session.add(custody)
    session.flush()
    return _response(event, replay)


def record_disposition(session: Session, *, shipment_id: str, business_ref: str,
                       decision: Decision, rationale: str, incident_refs: list[str],
                       principal: Principal) -> dict[str, object]:
    _lock_shipment(session, shipment_id)
    shipment = _shipment(session, shipment_id)
    if Role.QUALITY not in principal.roles or principal.user.org_id != shipment.receiver_org_id:
        raise AppError("Only the receiving organization's Quality Officer may decide this shipment",
                       status_code=403, code="forbidden")
    if session.scalar(select(Disposition.disposition_id).where(Disposition.business_ref == business_ref)):
        prior = session.scalar(select(Disposition).where(Disposition.business_ref == business_ref))
        if prior and prior.shipment_id == shipment_id and prior.decision == decision and prior.rationale == rationale.strip():
            event = session.get(BusinessEvent, prior.business_event_id)
            outbox = session.get(OutboxEntry, event.event_id) if event else None
            if event:
                return _response(event, bool(outbox and outbox.status == OutboxStatus.CONFIRMED))
        raise WorkflowConflict("Disposition business reference conflicts with an existing decision")
    prior = session.scalar(select(Disposition).where(Disposition.shipment_id == shipment_id).order_by(Disposition.decided_at.desc()).limit(1))
    unresolved_reassessments = []
    if prior:
        unresolved_reassessments = session.scalars(select(DecisionReassessment).where(
            DecisionReassessment.disposition_id == prior.disposition_id,
            ~DecisionReassessment.reassessment_id.in_(select(ReassessmentResolution.reassessment_id)),
        )).all()
        if not unresolved_reassessments:
            raise WorkflowConflict("A disposition is final; a new disposition requires an unresolved reassessment")
        if not any(item.reason.value == "NEW_INCIDENT_AFTER_DISPOSITION" for item in unresolved_reassessments):
            raise WorkflowConflict("Evidence revisions require a review; changing a decision requires a new incident")
        if session.scalar(select(WarehouseRelease.release_id).where(WarehouseRelease.disposition_id == prior.disposition_id)):
            raise WorkflowConflict("A physical warehouse release cannot be reversed by a new disposition")
    if shipment.status != ShipmentStatus.DELIVERED and not (
        unresolved_reassessments and shipment.status == ShipmentStatus.AWAITING_DISPOSITION
    ):
        raise WorkflowConflict("Quality disposition requires confirmed delivery or a new incident reassessment")
    open_incidents = session.scalars(select(Incident).where(
        Incident.shipment_id == shipment_id, Incident.status == "OPEN"
    ).order_by(Incident.business_ref)).all()
    required_refs = {incident.business_ref for incident in open_incidents}
    if set(incident_refs) != required_refs:
        raise WorkflowConflict("Disposition must reference every open incident and no other incident")
    all_incidents = session.scalars(select(Incident).where(
        Incident.shipment_id == shipment_id
    ).order_by(Incident.business_ref)).all()
    for incident in all_incidents:
        incident_event = session.get(BusinessEvent, incident.business_event_id) if incident.business_event_id else None
        incident_outbox = session.get(OutboxEntry, incident_event.event_id) if incident_event else None
        if incident_outbox is None or incident_outbox.status != OutboxStatus.CONFIRMED:
            raise WorkflowConflict("All incident evidence references must be confirmed on chain before disposition")
    latest_revisions = []
    for incident in all_incidents:
        revision = session.scalar(select(IncidentRevision).where(
            IncidentRevision.incident_id == incident.incident_id
        ).order_by(IncidentRevision.revision.desc()).limit(1))
        latest_revisions.append({"incident_ref": incident.business_ref,
                                 "revision": revision.revision if revision else None,
                                 "revision_id": str(revision.incident_revision_id) if revision else None})
    policy_hash = _policy_hash(session, shipment)
    evidence = {"policy_hash": policy_hash, "incident_revisions": latest_revisions}
    evidence_hash = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    payload = {"decision": decision.value, "policy_hash": policy_hash,
               "incident_refs": sorted(incident.business_ref for incident in all_incidents),
               "evidence_sha256": evidence_hash,
               "rationale_sha256": hashlib.sha256(rationale.strip().encode()).hexdigest()}
    event, replay = enqueue_business_event(
        session, business_ref=business_ref, event_type=BusinessEventType.DISPOSITION_RECORDED,
        shipment_id=shipment_id, actor_org_id=principal.user.org_id,
        actor_user_id=principal.user.user_id, payload=payload,
    )
    disposition = Disposition(
        disposition_id=uuid.uuid4(), business_ref=business_ref, shipment_id=shipment_id,
        decision=decision, decided_by_user_id=principal.user.user_id, decided_by_role=Role.QUALITY,
        decided_at=datetime.now(UTC), rationale=rationale.strip(), evidence_sha256=evidence_hash,
        policy_id=shipment.policy_id, business_event_id=event.event_id,
    )
    session.add(disposition)
    session.flush()
    for incident in open_incidents:
        session.add(DispositionIncident(disposition_id=disposition.disposition_id,
                                        incident_id=incident.incident_id, shipment_id=shipment_id))
    for reassessment in unresolved_reassessments:
        session.add(ReassessmentResolution(
            reassessment_id=reassessment.reassessment_id,
            disposition_id=disposition.disposition_id,
            resolved_by_user_id=principal.user.user_id,
            resolved_at=datetime.now(UTC),
            review_note_sha256=hashlib.sha256(b"resolved-by-new-quality-disposition").hexdigest(),
        ))
    session.flush()
    return _response(event, replay)


def review_reassessment(session: Session, *, shipment_id: str, reassessment_id: uuid.UUID,
                       review_note: str, principal: Principal) -> dict[str, object]:
    _lock_shipment(session, shipment_id)
    shipment = _shipment(session, shipment_id)
    if Role.QUALITY not in principal.roles or principal.user.org_id != shipment.receiver_org_id:
        raise AppError("Only the receiving organization's Quality Officer may review reassessment",
                       status_code=403, code="forbidden")
    reassessment = session.get(DecisionReassessment, reassessment_id)
    if reassessment is None or reassessment.shipment_id != shipment_id:
        raise AppError("Reassessment not found", status_code=404, code="not_found")
    if session.get(ReassessmentResolution, reassessment_id) is not None:
        return {"reassessment_id": str(reassessment_id), "status": "REVIEWED", "idempotent_replay": True}
    prior = session.get(Disposition, reassessment.disposition_id)
    assert prior is not None
    note_hash = hashlib.sha256(review_note.strip().encode()).hexdigest()
    resolution = ReassessmentResolution(
        reassessment_id=reassessment_id, disposition_id=prior.disposition_id,
        resolved_by_user_id=principal.user.user_id, resolved_at=datetime.now(UTC),
        review_note_sha256=note_hash, review_note=review_note.strip(),
    )
    session.add(resolution)
    from app.integrations.audit_log import append_audit_entry
    append_audit_entry(session, business_ref=f"reassessment-review:{reassessment_id}",
                       actor_user_id=principal.user.user_id, actor_org_id=principal.user.org_id,
                       action="REASSESSMENT_REVIEWED",
                       record={"shipment_id": shipment_id, "reassessment_id": str(reassessment_id),
                               "prior_disposition_id": str(prior.disposition_id),
                               "outcome": "RETAIN_EXISTING_DISPOSITION", "review_note": review_note.strip(),
                               "review_note_sha256": note_hash})
    session.flush()
    return {"reassessment_id": str(reassessment_id), "status": "REVIEWED",
            "outcome": "RETAIN_EXISTING_DISPOSITION", "idempotent_replay": False}


def release_warehouse(session: Session, *, shipment_id: str, business_ref: str,
                      principal: Principal) -> dict[str, object]:
    _lock_shipment(session, shipment_id)
    shipment = _shipment(session, shipment_id)
    if Role.WAREHOUSE not in principal.roles or principal.user.org_id != shipment.receiver_org_id:
        raise AppError("Only the receiving organization's warehouse operator may release goods",
                       status_code=403, code="forbidden")
    disposition = session.scalar(select(Disposition).where(
        Disposition.shipment_id == shipment_id, Disposition.decision == Decision.RELEASE
    ).order_by(Disposition.decided_at.desc()).limit(1))
    if disposition is None:
        raise WorkflowConflict("Warehouse release requires a Quality Officer RELEASE decision")
    existing_release = session.scalar(select(WarehouseRelease).where(WarehouseRelease.business_ref == business_ref))
    if existing_release is not None:
        event = session.get(BusinessEvent, existing_release.business_event_id) if existing_release.business_event_id else None
        if event and event.shipment_id == shipment_id and event.payload == {
            "disposition_ref": disposition.business_ref,
            "disposition_event_id": str(disposition.business_event_id),
        }:
            outbox = session.get(OutboxEntry, event.event_id)
            return _response(event, bool(outbox and outbox.status == OutboxStatus.CONFIRMED))
        raise WorkflowConflict("Warehouse release business reference conflicts with an existing record")
    outbox = session.get(OutboxEntry, disposition.business_event_id)
    if outbox is None or outbox.status != OutboxStatus.CONFIRMED:
        raise WorkflowConflict("Quality RELEASE decision has not been confirmed on chain")
    if shipment.status != ShipmentStatus.RELEASE_APPROVED:
        raise WorkflowConflict("Shipment is not in RELEASE_APPROVED state")
    if session.scalar(select(WarehouseRelease.release_id).where(WarehouseRelease.shipment_id == shipment_id)):
        raise WorkflowConflict("Shipment has already been released")
    payload = {"disposition_ref": disposition.business_ref,
               "disposition_event_id": str(disposition.business_event_id)}
    event, replay = enqueue_business_event(
        session, business_ref=business_ref, event_type=BusinessEventType.WAREHOUSE_RELEASED,
        shipment_id=shipment_id, actor_org_id=principal.user.org_id,
        actor_user_id=principal.user.user_id, payload=payload,
    )
    row = WarehouseRelease(
        release_id=uuid.uuid4(), business_ref=business_ref, shipment_id=shipment_id,
        disposition_id=disposition.disposition_id, disposition_decision=Decision.RELEASE,
        released_by_user_id=principal.user.user_id, released_at=datetime.now(UTC),
        business_event_id=event.event_id,
    )
    session.add(row)
    session.flush()
    return _response(event, replay)
