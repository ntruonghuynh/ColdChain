"""System information, including an honest list of which features exist yet."""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.schemas import Envelope, FeatureStatus, SystemInfo
from app.core.config import APP_NAME, APP_VERSION, CURRENT_MILESTONE, get_settings

router = APIRouter(prefix="/system", tags=["system"])

# Keep in sync with docs/implementation-plan.md. Only mark a feature "available"
# when it is implemented and tested.
FEATURES: list[FeatureStatus] = [
    FeatureStatus(key="database", name="Database and migrations", status="available", milestone="M1"),
    FeatureStatus(key="reference_data", name="Teaching policy, organizations and demo users",
                  status="available", milestone="M1",
                  note="Demo users have no login credentials yet."),
    FeatureStatus(key="shipments_read", name="Shipment list (read-only)", status="available", milestone="M1",
                  note="Empty until the synthetic dataset is imported (manual command, see README)."),
    FeatureStatus(key="synthetic_data", name="Synthetic journey dataset and import", status="available",
                  milestone="M2",
                  note="Canonical simulated dataset in data/release/, imported with a manual command. "
                       "Detection runs on it with `python -m app.monitoring replay` (Milestone 3)."),
    FeatureStatus(key="ingestion", name="Reading ingestion, gap detection and threshold baseline",
                  status="available", milestone="M3",
                  note="Live ingestion API (server receipt time), monitoring states, confirmed gaps, "
                       "policy-baseline excursions, incidents and excursion queue. Incidents stay open: "
                       "quality dispositions arrive in Milestone 5."),
    FeatureStatus(key="ml", name="ML excursion detection", status="not_implemented", milestone="M4"),
    FeatureStatus(key="blockchain", name="Blockchain records and reconciliation",
                  status="not_implemented", milestone="M5"),
    FeatureStatus(key="quality_workflow", name="Quality disposition and release gate",
                  status="not_implemented", milestone="M5"),
    FeatureStatus(key="llm", name="LLM response drafts (RAG)", status="not_implemented", milestone="M6"),
    FeatureStatus(key="authentication", name="User login and role-based access",
                  status="not_implemented", milestone="M5/M7"),
]


@router.get("/info", response_model=Envelope[SystemInfo], summary="Application and feature status")
def info() -> Envelope[SystemInfo]:
    settings = get_settings()
    return Envelope(
        data=SystemInfo(
            app_name=APP_NAME,
            version=APP_VERSION,
            milestone=CURRENT_MILESTONE,
            environment=settings.app_env,
            server_time=datetime.now(UTC),
            features=FEATURES,
        )
    )
