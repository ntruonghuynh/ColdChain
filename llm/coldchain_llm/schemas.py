"""Validated, advisory-only M6 explanation contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


OUTPUT_SCHEMA_VERSION = "explanation-content/v2"


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1, max_length=200)
    claim: str = Field(min_length=1, max_length=1000)
    quote: str | None = Field(default=None, max_length=500)


class TemporalClaim(BaseModel):
    """A checkable temporal assertion, tied to an exact supplied evidence timestamp."""

    model_config = ConfigDict(extra="forbid")
    statement_vi: str = Field(min_length=1, max_length=500)
    evidence_ref: str = Field(min_length=1, max_length=200)
    timestamp_field: str = Field(min_length=1, max_length=80)
    timestamp: str = Field(min_length=1, max_length=80)
    relation_to_cutoff: Literal["before", "at", "after", "unknown"]


class ExplanationContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary_vi: str = Field(min_length=1, max_length=2000)
    observations_vi: list[str] = Field(default_factory=list, max_length=30)
    policy_findings_vi: list[str] = Field(default_factory=list, max_length=20)
    ml_advisories_vi: list[str] = Field(default_factory=list, max_length=20)
    potential_factors_vi: list[str] = Field(default_factory=list, max_length=20)
    recommended_steps_vi: list[str] = Field(default_factory=list, max_length=20)
    evidence_needed_vi: list[str] = Field(default_factory=list, max_length=20)
    unknowns_vi: list[str] = Field(default_factory=list, max_length=20)
    citations: list[Citation] = Field(default_factory=list, max_length=50)
    temporal_claims: list[TemporalClaim] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def reject_unsafe_authorization_claims(self) -> "ExplanationContent":
        text = " ".join([
            self.summary_vi, *self.observations_vi, *self.policy_findings_vi, *self.ml_advisories_vi,
            *self.potential_factors_vi, *self.recommended_steps_vi, *self.evidence_needed_vi, *self.unknowns_vi,
            *(claim.statement_vi for claim in self.temporal_claims),
        ]).casefold()
        unsafe = (
            "được phép xuất kho", "cho phép release", "đã an toàn", "chắc chắn an toàn", "duyệt xuất kho",
            "safe to release", "shipment is safe", "release is approved", "approved for release",
        )
        if any(term in text for term in unsafe):
            raise ValueError("Explanation contains a disallowed safety or authorization claim")
        return self


class ExplanationValidationDiagnostics(BaseModel):
    """Safe, structured pipeline status; never contains prompts or generated raw text."""

    model_config = ConfigDict(extra="forbid")
    provider_call_status: Literal["not_run", "succeeded", "failed"] = "not_run"
    application_validation_status: Literal["not_run", "passed", "rejected"] = "not_run"
    provider_finish_reason: str | None = Field(default=None, max_length=40)
    output_parse_status: Literal["not_run", "passed", "failed"] = "not_run"
    output_parse_failure_category: str | None = Field(default=None, max_length=60)
    output_schema_status: Literal["not_run", "passed", "failed"] = "not_run"
    output_schema_failure_category: str | None = Field(default=None, max_length=60)
    citation_validation_status: Literal["not_run", "passed", "failed"] = "not_run"
    citation_failure_category: Literal[
        "policy_version_mismatch", "sensor_interval_mismatch", "citations_missing",
        "source_not_supplied", "quote_not_in_source",
    ] | None = None
    evidence_validation_status: Literal["not_run", "passed", "failed"] = "not_run"
    evidence_failure_category: str | None = Field(default=None, max_length=60)
    temporal_validation_status: Literal["not_run", "passed", "failed"] = "not_run"
    temporal_failure_category: str | None = Field(default=None, max_length=60)
    prompt_token_count: int | None = Field(default=None, ge=0)
    completion_token_count: int | None = Field(default=None, ge=0)


def strict_explanation_json_schema() -> dict[str, Any]:
    """Return Pydantic's content schema normalized for OpenAI strict JSON Schema mode.

    Strict mode requires every object property to be required; optional values are
    represented as nullable unions. Pydantic remains the authoritative validator.
    """
    schema = ExplanationContent.model_json_schema()
    # The API's strict subset does not enforce Pydantic's size constraints.
    # Keep those limits in the local validator and send only schema keywords
    # supported by Structured Outputs.
    api_unsupported_keywords = {"minLength", "maxLength", "minItems", "maxItems"}

    def normalize(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("title", None)
            node.pop("default", None)
            for keyword in api_unsupported_keywords:
                node.pop(keyword, None)
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(schema)
    return schema


class ExplanationResponse(ExplanationContent):
    explanation_id: UUID
    shipment_id: str
    incident_id: UUID
    incident_ref: str
    explained_at: datetime
    evidence_cutoff_at: datetime
    explanation_status: Literal["draft", "insufficient_evidence", "not_configured", "provider_error", "fallback"]
    source_mode: Literal["llm", "deterministic_fallback", "none"]
    provider: str
    model: str | None = None
    provider_api_version: str | None = None
    prompt_version: str
    prompt_sha256: str
    policy_version: str
    procedure_version: str
    sensor_interval_start_at: datetime
    sensor_interval_end_at: datetime
    evidence_references: list[str]
    document_versions: list[str]
    citation_verification: Literal["passed", "failed", "not_applicable"]
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    validation_diagnostics: ExplanationValidationDiagnostics = Field(
        default_factory=ExplanationValidationDiagnostics
    )
    human_authorization_disclaimer_vi: str = (
        "Đây là nội dung tham khảo. Chỉ Quality Officer được ủy quyền mới có thể quyết định RELEASE hoặc QUARANTINE; "
        "giải thích, dữ liệu thiếu hoặc điểm ML không thay thế quyết định đó."
    )

    @model_validator(mode="after")
    def reject_advisory_authorization_language(self) -> "ExplanationResponse":
        if self.source_mode == "deterministic_fallback" and self.explanation_status not in {
            "fallback", "insufficient_evidence",
        }:
            raise ValueError("Fallback content must be labeled as fallback or insufficient evidence")
        return self

