"""WhatsApp Cloud API webhook endpoint (unauthenticated, called by Meta)."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.setting import Setting
from ..services.webhook import process_webhook_payload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhook"])


@router.get("/whatsapp")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Handle Meta's webhook subscription verification handshake."""
    if hub_mode == "subscribe" and hub_verify_token:
        settings_rows = await db.scalars(select(Setting).where(Setting.webhook_verify_token == hub_verify_token))
        matches = list(settings_rows.all())
        if matches:
            logger.info("Webhook verified for user=%s", matches[0].user_id)
            return Response(content=hub_challenge or "", media_type="text/plain")
    logger.warning("Webhook verification failed (token mismatch)")
    return Response(content="Verification failed", status_code=403)


@router.post("/whatsapp")
async def receive_webhook(
    payload: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive incoming WhatsApp messages / status updates from Meta."""
    try:
        counts = await process_webhook_payload(db, payload)
    except Exception:  # noqa: BLE001
        logger.exception("Webhook processing failed")
        # Always 200 to Meta so it stops retrying and does not spam us.
        return {"ok": False, **{"messages": 0, "statuses": 0, "errors": 1}}
    logger.info("Webhook processed: %s", counts)
    return {"ok": True, **counts}
