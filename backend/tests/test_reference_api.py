"""Read-only API endpoints return real database content (no fabricated values)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_shipment


def test_policies_endpoint_returns_approved_teaching_policy(client: TestClient) -> None:
    response = client.get("/api/policies", params={"status": "ACTIVE"})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    policy = body["data"][0]
    assert policy["policy_code"] == "POL-CHILL-01"
    assert policy["product_id"] == "PRD-CHILL-01"
    assert policy["limits"] == {"min_temp_c": "2.00", "max_temp_c": "8.00"}
    assert policy["duration_rule"] == {"high_excursion_min_duration_min": 30, "low_excursion_min_duration_min": 15}
    assert policy["missing_data_rule"] == {"gap_unknown_after_min": 15, "gap_review_at_min": 30}
    assert policy["release_authority_role"] == "QUALITY"
    assert policy["is_teaching_policy"] is True
    assert "not a regulatory" in policy["disclaimer"]

    single = client.get(f"/api/policies/{policy['policy_id']}")
    assert single.status_code == 200
    assert single.json()["data"]["content_sha256"] == policy["content_sha256"]


def test_organizations_list_roles_and_no_credentials(client: TestClient) -> None:
    response = client.get("/api/organizations")
    assert response.status_code == 200
    orgs = {o["org_id"]: o for o in response.json()["data"]}
    assert set(orgs) == {"ORG-SHIPPER", "ORG-CARRIER", "ORG-RECEIVER", "ORG-PLATFORM"}
    receiver_users = {u["username"]: u for u in orgs["ORG-RECEIVER"]["users"]}
    assert receiver_users["quality.demo"]["roles"] == ["QUALITY"]
    assert all(not u["has_credentials"] for o in orgs.values() for u in o["users"])


def test_shipments_list_is_empty_without_ingestion(client: TestClient) -> None:
    response = client.get("/api/shipments")
    assert response.status_code == 200
    assert response.json() == {"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}}


def test_shipments_list_returns_database_rows(client: TestClient, db_session: Session) -> None:
    make_shipment(db_session, "TEST-SHP-API-1")
    response = client.get("/api/shipments")
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["shipment_id"] == "TEST-SHP-API-1"
    assert body["data"][0]["data_origin"] == "SIMULATED"
    assert body["data"][0]["status"] == "CREATED"
    assert client.get("/api/shipments/TEST-SHP-API-1").status_code == 200


def test_system_info_marks_future_features_not_implemented(client: TestClient) -> None:
    response = client.get("/api/system/info")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["milestone"] == "M3"
    features = {f["key"]: f for f in data["features"]}
    for key in ["ml", "llm", "blockchain", "quality_workflow", "authentication"]:
        assert features[key]["status"] == "not_implemented", key
    assert features["ingestion"]["status"] == "available"   # Milestone 3
    assert features["database"]["status"] == "available"
    assert features["synthetic_data"]["status"] == "available"
