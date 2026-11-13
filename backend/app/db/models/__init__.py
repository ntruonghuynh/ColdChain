"""Import every model so Base.metadata is complete (used by Alembic and tests)."""

from app.db.models.ledger import BusinessEvent, ChainRecord, OutboxEntry
from app.db.models.reference import AppUser, Organization, Policy, Product, UserRole
from app.db.models.shipment import Sensor, SensorAssignment, Shipment
from app.db.models.telemetry import ContextReading, IngestBatch, Reading, RejectedRecord
from app.db.models.workflow import CustodyEvent, Disposition, DispositionIncident, Incident, WarehouseRelease

__all__ = [
    "AppUser",
    "BusinessEvent",
    "ChainRecord",
    "ContextReading",
    "CustodyEvent",
    "Disposition",
    "DispositionIncident",
    "Incident",
    "IngestBatch",
    "Organization",
    "OutboxEntry",
    "Policy",
    "Product",
    "Reading",
    "RejectedRecord",
    "Sensor",
    "SensorAssignment",
    "Shipment",
    "UserRole",
    "WarehouseRelease",
]
