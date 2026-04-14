from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.database import get_db
from api.schemas import ExportPayload, ImportPayload, MessageOut
from api.services.io import export_simulation_state, import_simulation_state

router = APIRouter(prefix="/io", tags=["Import/Export"])


@router.get("/export", response_model=ExportPayload)
def export_state(db: Session = Depends(get_db)):
    return export_simulation_state(db)


@router.post("/import", response_model=MessageOut)
def import_state(body: ImportPayload, db: Session = Depends(get_db)):
    import_simulation_state(db, body)
    return {"message": "Simulation state imported successfully"}
