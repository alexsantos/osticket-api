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


class NoteCreate(BaseModel):
    body: str
    title: Optional[str] = None
    poster: Optional[str] = "API"


class StatusUpdateRequest(BaseModel):
    status_id: int


class DepartmentUpdateRequest(BaseModel):
    dept_id: int


class TeamUpdateRequest(BaseModel):
    team_id: int


class MessageUpdateRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None


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


class TeamResponse(BaseModel):
    team_id: int
    name: str


class MessagesResponse(BaseModel):
    ticket_id: int
    thread_id: int
    entry_id: int
    staff_id: Optional[int] = None
    user_id: Optional[int] = None
    type: str
    poster: str
    editor: Optional[int] = None
    editor_type: Optional[str] = None
    source: Optional[str] = None
    format: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None
    created: datetime
    updated: datetime


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
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    user_id: int
    user_name: str
    user_email: str
    subject: Optional[str] = None
    message: Optional[str] = None
    closed: Optional[datetime] = None
    custom_fields: Optional[dict] = None


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


class AttachmentsResponse(BaseModel):
    ticket_id: int
    attachment_id: int
    file_id: int
    thread_id: int
    entry_id: int
    name: str
    type: str
    size: int
    inline: int
    created: datetime
    content: str


class NoteResponse(BaseModel):
    entry_id: int


class CloseResponse(BaseModel):
    status: str


class UpdateResponse(BaseModel):
    status: str
