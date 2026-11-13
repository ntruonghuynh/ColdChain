"""Enumerations used by the data model.

Values mirror docs/architecture.md (sections 5, 7.2 and 7.4). Adding a value
requires a migration because each enum is stored with a CHECK constraint.
"""

from enum import StrEnum


class OrgType(StrEnum):
    SHIPPER = "SHIPPER"
    CARRIER = "CARRIER"
    RECEIVER = "RECEIVER"
    PLATFORM = "PLATFORM"


class Role(StrEnum):
    SHIPPER = "SHIPPER"
    CARRIER = "CARRIER"
    QUALITY = "QUALITY"
    WAREHOUSE = "WAREHOUSE"
    MONITOR = "MONITOR"
    ADMIN = "ADMIN"


class PolicyStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class DataOrigin(StrEnum):
    """Honest labelling of where data came from (NFR-01)."""

    SIMULATED = "SIMULATED"
    MEASURED = "MEASURED"


class ShipmentStatus(StrEnum):
    CREATED = "CREATED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    AWAITING_DISPOSITION = "AWAITING_DISPOSITION"
    RELEASE_APPROVED = "RELEASE_APPROVED"
    QUARANTINED = "QUARANTINED"
    RELEASED = "RELEASED"


class IngestSource(StrEnum):
    GATEWAY = "GATEWAY"
    SIMULATOR = "SIMULATOR"
    MANUAL = "MANUAL"


class RecordKind(StrEnum):
    READING = "READING"
    CONTEXT = "CONTEXT"


class DoorState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class IncidentCategory(StrEnum):
    TEMPERATURE_EXCURSION = "TEMPERATURE_EXCURSION"
    DATA_GAP = "DATA_GAP"
    SENSOR_FAULT_SUSPECTED = "SENSOR_FAULT_SUSPECTED"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class DetectionSource(StrEnum):
    POLICY_BASELINE = "POLICY_BASELINE"
    ML_MODEL = "ML_MODEL"
    GAP_DETECTOR = "GAP_DETECTOR"
    MANUAL = "MANUAL"


class Decision(StrEnum):
    RELEASE = "RELEASE"
    QUARANTINE = "QUARANTINE"


class CustodyStage(StrEnum):
    PICKUP = "PICKUP"
    DELIVERY = "DELIVERY"


class BusinessEventType(StrEnum):
    SHIPMENT_REGISTERED = "SHIPMENT_REGISTERED"
    CUSTODY_ACCEPTED = "CUSTODY_ACCEPTED"
    SENSOR_BATCH_ANCHORED = "SENSOR_BATCH_ANCHORED"
    INCIDENT_OPENED = "INCIDENT_OPENED"
    DISPOSITION_RECORDED = "DISPOSITION_RECORDED"
    WAREHOUSE_RELEASED = "WAREHOUSE_RELEASED"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    RETRY = "RETRY"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
