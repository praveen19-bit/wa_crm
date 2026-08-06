"""Tag management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.tag import Tag
from ..models.user import User
from ..schemas.tag import TagCreate, TagOut
from .deps import get_current_user

router = APIRouter(prefix="/tags", tags=["Tags"])


@router.get("", response_model=list[TagOut])
async def list_tags(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Tag]:
    result = await db.scalars(
        select(Tag).where(Tag.user_id == user.id).order_by(Tag.name)
    )
    return list(result.all())


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: TagCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tag:
    existing = await db.scalar(
        select(Tag).where(Tag.user_id == user.id, Tag.name == payload.name.strip())
    )
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")
    tag = Tag(user_id=user.id, name=payload.name.strip(), color=payload.color)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    tag = await db.get(Tag, tag_id)
    if not tag or tag.user_id != user.id:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.commit()
