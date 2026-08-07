"""Conversation + message business logic."""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.storage import signed_url
from ..core.websocket_manager import manager
from ..models.conversation import Conversation
from ..models.contact import Contact
from ..models.message import Message
from ..models.user import User
from ..schemas.message import MessageOut

logger = logging.getLogger(__name__)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Return a timezone-aware UTC datetime so clients can render local time.

    SQLite stores naive UTC datetimes; without an explicit offset the browser
    would parse them as local time and show the wrong hour.
    """
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


async def get_or_create_conversation(
    db: AsyncSession,
    user_id: str,
    contact: Contact,
    phone_number_id: Optional[str] = None,
) -> Conversation:
    """Return the active conversation for a contact, creating it if needed."""
    conv = await db.scalar(
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.contact_id == contact.id,
            Conversation.is_archived.is_(False),
        )
        .order_by(Conversation.last_message_at.desc())
        .limit(1)
    )
    if conv:
        return conv
    conv = Conversation(
        user_id=user_id,
        contact_id=contact.id,
        whatsapp_phone_number_id=phone_number_id,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def update_conversation_preview(
    conversation: Conversation, message: Message
) -> None:
    """Refresh the conversation list preview fields after a new message."""
    preview = message.text or message.caption or message.msg_type.capitalize()
    conversation.last_message_preview = (preview or "")[:500]
    conversation.last_message_type = message.msg_type
    conversation.last_message_at = message.timestamp
    if message.direction == "incoming":
        conversation.unread_count = (conversation.unread_count or 0) + 1


async def notify_new_message(db: AsyncSession, message: Message) -> dict:
    """Persist+flush a message, notify connected clients, return serialized payload."""
    message_out = await message_to_out(db, message)
    await manager.send_to_user(
        message.user_id, "message.new", message_out
    )
    await manager.send_to_user(
        message.user_id,
        "conversation.updated",
        {
        "conversation_id": message.conversation_id,
        "unread_count": message.conversation.unread_count if message.conversation else 0,
        "last_message_preview": (
            message.conversation.last_message_preview if message.conversation else None
        ),
        "last_message_at": (
            ensure_utc(message.conversation.last_message_at) if message.conversation else None
        ),
        },
    )
    return message_out


async def message_to_out(db: AsyncSession, message: Message) -> dict:
    """Serialize a message to a plain dict (avoids lazy-load in async contexts)."""
    media = None
    if message.media:
        url = None
        try:
            url = await signed_url(message.media.storage_path)
        except Exception:  # noqa: BLE001 - storage may be unconfigured locally
            url = None
        media = {
            "id": message.media.id,
            "file_name": message.media.file_name,
            "mime_type": message.media.mime_type,
            "size_bytes": message.media.size_bytes,
            "media_type": message.media.media_type,
            "storage_path": message.media.storage_path,
            "created_at": message.media.created_at,
            "url": url,
        }
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "contact_id": message.contact_id,
        "direction": message.direction,
        "msg_type": message.msg_type,
        "text": message.text,
        "caption": message.caption,
        "status": message.status,
        "whatsapp_message_id": message.whatsapp_message_id,
        "timestamp": ensure_utc(message.timestamp),
        "media": media,
    }


async def broadcast_status_update(
    user_id: str,
    conversation_id: str,
    whatsapp_message_id: str,
    status: str,
) -> None:
    await manager.send_to_user(
        user_id,
        "message.updated",
        {
            "conversation_id": conversation_id,
            "whatsapp_message_id": whatsapp_message_id,
            "status": status,
        },
    )
