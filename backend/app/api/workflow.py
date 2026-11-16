"""M5 authenticated workflow command APIs. All writes enter the transactional outbox."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.schemas import Envelope
from app.core.security import Principal, require_roles
from app.db.models.enums import CustodyStage, Decision, Role
from app.db.session import get_db
from app.services.workflow import (
    accept_custody, record_disposition, register_shipment, release_warehouse, review_reassessment,
)

router = APIRouter(prefix="/workflow", tags=["M5 workflow"])


class RefIn(BaseModel):
    business_ref: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


class CustodyIn(RefIn):
    stage: CustodyStage


class DispositionIn(RefIn):
    decision: Decision
    rationale: str = Field(min_length=1, max_length=4000)
    incident_refs: list[str] = Field(default_factory=list, max_length=200)


class ReassessmentReviewIn(BaseModel):
    review_note: str = Field(min_length=1, max_length=4000)


def _run(db: Session, call):
    try:
        result = call()
        db.commit()
        return Envelope(data=result)
    except Exception:
        db.rollback()
        raise


@router.post("/shipments/{shipment_id}/register", status_code=202,
            summary="Register shipment on the local chain")
def register(shipment_id: str, body: RefIn, db: Session = Depends(get_db),
             principal: Principal = Depends(require_roles(Role.SHIPPER))) -> Envelope[dict[str, object]]:
    return _run(db, lambda: register_shipment(db, shipment_id=shipment_id,
                                              business_ref=body.business_ref, principal=principal))


@router.post("/shipments/{shipment_id}/custody", status_code=202,
            summary="Record pickup or delivery custody acceptance")
def custody(shipment_id: str, body: CustodyIn, db: Session = Depends(get_db),
            principal: Principal = Depends(require_roles(Role.CARRIER, Role.WAREHOUSE))) -> Envelope[dict[str, object]]:
    return _run(db, lambda: accept_custody(db, shipment_id=shipment_id,
                                           business_ref=body.business_ref, stage=body.stage,
                                           principal=principal))


@router.post("/shipments/{shipment_id}/disposition", status_code=202,
            summary="Record an authorized quality disposition")
def disposition(shipment_id: str, body: DispositionIn, db: Session = Depends(get_db),
                principal: Principal = Depends(require_roles(Role.QUALITY))) -> Envelope[dict[str, object]]:
    return _run(db, lambda: record_disposition(
        db, shipment_id=shipment_id, business_ref=body.business_ref, decision=body.decision,
        rationale=body.rationale, incident_refs=body.incident_refs, principal=principal,
    ))


@router.post("/shipments/{shipment_id}/release", status_code=202,
            summary="Request physical warehouse release after confirmed quality RELEASE")
def release(shipment_id: str, body: RefIn, db: Session = Depends(get_db),
            principal: Principal = Depends(require_roles(Role.WAREHOUSE))) -> Envelope[dict[str, object]]:
    return _run(db, lambda: release_warehouse(db, shipment_id=shipment_id,
                                               business_ref=body.business_ref, principal=principal))


@router.post("/shipments/{shipment_id}/reassessments/{reassessment_id}/review",
            summary="Record Quality review of late or revised evidence")
def reassessment_review(shipment_id: str, reassessment_id: str, body: ReassessmentReviewIn,
                        db: Session = Depends(get_db),
                        principal: Principal = Depends(require_roles(Role.QUALITY))) -> Envelope[dict[str, object]]:
    import uuid
    try:
        parsed_id = uuid.UUID(reassessment_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Invalid reassessment identifier") from exc
    return _run(db, lambda: review_reassessment(db, shipment_id=shipment_id,
                                                reassessment_id=parsed_id,
                                                review_note=body.review_note, principal=principal))
