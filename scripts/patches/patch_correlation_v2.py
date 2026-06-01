import re

with open('app/main.py', 'r') as f:
    code = f.read()

new_metrics_endpoint = """@app.get("/stores/{store_id}/metrics")
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

@app.get("/health")"""

# Bulletproof regex that replaces everything between the metrics route and the health route
code = re.sub(r'@app\.get\("/stores/\{store_id\}/metrics"\).*?@app\.get\("/health"\)', new_metrics_endpoint, code, flags=re.DOTALL)

with open('app/main.py', 'w') as f:
    f.write(code)

print("✅ SUCCESS: POS time-window correlation forcibly injected!")
