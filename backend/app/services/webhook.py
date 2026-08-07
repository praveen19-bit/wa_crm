"""WhatsApp webhook payload processor.

Routes incoming messages to the user that owns the target phone number,
upserts contacts, stores media, persists messages, broadcasts over WS and
optionally triggers auto-replies.
"""
import logging
import mimetypes
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.storage import upload_file
from ..core.whatsapp import WhatsAppClient, WhatsAppError
from ..models.contact import Contact
from ..models.conversation import Conversation
from ..models.media import MediaFile
from ..models.message import Message
from ..models.setting import Setting
from ..models.user import User
from .media import build_storage_path, detect_media_type
from .messaging import (
    broadcast_status_update,
    get_or_create_conversation,
    notify_new_message,
    update_conversation_preview,
)

logger = logging.getLogger(__name__)


async def find_user_by_phone_number(db: AsyncSession, phone_number_id: str) -> Optional[tuple[User, Setting]]:
    setting = await db.scalar(
        select(Setting).where(Setting.whatsapp_phone_number_id == phone_number_id)
    )
    if not setting:
        return None
    user = await db.get(User, setting.user_id)
    return (user, setting) if user else None


def normalize_phone(raw: str) -> str:
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def _media_extension(mime_type: str, fallback: str) -> str:
    ext = mimetypes.guess_extension(mime_type or "") or ""
    ext = ext.lstrip(".") if ext else ""
    return ext or fallback


async def _upsert_contact(
    db: AsyncSession, user_id: str, wa_id: str, profile_name: Optional[str]
) -> Contact:
    phone = normalize_phone(wa_id)
    contact = await db.scalar(
        select(Contact).where(Contact.user_id == user_id, Contact.phone == phone)
    )
    if not contact:
        contact = Contact(
            user_id=user_id,
            phone=phone,
            name=(profile_name or "").strip() or None,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)
    elif profile_name and not contact.name:
        contact.name = profile_name.strip()
        await db.commit()
        await db.refresh(contact)
    return contact


async def _store_incoming_media(
    wa_client: WhatsAppClient,
    user_id: str,
    media_id: str,
    mime_type: str,
    file_name: str,
    conversation_id: str,
) -> Optional[MediaFile]:
    """Download media from Meta and persist into storage."""
    media_type = detect_media_type(file_name, mime_type)
    try:
        raw = await wa_client.download_media(media_id)
        path = build_storage_path(user_id, media_type, file_name)
        await upload_file(path=path, file_bytes=raw, mime_type=mime_type)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Media download failed (%s): %s", media_id, exc)
        return None

    media = MediaFile(
        user_id=user_id,
        conversation_id=conversation_id,
        storage_path=path,
        file_name=file_name,
        mime_type=mime_type,
        size_bytes=len(raw),
        media_type=media_type,
    )
    return media


async def _process_incoming_message(
    db: AsyncSession,
    user: User,
    contact: Contact,
    conversation: Conversation,
    message_payload: dict,
) -> None:
    """Handle a single incoming message object from the webhook."""
    msg_id = message_payload.get("id") or ""
    exists = await db.scalar(
        select(Message.id).where(Message.whatsapp_message_id == msg_id)
    )
    if exists:
        logger.info("Duplicate incoming message ignored: %s", msg_id)
        return

    msg_type = message_payload.get("type", "text")
    text = None
    caption = None
    media_obj = None
    mime_type = "text/plain"

    if msg_type == "text":
        text = (message_payload.get("text") or {}).get("body")
    elif msg_type in ("image", "sticker"):
        data = message_payload.get(msg_type) or {}
        text = data.get("caption")
        mime_type = data.get(
            "mime_type", "image/webp" if msg_type == "sticker" else "image/jpeg"
        )
        file_name = f"{msg_type}_{msg_id[-8:]}.{_media_extension(mime_type, 'webp' if msg_type == 'sticker' else 'jpg')}"
    elif msg_type in ("document", "video", "audio"):
        data = message_payload.get(msg_type) or {}
        text = data.get("caption")
        mime_type = data.get("mime_type", "application/octet-stream")
        file_name = data.get("filename") or f"{msg_type}_{msg_id[-8:]}.{_media_extension(mime_type, 'bin')}"

    if msg_type != "text":
        media_meta_id = (message_payload.get(msg_type) or {}).get("id")
        if media_meta_id:
            settings_row = await db.scalar(
                select(Setting).where(Setting.user_id == user.id)
            )
            token = (settings_row.whatsapp_access_token if settings_row else None) or ""
            pnid = conversation.whatsapp_phone_number_id or (
                settings_row.whatsapp_phone_number_id if settings_row else ""
            )
            try:
                wa = WhatsAppClient(token, pnid)
                media_obj = await _store_incoming_media(
                    wa, user.id, media_meta_id, mime_type, file_name, conversation.id
                )
                await wa.aclose()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Incoming media skipped: %s", exc)

    message = Message(
        user_id=user.id,
        conversation_id=conversation.id,
        contact_id=contact.id,
        direction="incoming",
        msg_type=msg_type,
        text=text,
        caption=caption,
        whatsapp_message_id=msg_id,
        media=media_obj,
        status="received",
    )
    if media_obj:
        db.add(media_obj)
    db.add(message)
    await db.commit()
    await db.refresh(message)

    await update_conversation_preview(conversation, message)
    await db.commit()

    await notify_new_message(db, message)
    logger.info("Incoming message saved: %s", msg_id)


async def _handle_status_update(db: AsyncSession, user: User, status_payload: dict) -> None:
    """Update sent/delivered/read status for an outgoing message."""
    wa_id = status_payload.get("id") or ""
    status = (status_payload.get("status") or "").lower()
    message = await db.scalar(
        select(Message).where(Message.whatsapp_message_id == wa_id)
    )
    if not message or status not in {"sent", "delivered", "read", "failed"}:
        return
    message.status = status
    await db.commit()
    # Update the existing message in place — do NOT broadcast message.new
    await broadcast_status_update(
        user.id, message.conversation_id, message.whatsapp_message_id, status
    )


async def _auto_reply(
    db: AsyncSession, user: User, setting: Setting, contact: Contact, conversation: Conversation
) -> None:
    if not (setting and setting.auto_reply_enabled and setting.auto_reply_text):
        return
    try:
        wa = WhatsAppClient(setting.whatsapp_access_token or "", setting.whatsapp_phone_number_id or "")
        wa_id = await wa.send_text(contact.phone, setting.auto_reply_text)
        await wa.aclose()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Auto-reply failed: %s", exc)
        return

    message = Message(
        user_id=user.id,
        conversation_id=conversation.id,
        contact_id=contact.id,
        direction="outgoing",
        msg_type="text",
        text=setting.auto_reply_text,
        whatsapp_message_id=wa_id,
        status="sent",
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    await update_conversation_preview(conversation, message)
    await db.commit()
    await notify_new_message(db, message)


async def process_webhook_payload(db: AsyncSession, payload: dict) -> dict:
    """Entry point for POST /api/webhook/whatsapp."""
    counts = {"messages": 0, "statuses": 0, "errors": 0}

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}

            for status_item in value.get("statuses", []):
                counts["statuses"] += 1
                phone_number_id = value.get("metadata", {}).get("phone_number_id") or ""
                resolved = await find_user_by_phone_number(db, phone_number_id)
                if resolved:
                    await _handle_status_update(db, resolved[0], status_item)

            messages = value.get("messages", [])
            if not messages:
                continue

            phone_number_id = value.get("metadata", {}).get("phone_number_id") or ""
            resolved = await find_user_by_phone_number(db, phone_number_id)
            if not resolved:
                logger.warning("No user configured for phone_number_id=%s", phone_number_id)
                counts["errors"] += 1
                continue

            user, setting = resolved
            contacts_raw = value.get("contacts", [{}])
            profile_name = (contacts_raw[0].get("profile") or {}).get("name") if contacts_raw else None

            for raw in messages:
                wa_id = raw.get("from", "")
                contact = await _upsert_contact(db, user.id, wa_id, profile_name)
                conversation = await get_or_create_conversation(
                    db, user.id, contact, phone_number_id
                )
                await _process_incoming_message(db, user, contact, conversation, raw)
                counts["messages"] += 1
                await _auto_reply(db, user, setting, contact, conversation)

    return counts
