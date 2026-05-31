import json
import uuid
from datetime import datetime, timezone

def generate_event(store_id, camera_id, visitor_id, event_type, 
                   zone_id=None, dwell_ms=0, is_staff=False, 
                   confidence=1.0, queue_depth=None, sku_zone=None, session_seq=1):
    """
    Formats a tracking event strictly to the Apex Retail API Schema.
    """
    event = {
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": camera_id,
        "visitor_id": f"VIS_{visitor_id}",
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": round(float(confidence), 2),
        "metadata": {
            "queue_depth": queue_depth,
            "sku_zone": sku_zone,
            "session_seq": session_seq
        }
    }
    return event

def emit_to_stdout(event):
    """Prints event as a single-line JSON string (JSONL format)"""
    print(json.dumps(event))

def append_to_jsonl(event, filepath="output/events.jsonl"):
    """Appends event to a JSONL file for batch processing"""
    with open(filepath, "a") as f:
        f.write(json.dumps(event) + "\n")
