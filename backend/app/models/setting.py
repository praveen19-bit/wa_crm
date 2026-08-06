"""Settings model - per-user WhatsApp integration config."""
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin


class Setting(TimestampMixin, Base):
    __tablename__ = "settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )

    # Meta / WhatsApp Cloud API credentials
    whatsapp_access_token: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    whatsapp_business_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    webhook_verify_token: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Display
    business_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    business_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Preferences
    auto_reply_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_reply_text: Mapped[str | None] = mapped_column(String(1000), nullable=True)
