from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from typing import List, Dict, Any
from pydantic import ValidationError
from models import EventModel
from database import init_db, insert_event_idempotent
from contextlib import asynccontextmanager
import sqlite3
import time
import uuid
import json
import asyncio
from datetime import datetime, timezone

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)
DB_PATH = "store_data.db"

# --- STRUCTURED LOGGING MIDDLEWARE ---
@app.middleware("http")
async def json_logging_middleware(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    store_id = "unknown"
    path_parts = request.url.path.split('/')
    if 'stores' in path_parts:
        try: store_id = path_parts[path_parts.index('stores') + 1]
        except IndexError: pass

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        status_code = 503
        response = JSONResponse(status_code=503, content={"error": "Database/System unavailable", "details": str(e)})

    latency_ms = round((time.time() - start_time) * 1000, 2)
    log_entry = {
        "trace_id": trace_id, "store_id": store_id, "endpoint": request.url.path,
        "latency_ms": latency_ms, "event_count": 0, "status_code": status_code
    }
    print(json.dumps(log_entry))
    return response

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.post("/events/ingest")
async def ingest_events(payload: List[Dict[str, Any]], request: Request):
    if len(payload) > 500: raise HTTPException(status_code=400, detail="Batch exceeds 500")
    successful, failed, errors = 0, 0, []
    try:
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
    except sqlite3.Error as e:
        raise HTTPException(status_code=503, detail={"error": "Database unavailable", "message": str(e)})

    print(json.dumps({"trace_id": "INGEST", "store_id": "N/A", "endpoint": "/events/ingest", "event_count": len(payload), "status_code": 200}))
    return {"status": "partial_success" if failed > 0 else "success", "processed": successful, "failed": failed, "errors": errors}

@app.get("/stores/{store_id}/metrics")
async def get_metrics(store_id: str):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT visitor_id) FROM events WHERE store_id=? AND is_staff=0 AND event_type='ENTRY'", (store_id,))
        unique_visitors = c.fetchone()[0] or 0
        
        # EDGE CASE FIXED: 5-Minute POS Correlation Window
        c.execute("""
            SELECT COUNT(DISTINCT p.transaction_id) 
            FROM pos_transactions p 
            INNER JOIN events e ON p.store_id = e.store_id 
            WHERE e.event_type='BILLING_QUEUE_JOIN' AND e.is_staff=0
            AND (julianday(p.timestamp) - julianday(e.timestamp)) * 24 * 60 BETWEEN 0 AND 5
        """)
        purchases = c.fetchone()[0] or 0
        conversion_rate = (purchases / unique_visitors) if unique_visitors > 0 else 0.0

        c.execute("SELECT zone_id, AVG(dwell_ms) FROM events WHERE store_id=? AND event_type='ZONE_DWELL' AND zone_id IS NOT NULL GROUP BY zone_id", (store_id,))
        avg_dwell = {row[0]: (row[1]/1000) for row in c.fetchall()}

        c.execute("SELECT COUNT(*) FROM events WHERE store_id=? AND event_type='BILLING_QUEUE_JOIN'", (store_id,))
        joins = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM events WHERE store_id=? AND event_type='BILLING_QUEUE_ABANDON'", (store_id,))
        abandons = c.fetchone()[0] or 0
        
        queue_depth = max(0, joins - abandons)
        abandonment_rate = (abandons / joins) if joins > 0 else 0.0

        return {
            "store_id": store_id, "unique_visitors": unique_visitors, "conversion_rate": conversion_rate,
            "avg_dwell_time_seconds": sum(avg_dwell.values())/len(avg_dwell) if avg_dwell else 0.0,
            "avg_dwell_per_zone": avg_dwell, "queue_depth": queue_depth, "abandonment_rate": abandonment_rate
        }
    except sqlite3.Error as e:
        raise HTTPException(status_code=503, detail={"error": "Database unavailable", "message": str(e)})

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
    
    # EDGE CASE FIXED: 5-Minute POS Correlation Window
    c.execute("""
        SELECT COUNT(DISTINCT p.transaction_id) 
        FROM pos_transactions p 
        INNER JOIN events e ON p.store_id = e.store_id 
        WHERE e.event_type='BILLING_QUEUE_JOIN' AND e.is_staff=0
        AND (julianday(p.timestamp) - julianday(e.timestamp)) * 24 * 60 BETWEEN 0 AND 5
    """)
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
    c.execute("SELECT COUNT(*) FROM events WHERE store_id=? AND event_type='BILLING_QUEUE_JOIN'", (store_id,))
    if (c.fetchone()[0] or 0) > 15: anomalies.append({"type": "BILLING_QUEUE_SPIKE", "severity": "WARN", "suggested_action": "Deploy staff to billing."})
    
    # EDGE CASE FIXED: Strict 30-Minute Inactivity Window
    c.execute("SELECT MAX(timestamp) FROM events WHERE store_id=? AND event_type='ZONE_ENTER'", (store_id,))
    last_event_ts = c.fetchone()[0]
    if not last_event_ts: 
        anomalies.append({"type": "DEAD_ZONE", "severity": "INFO", "suggested_action": "Check camera health (Never active)."})
    else:
        try:
            last_time = datetime.fromisoformat(last_event_ts.replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - last_time).total_seconds() > 1800: # 1800 seconds = 30 mins
                anomalies.append({"type": "DEAD_ZONE", "severity": "CRITICAL", "suggested_action": "No zone activity for 30+ mins."})
        except: pass

    return {"store_id": store_id, "anomalies": anomalies}

@app.get("/health")
async def health_check():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT store_id, MAX(timestamp) FROM events GROUP BY store_id")
        stores = []
        for sid, last_ts in c.fetchall():
            status = "healthy"
            if last_ts:
                try:
                    last_time = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                    lag_seconds = (datetime.now(timezone.utc) - last_time).total_seconds()
                    if lag_seconds > 600: # 10 minutes = 600 seconds
                        status = "STALE_FEED"
                except:
                    pass
            stores.append({"store_id": sid, "last_event_timestamp": last_ts, "feed_status": status})
        return {"status": "operational", "stores": stores}
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "Database unavailable", "message": str(e)})


@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Apex Retail Dashboard</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-900 text-white p-8">
        <h1 class="text-3xl font-bold mb-8">Live Store Analytics: STORE_BLR_002</h1>
        <div class="grid grid-cols-3 gap-6">
            <div class="bg-gray-800 p-6 rounded-xl border border-gray-700 shadow-lg">
                <h2 class="text-gray-400 text-sm uppercase tracking-wider mb-2">Unique Visitors</h2>
                <p id="visitors" class="text-5xl font-bold text-blue-400">0</p>
            </div>
            <div class="bg-gray-800 p-6 rounded-xl border border-gray-700 shadow-lg">
                <h2 class="text-gray-400 text-sm uppercase tracking-wider mb-2">Conversion Rate</h2>
                <p id="conversion" class="text-5xl font-bold text-green-400">0.0%</p>
            </div>
            <div class="bg-gray-800 p-6 rounded-xl border border-gray-700 shadow-lg">
                <h2 class="text-gray-400 text-sm uppercase tracking-wider mb-2">Queue Depth</h2>
                <p id="queue" class="text-5xl font-bold text-red-400">0</p>
            </div>
        </div>
        <script>
            const evtSource = new EventSource("/stream/STORE_BLR_002");
            evtSource.onmessage = function(event) {
                const data = JSON.parse(event.data);
                document.getElementById("visitors").innerText = data.unique_visitors || 0;
                document.getElementById("conversion").innerText = ((data.conversion_rate || 0) * 100).toFixed(1) + "%";
                document.getElementById("queue").innerText = data.queue_depth || 0;
            };
        </script>
    </body>
    </html>
    """

async def event_generator(store_id: str):
    while True:
        try:
            metrics = await get_metrics(store_id)
            yield f"data: {json.dumps(metrics)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        await asyncio.sleep(2)

@app.get("/stream/{store_id}")
async def stream_metrics(store_id: str):
    return StreamingResponse(event_generator(store_id), media_type="text/event-stream")
