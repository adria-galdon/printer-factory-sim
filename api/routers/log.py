from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import EventLog
from api.schemas import EventLogOut

router = APIRouter(prefix="/log", tags=["Event Log"])


@router.get("", response_model=list[EventLogOut])
def get_log(
    day_from: Optional[int] = Query(None, description="Filter events from this day (inclusive)"),
    day_to: Optional[int] = Query(None, description="Filter events up to this day (inclusive)"),
    event_type: Optional[str] = Query(None, description="Filter by event type, e.g. demand.generated"),
    limit: int = Query(200, ge=1, le=1000, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """
    Return event log entries, newest first.

    Filterable by day range and event_type.  Paginated via limit/offset.
    """
    q = db.query(EventLog)

    if day_from is not None:
        q = q.filter(EventLog.day >= day_from)
    if day_to is not None:
        q = q.filter(EventLog.day <= day_to)
    if event_type is not None:
        q = q.filter(EventLog.event_type == event_type)

    return (
        q.order_by(EventLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/summary")
def get_log_summary(db: Session = Depends(get_db)):
    """
    Aggregated event counts per (day, event_type), ordered by day ascending.
    """
    from sqlalchemy import func
    rows = (
        db.query(
            EventLog.day,
            EventLog.event_type,
            func.count(EventLog.id).label("count"),
        )
        .group_by(EventLog.day, EventLog.event_type)
        .order_by(EventLog.day.asc(), EventLog.event_type.asc())
        .all()
    )
    return [{"day": r.day, "event_type": r.event_type, "count": r.count} for r in rows]
