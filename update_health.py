import re

with open('app/main.py', 'r') as file:
    content = file.read()

new_health_endpoint = """@app.get("/health")
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
"""

# Replace the old health endpoint
content = re.sub(r'@app\.get\("/health"\)\s*async def health_check\(\):\s*return \{"status": "healthy"\}', new_health_endpoint, content)

with open('app/main.py', 'w') as file:
    file.write(content)

print("✅ Health endpoint updated with STALE_FEED logic!")
