# task - auto expires(sets them to cancelled) the seats held past the allowed time limit

import logging
import smtplib
from email.mime.text import MIMEText
from datetime import timezone, timedelta, datetime
from collections import defaultdict
import requests
from .celeryapp import celery_app
from .database import SessionLocal
from . import models
from .config import settings

logger = logging.getLogger(__name__)

HOLD_EXPIRY_MINUTES = settings.HOLD_EXPIRY_MINUTES   #timelimit for held expiry
FASTAPI_INTERNAL_URL=settings.FASTAPI_INTERNAL_URL   #uviron link/command (http://<ip>:<port>)
INTERNAL_API_SECRET=settings.SECRET_KEY   #the jwt secret key 


@celery_app.task(name="app.tasks.send_email_task")
def send_email_task(to_email: str, subject: str, body: str):
    """
    The 'mail room worker'. This is the ONLY function that actually talks
    to an SMTP server. Everywhere else in the app just calls
    send_email_task.delay(...) — which is like dropping an envelope in a
    mailbox — and moves on immediately. This function is what picks that
    envelope up (in the Celery worker process) and actually sends it,
    on its own time, without making the person who triggered it wait.
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD: 
        # if config is missing code should not crash just print in logs so dev can handle it 
        logger.warning(f"[send_email_task] SMTP not configured - skipping enail to {to_email}: '{subject}'")
        return

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = settings.FROM_EMAIL
    msg["To"] = to_email

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()  # upgrade the connection to encrypted (TLS)
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info(f"[send_email_task] sent '{subject}' to {to_email}")
    except Exception:
        logger.exception(f"[send_email_task] FAILED to send '{subject}' to {to_email}")
            
@celery_app.task(name="app.tasks.release_expired_holds")
def release_expired_holds():
    """
    Scans for tickets that have been HELD for longer than HOLD_EXPIRY_MINUTES
    and releases them (sets status -> CANCELLED), then notifies the live
    WebSocket clients for each affected event.
    """
    db = SessionLocal()
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=HOLD_EXPIRY_MINUTES)
        expired_tickets = (db.query(models.Ticket).filter(models.Ticket.status=="HELD", models.Ticket.created_at < cutoff_time,).all())

        if not expired_tickets:
            logger.info("[release_expired_holds] no expired holds found")
            return

        released_by_event = defaultdict(list)

        # Capture what we need for emails BEFORE committing — after commit,
        # SQLAlchemy may need to re-fetch attributes from the DB, and it's
        # simpler to just grab the plain values now while everything's loaded.
        email_notifications = []
        
        for ticket in expired_tickets:
            email_notifications.append({
                "to_email": ticket.user.email,
                "seat_id": ticket.seat_id,
                "event_id": ticket.event_id
            })
            ticket.status = "CANCELLED"
            released_by_event[ticket.event_id].append(ticket.seat_id)

        db.commit()

        logger.info(
            f"[release_expired_holds] released {len(expired_tickets)} expired holds"
            f"across {len(released_by_event)} event(s)"
        )

        # Now tell the FastAPI process to push a WebSocket event for each affected event_id, so connected clients see the seats free up live.
        for event_id, seat_ids in released_by_event.items():
            _notify_fastapi_of_release(event_id, seat_ids)

        # Drop an email notification in the mailbox for each affected user.
        for info in email_notifications:
            send_email_task.delay(
                info["to_email"],
                "Your seat hold has expired",
                f"Your hold on seat {info['seat_id']} for event {info['event_id']} "
                f"expired after {HOLD_EXPIRY_MINUTES} minutes and has been released. "
                f"The seat is now available for others to book.",
            )

    except Exception:
        db.rollback()
        logger.exception("[release_expired_holds] failed while processing expired holds")
        raise
    finally:
        db.close()


def _notify_fastapi_of_release(event_id: int, seat_ids: list[int]):
    """
    Calls a small internal FastAPI endpoint that lives in the SAME process
    as your ConnectionManager, so it can actually reach the live WebSocket
    connections. The Celery worker itself has no access to that in-memory
    connection registry, so this HTTP hop is the bridge between "background
    job updated the DB" and "connected clients get told about it".
    """
    url = f"{FASTAPI_INTERNAL_URL}/internal/broadcast-release/{event_id}"
    try:
        response = requests.post(
            url,
            json={"seat_ids": seat_ids},
            headers={"X-Internal-Secret": INTERNAL_API_SECRET},
            timeout=5,
        )
        response.raise_for_status()
        
    except requests.RequestException as e :
        # Don't let a broadcast failure roll back or crash the whole task —
        # the DB release already committed successfully, which is the part
        # that actually matters (seat is free). Worst case here is clients
        # find out on their next poll/refresh instead of instantly.
        body_detail = getattr(e.response, "text", "<no response body>")
        logger.exception(
            f"[release_expired_holds] DB release succeeded but failed to notify "
            f"FastAPI for event_id={event_id}, seat_ids={seat_ids}"
            f"Response body: {body_detail}"
        )