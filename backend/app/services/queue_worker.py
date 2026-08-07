"""Database-backed queue worker for campaign execution.

Runs as a background task on the single Render web process. It polls
``campaign_queue`` for due items, sends one WhatsApp message at a time
with the configured random delay, and records every status change. It is
fully idempotent and resumes automatically after a restart (nothing is
held in memory between ticks).
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.whatsapp import WhatsAppClient, WhatsAppError, resolve_whatsapp_client
from ..database import AsyncSessionLocal
from ..models.campaign import Campaign
from ..models.campaign_contact import CampaignContact
from ..models.campaign_log import CampaignLog
from ..models.campaign_message import CampaignMessage
from ..models.campaign_queue import CampaignQueue
from ..models.setting import Setting
from .leads import is_blacklisted, normalize_phone, render_template

logger = logging.getLogger(__name__)

TICK_SECONDS = 1.0


def _uuid() -> str:
    import uuid

    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_within_working_hours(campaign: Campaign, when: datetime) -> bool:
    if not campaign.working_hours_enabled:
        return True
    if not (campaign.work_start_time and campaign.work_end_time):
        return True
    tz_name = (campaign.timezone_name or "UTC").strip() or "UTC"
    try:
        import zoneinfo

        local = when.astimezone(zoneinfo.ZoneInfo(tz_name))
    except Exception:  # noqa: BLE001
        local = when
    current = local.time()
    start, end = campaign.work_start_time, campaign.work_end_time
    if start <= end:
        return start <= current <= end
    # overnight window (e.g. 22:00 -> 06:00)
    return current >= start or current <= end


def _random_delay(campaign: Campaign) -> float:
    lo = max(int(campaign.min_delay_seconds or 10), 1)
    hi = int(campaign.max_delay_seconds or lo)
    if hi < lo:
        lo, hi = hi, lo
    return random.uniform(lo, hi)


async def _typing_sleep(campaign: Campaign) -> None:
    if not campaign.typing_enabled:
        return
    lo = max(int(campaign.typing_min_seconds or 2), 1)
    hi = int(campaign.typing_max_seconds or lo)
    if hi < lo:
        lo, hi = hi, lo
    await asyncio.sleep(random.uniform(lo, hi))


async def _build_wa_client(db: AsyncSession, user_id: str) -> WhatsAppClient | None:
    setting = await db.scalar(select(Setting).where(Setting.user_id == user_id))
    if not setting:
        return None
    token = (setting.whatsapp_access_token or "").strip()
    pnid = (setting.whatsapp_phone_number_id or "").strip()
    if not token or not pnid:
        return None
    try:
        return resolve_whatsapp_client(token, pnid)
    except WhatsAppError:
        return None


def _contact_dict(contact: CampaignContact) -> dict:
    return {
        "name": contact.name or "",
        "phone": contact.phone,
        "company": contact.company or "",
        "website": contact.website or "",
        "city": contact.city or "",
        "country": contact.country or "",
        "email": contact.email or "",
        "notes": contact.notes or "",
    }


async def _log(db: AsyncSession, campaign_id: str, contact_id: str, phone: str | None,
               status: str, reason: str | None = None, retry: int = 0) -> None:
    db.add(
        CampaignLog(
            id=_uuid(),
            campaign_id=campaign_id,
            contact_id=contact_id,
            phone=phone,
            status=status,
            reason=reason,
            retry_count=retry,
        )
    )


async def _record_message(db: AsyncSession, campaign: Campaign, contact: CampaignContact,
                          msg_type: str, text: str, status: str,
                          wa_id: str | None = None, error: str | None = None,
                          sent_at: datetime | None = None) -> None:
    db.add(
        CampaignMessage(
            id=_uuid(),
            campaign_id=campaign.id,
            contact_id=contact.id,
            whatsapp_message_id=wa_id,
            msg_type=msg_type,
            text=text,
            status=status,
            error_reason=error,
            sent_at=sent_at,
        )
    )


# ---------------------------------------------------------------- scheduling
async def _count_sent_today(db: AsyncSession, campaign_id: str) -> int:
    """How many messages were successfully sent today (UTC)."""
    return await db.scalar(
        select(func.count())
        .select_from(CampaignMessage)
        .where(
            CampaignMessage.campaign_id == campaign_id,
            CampaignMessage.status.in_(("sent", "delivered", "read")),
            func.date_trunc("day", CampaignMessage.sent_at) == func.date_trunc("day", func.now()),
        )
    )


async def _enqueue_next(db: AsyncSession, campaign: Campaign, exclude_contact_id: str | None = None) -> None:
    """Queue the next pending contact for this campaign with a random delay."""
    stmt = (
        select(CampaignContact)
        .where(
            CampaignContact.campaign_id == campaign.id,
            CampaignContact.status.in_(("pending", "queued")),
        )
        .order_by(CampaignContact.id)
        .limit(1)
    )
    if exclude_contact_id:
        stmt = stmt.where(CampaignContact.id != exclude_contact_id)
    nxt = await db.scalar(stmt)
    if nxt is None:
        await _maybe_complete_campaign(db, campaign)
        return
    nxt.status = "queued"
    delay = _random_delay(campaign)
    run_after = _now() + timedelta(seconds=delay)
    db.add(
        CampaignQueue(
            id=_uuid(),
            campaign_id=campaign.id,
            contact_id=nxt.id,
            sort_order=0,
            run_after=run_after,
            attempt=0,
        )
    )
    await db.commit()


async def _requeue_after(db: AsyncSession, campaign: Campaign, contact: CampaignContact,
                         delay_seconds: int, attempt: int) -> None:
    contact.status = "retrying"
    db.add(
        CampaignQueue(
            id=_uuid(),
            campaign_id=campaign.id,
            contact_id=contact.id,
            sort_order=0,
            run_after=_now() + timedelta(seconds=delay_seconds),
            attempt=attempt,
        )
    )
    await db.commit()


async def _maybe_complete_campaign(db: AsyncSession, campaign: Campaign) -> None:
    remaining = await db.scalar(
        select(func.count())
        .where(
            CampaignContact.campaign_id == campaign.id,
            CampaignContact.status.in_(("pending", "queued", "sending", "retrying")),
        )
    )
    if not remaining:
        campaign.status = "completed"
        campaign.completed_at = _now()
        await db.commit()


# ---------------------------------------------------------------- sending
async def send_campaign_message(db: AsyncSession, campaign: Campaign,
                                contact: CampaignContact) -> bool:
    """Send a single message to one contact. Returns True on success (sent/delivered/read)."""
    phone = contact.phone
    wa_client = await _build_wa_client(db, campaign.user_id)
    if wa_client is None:
        contact.status = "failed"
        contact.error_reason = "WhatsApp integration not configured"
        campaign.failed_count = (campaign.failed_count or 0) + 1
        await _log(db, campaign.id, contact.id, phone, "failed", "WhatsApp integration not configured")
        await _record_message(db, campaign, contact, "text", campaign.message_text or "", "failed",
                              error="WhatsApp integration not configured")
        await db.commit()
        await _enqueue_next(db, campaign, exclude_contact_id=contact.id)
        return True  # processed (no retry possible without credentials)

    try:
        await _typing_sleep(campaign)
        text = render_template(campaign.message_text or "", _contact_dict(contact))
        wa_id = await wa_client.send_text(phone, text)
        contact.status = "sent"
        contact.whatsapp_message_id = wa_id or contact.whatsapp_message_id
        contact.processed_at = _now()
        contact.error_reason = None
        campaign.sent_count = (campaign.sent_count or 0) + 1
        await _log(db, campaign.id, contact.id, phone, "sent")
        await _record_message(db, campaign, contact, "text", text, "sent",
                              wa_id=wa_id, sent_at=_now())
        await db.commit()
        await wa_client.aclose()
        await _enqueue_next(db, campaign, exclude_contact_id=contact.id)
        return True
    except WhatsAppError as exc:
        logger.warning("WhatsApp send error (contact %s): %s", contact.id, exc)
        try:
            await wa_client.aclose()
        except Exception:  # noqa: BLE001
            pass
        return await _handle_failure(db, campaign, contact, exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected campaign send error for contact %s", contact.id)
        try:
            await wa_client.aclose()
        except Exception:  # noqa: BLE001
            pass
        return await _handle_failure(db, campaign, contact, exc)


async def _handle_failure(db: AsyncSession, campaign: Campaign, contact: CampaignContact,
                          exc: Exception) -> bool:
    contact.retry_count = (contact.retry_count or 0) + 1
    reason = str(exc)[:500]
    can_retry = bool(campaign.retry_enabled) and contact.retry_count <= (campaign.retry_count or 0)
    if can_retry:
        await _log(db, campaign.id, contact.id, contact.phone, "retrying", reason,
                   retry=contact.retry_count)
        await _record_message(db, campaign, contact, "text", campaign.message_text or "", "retrying",
                              error=reason)
        await db.commit()
        await _requeue_after(db, campaign, contact, campaign.retry_delay_seconds or 120, contact.retry_count)
        return True
    contact.status = "failed"
    contact.processed_at = _now()
    contact.error_reason = reason
    campaign.failed_count = (campaign.failed_count or 0) + 1
    await _log(db, campaign.id, contact.id, contact.phone, "failed", reason)
    await _record_message(db, campaign, contact, "text", campaign.message_text or "", "failed",
                          error=reason)
    await db.commit()
    await _enqueue_next(db, campaign, exclude_contact_id=contact.id)
    return True


# ---------------------------------------------------------------- tick loop
async def _claim_next_due(db: AsyncSession, campaign: Campaign) -> CampaignQueue | None:
    """Atomically claim one due queue row for a running campaign (skip-locked)."""
    # refresh campaign status from DB in case it was paused/stopped
    await db.refresh(campaign)
    if campaign.status != "running":
        return None
    if not await _is_allowed_window(db, campaign):
        return None
    return await db.scalar(
        select(CampaignQueue)
        .where(
            CampaignQueue.campaign_id == campaign.id,
            CampaignQueue.run_after <= func.now(),
        )
        .order_by(CampaignQueue.run_after.asc(), CampaignQueue.sort_order.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )


async def _is_allowed_window(db: AsyncSession, campaign: Campaign) -> bool:
    """Daily-limit + working-hours gating. Returns True if we may send now."""
    if campaign.daily_limit:
        sent_today = await _count_sent_today(db, campaign.id)
        if sent_today >= campaign.daily_limit:
            return False
    return _is_within_working_hours(campaign, _now())


async def tick_once(db: AsyncSession) -> int:
    """Process due work for every running campaign. Returns items processed."""
    processed = 0
    rows = await db.execute(select(Campaign).where(Campaign.status == "running"))
    for campaign in rows.scalars().all():
        # keep processing only while we can claim new work
        while True:
            await db.refresh(campaign)
            if campaign.status != "running":
                break
            item = await _claim_next_due(db, campaign)
            if item is None:
                break
            contact = await db.get(CampaignContact, item.contact_id)
            if contact is None:
                await db.delete(item)
                await db.commit()
                continue
            if contact.status not in ("pending", "queued", "retrying"):
                # stale queue row; re-enqueue next and discard
                await db.delete(item)
                await db.commit()
                await _enqueue_next(db, campaign, exclude_contact_id=contact.id)
                processed += 1
                continue
            # blacklist check
            if campaign.skip_blocked and await is_blacklisted(db, campaign.user_id, contact.phone):
                contact.status = "skipped"
                campaign.skip_count = (campaign.skip_count or 0) + 1
                await _log(db, campaign.id, contact.id, contact.phone, "skipped", "Blacklisted")
                await db.delete(item)
                await db.commit()
                await _enqueue_next(db, campaign, exclude_contact_id=contact.id)
                processed += 1
                continue
            # duplicate-contact check
            if campaign.skip_duplicates and contact.whatsapp_message_id:
                contact.status = "skipped"
                campaign.skip_count = (campaign.skip_count or 0) + 1
                await _log(db, campaign.id, contact.id, contact.phone, "skipped", "Already sent")
                await db.delete(item)
                await db.commit()
                await _enqueue_next(db, campaign, exclude_contact_id=contact.id)
                processed += 1
                continue
            contact.status = "sending"
            await db.commit()
            done = await send_campaign_message(db, campaign, contact)
            # ensure the queue row is consumed
            await db.refresh(item)
            if item in db:
                await db.delete(item)
                await db.commit()
            processed += 1
            if not done:
                break
    return processed


async def run_worker() -> None:
    """Main loop — run as a lifespan background task."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await tick_once(db)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Campaign worker tick failed: %s", exc)
        await asyncio.sleep(TICK_SECONDS)


# ---------------------------------------------------------------- lifecycle
async def start_campaign(db: AsyncSession, campaign_id: str) -> Campaign:
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise ValueError("campaign not found")
    if campaign.status not in ("draft", "paused", "scheduled"):
        return campaign
    # reset any stale statuses to pending
    await db.execute(
        update(CampaignContact)
        .where(CampaignContact.campaign_id == campaign_id)
        .where(CampaignContact.status.in_(("pending", "queued", "sending", "retrying")))
        .values(status="pending")
    )
    # clear any old queue rows for a clean (re)run
    await db.execute(delete(CampaignQueue).where(CampaignQueue.campaign_id == campaign_id))
    await db.commit()

    contact_ids = [
        r[0]
        for r in (await db.execute(
            select(CampaignContact.id)
            .where(CampaignContact.campaign_id == campaign_id)
            .order_by(CampaignContact.id)
        )).all()
    ]
    if not contact_ids:
        campaign.status = "completed"
        campaign.completed_at = _now()
        await db.commit()
        return campaign

    # seed the queue with a single initial item; each successful send enqueues the next
    db.add(
        CampaignQueue(
            id=_uuid(),
            campaign_id=campaign.id,
            contact_id=contact_ids[0],
            sort_order=0,
            run_after=_now(),
            attempt=0,
        )
    )
    first = await db.get(CampaignContact, contact_ids[0])
    if first:
        first.status = "queued"
    await db.commit()
    campaign.status = "running"
    campaign.started_at = _now()
    await db.commit()
    return campaign


async def pause_campaign(db: AsyncSession, campaign_id: str) -> Campaign:
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise ValueError("campaign not found")
    if campaign.status in ("running",):
        campaign.status = "paused"
        await db.commit()
    return campaign


async def stop_campaign(db: AsyncSession, campaign_id: str) -> Campaign:
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise ValueError("campaign not found")
    if campaign.status in ("running", "paused", "scheduled"):
        campaign.status = "cancelled"
        await db.execute(
            update(CampaignContact)
            .where(CampaignContact.campaign_id == campaign_id)
            .where(CampaignContact.status.in_(("pending", "queued", "sending", "retrying")))
            .values(status="skipped")
        )
        await db.commit()
    return campaign


async def resume_campaign(db: AsyncSession, campaign_id: str) -> Campaign:
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise ValueError("campaign not found")
    if campaign.status in ("paused",):
        # re-seed a due queue item if none pending
        due = await db.scalar(
            select(CampaignQueue)
            .where(CampaignQueue.campaign_id == campaign_id, CampaignQueue.run_after <= func.now())
            .order_by(CampaignQueue.run_after.asc())
            .limit(1)
        )
        if due is None:
            nxt = await db.scalar(
                select(CampaignContact)
                .where(
                    CampaignContact.campaign_id == campaign_id,
                    CampaignContact.status.in_(("pending", "queued", "retrying")),
                )
                .order_by(CampaignContact.id)
                .limit(1)
            )
            if nxt is not None:
                await db.execute(
                    update(CampaignContact)
                    .where(CampaignContact.id == nxt.id)
                    .values(status="queued")
                )
                db.add(CampaignQueue(
                    id=_uuid(), campaign_id=campaign.id, contact_id=nxt.id,
                    sort_order=0, run_after=_now(), attempt=nxt.retry_count or 0,
                ))
        campaign.status = "running"
        campaign.started_at = campaign.started_at or _now()
        await db.commit()
    return campaign


# ---------------------------------------------------------------- reply stop
async def stop_followups_for_reply(db: AsyncSession, user_id: str, phone: str) -> int:
    """When a contact replies, skip any pending/future campaign sends to them."""
    norm = normalize_phone(phone)
    if not norm:
        return 0
    res = await db.execute(
        update(CampaignContact)
        .where(
            CampaignContact.phone == norm,
            CampaignContact.status.in_(("pending", "queued", "sending", "retrying")),
        )
        .values(status="skipped")
    )
    await db.commit()
    return res.rowcount
