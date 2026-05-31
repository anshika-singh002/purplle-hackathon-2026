from pydantic import BaseModel, Field, UUID4
from enum import Enum
from typing import Optional
from datetime import datetime

class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REENTRY = "REENTRY"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"

class MetadataModel(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: Optional[int] = 1

class EventModel(BaseModel):
    event_id: UUID4
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: EventType
    timestamp: datetime
    zone_id: Optional[str] = None
    dwell_ms: Optional[int] = 0
    is_staff: Optional[bool] = False
    confidence: Optional[float] = 1.0
    metadata: Optional[MetadataModel] = Field(default_factory=MetadataModel)
