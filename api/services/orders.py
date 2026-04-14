"""
Manufacturing order operations: list, detail with BOM breakdown, release to production.
"""

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from api.models import BOMLine, EventLog, Inventory, ManufacturingOrder, SimulationState
from api.schemas import OrderBOMBreakdownLineOut


def list_manufacturing_orders(db: Session, status: str | None) -> list[ManufacturingOrder]:
    q = (
        db.query(ManufacturingOrder)
        .options(joinedload(ManufacturingOrder.printer_model))
        .order_by(ManufacturingOrder.created_day.asc(), ManufacturingOrder.id.asc())
    )
    if status is not None:
        q = q.filter(ManufacturingOrder.status == status)
    return q.all()


def get_manufacturing_order(
    db: Session, order_id: str
) -> ManufacturingOrder | None:
    return (
        db.query(ManufacturingOrder)
        .options(joinedload(ManufacturingOrder.printer_model))
        .filter(ManufacturingOrder.id == order_id)
        .first()
    )


def compute_bom_breakdown(db: Session, order: ManufacturingOrder) -> list[OrderBOMBreakdownLineOut]:
    lines = (
        db.query(BOMLine)
        .options(joinedload(BOMLine.material))
        .filter(BOMLine.printer_model_id == order.printer_model_id)
        .order_by(BOMLine.material_id)
        .all()
    )
    if not lines:
        return []

    material_ids = [ln.material_id for ln in lines]
    inv_rows = (
        db.query(Inventory)
        .filter(Inventory.material_id.in_(material_ids))
        .all()
    )
    inv_map = {inv.material_id: inv.quantity for inv in inv_rows}

    out: list[OrderBOMBreakdownLineOut] = []
    for line in lines:
        qty_needed = line.quantity_per_unit * order.quantity_ordered
        out.append(
            OrderBOMBreakdownLineOut(
                material_id=line.material_id,
                material_name=line.material.name,
                quantity_needed=qty_needed,
                quantity_in_stock=inv_map.get(line.material_id, 0),
            )
        )
    return out


def release_manufacturing_order(db: Session, order_id: str) -> ManufacturingOrder:
    order = (
        db.query(ManufacturingOrder)
        .options(joinedload(ManufacturingOrder.printer_model))
        .filter(ManufacturingOrder.id == order_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found")

    if order.status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only pending orders can be released to production",
        )

    state = db.get(SimulationState, 1)
    if state is None:
        raise HTTPException(status_code=500, detail="Simulation state not initialised")

    order.status = "in_production"
    order.released_day = state.current_day

    db.add(
        EventLog(
            day=state.current_day,
            event_type="order.released",
            entity_type="manufacturing_order",
            entity_id=order.id,
            payload=json.dumps(
                {
                    "printer_model_id": order.printer_model_id,
                    "quantity_ordered": order.quantity_ordered,
                    "released_day": state.current_day,
                }
            ),
            timestamp=datetime.utcnow(),
        )
    )
    db.commit()
    db.refresh(order)
    return order
