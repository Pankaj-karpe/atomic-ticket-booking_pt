"""
Tests for GET /admin/dashboard — revenue, ticket-count, and active-holds
aggregation SQL. We seed EXACT known values and assert EXACT numbers back,
not just "some number > 0" — that way a regression in the SUM/COUNT/filter
logic gets caught instead of silently passing.
"""
 
from app import models
 
 
def test_dashboard_forbidden_for_buyer(client, buyer_headers):
    response = client.get("/admin/dashboard", headers=buyer_headers)
    assert response.status_code == 403

def test_dashboard_forbidden_without_auth(client):
    response = client.get("/admin/dashboard")
    assert response.status_code == 401
 
 
def test_dashboard_math_matches_seeded_data(client, seeded_event, buyer, admin, db):
    buyer_user, _ = buyer
    _, admin_headers = admin
    event_id = seeded_event["event"].id
 
    # 2 CONFIRMED tickets: 100.00 + 250.00 = 350.00 revenue, 2 sold.
    t1 = models.Ticket(event_id=event_id, seat_id=seeded_event["seat1"].id, user_id=buyer_user.id, status="CONFIRMED", price_paid=100.00)
    t2 = models.Ticket(event_id=event_id, seat_id=seeded_event["seat2"].id, user_id=buyer_user.id, status="CONFIRMED", price_paid=250.00)
    db.add_all([t1, t2])
    db.commit()
 
    response = client.get("/admin/dashboard", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
 
    assert body["total_revenue"] == 350.0
    assert body["total_tickets_sold"] == 2
    assert body["active_holds"] == 0
 
    assert len(body["revenue_per_event"]) == 1
    event_row = body["revenue_per_event"][0]
    assert event_row["event_id"] == event_id
    assert event_row["tickets_sold"] == 2
    assert event_row["revenue"] == 350.0
 
 
def test_dashboard_held_tickets_dont_count_as_revenue(client, seeded_event, buyer, admin, db):
    buyer_user, _ = buyer
    _, admin_headers = admin
    event_id = seeded_event["event"].id
 
    # 1 HELD (counts toward active_holds, NOT revenue) + 1 CONFIRMED (counts
    # toward revenue, NOT active_holds).
    held = models.Ticket(event_id=event_id, seat_id=seeded_event["seat1"].id, user_id=buyer_user.id, status="HELD", price_paid=100.00)
    confirmed = models.Ticket(event_id=event_id, seat_id=seeded_event["seat2"].id, user_id=buyer_user.id, status="CONFIRMED", price_paid=250.00)
    db.add_all([held, confirmed])
    db.commit()
 
    response = client.get("/admin/dashboard", headers=admin_headers)
    body = response.json()
 
    assert body["active_holds"] == 1
    assert body["total_revenue"] == 250.0
    assert body["total_tickets_sold"] == 1
 
 
def test_dashboard_zero_state_is_zero_not_none(client, admin_headers):
    """With no tickets in the DB at all, revenue/counts should be plain
    zero — not null/None (func.coalesce(...) in admin.py exists exactly
    to guarantee this, since SQL SUM() of zero rows is NULL by default)."""
    response = client.get("/admin/dashboard", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_revenue"] == 0.0
    assert body["total_tickets_sold"] == 0
    assert body["active_holds"] == 0
    assert body["revenue_per_event"] == []