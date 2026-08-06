"""Message sending + search endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.whatsapp import WhatsAppClient, WhatsAppError
from ..database import get_db
from ..models.conversation import Conversation
from ..models.media import MediaFile
from ..models.message import Message
from ..models.setting import Setting
from ..models.user import User
from ..schemas.message import MessageCreate, MessageOut
from ..services.messaging import message_to_out, notify_new_message, update_conversation_preview
from .deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Messages"])


async def _load_wa(user: User, db: AsyncSession, phone_number_id: Optional[str] = None) -> WhatsAppClient:
    setting = await db.scalar(select(Setting).where(Setting.user_id == user.id))
    token = (setting.whatsapp_access_token if setting else None) or ""
    pnid = phone_number_id or (setting.whatsapp_phone_number_id if setting else "") or ""
    if not token or not pnid:
        raise HTTPException(
            status_code=400,
            detail="WhatsApp Cloud API is not configured. Add your credentials in Settings.",
        )
    try:
        return WhatsAppClient(token, pnid)
    except WhatsAppError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


async def _find_media(db: AsyncSession, user_id: str, media_id: str) -> MediaFile:
    media = await db.get(MediaFile, media_id)
    if not media or media.user_id != user_id:
        raise HTTPException(status_code=404, detail="Media file not found")
    return media


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut)
async def send_message(
    conversation_id: str,
    payload: MessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    media: Optional[MediaFile] = None
    caption = payload.caption

    if payload.type in {"image", "document", "video", "audio"}:
        if not payload.media_id:
            raise HTTPException(status_code=422, detail="media_id is required for media messages")
        media = await _find_media(db, user.id, payload.media_id)

    wa = await _load_wa(user, db, conv.whatsapp_phone_number_id)
    try:
        if payload.type == "text":
            if not payload.text:
                raise HTTPException(status_code=422, detail="Text message cannot be empty")
            wa_id = await wa.send_text(conv.contact.phone, payload.text)
        else:
            # For outbound media we must upload to Meta from our stored bytes.
            from ..core.storage import download_file

            stored = await download_file(media.storage_path)
            meta_media_id = await wa.upload_media(
                stored, media.mime_type, media.file_name
            )
            if payload.type == "image":
                wa_id = await wa.send_image(conv.contact.phone, meta_media_id, caption)
            elif payload.type == "document":
                wa_id = await wa.send_document(
                    conv.contact.phone, meta_media_id, caption, media.file_name
                )
            elif payload.type == "video":
                wa_id = await wa.send_video(conv.contact.phone, meta_media_id, caption)
            else:  # audio
                wa_id = await wa.send_audio(conv.contact.phone, meta_media_id)
    except WhatsAppError as exc:
        logger.error("WhatsApp send failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"WhatsApp send failed: {exc}")
    finally:
        await wa.aclose()

    message = Message(
        user_id=user.id,
        conversation_id=conversation_id,
        contact_id=conv.contact_id,
        direction="outgoing",
        msg_type=payload.type,
        text=payload.text if payload.type == "text" else caption,
        caption=caption,
        media_id=media.id if media else None,
        whatsapp_message_id=wa_id,
        status="sent",
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    await update_conversation_preview(conv, message)
    await db.commit()

    return await message_to_out(db, message)


@router.get("/messages/search", response_model=list[MessageOut])
async def search_messages(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    like = f"%{q.strip()}%"
    result = await db.execute(
        select(Message)
        .where(Message.user_id == user.id, or_(Message.text.ilike(like), Message.caption.ilike(like)))
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [await message_to_out(db, m) for m in messages]
