from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from api.database import get_db
from api.models import BOMLine, Material, PrinterModel, Supplier, SupplierProduct
from api.schemas import (
    BOMLineOut,
    MaterialOut,
    PrinterModelOut,
    PrinterModelWithBOMOut,
    SupplierOut,
    SupplierProductOut,
    SupplierWithProductsOut,
)

router = APIRouter(prefix="/catalog", tags=["Catalog"])


@router.get("/materials", response_model=list[MaterialOut])
def list_materials(db: Session = Depends(get_db)):
    return db.query(Material).order_by(Material.id).all()


@router.get("/printer-models", response_model=list[PrinterModelOut])
def list_printer_models(db: Session = Depends(get_db)):
    return db.query(PrinterModel).order_by(PrinterModel.id).all()


@router.get("/printer-models/{model_id}/bom", response_model=PrinterModelWithBOMOut)
def get_printer_model_bom(model_id: str, db: Session = Depends(get_db)):
    model = (
        db.query(PrinterModel)
        .options(
            joinedload(PrinterModel.bom_lines).joinedload(BOMLine.material)
        )
        .filter(PrinterModel.id == model_id)
        .first()
    )
    if not model:
        raise HTTPException(status_code=404, detail=f"Printer model '{model_id}' not found")
    return model


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db)):
    return db.query(Supplier).order_by(Supplier.id).all()


@router.get("/suppliers/{supplier_id}/products", response_model=list[SupplierProductOut])
def list_supplier_products(supplier_id: str, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail=f"Supplier '{supplier_id}' not found")

    products = (
        db.query(SupplierProduct)
        .options(
            joinedload(SupplierProduct.material),
            joinedload(SupplierProduct.price_tiers),
        )
        .filter(SupplierProduct.supplier_id == supplier_id)
        .all()
    )
    return products


@router.get("/products", response_model=list[SupplierProductOut])
def list_all_products(db: Session = Depends(get_db)):
    """All supplier products across all suppliers, with price tiers."""
    return (
        db.query(SupplierProduct)
        .options(
            joinedload(SupplierProduct.material),
            joinedload(SupplierProduct.price_tiers),
        )
        .order_by(SupplierProduct.id)
        .all()
    )
