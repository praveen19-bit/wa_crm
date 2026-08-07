"""Schemas for the Cold DM Campaign module."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ----------------------------------------------------------------- config
class CampaignConfig(BaseModel):
    min_delay_seconds: int = 20
    max_delay_seconds: int = 45
    typing_enabled: bool = False
    typing_min_seconds: int = 2
    typing_max_seconds: int = 5
    working_hours_enabled: bool = False
    work_start_time: Optional[str] = None
    work_end_time: Optional[str] = None
    timezone_name: Optional[str] = None
    daily_limit: Optional[int] = None
    retry_enabled: bool = False
    retry_count: int = 1
    retry_delay_seconds: int = 120
    skip_duplicates: bool = True
    skip_blocked: bool = True
    skip_contacted: bool = False


# ----------------------------------------------------------------- templates
class TemplateBase(BaseModel):
    name: str
    body: str
    is_favorite: bool = False


class TemplateCreate(TemplateBase):
    pass


class TemplateOut(TemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------- blacklist
class BlacklistEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    phone: str
    reason: Optional[str] = None
    created_at: datetime


# ----------------------------------------------------------------- campaigns
class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    campaign_type: str = "cold_outreach"
    message_text: Optional[str] = None
    media_id: Optional[str] = None
    config: CampaignConfig = Field(default_factory=CampaignConfig)
    scheduled_at: Optional[datetime] = None


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    campaign_type: str
    message_text: Optional[str] = None
    media_id: Optional[str] = None
    status: str
    min_delay_seconds: int = 20
    max_delay_seconds: int = 45
    typing_enabled: bool = False
    typing_min_seconds: int = 2
    typing_max_seconds: int = 5
    working_hours_enabled: bool = False
    work_start_time: Optional[Any] = None
    work_end_time: Optional[Any] = None
    timezone_name: Optional[str] = None
    daily_limit: Optional[int] = None
    retry_enabled: bool = False
    retry_count: int = 1
    retry_delay_seconds: int = 120
    skip_duplicates: bool = True
    skip_blocked: bool = True
    skip_contacted: bool = False
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    sent_count: int = 0
    failed_count: int = 0
    reply_count: int = 0
    skip_count: int = 0
    created_at: datetime
    updated_at: datetime

    # populated dynamically by the API (not columns)
    contact_count: int = 0
    media: Optional[Any] = None


class CampaignProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    campaign: CampaignOut
    contact_count: int = 0
    pending: int = 0
    sending: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    retrying: int = 0
    replied: int = 0
    current: Optional[Any] = None


# ----------------------------------------------------------------- leads / upload
class LeadPreviewRow(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    status: str = "valid"
    reason: Optional[str] = None


class LeadPreview(BaseModel):
    headers: list[str] = Field(default_factory=list)
    mapping: dict[str, Any] = Field(default_factory=dict)
    rows: list[LeadPreviewRow] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class SendTestRequest(BaseModel):
    phone: str
    body: str
    media_type: Optional[str] = None
    media_public_id: Optional[str] = None


class SendTestResponse(BaseModel):
    ok: bool
    wa_id: str
    error: Optional[str] = None
