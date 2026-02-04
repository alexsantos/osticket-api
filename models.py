from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# --- Request Models ---
class TicketCreate(BaseModel):
    name: str
    email: str
    subject: str
    message: str
    topic_id: int = 1


class ReplyCreate(BaseModel):
    ticket_id: int
    name: str
    message: str
    is_staff: bool = False


# --- Response Models ---
class HealthResponse(BaseModel):
    status: str
    database: str


class TopicResponse(BaseModel):
    topic_id: int
    topic: str
    ispublic: int


class DepartmentResponse(BaseModel):
    id: int
    name: str


class StatusResponse(BaseModel):
    id: int
    name: str
    state: str


class TicketItem(BaseModel):
    ticket_id: int
    number: str
    created: datetime
    status_name: str
    topic_name: Optional[str] = None
    dept_name: Optional[str] = None
    owner_name: str
    email: str


class PaginatedTicketResponse(BaseModel):
    total: int
    limit: int
    offset: int
    next: Optional[str] = None
    previous: Optional[str] = None
    items: List[TicketItem]


class TicketCreateResponse(BaseModel):
    ticket_id: int
    number: str


class AttachmentResponse(BaseModel):
    file_id: int


class CloseResponse(BaseModel):
    status: str
