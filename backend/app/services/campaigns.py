"""Campaign helpers: message rendering + report export."""
import csv
import io
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from ..models.campaign import Campaign
from ..models.campaign_contact import CampaignContact
from ..models.campaign_log import CampaignLog
from ..models.campaign_message import CampaignMessage
from ..models.media import MediaFile
from ..services.leads import render_template


def _uuid() -> str:
    import uuid

    return str(uuid.uuid4())


def contact_vars(contact: CampaignContact) -> dict:
    """Build the variable dict used for {{name}} / {{phone}} rendering."""
    return {
        "name": contact.name or "",
        "phone": contact.phone,
        "company": contact.company or "",
        "email": contact.email or "",
        "website": contact.website or "",
        "city": contact.city or "",
        "country": contact.country or "",
        "notes": contact.notes or "",
    }


def render_campaign(template: str, contact: CampaignContact) -> str:
    """Render a campaign message template for a contact."""
    return render_template(template, contact_vars(contact))


async def tag_contact_after_send(db, campaign: Campaign, contact: CampaignContact) -> None:
    """Auto-tag the CRM contact and log a note when a campaign message is sent."""
    if not contact.contact_id:
        return
    from ..models.contact import Contact, contact_tags
    from ..models.note import Note
    from ..models.tag import Tag

    # ensure the campaign tag exists
    tag = await db.scalar(
        select(Tag).where(Tag.user_id == campaign.user_id, Tag.name == f"Campaign: {campaign.name}")
    )
    if tag is None:
        tag = Tag(id=_uuid(), user_id=campaign.user_id, name=f"Campaign: {campaign.name}", color="#3b82f6")
        db.add(tag)
        await db.commit()
        await db.refresh(tag)
    # link tag if not already
    exists = await db.scalar(
        select(contact_tags).where(
            contact_tags.c.contact_id == contact.contact_id,
            contact_tags.c.tag_id == tag.id,
        )
    )
    if not exists:
        await db.execute(contact_tags.insert().values(contact_id=contact.contact_id, tag_id=tag.id))
    # add a note recording the campaign interaction
    await db.add(Note(
        id=_uuid(),
        user_id=campaign.user_id,
        contact_id=contact.contact_id,
        content=f"Messaged via campaign '{campaign.name}' on {contact.phone}. "
                f"Status: sent.",
        author_name="Campaign Bot",
    ))
    await db.commit()



def _csv_bytes(rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    for row in rows:
        w.writerow(row)
    return buf.getvalue().encode("utf-8")


def export_campaign_csv(
    campaign: Campaign,
    contacts: list[CampaignContact],
    logs: list[CampaignLog],
    stats: dict,
    media: MediaFile | None,
    fmt: str,
) -> tuple[bytes, str, str]:
    """Build a campaign report. Returns (content, filename, mime)."""
    header = ["Section", "Field", "Value"]
    rows: list[list] = [
        ["Campaign", "Name", campaign.name],
        ["Campaign", "Description", campaign.description or ""],
        ["Campaign", "Type", campaign.campaign_type],
        ["Campaign", "Status", campaign.status],
        ["Campaign", "Started", campaign.started_at.isoformat() if campaign.started_at else ""],
        ["Campaign", "Completed", campaign.completed_at.isoformat() if campaign.completed_at else ""],
        ["Campaign", "Sent", str(campaign.sent_count)],
        ["Campaign", "Failed", str(campaign.failed_count)],
        ["Campaign", "Skipped", str(campaign.skip_count)],
        ["Campaign", "Replies", str(campaign.reply_count)],
        ["Campaign", "Min Delay (s)", str(campaign.min_delay_seconds)],
        ["Campaign", "Max Delay (s)", str(campaign.max_delay_seconds)],
        ["Campaign", "Daily Limit", str(campaign.daily_limit if campaign.daily_limit else "none")],
        ["Campaign", "Media", media.file_name if media else "none"],
        [],
        ["Stats", "Status", "Count"],
    ]
    for status, count in sorted(stats.items()):
        rows.append(["Stats", status, str(count)])
    rows += [
        [],
        ["Contacts", "Phone", "Company", "Status", "Error", "Retries"],
    ]
    for c in contacts:
        rows.append(["Contacts", c.phone or "", c.company or "", c.status, c.error_reason or "", str(c.retry_count)])
    rows += [[], ["Logs", "Time", "Phone", "Status", "Reason", "Retries"]]
    for l in logs:
        rows.append(["Logs", l.created_at.isoformat(), l.phone or "", l.status, l.reason or "", str(l.retry_count)])

    content = _csv_bytes(rows)
    filename = f"campaign-{campaign.id}.csv"
    return content, filename, "text/csv"
