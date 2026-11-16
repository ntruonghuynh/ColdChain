"""Retry-safe PostgreSQL outbox relay for the local Hardhat chain."""

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, not_, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.models import BusinessEvent, ChainRecord, Disposition, Incident, OutboxAttempt, OutboxEntry, Shipment, WarehouseRelease
from app.db.models.enums import BusinessEventType, IncidentStatus, OutboxStatus, ShipmentStatus
from app.db.session import get_sessionmaker
from app.integrations.chain_gateway import ChainGateway, ChainUnavailable, ContractRevert, normalize_tx_hash
from app.services.ledger import capture_unanchored_incidents
from app.worker.status import worker_status

logger = logging.getLogger("coldchain.outbox")


def _claim(session: Session) -> tuple[BusinessEvent, OutboxEntry, OutboxAttempt] | None:
    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=60)
    event = aliased(BusinessEvent)
    registration_event = aliased(BusinessEvent)
    registration_outbox = aliased(OutboxEntry)
    registration_confirmed = exists(
        select(registration_event.event_id)
        .join(registration_outbox, registration_outbox.event_id == registration_event.event_id)
        .where(
            registration_event.shipment_id == event.shipment_id,
            registration_event.event_type == BusinessEventType.SHIPMENT_REGISTERED,
            registration_outbox.status == OutboxStatus.CONFIRMED,
        )
    )
    registration_required = event.event_type.in_((BusinessEventType.SENSOR_BATCH_ANCHORED,
                                                   BusinessEventType.INCIDENT_OPENED))
    entry = session.scalar(
        select(OutboxEntry).where(
            (
                (OutboxEntry.status.in_([OutboxStatus.PENDING, OutboxStatus.RETRY]) &
                 (OutboxEntry.next_attempt_at.is_(None) | (OutboxEntry.next_attempt_at <= now))) |
                ((OutboxEntry.status == OutboxStatus.SUBMITTED) & (OutboxEntry.updated_at <= stale_before))
            ),
        )
        .join(event, event.event_id == OutboxEntry.event_id)
        .where(or_(not_(registration_required), registration_confirmed))
        .order_by(OutboxEntry.updated_at)
        .with_for_update(skip_locked=True, of=OutboxEntry)
        .limit(1)
    )
    if entry is None:
        return None
    if entry.status == OutboxStatus.SUBMITTED:
        stale_attempt = session.scalar(select(OutboxAttempt).where(
            OutboxAttempt.event_id == entry.event_id
        ).order_by(OutboxAttempt.attempt_number.desc()).limit(1))
        if stale_attempt is not None and stale_attempt.outcome == "STARTED":
            stale_attempt.outcome = "UNCERTAIN"
            stale_attempt.error = "worker stopped before recording a submission result"
            stale_attempt.finished_at = now
    event = session.get(BusinessEvent, entry.event_id)
    assert event is not None
    entry.attempts += 1
    entry.status = OutboxStatus.SUBMITTED
    entry.last_error = None
    entry.next_attempt_at = None
    entry.updated_at = now
    attempt = OutboxAttempt(
        attempt_id=uuid.uuid4(), event_id=entry.event_id, attempt_number=entry.attempts,
        started_at=now, outcome="STARTED",
    )
    session.add(attempt)
    session.flush()
    return event, entry, attempt


def _confirm(session: Session, gateway: ChainGateway, event: BusinessEvent,
             entry: OutboxEntry, attempt: OutboxAttempt,
             tx_data: dict[str, int | str], confirmations: int) -> None:
    tx_hash = normalize_tx_hash(tx_data["tx_hash"])
    session.add(ChainRecord(
        chain_record_id=uuid.uuid4(), event_id=event.event_id, chain_id=gateway.settings.chain_id,
        contract_address=gateway.address, onchain_ref="0x" + gateway.hash_ref(event.business_ref).hex(),
        tx_hash=tx_hash, block_number=int(tx_data["block_number"]), log_index=int(tx_data["log_index"]),
        confirmed_at=datetime.now(UTC),
    ))
    attempt.outcome = "CONFIRMED"
    attempt.tx_hash = tx_hash
    attempt.finished_at = datetime.now(UTC)
    entry.status = OutboxStatus.CONFIRMED
    entry.last_error = None
    entry.updated_at = datetime.now(UTC)
    shipment = session.get(Shipment, event.shipment_id)
    if shipment is not None:
        if event.event_type.value == "CUSTODY_ACCEPTED":
            shipment.status = (ShipmentStatus.DELIVERED if event.payload["stage"] == "DELIVERY"
                               else ShipmentStatus.IN_TRANSIT)
        elif event.event_type.value == "DISPOSITION_RECORDED":
            shipment.status = (ShipmentStatus.RELEASE_APPROVED if event.payload["decision"] == "RELEASE"
                               else ShipmentStatus.QUARANTINED)
            for incident in session.scalars(select(Incident).where(
                Incident.shipment_id == event.shipment_id,
                Incident.business_ref.in_(event.payload.get("incident_refs", [])),
                Incident.status == IncidentStatus.OPEN,
            )).all():
                incident.status = IncidentStatus.CLOSED
                incident.closed_at = datetime.now(UTC)
        elif event.event_type.value == "WAREHOUSE_RELEASED":
            shipment.status = ShipmentStatus.RELEASED
        elif event.event_type.value == "INCIDENT_OPENED":
            prior_decision = session.scalar(select(Disposition.disposition_id).where(
                Disposition.shipment_id == event.shipment_id
            ).limit(1))
            physical_release = session.scalar(select(WarehouseRelease.release_id).where(
                WarehouseRelease.shipment_id == event.shipment_id
            ).limit(1))
            if prior_decision and not physical_release:
                shipment.status = ShipmentStatus.AWAITING_DISPOSITION
    session.info["confirmations"] = confirmations


def process_one(sessionmaker=None, gateway: ChainGateway | None = None) -> bool:
    """Process one due entry. Returns False when no work is available."""
    sessionmaker = sessionmaker or get_sessionmaker()
    gateway = gateway or ChainGateway()
    capture_session = sessionmaker()
    try:
        capture_unanchored_incidents(capture_session)
        capture_session.commit()
        worker_status.dependency("database", "available")
    except Exception:
        capture_session.rollback()
        raise
    finally:
        capture_session.close()
    session = sessionmaker()
    try:
        claimed = _claim(session)
        if claimed is None:
            session.rollback()
            return False
        event, entry, attempt = claimed
        worker_status.business_ref(event.business_ref)
        session.commit()  # claim and durable attempt record precede external submission
    finally:
        session.close()

    session = sessionmaker()
    try:
        event = session.get(BusinessEvent, event.event_id)
        entry = session.get(OutboxEntry, entry.event_id)
        attempt = session.get(OutboxAttempt, attempt.attempt_id)
        assert event and entry and attempt
        try:
            existing = gateway.get_reference(event.business_ref)
        except Exception as exc:
            _schedule_retry(entry, attempt, gateway.settings, uncertain=True)
            detail = str(exc)[:240] or type(exc).__name__
            attempt.error = detail
            entry.last_error = detail
            worker_status.dependency("chain", "unavailable", error=detail)
            session.commit()
            logger.warning("Outbox event deferred: event_id=%s ref=%s attempt=%s operation=eth_call:get_reference error=%s retry_at=%s",
                           event.event_id, event.business_ref, attempt.attempt_number, detail,
                           entry.next_attempt_at)
            return True
        worker_status.dependency("chain", "available")
        expected_payload = "0x" + gateway.payload_hash_for(event).hex()
        expected_shipment = "0x" + gateway._hash(event.shipment_id).hex()
        if existing is not None:
            if existing["payload_hash"].lower() != expected_payload.lower() or existing["shipment_key"].lower() != expected_shipment.lower():
                attempt.outcome = "FAILED"
                attempt.error = "on-chain reference exists with mismatched payload or shipment"
                attempt.finished_at = datetime.now(UTC)
                entry.status = OutboxStatus.FAILED
                entry.last_error = attempt.error
                entry.updated_at = datetime.now(UTC)
                session.commit()
                return True
            tx_data = gateway.find_reference_log(event.business_ref)
            if tx_data is None:
                attempt.outcome = "UNCERTAIN"
                attempt.error = "reference exists but corresponding event log was not found"
                entry.last_error = attempt.error
                _schedule_retry(entry, attempt, gateway.settings, uncertain=True)
                session.commit()
                return True
            if gateway.web3.eth.block_number < int(tx_data["block_number"]) + max(1, gateway.settings.chain_confirmations) - 1:
                _schedule_retry(entry, attempt, gateway.settings, uncertain=True)
                entry.last_error = "waiting for configured block confirmations"
                session.commit()
                return True
            _confirm(session, gateway, event, entry, attempt, tx_data, gateway.settings.chain_confirmations)
            session.commit()
            return True
        try:
            tx_hash, block, log_index, confirmations = gateway.submit(event, session)
            tx_data = {"tx_hash": tx_hash, "block_number": block, "log_index": log_index}
            _confirm(session, gateway, event, entry, attempt, tx_data, confirmations)
            session.commit()
            worker_status.dependency("chain", "available")
        except ContractRevert as exc:
            attempt.outcome = "FAILED"
            attempt.error = str(exc)[:400]
            attempt.finished_at = datetime.now(UTC)
            entry.status = OutboxStatus.FAILED
            entry.last_error = attempt.error
            entry.next_attempt_at = None
            entry.updated_at = datetime.now(UTC)
            session.commit()
            logger.error("Outbox business event rejected: event_id=%s ref=%s attempt=%s operation=%s code=%s detail=%s",
                         event.event_id, event.business_ref, attempt.attempt_number,
                         exc.operation, exc.code, exc.detail)
        except ChainUnavailable as exc:
            detail = str(exc)[:400]
            _schedule_retry(entry, attempt, gateway.settings, uncertain=True)
            attempt.error = detail
            entry.last_error = detail
            worker_status.dependency("chain", "unavailable", error=detail)
            session.commit()
            logger.warning("Outbox RPC unavailable: event_id=%s ref=%s attempt=%s error=%s retry_at=%s",
                           event.event_id, event.business_ref, attempt.attempt_number,
                           detail, entry.next_attempt_at)
        except Exception as exc:
            # The tx may have landed despite an RPC timeout. Keep it uncertain and resolve on retry.
            # A failed DB flush/commit also invalidates the current transaction; clear it before
            # checking chain state so an already-mined idempotent reference can be reconciled.
            session.rollback()
            event = session.get(BusinessEvent, event.event_id)
            entry = session.get(OutboxEntry, entry.event_id)
            attempt = session.get(OutboxAttempt, attempt.attempt_id)
            assert event and entry and attempt
            try:
                current = gateway.get_reference(event.business_ref)
            except Exception as lookup_exc:
                current = None
                worker_status.dependency("chain", "unavailable", error=str(lookup_exc)[:240])
            if current is not None:
                if current["payload_hash"].lower() == expected_payload.lower() and current["shipment_key"].lower() == expected_shipment.lower():
                    tx_data = gateway.find_reference_log(event.business_ref)
                    if tx_data:
                        _confirm(session, gateway, event, entry, attempt, tx_data, gateway.settings.chain_confirmations)
                        session.commit()
                        return True
                attempt.outcome = "FAILED"
                entry.status = OutboxStatus.FAILED
            else:
                _schedule_retry(entry, attempt, gateway.settings, uncertain=True)
            attempt.error = f"{type(exc).__name__}:{str(exc)[:240]}"
            attempt.finished_at = datetime.now(UTC)
            entry.last_error = attempt.error
            session.commit()
            logger.warning("Outbox submission uncertain: event_id=%s ref=%s attempt=%s error=%s retry_at=%s",
                           event.event_id, event.business_ref, attempt.attempt_number,
                           attempt.error, entry.next_attempt_at)
    except Exception:
        session.rollback()
        logger.exception("Outbox relay failed while processing event")
        raise
    finally:
        session.close()
    return True


def _schedule_retry(entry: OutboxEntry, attempt: OutboxAttempt, settings, uncertain: bool = False) -> None:
    attempt.outcome = "UNCERTAIN" if uncertain else "RETRY"
    attempt.finished_at = datetime.now(UTC)
    entry.updated_at = datetime.now(UTC)
    if entry.attempts >= settings.outbox_max_attempts:
        entry.status = OutboxStatus.FAILED
    else:
        delay = min(3600_000, settings.outbox_base_delay_ms * 2 ** max(0, entry.attempts - 1))
        entry.status = OutboxStatus.RETRY
        entry.next_attempt_at = datetime.now(UTC) + timedelta(milliseconds=delay)


def run_forever(poll_seconds: float = 1.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("web3.manager.RequestManager").setLevel(logging.WARNING)
    while True:
        worker_status.begin_cycle()
        try:
            had_work = process_one()
            worker_status.complete_cycle("processed" if had_work else "idle")
            if not had_work:
                time.sleep(poll_seconds)
        except Exception as exc:
            worker_status.dependency("database", "unavailable", error=f"{type(exc).__name__}:{str(exc)[:180]}")
            worker_status.complete_cycle("error", error=f"{type(exc).__name__}:{str(exc)[:180]}")
            logger.exception("Outbox loop failed; bounded polling will resume")
            time.sleep(poll_seconds)


if __name__ == "__main__":
    run_forever()
