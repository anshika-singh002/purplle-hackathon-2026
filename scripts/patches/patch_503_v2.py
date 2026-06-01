with open('app/main.py', 'r') as f:
    code = f.read()

new_handlers = """
# --- GRACEFUL DEGRADATION HANDLERS ---
import sqlite3
from fastapi.responses import JSONResponse
from fastapi import Request

@app.exception_handler(sqlite3.Error)
async def db_exception_handler(request: Request, exc: sqlite3.Error):
    return JSONResponse(
        status_code=503, 
        content={"error": "Database unavailable", "message": "A database error occurred while processing the request."}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if exc.__class__.__name__ == "HTTPException":
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(
        status_code=503, 
        content={"error": "Service unavailable", "message": "An unexpected system error occurred."}
    )
"""

if "db_exception_handler" not in code:
    with open('app/main.py', 'a') as f:
        f.write("\n" + new_handlers)
    print("✅ SUCCESS: 503 Handlers forcefully stapled to the bottom of main.py!")
else:
    print("✅ Handlers already present.")
