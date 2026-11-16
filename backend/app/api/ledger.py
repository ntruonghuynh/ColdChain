"""Read-only blockchain status, reconciliation and signed-audit endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import Envelope
from app.core.security import Principal, require_roles
from app.db.models import AuditLogEntry, BusinessEvent, ChainRecord, OutboxAttempt, OutboxEntry
from app.db.models.enums import Role
from app.db.session import get_db
from app.integrations.audit_log import verify_audit_log
from app.integrations.chain_gateway import ChainGateway

router = APIRouter(prefix="/ledger", tags=["blockchain and audit"])
READ_ROLES = (Role.ADMIN, Role.SHIPPER, Role.CARRIER, Role.QUALITY, Role.WAREHOUSE, Role.MONITOR)


@router.get("/transactions", response_model=Envelope[list[dict[str, object]]],
            summary="List business-event and chain transaction status")
def transactions(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db),
                 _principal: Principal = Depends(require_roles(*READ_ROLES))) -> Envelope[list[dict[str, object]]]:
    rows = db.execute(select(BusinessEvent, OutboxEntry, ChainRecord).join(
        OutboxEntry, OutboxEntry.event_id == BusinessEvent.event_id
    ).outerjoin(ChainRecord, ChainRecord.event_id == BusinessEvent.event_id)
      .order_by(BusinessEvent.created_at.desc()).limit(limit)).all()
    return Envelope(data=[{
        "event_id": str(event.event_id), "business_ref": event.business_ref,
        "event_type": event.event_type.value, "shipment_id": event.shipment_id,
        "outbox_status": outbox.status.value, "attempts": outbox.attempts,
        "last_error": outbox.last_error,
        "transaction": ({"chain_id": chain.chain_id, "contract_address": chain.contract_address,
                         "tx_hash": chain.tx_hash, "block_number": chain.block_number,
                         "confirmed_at": chain.confirmed_at.isoformat()} if chain else None),
    } for event, outbox, chain in rows])


@router.get("/verify/{business_ref}", response_model=Envelope[dict[str, object]],
            summary="Verify a business reference against its database and chain hashes")
def verify_business_reference(business_ref: str, db: Session = Depends(get_db),
                              _principal: Principal = Depends(require_roles(*READ_ROLES))) -> Envelope[dict[str, object]]:
    row = db.execute(select(BusinessEvent, OutboxEntry, ChainRecord).join(
        OutboxEntry, OutboxEntry.event_id == BusinessEvent.event_id
    ).outerjoin(ChainRecord, ChainRecord.event_id == BusinessEvent.event_id)
      .where(BusinessEvent.business_ref == business_ref)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Business reference not found")
    event, outbox, chain = row
    result: dict[str, object] = {
        "business_ref": business_ref,
        "event_type": event.event_type.value,
        "database_payload_sha256": event.payload_sha256,
        "evidence_sha256": event.payload.get("content_sha256"),
        "outbox_status": outbox.status.value,
        "chain_record_present": chain is not None,
        "verified": False,
    }
    try:
        gateway = ChainGateway()
        onchain = gateway.get_reference(business_ref)
        if onchain is None:
            result["verification_status"] = "MISSING_ON_CHAIN"
        else:
            expected_payload = "0x" + gateway.payload_hash_for(event).hex()
            expected_shipment = "0x" + gateway._hash(event.shipment_id).hex()
            result["chain_payload_sha256"] = onchain["payload_hash"]
            result["chain_shipment_key"] = onchain["shipment_key"]
            result["verified"] = (
                onchain["payload_hash"].lower() == expected_payload.lower()
                and onchain["shipment_key"].lower() == expected_shipment.lower()
                and outbox.status.value == "CONFIRMED" and chain is not None
            )
            result["verification_status"] = "MATCH" if result["verified"] else "MISMATCH"
    except Exception as exc:
        result["verification_status"] = "CHAIN_UNAVAILABLE"
        result["detail"] = type(exc).__name__
    return Envelope(data=result)


@router.get("/reconciliation", response_model=Envelope[dict[str, object]],
            summary="Compare PostgreSQL event/outbox evidence with on-chain state")
def reconciliation(db: Session = Depends(get_db),
                   _principal: Principal = Depends(require_roles(Role.ADMIN))) -> Envelope[dict[str, object]]:
    try:
        gateway = ChainGateway()
        connected = gateway.web3.is_connected()
    except Exception as exc:
        gateway, connected = None, False
        chain_error = type(exc).__name__
    else:
        chain_error = None
    events = db.execute(select(BusinessEvent, OutboxEntry, ChainRecord).join(
        OutboxEntry, OutboxEntry.event_id == BusinessEvent.event_id
    ).outerjoin(ChainRecord, ChainRecord.event_id == BusinessEvent.event_id)
      .order_by(BusinessEvent.created_at)).all()
    findings: list[dict[str, object]] = []
    categories: dict[str, int] = {}
    for event, outbox, chain in events:
        category = "OK"
        detail = None
        if outbox.status.value in {"PENDING", "RETRY", "SUBMITTED", "FAILED"}:
            category, detail = outbox.status.value, outbox.last_error
        elif not connected or gateway is None:
            category, detail = "CHAIN_UNAVAILABLE", chain_error or "RPC unavailable"
        else:
            try:
                onchain = gateway.get_reference(event.business_ref)
                if onchain is None:
                    category, detail = "MISSING_ON_CHAIN", "Database event has no matching chain reference"
                else:
                    expected_hash = "0x" + gateway.payload_hash_for(event).hex()
                    expected_shipment = "0x" + gateway._hash(event.shipment_id).hex()
                    if (onchain["payload_hash"].lower() != expected_hash.lower()
                            or onchain["shipment_key"].lower() != expected_shipment.lower()):
                        category, detail = "HASH_OR_REFERENCE_MISMATCH", "On-chain shipment or payload hash differs"
                    elif chain is None:
                        category, detail = "MISSING_DATABASE_CONFIRMATION", "Chain contains the ref but DB lacks ChainRecord"
            except Exception as exc:
                category, detail = "CHAIN_QUERY_ERROR", type(exc).__name__
        attempts = db.scalar(select(func.count()).select_from(OutboxAttempt).where(
            OutboxAttempt.event_id == event.event_id
        )) or 0
        if attempts > 1 and category == "OK":
            category, detail = "DUPLICATE_SUBMISSION_ATTEMPTS", f"{attempts} attempts; on-chain effect remains unique"
        categories[category] = categories.get(category, 0) + 1
        findings.append({"business_ref": event.business_ref, "event_type": event.event_type.value,
                         "shipment_id": event.shipment_id, "outbox_status": outbox.status.value,
                         "chain_record_present": chain is not None, "attempt_count": attempts,
                         "finding": category, "detail": detail})
    if connected and gateway is not None:
        onchain_logs = gateway.contract.events.BusinessAction().get_logs(from_block=0, to_block="latest")
        db_refs = {gateway.hash_ref(event.business_ref) for event, _, _ in events}
        unknown = [log["args"]["referenceHash"].hex() for log in onchain_logs
                   if log["args"]["referenceHash"] not in db_refs]
        if unknown:
            categories["ON_CHAIN_WITHOUT_DATABASE_RECORD"] = len(unknown)
    return Envelope(data={"checked_at": datetime.now(UTC).isoformat(), "chain_connected": connected,
                          "event_count": len(events), "counts_by_finding": categories,
                          "onchain_unknown_reference_hashes": unknown if connected and gateway else [],
                          "findings": findings})


@router.get("/audit", response_model=Envelope[list[dict[str, object]]], summary="List signed audit entries")
def audit_history(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db),
                  _principal: Principal = Depends(require_roles(*READ_ROLES))) -> Envelope[list[dict[str, object]]]:
    rows = db.scalars(select(AuditLogEntry).order_by(AuditLogEntry.sequence_no.desc()).limit(limit)).all()
    return Envelope(data=[{"sequence_no": row.sequence_no, "business_ref": row.business_ref,
                           "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                           "actor_org_id": row.actor_org_id, "action": row.action,
                           "record": row.record, "previous_hash": row.previous_hash,
                           "entry_hash": row.entry_hash, "signature": row.signature.hex(),
                           "public_key": row.public_key.hex(), "created_at": row.created_at.isoformat()}
                          for row in rows])


@router.get("/audit/verify", response_model=Envelope[dict[str, object]], summary="Verify signed audit chain")
def audit_verify(db: Session = Depends(get_db),
                 _principal: Principal = Depends(require_roles(Role.ADMIN))) -> Envelope[dict[str, object]]:
    return Envelope(data=verify_audit_log(db))
