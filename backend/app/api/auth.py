"""Local-demo login. Roles are read from active database grants, never from the request."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import Envelope
from app.core.config import get_settings
from app.core.security import Principal, get_current_principal, issue_token, verify_password
from app.db.models import AppUser, UserRole
from app.db.session import get_db
from app.local_demo import is_local_demo_username

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    username: str
    organization_id: str
    roles: list[str]


@router.post("/login", response_model=Envelope[LoginOut], summary="Create a local-demo bearer token")
def login(body: LoginIn, db: Session = Depends(get_db)) -> Envelope[LoginOut]:
    settings = get_settings()
    if is_local_demo_username(body.username) and not settings.local_demo_mode:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    user = db.scalar(select(AppUser).where(AppUser.username == body.username))
    if (user is None or user.username == "monitor.service" or not user.is_active
            or not verify_password(body.password, user.password_hash)):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    roles = list(db.scalars(select(UserRole.role).where(
        UserRole.user_id == user.user_id, UserRole.revoked_at.is_(None)
    )).all())
    return Envelope(data=LoginOut(
        access_token=issue_token(user, roles), expires_in_seconds=settings.jwt_expires_min * 60,
        username=user.username, organization_id=user.org_id,
        roles=[role.value for role in roles],
    ))


@router.get("/me", response_model=Envelope[dict[str, object]], summary="Current authenticated identity")
def me(principal: Principal = Depends(get_current_principal)) -> Envelope[dict[str, object]]:
    return Envelope(data={
        "user_id": str(principal.user.user_id), "username": principal.user.username,
        "organization_id": principal.user.org_id,
        "roles": sorted(role.value for role in principal.roles),
    })
