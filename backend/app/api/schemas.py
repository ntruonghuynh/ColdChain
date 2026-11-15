"""Response conventions.

Success: ``{"data": <payload>, "meta": <object or null>}``
List:    ``{"data": [...], "meta": {"total": n, "limit": n, "offset": n}}``
Error:   ``{"error": {"code", "message", "details", "request_id"}}`` (see app.core.errors)
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ListMeta(BaseModel):
    total: int
    limit: int
    offset: int


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: dict[str, object] | None = None


class ListEnvelope(BaseModel, Generic[T]):
    data: list[T]
    meta: ListMeta


class ErrorBody(BaseModel):
    code: str
    message: str
    details: object | None = None
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


# ---------- health ----------

class DatabaseHealth(BaseModel):
    status: Literal["ok", "unavailable", "migration_pending"]
    latency_ms: float | None = None
    migration_revision: str | None = None
    expected_revision: str | None = None
    detail: str | None = None


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    api: Literal["ok"] = "ok"
    database: DatabaseHealth
    checked_at: datetime


# ---------- system ----------

class FeatureStatus(BaseModel):
    key: str
    name: str
    status: Literal["available", "not_implemented"]
    milestone: str
    note: str | None = None


class SystemInfo(BaseModel):
    app_name: str
    version: str
    milestone: str
    environment: str
    server_time: datetime
    features: list[FeatureStatus]


# ---------- reference data ----------

class Limits(BaseModel):
    min_temp_c: Decimal
    max_temp_c: Decimal


class DurationRule(BaseModel):
    high_excursion_min_duration_min: int = Field(description="Minutes strictly above max_temp_c")
    low_excursion_min_duration_min: int = Field(description="Minutes strictly below min_temp_c")


class MissingDataRule(BaseModel):
    gap_unknown_after_min: int = Field(description="Gap longer than this is UNKNOWN")
    gap_review_at_min: int = Field(description="Gap of at least this requires quality review")


class PolicyOut(BaseModel):
    policy_id: uuid.UUID
    policy_code: str
    policy_version: str
    product_id: str
    product_name: str
    status: str
    limits: Limits
    duration_rule: DurationRule
    missing_data_rule: MissingDataRule
    release_authority_role: str
    procedure_version: str
    effective_from: datetime
    is_teaching_policy: bool
    disclaimer: str
    approval_reference: str
    source_file: str
    content_sha256: str


class OrganizationUserOut(BaseModel):
    username: str
    display_name: str
    roles: list[str]
    is_demo_user: bool
    has_credentials: bool


class OrganizationOut(BaseModel):
    org_id: str
    name: str
    org_type: str
    users: list[OrganizationUserOut]


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shipment_id: str
    product_id: str
    policy_id: uuid.UUID
    shipper_org_id: str
    carrier_org_id: str
    receiver_org_id: str
    origin: str | None
    destination: str | None
    status: str
    data_origin: str
    source_dataset_id: str | None = None
    created_at: datetime
