from fastapi import APIRouter, Depends, HTTPException, status, Header
from .. import schema, oauth2, models
from sqlalchemy.orm import Session
from typing import List, Optional
from sqlalchemy.exc import IntegrityError
from ..database import get_db
 
router = APIRouter(
    prefix="/events",
    tags=["Event"]
)
 
# -------------------------------------------------------------------
# Get all Events endpoint (PUBLIC)
#
# CHANGED: async def -> def for every route in this file that has no
# actual `await` in its body. These only do synchronous SQLAlchemy
# calls, which is BLOCKING work — inside `async def`, that blocks the
# whole event loop for the DB round-trip; as a plain `def`, FastAPI runs
# it in a worker thread instead, so it can't stall unrelated requests.
# This is the same class of bug auth.py had with bcrypt — just with a
# smaller (but still real, and cumulative under load) per-call cost.
# -------------------------------------------------------------------
@router.get("/", response_model=List[schema.EventResponse])
def get_all_events(db: Session = Depends(get_db)):
    events = db.query(models.Event).all()
    return events
 
 
# -------------------------------------------------------------------
# Get a specific Event by Event ID (PUBLIC)
# -------------------------------------------------------------------
@router.get("/{id}", response_model=schema.EventResponse)
def get_an_event(id: int, db: Session = Depends(get_db)):
 
    event = db.query(models.Event).filter(models.Event.id == id).first()
 
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail = f"Event with id: {id} not found")
 
    return event
 
 
# ----------------------------------------------------------------------------
# Get Event layout -> SVG configuration + current seat availability (PUBLIC)
# ----------------------------------------------------------------------------
@router.get("/{id}/layout", response_model=schema.EventVenueResponse)
def get_event_layout(id: int, db: Session = Depends(get_db)):
 
    event = db.query(models.Event).filter(models.Event.id == id).first()
 
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail = f"Event with id: {id} not found")
 
    return event
 
 
# -------------------------------------------------------------------
# create a new event (SELLER / ADMIN)
# -------------------------------------------------------------------
@router.post("/", response_model=schema.EventResponse, status_code=status.HTTP_201_CREATED)
def event_create(
    event:schema.EventCreate, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(oauth2.get_current_seller)
):
 
    #check if venue exist or not
    venue = db.query(models.Venue).filter(models.Venue.id == event.venue_id).first()
 
    if not venue:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail = f"venue with id: {event.venue_id} not found")
 
    new_event = models.Event(**event.model_dump())
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
 
    return new_event
 
 
# -------------------------------------------------------------------
# Update a existing event (SELLER / ADMIN)
# -------------------------------------------------------------------
@router.put("/{id}", response_model=schema.EventResponse, status_code=status.HTTP_202_ACCEPTED)
def update_event(
    id: int, 
    updated_event:schema.EventUpdate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_seller)
):
     
    query = db.query(models.Event).filter(models.Event.id == id)
    event = query.first()
 
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event with id: {id} not found"
        )
 
    update_data = updated_event.model_dump(exclude_unset=True)
    query.update(update_data, synchronize_session=False)
 
    db.commit()
    db.refresh(event)
 
    return event
 
# -------------------------------------------------------------------
# GET THE SEAT MAPPING FOR AN EVENT (PUBLIC/AUTHORISED)
# -------------------------------------------------------------------
def get_optional_user(authorization: Optional[str] = Header(None), db: Session= Depends(get_db)) -> Optional[models.User]:
    if not authorization:
        return None
 
    # handling the intentation/spaces errors
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0] != "Bearer":
        return None
 
    token = parts[1].strip()
    return  oauth2.resolve_user_from_token(token, db)
 
@router.get("/{event_id}/seats", response_model=schema.EventSeatMapResponse)
def get_event_seat_map(event_id: int, db: Session= Depends(get_db), current_user: Optional[models.User] = Depends(get_optional_user)):
 
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event with id {event_id} not found")
 
    # price-per-category for THIS event
    # e.g. both use "VIP" / "NORMAL"
    price_rows = db.query(models.Ticket_Price).filter(models.Ticket_Price.event_id == event_id).all()
 
    price_by_category = {row.section: float(row.price) for row in price_rows}
 
    # Single query: every seat in this event's venue, LEFT JOINed against
    # any ticket for THIS specific event (not tickets from other events —
    # the join condition includes event_id, so a seat's history in past
    # events never bleeds into this result).
    rows = db.query(
        models.Seat.id.label("seat_id"),
        models.Seat.row_number,
        models.Seat.seat_number,
        models.Seat.category,
        models.Ticket.id.label("ticket_id"),
        models.Ticket.status.label("ticket_status"),
        models.Ticket.user_id.label("held_by_user_id"),
    ).filter(models.Seat.venue_id == event.venue_id).outerjoin(
        models.Ticket,(models.Ticket.seat_id == models.Seat.id) & (models.Ticket.event_id == event_id)
    ).order_by(models.Seat.row_number, models.Seat.seat_number).all()
 
    current_user_id = current_user.id if current_user else None
    current_user_role = current_user.role if current_user else None
 
    seats_response = []
    for row in rows:
        if row.ticket_status is None or row.ticket_status == "CANCELLED":
            status_value = "AVAILABLE"
            ticket_id = None
            is_mine = False
        else:
            status_value = row.ticket_status  # "HELD" or "CONFIRMED"
 
            is_mine = current_user_id is not None and row.held_by_user_id == current_user_id
 
            # Only reveal the ticket_id to its owner or an admin — nobody
            ticket_id = row.ticket_id if (is_mine or current_user_role == "admin") else None
 
        seats_response.append(
                schema.SeatStatusResponse(
                    seat_id=row.seat_id,
                    row_number=row.row_number,
                    seat_number=row.seat_number,
                    category=row.category,
                    price=price_by_category.get(row.category, 0.0),
                    status=status_value,
                    ticket_id=ticket_id,
                    is_mine=is_mine,
                )
            )
 
    return schema.EventSeatMapResponse(event_id=event_id, seats=seats_response)
 
 
 
# -------------------------------------------------------------------
# Create a ticket price for an event's section (SELLER / ADMIN)
# -------------------------------------------------------------------
@router.post("/{event_id}/prices", response_model=schema.TicketPriceResponse, status_code=status.HTTP_201_CREATED)
def create_ticket_price(
    event_id: int,
    price: schema.TicketPriceBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_seller),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event with id: {event_id} not found")
 
    new_price = models.Ticket_Price(event_id=event_id, **price.model_dump())
    try:
        db.add(new_price)
        db.commit()
        db.refresh(new_price)
        return new_price
    except IntegrityError:
        # Hits Ticket_Price's uq_event_section_price constraint
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A price for section '{price.section}' already exists for this event. Use PUT to update it instead.",
        )
 
 
# -------------------------------------------------------------------
# Update an existing ticket price (SELLER / ADMIN)
# -------------------------------------------------------------------
@router.put("/prices/{price_id}", response_model=schema.TicketPriceResponse, status_code=status.HTTP_202_ACCEPTED)
def update_ticket_price(
    price_id: int,
    updated_price: schema.TicketPriceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_seller),
):
    query = db.query(models.Ticket_Price).filter(models.Ticket_Price.id == price_id)
    price = query.first()
    if not price:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket price with id: {price_id} not found")
 
    query.update(updated_price.model_dump(exclude_unset=True), synchronize_session=False)
    db.commit()
    db.refresh(price)
    return price