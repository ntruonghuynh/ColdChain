"""Batch ingestion of sensor readings and context records (FR-01 to FR-04, BR-06 to BR-08, BR-13).

* ``received_at`` comes from the trusted server clock in LIVE mode. Only the internal replay
  path (``IngestMode.REPLAY``) may pass a recorded receipt time (C-09); the HTTP API never
  accepts one.
* Every record is validated on its own. Rejected records are stored with a reason and the raw
  payload (never silently dropped). Accepted readings keep ``event_at`` and ``received_at``.
* BR-07: an identical duplicate of a stored reading is ignored (counted, no business effect).
  A different value for the same ``(sensor_id, event_at)`` is rejected as a conflict, the
  stored reading is never overwritten, and a ``READING_CONFLICT`` data-quality warning is kept
  for quality review (U-01). Context records get the same checks (U-05) and must belong to a
  reading.
* BR-13: re-submitting a batch reference with the same payload returns the original result;
  the same reference with a different payload is a conflict.
* After storing, every affected sensor is re-evaluated causally (full journey, C-07).
* The caller owns the transaction (commit or rollback). A per-shipment advisory lock
  serialises concurrent batches of one shipment.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text, tuple_
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.db.models import ContextReading, DataQualityWarning, IngestBatch, Reading, RejectedRecord, Sensor, Shipment
from app.db.models.enums import DataOrigin, EvaluationMode, EvaluationTrigger, IngestMode, IngestSource, RecordKind
from app.domain.reconcile import WarningKind, stable_id
from app.domain.validation import (
    ContextInput,
    ReadingInput,
    Reason,
    Rejection,
    same_context,
    same_reading,
    validate_context,
    validate_reading,
)
from app.services.detection import EvaluationSummary, evaluate_sensor, monitoring_windows

CANONICALIZATION_VERSION = "ingest-v1"
INGEST_LOCK_SQL = text("SELECT pg_advisory_xact_lock(hashtext(:key))")


class BatchConflictError(AppError):
    status_code = 409
    code = "batch_conflict"


@dataclass
class RecordResult:
    index: int
    record_kind: str
    outcome: str  # ACCEPTED | DUPLICATE_IGNORED | REJECTED
    reason_code: str | None = None
    detail: str | None = None


@dataclass
class IngestResult:
    batch_id: uuid.UUID
    business_ref: str
    shipment_id: str
    received_at: datetime
    ingest_mode: str
    idempotent_replay: bool
    record_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    records: list[RecordResult] = field(default_factory=list)
    evaluations: list[EvaluationSummary] = field(default_factory=list)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def payload_sha256(payload: dict[str, Any]) -> str:
    raw = json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stored_result(session: Session, batch: IngestBatch) -> IngestResult:
    rejected = session.scalars(
        select(RejectedRecord)
        .where(RejectedRecord.ingest_batch_id == batch.batch_id)
        .order_by(RejectedRecord.record_kind, RejectedRecord.record_index)
    ).all()
    return IngestResult(
        batch.batch_id,
        batch.business_ref,
        batch.shipment_id,
        batch.received_at,
        str(batch.ingest_mode),
        True,
        batch.record_count,
        batch.accepted_count,
        batch.rejected_count,
        batch.duplicate_count,
        [
            RecordResult(r.record_index, str(r.record_kind), "REJECTED", r.reason_code, r.reason_detail)
            for r in rejected
        ],
    )


def ingest_batch(
    session: Session,
    *,
    business_ref: str,
    shipment_id: str,
    readings: list[Any],
    context_records: list[Any],
    mode: IngestMode,
    received_at: datetime | None = None,
    source: IngestSource = IngestSource.GATEWAY,
    data_origin: DataOrigin = DataOrigin.SIMULATED,
    evaluate: bool = True,
) -> IngestResult:
    if mode == IngestMode.LIVE:
        if received_at is not None:
            raise ValueError("LIVE ingestion uses the server clock; received_at cannot be supplied (C-09)")
        received_at = datetime.now(UTC)
    elif mode == IngestMode.REPLAY:
        if received_at is None or received_at.tzinfo is None:
            raise ValueError("REPLAY ingestion needs the recorded, timezone-aware received_at")
    else:
        raise ValueError("IMPORT batches are written by the dataset importer, not by ingestion")

    session.execute(INGEST_LOCK_SQL, {"key": f"coldchain.ingest:{shipment_id}"})
    shipment = session.get(Shipment, shipment_id)
    if shipment is None:
        raise NotFoundError(f"Shipment {shipment_id} not found.")

    digest = payload_sha256(
        {
            "business_ref": business_ref,
            "shipment_id": shipment_id,
            "readings": readings,
            "context_records": context_records,
            "received_at": received_at.isoformat() if mode == IngestMode.REPLAY else None,
        }
    )
    existing = session.scalar(select(IngestBatch).where(IngestBatch.business_ref == business_ref))
    if existing is not None:
        if existing.content_sha256 == digest and existing.shipment_id == shipment_id:
            return _stored_result(session, existing)  # BR-13: same reference, same payload
        raise BatchConflictError(
            f"Batch reference {business_ref!r} was already used with a different payload (BR-13).",
            details={"business_ref": business_ref, "existing_batch_id": str(existing.batch_id)},
        )

    windows = monitoring_windows(session, shipment_id)
    referenced = {
        r.get("sensor_id")
        for r in [*readings, *context_records]
        if isinstance(r, dict) and isinstance(r.get("sensor_id"), str)
    }
    known = (
        set(session.scalars(select(Sensor.sensor_id).where(Sensor.sensor_id.in_(referenced))).all())
        if referenced
        else set()
    )
    batch_id = uuid.uuid4()
    results: list[RecordResult] = []
    rejected_rows: list[dict[str, Any]] = []
    warning_rows: list[dict[str, Any]] = []

    def reject(kind: RecordKind, index: int, raw: Any, rej: Rejection) -> None:
        results.append(RecordResult(index, kind.value, "REJECTED", rej.reason.value, rej.detail))
        rejected_rows.append(
            dict(
                ingest_batch_id=batch_id,
                record_index=index,
                record_kind=kind.value,
                raw_payload=_jsonable(raw) if isinstance(raw, dict) else {"value": _jsonable(raw)},
                reason_code=rej.reason.value,
                reason_detail=rej.detail,
            )
        )

    # ---- readings (BR-08, U-03, BR-07)
    valid: list[tuple[int, Any, ReadingInput]] = []
    for i, raw in enumerate(readings):
        out = validate_reading(
            raw, shipment_id=shipment_id, received_at=received_at, known_sensors=known, windows=windows
        )
        if isinstance(out, Rejection):
            reject(RecordKind.READING, i, raw, out)
        else:
            valid.append((i, raw, out))
    keys = {(r.sensor_id, r.event_at) for _, _, r in valid}
    stored = (
        {
            (s, e): (sh, t, rid)
            for s, e, sh, t, rid in session.execute(
                select(
                    Reading.sensor_id, Reading.event_at, Reading.shipment_id, Reading.temperature_c, Reading.reading_id
                ).where(tuple_(Reading.sensor_id, Reading.event_at).in_(list(keys)))
            ).all()
        }
        if keys
        else {}
    )
    accepted: dict[tuple[str, datetime], tuple[str, Decimal, uuid.UUID | None]] = {}
    reading_rows: list[dict[str, Any]] = []
    duplicates = 0
    for i, raw, r in valid:
        key = (r.sensor_id, r.event_at)
        prior = stored.get(key) or accepted.get(key)
        if prior is not None:
            if same_reading(prior[0], prior[1], shipment_id, r.temperature_c):
                duplicates += 1
                results.append(
                    RecordResult(
                        i,
                        "READING",
                        "DUPLICATE_IGNORED",
                        None,
                        "identical to the reading already accepted; no effect (BR-07)",
                    )
                )
                continue
            rej = Rejection(
                Reason.DUPLICATE_CONFLICT,
                f"a reading for this sensor and event_at already exists with temperature_c={prior[1]} "
                f"(shipment {prior[0]}); the first accepted reading is kept (BR-07)",
            )
            reject(RecordKind.READING, i, raw, rej)
            warning_rows.append(
                _conflict_warning(
                    WarningKind.READING_CONFLICT,
                    shipment_id,
                    r.sensor_id,
                    r.event_at,
                    business_ref,
                    i,
                    batch_id,
                    received_at,
                    True,
                    {
                        "stored_temperature_c": str(prior[1]),
                        "stored_shipment_id": prior[0],
                        "stored_reading_id": str(prior[2]) if prior[2] else None,
                        "submitted_temperature_c": str(r.temperature_c),
                        "submitted_shipment_id": shipment_id,
                    },
                )
            )
            continue
        accepted[key] = (shipment_id, r.temperature_c, None)
        reading_rows.append(
            dict(
                sensor_id=r.sensor_id,
                shipment_id=shipment_id,
                ingest_batch_id=batch_id,
                event_at=r.event_at,
                received_at=received_at,
                temperature_c=r.temperature_c,
            )
        )
        results.append(RecordResult(i, "READING", "ACCEPTED"))

    # ---- context records (U-05)
    cvalid: list[tuple[int, Any, ContextInput]] = []
    for i, raw in enumerate(context_records):
        out = validate_context(
            raw, shipment_id=shipment_id, received_at=received_at, known_sensors=known, windows=windows
        )
        if isinstance(out, Rejection):
            reject(RecordKind.CONTEXT, i, raw, out)
        else:
            cvalid.append((i, raw, out))
    ckeys = {(c.sensor_id, c.event_at) for _, _, c in cvalid}
    linked_stored = (
        {
            (s, e)
            for s, e in session.execute(
                select(Reading.sensor_id, Reading.event_at).where(
                    Reading.shipment_id == shipment_id, tuple_(Reading.sensor_id, Reading.event_at).in_(list(ckeys))
                )
            ).all()
        }
        if ckeys
        else set()
    )
    cstored = (
        {
            (s, e): (sh, d, b, a)
            for s, e, sh, d, b, a in session.execute(
                select(
                    ContextReading.sensor_id,
                    ContextReading.event_at,
                    ContextReading.shipment_id,
                    ContextReading.door_state,
                    ContextReading.battery_level_pct,
                    ContextReading.ambient_temperature_c,
                ).where(tuple_(ContextReading.sensor_id, ContextReading.event_at).in_(list(ckeys)))
            ).all()
        }
        if ckeys
        else {}
    )
    caccepted: dict[tuple[str, datetime], tuple[str, str | None, Decimal | None, Decimal | None]] = {}
    context_rows: list[dict[str, Any]] = []
    for i, raw, c in cvalid:
        key = (c.sensor_id, c.event_at)
        if key not in linked_stored and key not in accepted:
            reject(
                RecordKind.CONTEXT,
                i,
                raw,
                Rejection(
                    Reason.CONTEXT_WITHOUT_READING,
                    "no accepted reading of this shipment has this sensor_id and event_at",
                ),
            )
            continue
        prior_c = cstored.get(key) or caccepted.get(key)
        if prior_c is not None:
            norm = (prior_c[0], str(prior_c[1]) if prior_c[1] is not None else None, prior_c[2], prior_c[3])
            if same_context(norm, shipment_id, c):
                duplicates += 1
                results.append(
                    RecordResult(
                        i,
                        "CONTEXT",
                        "DUPLICATE_IGNORED",
                        None,
                        "identical to the context record already accepted; no effect (BR-07, U-05)",
                    )
                )
                continue
            reject(
                RecordKind.CONTEXT,
                i,
                raw,
                Rejection(
                    Reason.CONTEXT_CONFLICT,
                    "a different context record for this sensor and event_at already exists; "
                    "the first accepted record is kept (U-05)",
                ),
            )
            warning_rows.append(
                _conflict_warning(
                    WarningKind.CONTEXT_CONFLICT,
                    shipment_id,
                    c.sensor_id,
                    c.event_at,
                    business_ref,
                    i,
                    batch_id,
                    received_at,
                    False,
                    {
                        "stored": _jsonable(list(norm)),
                        "submitted": _jsonable(
                            [shipment_id, c.door_state, c.battery_level_pct, c.ambient_temperature_c]
                        ),
                    },
                )
            )
            continue
        caccepted[key] = (shipment_id, c.door_state, c.battery_level_pct, c.ambient_temperature_c)
        context_rows.append(
            dict(
                sensor_id=c.sensor_id,
                shipment_id=shipment_id,
                ingest_batch_id=batch_id,
                event_at=c.event_at,
                received_at=received_at,
                door_state=c.door_state,
                battery_level_pct=c.battery_level_pct,
                ambient_temperature_c=c.ambient_temperature_c,
            )
        )
        results.append(RecordResult(i, "CONTEXT", "ACCEPTED"))

    events = [row["event_at"] for row in reading_rows]
    rejected_count = len(rejected_rows)
    accepted_count = len(reading_rows) + len(context_rows)
    session.add(
        IngestBatch(
            batch_id=batch_id,
            business_ref=business_ref,
            shipment_id=shipment_id,
            submitted_by_org_id=shipment.carrier_org_id,
            source=source,
            data_origin=data_origin,
            ingest_mode=mode,
            received_at=received_at,
            first_event_at=min(events) if events else None,
            last_event_at=max(events) if events else None,
            record_count=len(readings) + len(context_records),
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            duplicate_count=duplicates,
            content_sha256=digest,
            canonicalization_version=CANONICALIZATION_VERSION,
        )
    )
    session.flush()
    for model, rows in (
        (Reading, reading_rows),
        (ContextReading, context_rows),
        (RejectedRecord, rejected_rows),
        (DataQualityWarning, warning_rows),
    ):
        if rows:
            session.execute(model.__table__.insert(), rows)  # type: ignore[attr-defined]
    session.flush()

    result = IngestResult(
        batch_id,
        business_ref,
        shipment_id,
        received_at,
        mode.value,
        False,
        len(readings) + len(context_records),
        accepted_count,
        rejected_count,
        duplicates,
        sorted(results, key=lambda r: (r.record_kind != "READING", r.index)),
    )
    if evaluate:
        as_of = datetime.now(UTC) if mode == IngestMode.LIVE else received_at
        eval_mode = EvaluationMode.LIVE if mode == IngestMode.LIVE else EvaluationMode.REPLAY
        for sensor_id in sorted({row["sensor_id"] for row in reading_rows}):
            summary = evaluate_sensor(
                session,
                shipment_id,
                sensor_id,
                as_of=as_of,
                mode=eval_mode,
                trigger=EvaluationTrigger.BATCH,
                trigger_batch_id=batch_id,
            )
            if summary is not None:
                result.evaluations.append(summary)
    return result


def _conflict_warning(
    kind: WarningKind,
    shipment_id: str,
    sensor_id: str,
    event_at: datetime,
    business_ref: str,
    index: int,
    batch_id: uuid.UUID,
    raised_at: datetime,
    evidence: bool,
    details: dict[str, Any],
) -> dict[str, Any]:
    key = f"{kind}|{sensor_id}|{event_at.isoformat()}|{business_ref}|{index}"
    what = "temperature reading" if kind == WarningKind.READING_CONFLICT else "context record"
    return dict(
        warning_revision_id=stable_id("warning", shipment_id, sensor_id, key),
        warning_key=key,
        kind=kind.value,
        affects_quality_evidence=evidence,
        shipment_id=shipment_id,
        sensor_id=sensor_id,
        run_key=None,
        gap_key=None,
        interval_start_at=event_at,
        interval_end_at=event_at,
        linked_incident_id=None,
        message=(
            f"Conflicting {what} submitted for {event_at.isoformat()}: rejected and kept for review; the first "
            "accepted value is used. Possible sensor or gateway fault (persisted warning, not an incident)."
        ),
        details=details,
        evaluation_id=None,
        ingest_batch_id=batch_id,
        raised_at=raised_at,
        superseded_by_evaluation_id=None,
        superseded_at=None,
    )


def batch_totals(session: Session, shipment_id: str) -> dict[str, int]:
    row = session.execute(
        select(
            func.coalesce(func.sum(IngestBatch.rejected_count), 0),
            func.coalesce(func.sum(IngestBatch.duplicate_count), 0),
        ).where(IngestBatch.shipment_id == shipment_id)
    ).one()
    return {"rejected": int(row[0]), "duplicates": int(row[1])}
