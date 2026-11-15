"""FastAPI application factory.

All routes live under ``/api`` so the frontend's reverse proxy can forward the
path unchanged. OpenAPI docs: ``/api/docs`` (Swagger UI), ``/api/redoc``,
schema at ``/api/openapi.json``.
"""

import logging
import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, ingest, monitoring, predictions, reference, shipments, system
from app.api.schemas import ErrorEnvelope
from app.core.config import APP_NAME, APP_VERSION, get_settings
from app.core.errors import register_exception_handlers

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

DESCRIPTION = """
Backend for the **Cold Chain Monitoring and Excursion Response** teaching prototype.

Milestone 3 adds validated sensor ingestion (`POST /api/ingest/batches`, server receipt time),
telemetry monitoring (CURRENT / STALE / UNKNOWN), confirmed data gaps, the policy-threshold
baseline detector, append-only incidents and the excursion queue. Milestone 4 adds read-only,
advisory ML predictions from a frozen model. Read endpoints accept an `as_of` processing time and
show only what was known by then. LLM, blockchain, quality dispositions and authentication are
**not implemented yet** (see `GET /api/system/info`).

All data is simulated. Policies are teaching policies, not regulatory standards.
"""


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()

    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description=DESCRIPTION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        responses={
            422: {"model": ErrorEnvelope, "description": "Validation error"},
            500: {"model": ErrorEnvelope, "description": "Internal error"},
        },
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_PATTERN.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    if settings.cors_origins():
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins(),
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(system.router)
    api.include_router(reference.router)
    api.include_router(shipments.router)
    api.include_router(ingest.router)
    api.include_router(monitoring.router)
    api.include_router(predictions.router)
    app.include_router(api)
    return app


app = create_app()
