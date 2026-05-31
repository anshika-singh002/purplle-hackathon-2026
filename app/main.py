from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any
from pydantic import ValidationError
from models import EventModel
from database import init_db, insert_event_idempotent
from contextlib import asynccontextmanager
import sqlite3
from datetime import datetime, timezone

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)
DB_PATH = "store_data.db"

# ==========================================
# PHASE 3: INGESTION (Already working!)
# ==========================================
@app.post("/events/ingest")
async def ingest_events(payload: List[Dict[str, Any]]):
    if len(payload) > 500: raise HTTPException(status_code=400, detail="Batch exceeds 500")
    successful, failed, errors = 0, 0, []
    for item in payload:
        try:
            event = EventModel(**item)
            event_dict = event.dict() if hasattr(event, 'dict') else event.model_dump()
            if insert_event_idempotent(event_dict): successful += 1
            else:
                failed += 1
                errors.append({"event_id": item.get("event_id", ""), "error": "DB insert failed"})
        except ValidationError:
            failed += 1
            errors.append({"event_id": item.get("event_id", ""), "error": "Schema invalid"})
    return {"status": "partial_success" if failed > 0 else "success", "processed": successful, "failed": failed, "errors": errors}

# ==========================================
# PHASE 4: INTELLIGENCE METRICS
# ==========================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/stores/{store_id}/metrics")
async def get_metrics(store_id: str):
    conn = get_db()
    c = conn.cursor()
    
    # Unique visitors (Exclude staff)
    c.execute("SELECT COUNT(DISTINCT visitor_id) FROM events WHERE store_id=? AND is_staff=0 AND event_type='ENTRY'", (store_id,))
    unique_visitors = c.fetchone()[0] or 0
    
    # Purchases for Conversion Rate
    c.execute("SELECT COUNT(*) FROM pos_transactions WHERE store_id=?", (store_id,))
    purchases = c.fetchone()[0] or 0
    conversion_rate = (purchases / unique_visitors) if unique_visitors > 0 else 0.0

    # Dwell Time
    c.execute("SELECT zone_id, AVG(dwell_ms) FROM events WHERE store_id=? AND event_type='ZONE_DWELL' AND zone_id IS NOT NULL GROUP BY zone_id", (store_id,))
    avg_dwell = {row[0]: (row[1]/1000) for row in c.fetchall()}

    # Queue Depth & Abandonment
    c.execute("SELECT COUNT(*) FROM events WHERE store_id=? AND event_type='BILLING_QUEUE_JOIN'", (store_id,))
    joins = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM events WHERE store_id=? AND event_type='BILLING_QUEUE_ABANDON'", (store_id,))
    abandons = c.fetchone()[0] or 0
    
    queue_depth = max(0, joins - abandons)
    abandonment_rate = (abandons / joins) if joins > 0 else 0.0

    return {
        "store_id": store_id,
        "unique_visitors": unique_visitors,
        "conversion_rate": conversion_rate,
        "avg_dwell_time_seconds": sum(avg_dwell.values())/len(avg_dwell) if avg_dwell else 0.0,
        "avg_dwell_per_zone": avg_dwell,
        "queue_depth": queue_depth,
        "abandonment_rate": abandonment_rate
    }

@app.get("/stores/{store_id}/funnel")
async def get_funnel(store_id: str):
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(DISTINCT visitor_id) FROM events WHERE store_id=? AND is_staff=0 AND event_type='ENTRY'", (store_id,))
    entries = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(DISTINCT visitor_id) FROM events WHERE store_id=? AND is_staff=0 AND event_type='ZONE_ENTER'", (store_id,))
    zone_visits = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(DISTINCT visitor_id) FROM events WHERE store_id=? AND is_staff=0 AND event_type='BILLING_QUEUE_JOIN'", (store_id,))
    queue_joins = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM pos_transactions WHERE store_id=?", (store_id,))
    purchases = c.fetchone()[0] or 0

    return {
        "store_id": store_id,
        "funnel": {"entries": entries, "zone_visits": zone_visits, "billing_queue": queue_joins, "purchases": purchases},
        "drop_off_percentages": {
            "entry_to_zone": 1 - (zone_visits/entries) if entries else 0.0,
            "zone_to_queue": 1 - (queue_joins/zone_visits) if zone_visits else 0.0,
            "queue_to_purchase": 1 - (purchases/queue_joins) if queue_joins else 0.0
        }
    }

@app.get("/stores/{store_id}/heatmap")
async def get_heatmap(store_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT visitor_id) FROM events WHERE store_id=? AND is_staff=0", (store_id,))
    total_sessions = c.fetchone()[0] or 0
    
    c.execute("SELECT zone_id, COUNT(DISTINCT visitor_id), AVG(dwell_ms) FROM events WHERE store_id=? AND zone_id IS NOT NULL GROUP BY zone_id", (store_id,))
    zones = [{"zone_id": r[0], "visit_frequency": min(100, (r[1]/total_sessions * 100)) if total_sessions else 0, "avg_dwell_ms": r[2]} for r in c.fetchall()]

    return {"store_id": store_id, "data_confidence": total_sessions >= 20, "total_sessions": total_sessions, "heatmap": zones}

@app.get("/stores/{store_id}/anomalies")
async def get_anomalies(store_id: str):
    conn = get_db()
    c = conn.cursor()
    anomalies = []
    
    # Check 1: Billing Queue Spike
    c.execute("SELECT COUNT(*) FROM events WHERE store_id=? AND event_type='BILLING_QUEUE_JOIN'", (store_id,))
    if (c.fetchone()[0] or 0) > 15:
        anomalies.append({"type": "BILLING_QUEUE_SPIKE", "severity": "WARN", "suggested_action": "Deploy staff to billing."})
    
    # Check 2: Dead Zone
    c.execute("SELECT MAX(timestamp) FROM events WHERE store_id=? AND event_type='ZONE_ENTER'", (store_id,))
    last_zone = c.fetchone()[0]
    if not last_zone:
        anomalies.append({"type": "DEAD_ZONE", "severity": "INFO", "suggested_action": "Check camera health."})
        
    return {"store_id": store_id, "anomalies": anomalies}

@app.get("/health")
async def health_check():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT store_id, MAX(timestamp) FROM events GROUP BY store_id")
    
    stores = []
    global_status = "healthy"
    
    for row in c.fetchall():
        store_id, last_event = row[0], row[1]
        try:
            last_time = datetime.fromisoformat(last_event.replace("Z", "+00:00"))
            lag = (datetime.now(timezone.utc) - last_time).total_seconds()
            feed_status = "STALE_FEED" if lag > 600 else "ACTIVE"
            if feed_status == "STALE_FEED": global_status = "degraded"
        except:
            feed_status = "UNKNOWN"
        stores.append({"store_id": store_id, "last_event_timestamp": last_event, "feed_status": feed_status})

    return {"status": global_status, "stores": stores}
