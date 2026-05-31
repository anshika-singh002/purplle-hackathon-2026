# PROMPT: Generate pytest for metrics covering zero purchases and funnel re-entry deduplication.
# CHANGES MADE: Added FastAPI TestClient to validate HTTP 200 responses.
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_zero_purchases():
    # Store with no sales should return 0.0, not error
    response = client.get("/stores/STORE_EMPTY/metrics")
    assert response.status_code == 200
    assert response.json()["conversion_rate"] == 0.0

def test_idempotent_ingest():
    # Same payload twice should succeed
    payload = [{"event_id": "123e4567-e89b-12d3-a456-426614174000", "store_id": "S1", "camera_id": "C1", "visitor_id": "V1", "event_type": "ENTRY", "timestamp": "2026-05-31T12:00:00Z"}]
    res1 = client.post("/events/ingest", json=payload)
    res2 = client.post("/events/ingest", json=payload)
    assert res1.status_code == 200 and res2.status_code == 200
