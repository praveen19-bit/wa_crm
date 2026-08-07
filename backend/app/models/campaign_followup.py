"""Campaign follow-up message — a step in a follow-up sequence."""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .campaign import Campaign
    from .media import MediaFile


class CampaignFollowup(Base):
    __tablename__ = "campaign_followups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=172800)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    media_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True
    )
    stop_on_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="followups")
    media: Mapped[Optional["MediaFile"]] = relationship(lazy="joined")
