from pydantic import BaseModel
from typing import Optional

class SendRequest(BaseModel):
    from_agent: str
    to_agent: str
    message: str
    thread_id: Optional[str] = None

class SendResponse(BaseModel):
    message_id: str
    status: str

class MessageRecord(BaseModel):
    id: str
    from_agent: str
    to_agent: str
    message: str
    thread_id: Optional[str]
    created_at: str
    read: bool

class AckResponse(BaseModel):
    status: str

class HealthResponse(BaseModel):
    status: str
    version: str
