"""Conversation schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from .contact import ContactOut


class ConversationOut(BaseModel):
    id: str
    contact_id: str
    subject: Optional[str] = None
    unread_count: int
    is_active: bool
    is_archived: bool
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    last_message_type: Optional[str] = None
    created_at: datetime
    contact: Optional[ContactOut] = None

    model_config = {"from_attributes": True}
