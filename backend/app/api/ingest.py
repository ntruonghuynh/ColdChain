"""Live sensor ingestion (FR-01 to FR-04). ``received_at`` is always the server's receipt time.

The body is parsed with exact decimals (``parse_float=Decimal``), so a measurement is never
rounded on the way in; values with more than 2 decimal places are rejected per record
(BR-08 amendment). Trusted replay of recorded receipt times is not available over HTTP
(internal command ``python -m app.monitoring``, C-09). Live submission requires an
authenticated CARRIER identity for the shipment's assigned carrier organization.
"""

import json
from dataclasses import asdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.monitoring_schemas import IngestBatchIn, IngestResultOut
from app.api.schemas import Envelope
from app.core.security import Principal, require_roles
from app.core.errors import AppError
from app.db.models import AppUser, Incident, IncidentRevision, IngestBatch, Policy, Shipment
from app.db.models.enums import BusinessEventType, IngestMode, IngestSource, Role
from app.db.session import get_db
from app.services.ingest import ingest_batch
from app.services.ledger import enqueue_business_event

router = APIRouter(prefix="/ingest", tags=["ingestion"])

_REQUEST_SCHEMA = IngestBatchIn.model_json_schema()


class InvalidBody(AppError):
    status_code = 422
    code = "validation_error"


def _ingest(db: Session, body: IngestBatchIn, principal: Principal) -> IngestResultOut:
    try:
        shipment = db.get(Shipment, body.shipment_id)
        if shipment is None:
            raise HTTPException(status_code=404, detail="Shipment not found")
        if shipment.carrier_org_id != principal.user.org_id:
            raise HTTPException(status_code=403, detail="Only the assigned carrier may submit telemetry")
        result = ingest_batch(
            db,
            business_ref=body.business_ref,
            shipment_id=body.shipment_id,
            readings=body.readings,
            context_records=body.context_records,
            mode=IngestMode.LIVE,
            source=IngestSource.GATEWAY,
            submitted_by_org_id=principal.user.org_id,
        )
        if not result.idempotent_replay:
            batch = db.get(IngestBatch, result.batch_id)
            assert batch is not None
            event, _ = enqueue_business_event(
                db, business_ref=f"sensor-batch:{batch.business_ref}",
                event_type=BusinessEventType.SENSOR_BATCH_ANCHORED,
                shipment_id=batch.shipment_id, actor_org_id=principal.user.org_id,
                actor_user_id=principal.user.user_id,
                payload={"batch_ref": batch.business_ref, "content_sha256": batch.content_sha256,
                         "canonicalization_version": batch.canonicalization_version,
                         "accepted_count": batch.accepted_count, "rejected_count": batch.rejected_count},
                occurred_at=batch.received_at,
            )
            batch.business_event_id = event.event_id
            monitor = db.scalar(select(AppUser).where(AppUser.username == "monitor.service"))
            if result.evaluations and not monitor:
                raise RuntimeError("Seeded monitoring identity is missing")
            for incident_ref in {ref for evaluation in result.evaluations for ref in evaluation.incidents_opened}:
                incident = db.scalar(select(Incident).where(Incident.business_ref == incident_ref))
                if incident is None or incident.business_event_id is not None:
                    continue
                first_revision = db.scalar(select(IncidentRevision).where(
                    IncidentRevision.incident_id == incident.incident_id,
                    IncidentRevision.revision == 1,
                ).limit(1))
                policy = db.get(Policy, incident.policy_id)
                incident_event, _ = enqueue_business_event(
                    db, business_ref=incident.business_ref, event_type=BusinessEventType.INCIDENT_OPENED,
                    shipment_id=incident.shipment_id, actor_org_id=monitor.org_id,
                    actor_user_id=monitor.user_id,
                    payload={"incident_id": str(incident.incident_id), "category": incident.category.value,
                             "interval_start": incident.interval_start.isoformat(),
                             "policy_sha256": policy.content_sha256 if policy else None,
                             "evidence_revision_id": str(first_revision.incident_revision_id) if first_revision else None},
                    occurred_at=incident.opened_at,
                )
                incident.business_event_id = incident_event.event_id
        db.commit()
    except Exception:
        db.rollback()
        raise
    return IngestResultOut.model_validate(asdict(result))


@router.post(
    "/batches",
    response_model=Envelope[IngestResultOut],
    status_code=201,
    summary="Ingest one batch of readings and context records (live)",
    responses={
        200: {"description": "Same business_ref and payload already ingested: original result (BR-13)"},
        404: {"description": "Shipment not found"},
        409: {"description": "business_ref already used with a different payload (BR-13)"},
    },
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": _REQUEST_SCHEMA}}}},
)
async def ingest(
    request: Request, response: Response, db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(Role.CARRIER)),
) -> Envelope[IngestResultOut]:
    raw = await request.body()
    try:
        payload = json.loads(raw, parse_float=Decimal)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidBody("Request body is not valid JSON.") from exc
    try:
        body = IngestBatchIn.model_validate(payload)
    except ValidationError as exc:
        raise InvalidBody(
            "Request validation failed.",
            details=[{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()],
        ) from exc
    result = await run_in_threadpool(_ingest, db, body, principal)
    if result.idempotent_replay:
        response.status_code = 200
    return Envelope(data=result)
