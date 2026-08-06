"""Media storage abstraction.

- Production:  Supabase Storage
- Local dev:   filesystem fallback under `media_storage/` (auto-selected when
               Supabase credentials are not configured)
"""
import logging
import os
import urllib.parse
from pathlib import Path
from typing import Optional

import anyio
from supabase import Client, create_client

from ..config import settings

logger = logging.getLogger(__name__)

LOCAL_ROOT = Path(__file__).resolve().parents[2] / "media_storage"

_shared_client: Optional[Client] = None


def supabase_configured() -> bool:
    return (
        settings.supabase_url
        and settings.supabase_service_key
        and settings.supabase_url != "https://your-project.supabase.co"
        and "your-project" not in settings.supabase_url
    )


def get_client() -> Client:
    global _shared_client
    if _shared_client is None:
        _shared_client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _shared_client


def _ensure_bucket() -> None:
    try:
        get_client().storage.get_bucket(settings.supabase_bucket)
    except Exception:
        get_client().storage.create_bucket(
            settings.supabase_bucket,
            {"public": False, "file_size_limit": 200 * 1024 * 1024},
        )


# ---------------------------------------------------------------- upload
async def upload_file(*, path: str, file_bytes: bytes, mime_type: str) -> str:
    if supabase_configured():
        await anyio.to_thread.run_sync(_ensure_bucket)

        def _do() -> None:
            get_client().storage.from_(settings.supabase_bucket).upload(
                path=path,
                file=file_bytes,
                file_options={"content-type": mime_type, "upsert": True},
            )

        await anyio.to_thread.run_sync(_do)
        return path

    # local fallback
    local_path = LOCAL_ROOT / path
    local_path.parent.mkdir(parents=True, exist_ok=True)
    await anyio.to_thread.run_sync(local_path.write_bytes, file_bytes)
    return path


# ---------------------------------------------------------------- download
async def download_file(path: str) -> bytes:
    if supabase_configured():
        def _do() -> bytes:
            return get_client().storage.from_(settings.supabase_bucket).download(path)

        return await anyio.to_thread.run_sync(_do)

    local_path = LOCAL_ROOT / path
    if not local_path.exists():
        raise FileNotFoundError(f"Media not found: {path}")
    return await anyio.to_thread.run_sync(local_path.read_bytes)


# ---------------------------------------------------------------- urls
async def signed_url(path: str, expires_in: int = 3600) -> str:
    """Return a time-limited URL the browser can use to fetch the file."""
    if supabase_configured():
        def _do() -> str:
            res = get_client().storage.from_(settings.supabase_bucket).create_signed_url(
                path=path, expires_in=expires_in
            )
            return res.get("signedURL", "") if isinstance(res, dict) else str(res)

        return await anyio.to_thread.run_sync(_do)

    # local fallback -> our own streaming endpoint
    encoded = urllib.parse.quote(path, safe="")
    return f"/api/media/file?path={encoded}"


async def delete_file(path: str) -> None:
    if supabase_configured():
        def _do() -> None:
            get_client().storage.from_(settings.supabase_bucket).remove([path])

        await anyio.to_thread.run_sync(_do)
        return
    local_path = LOCAL_ROOT / path
    if local_path.exists():
        await anyio.to_thread.run_sync(local_path.unlink)


def local_file_path(path: str) -> Path:
    """Resolve a storage path on local disk (dev helper)."""
    return LOCAL_ROOT / path
