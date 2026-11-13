"""Health endpoints, response envelope and error handling."""

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.health import expected_revision
from app.core.config import get_settings
from app.db.session import build_engine, get_db
from app.main import app


def test_liveness(client: TestClient) -> None:
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"data": {"status": "ok"}, "meta": None}


def test_readiness_reports_database_ok_and_migration_head(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "ok"
    assert body["database"]["status"] == "ok"
    assert body["database"]["migration_revision"] == expected_revision() == "0001"
    assert body["database"]["latency_ms"] >= 0


def test_readiness_returns_503_when_database_unreachable() -> None:
    bad = get_settings().model_copy(update={"postgres_host": "127.0.0.1", "postgres_port": 1,
                                            "db_connect_timeout_s": 1, "database_url": None})
    engine = build_engine(bad)

    def _override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as test_client:
            response = test_client.get("/api/health")
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
    assert response.status_code == 503
    body = response.json()["data"]
    assert body["status"] == "degraded"
    assert body["database"]["status"] == "unavailable"


def test_request_id_is_generated_and_echoed(client: TestClient) -> None:
    generated = client.get("/api/health/live")
    assert len(generated.headers["X-Request-ID"]) == 32
    echoed = client.get("/api/health/live", headers={"X-Request-ID": "abc-123"})
    assert echoed.headers["X-Request-ID"] == "abc-123"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/does-not-exist", headers={"X-Request-ID": "req-1"})
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found",
                                         "details": None, "request_id": "req-1"}}


def test_validation_error_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/shipments", params={"limit": 0})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["query", "limit"]


def test_missing_resource_uses_not_found_code(client: TestClient) -> None:
    response = client.get("/api/shipments/NO-SUCH-SHIPMENT")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_openapi_schema_is_served(client: TestClient) -> None:
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in ["/api/health", "/api/health/live", "/api/system/info", "/api/policies",
                 "/api/organizations", "/api/shipments"]:
        assert path in paths
