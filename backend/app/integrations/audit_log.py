"""Conventional Ed25519-signed, hash-chained PostgreSQL audit log."""

import hashlib
import hmac
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AuditLogEntry


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def _signer(org_id: str) -> Ed25519PrivateKey:
    value = get_settings().audit_signing_key.get_secret_value()
    try:
        master = bytes.fromhex(value)
        if len(master) != 32:
            raise ValueError
        seed = hmac.new(master, b"coldchain-audit-org:" + org_id.encode(), hashlib.sha256).digest()
        return Ed25519PrivateKey.from_private_bytes(seed)
    except ValueError as exc:
        raise RuntimeError("AUDIT_SIGNING_KEY must be a generated 32-byte hexadecimal seed") from exc


def append_audit_entry(
    session: Session, *, business_ref: str, actor_user_id, actor_org_id: str,
    action: str, record: dict,
) -> AuditLogEntry:
    """Append signed evidence in the same database transaction as the business event."""
    # Serialize allocation and predecessor selection across concurrent API workers.
    session.execute(text("SELECT pg_advisory_xact_lock(73910211)"))
    existing = session.scalar(select(AuditLogEntry).where(AuditLogEntry.business_ref == business_ref))
    if existing is not None:
        if existing.action != action or existing.record != record:
            raise ValueError("business reference conflicts with existing signed audit content")
        return existing
    previous = session.scalar(select(AuditLogEntry).order_by(AuditLogEntry.sequence_no.desc()).limit(1))
    sequence = (previous.sequence_no + 1) if previous else 1
    previous_hash = previous.entry_hash if previous else None
    signed_record = {
        "sequence_no": sequence, "business_ref": business_ref,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "actor_org_id": actor_org_id, "action": action, "record": record,
        "previous_hash": previous_hash,
    }
    digest = hashlib.sha256(_canonical(signed_record)).hexdigest()
    private_key = _signer(actor_org_id)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    row = AuditLogEntry(
        sequence_no=sequence, business_ref=business_ref, actor_user_id=actor_user_id,
        actor_org_id=actor_org_id, action=action, record=record, previous_hash=previous_hash,
        entry_hash=digest, signature=private_key.sign(bytes.fromhex(digest)), public_key=public_key,
    )
    session.add(row)
    session.flush()
    return row


def verify_audit_log(session: Session) -> dict[str, object]:
    rows = session.scalars(select(AuditLogEntry).order_by(AuditLogEntry.sequence_no)).all()
    previous_hash = None
    errors: list[dict[str, object]] = []
    for expected_seq, row in enumerate(rows, start=1):
        payload = {
            "sequence_no": row.sequence_no, "business_ref": row.business_ref,
            "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
            "actor_org_id": row.actor_org_id, "action": row.action, "record": row.record,
            "previous_hash": row.previous_hash,
        }
        digest = hashlib.sha256(_canonical(payload)).hexdigest()
        try:
            expected_public = _signer(row.actor_org_id or "").public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            Ed25519PublicKey.from_public_bytes(row.public_key).verify(row.signature, bytes.fromhex(digest))
            valid_signature = hmac.compare_digest(expected_public, row.public_key)
        except Exception:
            valid_signature = False
        if row.sequence_no != expected_seq or row.previous_hash != previous_hash or row.entry_hash != digest or not valid_signature:
            errors.append({"sequence_no": row.sequence_no, "business_ref": row.business_ref,
                           "sequence_valid": row.sequence_no == expected_seq,
                           "chain_valid": row.previous_hash == previous_hash,
                           "hash_valid": row.entry_hash == digest, "signature_valid": valid_signature})
        previous_hash = row.entry_hash
    return {"valid": not errors, "entries_checked": len(rows), "errors": errors}
