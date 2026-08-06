"""Pydantic schemas package."""
from .auth import LoginRequest, RegisterRequest, Token, UserOut, PasswordUpdate
from .contact import (
    ContactCreate,
    ContactOut,
    ContactUpdate,
    TagAssignRequest,
    NoteCreate,
    NoteOut,
)
from .tag import TagCreate, TagOut
from .conversation import ConversationOut
from .message import MessageCreate, MessageOut, SendMessageResponse
from .media import MediaOut, UploadResponse
from .analytics import Overview, DailyPoint, Stats, AnalyticsOut
from .settings import SettingsOut, SettingsUpdate

__all__ = [
    "LoginRequest",
    "RegisterRequest",
    "Token",
    "UserOut",
    "PasswordUpdate",
    "ContactCreate",
    "ContactOut",
    "ContactUpdate",
    "TagAssignRequest",
    "NoteCreate",
    "NoteOut",
    "TagCreate",
    "TagOut",
    "ConversationOut",
    "MessageCreate",
    "MessageOut",
    "SendMessageResponse",
    "MediaOut",
    "UploadResponse",
    "Overview",
    "DailyPoint",
    "Stats",
    "AnalyticsOut",
    "SettingsOut",
    "SettingsUpdate",
]
