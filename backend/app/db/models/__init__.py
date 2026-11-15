"""Import every model so Base.metadata is complete (used by Alembic and tests)."""

from app.db.models.dataset import DatasetRelease
from app.db.models.ground_truth import GroundTruthEvent, GroundTruthJourney
from app.db.models.ledger import BusinessEvent, ChainRecord, OutboxEntry
from app.db.models.monitoring import (
    DataGap,
    DataQualityWarning,
    DecisionReassessment,
    Detection,
    DetectorConfigVersion,
    DetectorEvaluation,
    IncidentRevision,
)
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
    "DataGap",
    "DataQualityWarning",
    "DatasetRelease",
    "DecisionReassessment",
    "Detection",
    "DetectorConfigVersion",
    "DetectorEvaluation",
    "Disposition",
    "DispositionIncident",
    "GroundTruthEvent",
    "GroundTruthJourney",
    "Incident",
    "IncidentRevision",
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
