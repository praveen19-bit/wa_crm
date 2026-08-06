"""Analytics schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Overview(BaseModel):
    total_contacts: int
    total_messages: int
    total_conversations: int
    unread_messages: int
    today_replies: int
    active_conversations: int
    outgoing_messages: int
    incoming_messages: int


class DailyPoint(BaseModel):
    date: str
    incoming: int
    outgoing: int


class Stats(BaseModel):
    reply_rate: float
    avg_messages_per_conversation: float
    active_contacts_7d: int
    media_messages: int


class AnalyticsOut(BaseModel):
    overview: Overview
    daily: list[DailyPoint]
    stats: Stats
    generated_at: datetime
