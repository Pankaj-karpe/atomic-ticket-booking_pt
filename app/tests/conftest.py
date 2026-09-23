#Root pytest configuration and shared fixtures.

import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv
from sqlalchemy import text

# ============================================================================
# STEP 0: load .env.test BEFORE importing anything from `app`.
# ============================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env.test", override=True)

# NOW it's safe to import the app. Every one of these imports triggers
# `app/config.py`'s settings object to be built from the .env.test values
# we just loaded — database.py's engine, tasks.py's SessionLocal, and
# celery_app.py's broker URL all end up pointing at the test database.
from app.main import app
from app.database import Base, engine, SessionLocal
from app.celeryapp import celery_app
from app import models, oauth2, utils, tasks

# ============================================================================
# STEP 1 (session-scoped, autouse): runs ONCE for the whole test run.
# Creates every table before any test executes, drops them all when the
# entire test session finishes. "autouse" means no test file needs to
# explicitly ask for this — it just happens.
# ============================================================================
@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    Base.metadata.create_all(bind=engine)

    #celery "eager" mode runs the task immediately instead of waiting for rabbitmq and worker
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    Base.metadata.drop_all(bind=engine)

# ============================================================================
# STEP 2 (autouse): wipe every table's ROWS after each individual test. Resets
# auto-increment ids back to 1 too
# ============================================================================
@pytest.fixture(autouse=True)
def clean_tables():
    yield # lets the test run first then clean up
    table_names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))

# ============================================================================
# STEP 3 (autouse): mock smtplib.SMTP everywhere, for every test, so NOTHING
# in the test suite ever makes a real network call to an email server.
# ============================================================================
@pytest.fixture(autouse=True)
def mock_smtp():
    with patch("app.tasks.smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server
        yield mock_server

# ============================================================================
# STEP 4: a plain DB session for tests to seed data / make assertions with.
# This is a DIFFERENT Python Session object than whatever the app's own
# `get_db()` dependency creates per HTTP request — but both point at the
# SAME physical test database, so anything committed here is immediately
# visible to the app's requests, and vice versa. No dependency_overrides
# needed for this to work.
# ============================================================================
@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


# ============================================================================
# STEP 5: the HTTP test client. `with TestClient(app) as c:` also fires
# FastAPI's startup/shutdown events (so your @app.on_event("startup")
# logging setup runs, matching real behavior).
# ============================================================================
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

# ============================================================================
# STEP 6: reusable "create a REAL user row + a valid auth header" factory
# ============================================================================
@pytest.fixture
def make_user(db):
    def _make_user(email: str, role: str, password: str = "testpass123"):
        user = models.User(email = email, hashed_pwd=utils.hash(password), role=role)
        db.add(user)
        db.commit()
        db.refresh(user)

        token = oauth2.create_access_token({"user_id": user.id, "role": user.role})
        headers = {"Authorization": f"Bearer {token}"}
        return user, headers
    
    return _make_user

@pytest.fixture
def buyer(make_user):
    return make_user("buyer@test.com", "buyer")

@pytest.fixture
def buyer_headers(buyer):
    return buyer[1]

@pytest.fixture
def seller(make_user):
    return make_user("seller@test.com", "seller")

@pytest.fixture
def seller_headers(seller):
    return seller[1]

@pytest.fixture
def admin(make_user):
    return make_user("admin@test.com", "admin")
 
 
@pytest.fixture
def admin_headers(admin):
    return admin[1]

# ============================================================================
# STEP 7: a ready-made Venue (2 seats) + Event + prices, since almost every
# test needs SOME event/seat to act on. Returns a dict so each test can
# grab exactly the pieces it needs by name.
# ============================================================================
@pytest.fixture
def seeded_event(db):
    venue = models.Venue(name="Test Arena", total_capacity=2)
    db.add(venue)
    db.commit()
    db.refresh(venue)

    seat1 = models.Seat(venue_id=venue.id, category="NORMAL", row_number=1, seat_number="A1")
    seat2 = models.Seat(venue_id=venue.id, category="VIP", row_number=2, seat_number="A2")
    db.add_all([seat1, seat2])
    db.commit()
    db.refresh(seat1)
    db.refresh(seat2)

    # 30 days out: comfortably outside any reasonable REFUND_CUTOFF_HOURS,
    # so refund tests default to "allowed" unless a test deliberately
    # moves start_time closer to test the rejection path.
    event = models.Event(
        venue_id=venue.id,
        title="Test Concert",
        start_time=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
 
    price_normal = models.Ticket_Price(event_id=event.id, section="NORMAL", price=100.00)
    price_vip = models.Ticket_Price(event_id=event.id, section="VIP", price=250.00)
    db.add_all([price_normal, price_vip])
    db.commit()
 
    return {
        "venue": venue,
        "seat1": seat1,
        "seat2": seat2,
        "event": event,
    }