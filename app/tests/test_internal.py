"""
Tests for POST /internal/broadcast-release/{event_id} — the endpoint the
Celery expiry job calls (from a separate process) to push WebSocket
updates. Guarded by a shared secret header (X-Internal-Secret).
"""
from app.config import settings

def test_broadcast_release_rejects_missing_secret_header(client, seeded_event):
    event_id = seeded_event["event"].id
    response = client.post(f"/internal/broadcast-release/{event_id}", json={"seat_ids": [1]})
    assert response.status_code == 422

def test_broadcast_release_rejects_wrong_secret(client, seeded_event):
    event_id = seeded_event["event"].id
    response = client.post(
        f"/internal/broadcast-release/{event_id}",
        json={"seat_ids": [1]},
        headers={"X-Internal-Secret": "definitely-the-wrong-value"},
    )
    assert response.status_code == 403

def test_broadcast_release_accepts_correct_secret(client, seeded_event):
    event_id = seeded_event["event"].id

    response = client.post(
        f"/internal/broadcast-release/{event_id}",
        json={"seat_ids": [1, 2]},
        headers={"X-Internal-Secret": settings.SECRET_KEY},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["broadcast_count"] == 2