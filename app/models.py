from pydantic import BaseModel
from typing import Optional

class Attachment(BaseModel):
    filename: str
    content_b64: str
    content_type: Optional[str] = "application/octet-stream"

class SendRequest(BaseModel):
    from_agent: str
    to_agent: str
    message: str
    thread_id: Optional[str] = None
    attachments: Optional[list[Attachment]] = None

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
    attachments: Optional[list[Attachment]] = None

class AckResponse(BaseModel):
    status: str

class HealthResponse(BaseModel):
    status: str
    version: str


class ReportCreateRequest(BaseModel):
    title: str
    html: str
    ttl_hours: Optional[int] = 168


class ReportCreateResponse(BaseModel):
    slug: str
    url: str
    expires_at: Optional[str] = None
