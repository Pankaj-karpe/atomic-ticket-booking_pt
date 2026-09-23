"""
Tests for the /ws/events/{event_id} WebSocket endpoint.
FastAPI's TestClient supports `client.websocket_connect(url)` as a context
manager that drives a real WebSocket handshake in-process — no separate
server process needed. We manually replicate the exact protocol your real
clients (Postman) use: connect -> send {"action":"auth",...} -> wait for
CONNECTED -> then send hold_seat/release_seat messages.
"""
import pytest
from starlette.websockets import WebSocketDisconnect
from app import models

def _token_from(headers: dict) -> str:
    """Headers store 'Authorization': 'Bearer <token>' — pull the raw token
    back out, since websocket auth takes the token directly, not a header."""
    return headers["Authorization"].split(" ")[1]

def test_ws_rejects_connection_without_valid_auth_message(client, seeded_event):
    event_id = seeded_event["event"].id
    with client.websocket_connect(f"/ws/events/{event_id}") as ws:
        # First message is NOT a valid {"action": "auth", ...} payload.
        ws.send_json({"action": "hold_seat", "seat_id": 1})
        # The server should close the connection (1008) instead of
        # processing it — receive_json() on a closed socket raises.
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

def test_ws_auth_success_returns_connected_event(client, seeded_event, buyer):
    _, headers = buyer
    event_id = seeded_event["event"].id
    with client.websocket_connect(f"/ws/events/{event_id}") as ws:
        ws.send_json({"action": "auth", "token": _token_from(headers)})
        response = ws.receive_json()
        assert response["event"] == "CONNECTED"
        assert response["message"] == f"Connected to live updates for event {event_id}"

def test_ws_hold_seat_success(client, seeded_event, buyer, db):
    _, headers = buyer
    event_id = seeded_event["event"].id
    seat_id = seeded_event["seat1"].id

    with client.websocket_connect(f"/ws/events/{event_id}") as ws:
        ws.send_json({"action": "auth", "token": _token_from(headers)})
        ws.receive_json()

        ws.send_json({"action": "hold_seat", "seat_id": seat_id, "price_paid": 100.0})
        broadcast = ws.receive_json()

        assert broadcast["event"] == "SEAT_HELD"
        assert broadcast["seat_id"] == seat_id
        assert broadcast["status"] == "HELD"

     # Confirm the DB actually reflects the hold, not just the broadcast message.
    ticket = db.query(models.Ticket).filter(models.Ticket.id == broadcast["ticket_id"]).first()
    assert ticket is not None
    assert ticket.status == "HELD"

def test_ws_hold_seat_already_taken_returns_error(client, seeded_event, buyer, make_user):
    _, buyer_headers = buyer
    _, other_headers = make_user("otherbuyer@test.com", "buyer")
    event_id = seeded_event["event"].id
    seat_id = seeded_event["seat1"].id

    with client.websocket_connect(f"/ws/events/{event_id}") as ws1:
        ws1.send_json({"action": "auth", "token": _token_from(buyer_headers)})
        ws1.receive_json()  # CONNECTED
        ws1.send_json({"action": "hold_seat", "seat_id": seat_id, "price_paid": 100.0})
        ws1.receive_json()  # SEAT_HELD

        with client.websocket_connect(f"/ws/events/{event_id}") as ws2:
            ws2.send_json({"action": "auth", "token": _token_from(other_headers)})
            ws2.receive_json()  # CONNECTED
            ws2.send_json({"action": "hold_seat", "seat_id": seat_id, "price_paid": 100.0})
            error_response = ws2.receive_json()

            assert error_response["event"] == "ERROR"
            assert "already occupied" in error_response["message"]

def test_ws_release_seat_manual(client, seeded_event, buyer, db):
    _, headers = buyer
    event_id = seeded_event["event"].id
    seat_id = seeded_event["seat1"].id

    with client.websocket_connect(f"/ws/events/{event_id}") as ws:
        ws.send_json({"action": "auth", "token": _token_from(headers)})
        ws.receive_json() # CONNECTED

        ws.send_json({"action": "hold_seat", "seat_id": seat_id, "price_paid": 100.0})
        held = ws.receive_json()
        ticket_id = held["ticket_id"]

        ws.send_json({"action": "release_seat", "seat_id": seat_id})
        released = ws.receive_json()

        assert released["event"] == "SEAT_RELEASED"
        assert released["seat_id"] == seat_id

    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    assert ticket.status == "CANCELLED"

def test_ws_release_seat_not_owner_forbidden(client, seeded_event, buyer, make_user):
    _, buyer_headers = buyer
    _, other_headers = make_user("notowner@test.com", "buyer")
    event_id = seeded_event["event"].id
    seat_id = seeded_event["seat1"].id
 
    with client.websocket_connect(f"/ws/events/{event_id}") as ws1:
        ws1.send_json({"action": "auth", "token": _token_from(buyer_headers)})
        ws1.receive_json()
        ws1.send_json({"action": "hold_seat", "seat_id": seat_id, "price_paid": 100.0})
        ws1.receive_json()
 
        with client.websocket_connect(f"/ws/events/{event_id}") as ws2:
            ws2.send_json({"action": "auth", "token": _token_from(other_headers)})
            ws2.receive_json()
            ws2.send_json({"action": "release_seat", "seat_id": seat_id})
            response = ws2.receive_json()
 
            assert response["event"] == "ERROR"
            assert "permission" in response["message"].lower()