from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session
from .. import schema, models
from ..database import get_db
 
router = APIRouter(
    prefix="/reservations",
    tags=["Reservations & Seat Holds"]
)
 
# -------------------------------------------------------------------
# Get all HELD or CONFIRMED seats for an event (PUBLIC)
#
# CHANGED: async def -> def — no await in this body, so it was blocking
# the event loop for its DB round-trip, same class of issue as auth.py.
# -------------------------------------------------------------------
@router.get("/event/{event_id}/occupied", response_model=List[schema.TicketResponse])
def get_occupied_seats(event_id: int, db: Session = Depends(get_db)):
    """
    Returns all seats that are currently HELD or CONFIRMED for a given event
    so the frontend can render unavailable seats on the venue map.
    """
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Event with id: {event_id} not found")
 
    occupied_seats = db.query(models.Ticket).filter(models.Ticket.event_id == event_id, models.Ticket.status.in_(["HELD", "CONFIRMED"])).all()
 
    return occupied_seats