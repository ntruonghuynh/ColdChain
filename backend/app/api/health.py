"""Health endpoints.

* ``GET /api/health/live``  — process is up (no dependencies). Used for liveness.
* ``GET /api/health``       — readiness: database reachable and schema at the
  expected Alembic revision. Returns 200 when ready and 503 when degraded; the
  body is the same ``{"data": HealthReport}`` shape in both cases so clients can
  show which component failed.
"""

import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.schemas import DatabaseHealth, Envelope, HealthReport
from app.db.session import get_db
from app.integrations.chain_gateway import ChainGateway
from app.integrations.llm_adapter import provider_readiness

router = APIRouter(prefix="/health", tags=["health"])

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@lru_cache
def expected_revision() -> str | None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent / "migrations"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def check_database(db: Session) -> DatabaseHealth:
    expected = expected_revision()
    started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
    except SQLAlchemyError as exc:
        db.rollback()
        return DatabaseHealth(status="unavailable", expected_revision=expected,
                              detail=exc.__class__.__name__)
    try:
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except SQLAlchemyError:
        db.rollback()  # table missing: migrations have never run
        revision = None
    if revision != expected:
        return DatabaseHealth(status="migration_pending", latency_ms=latency_ms,
                              migration_revision=revision, expected_revision=expected,
                              detail="Database schema is not at the expected migration revision.")
    return DatabaseHealth(status="ok", latency_ms=latency_ms, migration_revision=revision,
                          expected_revision=expected)


@router.get("/live", response_model=Envelope[dict[str, str]], summary="Liveness check")
def live() -> Envelope[dict[str, str]]:
    return Envelope(data={"status": "ok"})


@router.get(
    "",
    response_model=Envelope[HealthReport],
    summary="Readiness check (API + database + migrations)",
    responses={503: {"model": Envelope[HealthReport], "description": "A dependency is not ready"}},
)
def health(db: Session = Depends(get_db)) -> JSONResponse:
    database = check_database(db)
    report = HealthReport(
        status="ok" if database.status == "ok" else "degraded",
        database=database,
        checked_at=datetime.now(UTC),
    )
    return JSONResponse(
        status_code=200 if report.status == "ok" else 503,
        content=Envelope(data=report).model_dump(mode="json"),
    )


@router.get("/ledger", summary="Blockchain RPC and deployment readiness")
def ledger_health() -> JSONResponse:
    try:
        gateway = ChainGateway()
        connected = gateway.web3.is_connected()
        if not connected:
            raise RuntimeError("RPC unavailable")
        chain_id = gateway.web3.eth.chain_id
        deployed_code = gateway.web3.eth.get_code(gateway.address)
        if chain_id != gateway.settings.chain_id or not deployed_code:
            raise RuntimeError("Chain ID mismatch or contract code is missing")
        body = {"data": {"status": "ok", "chain_id": chain_id,
                          "contract_address": gateway.address, "contract_code_present": True}}
        return JSONResponse(status_code=200, content=body)
    except Exception as exc:
        return JSONResponse(status_code=503, content={"data": {
            "status": "degraded", "detail": type(exc).__name__,
        }})


@router.get("/llm", summary="RAG index and optional LLM provider readiness")
def llm_health() -> JSONResponse:
    result = provider_readiness()
    code = 200 if result.get("status") == "ok" else 503
    return JSONResponse(status_code=code, content={"data": result})
