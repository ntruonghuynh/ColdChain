"""Reference data: organizations, users, roles, products and policies."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, str_enum, uuid_pk
from app.db.models.enums import OrgType, PolicyStatus, Role
from app.db.types import UTCDateTime


class Organization(Base):
    __tablename__ = "organization"

    org_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    org_type: Mapped[OrgType] = mapped_column(str_enum(OrgType, "org_type"), nullable=False)
    # Legacy nullable display field; M5 role-specific accounts live in organization_chain_role.
    chain_address: Mapped[str | None] = mapped_column(String(42), unique=True)
    created_at: Mapped[datetime] = created_at_col()


class AppUser(Base):
    __tablename__ = "app_user"

    user_id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    org_id: Mapped[str] = mapped_column(ForeignKey("organization.org_id"), nullable=False)
    is_demo_user: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Authentication is not implemented in Milestone 1; no credentials are stored yet.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = created_at_col()


class UserRole(Base):
    """Role grant. Referenced by dispositions so the decider's role is provable.

    Grants are revoked by setting ``revoked_at``, never deleted, because past
    decisions keep a foreign key to the grant they were made under.
    """

    __tablename__ = "user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.user_id"), primary_key=True)
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"), primary_key=True)
    granted_at: Mapped[datetime] = created_at_col()
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (
        CheckConstraint("revoked_at IS NULL OR revoked_at >= granted_at", name="revoked_after_granted"),
    )


class OrganizationChainRole(Base):
    """Organization-to-role account mapping used by the contract and relay."""

    __tablename__ = "organization_chain_role"

    org_id: Mapped[str] = mapped_column(ForeignKey("organization.org_id"), primary_key=True)
    role: Mapped[Role] = mapped_column(str_enum(Role, "chain_role"), primary_key=True)
    chain_address: Mapped[str] = mapped_column(String(42), nullable=False, unique=True)

    __table_args__ = (
        CheckConstraint("chain_address ~ '^0x[0-9a-fA-F]{40}$'", name="chain_address_hex"),
    )


class Product(Base):
    __tablename__ = "product"

    product_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()


class Policy(Base):
    """Versioned temperature policy (DATA-03: product_id, limits, duration_rule, procedure_version).

    Values are configuration data loaded from ``app/seed/data/policies/*.json``.
    Comparison semantics are encoded in the column names:

    * excursion above ``max_temp_c`` (strictly greater) lasting at least
      ``high_excursion_min_duration_min`` minutes;
    * excursion below ``min_temp_c`` (strictly less) lasting at least
      ``low_excursion_min_duration_min`` minutes;
    * a reading gap longer than ``gap_unknown_after_min`` is UNKNOWN;
    * a reading gap of at least ``gap_review_at_min`` requires quality review.

    Detection logic that uses these values is implemented in Milestone 3.
    """

    __tablename__ = "policy"

    policy_id: Mapped[uuid.UUID] = uuid_pk()
    policy_code: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("product.product_id"), nullable=False)
    status: Mapped[PolicyStatus] = mapped_column(str_enum(PolicyStatus, "policy_status"), nullable=False)

    min_temp_c: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    max_temp_c: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    high_excursion_min_duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    low_excursion_min_duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    gap_unknown_after_min: Mapped[int] = mapped_column(Integer, nullable=False)
    gap_review_at_min: Mapped[int] = mapped_column(Integer, nullable=False)
    release_authority_role: Mapped[Role] = mapped_column(
        str_enum(Role, "release_authority_role"), nullable=False
    )

    procedure_version: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    is_teaching_policy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False)
    approval_reference: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("policy_code", "policy_version"),
        UniqueConstraint("policy_id", "product_id"),
        CheckConstraint("min_temp_c < max_temp_c", name="min_below_max"),
        CheckConstraint("high_excursion_min_duration_min > 0", name="high_duration_positive"),
        CheckConstraint("low_excursion_min_duration_min > 0", name="low_duration_positive"),
        CheckConstraint("gap_unknown_after_min > 0", name="gap_unknown_positive"),
        CheckConstraint("gap_review_at_min >= gap_unknown_after_min", name="gap_review_not_below_unknown"),
        # The brief allows only the quality role to authorize release (BC-05).
        CheckConstraint("release_authority_role = 'QUALITY'", name="release_authority_is_quality"),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="content_sha256_hex"),
        # At most one ACTIVE policy per product.
        Index(
            "uq_policy_one_active_per_product",
            "product_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )
