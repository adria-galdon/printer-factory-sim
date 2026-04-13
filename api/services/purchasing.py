"""
Purchasing service.

issue_purchase_order  — create a PO with price locked from best matching tier
process_arrivals      — deliver all in-transit POs due on or before current_day
"""

import json
import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from api.models import (
    EventLog,
    Inventory,
    PriceTier,
    PurchaseOrder,
    Supplier,
    SupplierProduct,
)


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------

def issue_purchase_order(
    db: Session,
    supplier_product_id: str,
    quantity: int,
    current_day: int,
) -> PurchaseOrder:
    """
    Create a new PurchaseOrder.  Unit price is locked at the best (lowest)
    matching price tier for the requested quantity.
    """
    if quantity <= 0:
        raise HTTPException(status_code=422, detail="quantity must be > 0")

    product = (
        db.query(SupplierProduct)
        .options(
            joinedload(SupplierProduct.supplier),
            joinedload(SupplierProduct.price_tiers),
        )
        .filter(SupplierProduct.id == supplier_product_id)
        .first()
    )
    if not product:
        raise HTTPException(
            status_code=404,
            detail=f"Supplier product '{supplier_product_id}' not found",
        )

    unit_price = _resolve_unit_price(product.price_tiers, quantity)
    total_price = round(unit_price * quantity, 2)
    arrival_day = current_day + product.supplier.lead_time_days

    po = PurchaseOrder(
        id=str(uuid.uuid4()),
        supplier_product_id=supplier_product_id,
        quantity=quantity,
        unit_price=unit_price,
        total_price=total_price,
        issued_day=current_day,
        expected_arrival_day=arrival_day,
        status="in_transit",
    )
    db.add(po)
    db.flush()

    db.add(EventLog(
        day=current_day,
        event_type="purchase.issued",
        entity_type="purchase_order",
        entity_id=po.id,
        payload=json.dumps({
            "supplier_product_id": supplier_product_id,
            "material_id": product.material_id,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_price": total_price,
            "expected_arrival_day": arrival_day,
        }),
        timestamp=datetime.utcnow(),
    ))
    return po


def _resolve_unit_price(tiers: list[PriceTier], quantity: int) -> float:
    """
    Return the unit price of the highest min_quantity tier that is still
    <= the requested quantity.  Falls back to the first tier if none qualify.
    """
    eligible = [t for t in tiers if t.min_quantity <= quantity]
    if not eligible:
        # quantity is below the lowest tier minimum — use the cheapest available
        return min(tiers, key=lambda t: t.unit_price).unit_price
    # best = highest min_quantity among eligible (deepest discount)
    best = max(eligible, key=lambda t: t.min_quantity)
    return best.unit_price


# ---------------------------------------------------------------------------
# Arrivals
# ---------------------------------------------------------------------------

def process_arrivals(db: Session, current_day: int) -> list[PurchaseOrder]:
    """
    Deliver all in-transit POs whose expected_arrival_day <= current_day.
    Updates inventory and logs purchase.delivered + inventory.restocked events.
    """
    due: list[PurchaseOrder] = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.supplier_product))
        .filter(
            PurchaseOrder.status == "in_transit",
            PurchaseOrder.expected_arrival_day <= current_day,
        )
        .all()
    )

    for po in due:
        material_id = po.supplier_product.material_id

        inventory = db.get(Inventory, material_id)
        if inventory is None:
            # Should never happen if DB is consistent, but guard anyway
            continue

        inventory.quantity += po.quantity
        po.status = "delivered"

        db.add(EventLog(
            day=current_day,
            event_type="purchase.delivered",
            entity_type="purchase_order",
            entity_id=po.id,
            payload=json.dumps({
                "material_id": material_id,
                "quantity": po.quantity,
            }),
            timestamp=datetime.utcnow(),
        ))
        db.add(EventLog(
            day=current_day,
            event_type="inventory.restocked",
            entity_type="inventory",
            entity_id=material_id,
            payload=json.dumps({
                "material_id": material_id,
                "delta": po.quantity,
                "new_quantity": inventory.quantity,
                "purchase_order_id": po.id,
            }),
            timestamp=datetime.utcnow(),
        ))

    return due
