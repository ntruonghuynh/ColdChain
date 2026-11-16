"""Small local-demo password and signed bearer-token helpers.

This is not an identity provider. Configure a random JWT_SECRET and never use the
shared demo password outside an isolated local demonstration.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AppUser, UserRole
from app.db.models.enums import Role
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("demo password must be at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, rounds, salt_hex, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def issue_token(user: AppUser, roles: list[Role]) -> str:
    settings = get_settings()
    secret = settings.jwt_secret.get_secret_value()
    if len(secret) < 32 or secret == "change-me-local-only":
        raise HTTPException(status_code=503, detail="Bearer authentication is not configured")
    now = int(time.time())
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    body = _b64(json.dumps({
        "sub": str(user.user_id), "org": user.org_id,
        "roles": [role.value for role in roles], "iat": now,
        "exp": now + settings.jwt_expires_min * 60,
    }, separators=(",", ":")).encode())
    signing = f"{header}.{body}".encode()
    sig = hmac.new(secret.encode(), signing, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(sig)}"


@dataclass(frozen=True)
class Principal:
    user: AppUser
    roles: frozenset[Role]


def get_current_principal(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Principal:
    settings = get_settings()
    secret = settings.jwt_secret.get_secret_value()
    if len(secret) < 32 or secret == "change-me-local-only":
        raise HTTPException(status_code=503, detail="Bearer authentication is not configured")
    try:
        head, body, signature = token.split(".")
        header = json.loads(base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)))
        if header != {"alg": "HS256", "typ": "JWT"}:
            raise ValueError("algorithm")
        signing = f"{head}.{body}".encode()
        expected = _b64(hmac.new(secret.encode(), signing, hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload["exp"]) <= int(time.time()):
            raise ValueError("expired")
        subject, org, token_roles = payload["sub"], payload["org"], frozenset(Role(v) for v in payload["roles"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired bearer token") from exc
    user = db.get(AppUser, subject)
    if user is None or not user.is_active or user.org_id != org:
        raise HTTPException(status_code=401, detail="Invalid or expired bearer token")
    active_roles = frozenset(db.scalars(select(UserRole.role).where(
        UserRole.user_id == user.user_id, UserRole.revoked_at.is_(None)
    )).all())
    if not token_roles.issubset(active_roles):
        raise HTTPException(status_code=401, detail="Invalid or expired bearer token")
    return Principal(user=user, roles=token_roles)


def require_roles(*roles: Role):
    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not principal.roles.intersection(roles):
            raise HTTPException(status_code=403, detail="This account is not authorized for this action")
        return principal
    return dependency
