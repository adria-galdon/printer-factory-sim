from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from api.database import get_db
from api.models import Inventory
from api.schemas import InventoryOut

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("", response_model=list[InventoryOut])
def list_inventory(db: Session = Depends(get_db)):
    """All materials with current stock levels."""
    return (
        db.query(Inventory)
        .options(joinedload(Inventory.material))
        .order_by(Inventory.material_id)
        .all()
    )


@router.get("/{material_id}", response_model=InventoryOut)
def get_inventory_item(material_id: str, db: Session = Depends(get_db)):
    item = (
        db.query(Inventory)
        .options(joinedload(Inventory.material))
        .filter(Inventory.material_id == material_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail=f"Material '{material_id}' not found")
    return item
