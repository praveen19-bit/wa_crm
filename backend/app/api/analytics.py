"""Analytics endpoints."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.conversation import Conversation
from ..models.contact import Contact
from ..models.message import Message
from ..models.user import User
from ..schemas.analytics import AnalyticsOut, DailyPoint, Overview, Stats
from .deps import get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/overview", response_model=Overview)
async def overview(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Overview:
    today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    total_contacts = await db.scalar(
        select(func.count()).select_from(Contact).where(Contact.user_id == user.id)
    )
    total_messages = await db.scalar(
        select(func.count()).select_from(Message).where(Message.user_id == user.id)
    )
    total_conversations = await db.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.user_id == user.id)
    )
    unread = await db.scalar(
        select(func.coalesce(func.sum(Conversation.unread_count), 0)).where(
            Conversation.user_id == user.id, Conversation.is_archived.is_(False)
        )
    )
    today_replies = await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.user_id == user.id, Message.direction == "incoming", Message.timestamp >= today_start)
    )
    active_convs = await db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.user_id == user.id,
            Conversation.is_archived.is_(False),
            Conversation.last_message_at >= (_utcnow() - timedelta(days=7)),
        )
    )
    incoming = await db.scalar(
        select(func.count()).select_from(Message).where(Message.user_id == user.id, Message.direction == "incoming")
    )
    outgoing = await db.scalar(
        select(func.count()).select_from(Message).where(Message.user_id == user.id, Message.direction == "outgoing")
    )

    return Overview(
        total_contacts=total_contacts or 0,
        total_messages=total_messages or 0,
        total_conversations=total_conversations or 0,
        unread_messages=int(unread or 0),
        today_replies=today_replies or 0,
        active_conversations=active_convs or 0,
        incoming_messages=incoming or 0,
        outgoing_messages=outgoing or 0,
    )


@router.get("/daily", response_model=list[DailyPoint])
async def daily_messages(
    days: int = Query(30, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DailyPoint]:
    start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    rows = await db.execute(
        select(
            func.date(Message.timestamp).label("day"),
            Message.direction,
            func.count().label("n"),
        )
        .where(Message.user_id == user.id, Message.timestamp >= start)
        .group_by(func.date(Message.timestamp), Message.direction)
        .order_by(func.date(Message.timestamp))
    )

    by_day: dict[str, dict[str, int]] = {}
    for day, direction, n in rows.all():
        by_day.setdefault(str(day), {"incoming": 0, "outgoing": 0})
        by_day[str(day)][direction] = n

    points: list[DailyPoint] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        key = day.date().isoformat()
        entry = by_day.get(key, {"incoming": 0, "outgoing": 0})
        points.append(DailyPoint(date=key, incoming=entry["incoming"], outgoing=entry["outgoing"]))
    return points


@router.get("/stats", response_model=Stats)
async def stats(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Stats:
    incoming = await db.scalar(
        select(func.count()).select_from(Message).where(Message.user_id == user.id, Message.direction == "incoming")
    )
    outgoing = await db.scalar(
        select(func.count()).select_from(Message).where(Message.user_id == user.id, Message.direction == "outgoing")
    )
    total = (incoming or 0) + (outgoing or 0)
    reply_rate = round((outgoing or 0) / incoming * 100, 1) if incoming else 0.0

    convs = await db.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.user_id == user.id)
    )
    avg_msgs = round(total / convs, 1) if convs else 0.0

    active_7d = await db.scalar(
        select(func.count(func.distinct(Message.contact_id))).where(
            Message.user_id == user.id, Message.timestamp >= (_utcnow() - timedelta(days=7))
        )
    )
    media_count = await db.scalar(
        select(func.count()).select_from(Message).where(
            Message.user_id == user.id, Message.msg_type.in_(["image", "document", "video", "audio"])
        )
    )

    return Stats(
        reply_rate=reply_rate,
        avg_messages_per_conversation=avg_msgs,
        active_contacts_7d=active_7d or 0,
        media_messages=media_count or 0,
    )


@router.get("", response_model=AnalyticsOut)
async def full_analytics(
    days: int = Query(30, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOut:
    return AnalyticsOut(
        overview=await overview(user, db),
        daily=await daily_messages(days, user, db),
        stats=await stats(user, db),
        generated_at=_utcnow(),
    )
