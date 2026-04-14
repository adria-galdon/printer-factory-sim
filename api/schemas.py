"""
Pydantic v2 request/response schemas.

Convention: ORM models live in api/models.py (SQLAlchemy).
            These schemas are the API surface — never return ORM objects directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Shared config: all response schemas use from_attributes=True so they can be
# constructed directly from SQLAlchemy ORM instances.
# ---------------------------------------------------------------------------

class _ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Material
# ---------------------------------------------------------------------------

class MaterialOut(_ORMBase):
    id: str
    name: str
    unit: str


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class InventoryOut(_ORMBase):
    material_id: str
    quantity: int
    warehouse_capacity: Optional[int]
    # Convenience: embed the material name so the UI doesn't need a second call
    material: MaterialOut


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------

class BOMLineOut(_ORMBase):
    material_id: str
    quantity_per_unit: int
    material: MaterialOut


# ---------------------------------------------------------------------------
# Printer model
# ---------------------------------------------------------------------------

class PrinterModelOut(_ORMBase):
    id: str
    name: str
    assembly_time_days: float
    demand_mean: float
    demand_variance: float


class PrinterModelWithBOMOut(PrinterModelOut):
    bom_lines: list[BOMLineOut]


# ---------------------------------------------------------------------------
# Price tier
# ---------------------------------------------------------------------------

class PriceTierOut(_ORMBase):
    id: int
    min_quantity: int
    unit_price: float
    lot_size: Optional[int]
    label: Optional[str]


# ---------------------------------------------------------------------------
# Supplier product
# ---------------------------------------------------------------------------

class SupplierProductOut(_ORMBase):
    id: str
    supplier_id: str
    material_id: str
    description: str
    material: MaterialOut
    price_tiers: list[PriceTierOut]


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------

class SupplierOut(_ORMBase):
    id: str
    name: str
    lead_time_days: int


class SupplierWithProductsOut(SupplierOut):
    products: list[SupplierProductOut]


# ---------------------------------------------------------------------------
# Simulation state
# ---------------------------------------------------------------------------

class SimulationStateOut(_ORMBase):
    id: int
    current_day: int
    daily_capacity: int
    capacity_used_today: int


# ---------------------------------------------------------------------------
# Manufacturing order
# ---------------------------------------------------------------------------

class ManufacturingOrderOut(_ORMBase):
    id: str
    printer_model_id: str
    quantity_ordered: int
    quantity_completed: int
    status: str
    created_day: int
    released_day: Optional[int]
    completed_day: Optional[int]
    printer_model: PrinterModelOut


class OrderBOMBreakdownLineOut(BaseModel):
    """Per-line material requirements for an order (BOM × quantity_ordered)."""

    material_id: str
    material_name: str
    quantity_needed: int
    quantity_in_stock: int


class ManufacturingOrderDetailOut(ManufacturingOrderOut):
    bom_breakdown: list[OrderBOMBreakdownLineOut]


# ---------------------------------------------------------------------------
# Purchase order (stub — full schemas added in M3)
# ---------------------------------------------------------------------------

class PurchaseOrderOut(_ORMBase):
    id: str
    supplier_product_id: str
    quantity: int
    unit_price: float
    total_price: float
    issued_day: int
    expected_arrival_day: int
    status: str


# ---------------------------------------------------------------------------
# Purchase order request
# ---------------------------------------------------------------------------

class PurchaseOrderCreate(BaseModel):
    supplier_product_id: str
    quantity: int


# ---------------------------------------------------------------------------
# Event log (stub — full schemas added in M2)
# ---------------------------------------------------------------------------

class EventLogOut(_ORMBase):
    id: int
    day: int
    event_type: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    payload: Optional[str]
    timestamp: datetime


# ---------------------------------------------------------------------------
# Generic responses
# ---------------------------------------------------------------------------

class MessageOut(BaseModel):
    message: str
