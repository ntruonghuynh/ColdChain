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
                  note="M5 assigns role-specific password hashes from local secrets; monitor.service is non-login."),
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
    FeatureStatus(key="ml", name="Frozen advisory ML excursion predictions", status="available", milestone="M4",
                  note="Read-only causal inference; insufficient evidence is unknown and predictions cannot authorize release."),
    FeatureStatus(key="blockchain", name="Blockchain records and reconciliation",
                  status="available", milestone="M5",
                  note="Local Hardhat registry, transactional outbox, confirmation tracking and read-only reconciliation."),
    FeatureStatus(key="quality_workflow", name="Custody, quality disposition and release gate",
                  status="available", milestone="M5",
                  note="Only an authenticated Quality Officer can record disposition; warehouse release requires confirmed RELEASE."),
    FeatureStatus(key="llm", name="Evidence-grounded incident explanations (RAG)", status="available", milestone="M6",
                  note="Lexical retrieval and causal evidence work offline; LLM is optional/configurable. "
                       "Without provider credentials, status is not_configured or an explicitly labeled fallback."),
    FeatureStatus(key="authentication", name="User login and role-based access",
                  status="available", milestone="M5",
                  note="Local-demo bearer auth; not a production identity provider."),
    FeatureStatus(key="signed_audit", name="Signed database audit log and verification",
                  status="available", milestone="M5"),
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
