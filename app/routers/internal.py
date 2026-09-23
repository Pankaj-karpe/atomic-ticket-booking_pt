"""
Internal-only endpoints — NOT part of your public API surface.
 
These exist purely so background processes (like the Celery worker) that
run OUTSIDE this FastAPI process can still trigger actions that require
access to in-memory state living INSIDE this process — specifically,
`manager` from websocket.py, which holds all active WebSocket connections.
"""

from ..config import settings
from fastapi import APIRouter, Header, HTTPException, status, Depends
from .websocket import manager
from pydantic import BaseModel

router = APIRouter(
    prefix="/internal",
    tags=["Internal"],
)

INTERNAL_SECRET_KEY = settings.SECRET_KEY

class ReleasePayLoad(BaseModel):
    seat_ids: list[int]

def verify_internal_secret(x_internal_secret: str = Header(...)):
    if x_internal_secret != INTERNAL_SECRET_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal secret")

@router.post("/broadcast-release/{event_id}")
async def broadcast_release(event_id: int, payload: ReleasePayLoad, _verified: None = Depends(verify_internal_secret),):
    """
    Called by the Celery task (release_expired_holds) after it has already
    committed the DB changes. This endpoint's only job is to push a
    WebSocket message out to whoever is currently watching this event.
 
    NOTE: this endpoint does no DB writes itself — the Celery task already
    did that. This is purely "notify live viewers" duty.
    """
    for seat_id in payload.seat_ids:
        await manager.broadcast_to_event(
            event_id=event_id,
            message={
                "event": "SEAT_RELEASED",
                "seat_id": seat_id,
                "status": "CANCELLED",
                "reason": "hold_expired",  # lets the frontend distinguish an
                                            # auto-expiry from a manual release
            },
        )
    return {"status": "ok", "broadcast_count": len(payload.seat_ids)}