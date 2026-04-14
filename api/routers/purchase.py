from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import PurchaseOrder, SimulationState
from api.schemas import PurchaseOrderCreate, PurchaseOrderOut
from api.services.purchasing import issue_purchase_order

router = APIRouter(prefix="/purchases", tags=["Purchases"])


@router.get("", response_model=list[PurchaseOrderOut])
def list_purchase_orders(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(PurchaseOrder).order_by(
        PurchaseOrder.issued_day.desc(),
        PurchaseOrder.id.asc(),
    )
    if status is not None:
        q = q.filter(PurchaseOrder.status == status)
    return q.all()


@router.post("", response_model=PurchaseOrderOut, status_code=201)
def create_purchase_order(body: PurchaseOrderCreate, db: Session = Depends(get_db)):
    state = db.get(SimulationState, 1)
    if state is None:
        raise HTTPException(status_code=500, detail="Simulation state not initialised")

    po = issue_purchase_order(
        db,
        body.supplier_product_id,
        body.quantity,
        state.current_day,
    )
    db.commit()
    db.refresh(po)
    return po


@router.get("/{po_id}", response_model=PurchaseOrderOut)
def get_purchase_order(po_id: str, db: Session = Depends(get_db)):
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise HTTPException(
            status_code=404,
            detail=f"Purchase order '{po_id}' not found",
        )
    return po
