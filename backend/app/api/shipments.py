"""Read-only shipment endpoints. Shipments are created by ingestion (Milestone 3)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import Envelope, ListEnvelope, ListMeta, ShipmentOut
from app.core.errors import NotFoundError
from app.db.models import Shipment
from app.db.models.enums import ShipmentStatus
from app.db.session import get_db

router = APIRouter(prefix="/shipments", tags=["shipments"])


@router.get("", response_model=ListEnvelope[ShipmentOut], summary="List shipments")
def list_shipments(
    status: ShipmentStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ListEnvelope[ShipmentOut]:
    base = select(Shipment)
    if status is not None:
        base = base.where(Shipment.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(Shipment.created_at.desc()).limit(limit).offset(offset)).all()
    return ListEnvelope(
        data=[ShipmentOut.model_validate(s) for s in rows],
        meta=ListMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/{shipment_id}", response_model=Envelope[ShipmentOut], summary="Get one shipment")
def get_shipment(shipment_id: str, db: Session = Depends(get_db)) -> Envelope[ShipmentOut]:
    shipment = db.get(Shipment, shipment_id)
    if shipment is None:
        raise NotFoundError(f"Shipment {shipment_id} not found.")
    return Envelope(data=ShipmentOut.model_validate(shipment))
