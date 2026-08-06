"""Contact, note schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from .tag import TagOut


class ContactCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    phone: str = Field(min_length=6, max_length=32)
    email: Optional[EmailStr] = None
    company: Optional[str] = Field(default=None, max_length=255)
    avatar_url: Optional[str] = None


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, min_length=6, max_length=32)
    email: Optional[EmailStr] = None
    company: Optional[str] = Field(default=None, max_length=255)
    avatar_url: Optional[str] = None


class ContactOut(BaseModel):
    id: str
    name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    company: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    tags: list[TagOut] = []
    unread_count: int = 0
    last_message_preview: Optional[str] = None
    last_message_at: Optional[datetime] = None
    conversation_id: Optional[str] = None

    model_config = {"from_attributes": True}


class TagAssignRequest(BaseModel):
    tag_ids: list[str]


class NoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class NoteOut(BaseModel):
    id: str
    contact_id: str
    content: str
    author_name: str
    created_at: datetime

    model_config = {"from_attributes": True}
