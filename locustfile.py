"""
Comprehensive load test covering every REST endpoint in the project.

NOT covered here (by design — Locust's HttpUser only speaks HTTP, not
WebSocket): hold_seat, release_seat, and anything downstream of them
(checkout, confirm-payment, refund all need an actual HELD/CONFIRMED
ticket to exist first, which can only be created via the WebSocket).
That flow is load-tested separately in test_ws_concurrency.py.

Run with:
    locust -f locustfile.py --host http://127.0.0.1:8000

Then open http://localhost:8089 to configure user count / spawn rate.
"""

import random
import string
from locust import HttpUser, task, between


def _random_email() -> str:
    """A fresh, unique email per signup — avoids every simulated user
    colliding on the same 'already registered' 400 response."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"loadtest_{suffix}@test.com"


# ============================================================================
# BUYER-LIKE TRAFFIC: mostly reads (browsing events, seat maps, own tickets),
# with occasional signups. This is the dominant traffic pattern on a real
# ticketing site — most visitors are browsing, not writing.
# ============================================================================
class BuyerUser(HttpUser):
    wait_time = between(0.1, 0.5)
    weight = 6  # most simulated users are this type

    def on_start(self):
        """Each simulated buyer signs up as a brand-new user, then logs in —
        exercising both endpoints, and giving each virtual user its own
        valid JWT for the authenticated tasks below."""
        self.email = _random_email()
        self.password = "loadtest123"

        self.client.post("/signup", json={
            "email": self.email,
            "password": self.password,
            "role": "buyer",
        })

        response = self.client.post("/login", data={
            "username": self.email,
            "password": self.password,
        })
        if response.status_code == 200:
            token = response.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {token}"}
        else:
            self.headers = {}

    @task(5)
    def list_events(self):
        self.client.get("/events/", name="/events/ [list]")

    @task(4)
    def view_event_seat_map(self):
        # Assumes event_id=1 exists — seed it first (see venue/event/price
        # setup steps from earlier in this conversation).
        self.client.get("/events/2/seats", headers=self.headers, name="/events/{id}/seats")

    @task(3)
    def view_specific_event(self):
        self.client.get("/events/2", name="/events/{id}")

    @task(2)
    def view_event_layout(self):
        self.client.get("/events/2/layout", name="/events/{id}/layout")

    @task(3)
    def list_venues(self):
        self.client.get("/venues/", name="/venues/ [list]")

    @task(1)
    def view_venue_seats(self):
        self.client.get("/venues/2/seats", name="/venues/{id}/seats")

    @task(2)
    def view_my_tickets(self):
        self.client.get("/orders/", headers=self.headers, name="/orders/ [my tickets]")


# ============================================================================
# SELLER-LIKE TRAFFIC: the write-heavy side — creating venues, seats,
# events, and prices. Lower weight since this is rarer in real usage
# (a handful of organizers vs. thousands of browsing buyers).
# ============================================================================
class SellerUser(HttpUser):
    wait_time = between(0.5, 1.5)
    weight = 1

    def on_start(self):
        self.email = _random_email()
        self.password = "loadtest123"

        self.client.post("/signup", json={
            "email": self.email,
            "password": self.password,
            "role": "seller",
        })

        response = self.client.post("/login", data={
            "username": self.email,
            "password": self.password,
        })
        if response.status_code == 200:
            token = response.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {token}"}
        else:
            self.headers = {}

    @task(3)
    def create_venue(self):
        self.client.post(
            "/venues/",
            json={"name": f"Load Test Venue {random.randint(1, 100000)}", "total_capacity": 10},
            headers=self.headers,
            name="/venues/ [create]",
        )

    @task(2)
    def create_venue_then_seats_then_event_then_price(self):
        """One full write-path chain: venue -> seats -> event -> price.
        Exercises all four write endpoints together, the way a real
        seller onboarding a new event actually would."""
        venue_resp = self.client.post(
            "/venues/",
            json={"name": f"Chain Venue {random.randint(1, 100000)}", "total_capacity": 5},
            headers=self.headers,
            name="/venues/ [create, chained]",
        )
        if venue_resp.status_code != 201:
            return
        venue_id = venue_resp.json()["id"]

        self.client.post(
            f"/venues/{venue_id}/seats/bulk",
            json={"seats": [
                {"category": "NORMAL", "row_number": 1, "seat_number": "A1"},
                {"category": "NORMAL", "row_number": 1, "seat_number": "A2"},
            ]},
            headers=self.headers,
            name="/venues/{id}/seats/bulk [chained]",
        )

        event_resp = self.client.post(
            "/events/",
            json={
                "venue_id": venue_id,
                "title": f"Load Test Event {random.randint(1, 100000)}",
                "start_time": "2026-12-31T20:00:00Z",
            },
            headers=self.headers,
            name="/events/ [create, chained]",
        )
        if event_resp.status_code != 201:
            return
        event_id = event_resp.json()["id"]

        self.client.post(
            f"/events/{event_id}/prices",
            json={"section": "NORMAL", "price": 500.0},
            headers=self.headers,
            name="/events/{id}/prices [chained]",
        )

    @task(1)
    def update_a_venue(self):
        # Best-effort — venue id=1 may or may not exist depending on seed
        # state, so a 404 here is expected/acceptable under load.
        self.client.put(
            "/venues/2",
            json={"name": "Renamed Under Load"},
            headers=self.headers,
            name="/venues/{id} [update]",
        )


# ============================================================================
# ADMIN-LIKE TRAFFIC: dashboard checks. Low weight — realistically just one
# or two admins glancing at analytics occasionally, not constant traffic.
# ============================================================================
class AdminUser(HttpUser):
    wait_time = between(1, 3)
    weight = 1

    def on_start(self):
        self.email = _random_email()
        self.password = "loadtest123"

        self.client.post("/signup", json={
            "email": self.email,
            "password": self.password,
            "role": "admin",
        })

        response = self.client.post("/login", data={
            "username": self.email,
            "password": self.password,
        })
        if response.status_code == 200:
            token = response.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {token}"}
        else:
            self.headers = {}

    @task
    def view_dashboard(self):
        self.client.get("/admin/dashboard", headers=self.headers, name="/admin/dashboard")