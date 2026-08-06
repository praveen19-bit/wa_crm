"""Message schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .media import MediaOut

ALLOWED_TYPES = {"text", "image", "document", "video", "audio"}


class MessageCreate(BaseModel):
    type: str = Field(default="text", pattern="^(text|image|document|video|audio)$")
    text: Optional[str] = Field(default=None, max_length=4000)
    caption: Optional[str] = Field(default=None, max_length=1000)
    media_id: Optional[str] = None

    @property
    def kind(self) -> str:
        return self.type


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    contact_id: str
    direction: str
    msg_type: str
    text: Optional[str] = None
    caption: Optional[str] = None
    status: str
    whatsapp_message_id: Optional[str] = None
    timestamp: datetime
    media: Optional[MediaOut] = None

    model_config = {"from_attributes": True}


class SendMessageResponse(BaseModel):
    ok: bool = True
    message: MessageOut
    whatsapp_id: Optional[str] = None
