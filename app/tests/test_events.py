"""
Tests for the /events router: public listing/fetching, the (static) layout
endpoint, seller/admin-only create+update, and the (live) seat-map endpoint.
"""
from datetime import datetime, timedelta, timezone
from app import models


def test_list_events_public(client, seeded_event):
    response = client.get("/events/")
    assert response.status_code == 200
    titles = [e["title"] for e in response.json()]
    assert "Test Concert" in titles

def test_get_event_by_id(client, seeded_event):
    event_id = seeded_event["event"].id
    response = client.get(f"/events/{event_id}")
    assert response.status_code == 200
    assert response.json()["id"] == event_id

def test_get_event_by_id_404(client):
    response = client.get("/events/99999")
    assert response.status_code == 404

def test_get_event_layout_returns_static_structure_only(client, seeded_event):
    event_id = seeded_event["event"].id
    response = client.get(f"/events/{event_id}/layout")
    assert response.status_code == 200
    body = response.json()
    assert body["venue"]["name"] == "Test Arena"
    assert len(body["ticket_prices"]) == 2
    assert "seats" not in body 

def test_create_event_forbidden_for_buyer(client, seeded_event, buyer_headers):
    response = client.post("/events/", json={
        "venue_id": seeded_event["event"].id,
        "title": "buyer Cannot Make This",
        "start_time": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    }, headers=buyer_headers)
    assert response.status_code == 403

def test_create_event_allowed_for_seller(client, seeded_event, seller_headers):
    response = client.post("/events/", json={
        "venue_id": seeded_event["event"].id,
        "title": "Seller's New Show",
        "start_time": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    }, headers=seller_headers)

    assert response.status_code == 201
    assert response.json()["title"] == "Seller's New Show"

def test_create_event_unknown_venue_404(client, seller_headers):
    response = client.post("/events/", json={
        "venue_id": 99999,
        "title": "Ghost Venue Show",
        "start_time": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
    }, headers=seller_headers)
    assert response.status_code == 404

def test_update_event(client, seeded_event, seller_headers):
    event_id = seeded_event["event"].id
    response = client.put(f"/events/{event_id}", json={"title": "Renamed Concert"}, headers=seller_headers)
    assert response.status_code == 202
    assert response.json()["title"] == "Renamed Concert"

def test_seat_map_all_available_before_any_holds(client, seeded_event):
    event_id = seeded_event["event"].id
    response = client.get(f"/events/{event_id}/seats")
    assert response.status_code == 200

    body = response.json()
    assert body["event_id"] == event_id
    assert len(body["seats"]) == 2
    for seat in body["seats"]:
        assert seat["status"] == "AVAILABLE"
        assert seat["ticket_id"] is None
        assert seat["is_mine"] is False

def test_seat_map_shows_is_mine_only_to_the_holder(client, seeded_event, buyer, buyer_headers, db):
    seat_id = seeded_event["seat1"].id
    event_id = seeded_event["event"].id
    buyer_user, _ = buyer
 
    # Seed a HELD ticket directly — this file tests the REST seat-map
    # endpoint, not the hold flow itself (that's in test_websocket.py).
    ticket = models.Ticket(
        event_id=event_id, seat_id=seat_id, user_id=buyer_user.id,
        status="HELD", price_paid=100.0,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
 
    # As the holder: sees is_mine=True and the real ticket_id
    mine_response = client.get(f"/events/{event_id}/seats", headers=buyer_headers)
    mine_seat = next(s for s in mine_response.json()["seats"] if s["seat_id"] == seat_id)
    assert mine_seat["status"] == "HELD"
    assert mine_seat["is_mine"] is True
    assert mine_seat["ticket_id"] == ticket.id
 
    # As nobody (anonymous, no Authorization header): sees HELD, but the
    # ticket_id is hidden and is_mine is False.
    anon_response = client.get(f"/events/{event_id}/seats")
    anon_seat = next(s for s in anon_response.json()["seats"] if s["seat_id"] == seat_id)
    assert anon_seat["status"] == "HELD"
    assert anon_seat["is_mine"] is False
    assert anon_seat["ticket_id"] is None
 