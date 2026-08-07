"""WhatsApp Cloud API client (async).

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
from typing import Optional

import httpx

from ..config import settings


class WhatsAppError(Exception):
    def __init__(self, message: str, status_code: int = 0, fb_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.fb_code = fb_code


class WhatsAppClient:
    """Thin async wrapper around the Meta WhatsApp Cloud API."""

    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        api_version: Optional[str] = None,
        graph_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        if not access_token or not phone_number_id:
            raise WhatsAppError("WhatsApp integration not configured")
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version or settings.whatsapp_api_version
        self.base_url = f"{graph_url or settings.whatsapp_graph_url}/{self.api_version}"
        self._client = httpx.AsyncClient(timeout=timeout)

    # ------------------------------------------------------------------ headers
    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ send
    async def send_text(self, to: str, text: str, preview_url: bool = False) -> str:
        """Send a text message. Returns the Meta message id."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": preview_url, "body": text},
        }
        data = await self._post(payload)
        msgs = data.get("messages") if isinstance(data, dict) else None
        if isinstance(msgs, list) and msgs:
            return msgs[0].get("id", "")
        return data.get("id", "") if isinstance(data, dict) else ""

    async def upload_media(self, file_bytes: bytes, mime_type: str, file_name: str) -> str:
        """Upload a media file to Meta. Returns the media id (h:xxxx)."""
        url = f"{self.base_url}/{self.phone_number_id}/media"
        files = {"file": (file_name, file_bytes, mime_type)}
        resp = await self._client.post(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            files=files,
            data={"messaging_product": "whatsapp", "type": mime_type},
        )
        data = self._raise_if_error(resp, (200, 201))
        media_id = data.get("id")
        if not media_id:
            raise WhatsAppError("Meta did not return a media id", resp.status_code)
        return media_id

    async def send_media(
        self,
        to: str,
        media_id: str,
        media_type: str,
        caption: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> str:
        """Send a previously uploaded media message. Returns Meta message id."""
        payload: dict = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": media_type,
            media_type: {"id": media_id},
        }
        if caption:
            payload[media_type]["caption"] = caption
        if file_name and media_type in ("document",):
            payload[media_type]["filename"] = file_name
        data = await self._post(payload)
        msgs = data.get("messages") if isinstance(data, dict) else None
        if isinstance(msgs, list) and msgs:
            return msgs[0].get("id", "")
        return data.get("id", "") if isinstance(data, dict) else ""

    async def send_image(self, to: str, media_id: str, caption: Optional[str] = None) -> str:
        return await self.send_media(to, media_id, "image", caption)

    async def send_document(self, to: str, media_id: str, caption=None, file_name=None) -> str:
        return await self.send_media(to, media_id, "document", caption, file_name)

    async def send_video(self, to: str, media_id: str, caption=None) -> str:
        return await self.send_media(to, media_id, "video", caption)

    async def send_audio(self, to: str, media_id: str) -> str:
        return await self.send_media(to, media_id, "audio")

    # ------------------------------------------------------------------ receive
    async def get_media_url(self, media_id: str) -> str:
        """Resolve a Meta media id to a temporary download URL."""
        data = await self._get(f"/{media_id}")
        url = data.get("url")
        if not url:
            raise WhatsAppError("Meta did not return a media url", 0)
        return url

    async def download_media(self, media_id: str, timeout: float = 60.0) -> bytes:
        """Download raw bytes for a Meta media id."""
        url = await self.get_media_url(media_id)
        resp = await self._client.get(
            url, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=timeout
        )
        if resp.status_code != 200:
            raise WhatsAppError(f"Failed to download media: {resp.status_code}", resp.status_code)
        return resp.content

    # ------------------------------------------------------------------ misc
    async def get_phone_numbers(self) -> list[dict]:
        """Fetch numbers for the configured id.

        The id may be a phone number id (most common) or a WhatsApp
        business account id. Try the phone number object first, then
        fall back to the WABA ``phone_numbers`` edge.
        """
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.base_url}/{self.phone_number_id}"

        # 1) Phone number node
        resp = await self._client.get(
            url,
            params={
                "fields": (
                    "id,display_phone_number,verified_name,quality_rating,"
                    "code_verification_status,platform_type"
                )
            },
            headers=headers,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and not data.get("error"):
                return [data]

        # 2) WABA id -> phone_numbers edge
        resp = await self._client.get(
            url, params={"fields": "phone_numbers"}, headers=headers
        )
        data = self._raise_if_error(resp, 200)
        return data.get("data", [])

    # ------------------------------------------------------------------ helpers
    async def _post(self, payload: dict) -> dict:
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        resp = await self._client.post(url, headers=self._headers, json=payload)
        # Meta returns 201 Created for successful sends (200 in some environments)
        return self._raise_if_error(resp, (200, 201))

    async def _get(self, path: str) -> dict:
        resp = await self._client.get(
            f"{self.base_url}{path}", headers={"Authorization": f"Bearer {self.access_token}"}
        )
        return self._raise_if_error(resp, 200)

    @staticmethod
    def _raise_if_error(resp: httpx.Response, expected) -> dict:
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        ok = (
            resp.status_code == expected
            if not isinstance(expected, (list, tuple))
            else resp.status_code in expected
        )
        if not ok:
            fb_code = None
            if isinstance(data, dict):
                err = data.get("error", {})
                fb_code = err.get("code") if isinstance(err, dict) else None
                msg = err.get("message", resp.text) if isinstance(err, dict) else resp.text
            else:
                msg = resp.text
            raise WhatsAppError(f"{msg} (HTTP {resp.status_code})", resp.status_code, fb_code)
        return data if isinstance(data, dict) else {}


def resolve_whatsapp_client(
    access_token: str, phone_number_id: str
) -> WhatsAppClient:
    """Factory that raises a friendly error when config is missing."""
    if not access_token or not phone_number_id:
        raise WhatsAppError(
            "WhatsApp Cloud API is not configured. "
            "Add your access token and phone number id in Settings."
        )
    return WhatsAppClient(access_token=access_token, phone_number_id=phone_number_id)
