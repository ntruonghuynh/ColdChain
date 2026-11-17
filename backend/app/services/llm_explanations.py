"""Orchestrate retrieval, causal evidence, bounded provider inference and append-only storage."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal
from app.db.models import Incident, LLMExplanation, Shipment
from app.services.evidence_package import build_evidence_package
from app.integrations import llm_adapter
from coldchain_llm.prompts import PROMPT_VERSION, build_user_prompt, load_system_prompt
from coldchain_llm.retrieval import RetrievalResult
from coldchain_llm.schemas import (
    Citation, ExplanationContent, ExplanationResponse, ExplanationValidationDiagnostics,
)
from coldchain_llm.validate import validate_generated_content, verify_citations
from coldchain_llm.temporal import date_relation
from coldchain_llm.providers import ProviderError


def authorize_shipment(db: Session, shipment_id: str, principal: Principal) -> Shipment:
    shipment = db.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    role_names = {role.value for role in principal.roles}
    allowed = (
        ("SHIPPER" in role_names and principal.user.org_id == shipment.shipper_org_id)
        or ("CARRIER" in role_names and principal.user.org_id == shipment.carrier_org_id)
        or (bool(role_names & {"QUALITY", "WAREHOUSE"}) and principal.user.org_id == shipment.receiver_org_id)
        or "ADMIN" in role_names
    )
    if not allowed:
        # Avoid revealing whether a shipment exists to an unrelated organization.
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment


def _retrieval(query: str, package: dict, cutoff: datetime) -> RetrievalResult:
    _, retriever = llm_adapter.load_retriever()
    return retriever.search(
        query, procedure_version=package["procedure_version"],
        product_category=package["product_category"], at=cutoff.date(),
        incident_category=package["incident"]["category"], top_k=5,
    )


def _fallback_content(package: dict, retrieval: RetrievalResult, question: str) -> ExplanationContent:
    evidence = package["evidence"]
    summary = evidence["reading_summary"]
    incident = evidence["incident"]
    readings = evidence["readings"]
    citation_ids = [
        f"SYS:incident/{incident['incident_id']}:revision/{incident['revision'] or 0}",
        f"SYS:policy/{evidence['policy']['policy_code']}@{evidence['policy']['policy_version']}",
    ]
    citations = [Citation(source_id=citation_ids[0], claim="Thông tin incident và revision sẵn có tại cutoff.")]
    observations = [
        f"Incident {incident['category']} mở lúc {incident['opened_at']}; trạng thái tại cutoff: {incident['status_at_cutoff']}.",
        f"Có {summary['count']} số đo quan sát được trong sensor interval; khoảng thời gian không có số đo vẫn là UNKNOWN.",
    ]
    if readings:
        observations.append(
            f"Khoảng số đo khả dụng: {summary['first_event_at']} đến {summary['last_event_at']}; "
            f"min/max quan sát {summary['min_temperature_c']}–{summary['max_temperature_c']} °C; "
            f"{summary['delayed_count']} bản ghi có received_at muộn hơn event_at."
        )
    policy = evidence["policy"]
    policy_findings = [
        f"Policy {policy['policy_code']} phiên bản {policy['policy_version']} đang áp dụng; "
        f"giới hạn {policy['min_temp_c']}–{policy['max_temp_c']} °C. Đây là policy mô phỏng, không phải chuẩn an toàn chính thức."
    ]
    citations.append(Citation(source_id=citation_ids[1], claim="Phiên bản policy áp dụng.",
                              quote=f'"policy_version": "{policy["policy_version"]}"'))
    steps: list[str] = []
    if retrieval.chunks:
        for chunk in retrieval.chunks[:2]:
            steps.append(f"Tham khảo section {chunk.section_id} ({chunk.title}) trong quy trình mô phỏng; chuyển Quality Officer xem xét.")
            citations.append(Citation(source_id=chunk.source_id, claim=f"Hướng dẫn tham khảo: {chunk.section_title}.",
                                      quote=chunk.text[:min(180, len(chunk.text))]))
    if not package["sufficient"]:
        steps = []
    unknowns = list(package["insufficient_reasons"])
    if evidence["gaps"]:
        unknowns.append("Khoảng thiếu dữ liệu không chứng minh nhiệt độ an toàn; không nội suy qua khoảng trống.")
    ml_notes = [
        f"Dự đoán {item['prediction_id']} từ {item['model_version']} là advisory-only, "
        f"trạng thái {item['status']}, alert={item['alert']}; không phải disposition."
        for item in evidence["m4_predictions_advisory_only"]
    ]
    return ExplanationContent(
        summary_vi=(f"Giải thích xác định cho {incident['category']} trong shipment {evidence['shipment_id']}. "
                    "Đây không phải nội dung do LLM tạo."),
        observations_vi=observations,
        policy_findings_vi=policy_findings,
        ml_advisories_vi=ml_notes,
        potential_factors_vi=[],
        recommended_steps_vi=steps,
        evidence_needed_vi=unknowns or ["Quality Officer cần xem xét evidence và workflow hiện hành trước mọi quyết định."],
        unknowns_vi=unknowns,
        citations=citations,
    )


def _response(
    *, explanation_id: uuid.UUID, incident_id: uuid.UUID, package: dict,
    content: ExplanationContent, cutoff: datetime, status: str, mode: str,
    provider: str, model: str | None, api_version: str | None, prompt_hash: str,
    citation_status: str, input_tokens: int | None = None, output_tokens: int | None = None,
    latency_ms: int | None = None, cost_usd: float | None = None,
    validation_diagnostics: ExplanationValidationDiagnostics | None = None,
) -> ExplanationResponse:
    return ExplanationResponse(
        **content.model_dump(), explanation_id=explanation_id,
        shipment_id=package["evidence"]["shipment_id"], incident_id=incident_id,
        incident_ref=package["incident"]["incident_ref"], explained_at=datetime.now(UTC),
        evidence_cutoff_at=cutoff, explanation_status=status, source_mode=mode,
        provider=provider, model=model, provider_api_version=api_version,
        prompt_version=PROMPT_VERSION, prompt_sha256=prompt_hash,
        policy_version=package["evidence"]["policy"]["policy_version"],
        procedure_version=package["procedure_version"],
        sensor_interval_start_at=package["interval_start_at"],
        sensor_interval_end_at=package["interval_end_at"],
        evidence_references=package["evidence_references"],
        document_versions=sorted({chunk.version for chunk in package["retrieved_chunks"]}),
        citation_verification=citation_status,
        input_tokens=input_tokens, output_tokens=output_tokens,
        latency_ms=latency_ms, cost_usd=cost_usd,
        validation_diagnostics=validation_diagnostics or ExplanationValidationDiagnostics(),
    )


def create_explanation(
    db: Session, *, incident_id: uuid.UUID, request_ref: str, question: str,
    evidence_cutoff_at: datetime | None, principal: Principal,
    settings: Settings | None = None,
) -> ExplanationResponse:
    settings = settings or get_settings()
    cutoff = evidence_cutoff_at or datetime.now(UTC)
    if cutoff.tzinfo is None:
        raise HTTPException(status_code=422, detail="evidence_cutoff_at must include a timezone")
    cutoff = cutoff.astimezone(UTC)
    if cutoff > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="evidence_cutoff_at cannot be in the future")
    # A retry with no caller-specified cutoff must map to the same idempotency
    # request even though server time advances between HTTP attempts.
    request_cutoff_key = cutoff.isoformat() if evidence_cutoff_at is not None else "server_time"
    incident_hash = hashlib.sha256(
        f"{incident_id}|{request_cutoff_key}|{question}".encode()
    ).hexdigest()
    lock_material = f"{principal.user.user_id}:{request_ref}".encode("utf-8")
    advisory_lock_id = int.from_bytes(hashlib.sha256(lock_material).digest()[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": advisory_lock_id})
    existing = db.scalar(select(LLMExplanation).where(
        LLMExplanation.requested_by_user_id == principal.user.user_id,
        LLMExplanation.request_ref == request_ref,
    ))
    if existing:
        if existing.request_sha256 != incident_hash or existing.incident_id != incident_id:
            raise HTTPException(status_code=409, detail="request_ref was already used for a different request")
        return ExplanationResponse.model_validate(existing.output)

    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    authorize_shipment(db, incident.shipment_id, principal)
    package = build_evidence_package(db, incident_id, cutoff)
    retrieval = _retrieval(question + " " + incident.category.value, package, cutoff)
    package["retrieved_chunks"] = list(retrieval.chunks)
    for chunk in retrieval.chunks:
        for field, value in (("effective_from", chunk.effective_from), ("effective_to", chunk.effective_to)):
            if value:
                package["temporal_facts"].append({
                    "evidence_ref": chunk.source_id,
                    "timestamp_field": field,
                    "timestamp": value,
                    "relation_to_cutoff": date_relation(value, cutoff),
                    "relation_to_incident_opened": date_relation(value, datetime.fromisoformat(
                        package["incident"]["opened_at"].replace("Z", "+00:00")
                    )),
                })
    system_prompt, prompt_hash = load_system_prompt()
    sources = dict(package["sources"])
    for chunk in retrieval.chunks:
        sources[chunk.source_id] = chunk.text
    explanation_id = uuid.uuid4()
    provider_name = settings.llm_provider.casefold()
    status, mode, citation_status = "NOT_CONFIGURED", "NONE", "NOT_APPLICABLE"
    model = settings.llm_model or None
    api_version = None
    input_tokens = output_tokens = latency_ms = None
    cost_usd = None
    validation_diagnostics = ExplanationValidationDiagnostics(
        evidence_validation_status="passed" if package["sufficient"] else "failed",
        evidence_failure_category=None if package["sufficient"] else "insufficient_evidence",
    )

    if not package["sufficient"] or not retrieval.chunks:
        status, citation_status = "INSUFFICIENT_EVIDENCE", "NOT_APPLICABLE"
        if settings.llm_fallback_enabled:
            content = _fallback_content(package, retrieval, question)
            mode = "DETERMINISTIC_FALLBACK"
            valid, citation_failure = verify_citations(
                content, sources, required_policy_version=package["evidence"]["policy"]["policy_version"],
                required_sensor_interval=(package["interval_start_at"].isoformat(), package["interval_end_at"].isoformat()),
                response_policy_version=package["evidence"]["policy"]["policy_version"],
                response_sensor_interval=(package["interval_start_at"].isoformat(), package["interval_end_at"].isoformat()),
            )
            citation_status = "PASSED" if valid else "FAILED"
            validation_diagnostics = validation_diagnostics.model_copy(update={
                "application_validation_status": "passed" if valid else "rejected",
                "citation_validation_status": "passed" if valid else "failed",
                "citation_failure_category": citation_failure,
            })
        else:
            mode = "NONE"
            content = ExplanationContent(
                summary_vi="Chưa đủ bằng chứng có thể dùng tại thời điểm yêu cầu; không tạo bản nháp.",
                evidence_needed_vi=list(package["insufficient_reasons"]),
                unknowns_vi=list(package["insufficient_reasons"]),
            )
    else:
        try:
            provider = llm_adapter.get_provider(settings)
        except ValueError:
            provider = None
            status = "NOT_CONFIGURED"
        if provider is None or provider.name == "disabled" or provider_name == "disabled" or not model:
            if settings.llm_fallback_enabled:
                content = _fallback_content(package, retrieval, question)
                status, mode, citation_status = "FALLBACK", "DETERMINISTIC_FALLBACK", "PASSED"
                valid, citation_failure = verify_citations(
                    content, sources, required_policy_version=package["evidence"]["policy"]["policy_version"],
                    required_sensor_interval=(package["interval_start_at"].isoformat(), package["interval_end_at"].isoformat()),
                    response_policy_version=package["evidence"]["policy"]["policy_version"],
                    response_sensor_interval=(package["interval_start_at"].isoformat(), package["interval_end_at"].isoformat()),
                )
                validation_diagnostics = validation_diagnostics.model_copy(update={
                    "application_validation_status": "passed" if valid else "rejected",
                    "citation_validation_status": "passed" if valid else "failed",
                    "citation_failure_category": citation_failure,
                })
                if not valid:
                    status, citation_status = "INSUFFICIENT_EVIDENCE", "FAILED"
            else:
                content = ExplanationContent(summary_vi="LLM chưa được cấu hình; chưa tạo bản nháp do LLM.")
        else:
            started = time.perf_counter()
            try:
                generated = provider.generate(
                    model=model, system_prompt=system_prompt,
                    user_prompt=build_user_prompt(package["evidence"], sources, question, retrieval.chunks, package["temporal_facts"]),
                    max_output_tokens=max(64, min(settings.llm_max_output_tokens, 4096)),
                )
                latency_ms = round((time.perf_counter() - started) * 1000)
                # Preserve provider/model/usage metadata even when structural or citation
                # validation rejects the generated content. The unsafe answer remains discarded.
                provider_name, model, api_version = generated.provider, generated.model, generated.api_version
                input_tokens, output_tokens = generated.input_tokens, generated.output_tokens
                validation_diagnostics = validation_diagnostics.model_copy(update={
                    "provider_call_status": "succeeded",
                    "provider_finish_reason": generated.finish_reason,
                    "prompt_token_count": generated.input_tokens,
                    "completion_token_count": generated.output_tokens,
                })
                if (input_tokens is not None and output_tokens is not None
                        and settings.llm_price_input_per_mtok_usd is not None
                        and settings.llm_price_output_per_mtok_usd is not None):
                    cost_usd = (input_tokens * settings.llm_price_input_per_mtok_usd
                                + output_tokens * settings.llm_price_output_per_mtok_usd) / 1_000_000
                interval = (package["interval_start_at"].isoformat(), package["interval_end_at"].isoformat())
                content, validation_diagnostics = validate_generated_content(
                    generated.content, sources, finish_reason=generated.finish_reason,
                    prompt_tokens=generated.input_tokens, completion_tokens=generated.output_tokens,
                    required_policy_version=package["evidence"]["policy"]["policy_version"],
                    required_sensor_interval=interval,
                    response_policy_version=package["evidence"]["policy"]["policy_version"],
                    response_sensor_interval=interval,
                    temporal_facts=package["temporal_facts"],
                    evidence_cutoff_at=cutoff.isoformat(),
                )
                if content is not None:
                    status, mode, citation_status = "DRAFT", "LLM", "PASSED"
                else:
                    status, mode = "INSUFFICIENT_EVIDENCE", "NONE"
                    citation_status = (
                        "FAILED" if validation_diagnostics.citation_validation_status == "failed"
                        else "NOT_APPLICABLE"
                    )
                    content = ExplanationContent(
                        summary_vi="Đầu ra LLM không qua kiểm tra; nội dung chưa xác minh đã bị loại bỏ.",
                        unknowns_vi=["Không hiển thị nội dung chưa được xác minh."],
                    )
            except ProviderError as exc:
                latency_ms = round((time.perf_counter() - started) * 1000)
                validation_diagnostics = validation_diagnostics.model_copy(update={
                    "provider_call_status": "failed",
                    "application_validation_status": "not_run",
                })
                if settings.llm_fallback_enabled:
                    content = _fallback_content(package, retrieval, question)
                    status, mode = "FALLBACK", "DETERMINISTIC_FALLBACK"
                    citation_status = "PASSED"
                    valid, citation_failure = verify_citations(
                        content, sources, required_policy_version=package["evidence"]["policy"]["policy_version"],
                        required_sensor_interval=(package["interval_start_at"].isoformat(), package["interval_end_at"].isoformat()),
                        response_policy_version=package["evidence"]["policy"]["policy_version"],
                        response_sensor_interval=(package["interval_start_at"].isoformat(), package["interval_end_at"].isoformat()),
                    )
                    validation_diagnostics = validation_diagnostics.model_copy(update={
                        "application_validation_status": "passed" if valid else "rejected",
                        "citation_validation_status": "passed" if valid else "failed",
                        "citation_failure_category": citation_failure,
                    })
                    if not valid:
                        status, citation_status = "INSUFFICIENT_EVIDENCE", "FAILED"
                else:
                    status, mode, citation_status = "PROVIDER_ERROR", "NONE", "NOT_APPLICABLE"
                    content = ExplanationContent(
                        summary_vi=f"Nhà cung cấp LLM không khả dụng ({exc.code}); không tạo bản giải thích do LLM.",
                        unknowns_vi=["Yêu cầu chưa được xử lý bởi nhà cung cấp LLM."],
                    )

    response = _response(
        explanation_id=explanation_id, incident_id=incident_id, package=package,
        content=content, cutoff=cutoff, status=status.lower(),
        mode={"LLM": "llm", "DETERMINISTIC_FALLBACK": "deterministic_fallback", "NONE": "none"}[mode],
        provider=provider_name, model=model, api_version=api_version, prompt_hash=prompt_hash,
        citation_status=citation_status.lower(), input_tokens=input_tokens,
        output_tokens=output_tokens, latency_ms=latency_ms, cost_usd=cost_usd,
        validation_diagnostics=validation_diagnostics,
    )
    db.add(LLMExplanation(
        explanation_id=explanation_id, request_ref=request_ref, request_sha256=incident_hash,
        incident_id=incident_id, shipment_id=package["evidence"]["shipment_id"],
        requested_by_user_id=principal.user.user_id, explained_at=response.explained_at,
        evidence_cutoff_at=cutoff, prompt_version=PROMPT_VERSION, prompt_sha256=prompt_hash,
        provider=provider_name, model=model, provider_api_version=api_version,
        explanation_status=status, source_mode=mode,
        policy_version=response.policy_version, procedure_version=response.procedure_version,
        sensor_interval_start_at=response.sensor_interval_start_at,
        sensor_interval_end_at=response.sensor_interval_end_at,
        evidence_references=response.evidence_references, document_versions=response.document_versions,
        citation_verification=citation_status, input_tokens=input_tokens, output_tokens=output_tokens,
        latency_ms=latency_ms, cost_usd=cost_usd, output=response.model_dump(mode="json"),
        request_metadata={"question_length": len(question), "request_sha256": incident_hash,
                          "role_snapshot": sorted(role.value for role in principal.roles),
                          "validation_diagnostics": validation_diagnostics.model_dump(mode="json")},
    ))
    db.flush()
    return response

