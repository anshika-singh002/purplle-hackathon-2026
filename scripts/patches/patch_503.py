import re

with open('app/main.py', 'r') as f:
    code = f.read()

# Ensure required libraries are imported
imports_to_add = []
if "from fastapi.responses import JSONResponse" not in code:
    imports_to_add.append("from fastapi.responses import JSONResponse")
if "from fastapi import Request" not in code:
    imports_to_add.append("from fastapi import Request")
if "import sqlite3" not in code:
    imports_to_add.append("import sqlite3")

if imports_to_add:
    code = "\n".join(imports_to_add) + "\n" + code

# The Global 503 Fallback Handlers
exception_handlers = """
@app.exception_handler(sqlite3.Error)
async def db_exception_handler(request: Request, exc: sqlite3.Error):
    return JSONResponse(
        status_code=503, 
        content={"error": "Database unavailable", "message": "A database error occurred while processing the request."}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Let standard HTTP exceptions pass through normally
    if exc.__class__.__name__ == "HTTPException":
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    
    # Catch any other unhandled crash and gracefully degrade to 503
    return JSONResponse(
        status_code=503, 
        content={"error": "Service unavailable", "message": "An unexpected system error occurred."}
    )
"""

if "db_exception_handler" not in code:
    code = code.replace("app = FastAPI()", "app = FastAPI()\n" + exception_handlers)
    with open('app/main.py', 'w') as f:
        f.write(code)
    print("✅ SUCCESS: Global Graceful Degradation (503 Handlers) successfully applied to ALL endpoints!")
else:
    print("✅ Handlers already present.")
