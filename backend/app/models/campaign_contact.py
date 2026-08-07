"""Campaign contact (a single lead / recipient row)."""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .campaign import Campaign
    from .campaign_message import CampaignMessage


class CampaignContact(Base):
    __tablename__ = "campaign_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    whatsapp_message_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="contacts")
    messages: Mapped[list["CampaignMessage"]] = relationship(
        back_populates="contact",
        primaryjoin="CampaignContact.id==CampaignMessage.contact_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
