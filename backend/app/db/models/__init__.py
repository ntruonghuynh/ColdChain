"""Import every model so Base.metadata is complete (used by Alembic and tests)."""

from app.db.models.dataset import DatasetRelease
from app.db.models.ground_truth import GroundTruthEvent, GroundTruthJourney
from app.db.models.ledger import AuditLogEntry, BusinessEvent, ChainRecord, OutboxAttempt, OutboxEntry
from app.db.models.ml import MLPrediction
from app.db.models.monitoring import (
    DataGap,
    DataQualityWarning,
    DecisionReassessment,
    Detection,
    DetectorConfigVersion,
    DetectorEvaluation,
    IncidentRevision,
)
from app.db.models.reference import AppUser, Organization, OrganizationChainRole, Policy, Product, UserRole
from app.db.models.shipment import Sensor, SensorAssignment, Shipment
from app.db.models.telemetry import ContextReading, IngestBatch, Reading, RejectedRecord
from app.db.models.workflow import (
    CustodyEvent, Disposition, DispositionIncident, Incident, ReassessmentResolution, WarehouseRelease,
)

__all__ = [
    "AppUser",
    "AuditLogEntry",
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
    "MLPrediction",
    "IngestBatch",
    "Organization",
    "OrganizationChainRole",
    "OutboxEntry",
    "OutboxAttempt",
    "Policy",
    "Product",
    "Reading",
    "RejectedRecord",
    "ReassessmentResolution",
    "Sensor",
    "SensorAssignment",
    "Shipment",
    "UserRole",
    "WarehouseRelease",
]
