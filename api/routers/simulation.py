from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import SimulationState
from api.schemas import MessageOut, SimulationStateOut
from api.services.simulation import advance_day, reset_simulation

router = APIRouter(prefix="/simulation", tags=["Simulation"])


def _get_state(db: Session) -> SimulationState:
    state = db.get(SimulationState, 1)
    if not state:
        raise HTTPException(status_code=500, detail="Simulation state not initialised")
    return state


@router.get("/state", response_model=SimulationStateOut)
def get_simulation_state(db: Session = Depends(get_db)):
    return _get_state(db)


@router.post("/advance")
def advance(db: Session = Depends(get_db)):
    """
    Run a full 24-hour simulation cycle:
    demand generation → purchase arrivals → production → day increment.
    Returns a summary of what happened.
    """
    return advance_day(db)


@router.post("/reset", response_model=MessageOut)
def reset(db: Session = Depends(get_db)):
    """
    Wipe all transient state (orders, POs, inventory, event log) and reset to day 1.
    Catalog data (materials, models, suppliers) is preserved.
    """
    reset_simulation(db)
    return {"message": "Simulation reset to day 1"}
