from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# --- Request Models ---
class TicketCreate(BaseModel):
    user_id: int
    subject: str
    message: str
    topic_id: Optional[int] = None
    dept_id: Optional[int] = None


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


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    created: datetime
    updated: datetime


class PaginatedUserResponse(BaseModel):
    total: int
    limit: int
    offset: int
    next: Optional[str] = None
    previous: Optional[str] = None
    items: List[UserResponse]


class TicketItem(BaseModel):
    ticket_id: int
    number: str
    created: datetime
    status_id: int
    status_name: str
    topic_id: Optional[int] = None
    topic_name: Optional[str] = None
    dept_id: Optional[int] = None
    dept_name: Optional[str] = None
    user_id: int
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
