"""Read-only recovery inventory for historical M5 INCIDENT_OPENED failures.

Run only inside the backend container against the active chain. This script contains no write
operations and deliberately has no execution mode. Its stdout can be saved as a raw JSON report.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict

from sqlalchemy import select

from app.db.models import (
    BusinessEvent,
    ChainRecord,
    Incident,
    IncidentRevision,
    OutboxAttempt,
    OutboxEntry,
)
from app.db.models.enums import BusinessEventType, OutboxStatus
from app.db.session import get_sessionmaker
from app.integrations.chain_gateway import ChainGateway

STATE_NAMES = ("NONE", "CREATED", "IN_TRANSIT", "DELIVERED", "RELEASE_APPROVED", "QUARANTINED", "RELEASED")


def stable_ref(prefix: str, value: str) -> str:
    return f"M5-RECOVERY-{prefix}-{hashlib.sha256(value.encode()).hexdigest()[:24]}"


def main() -> None:
    gateway = ChainGateway()
    if not gateway.web3.is_connected():
        raise RuntimeError("active chain is unavailable; no recovery inventory emitted")

    with get_sessionmaker()() as session:
        events = session.scalars(
            select(BusinessEvent)
            .join(OutboxEntry, OutboxEntry.event_id == BusinessEvent.event_id)
            .where(BusinessEvent.event_type == BusinessEventType.INCIDENT_OPENED,
                   OutboxEntry.status == OutboxStatus.FAILED)
            .order_by(BusinessEvent.shipment_id, BusinessEvent.occurred_at, BusinessEvent.event_id)
        ).all()
        by_shipment: dict[str, list] = defaultdict(list)
        for event in events:
            by_shipment[event.shipment_id].append(event)

        shipment_inventory = []
        missing_registration_count = 0
        for shipment_id, shipment_events in sorted(by_shipment.items()):
            raw_state = gateway.contract.functions.shipments(gateway._hash(shipment_id)).call()
            state_index = int(raw_state[0])
            state_name = STATE_NAMES[state_index] if 0 <= state_index < len(STATE_NAMES) else f"UNKNOWN_{state_index}"
            registration_events = session.scalars(
                select(BusinessEvent).where(
                    BusinessEvent.shipment_id == shipment_id,
                    BusinessEvent.event_type == BusinessEventType.SHIPMENT_REGISTERED,
                ).order_by(BusinessEvent.occurred_at, BusinessEvent.event_id)
            ).all()
            current_incidents = []
            for event in shipment_events:
                incident = session.scalar(select(Incident).where(Incident.business_ref == event.business_ref))
                revisions = session.scalars(
                    select(IncidentRevision).where(IncidentRevision.incident_id == incident.incident_id)
                    .order_by(IncidentRevision.revision)
                ).all() if incident else []
                outbox = session.get(OutboxEntry, event.event_id)
                db_chain_record = session.scalar(
                    select(ChainRecord).where(ChainRecord.event_id == event.event_id)
                )
                attempts = session.scalars(
                    select(OutboxAttempt).where(OutboxAttempt.event_id == event.event_id)
                    .order_by(OutboxAttempt.attempt_number)
                ).all()
                on_chain_reference = gateway.get_reference(event.business_ref)
                expected_payload_hash = "0x" + gateway.payload_hash_for(event).hex()
                expected_shipment_key = "0x" + gateway._hash(shipment_id).hex()
                current_incidents.append({
                    "event_id": str(event.event_id),
                    "business_ref": event.business_ref,
                    "payload_sha256": event.payload_sha256,
                    "original_occurred_at": event.occurred_at.isoformat(),
                    "business_event_created_at": event.created_at.isoformat(),
                    "incident_id_in_original_payload": event.payload.get("incident_id"),
                    "evidence_revision_id_in_original_payload": event.payload.get("evidence_revision_id")
                    or event.payload.get("revision_id"),
                    "current_incident": {
                        "exists": incident is not None,
                        "incident_id": str(incident.incident_id) if incident else None,
                        "current_status": incident.status.value if incident else None,
                        "current_category": incident.category.value if incident else None,
                        "opened_at": incident.opened_at.isoformat() if incident else None,
                        "closed_at": incident.closed_at.isoformat() if incident and incident.closed_at else None,
                        "revision_count": len(revisions),
                        "revision_ids": [str(r.incident_revision_id) for r in revisions],
                        "latest_revision": revisions[-1].revision if revisions else None,
                    },
                    "outbox_status": outbox.status.value if outbox else None,
                    "database_chain_record_present": db_chain_record is not None,
                    "original_incident_reference_present_on_chain": on_chain_reference is not None,
                    "on_chain_payload_matches_original": bool(
                        on_chain_reference and on_chain_reference["payload_hash"].lower() == expected_payload_hash.lower()
                    ),
                    "on_chain_shipment_matches_original": bool(
                        on_chain_reference and on_chain_reference["shipment_key"].lower() == expected_shipment_key.lower()
                    ),
                    "outbox_attempts": [{
                        "attempt_number": attempt.attempt_number,
                        "started_at": attempt.started_at.isoformat(),
                        "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
                        "outcome": attempt.outcome,
                        "transaction_hash": attempt.tx_hash,
                        "error_type": (attempt.error.split(":", 1)[0] if attempt.error else None),
                    } for attempt in attempts],
                    "proposed_deterministic_compensation_ref_for_review_only": stable_ref("INC", str(event.event_id)),
                })

            registrations = []
            for event in registration_events:
                chain_ref = gateway.get_reference(event.business_ref)
                registrations.append({
                    "event_id": str(event.event_id),
                    "business_ref": event.business_ref,
                    "outbox_status": (session.get(OutboxEntry, event.event_id).status.value
                                      if session.get(OutboxEntry, event.event_id) else None),
                    "on_chain_reference_present": chain_ref is not None,
                    "on_chain_payload_sha256": chain_ref.get("payload_hash") if chain_ref else None,
                })
            registration_required = state_name == "NONE"
            missing_registration_count += int(registration_required)
            proposed_registration_ref = stable_ref("REG", shipment_id)
            on_chain_registration_ref_used = gateway.contract.functions.isReferenceUsed(
                gateway.hash_ref(proposed_registration_ref)
            ).call()
            db_registration_collision = session.scalar(
                select(BusinessEvent.event_id).where(BusinessEvent.business_ref == proposed_registration_ref)
            ) is not None
            shipment_inventory.append({
                "shipment_id": shipment_id,
                "failed_incident_event_count": len(shipment_events),
                "current_on_chain_state": state_name,
                "on_chain_incident_count": int(raw_state[3]),
                "on_chain_reviewed_incident_count": int(raw_state[4]),
                "has_on_chain_disposition": bool(raw_state[5]),
                "shipper_registration_required_by_current_chain_state": registration_required,
                "existing_database_registration_events": registrations,
                "proposed_deterministic_shipper_registration_ref_for_review_only": proposed_registration_ref,
                "proposed_registration_ref_collision_in_database": db_registration_collision,
                "proposed_registration_ref_used_on_chain": on_chain_registration_ref_used,
                "incidents": current_incidents,
            })

        proposed_refs = []
        for shipment in shipment_inventory:
            proposed_refs.append(shipment["proposed_deterministic_shipper_registration_ref_for_review_only"])
            proposed_refs.extend(i["proposed_deterministic_compensation_ref_for_review_only"]
                                 for i in shipment["incidents"])
        collisions = []
        for reference in proposed_refs:
            in_database = session.scalar(
                select(BusinessEvent.event_id).where(BusinessEvent.business_ref == reference)
            ) is not None
            in_chain = gateway.contract.functions.isReferenceUsed(gateway.hash_ref(reference)).call()
            if in_database or in_chain:
                collisions.append({"business_ref": reference, "database": in_database, "chain": in_chain})
        output = {
            "run_type": "READ_ONLY_DRY_RUN_NO_WRITES",
            "chain_id": gateway.web3.eth.chain_id,
            "contract_address": gateway.address,
            "failed_incident_opened_event_count": len(events),
            "unique_shipment_count": len(by_shipment),
            "shipments_requiring_shipper_registration_by_current_on_chain_state": missing_registration_count,
            "current_on_chain_state_counts": dict(Counter(s["current_on_chain_state"] for s in shipment_inventory)),
            "incident_current_status_counts": dict(Counter(
                incident["current_incident"]["current_status"] or "MISSING"
                for shipment in shipment_inventory for incident in shipment["incidents"]
            )),
            "revision_count_distribution": dict(Counter(
                str(incident["current_incident"]["revision_count"])
                for shipment in shipment_inventory for incident in shipment["incidents"]
            )),
            "deterministic_proposed_reference_collision_count": len(collisions),
            "deterministic_proposed_reference_collisions": collisions,
            "shipment_inventory": shipment_inventory,
        }
        print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
