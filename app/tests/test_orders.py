"""
Tests for /orders: checkout (QR/payment-intent creation), the confirm-payment
callback, listing tickets, and the refund/cancel endpoint.
"""

from datetime import datetime, timedelta, timezone
from app import models


def _hold_a_seat(db, event_id, seat_id, user_id, price=100.0):
    """Seed a HELD ticket directly in the DB. These tests are about
    checkout/confirm/refund — NOT about the hold_seat flow itself, which
    is already covered end-to-end in test_websocket.py."""
    ticket = models.Ticket(event_id=event_id, seat_id=seat_id, user_id=user_id, status="HELD", price_paid=price)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


# ----------------------------------------------------------------------
# CHECKOUT (step 1: generates QR/payment intent, does NOT confirm yet)
# ----------------------------------------------------------------------

def test_checkout_generates_qr_and_payment_intent(client, seeded_event, buyer, db):
    buyer_user, headers = buyer
    ticket = _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)

    response = client.post("/orders/checkout", json={"ticket_id": ticket.id}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["ticket_id"] == ticket.id
    assert body["confirm_url"].endswith(f"/orders/confirm-payment/{body['payment_token']}")
    assert body["qr_code_base64"].startswith("data:image/png;base64,")

    # Checkout must NOT confirm the ticket yet — only /confirm-payment does.
    db.refresh(ticket)
    assert ticket.status == "HELD"

    intent = db.query(models.PaymentIntent).filter(models.PaymentIntent.ticket_id == ticket.id).first()
    assert intent is not None
    assert intent.status == "PENDING"
    assert intent.token == body["payment_token"]


def test_checkout_rejects_non_held_ticket(client, seeded_event, buyer, db):
    buyer_user, headers = buyer
    ticket = _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)
    ticket.status = "CONFIRMED"
    db.commit()

    response = client.post("/orders/checkout", json={"ticket_id": ticket.id}, headers=headers)
    assert response.status_code == 400


def test_checkout_forbidden_for_non_owner(client, seeded_event, buyer, make_user, db):
    buyer_user, _ = buyer
    ticket = _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)

    _, other_headers = make_user("nottheowner@test.com", "buyer")
    response = client.post("/orders/checkout", json={"ticket_id": ticket.id}, headers=other_headers)
    assert response.status_code == 403


def test_checkout_unknown_ticket_404(client, buyer_headers):
    response = client.post("/orders/checkout", json={"ticket_id": 99999}, headers=buyer_headers)
    assert response.status_code == 404


# ----------------------------------------------------------------------
# CONFIRM PAYMENT (step 2: the QR's target URL — "scanning" it)
# ----------------------------------------------------------------------

def test_confirm_payment_flips_ticket_to_confirmed(client, seeded_event, buyer, db):
    buyer_user, headers = buyer
    ticket = _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)

    checkout = client.post("/orders/checkout", json={"ticket_id": ticket.id}, headers=headers)
    token = checkout.json()["payment_token"]

    # This is a PUBLIC GET — it's what the QR/redirect hits, no auth header.
    response = client.get(f"/orders/confirm-payment/{token}")
    assert response.status_code == 200
    assert "Payment successful" in response.text

    db.refresh(ticket)
    assert ticket.status == "CONFIRMED"

    intent = db.query(models.PaymentIntent).filter(models.PaymentIntent.token == token).first()
    assert intent.status == "COMPLETED"


def test_confirm_payment_twice_is_idempotent(client, seeded_event, buyer, db):
    buyer_user, headers = buyer
    ticket = _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)
    checkout = client.post("/orders/checkout", json={"ticket_id": ticket.id}, headers=headers)
    token = checkout.json()["payment_token"]

    first = client.get(f"/orders/confirm-payment/{token}")
    second = client.get(f"/orders/confirm-payment/{token}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert "already confirmed" in second.text.lower()


def test_confirm_payment_unknown_token_404(client):
    response = client.get("/orders/confirm-payment/not-a-real-token")
    assert response.status_code == 404


def test_confirm_payment_rejects_if_hold_no_longer_active(client, seeded_event, buyer, db):
    buyer_user, headers = buyer
    ticket = _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)
    checkout = client.post("/orders/checkout", json={"ticket_id": ticket.id}, headers=headers)
    token = checkout.json()["payment_token"]

    # Simulate the hold expiring/being released BEFORE the QR gets scanned
    # (e.g. Celery's release_expired_holds job beat the user to it).
    ticket.status = "CANCELLED"
    db.commit()

    response = client.get(f"/orders/confirm-payment/{token}")
    assert response.status_code == 400
    assert "expired" in response.text.lower()


# ----------------------------------------------------------------------
# LISTING TICKETS
# ----------------------------------------------------------------------

def test_get_my_tickets_only_shows_own_tickets(client, seeded_event, buyer, make_user, db):
    buyer_user, buyer_headers = buyer
    other_user, _ = make_user("someoneelse@test.com", "buyer")

    _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)
    _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat2"].id, other_user.id)

    response = client.get("/orders/", headers=buyer_headers)
    assert response.status_code == 200
    tickets = response.json()
    assert len(tickets) == 1
    assert tickets[0]["user_id"] == buyer_user.id


def test_admin_sees_all_tickets(client, seeded_event, buyer, admin, db):
    buyer_user, _ = buyer
    _, admin_headers = admin
    _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)

    response = client.get("/orders/", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


# ----------------------------------------------------------------------
# REFUND / CANCEL (CONFIRMED tickets only, within REFUND_CUTOFF_HOURS)
# ----------------------------------------------------------------------

def test_refund_confirmed_ticket_within_window(client, seeded_event, buyer, db):
    buyer_user, headers = buyer
    ticket = _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)
    ticket.status = "CONFIRMED"
    db.commit()
    # seeded_event's start_time is 30 days out — well outside the default
    # 24h refund cutoff, so this refund should succeed.

    response = client.delete(f"/orders/{ticket.id}/cancel", headers=headers)
    assert response.status_code == 200

    db.refresh(ticket)
    assert ticket.status == "CANCELLED"


def test_refund_rejected_outside_window(client, seeded_event, buyer, db):
    buyer_user, headers = buyer
    ticket = _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)
    ticket.status = "CONFIRMED"
    db.commit()

    # Move the event's start_time to just 1 hour away — inside the default
    # 24h cutoff, so the refund should now be rejected.
    event = seeded_event["event"]
    event.start_time = datetime.now(timezone.utc) + timedelta(hours=1)
    db.commit()

    response = client.delete(f"/orders/{ticket.id}/cancel", headers=headers)
    assert response.status_code == 400
    assert "refund window" in response.json()["detail"].lower()


def test_refund_rejects_held_ticket(client, seeded_event, buyer, db):
    """A HELD (not-yet-paid) ticket should be rejected here and pointed at
    the WebSocket release_seat action instead — this endpoint is refund-only."""
    buyer_user, headers = buyer
    ticket = _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)

    response = client.delete(f"/orders/{ticket.id}/cancel", headers=headers)
    assert response.status_code == 400
    assert "release_seat" in response.json()["detail"]


def test_refund_rejects_already_cancelled(client, seeded_event, buyer, db):
    buyer_user, headers = buyer
    ticket = _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)
    ticket.status = "CANCELLED"
    db.commit()

    response = client.delete(f"/orders/{ticket.id}/cancel", headers=headers)
    assert response.status_code == 400


def test_refund_forbidden_for_non_owner(client, seeded_event, buyer, make_user, db):
    buyer_user, _ = buyer
    ticket = _hold_a_seat(db, seeded_event["event"].id, seeded_event["seat1"].id, buyer_user.id)
    ticket.status = "CONFIRMED"
    db.commit()

    _, other_headers = make_user("notowner2@test.com", "buyer")
    response = client.delete(f"/orders/{ticket.id}/cancel", headers=other_headers)
    assert response.status_code == 403