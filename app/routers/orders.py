import io
import uuid
import base64
import qrcode
from datetime import datetime, timezone, timedelta
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi import APIRouter, Depends,status, HTTPException
from .. import schema, oauth2, models, config, tasks
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .websocket import manager
 
 
router = APIRouter(
    prefix="/orders",
    tags=["Order"]
)
 
# ----------------------------------------------------------------------------
# Get all tickets endpoint (BUYER - see user's all ticket / ADMIN - see all)
#
# CHANGED: async def -> def. No await in this body — purely sync DB reads,
# so it was blocking the event loop for no benefit. checkout_order,
# confirm_payment, and delete_order below all genuinely `await
# manager.broadcast_to_event(...)`, so those correctly STAY async def.
# ----------------------------------------------------------------------------
@router.get("/", response_model=List[schema.TicketResponse])
def get_user_all_tickets(db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    query = db.query(models.Ticket)
    if current_user.role != "admin":
        query = query.filter(models.Ticket.user_id == current_user.id)
 
    return query.all()
 
 
# -------------------------------------------------------------------
# Get tickets by id (BUYER / ADMIN)
# -------------------------------------------------------------------
@router.get("/{id}", response_model=schema.TicketResponse)
def get_a_ticket(
    id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == id).first()
    
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail = f"Ticket with id: {id} not found")
 
    if ticket.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this ticket")
    
    return ticket
 
 
# -------------------------------------------------------------------------------------
# STEP 1: CHECKOUT -> generates a QR / payment link, does NOT confirm yet
# -------------------------------------------------------------------------------------
@router.post("/checkout", response_model=schema.CheckoutInitiateResponse)
async def checkout_order(
    payload: schema.TicketCheckoutRequest, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_buyer)
):
 
    ticket = db.query(models.Ticket).filter(models.Ticket.id == payload.ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail = f"Ticket with id: {payload.ticket_id} not found")
 
    if ticket.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to checkout this ticket")
 
    if ticket.status != "HELD":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket status is '{ticket.status}', only 'HELD' tickets can be checked out"
        )
 
    intent = db.query(models.PaymentIntent).filter(models.PaymentIntent.ticket_id == ticket.id).first()
    new_token = uuid.uuid4().hex
 
    if intent:
        intent.token = new_token
        intent.status = "PENDING"
    else:
        intent = models.PaymentIntent(ticket_id=ticket.id, token=new_token, status="PENDING")
        db.add(intent)
 
    db.commit()
    db.refresh(intent)
 
    confirm_url = f"{config.settings.FASTAPI_INTERNAL_URL}/orders/confirm-payment/{intent.token}"
 
    qr_img = qrcode.make(confirm_url)
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
 
    return schema.CheckoutInitiateResponse(
        ticket_id=ticket.id,
        payment_token=intent.token,
        confirm_url=confirm_url,
        qr_code_base64=f"data:image/png;base64,{qr_base64}",
    )
 
 
# --------------------------------------------------------------------------
# STEP 2: "SCAN" THE QR -> this is the confirm URL the QR points to.
# --------------------------------------------------------------------------
@router.get("/confirm-payment/{token}", response_class=HTMLResponse)
async def confirm_payment(token: str, db: Session = Depends(get_db)):
    intent = db.query(models.PaymentIntent).filter(models.PaymentIntent.token == token).first()
    if not intent:
        return HTMLResponse("<h2>Invalid or unknown payment link.</h2>", status_code=status.HTTP_404_NOT_FOUND)
 
    if intent.status == "COMPLETED":
        return HTMLResponse("<h2>This payment was already confirmed. Your ticket is booked!</h2>")
 
    ticket = db.query(models.Ticket).filter(models.Ticket.id == intent.ticket_id).first()
 
    if not ticket or ticket.status != "HELD":
        intent.status = "EXPIRED"
        db.commit()
        return HTMLResponse(
            "<h2>Sorry, this seat hold has expired or was released. Please pick a seat again.</h2>",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
 
    ticket.status = "CONFIRMED"
    intent.status = "COMPLETED"
    db.commit()
    db.refresh(intent)
 
    tasks.send_email_task.delay(
        ticket.user.email,
        "Your ticket is booked! 🎟️",
        f"Seat {ticket.seat_id} for event {ticket.event_id} is confirmed. "
        f"Ticket ID: {ticket.id}. See you there!",
    )
 
    await manager.broadcast_to_event(
        event_id=ticket.event_id,
        message={
            "event": "SEAT_CONFIRMED",
            "seat_id": ticket.seat_id,
            "ticket_id": ticket.id,
            "buyer_id": ticket.user_id,
            "status": "CONFIRMED"
        }
    )
 
    total_seats = db.query(models.Seat).filter(models.Seat.venue_id == ticket.event.venue_id).count()
    confirmed_count = db.query(models.Ticket).filter(models.Ticket.event_id == ticket.event_id, models.Ticket.status == "CONFIRMED").count()
 
    if total_seats > 0 and confirmed_count >= total_seats:
        await manager.broadcast_to_event(
            event_id=ticket.event_id,
            message={"event": "EVENT_SOLD_OUT", "message": f"Event {ticket.event_id} is fully booked."},
        )
 
        admins = db.query(models.User).filter(models.User.role == "admin").all()
        for admin in admins:
            tasks.send_email_task.delay(
                admin.email,
                f"Event {ticket.event_id} is SOLD OUT",
                f"All {total_seats} seats for event {ticket.event_id} have now been booked.",
            )
    return HTMLResponse(
        f"<h2>Payment successful! Seat {ticket.seat_id} is confirmed.</h2>"
        f"<p>Ticket ID: {ticket.id}</p>"
    )
 
 
# -------------------------------------------------------------------
# REFUND a CONFIRMED ticket, within a time window (BUYER / ADMIN)
# -------------------------------------------------------------------
@router.delete("/{id}/cancel") 
async def delete_order(
    id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user)
):
 
    ticket = db.query(models.Ticket).filter(models.Ticket.id == id).first()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail = f"Ticket with id: {id} not found")
 
    if ticket.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to cancel this ticket")
 
    if ticket.status == "HELD":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                            detail="This ticket is only HELD, not paid for yet. Use the WebSocket 'release_seat' action to drop a hold, not this endpoint.")
    
    if ticket.status == "CANCELLED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order is already cancelled/refunded.")
 
    event = ticket.event
    cutoff_time = event.start_time - timedelta(hours=config.settings.REFUND_CUTOFF_HOURS)
    now = datetime.now(timezone.utc)
 
    if now >= cutoff_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Refund window has closed. Refunds are only allowed up to {config.settings.REFUND_CUTOFF_HOURS} hours before the event starts.")
 
    owner_email = ticket.user.email
    seat_id = ticket.seat_id
    event_id = ticket.event_id
 
    ticket.status = "CANCELLED"
    db.commit()
 
    tasks.send_email_task.delay(
        owner_email,
        "Your refund has been processed",
        f"Your ticket for seat {seat_id} at event {event_id} has been refunded and cancelled.",
    )
    await manager.broadcast_to_event(
        event_id=event_id,
        message={
            "event": "SEAT_RELEASED",
            "seat_id": seat_id,
            "status": "CANCELLED"
        }
    )
 
    return {"detail": f"Order {id} successfully refunded and cancelled"}