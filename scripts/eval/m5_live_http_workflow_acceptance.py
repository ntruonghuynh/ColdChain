"""Run the M5 live authenticated HTTP workflow against a uniquely named demo shipment.

Run inside the backend container (which already has local demo credentials and DB access):
`docker compose exec -T backend python - < scripts/eval/m5_live_http_workflow_acceptance.py`

This script adds one SIMULATED shipment/sensor fixture and intentionally leaves its audit,
outbox, and chain evidence in place. It does not alter existing shipments or incidents.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models import (
    AppUser,
    BusinessEvent,
    ChainRecord,
    Incident,
    OutboxAttempt,
    OutboxEntry,
    Policy,
    Sensor,
    SensorAssignment,
    Shipment,
)
from app.db.models.enums import DataOrigin, PolicyStatus
from app.db.session import get_sessionmaker

BASE = "http://127.0.0.1:8000/api"


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def call(path: str, method: str = "GET", body: dict | None = None, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    started = datetime.now(UTC)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        status = error.code
        try:
            result = json.loads(error.read())
        except Exception:
            result = {}
    return status, result, started, datetime.now(UTC)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


passwords = {
    "SHIPPER": ("shipper.demo", "SHIPPER_DEMO_PASSWORD"),
    "CARRIER": ("carrier.demo", "CARRIER_DEMO_PASSWORD"),
    "QUALITY": ("quality.demo", "QUALITY_DEMO_PASSWORD"),
    "WAREHOUSE": ("warehouse.demo", "WAREHOUSE_DEMO_PASSWORD"),
    "ADMIN": ("platform.admin", "ADMIN_DEMO_PASSWORD"),
}
tokens: dict[str, str] = {}
login_results = []
for role, (username, env_key) in passwords.items():
    status, payload, _, _ = call(
        "/auth/login", "POST", {"username": username, "password": os.environ[env_key]}
    )
    login = payload.get("data", {})
    require(status == 200 and role in login.get("roles", []), f"login failed for {role}: {status}")
    tokens[role] = login["access_token"]
    login_results.append({"role": role, "status": status})

with get_sessionmaker()() as session:
    policy = session.scalar(select(Policy).where(Policy.status == PolicyStatus.ACTIVE).limit(1))
    require(policy is not None, "active policy missing")
    suffix = uuid.uuid4().hex[:8].upper()
    shipment_id = f"M5HTTP-{datetime.now(UTC):%Y%m%d}-{suffix}"
    sensor_id = f"M5SENSOR-{suffix}"
    first_event_at = datetime.now(UTC) - timedelta(minutes=31)
    session.add(
        Shipment(
            shipment_id=shipment_id,
            product_id=policy.product_id,
            policy_id=policy.policy_id,
            shipper_org_id="ORG-SHIPPER",
            carrier_org_id="ORG-CARRIER",
            receiver_org_id="ORG-RECEIVER",
            origin="M5 isolated acceptance",
            destination="M5 isolated acceptance receiver",
            data_origin=DataOrigin.SIMULATED,
        )
    )
    session.flush()
    session.add(Sensor(sensor_id=sensor_id, sensor_type="TEMPERATURE_LOGGER",
                       owner_org_id="ORG-CARRIER", description="M5 isolated HTTP acceptance"))
    session.add(SensorAssignment(sensor_id=sensor_id, shipment_id=shipment_id,
                                 assigned_from=first_event_at - timedelta(minutes=5)))
    session.commit()

refs = {
    label: f"M5-HTTP-ACCEPTANCE-{suffix}-{label}"
    for label in ("REGISTER", "PICKUP", "BATCH", "DELIVERY", "DISPOSITION", "RELEASE")
}
step_records: dict[str, dict] = {}
event_origin: dict[str, str] = {}
confirmed_observed: dict[str, datetime] = {}


def post_step(name: str, path: str, body: dict, role: str) -> dict:
    status, payload, started, ended = call(path, "POST", body, tokens[role])
    require(status == 202, f"{name} expected 202, got {status}: {payload}")
    result = payload.get("data", {})
    step_records[name] = {"status": status, "body": result, "started": started, "ended": ended}
    if result.get("business_ref"):
        event_origin[result["business_ref"]] = name
    return result


def wait_confirmed(business_ref: str, timeout_s: int = 45) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status, payload, _, _ = call("/ledger/transactions?limit=500", token=tokens["ADMIN"])
        require(status == 200, f"transaction status API returned {status}")
        for row in payload.get("data", []):
            if row.get("business_ref") == business_ref and row.get("outbox_status") == "CONFIRMED":
                confirmed_observed[business_ref] = datetime.now(UTC)
                return row
        time.sleep(0.25)
    raise RuntimeError(f"timed out waiting for on-chain confirmation: {business_ref}")


premature_delivery = call(
    f"/workflow/shipments/{shipment_id}/custody", "POST",
    {"business_ref": f"M5-HTTP-ACCEPTANCE-{suffix}-PREDELIVERY", "stage": "DELIVERY"},
    tokens["WAREHOUSE"],
)[0]
require(premature_delivery == 409, f"premature delivery expected 409, got {premature_delivery}")
premature_release = call(
    f"/workflow/shipments/{shipment_id}/release", "POST",
    {"business_ref": f"M5-HTTP-ACCEPTANCE-{suffix}-PRERELEASE"}, tokens["WAREHOUSE"]
)[0]
require(premature_release == 409, f"premature release expected 409, got {premature_release}")
wrong_quality_role = call(
    f"/workflow/shipments/{shipment_id}/disposition", "POST",
    {"business_ref": f"M5-HTTP-ACCEPTANCE-{suffix}-WRONGQUALITY", "decision": "RELEASE",
     "rationale": "should be rejected", "incident_refs": []}, tokens["WAREHOUSE"]
)[0]
require(wrong_quality_role == 403, f"wrong role expected 403, got {wrong_quality_role}")

registration = post_step(
    "registration", f"/workflow/shipments/{shipment_id}/register",
    {"business_ref": refs["REGISTER"]}, "SHIPPER"
)
registration_id = registration["event_id"]
wait_confirmed(refs["REGISTER"])
registration_replay = call(
    f"/workflow/shipments/{shipment_id}/register", "POST",
    {"business_ref": refs["REGISTER"]}, tokens["SHIPPER"]
)
require(registration_replay[0] == 202
        and registration_replay[1].get("data", {}).get("event_id") == registration_id
        and registration_replay[1].get("data", {}).get("idempotent_replay"),
        "registration duplicate did not return the original event")

carrier_delivery = call(
    f"/workflow/shipments/{shipment_id}/custody", "POST",
    {"business_ref": f"M5-HTTP-ACCEPTANCE-{suffix}-CARRIER-DELIVERY", "stage": "DELIVERY"},
    tokens["CARRIER"],
)[0]
require(carrier_delivery == 403, f"carrier delivery expected 403, got {carrier_delivery}")
post_step("pickup", f"/workflow/shipments/{shipment_id}/custody",
          {"business_ref": refs["PICKUP"], "stage": "PICKUP"}, "CARRIER")
wait_confirmed(refs["PICKUP"])

# Seven observed high readings at five-minute intervals make one continuous 30-minute run.
reading_times = [datetime.now(UTC) - timedelta(minutes=31 - 5 * i) for i in range(7)]
readings = [{"sensor_id": sensor_id, "shipment_id": shipment_id, "event_at": iso(at),
             "temperature_c": 9.0} for at in reading_times]
ingest_body = {"business_ref": refs["BATCH"], "shipment_id": shipment_id,
               "readings": readings, "context_records": []}
ingest_status, ingest_payload, ingest_started, ingest_ended = call(
    "/ingest/batches", "POST", ingest_body, tokens["CARRIER"]
)
require(ingest_status == 201, f"ingest expected 201, got {ingest_status}: {ingest_payload}")
ingest_result = ingest_payload["data"]
step_records["ingest"] = {"status": ingest_status, "body": ingest_result,
                         "started": ingest_started, "ended": ingest_ended}
batch_ref = f"sensor-batch:{refs['BATCH']}"
event_origin[batch_ref] = "ingest"
incident_refs = sorted({ref for evaluation in ingest_result.get("evaluations", [])
                        for ref in evaluation.get("incidents_opened", [])})
require(bool(incident_refs), "the 30-minute policy excursion did not open an incident via MONITOR")
for incident_ref in incident_refs:
    event_origin[incident_ref] = "monitor_incident_from_ingest"
wait_confirmed(batch_ref)
for incident_ref in incident_refs:
    wait_confirmed(incident_ref)

duplicate_batch = call("/ingest/batches", "POST", ingest_body, tokens["CARRIER"])
require(duplicate_batch[0] == 200 and duplicate_batch[1].get("data", {}).get("idempotent_replay"),
        "duplicate batch did not replay idempotently")

# Delivery precedes disposition in the approved state machine.
post_step("delivery", f"/workflow/shipments/{shipment_id}/custody",
          {"business_ref": refs["DELIVERY"], "stage": "DELIVERY"}, "WAREHOUSE")
wait_confirmed(refs["DELIVERY"])
post_step("disposition", f"/workflow/shipments/{shipment_id}/disposition",
          {"business_ref": refs["DISPOSITION"], "decision": "RELEASE",
           "rationale": "M5 acceptance test only; this is not a product safety claim.",
           "incident_refs": incident_refs}, "QUALITY")
wait_confirmed(refs["DISPOSITION"])
post_step("release", f"/workflow/shipments/{shipment_id}/release",
          {"business_ref": refs["RELEASE"]}, "WAREHOUSE")
wait_confirmed(refs["RELEASE"])

verification = []
all_refs = [refs["REGISTER"], refs["PICKUP"], batch_ref, *incident_refs,
            refs["DELIVERY"], refs["DISPOSITION"], refs["RELEASE"]]
for business_ref in all_refs:
    status, payload, _, _ = call("/ledger/verify/" + urllib.parse.quote(business_ref, safe=""),
                                 token=tokens["ADMIN"])
    result = payload.get("data", {})
    verification.append({"business_ref": business_ref, "status": status,
                         "verified": result.get("verified"),
                         "verification_status": result.get("verification_status")})
    require(status == 200 and result.get("verified"), f"business ref did not verify: {business_ref}")

reconciliation_status, reconciliation_payload, _, _ = call("/ledger/reconciliation", token=tokens["ADMIN"])
reconciliation = reconciliation_payload.get("data", {})
require(reconciliation_status == 200 and reconciliation.get("chain_connected"),
        f"reconciliation failed: {reconciliation_status}")
audit_status, audit_payload, _, _ = call("/ledger/audit/verify", token=tokens["ADMIN"])
audit = audit_payload.get("data", {})
require(audit_status == 200 and audit.get("valid"), f"signed audit failed: {audit_status}")

latency = []
with get_sessionmaker()() as session:
    for event in session.scalars(select(BusinessEvent).where(BusinessEvent.business_ref.in_(all_refs))).all():
        outbox = session.get(OutboxEntry, event.event_id)
        chain = session.scalar(select(ChainRecord).where(ChainRecord.event_id == event.event_id))
        attempt = session.scalar(
            select(OutboxAttempt).where(OutboxAttempt.event_id == event.event_id,
                                        OutboxAttempt.outcome == "CONFIRMED")
            .order_by(OutboxAttempt.attempt_number.desc()).limit(1)
        )
        origin = event_origin[event.business_ref]
        source = step_records.get(origin) or step_records["ingest"]
        request_started = source["started"]
        observed = confirmed_observed.get(event.business_ref)
        latency.append({
            "business_ref": event.business_ref,
            "event_type": event.event_type.value,
            "event_id": str(event.event_id),
            "request_started_at": iso(request_started),
            "business_event_created_at": iso(event.created_at),
            "outbox_attempt_started_at": iso(attempt.started_at) if attempt else None,
            "chain_confirmed_at": iso(chain.confirmed_at) if chain else None,
            "confirmation_observed_at": iso(observed) if observed else None,
            "request_to_observed_confirmation_ms": round((observed - request_started).total_seconds() * 1000, 3)
            if observed else None,
            "attempt_start_to_chain_confirmation_ms": round((chain.confirmed_at - attempt.started_at).total_seconds() * 1000, 3)
            if chain and attempt else None,
            "outbox_status": outbox.status.value if outbox else None,
            "attempts": outbox.attempts if outbox else None,
        })
    incident_actor = []
    for event in session.scalars(select(BusinessEvent).where(BusinessEvent.business_ref.in_(incident_refs))).all():
        user = session.get(AppUser, event.actor_user_id) if event.actor_user_id else None
        incident_actor.append({"business_ref": event.business_ref,
                               "actor_username": user.username if user else None,
                               "actor_org_id": event.actor_org_id})
    final_status = session.get(Shipment, shipment_id).status.value

output = {
    "run": "live authenticated HTTP acceptance; new unique simulated shipment",
    "shipment_id": shipment_id,
    "sensor_id": sensor_id,
    "fixture_data_origin": "SIMULATED",
    "login_results": login_results,
    "expected_rejections": {
        "premature_delivery_http": premature_delivery,
        "premature_release_http": premature_release,
        "wrong_role_quality_http": wrong_quality_role,
        "carrier_wrong_stage_http": carrier_delivery,
    },
    "workflow_statuses": {name: record["status"] for name, record in step_records.items()},
    "shipment_final_status": final_status,
    "incident_refs_opened_by_monitor": incident_refs,
    "monitor_actor_evidence": incident_actor,
    "registration_idempotency": {
        "initial_event_id": registration_id,
        "replay_event_id": registration_replay[1]["data"]["event_id"],
        "same_event": registration_id == registration_replay[1]["data"]["event_id"],
        "idempotent_replay": registration_replay[1]["data"].get("idempotent_replay"),
    },
    "batch_idempotency": {"http_status": duplicate_batch[0],
                           "idempotent_replay": duplicate_batch[1]["data"].get("idempotent_replay")},
    "business_reference_verification": verification,
    "reconciliation": {"http_status": reconciliation_status,
                       "chain_connected": reconciliation.get("chain_connected"),
                       "event_count": reconciliation.get("event_count"),
                       "counts_by_finding": reconciliation.get("counts_by_finding")},
    "signed_audit_verification": {"http_status": audit_status, "valid": audit.get("valid"),
                                  "entry_count": audit.get("entry_count")},
    "integration_latency_samples": latency,
}
print(json.dumps(output, indent=2, sort_keys=True))
