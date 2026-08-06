"""Media upload / download endpoints (Supabase Storage + local dev fallback)."""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.storage import download_file, signed_url
from ..database import get_db
from ..models.media import MediaFile
from ..models.user import User
from ..schemas.media import MediaOut
from ..services.media import build_storage_path, detect_media_type
from .deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["Media"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB


def _media_out(media: MediaFile, url: str | None = None) -> MediaOut:
    return MediaOut(
        id=media.id,
        file_name=media.file_name,
        mime_type=media.mime_type,
        size_bytes=media.size_bytes,
        media_type=media.media_type,
        storage_path=media.storage_path,
        created_at=media.created_at,
        url=url,
    )


@router.post("/upload", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(...),
    conversation_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MediaOut:
    filename = file.filename or "upload.bin"
    mime_type = file.content_type or "application/octet-stream"
    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=422, detail="Empty file")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit")

    media_type = detect_media_type(filename, mime_type)
    storage_path = build_storage_path(user.id, media_type, filename)

    from ..core.storage import upload_file

    try:
        await upload_file(path=storage_path, file_bytes=raw, mime_type=mime_type)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Storage upload failed")
        raise HTTPException(status_code=503, detail=f"Storage upload failed: {exc}")

    media = MediaFile(
        user_id=user.id,
        conversation_id=conversation_id,
        storage_path=storage_path,
        file_name=filename,
        mime_type=mime_type,
        size_bytes=len(raw),
        media_type=media_type,
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)

    url = None
    try:
        url = await signed_url(media.storage_path)
    except Exception:  # noqa: BLE001
        url = None
    return _media_out(media, url)


@router.get("/file")
async def stream_local_media(
    path: str,
) -> StreamingResponse:
    """Dev fallback: streams a locally stored file by storage path."""
    try:
        data = await download_file(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Media not found")
    mime = "application/octet-stream"
    return StreamingResponse(iter([data]), media_type=mime)


@router.get("/{media_id}", response_model=MediaOut)
async def get_media(
    media_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MediaOut:
    media = await db.get(MediaFile, media_id)
    if not media or media.user_id != user.id:
        raise HTTPException(status_code=404, detail="Media not found")
    url = None
    try:
        url = await signed_url(media.storage_path)
    except Exception:  # noqa: BLE001
        url = None
    return _media_out(media, url)


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    media = await db.get(MediaFile, media_id)
    if not media or media.user_id != user.id:
        raise HTTPException(status_code=404, detail="Media not found")
    from ..core.storage import delete_file

    try:
        await delete_file(media.storage_path)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to delete stored file for %s", media.id)
    await db.delete(media)
    await db.commit()
