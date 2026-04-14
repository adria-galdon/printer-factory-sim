from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api.schemas import ManufacturingOrderDetailOut, ManufacturingOrderOut
from api.services.orders import (
    compute_bom_breakdown,
    get_manufacturing_order,
    list_manufacturing_orders,
    release_manufacturing_order,
)

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("", response_model=list[ManufacturingOrderOut])
def list_orders(status: str | None = None, db: Session = Depends(get_db)):
    return list_manufacturing_orders(db, status)


@router.get("/{order_id}", response_model=ManufacturingOrderDetailOut)
def get_order(order_id: str, db: Session = Depends(get_db)):
    order = get_manufacturing_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found")
    bom_breakdown = compute_bom_breakdown(db, order)
    base = ManufacturingOrderOut.model_validate(order)
    return ManufacturingOrderDetailOut(**base.model_dump(), bom_breakdown=bom_breakdown)


@router.post("/{order_id}/release", response_model=ManufacturingOrderOut)
def release_order(order_id: str, db: Session = Depends(get_db)):
    order = release_manufacturing_order(db, order_id)
    return order
