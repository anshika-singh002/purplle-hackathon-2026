import re

with open('app/main.py', 'r') as f:
    code = f.read()

# The old simple count query
pattern = r'c\.execute\("SELECT COUNT\(\*\) FROM pos_transactions WHERE store_id=\?", \(store_id,\)\)'

# The new strict 5-minute rolling window correlation query
new_query = '''c.execute("""
            SELECT COUNT(DISTINCT p.transaction_id) 
            FROM pos_transactions p 
            INNER JOIN events e ON p.store_id = e.store_id 
            WHERE p.store_id = ? 
              AND e.event_type = 'BILLING_QUEUE_JOIN' 
              AND e.is_staff = 0 
              AND (julianday(p.timestamp) - julianday(e.timestamp)) * 1440 >= 0
              AND (julianday(p.timestamp) - julianday(e.timestamp)) * 1440 <= 5
        """, (store_id,))'''

if "SELECT COUNT(*) FROM pos_transactions" in code:
    code = re.sub(pattern, new_query, code)
    with open('app/main.py', 'w') as f:
        f.write(code)
    print("✅ POS time-window correlation successfully injected into app/main.py!")
else:
    print("⚠️ Query already updated or not found.")
