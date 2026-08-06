"""Tag model."""
from uuid import uuid4

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin
from .contact import contact_tags


class Tag(TimestampMixin, Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#6366f1", nullable=False)

    contacts: Mapped[list["Contact"]] = relationship(  # noqa: F821
        secondary=contact_tags, back_populates="tags", lazy="selectin"
    )
