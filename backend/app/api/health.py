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
