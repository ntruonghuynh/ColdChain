"""Opt-in classroom accounts keep the existing M5 auth and workflow gates intact."""

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password, verify_password
from app.db.models import AppUser, UserRole
from app.local_demo import LOCAL_DEMO_ACCOUNTS, LOCAL_DEMO_PASSWORD
from app.seed.loader import SeedConflictError, run_seed


def _demo_settings() -> Settings:
    return Settings(app_env="local", local_demo_mode=True, frontend_bind_address="127.0.0.1",
                    jwt_secret=SecretStr("j" * 48))


def test_local_demo_mode_requires_local_loopback_configuration() -> None:
    assert Settings().local_demo_mode is False
    with pytest.raises(ValidationError, match="loopback IP"):
        Settings(app_env="local", local_demo_mode=True, frontend_bind_address="0.0.0.0")
    with pytest.raises(ValidationError, match="APP_ENV=local"):
        Settings(local_demo_mode=True, app_env="production")


def test_short_password_is_hashed_only_through_explicit_demo_path() -> None:
    with pytest.raises(ValueError, match="at least 12 characters"):
        hash_password("123")
    encoded = hash_password("123", allow_short_local_demo_password=True)
    assert encoded.startswith("pbkdf2_sha256$310000$")
    assert verify_password("123", encoded)


def test_fresh_seed_provisions_idempotent_alias_accounts(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    db_session.execute(delete(UserRole))
    db_session.execute(delete(AppUser))
    monkeypatch.setattr("app.seed.loader.get_settings", _demo_settings)

    first = run_seed(db_session)
    users = {user.username: user for user in db_session.scalars(select(AppUser)).all()}
    assert set(LOCAL_DEMO_ACCOUNTS) <= set(users)
    for username, (_display, org_id, role) in LOCAL_DEMO_ACCOUNTS.items():
        user = users[username]
        assert user.org_id == org_id and user.is_demo_user and user.is_active
        assert verify_password(LOCAL_DEMO_PASSWORD, user.password_hash)
        assert db_session.get(UserRole, (user.user_id, role)) is not None
    hashes = {name: users[name].password_hash for name in LOCAL_DEMO_ACCOUNTS}
    assert set(LOCAL_DEMO_ACCOUNTS) <= set(first.created)

    second = run_seed(db_session)
    users_after = {user.username: user for user in db_session.scalars(select(AppUser)).all()}
    assert second.created == []
    assert hashes == {name: users_after[name].password_hash for name in LOCAL_DEMO_ACCOUNTS}


def test_existing_database_refuses_first_time_local_demo_activation(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.seed.loader.get_settings", _demo_settings)
    with pytest.raises(SeedConflictError, match="fresh database"):
        run_seed(db_session)
    db_session.rollback()
    assert all(db_session.scalar(select(AppUser).where(AppUser.username == username)) is None
               for username in LOCAL_DEMO_ACCOUNTS)


def test_local_demo_login_and_quality_warehouse_authorization_are_separate(
    db_session: Session,
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_session.execute(delete(UserRole))
    db_session.execute(delete(AppUser))
    monkeypatch.setattr("app.seed.loader.get_settings", _demo_settings)
    run_seed(db_session)
    monkeypatch.setattr("app.api.auth.get_settings", _demo_settings)
    monkeypatch.setattr("app.core.security.get_settings", _demo_settings)

    tokens: dict[str, str] = {}
    for username, (_display, _org, role) in LOCAL_DEMO_ACCOUNTS.items():
        response = client.post("/api/auth/login", json={"username": username, "password": "123"})
        assert response.status_code == 200
        tokens[username] = response.json()["data"]["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens[username]}"})
        assert me.status_code == 200
        assert me.json()["data"]["roles"] == [role.value]
        assert client.get("/api/ledger/transactions",
                          headers={"Authorization": f"Bearer {tokens[username]}"}).status_code == 200

    assert client.get("/api/ledger/transactions").status_code == 401
    monkeypatch.setattr("app.api.auth.get_settings", lambda: Settings(jwt_secret=SecretStr("j" * 48)))
    assert client.post("/api/auth/login", json={"username": "quality", "password": "123"}).status_code == 401
    monkeypatch.setattr("app.api.auth.get_settings", _demo_settings)

    # Mock the business services so authorized route access is verified without writes.
    import app.api.workflow as workflow_api

    monkeypatch.setattr(workflow_api, "record_disposition",
                        lambda *_args, **_kwargs: {"authorized": "QUALITY"})
    monkeypatch.setattr(workflow_api, "release_warehouse",
                        lambda *_args, **_kwargs: {"authorized": "WAREHOUSE"})
    quality_headers = {"Authorization": f"Bearer {tokens['quality']}"}
    warehouse_headers = {"Authorization": f"Bearer {tokens['warehouse']}"}
    shipment_id = "00000000-0000-0000-0000-000000000001"

    quality_action = client.post(
        f"/api/workflow/shipments/{shipment_id}/disposition", headers=quality_headers,
        json={"business_ref": "test-quality", "decision": "RELEASE", "rationale": "mocked auth gate"},
    )
    warehouse_action = client.post(
        f"/api/workflow/shipments/{shipment_id}/release", headers=warehouse_headers,
        json={"business_ref": "test-warehouse"},
    )
    assert quality_action.status_code == 202
    assert quality_action.json()["data"]["authorized"] == "QUALITY"
    assert warehouse_action.status_code == 202
    assert warehouse_action.json()["data"]["authorized"] == "WAREHOUSE"
    assert client.post(f"/api/workflow/shipments/{shipment_id}/release", headers=quality_headers,
                       json={"business_ref": "wrong-quality-release"}).status_code == 403
    assert client.post(f"/api/workflow/shipments/{shipment_id}/disposition", headers=warehouse_headers,
                       json={"business_ref": "wrong-warehouse-disposition", "decision": "RELEASE",
                             "rationale": "must be forbidden"}).status_code == 403
