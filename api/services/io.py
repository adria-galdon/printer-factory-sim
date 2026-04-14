"""
Export / import simulation state (inventory, orders, POs, event log, simulation state).
"""

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.models import (
    EventLog,
    Inventory,
    ManufacturingOrder,
    PurchaseOrder,
    SimulationState,
)
from api.schemas import (
    EventLogOut,
    ExportPayload,
    ImportPayload,
    InventoryLevelOut,
    ManufacturingOrderExportOut,
    PurchaseOrderOut,
    SimulationStateExportOut,
)
from api.services.simulation import reset_simulation


def export_simulation_state(db: Session) -> ExportPayload:
    state = db.get(SimulationState, 1)
    if state is None:
        raise HTTPException(status_code=500, detail="Simulation state not initialised")

    simulation_state = SimulationStateExportOut(
        current_day=state.current_day,
        daily_capacity=state.daily_capacity,
        capacity_used_today=state.capacity_used_today,
    )

    inv_rows = (
        db.query(Inventory)
        .order_by(Inventory.material_id.asc())
        .all()
    )
    inventory = [
        InventoryLevelOut(
            material_id=row.material_id,
            quantity=row.quantity,
            warehouse_capacity=row.warehouse_capacity,
        )
        for row in inv_rows
    ]

    mo_rows = (
        db.query(ManufacturingOrder)
        .order_by(ManufacturingOrder.created_day.asc(), ManufacturingOrder.id.asc())
        .all()
    )
    manufacturing_orders = [
        ManufacturingOrderExportOut.model_validate(mo) for mo in mo_rows
    ]

    po_rows = (
        db.query(PurchaseOrder)
        .order_by(PurchaseOrder.issued_day.asc(), PurchaseOrder.id.asc())
        .all()
    )
    purchase_orders = [PurchaseOrderOut.model_validate(po) for po in po_rows]

    ev_rows = (
        db.query(EventLog)
        .order_by(EventLog.id.asc())
        .all()
    )
    event_log = [EventLogOut.model_validate(ev) for ev in ev_rows]

    return ExportPayload(
        simulation_state=simulation_state,
        inventory=inventory,
        manufacturing_orders=manufacturing_orders,
        purchase_orders=purchase_orders,
        event_log=event_log,
    )


def import_simulation_state(db: Session, payload: ImportPayload) -> None:
    reset_simulation(db)

    state = db.get(SimulationState, 1)
    if state is None:
        raise HTTPException(status_code=500, detail="Simulation state not initialised")

    state.current_day = payload.simulation_state.current_day
    state.daily_capacity = payload.simulation_state.daily_capacity
    state.capacity_used_today = payload.simulation_state.capacity_used_today

    for inv in payload.inventory:
        row = db.get(Inventory, inv.material_id)
        if row is None:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown material_id in inventory: '{inv.material_id}'",
            )
        row.quantity = inv.quantity
        if inv.warehouse_capacity is not None:
            row.warehouse_capacity = inv.warehouse_capacity

    for mo in payload.manufacturing_orders:
        db.add(
            ManufacturingOrder(
                id=mo.id,
                printer_model_id=mo.printer_model_id,
                quantity_ordered=mo.quantity_ordered,
                quantity_completed=mo.quantity_completed,
                status=mo.status,
                created_day=mo.created_day,
                released_day=mo.released_day,
                completed_day=mo.completed_day,
            )
        )

    for po in payload.purchase_orders:
        db.add(
            PurchaseOrder(
                id=po.id,
                supplier_product_id=po.supplier_product_id,
                quantity=po.quantity,
                unit_price=po.unit_price,
                total_price=po.total_price,
                issued_day=po.issued_day,
                expected_arrival_day=po.expected_arrival_day,
                status=po.status,
            )
        )

    for ev in payload.event_log:
        db.add(
            EventLog(
                id=ev.id,
                day=ev.day,
                event_type=ev.event_type,
                entity_type=ev.entity_type,
                entity_id=ev.entity_id,
                payload=ev.payload,
                timestamp=ev.timestamp,
            )
        )

    db.add(
        EventLog(
            day=state.current_day,
            event_type="simulation.imported",
            entity_type="simulation",
            entity_id="1",
            payload=json.dumps({"source": "io.import"}),
            timestamp=datetime.utcnow(),
        )
    )
    db.commit()
