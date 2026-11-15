"""Live sensor ingestion (FR-01 to FR-04). ``received_at`` is always the server's receipt time.

The body is parsed with exact decimals (``parse_float=Decimal``), so a measurement is never
rounded on the way in; values with more than 2 decimal places are rejected per record
(BR-08 amendment). Trusted replay of recorded receipt times is not available over HTTP
(internal command ``python -m app.monitoring``, C-09). Authentication arrives in M5; until then
batches are attributed to the shipment's carrier organization.
"""

import json
from dataclasses import asdict
from decimal import Decimal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.monitoring_schemas import IngestBatchIn, IngestResultOut
from app.api.schemas import Envelope
from app.core.errors import AppError
from app.db.models.enums import IngestMode, IngestSource
from app.db.session import get_db
from app.services.ingest import ingest_batch

router = APIRouter(prefix="/ingest", tags=["ingestion"])

_REQUEST_SCHEMA = IngestBatchIn.model_json_schema()


class InvalidBody(AppError):
    status_code = 422
    code = "validation_error"


def _ingest(db: Session, body: IngestBatchIn) -> IngestResultOut:
    try:
        result = ingest_batch(
            db,
            business_ref=body.business_ref,
            shipment_id=body.shipment_id,
            readings=body.readings,
            context_records=body.context_records,
            mode=IngestMode.LIVE,
            source=IngestSource.GATEWAY,
        )
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
async def ingest(request: Request, response: Response, db: Session = Depends(get_db)) -> Envelope[IngestResultOut]:
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
    result = await run_in_threadpool(_ingest, db, body)
    if result.idempotent_replay:
        response.status_code = 200
    return Envelope(data=result)
