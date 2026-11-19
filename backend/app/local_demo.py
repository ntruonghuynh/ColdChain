"""Opt-in credentials for disposable, loopback-only classroom demonstrations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.models import AppUser, UserRole
from app.db.models.enums import Role

LOCAL_DEMO_PASSWORD = "123"
LOCAL_DEMO_ACCOUNTS: dict[str, tuple[str, str, Role]] = {
    "quality": ("Quality classroom demo", "ORG-RECEIVER", Role.QUALITY),
    "warehouse": ("Warehouse classroom demo", "ORG-RECEIVER", Role.WAREHOUSE),
    "carrier": ("Carrier classroom demo", "ORG-CARRIER", Role.CARRIER),
    "shipper": ("Shipper classroom demo", "ORG-SHIPPER", Role.SHIPPER),
    "admin": ("Administrator classroom demo", "ORG-PLATFORM", Role.ADMIN),
}


def is_local_demo_username(username: str) -> bool:
    return username in LOCAL_DEMO_ACCOUNTS


def provision_local_demo_accounts(session: Session, *, database_was_empty: bool) -> list[str]:
    """Provision once on a fresh database; later seed runs only verify, never rewrite."""
    existing_accounts = {
        username: session.scalar(select(AppUser).where(AppUser.username == username))
        for username in LOCAL_DEMO_ACCOUNTS
    }
    if not database_was_empty:
        if all(_matches_expected_account(session, username, user)
               for username, user in existing_accounts.items()):
            return []
        raise RuntimeError(
            "LOCAL_DEMO_MODE can only be enabled on a fresh database; existing users were not changed"
        )

    if any(user is not None for user in existing_accounts.values()):
        raise RuntimeError("refusing to replace an existing local classroom demo account")

    created: list[str] = []
    for username, (display_name, org_id, role) in LOCAL_DEMO_ACCOUNTS.items():
        user = AppUser(
            username=username,
            display_name=display_name,
            org_id=org_id,
            is_demo_user=True,
            password_hash=hash_password(LOCAL_DEMO_PASSWORD, allow_short_local_demo_password=True),
        )
        session.add(user)
        session.flush()
        session.add(UserRole(user_id=user.user_id, role=role))
        created.append(username)
    session.flush()
    return created


def _matches_expected_account(session: Session, username: str, user: AppUser | None) -> bool:
    if user is None:
        return False
    _display_name, org_id, role = LOCAL_DEMO_ACCOUNTS[username]
    if (not user.is_active or not user.is_demo_user or user.org_id != org_id
            or not verify_password(LOCAL_DEMO_PASSWORD, user.password_hash)):
        return False
    active_roles = set(session.scalars(select(UserRole.role).where(
        UserRole.user_id == user.user_id, UserRole.revoked_at.is_(None)
    )).all())
    return active_roles == {role}
