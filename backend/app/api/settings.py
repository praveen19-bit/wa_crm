"""User settings endpoints (WhatsApp integration config)."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.whatsapp import WhatsAppClient, WhatsAppError
from ..database import get_db
from ..models.setting import Setting
from ..models.user import User
from ..schemas.settings import SettingsOut, SettingsUpdate
from .deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])


async def _get_or_create(db: AsyncSession, user_id: str) -> Setting:
    setting = await db.scalar(select(Setting).where(Setting.user_id == user_id))
    if not setting:
        setting = Setting(user_id=user_id)
        db.add(setting)
        await db.commit()
        await db.refresh(setting)
    return setting


def _out(setting: Setting) -> SettingsOut:
    return SettingsOut(
        whatsapp_access_token=(
            (setting.whatsapp_access_token[:6] + "..." + setting.whatsapp_access_token[-4:])
            if setting.whatsapp_access_token else None
        ),
        whatsapp_phone_number_id=setting.whatsapp_phone_number_id,
        whatsapp_business_account_id=setting.whatsapp_business_account_id,
        webhook_verify_token=setting.webhook_verify_token,
        business_name=setting.business_name,
        business_phone=setting.business_phone,
        auto_reply_enabled=setting.auto_reply_enabled,
        auto_reply_text=setting.auto_reply_text,
        webhook_configured=bool(
            setting.whatsapp_access_token and setting.whatsapp_phone_number_id
        ),
    )


@router.get("", response_model=SettingsOut)
async def get_settings(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> SettingsOut:
    setting = await _get_or_create(db, user.id)
    return _out(setting)


@router.put("", response_model=SettingsOut)
async def update_settings(
    payload: SettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SettingsOut:
    setting = await _get_or_create(db, user.id)
    data = payload.model_dump(exclude_unset=True)

    # Never overwrite with the masked token shown in the UI
    if "whatsapp_access_token" in data:
        token = data["whatsapp_access_token"]
        if token and "..." in token:
            data.pop("whatsapp_access_token")

    for field, value in data.items():
        setattr(setting, field, value)
    await db.commit()
    await db.refresh(setting)
    return _out(setting)


@router.post("/test-connection", response_model=dict)
async def test_connection(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    setting = await _get_or_create(db, user.id)
    if not setting.whatsapp_access_token or not setting.whatsapp_phone_number_id:
        raise HTTPException(status_code=400, detail="Save access token and phone number id first")
    try:
        wa = WhatsAppClient(setting.whatsapp_access_token, setting.whatsapp_phone_number_id)
        numbers = await wa.get_phone_numbers()
        await wa.aclose()
    except WhatsAppError as exc:
        raise HTTPException(status_code=400, detail=f"Connection failed: {exc}")
    return {
        "ok": True,
        "detail": "Connection successful",
        "phone_numbers": numbers[:10],
    }


@router.get("/webhook-url", response_model=dict)
async def webhook_url(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    setting = await _get_or_create(db, user.id)
    base = str(request.base_url).rstrip("/")
    verify_token = setting.webhook_verify_token or ""
    return {
        "webhook_url": f"{base}/api/webhook/whatsapp",
        "verify_token": verify_token,
        "configured": bool(verify_token),
    }
