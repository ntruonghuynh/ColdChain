"""Idempotent import of a verified synthetic dataset into PostgreSQL.

What is written
---------------
Observed side (operational tables, as a monitoring system would hold them):
``sensor``, ``shipment`` (``data_origin = SIMULATED``, ``source_dataset_id``),
``sensor_assignment``, ``ingest_batch`` (one per received upload), ``reading`` and
``context_reading`` with ``event_at`` and ``received_at`` exactly as in the files (FR-03).

Ground truth (schema ``ground_truth``): ``journey`` and ``event``. Slot-level truth
(``ground_truth/slots.csv.gz``) stays in the files.

Provenance: one ``dataset_release`` row with the full manifest.

Safety rules
------------
* Files are verified against the manifest before anything is written (I-9).
* The labels must come from the policy stored in the database: the policy's
  ``content_sha256`` must equal the manifest's (CLAUDE.md rule 3).
* Idempotent: re-importing a dataset with the same fingerprint writes nothing and
  checks that the stored row counts still match the manifest.
* No silent merge: a different dataset with the same ID, or existing shipments or sensors
  with the same IDs, is a conflict and nothing is written.
* All-or-nothing: the caller commits once; any error leaves the database unchanged.
  A PostgreSQL advisory lock serialises concurrent imports.
* Records are validated strictly; one invalid record fails the whole import (the
  dataset is generated, so an invalid record means a broken dataset).
  Business validation of live data (BR-07, BR-08) belongs to Milestone 3 ingestion.

This is not the Milestone 3 ingestion path and runs no detection.
"""

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import Table, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.dataset.manifest import DatasetIntegrityError, VerifiedDataset, load_and_verify
from app.db.models import (
    ContextReading,
    DatasetRelease,
    GroundTruthEvent,
    GroundTruthJourney,
    IngestBatch,
    Organization,
    Policy,
    Reading,
    Sensor,
    SensorAssignment,
    Shipment,
)
from app.db.models.enums import DataOrigin, DoorState, IngestSource

ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:coldchain:dataset-import")
ADVISORY_LOCK_SQL = text("SELECT pg_advisory_xact_lock(hashtext('coldchain.dataset_import'))")
SHIPPER_ORG, CARRIER_ORG, RECEIVER_ORG = "ORG-SHIPPER", "ORG-CARRIER", "ORG-RECEIVER"
TEMP_RANGE_C = (Decimal("-40"), Decimal("60"))  # logger physical range; matches the generator config
CHUNK = 5000


class DatasetConflictError(RuntimeError):
    """The dataset clashes with data already in the database."""


class PolicyMismatchError(RuntimeError):
    """The dataset's labels were derived from a policy that differs from the stored one."""


@dataclass
class ImportReport:
    dataset_id: str
    status: str  # "imported" | "already_imported"
    fingerprint: str
    inserted: dict[str, int] = field(default_factory=dict)
    stored: dict[str, int] = field(default_factory=dict)

    def lines(self) -> list[str]:
        out = [f"dataset_id   {self.dataset_id}", f"fingerprint  {self.fingerprint}", f"status       {self.status}"]
        for table in self.stored:
            out.append(f"  {table:<26} inserted {self.inserted.get(table, 0):>8}   stored {self.stored[table]:>8}")
        return out


def stable_uuid(kind: str, key: str) -> uuid.UUID:
    """Deterministic primary keys: the same dataset gets the same IDs in every database."""
    return uuid.uuid5(ID_NAMESPACE, f"{kind}|{key}")


def parse_utc(value: str, field_name: str) -> datetime:
    if not value or not value.endswith("Z"):
        raise DatasetIntegrityError(f"{field_name}={value!r} is not a UTC timestamp ending in 'Z'")
    try:
        return datetime.fromisoformat(value[:-1]).replace(tzinfo=UTC)
    except ValueError as exc:
        raise DatasetIntegrityError(f"{field_name}={value!r} is not ISO 8601") from exc


def parse_decimal(value: str, field_name: str, *, nullable: bool = False) -> Decimal | None:
    if value == "":
        if nullable:
            return None  # "not reported" stays NULL, never a default value
        raise DatasetIntegrityError(f"{field_name} is empty")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise DatasetIntegrityError(f"{field_name}={value!r} is not a number") from exc


# ------------------------------------------------------------------ counting

def stored_counts(session: Session, dataset_id: str) -> dict[str, int]:
    ship = select(Shipment.shipment_id).where(Shipment.source_dataset_id == dataset_id).scalar_subquery()

    def count(stmt: Any) -> int:
        return int(session.scalar(stmt) or 0)

    return {
        "shipment": count(select(func.count()).select_from(Shipment).where(Shipment.source_dataset_id == dataset_id)),
        "sensor_assignment": count(select(func.count()).select_from(SensorAssignment)
                                   .where(SensorAssignment.shipment_id.in_(ship))),
        "ingest_batch": count(select(func.count()).select_from(IngestBatch).where(IngestBatch.shipment_id.in_(ship))),
        "reading": count(select(func.count()).select_from(Reading).where(Reading.shipment_id.in_(ship))),
        "context_reading": count(select(func.count()).select_from(ContextReading)
                                 .where(ContextReading.shipment_id.in_(ship))),
        "ground_truth.journey": count(select(func.count()).select_from(GroundTruthJourney)
                                      .where(GroundTruthJourney.dataset_id == dataset_id)),
        "ground_truth.event": count(select(func.count()).select_from(GroundTruthEvent)
                                    .where(GroundTruthEvent.dataset_id == dataset_id)),
    }


def expected_counts(ds: VerifiedDataset) -> dict[str, int]:
    shipments = ds.rows_expected("observed/shipments.csv")
    return {
        "shipment": shipments,
        "sensor_assignment": shipments,
        "ingest_batch": ds.rows_expected("observed/uploads.csv.gz"),
        "reading": ds.rows_expected("observed/readings.csv.gz"),
        "context_reading": ds.rows_expected("observed/context.csv.gz"),
        "ground_truth.journey": ds.rows_expected("ground_truth/journeys.csv"),
        "ground_truth.event": ds.rows_expected("ground_truth/events.csv.gz"),
    }


def _insert(session: Session, table: Table, rows: Iterable[dict[str, Any]]) -> int:
    batch: list[dict[str, Any]] = []
    total = 0
    for row in rows:
        batch.append(row)
        if len(batch) >= CHUNK:
            session.execute(pg_insert(table).on_conflict_do_nothing(), batch)
            total += len(batch)
            batch = []
    if batch:
        session.execute(pg_insert(table).on_conflict_do_nothing(), batch)
        total += len(batch)
    return total


# ------------------------------------------------------------------ import

def import_dataset(session: Session, dataset_dir: Path, *, now: datetime | None = None) -> ImportReport:
    """Verify and import. The caller commits on success and rolls back on any exception."""
    ds = load_and_verify(dataset_dir)
    manifest = ds.manifest
    dataset_id = ds.dataset_id
    fingerprint = str(manifest["dataset_fingerprint"])
    expected = expected_counts(ds)

    session.execute(ADVISORY_LOCK_SQL)

    existing = session.get(DatasetRelease, dataset_id)
    if existing is not None:
        if existing.dataset_fingerprint != fingerprint:
            raise DatasetConflictError(
                f"{dataset_id} is already imported with different content (stored fingerprint "
                f"{existing.dataset_fingerprint}, file fingerprint {fingerprint}). Datasets are immutable: "
                "generate a new dataset version instead.")
        stored = stored_counts(session, dataset_id)
        if stored != expected:
            raise DatasetIntegrityError(f"{dataset_id} is registered but stored counts {stored} differ from "
                                        f"the manifest {expected}")
        return ImportReport(dataset_id, "already_imported", fingerprint, {}, stored)
    same_content = session.scalar(select(DatasetRelease.dataset_id)
                                  .where(DatasetRelease.dataset_fingerprint == fingerprint))
    if same_content is not None:
        raise DatasetConflictError(f"The same content is already imported as {same_content}")

    # ---- policy: labels must come from the stored policy version -----------------
    pol = manifest["policy"]
    policy = session.scalar(select(Policy).where(Policy.policy_code == pol["policy_code"],
                                                 Policy.policy_version == pol["policy_version"]))
    if policy is None:
        raise PolicyMismatchError(f"Policy {pol['policy_code']} v{pol['policy_version']} is not in the database "
                                  "(run the seed first)")
    if policy.content_sha256 != pol["content_sha256"] or policy.product_id != pol["product_id"]:
        raise PolicyMismatchError(
            f"Dataset labels were derived from policy content {pol['content_sha256']}, but the stored "
            f"{pol['policy_code']} v{pol['policy_version']} has {policy.content_sha256}. Refusing to import.")
    for org in (SHIPPER_ORG, CARRIER_ORG, RECEIVER_ORG):
        if session.get(Organization, org) is None:
            raise DatasetConflictError(f"Organization {org} is missing (run the seed first)")

    # ---- observed: shipments and sensors -------------------------------------------
    shipments = list(ds.rows("observed/shipments.csv"))
    ship_ids = [r["shipment_id"] for r in shipments]
    sensor_of = {r["shipment_id"]: r["sensor_id"] for r in shipments}
    if len(set(ship_ids)) != len(ship_ids) or len(set(sensor_of.values())) != len(ship_ids):
        raise DatasetIntegrityError("Shipment or sensor IDs are not unique in observed/shipments.csv")
    clash = session.scalars(select(Shipment.shipment_id).where(Shipment.shipment_id.in_(ship_ids)).limit(5)).all()
    clash += session.scalars(select(Sensor.sensor_id).where(Sensor.sensor_id.in_(sensor_of.values())).limit(5)).all()
    if clash:
        raise DatasetConflictError(f"IDs already exist in the database (another dataset or manual data): {clash}")

    window: dict[str, tuple[datetime, datetime]] = {}
    for r in shipments:
        if r["dataset_id"] != dataset_id or r["data_origin"] != DataOrigin.SIMULATED.value:
            raise DatasetIntegrityError(f"{r['shipment_id']}: dataset_id/data_origin do not match the manifest")
        if r["policy_code"] != pol["policy_code"] or r["policy_version"] != pol["policy_version"]:
            raise DatasetIntegrityError(f"{r['shipment_id']}: policy differs from the manifest")
        dep, arr = parse_utc(r["departure_at"], "departure_at"), parse_utc(r["arrival_at"], "arrival_at")
        if arr <= dep:
            raise DatasetIntegrityError(f"{r['shipment_id']}: arrival_at is not after departure_at")
        window[r["shipment_id"]] = (dep, arr)

    imported_at = now or datetime.now(UTC)
    session.add(DatasetRelease(
        dataset_id=dataset_id,
        dataset_name=manifest["dataset_name"],
        dataset_version=manifest["dataset_version"],
        data_origin=DataOrigin.SIMULATED,
        generator_name=manifest["generator"]["name"],
        generator_version=manifest["generator"]["version"],
        config_version=manifest["config"]["config_version"],
        config_sha256=manifest["config"]["sha256"],
        seed=int(manifest["seed"]),
        split_seed=int(manifest["split_seed"]),
        journey_count=int(manifest["journey_count"]),
        policy_id=policy.policy_id,
        policy_content_sha256=pol["content_sha256"],
        dataset_fingerprint=fingerprint,
        manifest=manifest,
        imported_at=imported_at,
    ))
    session.flush()

    inserted: dict[str, int] = {}
    inserted["sensor"] = _insert(session, Sensor.__table__, (
        {"sensor_id": r["sensor_id"], "sensor_type": "TEMPERATURE_LOGGER", "owner_org_id": CARRIER_ORG,
         "description": f"Simulated logger ({dataset_id})"} for r in shipments))
    inserted["shipment"] = _insert(session, Shipment.__table__, (
        {"shipment_id": r["shipment_id"], "product_id": policy.product_id, "policy_id": policy.policy_id,
         "shipper_org_id": SHIPPER_ORG, "carrier_org_id": CARRIER_ORG, "receiver_org_id": RECEIVER_ORG,
         "origin": r["origin"] or None, "destination": r["destination"] or None,
         "data_origin": DataOrigin.SIMULATED.value, "source_dataset_id": dataset_id} for r in shipments))
    inserted["sensor_assignment"] = _insert(session, SensorAssignment.__table__, (
        {"assignment_id": stable_uuid("assignment", r["shipment_id"]), "sensor_id": r["sensor_id"],
         "shipment_id": r["shipment_id"], "assigned_from": window[r["shipment_id"]][0],
         "assigned_to": window[r["shipment_id"]][1]} for r in shipments))

    # ---- uploads -> ingest_batch ------------------------------------------------------
    batch_of: dict[str, tuple[uuid.UUID, str, datetime]] = {}

    def batches() -> Iterable[dict[str, Any]]:
        for r in ds.rows("observed/uploads.csv.gz"):
            sid = r["shipment_id"]
            if sid not in sensor_of or r["sensor_id"] != sensor_of[sid]:
                raise DatasetIntegrityError(f"upload {r['upload_id']}: unknown shipment or sensor")
            received = parse_utc(r["received_at"], "received_at")
            first, last = parse_utc(r["first_event_at"], "first_event_at"), parse_utc(r["last_event_at"], "last_event_at")
            if not first <= last <= received:
                raise DatasetIntegrityError(f"upload {r['upload_id']}: event range not before received_at")
            count = int(r["reading_count"])
            batch_id = stable_uuid("ingest_batch", r["upload_id"])
            batch_of[r["upload_id"]] = (batch_id, sid, received)
            yield {"batch_id": batch_id, "business_ref": r["upload_id"], "shipment_id": sid,
                   "submitted_by_org_id": CARRIER_ORG, "source": IngestSource.SIMULATOR.value,
                   "data_origin": DataOrigin.SIMULATED.value, "received_at": received,
                   "first_event_at": first, "last_event_at": last,
                   # one temperature reading and one context record per sample
                   "record_count": 2 * count, "accepted_count": 2 * count, "rejected_count": 0}

    inserted["ingest_batch"] = _insert(session, IngestBatch.__table__, batches())

    def common(r: dict[str, str], kind: str) -> dict[str, Any]:
        upload = batch_of.get(r["upload_id"])
        if upload is None or upload[1] != r["shipment_id"] or r["sensor_id"] != sensor_of.get(r["shipment_id"]):
            raise DatasetIntegrityError(f"{kind} {r['shipment_id']} {r['event_at']}: upload/shipment/sensor mismatch")
        event_at, received_at = parse_utc(r["event_at"], "event_at"), parse_utc(r["received_at"], "received_at")
        dep, arr = window[r["shipment_id"]]
        if not dep <= event_at <= arr:
            raise DatasetIntegrityError(f"{kind} {r['shipment_id']} {r['event_at']}: outside the journey")
        if received_at < event_at or received_at != upload[2]:
            raise DatasetIntegrityError(f"{kind} {r['shipment_id']} {r['event_at']}: received_at inconsistent")
        return {"sensor_id": r["sensor_id"], "shipment_id": r["shipment_id"], "ingest_batch_id": upload[0],
                "event_at": event_at, "received_at": received_at}

    def readings() -> Iterable[dict[str, Any]]:
        for r in ds.rows("observed/readings.csv.gz"):
            temp = parse_decimal(r["temperature_c"], "temperature_c")
            assert temp is not None
            if not TEMP_RANGE_C[0] <= temp <= TEMP_RANGE_C[1]:
                raise DatasetIntegrityError(f"temperature_c {temp} outside the logger range")
            yield {"reading_id": stable_uuid("reading", f"{r['sensor_id']}|{r['event_at']}"),
                   **common(r, "reading"), "temperature_c": temp}

    def contexts() -> Iterable[dict[str, Any]]:
        for r in ds.rows("observed/context.csv.gz"):
            door = r["door_state"] or None
            if door is not None and door not in DoorState.__members__:
                raise DatasetIntegrityError(f"door_state {door!r} invalid")
            battery = parse_decimal(r["battery_level_pct"], "battery_level_pct", nullable=True)
            if battery is not None and not Decimal(0) <= battery <= Decimal(100):
                raise DatasetIntegrityError(f"battery_level_pct {battery} outside 0-100")
            yield {"context_id": stable_uuid("context", f"{r['sensor_id']}|{r['event_at']}"),
                   **common(r, "context"), "door_state": door, "battery_level_pct": battery,
                   "ambient_temperature_c": parse_decimal(r["ambient_temperature_c"], "ambient_temperature_c",
                                                          nullable=True)}

    inserted["reading"] = _insert(session, Reading.__table__, readings())
    inserted["context_reading"] = _insert(session, ContextReading.__table__, contexts())

    # ---- ground truth (separate schema) -----------------------------------------------
    journey_ids: set[str] = set()

    def gt_journeys() -> Iterable[dict[str, Any]]:
        for r in ds.rows("ground_truth/journeys.csv"):
            if r["shipment_id"] not in window:
                raise DatasetIntegrityError(f"ground truth journey {r['journey_id']} has no shipment")
            journey_ids.add(r["journey_id"])
            core = ("journey_id", "shipment_id", "primary_scenario", "scenario_tags", "ambient_profile",
                    "route_type", "policy_excursion_count")
            yield {"journey_id": r["journey_id"], "dataset_id": dataset_id, "shipment_id": r["shipment_id"],
                   "primary_scenario": r["primary_scenario"], "scenario_tags": r["scenario_tags"].split(";"),
                   "ambient_profile": r["ambient_profile"], "route_type": r["route_type"],
                   "policy_excursion_count": int(r["policy_excursion_count"]),
                   "parameters": {k: v for k, v in r.items() if k not in core}}

    def gt_events() -> Iterable[dict[str, Any]]:
        for r in ds.rows("ground_truth/events.csv.gz"):
            if r["journey_id"] not in journey_ids:
                raise DatasetIntegrityError(f"event {r['event_id']} references unknown journey")
            yield {"event_id": r["event_id"], "dataset_id": dataset_id, "journey_id": r["journey_id"],
                   "event_type": r["event_type"], "label_source": r["label_source"], "cause": r["cause"],
                   "start_at": parse_utc(r["start_at"], "start_at"), "end_at": parse_utc(r["end_at"], "end_at"),
                   "duration_min": int(r["duration_min"]), "attributes": json.loads(r["attributes"])}

    inserted["ground_truth.journey"] = _insert(session, GroundTruthJourney.__table__, gt_journeys())
    inserted["ground_truth.event"] = _insert(session, GroundTruthEvent.__table__, gt_events())
    session.flush()

    stored = stored_counts(session, dataset_id)
    if stored != expected:
        raise DatasetIntegrityError(f"Row counts after import {stored} differ from the manifest {expected}; "
                                    "nothing is committed")
    inserted.pop("sensor", None)
    return ImportReport(dataset_id, "imported", fingerprint, inserted, stored)
