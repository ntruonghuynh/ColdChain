from copy import copy
from datetime import UTC, datetime, timedelta
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.security import hash_password, verify_password
from app.core.errors import AppError
from app.db.models import AppUser, BusinessEvent, ChainRecord, Incident, Organization, OutboxAttempt, OutboxEntry
from app.db.models.enums import (
    BusinessEventType, DetectionSource, IncidentCategory, IncidentStatus, OutboxStatus, Role, ShipmentStatus,
)
from app.integrations import audit_log
from app.integrations.chain_gateway import (
    ChainUnavailable, ContractRevert, _revert_data, _rpc_summary, normalize_data_hex, normalize_tx_hash,
)
from app.integrations.audit_log import append_audit_entry, verify_audit_log
from app.services.ledger import enqueue_business_event
from app.worker.outbox_relay import _claim, _confirm, _schedule_retry, process_one
from app.worker.healthcheck import inspect_status
from app.core.config import get_settings
from tests.factories import make_shipment


def test_pbkdf2_password_hash_is_salted_and_verifiable() -> None:
    one = hash_password("local-demo-passphrase-1")
    two = hash_password("local-demo-passphrase-1")
    assert one != two
    assert verify_password("local-demo-passphrase-1", one)
    assert not verify_password("wrong-password", one)
    assert not verify_password("local-demo-passphrase-1", None)
    with pytest.raises(ValueError):
        hash_password("short")


def test_login_uses_database_role_and_rejects_anonymous_privileged_actions(
    client: TestClient, db_session, monkeypatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: Settings(jwt_secret="x" * 48))
    monkeypatch.setattr("app.api.auth.get_settings", lambda: Settings(jwt_secret="x" * 48))
    user = db_session.scalar(select(AppUser).where(AppUser.username == "quality.demo"))
    assert user is not None
    user.password_hash = hash_password("local-demo-passphrase-1")
    db_session.flush()

    anonymous = client.post("/api/workflow/shipments/no-such-shipment/release", json={"business_ref": "release-1"})
    assert anonymous.status_code == 401
    login = client.post("/api/auth/login", json={"username": user.username, "password": "local-demo-passphrase-1"})
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    assert "QUALITY" in login.json()["data"]["roles"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    forbidden = client.post("/api/workflow/shipments/no-such-shipment/release",
                            json={"business_ref": "release-1"},
                            headers={"Authorization": f"Bearer {token}"})
    assert forbidden.status_code == 403


def test_signed_audit_chain_detects_record_tampering(db_session, monkeypatch) -> None:
    monkeypatch.setattr(audit_log, "get_settings", lambda: Settings(audit_signing_key="ab" * 32))
    user = db_session.scalar(select(AppUser).where(AppUser.username == "platform.admin"))
    org = db_session.get(Organization, "ORG-PLATFORM")
    assert user is not None and org is not None
    first = append_audit_entry(db_session, business_ref="audit-test-1", actor_user_id=user.user_id,
                               actor_org_id=org.org_id, action="TEST", record={"value": 1})
    append_audit_entry(db_session, business_ref="audit-test-2", actor_user_id=user.user_id,
                       actor_org_id=org.org_id, action="TEST", record={"value": 2})
    assert verify_audit_log(db_session)["valid"] is True

    tampered = copy(first)
    tampered.record = {"value": 99}

    class Rows:
        def all(self):
            return [tampered]

    monkeypatch.setattr(db_session, "scalars", lambda _statement: Rows())
    result = verify_audit_log(db_session)
    assert result["valid"] is False
    assert result["errors"][0]["hash_valid"] is False

    invalid_signature = copy(first)
    invalid_signature.signature = bytes([first.signature[0] ^ 1]) + first.signature[1:]

    class SignatureRows:
        def all(self):
            return [invalid_signature]

    monkeypatch.setattr(db_session, "scalars", lambda _statement: SignatureRows())
    result = verify_audit_log(db_session)
    assert result["valid"] is False
    assert result["errors"][0]["hash_valid"] is True
    assert result["errors"][0]["signature_valid"] is False


def test_audit_signing_fails_closed_for_invalid_local_key(db_session, monkeypatch) -> None:
    monkeypatch.setattr(audit_log, "get_settings", lambda: Settings(audit_signing_key="not-a-32-byte-seed"))
    actor = db_session.scalar(select(AppUser).where(AppUser.username == "platform.admin"))
    assert actor is not None
    with pytest.raises(RuntimeError, match="32-byte hexadecimal seed"):
        append_audit_entry(db_session, business_ref="audit-invalid-key", actor_user_id=actor.user_id,
                           actor_org_id=actor.org_id, action="TEST", record={"value": 1})
    db_session.rollback()


def test_br13_business_event_and_outbox_are_atomic_and_idempotent(db_session, monkeypatch) -> None:
    monkeypatch.setattr(audit_log, "get_settings", lambda: Settings(audit_signing_key="ab" * 32))
    actor = db_session.scalar(select(AppUser).where(AppUser.username == "platform.admin"))
    shipment = make_shipment(db_session, "M5-OUTBOX-ATOMIC")
    assert actor is not None
    event, replay = enqueue_business_event(
        db_session, business_ref="m5-atomic-event", event_type=BusinessEventType.SHIPMENT_REGISTERED,
        shipment_id=shipment.shipment_id, actor_org_id=actor.org_id, actor_user_id=actor.user_id,
        payload={"policy_hash": "a" * 64},
    )
    assert replay is False
    outbox = db_session.get(OutboxEntry, event.event_id)
    assert outbox is not None and outbox.status == OutboxStatus.PENDING
    same, replay = enqueue_business_event(
        db_session, business_ref="m5-atomic-event", event_type=BusinessEventType.SHIPMENT_REGISTERED,
        shipment_id=shipment.shipment_id, actor_org_id=actor.org_id, actor_user_id=actor.user_id,
        payload={"policy_hash": "a" * 64},
    )
    assert replay is True and same.event_id == event.event_id
    with pytest.raises(AppError):
        enqueue_business_event(
            db_session, business_ref="m5-atomic-event", event_type=BusinessEventType.SHIPMENT_REGISTERED,
            shipment_id=shipment.shipment_id, actor_org_id=actor.org_id, actor_user_id=actor.user_id,
            payload={"policy_hash": "b" * 64},
        )
    assert db_session.scalar(select(BusinessEvent.event_id).where(
        BusinessEvent.business_ref == "m5-atomic-event"
    )) == event.event_id


def test_outbox_claim_records_uncertain_attempt_and_retry_is_bounded(db_session) -> None:
    actor = db_session.scalar(select(AppUser).where(AppUser.username == "platform.admin"))
    shipment = make_shipment(db_session, "M5-OUTBOX-RETRY")
    assert actor is not None
    event, _ = enqueue_business_event(
        db_session, business_ref="m5-retry-event", event_type=BusinessEventType.SHIPMENT_REGISTERED,
        shipment_id=shipment.shipment_id, actor_org_id=actor.org_id, actor_user_id=actor.user_id,
        payload={"policy_hash": "c" * 64},
    )
    entry = db_session.get(OutboxEntry, event.event_id)
    assert entry is not None
    entry.attempts = 1
    entry.status = OutboxStatus.SUBMITTED
    entry.updated_at = datetime.now(UTC) - timedelta(minutes=2)
    first_attempt = OutboxAttempt(event_id=event.event_id, attempt_number=1,
                                  started_at=entry.updated_at, outcome="STARTED")
    db_session.add(first_attempt)
    db_session.flush()
    claimed = _claim(db_session)
    assert claimed is not None and claimed[0].event_id == event.event_id
    assert first_attempt.outcome == "UNCERTAIN"
    assert claimed[2].attempt_number == 2 and entry.status == OutboxStatus.SUBMITTED

    settings = get_settings().model_copy(update={"outbox_max_attempts": 2, "outbox_base_delay_ms": 1})
    _schedule_retry(entry, claimed[2], settings, uncertain=True)
    assert entry.status == OutboxStatus.FAILED
    assert claimed[2].outcome == "UNCERTAIN"


def test_sensor_and_multiple_incident_events_wait_for_same_shipment_registration(db_session, monkeypatch) -> None:
    monkeypatch.setattr(audit_log, "get_settings", lambda: Settings(audit_signing_key="ab" * 32))
    shipper = db_session.scalar(select(AppUser).where(AppUser.username == "shipper.demo"))
    monitor = db_session.scalar(select(AppUser).where(AppUser.username == "monitor.service"))
    shipment = make_shipment(db_session, "M5-DEPENDENCY-GATE")
    other_shipment = make_shipment(db_session, "M5-DEPENDENCY-GATE-OTHER")
    assert shipper is not None and monitor is not None

    sensor_event, _ = enqueue_business_event(
        db_session, business_ref="m5-dependency-sensor", event_type=BusinessEventType.SENSOR_BATCH_ANCHORED,
        shipment_id=shipment.shipment_id, actor_org_id="ORG-CARRIER", actor_user_id=None,
        payload={"batch_ref": "m5-dependency-batch", "content_sha256": "1" * 64},
    )
    incident_events = []
    for suffix in ("one", "two"):
        incident = Incident(
            business_ref=f"m5-dependency-incident-{suffix}", shipment_id=shipment.shipment_id,
            category=IncidentCategory.DATA_GAP, interval_start=datetime.now(UTC),
            detected_by=DetectionSource.MANUAL, policy_id=shipment.policy_id, opened_at=datetime.now(UTC),
        )
        db_session.add(incident)
        db_session.flush()
        incident_event, _ = enqueue_business_event(
            db_session, business_ref=incident.business_ref, event_type=BusinessEventType.INCIDENT_OPENED,
            shipment_id=shipment.shipment_id, actor_org_id=monitor.org_id, actor_user_id=monitor.user_id,
            payload={"incident_id": str(incident.incident_id), "evidence_revision_id": str(uuid.uuid4())},
        )
        replay, is_replay = enqueue_business_event(
            db_session, business_ref=incident.business_ref, event_type=BusinessEventType.INCIDENT_OPENED,
            shipment_id=shipment.shipment_id, actor_org_id=monitor.org_id, actor_user_id=monitor.user_id,
            payload=incident_event.payload,
        )
        assert is_replay and replay.event_id == incident_event.event_id
        incident_events.append(incident_event)

    # Neither event is attempted before a registration for this exact shipment.
    assert _claim(db_session) is None
    assert db_session.get(OutboxEntry, sensor_event.event_id).attempts == 0
    assert all(db_session.get(OutboxEntry, event.event_id).attempts == 0 for event in incident_events)

    other_registration, _ = enqueue_business_event(
        db_session, business_ref="m5-dependency-other-registration",
        event_type=BusinessEventType.SHIPMENT_REGISTERED, shipment_id=other_shipment.shipment_id,
        actor_org_id=shipper.org_id, actor_user_id=shipper.user_id, payload={"policy_hash": "2" * 64},
    )
    db_session.get(OutboxEntry, other_registration.event_id).status = OutboxStatus.CONFIRMED
    assert _claim(db_session) is None  # another shipment's registration cannot unlock these events

    registration, _ = enqueue_business_event(
        db_session, business_ref="m5-dependency-registration", event_type=BusinessEventType.SHIPMENT_REGISTERED,
        shipment_id=shipment.shipment_id, actor_org_id=shipper.org_id, actor_user_id=shipper.user_id,
        payload={"policy_hash": "3" * 64},
    )
    registration_entry = db_session.get(OutboxEntry, registration.event_id)
    assert registration_entry is not None
    registration_entry.status = OutboxStatus.CONFIRMED

    claimable_event_ids = {sensor_event.event_id, *(event.event_id for event in incident_events)}
    claimed_ids = set()
    for _ in range(len(claimable_event_ids)):
        claimed = _claim(db_session)
        assert claimed is not None and claimed[0].event_id in claimable_event_ids
        assert claimed[0].event_id not in claimed_ids
        claimed_ids.add(claimed[0].event_id)
        claimed[1].status = OutboxStatus.CONFIRMED
    assert claimed_ids == claimable_event_ids


def test_contract_reverts_are_decoded_and_have_no_retry_classification() -> None:
    class RPCError(Exception):
        pass

    error = RPCError({"code": -32000, "message": "execution reverted", "data": "0xa6532e5d"})
    assert _revert_data(error) == "0xa6532e5d"
    with pytest.raises(ContractRevert, match="InvalidTransition") as raised:
        _rpc_summary(error, "eth_sendRawTransaction")
    assert raised.value.operation == "eth_sendRawTransaction"
    assert raised.value.code == "InvalidTransition"


def test_chain_transaction_hash_is_normalized_for_database_constraint() -> None:
    assert normalize_tx_hash("ab" * 32) == "0x" + "ab" * 32
    assert normalize_tx_hash("0x" + "cd" * 32) == "0x" + "cd" * 32
    assert normalize_tx_hash(bytes.fromhex("ef" * 32)) == "0x" + "ef" * 32
    assert normalize_data_hex(bytes.fromhex("12" * 32)) == "0x" + "12" * 32


def test_worker_health_is_live_during_dependency_outage_and_detects_stall(tmp_path) -> None:
    from app.worker.status import WorkerStatus
    import json
    from datetime import UTC, datetime, timedelta

    path = tmp_path / "worker.json"
    status = WorkerStatus(path)
    status.begin_cycle()
    status.dependency("chain", "unavailable", error="ConnectionError:node unavailable")
    status.dependency("database", "available")
    healthy, state = inspect_status(path)
    assert healthy is True
    assert state["status"] == "alive_degraded"
    assert state["dependencies"]["chain"] == "unavailable"
    assert state["dependency_errors"]["chain"] == "ConnectionError:node unavailable"
    assert state["last_error_dependency"] == "chain"

    payload = json.loads(path.read_text())
    payload["phase"] = "idle"
    payload["last_cycle_at"] = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
    path.write_text(json.dumps(payload))
    healthy, state = inspect_status(path)
    assert healthy is False
    assert state["reason"] == "relay_cycle_stalled"

    payload["last_cycle_at"] = datetime.now(UTC).isoformat()
    payload["pid"] = 2**30
    path.write_text(json.dumps(payload))
    healthy, state = inspect_status(path)
    assert healthy is False and state["reason"] == "relay_process_not_alive"


def test_outbox_chain_outage_retries_then_recovers_idempotently(db_session) -> None:
    shipment = make_shipment(db_session, "M5-CHAIN-RECOVERY")
    actor = db_session.scalar(select(AppUser).where(AppUser.username == "shipper.demo"))
    assert actor is not None
    event = BusinessEvent(
        event_id=uuid.uuid4(), business_ref="m5-chain-recovery-event",
        event_type=BusinessEventType.SHIPMENT_REGISTERED, shipment_id=shipment.shipment_id,
        actor_org_id=actor.org_id, actor_user_id=actor.user_id, occurred_at=datetime.now(UTC),
        payload={"policy_hash": "a" * 64}, payload_sha256="b" * 64,
    )
    db_session.add(event)
    db_session.flush()
    db_session.add(OutboxEntry(event_id=event.event_id, status=OutboxStatus.PENDING, attempts=0))
    db_session.flush()

    class FakeGateway:
        address = "0x" + "1" * 40
        settings = Settings(chain_id=31337, outbox_base_delay_ms=10, outbox_max_attempts=8)

        def __init__(self):
            self.submit_calls = 0
            self.onchain = None

        @staticmethod
        def hash_ref(_ref):
            return bytes.fromhex("12" * 32)

        @staticmethod
        def _hash(_value):
            return bytes.fromhex("34" * 32)

        @staticmethod
        def payload_hash_for(_event):
            return bytes.fromhex("56" * 32)

        def get_reference(self, _ref):
            return self.onchain

        def submit(self, _event, _session):
            self.submit_calls += 1
            if self.submit_calls == 1:
                raise ChainUnavailable("eth_sendRawTransaction:-32000:node unavailable")
            self.onchain = {"payload_hash": "0x" + "56" * 32,
                            "shipment_key": "0x" + "34" * 32}
            return "0x" + "78" * 32, 42, 0, 1

    gateway = FakeGateway()
    from sqlalchemy.orm import sessionmaker as make_sessionmaker
    maker = make_sessionmaker(bind=db_session.connection(), autoflush=False,
                              expire_on_commit=False, join_transaction_mode="create_savepoint")
    assert process_one(maker, gateway) is True
    entry = db_session.get(OutboxEntry, event.event_id)
    assert entry is not None and entry.status == OutboxStatus.RETRY
    assert entry.next_attempt_at is not None and entry.last_error.startswith("eth_sendRawTransaction")
    attempts = list(db_session.scalars(select(OutboxAttempt).where(
        OutboxAttempt.event_id == event.event_id).order_by(OutboxAttempt.attempt_number)))
    assert len(attempts) == 1 and attempts[0].outcome == "UNCERTAIN"

    entry.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()
    assert process_one(maker, gateway) is True
    db_session.refresh(entry)
    assert entry.status == OutboxStatus.CONFIRMED
    assert gateway.submit_calls == 2
    assert db_session.scalar(select(ChainRecord).where(ChainRecord.event_id == event.event_id)) is not None


def test_mined_transaction_with_interrupted_database_confirmation_reconciles_once(db_session) -> None:
    shipment = make_shipment(db_session, "M5-MINED-DB-INTERRUPTION")
    actor = db_session.scalar(select(AppUser).where(AppUser.username == "shipper.demo"))
    assert actor is not None
    event, _ = enqueue_business_event(
        db_session, business_ref="m5-mined-db-interruption", event_type=BusinessEventType.SHIPMENT_REGISTERED,
        shipment_id=shipment.shipment_id, actor_org_id=actor.org_id, actor_user_id=actor.user_id,
        payload={"policy_hash": "a" * 64},
    )

    class MinedThenInterruptedGateway:
        address = "0x" + "1" * 40
        settings = Settings(chain_id=31337, chain_confirmations=1)

        def __init__(self):
            self.reference = None
            self.submit_calls = 0
            self.lookup_calls = 0
            self.tx_hash = "0x" + "9" * 64

        @staticmethod
        def hash_ref(_ref):
            return bytes.fromhex("12" * 32)

        @staticmethod
        def _hash(_value):
            return bytes.fromhex("34" * 32)

        @staticmethod
        def payload_hash_for(_event):
            return bytes.fromhex("56" * 32)

        def get_reference(self, _ref):
            self.lookup_calls += 1
            return self.reference

        def submit(self, _event, _session):
            self.submit_calls += 1
            self.reference = {"payload_hash": "0x" + "56" * 32,
                              "shipment_key": "0x" + "34" * 32}
            raise TimeoutError("injected database confirmation interruption after mining")

        def find_reference_log(self, _ref):
            return {"tx_hash": self.tx_hash, "block_number": 55, "log_index": 0}

    gateway = MinedThenInterruptedGateway()
    from sqlalchemy.orm import sessionmaker as make_sessionmaker
    maker = make_sessionmaker(bind=db_session.connection(), autoflush=False,
                              expire_on_commit=False, join_transaction_mode="create_savepoint")

    assert process_one(maker, gateway) is True
    entry = db_session.get(OutboxEntry, event.event_id)
    chain_records = list(db_session.scalars(select(ChainRecord).where(ChainRecord.event_id == event.event_id)))
    attempts = list(db_session.scalars(select(OutboxAttempt).where(
        OutboxAttempt.event_id == event.event_id).order_by(OutboxAttempt.attempt_number)))
    assert entry is not None and entry.status == OutboxStatus.CONFIRMED
    assert gateway.submit_calls == 1 and gateway.lookup_calls == 2
    assert len(chain_records) == 1 and len(attempts) == 1
    assert attempts[0].outcome == "CONFIRMED" and attempts[0].tx_hash == gateway.tx_hash


def test_br10_incident_closes_only_after_disposition_confirmation(db_session) -> None:
    shipment = make_shipment(db_session, "M5-CONFIRMED-DISPOSITION")
    shipment.status = ShipmentStatus.DELIVERED
    incident = Incident(
        business_ref="m5-confirmed-incident", shipment_id=shipment.shipment_id,
        category=IncidentCategory.DATA_GAP, interval_start=datetime.now(UTC),
        detected_by=DetectionSource.MANUAL, policy_id=shipment.policy_id, opened_at=datetime.now(UTC),
    )
    db_session.add(incident)
    db_session.flush()
    actor = db_session.scalar(select(AppUser).where(AppUser.username == "quality.demo"))
    assert actor is not None
    event = BusinessEvent(
        event_id=uuid.uuid4(), business_ref="m5-confirmed-disposition",
        event_type=BusinessEventType.DISPOSITION_RECORDED, shipment_id=shipment.shipment_id,
        actor_org_id=actor.org_id, actor_user_id=actor.user_id, occurred_at=datetime.now(UTC),
        payload={"decision": "QUARANTINE", "incident_refs": [incident.business_ref]}, payload_sha256="d" * 64,
    )
    entry = OutboxEntry(event_id=event.event_id, status=OutboxStatus.SUBMITTED, attempts=1)
    attempt = OutboxAttempt(event_id=event.event_id, attempt_number=1,
                            started_at=datetime.now(UTC), outcome="STARTED")
    db_session.add_all([event, entry])
    db_session.flush()
    db_session.add(attempt)
    db_session.flush()

    class FakeGateway:
        address = "0x" + "1" * 40
        settings = Settings(chain_id=31337)

        @staticmethod
        def hash_ref(_ref: str) -> bytes:
            return bytes.fromhex("12" * 32)

    _confirm(db_session, FakeGateway(), event, entry, attempt,
             {"tx_hash": "0x" + "2" * 64, "block_number": 10, "log_index": 0}, 1)
    assert entry.status == OutboxStatus.CONFIRMED
    assert shipment.status == ShipmentStatus.QUARANTINED
    assert incident.status == IncidentStatus.CLOSED and incident.closed_at is not None


def test_partner_reference_verification_checks_chain_and_database(client, db_session, monkeypatch) -> None:
    from app.api import ledger
    from app.core.security import issue_token

    monkeypatch.setattr("app.core.security.get_settings", lambda: Settings(jwt_secret="x" * 48))
    actor = db_session.scalar(select(AppUser).where(AppUser.username == "quality.demo"))
    shipment = make_shipment(db_session, "M5-PARTNER-VERIFY")
    assert actor is not None
    event, _ = enqueue_business_event(
        db_session, business_ref="m5-partner-verify", event_type=BusinessEventType.SHIPMENT_REGISTERED,
        shipment_id=shipment.shipment_id, actor_org_id=actor.org_id, actor_user_id=actor.user_id,
        payload={"content_sha256": "c" * 64},
    )
    outbox = db_session.get(OutboxEntry, event.event_id)
    assert outbox is not None
    outbox.status = OutboxStatus.CONFIRMED
    db_session.add(ChainRecord(
        event_id=event.event_id, chain_id=31337, contract_address="0x" + "1" * 40,
        onchain_ref="0x" + "2" * 64, tx_hash="0x" + "3" * 64, block_number=3,
        log_index=0, confirmed_at=datetime.now(UTC),
    ))
    db_session.flush()

    class FakeGateway:
        mismatch = False

        @staticmethod
        def get_reference(_ref):
            payload = "0x" + ("0" if FakeGateway.mismatch else "a") * 64
            return {"payload_hash": payload, "shipment_key": "0x" + "b" * 64}

        @staticmethod
        def payload_hash_for(_event):
            return bytes.fromhex("a" * 64)

        @staticmethod
        def _hash(_shipment):
            return bytes.fromhex("b" * 64)

    monkeypatch.setattr(ledger, "ChainGateway", FakeGateway)
    token = issue_token(actor, [Role.QUALITY])
    response = client.get("/api/ledger/verify/m5-partner-verify",
                          headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["data"]["verified"] is True
    assert response.json()["data"]["evidence_sha256"] == "c" * 64

    FakeGateway.mismatch = True
    mismatch = client.get("/api/ledger/verify/m5-partner-verify",
                          headers={"Authorization": f"Bearer {token}"})
    assert mismatch.status_code == 200
    assert mismatch.json()["data"]["verified"] is False
    assert mismatch.json()["data"]["verification_status"] == "MISMATCH"

