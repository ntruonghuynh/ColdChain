"""Validated, explicitly advisory M4 prediction contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: str = Field(min_length=1, max_length=60)
    sensor_id: str | None = Field(default=None, min_length=1, max_length=60)
    as_of: datetime


class PredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["SCORED", "INSUFFICIENT_EVIDENCE"]
    prediction_id: UUID
    as_of: datetime
    model_version: str
    feature_schema_version: str
    advisory_only: Literal[True]
    temperature_safety_established: Literal[False]
    risk_probability: float | None
    alert: bool
    threshold: float | None = None
    interpretation: str | None = None
    message: str | None = None
    evidence: dict[str, float | int] | None = None


class ModelReadiness(BaseModel):
    status: Literal["ready", "unavailable"]
    model_version: str
    detail: str | None = None
