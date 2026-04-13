"""
Simulation orchestrator.

advance_day(db) uses SimPy to run the four-phase day cycle in strict order:
  1. Demand generation
  2. Purchase arrivals
  3. Production run
  4. Day close (increment day, reset capacity, log day.advanced)

SimPy is used here as a lightweight deterministic event scheduler.  Each phase
is a SimPy process that yields after completing, guaranteeing phase ordering
without threading complexity.

reset_simulation(db) wipes all transient state (orders, POs, inventory, log)
and re-seeds from initial_config.json.
"""

import json
import logging
from datetime import datetime

import simpy
from sqlalchemy.orm import Session

from api.models import (
    EventLog,
    Inventory,
    ManufacturingOrder,
    PurchaseOrder,
    SimulationState,
)
from api.services.demand import generate_demand
from api.services.production import run_production
from api.services.purchasing import process_arrivals

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Advance day
# ---------------------------------------------------------------------------

def advance_day(db: Session) -> dict:
    """
    Run a full 24-hour simulation cycle.
    Returns a summary dict with counts of what happened.
    """
    state: SimulationState = db.get(SimulationState, 1)
    if not state:
        raise RuntimeError("Simulation state not initialised — run init_db() first")

    current_day = state.current_day
    summary: dict = {}

    env = simpy.Environment()

    def _day_cycle(env):
        # Phase 1 — demand generation
        new_orders = generate_demand(db, current_day)
        summary["new_orders"] = len(new_orders)
        summary["new_order_ids"] = [o.id for o in new_orders]
        yield env.timeout(1)

        # Phase 2 — purchase arrivals
        arrived_pos = process_arrivals(db, current_day)
        summary["purchase_arrivals"] = len(arrived_pos)
        yield env.timeout(1)

        # Phase 3 — production run
        production_results = run_production(db, current_day)
        summary["production_results"] = production_results
        summary["units_produced"] = sum(r["produced"] for r in production_results)
        yield env.timeout(1)

        # Phase 4 — close the day
        state.current_day += 1
        state.capacity_used_today = 0

        db.add(EventLog(
            day=current_day,
            event_type="day.advanced",
            entity_type="simulation",
            entity_id="1",
            payload=json.dumps({
                "day_completed": current_day,
                "next_day": state.current_day,
                "new_orders": summary["new_orders"],
                "purchase_arrivals": summary["purchase_arrivals"],
                "units_produced": summary["units_produced"],
            }),
            timestamp=datetime.utcnow(),
        ))
        yield env.timeout(1)

    env.process(_day_cycle(env))
    env.run()

    db.commit()

    summary["day_completed"] = current_day
    summary["next_day"] = state.current_day
    logger.info(
        "Day %d complete — orders: %d, arrivals: %d, produced: %d",
        current_day,
        summary["new_orders"],
        summary["purchase_arrivals"],
        summary["units_produced"],
    )
    return summary


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def reset_simulation(db: Session) -> None:
    """
    Wipe all transient simulation data and re-seed from initial_config.json.
    Preserves the catalog (materials, printer models, suppliers, products, tiers).
    """
    # Delete transient tables
    db.query(EventLog).delete()
    db.query(ManufacturingOrder).delete()
    db.query(PurchaseOrder).delete()

    # Zero out inventory
    db.query(Inventory).update({"quantity": 0})

    # Reset simulation state to day 1
    state = db.get(SimulationState, 1)
    if state:
        state.current_day = 1
        state.capacity_used_today = 0

    db.commit()
    logger.info("Simulation reset to day 1.")
