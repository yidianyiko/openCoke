from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Protocol

import httpx

from coke.domains.conversation_runtime.models import (
    InboundMedia,
    InboundMediaStatusUpdate,
    Message,
)


class AsrClient(Protocol):
    def transcribe(self, *, storage_uri: str, mime: str | None = None) -> str:
        raise NotImplementedError


class VisionTextClient(Protocol):
    def describe(self, *, storage_uri: str, mime: str | None = None) -> str:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class MediaTextResolution:
    resolved_text: str | None
    media_status_updates: tuple[InboundMediaStatusUpdate, ...]
    suppress_turn: bool


@dataclass(frozen=True, slots=True)
class MediaBytes:
    content: bytes
    mime: str
    filename: str


class MediaTextResolver:
    def __init__(
        self,
        *,
        asr_client: AsrClient | None,
        vision_text_client: VisionTextClient | None,
    ) -> None:
        self.asr_client = asr_client
        self.vision_text_client = vision_text_client

    def resolve(
        self,
        *,
        message: Message,
        media: list[InboundMedia] | tuple[InboundMedia, ...],
    ) -> MediaTextResolution:
        if str(message.text or "").strip():
            return MediaTextResolution(
                resolved_text=None,
                media_status_updates=(),
                suppress_turn=False,
            )
        preserved = [item for item in media if item.processing_status == "preserved"]
        target = _first_media(preserved, "voice") or _first_media(preserved, "image")
        if target is None:
            return MediaTextResolution(
                resolved_text="",
                media_status_updates=(),
                suppress_turn=True,
            )
        try:
            resolved_text = self._resolve_target(target).strip()
        except Exception:
            resolved_text = ""
        if resolved_text:
            return MediaTextResolution(
                resolved_text=resolved_text,
                media_status_updates=(
                    InboundMediaStatusUpdate(
                        media_id=target.id,
                        processing_status="resolved",
                    ),
                ),
                suppress_turn=False,
            )
        return MediaTextResolution(
            resolved_text="",
            media_status_updates=(
                InboundMediaStatusUpdate(
                    media_id=target.id,
                    processing_status="failed",
                ),
            ),
            suppress_turn=True,
        )

    def _resolve_target(self, target: InboundMedia) -> str:
        mime = _mime_from_media(target)
        if target.media_type == "voice":
            if self.asr_client is None:
                return ""
            return self.asr_client.transcribe(storage_uri=target.storage_uri, mime=mime)
        if target.media_type == "image":
            if self.vision_text_client is None:
                return ""
            return self.vision_text_client.describe(
                storage_uri=target.storage_uri, mime=mime
            )
        return ""


class SiliconFlowAsrClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_id: str,
        timeout_s: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.timeout_s = timeout_s
        self._client = http_client or httpx.Client(timeout=timeout_s)

    def transcribe(self, *, storage_uri: str, mime: str | None = None) -> str:
        media = load_media_bytes(storage_uri, mime=mime, default_filename="voice.wav")
        response = self._client.post(
            f"{self.base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            data={"model": self.model_id},
            files={"file": (media.filename, media.content, media.mime)},
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        body = response.json()
        return str(body.get("text") or "").strip() if isinstance(body, dict) else ""


class SiliconFlowVisionTextClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_id: str,
        timeout_s: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.timeout_s = timeout_s
        self._client = http_client or httpx.Client(timeout=timeout_s)

    def describe(self, *, storage_uri: str, mime: str | None = None) -> str:
        data_uri = (
            storage_uri
            if storage_uri.startswith("data:")
            else media_to_data_uri(storage_uri, mime=mime)
        )
        response = self._client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model_id,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Convert this WeChat image into concise user text for a text-only assistant. "
                                    "Include visible in-image text and the actionable context."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": data_uri},
                            },
                        ],
                    }
                ],
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        body = response.json()
        try:
            return str(body["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            return ""


def load_media_bytes(
    storage_uri: str, *, mime: str | None, default_filename: str
) -> MediaBytes:
    if storage_uri.startswith("data:"):
        header, encoded = storage_uri.split(",", 1)
        header_mime = (
            header.removeprefix("data:").split(";", 1)[0]
            or mime
            or "application/octet-stream"
        )
        return MediaBytes(
            content=base64.b64decode(encoded),
            mime=header_mime,
            filename=default_filename,
        )
    response = httpx.get(storage_uri, timeout=30.0)
    response.raise_for_status()
    return MediaBytes(
        content=response.content,
        mime=mime or response.headers.get("content-type", "application/octet-stream"),
        filename=default_filename,
    )


def media_to_data_uri(storage_uri: str, *, mime: str | None) -> str:
    media = load_media_bytes(storage_uri, mime=mime, default_filename="image")
    return f"data:{media.mime};base64,{base64.b64encode(media.content).decode()}"


def _first_media(media: list[InboundMedia], media_type: str) -> InboundMedia | None:
    for item in media:
        if item.media_type == media_type:
            return item
    return None


def _mime_from_media(media: InboundMedia) -> str | None:
    value = media.agent_reference.get("mime")
    return value if isinstance(value, str) and value.strip() else None
