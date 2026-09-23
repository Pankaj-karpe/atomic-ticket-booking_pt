

"""
Venue and Seat management. This was the actual gap: there was no way to
create a Venue or its Seats through the API at all — event.py could create
Events, but only if a Venue already existed, and nothing could ever create
that Venue or populate its seats. Tickets and PaymentIntents are correctly
NOT here — those are meant to be created automatically by the booking flow
(hold_seat / checkout), not manually by a seller.
"""
 
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .. import schema, oauth2, models
from ..database import get_db
 
router = APIRouter(
    prefix="/venues",
    tags=["Venues"],
)
 
 
# -------------------------------------------------------------------
# Create a venue (SELLER / ADMIN)
# -------------------------------------------------------------------
@router.post("/", response_model=schema.VenueResponse, status_code=status.HTTP_201_CREATED)
def create_venue(
    venue: schema.VenueCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_seller),
):
    new_venue = models.Venue(**venue.model_dump())
    db.add(new_venue)
    db.commit()
    db.refresh(new_venue)
    return new_venue
 
 
# -------------------------------------------------------------------
# List all venues (PUBLIC)
# -------------------------------------------------------------------
@router.get("/", response_model=List[schema.VenueResponse])
def get_all_venues(db: Session = Depends(get_db)):
    return db.query(models.Venue).all()
 
 
# -------------------------------------------------------------------
# Get a single venue (PUBLIC)
# -------------------------------------------------------------------
@router.get("/{id}", response_model=schema.VenueResponse)
def get_venue(id: int, db: Session = Depends(get_db)):
    venue = db.query(models.Venue).filter(models.Venue.id == id).first()
    if not venue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Venue with id: {id} not found")
    return venue
 
 
# -------------------------------------------------------------------
# Update a venue (SELLER / ADMIN)
# -------------------------------------------------------------------
@router.put("/{id}", response_model=schema.VenueResponse, status_code=status.HTTP_202_ACCEPTED)
def update_venue(
    id: int,
    updated_venue: schema.VenueUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_seller),
):
    query = db.query(models.Venue).filter(models.Venue.id == id)
    venue = query.first()
    if not venue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Venue with id: {id} not found")
 
    query.update(updated_venue.model_dump(exclude_unset=True), synchronize_session=False)
    db.commit()
    db.refresh(venue)
    return venue
 
 
# -------------------------------------------------------------------
# Create ONE seat in a venue (SELLER / ADMIN)
#
# Note: uses schema.SeatBase (not SeatCreate) as the request body, since
# venue_id already comes from the URL path — repeating it in the body too
# would just invite a mismatch between the two.
# -------------------------------------------------------------------
@router.post("/{venue_id}/seats", response_model=schema.SeatResponse, status_code=status.HTTP_201_CREATED)
def create_seat(
    venue_id: int,
    seat: schema.SeatBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_seller),
):
    venue = db.query(models.Venue).filter(models.Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Venue with id: {venue_id} not found")

    # Enforce total_capacity as a real ceiling, not just a declared number —
    # otherwise a venue could end up with more Seat rows than its stated capacity
    existing_seat_count = db.query(models.Seat).filter(models.Seat.venue_id == venue_id).count()
    if existing_seat_count + 1 > venue.total_capacity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Venue capacity ({venue.total_capacity}) already reached — {existing_seat_count} seats exist.",
        )

    
    new_seat = models.Seat(venue_id=venue_id, **seat.model_dump())
    try:
        db.add(new_seat)
        db.commit()
        db.refresh(new_seat)
        return new_seat
    except IntegrityError:
        # Hits Seat's uq_venue_seat constraint (venue_id, category, row_number, seat_number)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A seat with this category/row/seat_number already exists in this venue.",
        )
 
 
# -------------------------------------------------------------------
# Create MANY seats in a venue at once (SELLER / ADMIN)
#
# This is the practically useful one — a real venue has dozens/hundreds
# of seats, and creating them one HTTP call at a time isn't realistic.
# -------------------------------------------------------------------
@router.post("/{venue_id}/seats/bulk", response_model=List[schema.SeatResponse], status_code=status.HTTP_201_CREATED)
def create_seats_bulk(
    venue_id: int,
    payload: schema.SeatBulkCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_seller),
):
    venue = db.query(models.Venue).filter(models.Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Venue with id: {venue_id} not found")


    existing_seat_count = db.query(models.Seat).filter(models.Seat.venue_id == venue_id).count()
    if existing_seat_count + len(payload.seats) > venue.total_capacity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Adding {len(payload.seats)} seats would exceed this venue's capacity "
                f"({venue.total_capacity}) — {existing_seat_count} seats already exist."
            ),
        )

    
    new_seats = [models.Seat(venue_id=venue_id, **seat.model_dump()) for seat in payload.seats]
    try:
        db.add_all(new_seats)
        db.commit()
        for seat in new_seats:
            db.refresh(seat)
        return new_seats
    except IntegrityError:
        # If ANY seat in the batch collides, the WHOLE batch rolls back —
        # simpler to reason about than partial success, and lets the
        # caller fix their list and resend the exact same batch cleanly.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more seats in this batch already exist (duplicate category/row/seat_number in this venue).",
        )
 
 
# -------------------------------------------------------------------
# List all seats in a venue (PUBLIC) — the STATIC seat list, not live
# per-event status. For live HELD/CONFIRMED/AVAILABLE status, use
# GET /events/{event_id}/seats instead.
# -------------------------------------------------------------------
@router.get("/{venue_id}/seats", response_model=List[schema.SeatResponse])
def get_venue_seats(venue_id: int, db: Session = Depends(get_db)):
    venue = db.query(models.Venue).filter(models.Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Venue with id: {venue_id} not found")
 
    return db.query(models.Seat).filter(models.Seat.venue_id == venue_id).all()
 