"""Campaign message — audit trail of a send attempt for a campaign contact."""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .campaign import Campaign
    from .campaign_contact import CampaignContact


class CampaignMessage(Base):
    __tablename__ = "campaign_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[str] = mapped_column(
        ForeignKey("campaign_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    whatsapp_message_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    msg_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # sent|delivered|read|failed|skipped
    error_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    campaign: Mapped["Campaign"] = relationship()
    contact: Mapped["CampaignContact"] = relationship(
        back_populates="messages",
        primaryjoin="CampaignContact.id==CampaignMessage.contact_id",
    )
