"""
Demand generation service.

For each printer model, samples from Normal(demand_mean, sqrt(demand_variance))
clipped at 0 and rounded to the nearest integer.  Creates ManufacturingOrder
rows with status='pending' and logs a demand.generated event per order.
"""

import json
import math
import random
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from api.models import EventLog, ManufacturingOrder, PrinterModel


def generate_demand(db: Session, current_day: int) -> list[ManufacturingOrder]:
    """
    Sample demand for every printer model and persist ManufacturingOrder rows.

    Returns the list of newly created orders (may be empty if all samples round
    to 0).
    """
    models = db.query(PrinterModel).all()
    created: list[ManufacturingOrder] = []

    for model in models:
        qty = _sample_demand(model.demand_mean, model.demand_variance)
        if qty <= 0:
            continue

        order = ManufacturingOrder(
            id=str(uuid.uuid4()),
            printer_model_id=model.id,
            quantity_ordered=qty,
            quantity_completed=0,
            status="pending",
            created_day=current_day,
        )
        db.add(order)
        db.flush()  # populate order.id before logging

        db.add(EventLog(
            day=current_day,
            event_type="demand.generated",
            entity_type="manufacturing_order",
            entity_id=order.id,
            payload=json.dumps({
                "printer_model_id": model.id,
                "quantity_ordered": qty,
            }),
            timestamp=datetime.utcnow(),
        ))
        created.append(order)

    return created


def _sample_demand(mean: float, variance: float) -> int:
    """
    Draw one sample from Normal(mean, sqrt(variance)), clip at 0, round to int.
    Uses random.gauss for reproducibility with random.seed().
    """
    if variance <= 0:
        return max(0, round(mean))
    sample = random.gauss(mean, math.sqrt(variance))
    return max(0, round(sample))
