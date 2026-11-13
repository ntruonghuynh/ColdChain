"""Read-only reference data: policies and organizations."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    DurationRule,
    Envelope,
    Limits,
    ListEnvelope,
    ListMeta,
    MissingDataRule,
    OrganizationOut,
    OrganizationUserOut,
    PolicyOut,
)
from app.core.errors import NotFoundError
from app.db.models import AppUser, Organization, Policy, Product, UserRole
from app.db.models.enums import PolicyStatus
from app.db.session import get_db

router = APIRouter(tags=["reference data"])


def _policy_out(policy: Policy, product: Product) -> PolicyOut:
    return PolicyOut(
        policy_id=policy.policy_id,
        policy_code=policy.policy_code,
        policy_version=policy.policy_version,
        product_id=policy.product_id,
        product_name=product.name,
        status=policy.status.value,
        limits=Limits(min_temp_c=policy.min_temp_c, max_temp_c=policy.max_temp_c),
        duration_rule=DurationRule(
            high_excursion_min_duration_min=policy.high_excursion_min_duration_min,
            low_excursion_min_duration_min=policy.low_excursion_min_duration_min,
        ),
        missing_data_rule=MissingDataRule(
            gap_unknown_after_min=policy.gap_unknown_after_min,
            gap_review_at_min=policy.gap_review_at_min,
        ),
        release_authority_role=policy.release_authority_role.value,
        procedure_version=policy.procedure_version,
        effective_from=policy.effective_from,
        is_teaching_policy=policy.is_teaching_policy,
        disclaimer=policy.disclaimer,
        approval_reference=policy.approval_reference,
        source_file=policy.source_file,
        content_sha256=policy.content_sha256,
    )


@router.get("/policies", response_model=ListEnvelope[PolicyOut], summary="List temperature policies")
def list_policies(
    status: PolicyStatus | None = Query(default=None, description="Filter by status"),
    db: Session = Depends(get_db),
) -> ListEnvelope[PolicyOut]:
    stmt = select(Policy, Product).join(Product, Product.product_id == Policy.product_id)
    if status is not None:
        stmt = stmt.where(Policy.status == status)
    rows = db.execute(stmt.order_by(Policy.policy_code, Policy.policy_version)).all()
    items = [_policy_out(policy, product) for policy, product in rows]
    return ListEnvelope(data=items, meta=ListMeta(total=len(items), limit=len(items), offset=0))


@router.get("/policies/{policy_id}", response_model=Envelope[PolicyOut], summary="Get one policy")
def get_policy(policy_id: uuid.UUID, db: Session = Depends(get_db)) -> Envelope[PolicyOut]:
    row = db.execute(
        select(Policy, Product).join(Product, Product.product_id == Policy.product_id)
        .where(Policy.policy_id == policy_id)
    ).first()
    if row is None:
        raise NotFoundError(f"Policy {policy_id} not found.")
    return Envelope(data=_policy_out(*row))


@router.get("/organizations", response_model=ListEnvelope[OrganizationOut],
            summary="List organizations with demo users and roles")
def list_organizations(db: Session = Depends(get_db)) -> ListEnvelope[OrganizationOut]:
    orgs = db.scalars(select(Organization).order_by(Organization.org_id)).all()
    users = db.scalars(select(AppUser).order_by(AppUser.username)).all()
    grants = db.scalars(select(UserRole).where(UserRole.revoked_at.is_(None))).all()
    roles_by_user: dict[uuid.UUID, list[str]] = {}
    for grant in grants:
        roles_by_user.setdefault(grant.user_id, []).append(grant.role.value)

    items = [
        OrganizationOut(
            org_id=org.org_id,
            name=org.name,
            org_type=org.org_type.value,
            users=[
                OrganizationUserOut(
                    username=u.username,
                    display_name=u.display_name,
                    roles=sorted(roles_by_user.get(u.user_id, [])),
                    is_demo_user=u.is_demo_user,
                    has_credentials=u.password_hash is not None,
                )
                for u in users
                if u.org_id == org.org_id
            ],
        )
        for org in orgs
    ]
    return ListEnvelope(data=items, meta=ListMeta(total=len(items), limit=len(items), offset=0))
