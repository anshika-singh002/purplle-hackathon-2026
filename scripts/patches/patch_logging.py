import re

with open('app/main.py', 'r') as f:
    code = f.read()

if "structured_logging_middleware" not in code:
    # Ensure Request is imported for the middleware
    if "from fastapi import Request" not in code:
        code = "from fastapi import Request\n" + code
        
    middleware_code = """
import time, uuid, json, logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("apex_logger")

@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Process the request
    response = await call_next(request)
    
    # Calculate latency
    latency_ms = round((time.time() - start_time) * 1000, 2)
    
    # Extract store_id from URL if present
    store_id = None
    parts = request.url.path.strip('/').split('/')
    if len(parts) >= 2 and parts[0] == 'stores':
        store_id = parts[1]
        
    # Extract event_count (passed securely from the ingest endpoint)
    event_count = getattr(request.state, "event_count", 0)
    
    # Build the structured log exactly as requested
    log_dict = {
        "trace_id": trace_id,
        "store_id": store_id,
        "endpoint": request.url.path,
        "latency_ms": latency_ms,
        "event_count": event_count,
        "status_code": response.status_code
    }
    logger.info(json.dumps(log_dict))
    
    return response
"""
    # 1. Inject the middleware right after app initialization
    code = code.replace("app = FastAPI()", "app = FastAPI()\n" + middleware_code)
    
    # 2. Inject `request: Request` into the ingest endpoint so it can pass the event_count
    code = re.sub(r'async def ingest_events\((.*?)\):', r'async def ingest_events(\1, request: Request):\n    request.state.event_count = len(events)', code)
    
    with open('app/main.py', 'w') as f:
        f.write(code)
    print("✅ SUCCESS: Structured logging middleware securely injected!")
else:
    print("✅ Middleware already exists.")
