"""Campaign queue row — a single unit of work for the queue worker."""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .campaign import Campaign
    from .campaign_contact import CampaignContact


class CampaignQueue(Base):
    __tablename__ = "campaign_queue"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[str] = mapped_column(
        ForeignKey("campaign_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    campaign: Mapped["Campaign"] = relationship()
    contact: Mapped["CampaignContact"] = relationship()
