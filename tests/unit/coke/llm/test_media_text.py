from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coke.domains.conversation_runtime.models import (
    InboundMedia,
    InboundMediaStatusUpdate,
    Message,
)
from coke.llm.media_text import MediaTextResolver

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


class FakeAsrClient:
    def __init__(self, result: str | Exception) -> None:
        self.result = result
        self.calls = []

    def transcribe(self, *, storage_uri: str, mime: str | None = None) -> str:
        self.calls.append({"storage_uri": storage_uri, "mime": mime})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeVisionTextClient:
    def __init__(self, result: str | Exception) -> None:
        self.result = result
        self.calls = []

    def describe(self, *, storage_uri: str, mime: str | None = None) -> str:
        self.calls.append({"storage_uri": storage_uri, "mime": mime})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def message(text: str | None = "") -> Message:
    return Message(
        id="message_1",
        conversation_id="conversation_1",
        turn_id=None,
        direction="inbound",
        segment_index=None,
        seq=1,
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:1",
        text=text,
        payload={"provider": "wechat_personal"},
        facts_hash=None,
        created_at=NOW,
        updated_at=NOW,
    )


def media(media_type: str, storage_uri: str, mime: str | None) -> InboundMedia:
    return InboundMedia(
        id=f"media_{media_type}",
        message_id="message_1",
        media_type=media_type,
        storage_uri=storage_uri,
        processing_status="preserved",
        agent_reference={
            "type": media_type,
            "label": f"{media_type} message",
            **({"mime": mime} if mime else {}),
        },
        created_at=NOW,
        updated_at=NOW,
    )


def test_resolver_skips_models_when_message_text_already_exists():
    asr = FakeAsrClient("unused")
    vision = FakeVisionTextClient("unused")
    resolver = MediaTextResolver(asr_client=asr, vision_text_client=vision)

    result = resolver.resolve(
        message=message("native voice transcript"),
        media=[media("voice", "data:audio/wav;base64,UklGRg==", "audio/wav")],
    )

    assert result.resolved_text is None
    assert result.media_status_updates == ()
    assert result.suppress_turn is False
    assert asr.calls == []
    assert vision.calls == []


def test_resolver_uses_asr_for_empty_voice_message():
    asr = FakeAsrClient("remind me at 9")
    vision = FakeVisionTextClient("unused")
    resolver = MediaTextResolver(asr_client=asr, vision_text_client=vision)

    result = resolver.resolve(
        message=message(""),
        media=[media("voice", "data:audio/wav;base64,UklGRg==", "audio/wav")],
    )

    assert result.resolved_text == "remind me at 9"
    assert result.media_status_updates == (
        InboundMediaStatusUpdate(media_id="media_voice", processing_status="resolved"),
    )
    assert result.suppress_turn is False
    assert asr.calls == [
        {"storage_uri": "data:audio/wav;base64,UklGRg==", "mime": "audio/wav"}
    ]
    assert vision.calls == []


def test_resolver_uses_vision_for_empty_image_message():
    asr = FakeAsrClient("unused")
    vision = FakeVisionTextClient("The image contains a receipt total of 32 RMB.")
    resolver = MediaTextResolver(asr_client=asr, vision_text_client=vision)

    result = resolver.resolve(
        message=message(""),
        media=[media("image", "data:image/jpeg;base64,/9j/2w==", "image/jpeg")],
    )

    assert result.resolved_text == "The image contains a receipt total of 32 RMB."
    assert result.media_status_updates == (
        InboundMediaStatusUpdate(media_id="media_image", processing_status="resolved"),
    )
    assert result.suppress_turn is False
    assert asr.calls == []
    assert vision.calls == [
        {"storage_uri": "data:image/jpeg;base64,/9j/2w==", "mime": "image/jpeg"}
    ]


@pytest.mark.parametrize("client_result", ["", RuntimeError("model failed")])
def test_resolver_marks_failed_and_suppresses_turn_for_empty_resolution(
    client_result,
):
    asr = FakeAsrClient("unused")
    vision = FakeVisionTextClient(client_result)
    resolver = MediaTextResolver(asr_client=asr, vision_text_client=vision)

    result = resolver.resolve(
        message=message(""),
        media=[media("image", "data:image/jpeg;base64,/9j/2w==", "image/jpeg")],
    )

    assert result.resolved_text == ""
    assert result.media_status_updates == (
        InboundMediaStatusUpdate(media_id="media_image", processing_status="failed"),
    )
    assert result.suppress_turn is True
