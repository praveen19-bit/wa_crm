"""Campaign REST API: CRUD, lead upload/preview, execution control, templates, blacklist."""
import csv
import io
import logging
from datetime import date, datetime, time as dtime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.storage import signed_url
from ..database import get_db
from ..models.campaign import Campaign
from ..models.campaign_contact import CampaignContact
from ..models.campaign_log import CampaignLog
from ..models.campaign_message import CampaignMessage
from ..models.campaign_template import CampaignTemplate
from ..models.campaign_queue import CampaignQueue
from ..models.media import MediaFile
from ..models.contact import Contact
from ..models import BlacklistedContact
from ..schemas.campaign import (
    BlacklistEntryOut,
    CampaignCreate,
    CampaignOut,
    CampaignProgressOut,
    LeadPreview,
    LeadPreviewRow,
    TemplateCreate,
    TemplateOut,
)
from ..services.campaigns import export_campaign_csv
from ..services.leads import parse_leads
from ..services.queue_worker import (
    pause_campaign,
    resume_campaign,
    start_campaign,
    stop_campaign,
)
from .deps import get_current_user

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])
logger = logging.getLogger(__name__)

MAX_LEADS = 50000
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


# ----------------------------------------------------------------- helpers
def _campaign_row(c: Campaign) -> CampaignOut:
    return CampaignOut(
        id=c.id,
        user_id=c.user_id,
        name=c.name,
        description=c.description,
        campaign_type=c.campaign_type,
        status=c.status,
        message_text=c.message_text,
        media_id=c.media_id,
        min_delay_seconds=c.min_delay_seconds,
        max_delay_seconds=c.max_delay_seconds,
        typing_enabled=c.typing_enabled,
        typing_min_seconds=c.typing_min_seconds,
        typing_max_seconds=c.typing_max_seconds,
        working_hours_enabled=c.working_hours_enabled,
        work_start_time=_t(c.work_start_time),
        work_end_time=_t(c.work_end_time),
        timezone_name=c.timezone_name,
        daily_limit=c.daily_limit,
        retry_enabled=c.retry_enabled,
        retry_count=c.retry_count,
        retry_delay_seconds=c.retry_delay_seconds,
        skip_duplicates=c.skip_duplicates,
        skip_blocked=c.skip_blocked,
        skip_contacted=c.skip_contacted,
        scheduled_at=c.scheduled_at,
        started_at=c.started_at,
        completed_at=c.completed_at,
        sent_count=c.sent_count,
        failed_count=c.failed_count,
        reply_count=c.reply_count,
        skip_count=c.skip_count,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _t(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M")
    return v


async def _load_media(db: AsyncSession, user_id: str, media_id: str) -> MediaFile | None:
    media = await db.get(MediaFile, media_id)
    if media and media.user_id == user_id:
        media.url = await signed_url(media.storage_path)
        return media
    return None


# ----------------------------------------------------------------- list + CRUD
@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    status: Optional[str] = Query(None),
    campaign_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    stmt = select(Campaign).where(Campaign.user_id == user.id)
    if status:
        stmt = stmt.where(Campaign.status == status)
    if campaign_type:
        stmt = stmt.where(Campaign.campaign_type == campaign_type)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(Campaign.name.ilike(like))
    rows = await db.execute(stmt.order_by(Campaign.created_at.desc()).limit(limit))
    out = []
    for c in rows.scalars().all():
        co = _campaign_row(c)
        co.contact_count, co.media = await _counts_and_media(db, user.id, c)
        out.append(co)
    return out


async def _counts_and_media(db, user_id, c: Campaign):
    contact_count = await db.scalar(
        select(func.count()).where(CampaignContact.campaign_id == c.id)
    )
    media = None
    if c.media_id:
        m = await db.get(MediaFile, c.media_id)
        if m and m.user_id == user_id:
            media = m
    return contact_count or 0, media


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    import uuid as _uuid

    if payload.campaign_type not in {"cold_outreach", "promotion", "follow_up", "custom"}:
        raise HTTPException(400, "invalid campaign_type")
    if payload.media_id:
        media = await _load_media(db, user.id, payload.media_id)
        if not media:
            raise HTTPException(404, "Attachment not found")
    c = Campaign(
        id=str(_uuid.uuid4()),
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        campaign_type=payload.campaign_type,
        message_text=payload.message_text,
        media_id=payload.media_id,
        **_config_kwargs(payload.config),
        scheduled_at=payload.scheduled_at,
        status="draft",
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    co = _campaign_row(c)
    co.contact_count, co.media = 0, None
    return co


def _config_kwargs(cfg):
    return {
        "min_delay_seconds": cfg.min_delay_seconds,
        "max_delay_seconds": cfg.max_delay_seconds,
        "typing_enabled": cfg.typing_enabled,
        "typing_min_seconds": cfg.typing_min_seconds,
        "typing_max_seconds": cfg.typing_max_seconds,
        "working_hours_enabled": cfg.working_hours_enabled,
        "work_start_time": _parse_time(cfg.work_start_time),
        "work_end_time": _parse_time(cfg.work_end_time),
        "timezone_name": cfg.timezone_name,
        "daily_limit": cfg.daily_limit,
        "retry_enabled": cfg.retry_enabled,
        "retry_count": cfg.retry_count,
        "retry_delay_seconds": cfg.retry_delay_seconds,
        "skip_duplicates": cfg.skip_duplicates,
        "skip_blocked": cfg.skip_blocked,
        "skip_contacted": cfg.skip_contacted,
    }


def _parse_time(v):
    if not v:
        return None
    if hasattr(v, "hour"):
        return v
    try:
        hh, mm = str(v).split(":")
        return dtime(int(hh), int(mm))
    except Exception:  # noqa: BLE001
        return None


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(campaign_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    co = _campaign_row(c)
    co.contact_count, co.media = await _counts_and_media(db, user.id, c)
    return co


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(campaign_id: str, payload: CampaignCreate,
                          user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    if c.status not in ("draft", "paused", "scheduled"):
        raise HTTPException(400, "Campaign cannot be modified while running")
    if payload.media_id:
        media = await _load_media(db, user.id, payload.media_id)
        if not media:
            raise HTTPException(404, "Attachment not found")
    c.name = payload.name
    c.description = payload.description
    c.campaign_type = payload.campaign_type
    c.message_text = payload.message_text
    c.media_id = payload.media_id
    for k, v in _config_kwargs(payload.config).items():
        setattr(c, k, v)
    c.scheduled_at = payload.scheduled_at
    await db.commit()
    await db.refresh(c)
    co = _campaign_row(c)
    co.contact_count, co.media = await _counts_and_media(db, user.id, c)
    return co


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    if c.status in ("running", "scheduled"):
        raise HTTPException(400, "Stop or pause the campaign before deleting")
    await db.delete(c)
    await db.commit()


# ----------------------------------------------------------------- upload + preview
@router.post("/{campaign_id}/upload", response_model=LeadPreview)
async def upload_leads(
    campaign_id: str,
    file: UploadFile = File(...),
    column_map: Optional[str] = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 25 MB)")
    fname = file.filename or "leads.csv"
    lower = fname.lower()
    if not (lower.endswith(".csv") or lower.endswith(".xlsx") or lower.endswith(".xls")):
        raise HTTPException(422, "Unsupported file type. Allowed: .csv, .xlsx, .xls")
    import json as _json

    cmap = _json.loads(column_map) if column_map else {}
    preview = parse_leads(raw, fname, cmap)
    return LeadPreview(
        headers=preview["headers"],
        mapping=preview["mapping"],
        rows=[LeadPreviewRow(**r) for r in preview["rows"]],
        meta=preview["meta"],
    )


# ----------------------------------------------------------------- contacts
@router.get("/{campaign_id}/contacts", response_model=list)
async def list_campaign_contacts(
    campaign_id: str,
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    stmt = select(CampaignContact).where(CampaignContact.campaign_id == c.id)
    if status:
        stmt = stmt.where(CampaignContact.status == status)
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            func.lower(CampaignContact.name + " " + CampaignContact.phone).like(func.lower(like))
        )
    rows = await db.execute(stmt.order_by(CampaignContact.created_at).offset(offset).limit(limit))
    return [dict(id=r.id, name=r.name, phone=r.phone, company=r.company,
                 status=r.status, error_reason=r.error_reason, retry_count=r.retry_count) for r in rows.scalars().all()]


@router.post("/{campaign_id}/seed", status_code=201)
async def seed_campaign_contacts(
    campaign_id: str,
    rows: list[LeadPreviewRow],
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Persist validated lead rows as campaign_contacts (idempotent per phone)."""
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    if c.status not in ("draft", "paused", "scheduled"):
        raise HTTPException(400, "Campaign is already running")
    existing = set(
        p for (p,) in (await db.execute(
            select(CampaignContact.phone).where(CampaignContact.campaign_id == c.id)
        )).all()
    )
    import uuid as _uuid

    added = 0
    seen: set[str] = set(existing)
    invalid = 0
    for row in rows:
        if row.status != "valid":
            invalid += 1
            continue
        phone = (row.phone or "").strip()
        if not phone or phone in seen:
            continue
        seen.add(phone)
        contact_id = await db.scalar(
            select(Contact.id).where(Contact.user_id == user.id, Contact.phone == phone)
        )
        db.add(
            CampaignContact(
                id=str(_uuid.uuid4()),
                campaign_id=c.id,
                contact_id=contact_id,
                name=row.name,
                phone=phone,
                company=row.company,
                email=row.email,
                website=row.website,
                city=row.city,
                country=row.country,
                notes=row.notes,
                extra=row.extra,
                status="pending",
            )
        )
        added += 1
    if added:
        await db.commit()
    return {"added": added, "skipped_invalid": invalid}


# ----------------------------------------------------------------- execution
@router.post("/{campaign_id}/start", response_model=CampaignOut)
async def start(campaign_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    total = await db.scalar(
        select(func.count()).where(CampaignContact.campaign_id == c.id)
    )
    if not total:
        raise HTTPException(400, "No contacts in the campaign")
    await start_campaign(db, c.id)
    await db.refresh(c)
    return _campaign_row(c)


@router.post("/{campaign_id}/pause", response_model=CampaignOut)
async def pause(campaign_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    await pause_campaign(db, c.id)
    await db.refresh(c)
    return _campaign_row(c)


@router.post("/{campaign_id}/resume", response_model=CampaignOut)
async def resume(campaign_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    await resume_campaign(db, c.id)
    await db.refresh(c)
    return _campaign_row(c)


@router.post("/{campaign_id}/stop", response_model=CampaignOut)
async def stop(campaign_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    await stop_campaign(db, c.id)
    await db.refresh(c)
    return _campaign_row(c)


# ----------------------------------------------------------------- progress + logs
@router.get("/{campaign_id}/progress", response_model=CampaignProgressOut)
async def progress(campaign_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    counts = {}
    for (status, n) in (await db.execute(
        select(CampaignContact.status, func.count())
        .where(CampaignContact.campaign_id == c.id)
        .group_by(CampaignContact.status)
    )).all():
        counts[status] = n
    current = await db.scalar(
        select(CampaignContact)
        .where(CampaignContact.campaign_id == c.id, CampaignContact.status == "sending")
        .order_by(CampaignContact.created_at.desc())
        .limit(1)
    )
    out = _campaign_row(c)
    out.contact_count = counts.get("pending", 0) + counts.get("queued", 0) + counts.get("sending", 0) \
        + counts.get("sent", 0) + counts.get("failed", 0) + counts.get("skipped", 0) + counts.get("retrying", 0)
    return CampaignProgressOut(
        campaign=out,
        contact_count=out.contact_count,
        pending=counts.get("pending", 0),
        sending=counts.get("sending", 0),
        sent=counts.get("sent", 0),
        failed=counts.get("failed", 0),
        skipped=counts.get("skipped", 0),
        retrying=counts.get("retrying", 0),
        replied=c.reply_count,
        current=current,
    )


@router.get("/{campaign_id}/logs", response_model=list)
async def logs(campaign_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    rows = await db.execute(
        select(CampaignLog)
        .where(CampaignLog.campaign_id == c.id)
        .order_by(CampaignLog.created_at.desc())
        .limit(2000)
    )
    phones = dict(
        (await db.execute(
            select(CampaignContact.id, CampaignContact.phone)
            .where(CampaignContact.campaign_id == c.id)
        )).all()
    )
    out = []
    for r in rows.scalars().all():
        out.append({
            "id": r.id,
            "time": r.created_at,
            "phone": r.phone or phones.get(r.contact_id),
            "status": r.status,
            "reason": r.reason,
            "retry_count": r.retry_count,
        })
    return out


# ----------------------------------------------------------------- templates
@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(CampaignTemplate).where(CampaignTemplate.user_id == user.id)
        .order_by(CampaignTemplate.is_favorite.desc(), CampaignTemplate.created_at.desc())
    )
    return rows.scalars().all()


@router.post("/templates", response_model=TemplateOut, status_code=201)
async def create_template(payload: TemplateCreate, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    import uuid as _uuid

    if not payload.name.strip():
        raise HTTPException(400, "name required")
    if (await db.scalar(select(func.count()).where(CampaignTemplate.user_id == user.id, CampaignTemplate.name == payload.name))) > 0:
        raise HTTPException(409, "A template with this name already exists")
    t = CampaignTemplate(id=str(_uuid.uuid4()), user_id=user.id, name=payload.name,
                         body=payload.body, is_favorite=payload.is_favorite)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@router.post("/templates/{template_id}/favorite")
async def favorite_template(template_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = await db.get(CampaignTemplate, template_id)
    if not t or t.user_id != user.id:
        raise HTTPException(404, "Template not found")
    t.is_favorite = not t.is_favorite
    await db.commit()
    return {"ok": True, "is_favorite": t.is_favorite}


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = await db.get(CampaignTemplate, template_id)
    if not t or t.user_id != user.id:
        raise HTTPException(404, "Template not found")
    await db.delete(t)
    await db.commit()


# ----------------------------------------------------------------- blacklist
@router.get("/blacklist", response_model=list[BlacklistEntryOut])
async def list_blacklist(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(BlacklistedContact).where(BlacklistedContact.user_id == user.id)
        .order_by(BlacklistedContact.created_at.desc())
    )
    return rows.scalars().all()


@router.post("/blacklist", response_model=BlacklistEntryOut, status_code=201)
async def add_blacklist(phone: str = Query(...), reason: Optional[str] = Query(None),
                       user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from ..services.leads import normalize_phone as _norm
    import uuid as _uuid

    norm = _norm(phone)
    if not norm:
        raise HTTPException(400, "Invalid phone number")
    if await db.scalar(select(BlacklistedContact).where(BlacklistedContact.user_id == user.id, BlacklistedContact.phone == norm)):
        raise HTTPException(409, "Already blacklisted")
    b = BlacklistedContact(id=str(_uuid.uuid4()), user_id=user.id, phone=norm, reason=reason)
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return b


@router.delete("/blacklist/{entry_id}", status_code=204)
async def remove_blacklist(entry_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    b = await db.get(BlacklistedContact, entry_id)
    if not b or b.user_id != user.id:
        raise HTTPException(404, "Entry not found")
    await db.delete(b)
    await db.commit()


# ----------------------------------------------------------------- export
@router.get("/{campaign_id}/export")
async def export_campaign(campaign_id: str, fmt: str = Query("csv"),
                          user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    media = None
    if c.media_id:
        m = await db.get(MediaFile, c.media_id)
        if m and m.user_id == user.id:
            media = m
    rows = await db.execute(
        select(CampaignContact).where(CampaignContact.campaign_id == c.id)
        .order_by(CampaignContact.created_at)
    )
    contacts = rows.scalars().all()
    logs = await db.execute(
        select(CampaignLog).where(CampaignLog.campaign_id == c.id).order_by(CampaignLog.created_at)
    )
    logs = logs.scalars().all()
    stats = await db.execute(
        select(CampaignMessage.status, func.count())
        .where(CampaignMessage.campaign_id == c.id).group_by(CampaignMessage.status)
    )
    stats = dict(stats.all())
    from fastapi.responses import StreamingResponse

    content, filename, mime = export_campaign_csv(c, contacts, logs, stats, media, fmt)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(content), media_type=mime, headers=headers)


# ----------------------------------------------------------------- analytics
@router.get("/{campaign_id}/analytics", response_model=dict)
async def analytics(campaign_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found")
    stats = dict(
        (await db.execute(
            select(CampaignMessage.status, func.count())
            .where(CampaignMessage.campaign_id == c.id).group_by(CampaignMessage.status)
        )).all()
    )
    rows = await db.execute(
        select(func.date(CampaignMessage.sent_at), CampaignMessage.status, func.count())
        .where(CampaignMessage.campaign_id == c.id, CampaignMessage.sent_at.isnot(None))
        .group_by(func.date(CampaignMessage.sent_at), CampaignMessage.status)
        .order_by(func.date(CampaignMessage.sent_at))
    )
    timeline = {}
    for day, status, n in rows:
        timeline.setdefault(str(day), {})[status] = n
    return {
        "sent": stats.get("sent", 0),
        "delivered": stats.get("delivered", 0),
        "read": stats.get("read", 0),
        "failed": stats.get("failed", 0),
        "skipped": stats.get("skipped", 0),
        "timeline": timeline,
        "started_at": c.started_at,
        "completed_at": c.completed_at,
    }
