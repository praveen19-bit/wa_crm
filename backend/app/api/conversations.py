"""Conversation endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.websocket_manager import manager
from ..database import get_db
from ..models.conversation import Conversation
from ..models.contact import Contact
from ..models.message import Message
from ..models.user import User
from ..schemas.conversation import ConversationOut
from ..schemas.message import MessageOut
from ..services.messaging import ensure_utc, message_to_out
from .deps import get_current_user

router = APIRouter(prefix="/conversations", tags=["Conversations"])


def _conv_out(conv: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        contact_id=conv.contact_id,
        subject=conv.subject,
        unread_count=conv.unread_count,
        is_active=conv.is_active,
        is_archived=conv.is_archived,
        last_message_at=ensure_utc(conv.last_message_at),
        last_message_preview=conv.last_message_preview,
        last_message_type=conv.last_message_type,
        created_at=ensure_utc(conv.created_at),
        contact=conv.contact,
    )


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    search: Optional[str] = Query(None),
    archived: bool = Query(False),
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationOut]:
    query = (
        select(Conversation)
        .join(Contact, Conversation.contact_id == Contact.id)
        .where(Conversation.user_id == user.id)
    )
    if not archived:
        query = query.where(Conversation.is_archived.is_(False))
    if unread_only:
        query = query.where(Conversation.unread_count > 0)
    if search and search.strip():
        like = f"%{search.strip()}%"
        query = query.where(
            or_(
                Contact.name.ilike(like),
                Contact.phone.ilike(like),
                Conversation.last_message_preview.ilike(like),
            )
        )

    result = await db.execute(
        query.order_by(Conversation.last_message_at.desc().nullslast())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return [_conv_out(c) for c in result.scalars().all()]


@router.get("/counts", response_model=dict)
async def conversation_counts(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    total = await db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.user_id == user.id, Conversation.is_archived.is_(False))
    )
    unread = await db.scalar(
        select(func.coalesce(func.sum(Conversation.unread_count), 0)).where(
            Conversation.user_id == user.id, Conversation.is_archived.is_(False)
        )
    )
    return {"total": total or 0, "unread": int(unread or 0)}


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conv_out(conv)


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    contact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    contact = await db.get(Contact, contact_id)
    if not contact or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    existing = await db.scalar(
        select(Conversation).where(
            Conversation.user_id == user.id,
            Conversation.contact_id == contact_id,
            Conversation.is_archived.is_(False),
        )
    )
    if existing:
        return _conv_out(existing)
    conv = Conversation(user_id=user.id, contact_id=contact_id)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return _conv_out(conv)


@router.post("/{conversation_id}/read", response_model=ConversationOut)
async def mark_read(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.unread_count = 0
    await db.commit()
    await db.refresh(conv)
    await manager.send_to_user(user.id, "conversation.read", {"conversation_id": conv.id})
    return _conv_out(conv)


@router.put("/{conversation_id}/archive", response_model=ConversationOut)
async def toggle_archive(
    conversation_id: str,
    archived: bool = True,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.is_archived = archived
    await db.commit()
    await db.refresh(conv)
    return _conv_out(conv)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_conversation_messages(
    conversation_id: str,
    before: Optional[str] = Query(None, description="ISO timestamp for pagination"),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    query = (
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.user_id == user.id)
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    messages = list(reversed(result.scalars().all()))

    return [await message_to_out(db, m) for m in messages]
