"""Campaign log — per-contact timeline events for the Live log view."""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .campaign import Campaign
    from .campaign_contact import CampaignContact


class CampaignLog(Base):
    __tablename__ = "campaign_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[str] = mapped_column(
        ForeignKey("campaign_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    campaign: Mapped["Campaign"] = relationship()
    contact: Mapped["CampaignContact"] = relationship()
