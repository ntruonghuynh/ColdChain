from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from coldchain_llm.schemas import ExplanationResponse


class CreateExplanationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_ref: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    question: str = Field(min_length=1, max_length=1000)
    evidence_cutoff_at: datetime | None = None


class ProcedureSearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)
    procedure_version: str = Field(min_length=1, max_length=40)
    product_category: str = Field(min_length=1, max_length=80)
    at: datetime
    incident_category: str | None = Field(default=None, max_length=80)
    top_k: int = Field(default=5, ge=1, le=10)


class ExplanationListItem(BaseModel):
    explanation_id: UUID
    explanation_status: str
    source_mode: str
    provider: str
    model: str | None
    prompt_version: str
    explained_at: datetime
    evidence_cutoff_at: datetime
    citation_verification: str


class ExplanationEnvelopeData(BaseModel):
    explanation: ExplanationResponse

