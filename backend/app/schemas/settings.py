"""Settings schemas."""
from typing import Optional

from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    whatsapp_access_token: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_business_account_id: Optional[str] = None
    webhook_verify_token: Optional[str] = None
    business_name: Optional[str] = None
    business_phone: Optional[str] = None
    auto_reply_enabled: bool = False
    auto_reply_text: Optional[str] = None
    webhook_configured: bool = False

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    whatsapp_access_token: Optional[str] = Field(default=None, max_length=1000)
    whatsapp_phone_number_id: Optional[str] = Field(default=None, max_length=64)
    whatsapp_business_account_id: Optional[str] = Field(default=None, max_length=64)
    webhook_verify_token: Optional[str] = Field(default=None, max_length=255)
    business_name: Optional[str] = Field(default=None, max_length=120)
    business_phone: Optional[str] = Field(default=None, max_length=32)
    auto_reply_enabled: Optional[bool] = None
    auto_reply_text: Optional[str] = Field(default=None, max_length=1000)
