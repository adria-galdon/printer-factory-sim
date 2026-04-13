"""
Production service.

run_production(db) implements the FIFO partial-fill logic from PRD section 6:

  For each released order (sorted by created_day ASC):
    1. Compute how many units can be built given remaining daily capacity
       and current stock for every BOM material.
    2. Consume materials proportionally.
    3. Update quantity_completed and order status.
    4. Log events.

Order statuses:
  pending        — generated, not yet released by user
  in_production  — released; partially complete or waiting for stock
  completed      — quantity_completed == quantity_ordered
  blocked        — released but 0 units producible (no stock, no capacity)
"""

import json
import math
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from api.models import (
    BOMLine,
    EventLog,
    Inventory,
    ManufacturingOrder,
    PrinterModel,
    SimulationState,
)


def run_production(db: Session, current_day: int) -> list[dict]:
    """
    Run one day's production cycle.  Returns a summary list of dicts
    (one per processed order) describing what happened.
    """
    state: SimulationState = db.get(SimulationState, 1)
    remaining_capacity = state.daily_capacity - state.capacity_used_today

    # Collect all orders that are eligible for production (released by user)
    orders: list[ManufacturingOrder] = (
        db.query(ManufacturingOrder)
        .filter(ManufacturingOrder.status.in_(["in_production", "pending"]))
        # Only process orders that have been released (released_day is set)
        .filter(ManufacturingOrder.released_day.isnot(None))
        .order_by(ManufacturingOrder.created_day.asc(), ManufacturingOrder.id.asc())
        .all()
    )

    # Pre-load BOM lines and inventory into dicts for fast lookup
    bom_map = _build_bom_map(db)
    inventory_map: dict[str, Inventory] = {
        inv.material_id: inv
        for inv in db.query(Inventory).all()
    }

    results = []

    for order in orders:
        if remaining_capacity <= 0:
            break

        remaining_units = order.quantity_ordered - order.quantity_completed
        bom = bom_map.get(order.printer_model_id, [])

        producible = _max_producible(
            bom=bom,
            inventory_map=inventory_map,
            remaining_capacity=remaining_capacity,
            remaining_units=remaining_units,
        )

        if producible == 0:
            _set_status(order, "blocked")
            db.add(EventLog(
                day=current_day,
                event_type="order.blocked",
                entity_type="manufacturing_order",
                entity_id=order.id,
                payload=json.dumps({
                    "printer_model_id": order.printer_model_id,
                    "quantity_remaining": remaining_units,
                    "reason": "insufficient_stock_or_capacity",
                }),
                timestamp=datetime.utcnow(),
            ))
            results.append({"order_id": order.id, "produced": 0, "status": "blocked"})
            continue

        # Consume materials
        for line in bom:
            inv = inventory_map[line.material_id]
            consumed = line.quantity_per_unit * producible
            inv.quantity -= consumed
            db.add(EventLog(
                day=current_day,
                event_type="inventory.consumed",
                entity_type="inventory",
                entity_id=line.material_id,
                payload=json.dumps({
                    "material_id": line.material_id,
                    "delta": -consumed,
                    "new_quantity": inv.quantity,
                    "manufacturing_order_id": order.id,
                }),
                timestamp=datetime.utcnow(),
            ))

        order.quantity_completed += producible
        remaining_capacity -= producible
        state.capacity_used_today += producible

        if order.quantity_completed >= order.quantity_ordered:
            order.completed_day = current_day
            _set_status(order, "completed")
            db.add(EventLog(
                day=current_day,
                event_type="order.completed",
                entity_type="manufacturing_order",
                entity_id=order.id,
                payload=json.dumps({
                    "printer_model_id": order.printer_model_id,
                    "quantity_ordered": order.quantity_ordered,
                    "quantity_completed": order.quantity_completed,
                }),
                timestamp=datetime.utcnow(),
            ))
            results.append({"order_id": order.id, "produced": producible, "status": "completed"})
        else:
            _set_status(order, "in_production")
            db.add(EventLog(
                day=current_day,
                event_type="order.partially_completed",
                entity_type="manufacturing_order",
                entity_id=order.id,
                payload=json.dumps({
                    "printer_model_id": order.printer_model_id,
                    "quantity_produced_today": producible,
                    "quantity_completed": order.quantity_completed,
                    "quantity_remaining": order.quantity_ordered - order.quantity_completed,
                }),
                timestamp=datetime.utcnow(),
            ))
            results.append({"order_id": order.id, "produced": producible, "status": "in_production"})

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_bom_map(db: Session) -> dict[str, list[BOMLine]]:
    """Return {printer_model_id: [BOMLine, ...]} for all models."""
    lines = db.query(BOMLine).all()
    result: dict[str, list[BOMLine]] = {}
    for line in lines:
        result.setdefault(line.printer_model_id, []).append(line)
    return result


def _max_producible(
    bom: list[BOMLine],
    inventory_map: dict[str, Inventory],
    remaining_capacity: int,
    remaining_units: int,
) -> int:
    """
    Compute how many units can be produced given current stock and capacity.
    Returns an integer >= 0.
    """
    limit = min(remaining_capacity, remaining_units)

    for line in bom:
        inv = inventory_map.get(line.material_id)
        if inv is None or line.quantity_per_unit == 0:
            return 0
        stock_limit = inv.quantity // line.quantity_per_unit
        limit = min(limit, stock_limit)

    return max(0, limit)


def _set_status(order: ManufacturingOrder, status: str) -> None:
    order.status = status
