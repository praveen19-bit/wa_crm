"""Media schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MediaOut(BaseModel):
    id: str
    file_name: str
    mime_type: str
    size_bytes: int
    media_type: str
    storage_path: str
    created_at: datetime
    url: Optional[str] = None

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    ok: bool = True
    media: MediaOut
