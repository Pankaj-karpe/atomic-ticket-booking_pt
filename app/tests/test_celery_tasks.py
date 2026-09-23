"""
Tests for background jobs in app/tasks.py.
 
These call the task FUNCTIONS DIRECTLY (e.g. tasks.release_expired_holds())
rather than via .delay(). With Celery in eager mode (set in conftest.py),
.delay() would ALSO run synchronously — but calling the plain function
directly is simpler for a unit test and skips Celery's machinery entirely.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
 
from app import models, tasks, utils, oauth2

def test_release_expired_holds_cancels_stale_ticket(seeded_event, buyer, db):
    buyer_user, _ = buyer
    event_id = seeded_event["event"].id
    seat_id = seeded_event["seat1"].id
 
    # Backdate created_at so this ticket looks like it's been HELD far
    # longer than HOLD_EXPIRY_MINUTES (15, from .env.test) allows.
    stale_ticket = models.Ticket(
        event_id=event_id, seat_id=seat_id, user_id=buyer_user.id,
        status="HELD", price_paid=100.0,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(stale_ticket)
    db.commit()
    db.refresh(stale_ticket)

    # release_expired_holds() calls `requests.post(...)` to hit the internal
    # broadcast endpoint over real HTTP — there's no live server to hit in
    # a unit test, so we patch that call out and just verify it WAS
    # attempted with the right event_id/seat_ids.
    with patch("app.tasks.requests.post") as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        tasks.release_expired_holds()
 
        mock_post.assert_called_once()
        called_url = mock_post.call_args.args[0]
        assert f"/internal/broadcast-release/{event_id}" in called_url
        assert mock_post.call_args.kwargs["json"]["seat_ids"] == [seat_id]
 
    db.refresh(stale_ticket)
    assert stale_ticket.status == "CANCELLED"

def test_release_expired_holds_ignores_recent_holds(seeded_event, buyer, db):
    buyer_user, _ = buyer
    fresh_ticket = models.Ticket(
        event_id=seeded_event["event"].id, seat_id=seeded_event["seat1"].id,
        user_id=buyer_user.id, status="HELD", price_paid=100.0,
        created_at=datetime.now(timezone.utc),  # held just now — should NOT expire
    )
    db.add(fresh_ticket)
    db.commit()
    db.refresh(fresh_ticket)
 
    with patch("app.tasks.requests.post"):
        tasks.release_expired_holds()
 
    db.refresh(fresh_ticket)
    assert fresh_ticket.status == "HELD"  # untouched

def test_release_expired_holds_sends_email_to_owner(seeded_event, buyer, db, mock_smtp):
    buyer_user, _ = buyer
    stale_ticket = models.Ticket(
        event_id=seeded_event["event"].id, seat_id=seeded_event["seat1"].id,
        user_id=buyer_user.id, status="HELD", price_paid=100.0,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(stale_ticket)
    db.commit()
 
    with patch("app.tasks.requests.post"):
        tasks.release_expired_holds()
 
    # mock_smtp is the mocked `server` object from conftest.py's autouse
    # fixture. send_email_task.delay(...) inside release_expired_holds runs
    # synchronously (Celery eager mode), so by this point it's already fired.
    mock_smtp.send_message.assert_called_once()
    sent_message = mock_smtp.send_message.call_args.args[0]
    assert sent_message["To"] == buyer_user.email
    assert "expired" in sent_message["Subject"].lower()

def test_send_email_task_skips_silently_without_smtp_config(monkeypatch):
    """If SMTP_USER/SMTP_PASSWORD aren't configured, send_email_task should
    log a warning and return WITHOUT raising — email being unconfigured
    should never crash whatever called it."""
    monkeypatch.setattr("app.tasks.settings.SMTP_USER", None)
    monkeypatch.setattr("app.tasks.settings.SMTP_PASSWORD", None)
 
    tasks.send_email_task("someone@test.com", "Subject", "Body")  # must not raise
 
 
def test_confirming_last_seat_triggers_sold_out_notification(client, db, mock_smtp):
    """
    Full integration test: a venue with exactly 1 seat. Confirming that
    single ticket's payment makes it the LAST seat sold, which should
    trigger the EVENT_SOLD_OUT broadcast plus an email to every admin —
    in addition to the normal "your ticket is booked" email to the buyer.
    """
    venue = models.Venue(name="Tiny Venue", total_capacity=1)
    db.add(venue)
    db.commit()
    db.refresh(venue)
 
    seat = models.Seat(venue_id=venue.id, category="NORMAL", row_number=1, seat_number="A1")
    db.add(seat)
    db.commit()
    db.refresh(seat)
 
    event = models.Event(venue_id=venue.id, title="Sellout Show", start_time=datetime.now(timezone.utc) + timedelta(days=30))
    db.add(event)
    db.commit()
    db.refresh(event)
 
    buyer_user = models.User(email="solobuyer@test.com", hashed_pwd=utils.hash("pass12345"), role="buyer")
    admin_user = models.User(email="soloadmin@test.com", hashed_pwd=utils.hash("pass12345"), role="admin")
    db.add_all([buyer_user, admin_user])
    db.commit()
    db.refresh(buyer_user)
 
    ticket = models.Ticket(event_id=event.id, seat_id=seat.id, user_id=buyer_user.id, status="HELD", price_paid=50.0)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
 
    token = oauth2.create_access_token({"user_id": buyer_user.id, "role": buyer_user.role})
    headers = {"Authorization": f"Bearer {token}"}
 
    checkout = client.post("/orders/checkout", json={"ticket_id": ticket.id}, headers=headers)
    payment_token = checkout.json()["payment_token"]
 
    response = client.get(f"/orders/confirm-payment/{payment_token}")
    assert response.status_code == 200
 
    db.refresh(ticket)
    assert ticket.status == "CONFIRMED"
 
    # 2 emails: 1 buyer confirmation + 1 admin sold-out notice.
    assert mock_smtp.send_message.call_count == 2
    sent_subjects = [call.args[0]["Subject"] for call in mock_smtp.send_message.call_args_list]
    assert any("booked" in s.lower() for s in sent_subjects)
    assert any("sold out" in s.lower() for s in sent_subjects)