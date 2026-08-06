"""Message model."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contact_id: Mapped[str] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), index=True, nullable=False
    )

    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # incoming | outgoing
    msg_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)  # text|image|document|video|audio
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Meta message ID (for status updates & dedup)
    whatsapp_message_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    media_id: Mapped[str | None] = mapped_column(
        ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="sent", nullable=False)  # sent|delivered|read|failed

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")  # noqa: F821
    media: Mapped["MediaFile | None"] = relationship(lazy="selectin")  # noqa: F821
