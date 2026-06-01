with open('tests/test_integration.py', 'w') as f:
    f.write("""import sys, os, uuid
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from app.main import app

@pytest.fixture(scope="module")
def client():
    # Using 'with' forces FastAPI to trigger the database startup events!
    with TestClient(app) as c:
        yield c

def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200

def test_empty_store(client):
    res = client.get("/stores/STORE_EMPTY_999/metrics")
    assert res.status_code == 200
    assert res.json()["unique_visitors"] == 0

def test_all_staff_clip(client):
    events = [
        {"event_id": str(uuid.uuid4()), "store_id": "STORE_STAFF_ONLY", "camera_id": "CAM1", "visitor_id": "V1", "event_type": "ENTRY", "timestamp": "2026-04-10T10:00:00Z", "is_staff": True},
        {"event_id": str(uuid.uuid4()), "store_id": "STORE_STAFF_ONLY", "camera_id": "CAM1", "visitor_id": "V2", "event_type": "ENTRY", "timestamp": "2026-04-10T10:05:00Z", "is_staff": True}
    ]
    client.post("/events/ingest", json=events)
    res = client.get("/stores/STORE_STAFF_ONLY/metrics")
    assert res.status_code == 200
    assert res.json()["unique_visitors"] == 0

def test_zero_purchases(client):
    events = [{"event_id": str(uuid.uuid4()), "store_id": "STORE_NO_SALES", "camera_id": "CAM1", "visitor_id": "V3", "event_type": "ENTRY", "timestamp": "2026-04-10T10:00:00Z", "is_staff": False}]
    client.post("/events/ingest", json=events)
    res = client.get("/stores/STORE_NO_SALES/metrics")
    assert res.status_code == 200
    assert res.json()["conversion_rate"] == 0.0

def test_reentry_deduplication(client):
    events = [
        {"event_id": str(uuid.uuid4()), "store_id": "STORE_REENTRY", "camera_id": "CAM1", "visitor_id": "V_REENTRY", "event_type": "ENTRY", "timestamp": "2026-04-10T10:00:00Z", "is_staff": False},
        {"event_id": str(uuid.uuid4()), "store_id": "STORE_REENTRY", "camera_id": "CAM1", "visitor_id": "V_REENTRY", "event_type": "EXIT", "timestamp": "2026-04-10T10:15:00Z", "is_staff": False},
        {"event_id": str(uuid.uuid4()), "store_id": "STORE_REENTRY", "camera_id": "CAM1", "visitor_id": "V_REENTRY", "event_type": "REENTRY", "timestamp": "2026-04-10T10:30:00Z", "is_staff": False}
    ]
    client.post("/events/ingest", json=events)
    res = client.get("/stores/STORE_REENTRY/metrics")
    assert res.status_code == 200
    assert res.json()["unique_visitors"] == 1

def test_batch_size_limit(client):
    events = [{"event_id": str(uuid.uuid4()), "store_id": "S1", "camera_id": "C1", "visitor_id": "V1", "event_type": "ENTRY", "timestamp": "2026-04-10T10:00:00Z"} for _ in range(501)]
    res = client.post("/events/ingest", json=events)
    assert res.status_code == 400
""")
print("✅ SUCCESS: Tests updated to properly initialize the database!")
