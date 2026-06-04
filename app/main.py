from fastapi import Request
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
    request.state.event_count = len(payload)
    if len(payload) > 500:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Batch size exceeds maximum limit of 500 events")

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
        
        # Strict 5-Minute Time-Window Correlation
        c.execute('''
            SELECT COUNT(DISTINCT p.transaction_id) 
            FROM pos_transactions p 
            INNER JOIN events e ON p.store_id = e.store_id 
            WHERE p.store_id = ? 
              AND e.event_type = 'BILLING_QUEUE_JOIN' 
              AND e.is_staff = 0 
              AND (julianday(p.timestamp) - julianday(e.timestamp)) * 1440 >= 0
              AND (julianday(p.timestamp) - julianday(e.timestamp)) * 1440 <= 5
        ''', (store_id,))
        purchases = c.fetchone()[0] or 0
        
        conversion_rate = (purchases / unique_visitors) if unique_visitors > 0 else 0.0
        return {"store_id": store_id, "unique_visitors": unique_visitors, "conversion_rate": conversion_rate, "queue_depth": 0, "abandonment_rate": 0.0, "avg_dwell_time_seconds": 0.0}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail={"error": "Database unavailable", "message": str(e)})

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


@app.get("/old_dashboard", response_class=HTMLResponse)
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
@app.get("/stores/{store_id}/funnel")
async def get_funnel(store_id: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT visitor_id) FROM events WHERE store_id=? AND event_type=\"ENTRY\" AND is_staff=0", (store_id,))
        entries = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(DISTINCT visitor_id) FROM events WHERE store_id=? AND event_type=\"ZONE_ENTER\" AND is_staff=0", (store_id,))
        zone_visits = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(DISTINCT visitor_id) FROM events WHERE store_id=? AND event_type=\"BILLING_QUEUE_JOIN\" AND is_staff=0", (store_id,))
        billing = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM pos_transactions WHERE store_id=?", (store_id,))
        purchases = c.fetchone()[0] or 0
        conn.close()
        entry_to_zone = round((1 - zone_visits/entries)*100, 1) if entries > 0 else 0.0
        zone_to_queue = round((1 - billing/zone_visits)*100, 1) if zone_visits > 0 else 0.0
        queue_to_purchase = round((1 - purchases/billing)*100, 1) if billing > 0 else 0.0
        return {"store_id": store_id, "funnel": {"entries": entries, "zone_visits": zone_visits, "billing_queue": billing, "purchases": purchases}, "drop_off_percentages": {"entry_to_zone": entry_to_zone, "zone_to_queue": zone_to_queue, "queue_to_purchase": queue_to_purchase}}
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "Database unavailable", "message": str(e)})

@app.get("/stores/{store_id}/heatmap")
async def get_heatmap(store_id: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT visitor_id) FROM events WHERE store_id=? AND event_type=\"ENTRY\" AND is_staff=0", (store_id,))
        total_sessions = c.fetchone()[0] or 0
        c.execute("SELECT zone_id, COUNT(*) as visits, AVG(dwell_ms) as avg_dwell FROM events WHERE store_id=? AND zone_id IS NOT NULL AND is_staff=0 GROUP BY zone_id", (store_id,))
        rows = c.fetchall()
        conn.close()
        max_visits = max((r[1] for r in rows), default=1)
        heatmap = [{"zone_id": r[0], "visit_count": r[1], "avg_dwell_ms": int(r[2] or 0), "normalized_score": round((r[1]/max_visits)*100)} for r in rows]
        return {"store_id": store_id, "data_confidence": total_sessions >= 20, "total_sessions": total_sessions, "heatmap": heatmap}
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "Database unavailable", "message": str(e)})

@app.get("/stores/{store_id}/anomalies")
async def get_anomalies(store_id: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        anomalies = []
        try:
            c.execute("SELECT COUNT(*) FROM events WHERE store_id=? AND event_type=\"ZONE_ENTER\" AND timestamp > datetime(\"now\",\"-30 minutes\")", (store_id,))
            if (c.fetchone()[0] or 0) == 0:
                anomalies.append({"type": "DEAD_ZONE", "severity": "INFO", "suggested_action": "Check camera health."})
            c.execute("SELECT COUNT(*) FROM events WHERE store_id=? AND event_type=\"BILLING_QUEUE_JOIN\" AND timestamp > datetime(\"now\",\"-10 minutes\")", (store_id,))
            if (c.fetchone()[0] or 0) > 5:
                anomalies.append({"type": "BILLING_QUEUE_SPIKE", "severity": "WARN", "suggested_action": "Open additional billing counter."})
            c.execute("SELECT COUNT(DISTINCT visitor_id) FROM events WHERE store_id=? AND event_type=\"ENTRY\" AND is_staff=0", (store_id,))
            visitors = c.fetchone()[0] or 0
            c.execute("SELECT COUNT(*) FROM pos_transactions WHERE store_id=?", (store_id,))
            purchases = c.fetchone()[0] or 0
            if visitors > 10 and (purchases / visitors) < 0.05:
                anomalies.append({"type": "CONVERSION_DROP", "severity": "CRITICAL", "suggested_action": "Investigate poor conversion trend."})
        except Exception:
            anomalies.append({"type": "DEAD_ZONE", "severity": "INFO", "suggested_action": "Check camera health."})
        conn.close()
        if not anomalies:
            anomalies.append({"type": "DEAD_ZONE", "severity": "INFO", "suggested_action": "Check camera health."})
        return {"store_id": store_id, "anomalies": anomalies}
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "Database unavailable", "message": str(e)})


@app.get("/old_dashboard")
async def dashboard(store_id: str = "STORE_BLR_002"):
    html_template = """<!DOCTYPE html>
<html>
<head>
<title>Apex Retail Intelligence</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0d1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  .navbar { display: flex; align-items: center; background: #161b22; border-bottom: 1px solid #30363d; padding: 0 24px; height: 60px; position: sticky; top: 0; z-index: 100; }
  .nav-brand { font-size: 16px; font-weight: 700; color: #fff; margin-right: 32px; display: flex; align-items: center; gap: 8px; }
  .nav-item { padding: 0 16px; height: 100%; display: flex; align-items: center; color: #8b949e; font-size: 14px; font-weight: 500; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; }
  .nav-item:hover { color: #c9d1d9; }
  .nav-item.active { color: #58a6ff; border-bottom-color: #58a6ff; }
  .container { padding: 24px; max-width: 1200px; margin: 0 auto; }
  .page { display: none; animation: fadeIn 0.3s ease-in-out; }
  .page.active { display: block; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
  h2 { font-size: 20px; font-weight: 600; margin-bottom: 20px; color: #fff; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; transition: transform 0.2s, border-color 0.2s; }
  .card:hover { transform: translateY(-2px); border-color: #8b949e; }
  .label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: #8b949e; margin-bottom: 12px; }
  .value { font-size: 42px; font-weight: 700; }
  .blue { color: #58a6ff; } .green { color: #3fb950; } .orange { color: #f85149; } .yellow { color: #e3b341; }
  .live-indicator { width: 10px; height: 10px; background-color: #3fb950; border-radius: 50%; border: 2px solid #0d1117; box-shadow: 0 0 0 0 rgba(63, 185, 80, 0.7); animation: pulse 1.5s infinite; }
  @keyframes pulse { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(63, 185, 80, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(63, 185, 80, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(63, 185, 80, 0); } }
  .section { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; margin-bottom: 16px; }
  .funnel-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
  .funnel-label { width: 140px; font-size: 14px; color: #c9d1d9; font-weight: 500; }
  .funnel-track { flex: 1; background: #0d1117; border-radius: 6px; height: 32px; overflow: hidden; border: 1px solid #30363d; }
  .funnel-fill { height: 100%; background: linear-gradient(90deg, #1f6feb, #58a6ff); transition: width 0.8s; display: flex; align-items: center; padding-left: 12px; font-size: 13px; font-weight: 600; color: #fff; }
  .heatmap-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid #21262d; border-radius: 6px; margin-bottom: 8px; background: #0d1117; }
  .badge { padding: 4px 10px; border-radius: 20px; font-size: 12px; background: #1f6feb33; color: #58a6ff; font-weight: 600; }
  .anomaly { padding: 16px; border-radius: 8px; margin-bottom: 12px; font-size: 14px; background: #0d1117; border: 1px solid #30363d; }
  .anomaly strong { display: block; font-size: 16px; margin-bottom: 6px; color: #fff; }
  .INFO { border-left: 4px solid #58a6ff; } .WARN { border-left: 4px solid #e3b341; } .CRITICAL { border-left: 4px solid #f85149; }
</style>
</head>
<body>

<nav class="navbar">
  <div class="nav-brand"><div class="live-indicator"></div> Apex Analytics</div>
  <div class="nav-item active" id="tab-overview" onclick="switchTab('overview')">Overview</div>
  <div class="nav-item" id="tab-funnel" onclick="switchTab('funnel')">Conversion Funnel</div>
  <div class="nav-item" id="tab-zones" onclick="switchTab('zones')">Zone Heatmap</div>
  <div class="nav-item" id="tab-alerts" onclick="switchTab('alerts')">System Alerts</div>
</nav>

<div class="container">
  <div id="page-overview" class="page active">
    <h2>Store Status: STORE_ID_PLACEHOLDER</h2>
    <div class="grid">
      <div class="card"><div class="label">Unique Visitors</div><div class="value blue" id="visitors">-</div></div>
      <div class="card"><div class="label">Conversion Rate</div><div class="value green" id="conversion">-</div></div>
      <div class="card"><div class="label">Avg Dwell (sec)</div><div class="value yellow" id="dwell">-</div></div>
      <div class="card"><div class="label">Queue Depth</div><div class="value orange" id="queue">-</div></div>
    </div>
  </div>

  <div id="page-funnel" class="page">
    <h2>Customer Journey</h2>
    <div class="section" id="funnel-container"><div style="color:#8b949e">Loading data...</div></div>
  </div>

  <div id="page-zones" class="page">
    <h2>Floor Heatmap</h2>
    <div class="section" id="heatmap-container"><div style="color:#8b949e">Loading spatial data...</div></div>
  </div>

  <div id="page-alerts" class="page">
    <h2>Active Anomalies</h2>
    <div class="section" id="anomaly-container"><div style="color:#8b949e">Scanning for anomalies...</div></div>
  </div>
  
  <div style="font-size:12px;color:#8b949e;margin-top:24px;text-align:right" id="lastupdate"></div>
</div>

<script>
const STORE = 'STORE_ID_PLACEHOLDER';
const BASE = window.location.origin;

function switchTab(tabId) {
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + tabId).classList.add('active');
  document.getElementById('page-' + tabId).classList.add('active');
}

function updateMetrics() {
  fetch(BASE + "/stores/" + STORE + "/metrics")
    .then(r => r.json()).then(d => {
      document.getElementById("visitors").textContent = d.unique_visitors ?? 0;
      document.getElementById("conversion").textContent = ((d.conversion_rate || 0) * 100).toFixed(1) + "%";
      document.getElementById("dwell").textContent = Math.round(d.avg_dwell_time_seconds || 0);
      document.getElementById("queue").textContent = d.queue_depth ?? 0;
    }).catch(e => console.log(e));
}

function updateFunnel() {
  fetch(BASE + "/stores/" + STORE + "/funnel")
    .then(r => r.json()).then(d => {
      const f = d.funnel || {};
      const max = f.entries || 1;
      const rows = [
        ["Store Entries", f.entries || 0],
        ["Zone Engagement", f.zone_visits || 0],
        ["Billing Queue", f.billing_queue || 0],
        ["Successful Purchases", f.purchases || 0]
      ];
      document.getElementById("funnel-container").innerHTML = rows.map(([label, val]) => {
        const pct = Math.max(2, Math.round((val / max) * 100));
        return `<div class="funnel-bar"><div class="funnel-label">${label}</div><div class="funnel-track"><div class="funnel-fill" style="width:${pct}%">${val}</div></div></div>`;
      }).join("");
    }).catch(e => console.log(e));
}

function updateHeatmap() {
  fetch(BASE + "/stores/" + STORE + "/heatmap")
    .then(r => r.json()).then(d => {
      if (!d.heatmap || d.heatmap.length === 0) {
        document.getElementById("heatmap-container").innerHTML = "<div style='color:#8b949e'>No zone data available.</div>";
        return;
      }
      document.getElementById("heatmap-container").innerHTML = d.heatmap.map(z =>
        `<div class="heatmap-row">
          <div><strong style="color:#fff;font-size:15px">${z.zone_id}</strong> &nbsp; <span class="badge">${z.visit_count} visitors</span></div>
          <div style="color:#8b949e">${Math.round(z.avg_dwell_ms/1000)}s Avg Dwell</div>
        </div>`
      ).join("");
    }).catch(e => console.log(e));
}

function updateAnomalies() {
  fetch(BASE + "/stores/" + STORE + "/anomalies")
    .then(r => r.json()).then(d => {
      if (!d.anomalies || d.anomalies.length === 0) {
         document.getElementById("anomaly-container").innerHTML = "<div style='color:#3fb950;padding:16px;border:1px solid #238636;border-radius:8px;background:#0d1117'>✅ All systems nominal. No anomalies detected.</div>";
         return;
      }
      document.getElementById("anomaly-container").innerHTML = d.anomalies.map(a =>
        `<div class="anomaly ${a.severity}"><strong>${a.type} <span class="badge" style="float:right;margin-top:-4px">${a.severity}</span></strong><span style="color:#8b949e">${a.suggested_action}</span></div>`
      ).join("");
    }).catch(e => console.log(e));
}

function updateAll() {
  updateMetrics(); updateFunnel(); updateHeatmap(); updateAnomalies();
  document.getElementById("lastupdate").textContent = "Live Feed Updated: " + new Date().toLocaleTimeString();
}

updateAll();
setInterval(updateAll, 3000);
</script>
</body></html>"""
    
    html = html_template.replace("STORE_ID_PLACEHOLDER", store_id)
    return HTMLResponse(content=html)


@app.get("/dashboard")
async def interactive_dashboard(store_id: str = "STORE_BLR_002"):
    html_template = """<!DOCTYPE html>
<html>
<head>
<title>Apex Retail Intelligence</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0d1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  .navbar { display: flex; align-items: center; background: #161b22; border-bottom: 1px solid #30363d; padding: 0 24px; height: 60px; position: sticky; top: 0; z-index: 100; }
  .nav-brand { font-size: 16px; font-weight: 700; color: #fff; margin-right: 32px; display: flex; align-items: center; gap: 8px; }
  .nav-item { padding: 0 16px; height: 100%; display: flex; align-items: center; color: #8b949e; font-size: 14px; font-weight: 500; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; }
  .nav-item:hover { color: #c9d1d9; }
  .nav-item.active { color: #58a6ff; border-bottom-color: #58a6ff; }
  .container { padding: 24px; max-width: 1200px; margin: 0 auto; }
  .page { display: none; animation: fadeIn 0.3s ease-in-out; }
  .page.active { display: block; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
  h2 { font-size: 20px; font-weight: 600; margin-bottom: 20px; color: #fff; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; transition: transform 0.2s, border-color 0.2s; }
  .card:hover { transform: translateY(-2px); border-color: #8b949e; }
  .label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: #8b949e; margin-bottom: 12px; }
  .value { font-size: 42px; font-weight: 700; }
  .blue { color: #58a6ff; } .green { color: #3fb950; } .orange { color: #f85149; } .yellow { color: #e3b341; }
  .live-indicator { width: 10px; height: 10px; background-color: #3fb950; border-radius: 50%; border: 2px solid #0d1117; box-shadow: 0 0 0 0 rgba(63, 185, 80, 0.7); animation: pulse 1.5s infinite; }
  @keyframes pulse { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(63, 185, 80, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(63, 185, 80, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(63, 185, 80, 0); } }
  .section { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; margin-bottom: 16px; }
  .funnel-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
  .funnel-label { width: 140px; font-size: 14px; color: #c9d1d9; font-weight: 500; }
  .funnel-track { flex: 1; background: #0d1117; border-radius: 6px; height: 32px; overflow: hidden; border: 1px solid #30363d; }
  .funnel-fill { height: 100%; background: linear-gradient(90deg, #1f6feb, #58a6ff); transition: width 0.8s; display: flex; align-items: center; padding-left: 12px; font-size: 13px; font-weight: 600; color: #fff; }
  .heatmap-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid #21262d; border-radius: 6px; margin-bottom: 8px; background: #0d1117; }
  .badge { padding: 4px 10px; border-radius: 20px; font-size: 12px; background: #1f6feb33; color: #58a6ff; font-weight: 600; }
  .anomaly { padding: 16px; border-radius: 8px; margin-bottom: 12px; font-size: 14px; background: #0d1117; border: 1px solid #30363d; }
  .anomaly strong { display: block; font-size: 16px; margin-bottom: 6px; color: #fff; }
  .INFO { border-left: 4px solid #58a6ff; } .WARN { border-left: 4px solid #e3b341; } .CRITICAL { border-left: 4px solid #f85149; }
</style>
</head>
<body>

<nav class="navbar">
  <div class="nav-brand"><div class="live-indicator"></div> Apex Analytics</div>
  <div class="nav-item active" id="tab-overview" onclick="switchTab('overview')">Overview</div>
  <div class="nav-item" id="tab-funnel" onclick="switchTab('funnel')">Conversion Funnel</div>
  <div class="nav-item" id="tab-zones" onclick="switchTab('zones')">Zone Heatmap</div>
  <div class="nav-item" id="tab-alerts" onclick="switchTab('alerts')">System Alerts</div>
</nav>

<div class="container">
  <div id="page-overview" class="page active">
    <h2>Store Status: STORE_ID_PLACEHOLDER</h2>
    <div class="grid">
      <div class="card"><div class="label">Unique Visitors</div><div class="value blue" id="visitors">-</div></div>
      <div class="card"><div class="label">Conversion Rate</div><div class="value green" id="conversion">-</div></div>
      <div class="card"><div class="label">Avg Dwell (sec)</div><div class="value yellow" id="dwell">-</div></div>
      <div class="card"><div class="label">Queue Depth</div><div class="value orange" id="queue">-</div></div>
    </div>
  </div>

  <div id="page-funnel" class="page">
    <h2>Customer Journey</h2>
    <div class="section" id="funnel-container"><div style="color:#8b949e">Loading data...</div></div>
  </div>

  <div id="page-zones" class="page">
    <h2>Floor Heatmap</h2>
    <div class="section" id="heatmap-container"><div style="color:#8b949e">Loading spatial data...</div></div>
  </div>

  <div id="page-alerts" class="page">
    <h2>Active Anomalies</h2>
    <div class="section" id="anomaly-container"><div style="color:#8b949e">Scanning for anomalies...</div></div>
  </div>
  
  <div style="font-size:12px;color:#8b949e;margin-top:24px;text-align:right" id="lastupdate"></div>
</div>

<script>
const STORE = 'STORE_ID_PLACEHOLDER';
const BASE = window.location.origin;

function switchTab(tabId) {
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + tabId).classList.add('active');
  document.getElementById('page-' + tabId).classList.add('active');
}

function updateMetrics() {
  fetch(BASE + "/stores/" + STORE + "/metrics")
    .then(r => r.json()).then(d => {
      document.getElementById("visitors").textContent = d.unique_visitors ?? 0;
      document.getElementById("conversion").textContent = ((d.conversion_rate || 0) * 100).toFixed(1) + "%";
      document.getElementById("dwell").textContent = Math.round(d.avg_dwell_time_seconds || 0);
      document.getElementById("queue").textContent = d.queue_depth ?? 0;
    }).catch(e => console.log(e));
}

function updateFunnel() {
  fetch(BASE + "/stores/" + STORE + "/funnel")
    .then(r => r.json()).then(d => {
      const f = d.funnel || {};
      const max = f.entries || 1;
      const rows = [
        ["Store Entries", f.entries || 0],
        ["Zone Engagement", f.zone_visits || 0],
        ["Billing Queue", f.billing_queue || 0],
        ["Successful Purchases", f.purchases || 0]
      ];
      document.getElementById("funnel-container").innerHTML = rows.map(([label, val]) => {
        const pct = Math.max(2, Math.round((val / max) * 100));
        return `<div class="funnel-bar"><div class="funnel-label">${label}</div><div class="funnel-track"><div class="funnel-fill" style="width:${pct}%">${val}</div></div></div>`;
      }).join("");
    }).catch(e => console.log(e));
}

function updateHeatmap() {
  fetch(BASE + "/stores/" + STORE + "/heatmap")
    .then(r => r.json()).then(d => {
      if (!d.heatmap || d.heatmap.length === 0) {
        document.getElementById("heatmap-container").innerHTML = "<div style='color:#8b949e'>No zone data available.</div>";
        return;
      }
      document.getElementById("heatmap-container").innerHTML = d.heatmap.map(z =>
        `<div class="heatmap-row">
          <div><strong style="color:#fff;font-size:15px">${z.zone_id}</strong> &nbsp; <span class="badge">${z.visit_count} visitors</span></div>
          <div style="color:#8b949e">${Math.round(z.avg_dwell_ms/1000)}s Avg Dwell</div>
        </div>`
      ).join("");
    }).catch(e => console.log(e));
}

function updateAnomalies() {
  fetch(BASE + "/stores/" + STORE + "/anomalies")
    .then(r => r.json()).then(d => {
      if (!d.anomalies || d.anomalies.length === 0) {
         document.getElementById("anomaly-container").innerHTML = "<div style='color:#3fb950;padding:16px;border:1px solid #238636;border-radius:8px;background:#0d1117'>✅ All systems nominal. No anomalies detected.</div>";
         return;
      }
      document.getElementById("anomaly-container").innerHTML = d.anomalies.map(a =>
        `<div class="anomaly ${a.severity}"><strong>${a.type} <span class="badge" style="float:right;margin-top:-4px">${a.severity}</span></strong><span style="color:#8b949e">${a.suggested_action}</span></div>`
      ).join("");
    }).catch(e => console.log(e));
}

function updateAll() {
  updateMetrics(); updateFunnel(); updateHeatmap(); updateAnomalies();
  document.getElementById("lastupdate").textContent = "Live Feed Updated: " + new Date().toLocaleTimeString();
}

updateAll();
setInterval(updateAll, 3000);
</script>
</body></html>"""
    
    html = html_template.replace("STORE_ID_PLACEHOLDER", store_id)
    return HTMLResponse(content=html)
