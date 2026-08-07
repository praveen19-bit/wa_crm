"""Campaign model — a cold DM outreach run."""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .media import MediaFile


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    campaign_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="cold_outreach"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", index=True
    )
    message_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True
    )
    min_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    max_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    typing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    typing_min_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    typing_max_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    working_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    work_start_time: Mapped[Optional[Time]] = mapped_column(Time, nullable=True)
    work_end_time: Mapped[Optional[Time]] = mapped_column(Time, nullable=True)
    timezone_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    daily_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retry_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_delay_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=120
    )
    skip_duplicates: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    skip_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    skip_contacted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skip_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    contacts: Mapped[list["CampaignContact"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", lazy="selectin"
    )
    followups: Mapped[list["CampaignFollowup"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", lazy="selectin"
    )
    media: Mapped[Optional["MediaFile"]] = relationship(lazy="joined")
