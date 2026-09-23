import asyncio
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from typing import Dict, Set
import json
from .. import models, oauth2, database
from ..tasks import send_email_task
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
 
router = APIRouter(
    prefix="/ws",
    tags=["Websocket"]
)

# How long (seconds) a client has to send its auth message after connecting
AUTH_TIMEOUT_SECONDS = 10


# ============================================================================
# WEBSOCKET CONNECTION MANAGER
# ============================================================================
class ConnectionManager:
    """
    this manages the active websocked connections grouped by event_id.
    this ensure the real-time specific event's seats [HELD, CONFIRMED, RELEASE] 
    broadcasted to the particular clients viewing that event, reduces unnecessary network traffic.
    """
    def __init__(self):
        # maps: event_id -> set of active websocket client connections
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, event_id: int):
        """Accepts the incoming WebSocket connection and registers it under the event_id."""
        if event_id not in self.active_connections:  # check if the event_id do not exist in the dict (the new connection asking about)
            self.active_connections[event_id] = set() # then create a new key for that non existing event_id 
        self.active_connections[event_id].add(websocket) # map the new connection to their requested event_id whether it is created new or existed in dict 

    def disconnect(self, websocket: WebSocket, event_id: int):
        """Removes a disconnected WebSocket client from the event channel."""
        if event_id in self.active_connections:
            self.active_connections[event_id].discard(websocket)
            # remove the event if no active connections exist
            if not self.active_connections[event_id]:
                del self.active_connections[event_id]

    async def broadcast_to_event(self, event_id: int, message:dict, sender: WebSocket = None):
        """
        Broadcasts a JSON message payload to all clients connected to an event channel.
        
        Args:get_current_user_ws
            event_id: Target event ID room.
            message: Dictionary payload to serialize to JSON.
            sender: (Optional) WebSocket instance of the sender if you want to exclude them.
        """
        if event_id not in self.active_connections:
            return

        # perpare payload
        payload = json.dumps(message)

        # dead socket cleanup list
        disconnected_sockets = []

        for connection in self.active_connections[event_id]:
            #skip sending back to the socket that triggered the event
            if sender and connection == sender:
                continue
            try:
                await connection.send_text(payload)
            except Exception:
                # Socket connection died unexpectedly
                disconnected_sockets.append(connection)

        # remove stale sockets
        for dead_socket in disconnected_sockets:
            self.disconnect(dead_socket, event_id)

# Global instance of ConnectionManager
manager = ConnectionManager()      


# ============================================================================
# HELPER: WEBSOCKET AUTHENTICATION
# ============================================================================
def resolve_user_from_token(token: str, db: Session) -> models.User:
    if not token:
        print("[ws-auth] no token provided")
        return None
    try:
        payload = oauth2.jwt.decode(token, oauth2.settings.SECRET_KEY, algorithms=[oauth2.settings.ALGORITHM])
        print(f"[ws-auth] decoded payload: {payload}")
        user_id = payload.get("user_id")
        if user_id is None:
            print("[ws-auth] no 'user_id' claim in payload")
            return None
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user is None:
            print(f"[ws-auth] no user found in DB for id={user_id}")
        return user
    except Exception as e:
        print(f"[ws-auth] token decode/verify failed: {e!r}")
        return None

async def authenticate_websocket(websocket: WebSocket, db: Session) -> models.User:
    """
    Waits for the client's first message and expects it to be an auth payload:
        {"action": "auth", "token": "<JWT>"}
 
    Returns the authenticated User, or None if auth failed / timed out / was malformed.
    The connection must already be accepted before calling this.
    """
    try:
        raw = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT_SECONDS)
    except(asyncio.TimeoutError, WebSocketDisconnect, json.JSONDecodeError):
        return None

    if not isinstance(raw, dict) or raw.get("action") != "auth":
        return None
    
    token = raw.get("token")
    return resolve_user_from_token(token, db)

# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================
@router.websocket("/events/{event_id}")
async def websocket_event_seats(websocket: WebSocket, event_id: int, token: str = None, db: Session = Depends(database.get_db)):
    """
    Real-Time Seat Locking & Availability Channel.
 
    Connect with NO token in the URL:
        ws://host/ws/events/{event_id}
 
    Immediately after the connection opens, send an auth message as your
    FIRST message (this is required before anything else will be processed):
        {"action": "auth", "token": "<JWT>"}
 
    If auth is missing, invalid, or not sent within AUTH_TIMEOUT_SECONDS,
    the server closes the connection with code 1008 (policy violation).
 
    Once authenticated, connected clients receive real-time events when seats are:
      - 'SEAT_HELD': A user temporarily locks a seat.
      - 'SEAT_RELEASED': A user cancels or lets their hold expire.
      - 'SEAT_CONFIRMED': A purchase is finalized.
 
    Incoming Action Types Expected from Client (post-auth):
      - {"action": "hold_seat", "seat_id": 102, "price_paid": 50.0}
      - {"action": "release_seat", "seat_id": 102}
    """
    # 1. Accept the raw connection first (WebSocket protocol requires this
    #    before we can exchange any messages, including the auth message).
    await websocket.accept()
 
    # 2. Wait for the client's auth message and validate the token from it,
    #    instead of a token= query param (keeps it out of the URL entirely).
    try:
        current_user = await authenticate_websocket(websocket, db)
    except Exception as e:
        import traceback
        print(f"[ws-auth] UNEXPECTED exception during auth: {e!r}")
        traceback.print_exc()
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Server error during auth")
        except Exception:
            pass
        return
 
    if not current_user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized: missing/invalid auth message")
        return
 
    # 3. Register the now-authenticated connection in the event room
    await manager.connect(websocket, event_id)
 
    try:
        # Send initial status payload upon successful handshake
        await websocket.send_json({
            "event": "CONNECTED",
            "message": f"Connected to live updates for event {event_id}",
            "user_id": current_user.id
        })
 
        # 4. Main event loop: listen for incoming client actions
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            seat_id = data.get("seat_id")
 
            if not action or not seat_id:
                await websocket.send_json({"error": "Invalid payload format. 'action' and 'seat_id' is required."})
                continue

            # ----------------------------------------------------------------
            # ACTION: HOLD SEAT
            # ----------------------------------------------------------------
            if action == "hold_seat":
                # client should pass correct event_id, seat_id, and price

                # ------------------------------------------------------------
                # VALIDATION 1: does this event actually exist?
                # ------------------------------------------------------------
                event = db.query(models.Event).filter(models.Event.id == event_id).first()
                if not event:
                    await websocket.send_json({
                        "event": "ERROR",
                        "message": f"Event {event_id} not found."
                    })
                    continue

                # ------------------------------------------------------------
                # VALIDATION 2: does this seat actually exist?
                # ------------------------------------------------------------
                seat = db.query(models.Seat).filter(models.Seat.id == seat_id).first()
                if not seat:
                    await websocket.send_json({
                        "event": "ERROR",
                        "message": f"Seat {seat_id} not found."
                    })
                    continue

                # ------------------------------------------------------------
                # VALIDATION 3 (THE KEY FIX): does this seat actually belong
                # to THIS event's venue?
                # ------------------------------------------------------------
                if seat.venue_id != event.venue_id:
                    await websocket.send_json({
                        "event": "ERROR",
                        "message": f"Seat {seat_id} does not belong to this event's venue."
                    })
                    continue

                                # ------------------------------------------------------------
                # VALIDATION 4 + SERVER-COMPUTED PRICE: look up the actual
                # price for this seat's category on THIS event. The price
                # the client sends is never trusted — it's derived here from
                # Ticket_Price, which only a seller/admin can set.
                # ------------------------------------------------------------
                ticket_price = db.query(models.Ticket_Price).filter(
                    models.Ticket_Price.event_id == event_id,
                    models.Ticket_Price.section == seat.category,
                ).first()
                if not ticket_price:
                    await websocket.send_json({
                        "event": "ERROR",
                        "message": f"No price has been set for category '{seat.category}' on this event yet."
                    })
                    continue
 
                price_paid = float(ticket_price.price)


                try:
                    # Query database for existing ticket/hold
                    existing_ticket = db.query(models.Ticket).filter(models.Ticket.event_id == event_id, models.Ticket.seat_id == seat_id).with_for_update().first()

                    #case : if the seat is already held
                    if existing_ticket and existing_ticket.status in ["HELD", "CONFIRMED"]:
                        db.rollback()
                        await websocket.send_json({
                            "event": "ERROR",
                            "message": f"Seat {seat_id} is already occupied or locked."
                        })
                        continue

                    #case : if the ticket is cancelled
                    if existing_ticket and existing_ticket.status == "CANCELLED":
                        existing_ticket.user_id = current_user.id
                        existing_ticket.status = "HELD"
                        existing_ticket.price_paid = price_paid
                        existing_ticket.created_at = datetime.utcnow()
                        db.commit()
                        ticket_id = existing_ticket.id
                    
                    #case : if  new ticket is being booked
                    else:
                        new_ticket = models.Ticket(
                            event_id=event_id,
                            seat_id=seat_id,
                            user_id=current_user.id,
                            status="HELD",
                            price_paid=price_paid
                        )
                        db.add(new_ticket)
                        db.commit()
                        db.refresh(new_ticket)
                        ticket_id = new_ticket.id

                except IntegrityError:
                    db.rollback()
                    await websocket.send_json({
                        "event": "ERROR",
                        "message": f"Seat {seat_id} was just taken by someone else. Please pick another seat."
                    })
                    continue


                # Broadcast update to ALL connected users viewing this event map
                await manager.broadcast_to_event(
                    event_id=event_id,
                    message={
                        "event": "SEAT_HELD",
                        "seat_id": seat_id,
                        "ticket_id": ticket_id,
                        "held_by_user_id": current_user.id,
                        "status": "HELD"
                    }
                )

            # ----------------------------------------------------------------
            # ACTION: RELEASE SEAT
            # ----------------------------------------------------------------
            elif action == "release_seat":
                ticket = db.query(models.Ticket).filter(
                    models.Ticket.event_id == event_id,
                    models.Ticket.seat_id == seat_id,
                    models.Ticket.status == "HELD"
                ).first()

                if not ticket:
                    await websocket.send_json({
                        "event": "ERROR",
                        "message": f"No active hold found for seat {seat_id}."
                    })
                    continue

                # Authorization check: only ticket owner or admin can release via socket
                if ticket.user_id != current_user.id and current_user.role != "admin":
                    await websocket.send_json({
                        "event": "ERROR",
                        "message": "You do not have permission to release this seat lock."
                    })
                    continue

                # Capture the owner's email BEFORE cancelling
                owner_email = ticket.user.email

                ticket.status = "CANCELLED"
                db.commit()

                send_email_task(owner_email, "Your seat hold was released",
                    f"Seat {seat_id} for event {event_id} was released and is now available for others.",)


                # Broadcast release event to all listeners
                await manager.broadcast_to_event(
                    event_id=event_id,
                    message={
                        "event": "SEAT_RELEASED",
                        "seat_id": seat_id,
                        "status": "CANCELLED"
                    }
                )
    except WebSocketDisconnect:
        # Gracefully disconnect client upon drop
        manager.disconnect(websocket, event_id)