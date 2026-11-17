"""Strict argument models for any future read-only evidence tool invocation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IncidentReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: str = Field(min_length=1, max_length=80)
    shipment_id: str = Field(min_length=1, max_length=60)
    interval_start_at: datetime
    interval_end_at: datetime
    as_of: datetime

    @model_validator(mode="after")
    def validate_window(self) -> "IncidentReadArgs":
        values = (self.interval_start_at, self.interval_end_at, self.as_of)
        if any(value.tzinfo is None for value in values):
            raise ValueError("all timestamps must include a timezone")
        if self.interval_end_at < self.interval_start_at:
            raise ValueError("interval end precedes interval start")
        if (self.interval_end_at - self.interval_start_at).total_seconds() > 48 * 3600:
            raise ValueError("read-only evidence window exceeds 48 hours")
        if self.interval_end_at > self.as_of:
            raise ValueError("evidence interval cannot extend past as_of")
        return self


class ProcedureSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)
    procedure_version: str = Field(min_length=1, max_length=40)
    product_category: str = Field(min_length=1, max_length=80)
    at: datetime
    top_k: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def timestamp_has_zone(self) -> "ProcedureSearchArgs":
        if self.at.tzinfo is None:
            raise ValueError("at must include a timezone")
        return self

