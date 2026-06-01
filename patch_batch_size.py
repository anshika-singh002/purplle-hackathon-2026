import re

with open('app/main.py', 'r') as f:
    code = f.read()

# Find the start of the ingest_events function and insert the limit check
pattern = r'(async def ingest_events\(.*?\):)'
replacement = r'\1\n    if len(events) > 500:\n        from fastapi import HTTPException\n        raise HTTPException(status_code=400, detail="Batch size exceeds maximum limit of 500 events")\n'

if "len(events) > 500" not in code:
    code = re.sub(pattern, replacement, code, count=1)
    with open('app/main.py', 'w') as f:
        f.write(code)
    print("✅ SUCCESS: 500-event batch limit strictly enforced!")
else:
    print("✅ Batch limit already exists.")
