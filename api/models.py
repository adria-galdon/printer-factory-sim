from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Text, ForeignKey,
    UniqueConstraint, DateTime, func,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Material(Base):
    __tablename__ = "materials"

    id = Column(String, primary_key=True)  # e.g. "kit_piezas"
    name = Column(String, nullable=False)
    unit = Column(String, nullable=False, default="unit")

    inventory = relationship("Inventory", back_populates="material", uselist=False)
    bom_lines = relationship("BOMLine", back_populates="material")
    supplier_products = relationship("SupplierProduct", back_populates="material")


class Inventory(Base):
    __tablename__ = "inventory"

    material_id = Column(String, ForeignKey("materials.id"), primary_key=True)
    quantity = Column(Integer, nullable=False, default=0)
    warehouse_capacity = Column(Integer, nullable=True)  # NULL = unlimited

    material = relationship("Material", back_populates="inventory")


class PrinterModel(Base):
    __tablename__ = "printer_models"

    id = Column(String, primary_key=True)  # e.g. "P3D-Classic"
    name = Column(String, nullable=False)
    assembly_time_days = Column(Float, nullable=False)  # capacity consumed per unit
    demand_mean = Column(Float, nullable=False)
    demand_variance = Column(Float, nullable=False)

    bom_lines = relationship("BOMLine", back_populates="printer_model")
    manufacturing_orders = relationship("ManufacturingOrder", back_populates="printer_model")


class BOMLine(Base):
    __tablename__ = "bom_lines"

    printer_model_id = Column(String, ForeignKey("printer_models.id"), primary_key=True)
    material_id = Column(String, ForeignKey("materials.id"), primary_key=True)
    quantity_per_unit = Column(Integer, nullable=False)

    printer_model = relationship("PrinterModel", back_populates="bom_lines")
    material = relationship("Material", back_populates="bom_lines")


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    lead_time_days = Column(Integer, nullable=False)

    products = relationship("SupplierProduct", back_populates="supplier")


class SupplierProduct(Base):
    __tablename__ = "supplier_products"

    id = Column(String, primary_key=True)
    supplier_id = Column(String, ForeignKey("suppliers.id"), nullable=False)
    material_id = Column(String, ForeignKey("materials.id"), nullable=False)
    description = Column(String, nullable=False)

    supplier = relationship("Supplier", back_populates="products")
    material = relationship("Material", back_populates="supplier_products")
    price_tiers = relationship(
        "PriceTier", back_populates="supplier_product", order_by="PriceTier.min_quantity"
    )
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier_product")


class PriceTier(Base):
    __tablename__ = "price_tiers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_product_id = Column(String, ForeignKey("supplier_products.id"), nullable=False)
    min_quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    lot_size = Column(Integer, nullable=True)   # e.g. 20 (box), 1000 (pallet); NULL = any
    label = Column(String, nullable=True)        # e.g. "box of 20"

    supplier_product = relationship("SupplierProduct", back_populates="price_tiers")


class ManufacturingOrder(Base):
    __tablename__ = "manufacturing_orders"

    id = Column(String, primary_key=True)  # UUID
    printer_model_id = Column(String, ForeignKey("printer_models.id"), nullable=False)
    quantity_ordered = Column(Integer, nullable=False)
    quantity_completed = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="pending")
    # statuses: pending | in_production | completed | blocked
    created_day = Column(Integer, nullable=False)
    released_day = Column(Integer, nullable=True)
    completed_day = Column(Integer, nullable=True)

    printer_model = relationship("PrinterModel", back_populates="manufacturing_orders")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(String, primary_key=True)  # UUID
    supplier_product_id = Column(String, ForeignKey("supplier_products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)   # locked at order time
    total_price = Column(Float, nullable=False)
    issued_day = Column(Integer, nullable=False)
    expected_arrival_day = Column(Integer, nullable=False)  # issued_day + lead_time_days
    status = Column(String, nullable=False, default="in_transit")
    # statuses: in_transit | delivered

    supplier_product = relationship("SupplierProduct", back_populates="purchase_orders")


class EventLog(Base):
    __tablename__ = "event_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    payload = Column(Text, nullable=True)   # JSON blob
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)


class SimulationState(Base):
    """Singleton row — always id=1."""
    __tablename__ = "simulation_state"

    id = Column(Integer, primary_key=True, default=1)
    current_day = Column(Integer, nullable=False, default=1)
    daily_capacity = Column(Integer, nullable=False, default=10)
    capacity_used_today = Column(Integer, nullable=False, default=0)
