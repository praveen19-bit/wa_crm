"""Contact management endpoints: CRUD, search, CSV import/export, notes, tags."""
import csv
import io
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.conversation import Conversation
from ..models.contact import Contact, contact_tags
from ..models.note import Note
from ..models.tag import Tag
from ..models.user import User
from ..schemas.contact import (
    ContactCreate,
    ContactOut,
    ContactUpdate,
    NoteCreate,
    NoteOut,
    TagAssignRequest,
)
from ..schemas.tag import TagOut
from ..services.messaging import ensure_utc
from .deps import get_current_user

router = APIRouter(prefix="/contacts", tags=["Contacts"])


def normalize_phone(raw: str) -> str:
    """Strip non-digit chars from a phone number."""
    return "".join(ch for ch in raw if ch.isdigit())


# ------------------------------------------------------------------ serializers
def enrich_contact(contact: Contact, conv: Optional[Conversation]) -> ContactOut:
    return ContactOut(
        id=contact.id,
        name=contact.name,
        phone=contact.phone,
        email=contact.email,
        company=contact.company,
        avatar_url=contact.avatar_url,
        created_at=ensure_utc(contact.created_at),
        updated_at=ensure_utc(contact.updated_at),
        tags=[TagOut.model_validate(t) for t in contact.tags] if contact.tags else [],
        unread_count=conv.unread_count if conv else 0,
        last_message_preview=conv.last_message_preview if conv else None,
        last_message_at=ensure_utc(conv.last_message_at) if conv else None,
        conversation_id=conv.id if conv else None,
    )


async def _get_conversation_map(
    db: AsyncSession, user_id: str, contact_ids: list[str]
) -> dict[str, Conversation]:
    """Map contact_id -> most relevant conversation (active first)."""
    if not contact_ids:
        return {}
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.contact_id.in_(contact_ids),
            Conversation.is_archived.is_(False),
        )
        .order_by(Conversation.last_message_at.desc())
    )
    out: dict[str, Conversation] = {}
    for conv in result.scalars().all():
        out.setdefault(conv.contact_id, conv)
    return out


async def _load_conversation(db: AsyncSession, user_id: str, contact_id: str) -> Optional[Conversation]:
    return await db.scalar(
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.contact_id == contact_id,
            Conversation.is_archived.is_(False),
        )
        .order_by(Conversation.last_message_at.desc())
        .limit(1)
    )


# ------------------------------------------------------------------ list / search
@router.get("", response_model=list[ContactOut])
async def list_contacts(
    search: Optional[str] = Query(None, description="Search name, phone or company"),
    tag_id: Optional[str] = Query(None, description="Filter by tag id"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContactOut]:
    query = select(Contact).where(Contact.user_id == user.id)

    if search and search.strip():
        like = f"%{search.strip()}%"
        query = query.where(
            or_(
                Contact.name.ilike(like),
                Contact.phone.ilike(like),
                Contact.company.ilike(like),
                Contact.email.ilike(like),
            )
        )

    if tag_id:
        query = query.where(
            Contact.id.in_(select(contact_tags.c.contact_id).where(contact_tags.c.tag_id == tag_id))
        )

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(
        query.order_by(Contact.created_at.desc()).offset((page - 1) * limit).limit(limit)
    )
    contacts = list(result.scalars().all())

    conv_map = await _get_conversation_map(db, user.id, [c.id for c in contacts])
    return [enrich_contact(c, conv_map.get(c.id)) for c in contacts]


@router.get("/count", response_model=dict)
async def contacts_count(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    total = await db.scalar(select(func.count()).select_from(Contact).where(Contact.user_id == user.id))
    return {"total": total or 0}


@router.get("/export")
async def export_contacts_csv(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    contacts = await db.scalars(select(Contact).where(Contact.user_id == user.id))
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Name", "Phone", "Email", "Company", "Tags"])
    for c in contacts:
        tags = ", ".join(t.name for t in c.tags) if c.tags else ""
        writer.writerow([c.name or "", c.phone, c.email or "", c.company or "", tags])

    buffer.seek(0)
    filename = "contacts.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ------------------------------------------------------------------ CRUD
@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactOut:
    phone = normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="A valid phone number is required")
    existing = await db.scalar(
        select(Contact).where(Contact.user_id == user.id, Contact.phone == phone)
    )
    if existing:
        raise HTTPException(status_code=409, detail="A contact with this phone already exists")
    contact = Contact(
        user_id=user.id,
        name=payload.name.strip() if payload.name else None,
        phone=phone,
        email=payload.email,
        company=payload.company.strip() if payload.company else None,
        avatar_url=payload.avatar_url,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return enrich_contact(contact, None)


@router.get("/{contact_id}", response_model=ContactOut)
async def get_contact(
    contact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactOut:
    contact = await db.get(Contact, contact_id)
    if not contact or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    conv = await _load_conversation(db, user.id, contact.id)
    return enrich_contact(contact, conv)


@router.put("/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: str,
    payload: ContactUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactOut:
    contact = await db.get(Contact, contact_id)
    if not contact or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")

    data = payload.model_dump(exclude_unset=True)
    if "phone" in data and data["phone"]:
        data["phone"] = normalize_phone(data["phone"])
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    if "company" in data and data["company"] is not None:
        data["company"] = data["company"].strip()

    for field, value in data.items():
        setattr(contact, field, value)
    await db.commit()
    await db.refresh(contact)
    conv = await _load_conversation(db, user.id, contact.id)
    return enrich_contact(contact, conv)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    contact = await db.get(Contact, contact_id)
    if not contact or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(contact)
    await db.commit()


# ------------------------------------------------------------------ CSV import
@router.post("/import", response_model=dict)
async def import_contacts_csv(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Please upload a .csv file")

    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    required_phone_col = None
    for candidate in ("phone", "Phone", "mobile", "Mobile", "telephone", "wa_id"):
        if candidate in (reader.fieldnames or []):
            required_phone_col = candidate
            break
    if not required_phone_col:
        raise HTTPException(
            status_code=422, detail='CSV must include a "phone" column (or mobile/telephone)'
        )

    created = skipped = failed = 0
    tags_cache: dict[str, Tag] = {}

    for row in reader:
        phone = normalize_phone(row.get(required_phone_col) or "")
        if not phone:
            failed += 1
            continue
        existing = await db.scalar(
            select(Contact).where(Contact.user_id == user.id, Contact.phone == phone)
        )
        if existing:
            skipped += 1
            continue

        contact = Contact(
            user_id=user.id,
            name=(row.get("name") or row.get("Name") or "").strip() or None,
            phone=phone,
            email=(row.get("email") or row.get("Email") or "").strip() or None,
            company=(row.get("company") or row.get("Company") or "").strip() or None,
        )
        db.add(contact)
        created += 1

        tags_raw = (row.get("tags") or row.get("Tags") or "").strip()
        if tags_raw:
            await db.flush()
            for tag_name in (t.strip() for t in tags_raw.split(",") if t.strip()):
                tag = tags_cache.get(tag_name.lower())
                if not tag:
                    tag = await db.scalar(
                        select(Tag).where(Tag.user_id == user.id, Tag.name == tag_name)
                    )
                    if not tag:
                        tag = Tag(user_id=user.id, name=tag_name)
                        db.add(tag)
                        await db.flush()
                    tags_cache[tag_name.lower()] = tag
                contact.tags.append(tag)

    await db.commit()
    return {"created": created, "skipped": skipped, "failed": failed}


# ------------------------------------------------------------------ notes
@router.post("/{contact_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def add_note(
    contact_id: str,
    payload: NoteCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Note:
    contact = await db.get(Contact, contact_id)
    if not contact or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    note = Note(
        user_id=user.id,
        contact_id=contact_id,
        content=payload.content.strip(),
        author_name=user.name,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


@router.get("/{contact_id}/notes", response_model=list[NoteOut])
async def list_notes(
    contact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Note]:
    contact = await db.get(Contact, contact_id)
    if not contact or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    result = await db.scalars(
        select(Note).where(Note.contact_id == contact_id).order_by(Note.created_at.desc())
    )
    return list(result.all())


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    note = await db.get(Note, note_id)
    if not note or note.user_id != user.id:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.delete(note)
    await db.commit()


# ------------------------------------------------------------------ tags
@router.put("/{contact_id}/tags", response_model=ContactOut)
async def assign_tags(
    contact_id: str,
    payload: TagAssignRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactOut:
    contact = await db.get(Contact, contact_id)
    if not contact or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    if payload.tag_ids:
        tags = await db.scalars(select(Tag).where(Tag.user_id == user.id, Tag.id.in_(payload.tag_ids)))
        contact.tags = list(tags.all())
    else:
        contact.tags = []
    await db.commit()
    await db.refresh(contact)
    conv = await _load_conversation(db, user.id, contact.id)
    return enrich_contact(contact, conv)
