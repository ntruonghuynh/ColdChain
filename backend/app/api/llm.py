"""Authenticated, read-only incident explanations and approved teaching-procedure retrieval."""

from __future__ import annotations

import uuid
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.llm_schemas import CreateExplanationIn, ExplanationListItem, ProcedureSearchIn
from app.api.schemas import Envelope
from app.core.security import Principal, require_roles
from app.db.models import Incident, LLMExplanation
from app.db.models.enums import Role
from app.db.session import get_db
from app.integrations import llm_adapter
from app.services.llm_explanations import authorize_shipment, create_explanation
from coldchain_llm.retrieval import INDEX_VERSION
from coldchain_llm.schemas import ExplanationResponse

router = APIRouter(prefix="/llm", tags=["M6 advisory incident explanations"])
READ_ROLES = (Role.ADMIN, Role.SHIPPER, Role.CARRIER, Role.QUALITY, Role.WAREHOUSE)


@router.get("/readiness", response_model=Envelope[dict[str, object]], summary="RAG corpus and optional provider readiness")
def readiness() -> Envelope[dict[str, object]]:
    return Envelope(data=llm_adapter.provider_readiness())


@router.post("/procedures/search", response_model=Envelope[dict[str, object]],
             summary="Search only applicable, teaching-approved SOP sections")
def search_procedures(body: ProcedureSearchIn, _principal: Principal = Depends(require_roles(*READ_ROLES))) -> Envelope[dict[str, object]]:
    if body.at.tzinfo is None:
        raise HTTPException(status_code=422, detail="at must include a timezone")
    chunks, retriever = llm_adapter.load_retriever()
    result = retriever.search(
        body.query, procedure_version=body.procedure_version,
        product_category=body.product_category, at=body.at.astimezone(UTC).date(),
        incident_category=body.incident_category, top_k=body.top_k,
    )
    return Envelope(data={
        "status": result.status,
        "index_version": INDEX_VERSION,
        "indexed_chunk_count": len(chunks),
        "results": [
            {"source_id": chunk.source_id, "doc_id": chunk.doc_id, "title": chunk.title,
             "version": chunk.version, "section_id": chunk.section_id,
             "section_title": chunk.section_title, "score": score,
             "content_sha256": chunk.content_sha256, "text": chunk.text,
             "origin": chunk.origin, "approval_scope": chunk.status}
            for chunk, score in zip(result.chunks, result.scores, strict=True)
        ],
    })


@router.post("/incidents/{incident_id}/explanations", response_model=Envelope[ExplanationResponse],
             summary="Create an advisory, evidence-grounded incident explanation")
def explain_incident(incident_id: uuid.UUID, body: CreateExplanationIn,
                     db: Session = Depends(get_db),
                     principal: Principal = Depends(require_roles(*READ_ROLES))) -> Envelope[ExplanationResponse]:
    try:
        response = create_explanation(
            db, incident_id=incident_id, request_ref=body.request_ref,
            question=body.question, evidence_cutoff_at=body.evidence_cutoff_at,
            principal=principal,
        )
        db.commit()
        return Envelope(data=response)
    except Exception:
        db.rollback()
        raise


@router.get("/incidents/{incident_id}/explanations", response_model=Envelope[list[ExplanationListItem]],
            summary="Read append-only explanation history for an incident")
def list_explanations(incident_id: uuid.UUID, limit: int = Query(default=25, ge=1, le=100),
                      db: Session = Depends(get_db),
                      principal: Principal = Depends(require_roles(*READ_ROLES))) -> Envelope[list[ExplanationListItem]]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    authorize_shipment(db, incident.shipment_id, principal)
    rows = db.scalars(select(LLMExplanation).where(
        LLMExplanation.incident_id == incident_id
    ).order_by(LLMExplanation.created_at.desc()).limit(limit)).all()
    return Envelope(data=[ExplanationListItem(
        explanation_id=row.explanation_id, explanation_status=row.explanation_status.lower(),
        source_mode=row.source_mode.lower(), provider=row.provider, model=row.model,
        prompt_version=row.prompt_version, explained_at=row.explained_at,
        evidence_cutoff_at=row.evidence_cutoff_at,
        citation_verification=row.citation_verification.lower(),
    ) for row in rows])


@router.get("/explanations/{explanation_id}", response_model=Envelope[ExplanationResponse],
            summary="Read one stored explanation with evidence and provenance metadata")
def get_explanation(explanation_id: uuid.UUID, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_roles(*READ_ROLES))) -> Envelope[ExplanationResponse]:
    row = db.get(LLMExplanation, explanation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Explanation not found")
    authorize_shipment(db, row.shipment_id, principal)
    return Envelope(data=ExplanationResponse.model_validate(row.output))

