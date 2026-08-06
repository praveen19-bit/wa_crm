"""Media helpers: type detection, signed URL resolution."""
import mimetypes
import uuid
from typing import Optional

from ..core.storage import signed_url
from ..models.media import MediaFile

MEDIA_TYPE_MAP = {
    "image": {"png", "jpg", "jpeg", "gif", "webp", "bmp", "heic", "avif"},
    "video": {"mp4", "3gp", "mkv", "mov", "webm"},
    "audio": {"mp3", "aac", "m4a", "opus", "ogg", "wav", "amr"},
    "document": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "zip"},
}


def detect_media_type(filename: str, mime: str) -> str:
    """Classify a file as image|video|audio|document."""
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    if ext in MEDIA_TYPE_MAP["image"]:
        return "image"
    if ext in MEDIA_TYPE_MAP["video"]:
        return "video"
    if ext in MEDIA_TYPE_MAP["audio"]:
        return "audio"
    if ext in MEDIA_TYPE_MAP["document"]:
        return "document"
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "document"


def build_storage_path(user_id: str, media_type: str, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    key = uuid.uuid4().hex
    return f"{user_id}/{media_type}/{key}.{ext}"


def media_to_dict(media: MediaFile, with_url: bool = True) -> dict:
    return {
        "id": media.id,
        "file_name": media.file_name,
        "mime_type": media.mime_type,
        "size_bytes": media.size_bytes,
        "media_type": media.media_type,
        "storage_path": media.storage_path,
        "created_at": media.created_at,
        "url": None,
    }


async def resolve_media_urls(media_list: list[MediaFile]) -> list[dict]:
    """Convert MediaFile ORM objects to dicts with signed URLs (best effort)."""
    out: list[dict] = []
    for media in media_list:
        d = media_to_dict(media)
        try:
            d["url"] = await signed_url(media.storage_path)
        except Exception:  # noqa: BLE001 - storage may be unconfigured locally
            d["url"] = None
        out.append(d)
    return out
