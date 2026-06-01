# WeChat Personal Voice & Image Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert WeChat Personal voice and image inbound media into text before The Turn so the existing text-only runner receives the same input it would have received from a typed message.

**Architecture:** The connector forwards text plus readable media references; provider normalization maps those references into the existing `InboundMediaInput` pipeline and records them with the inbound message. The worker runs `MediaTextResolver` before `_inbound_trigger`, updates `Message.text` and `InboundMedia.processing_status`, then either builds the normal trigger from the updated row or records a pre-agent `no_reply` close decision for failed empty media so recovery does not resurrect the open input window.

**Tech Stack:** Python 3.12, Flask connector edge, SQLAlchemy/Postgres repositories, pytest, httpx, SiliconFlow OpenAI-compatible APIs, existing Coke conversation-runtime and worker surfaces.

---

## File Structure

- Modify: `provider_edges/wechat_personal_connector/app.py` - extract WeChat item `type: 2` image and `type: 3` voice media references and include `media` in the webhook payload.
- Modify: `tests/unit/coke/provider_edges/test_wechat_personal_connector.py` - connector unit coverage for image media and voice transcript-plus-media forwarding.
- Modify: `coke/domains/conversation_runtime/models.py` - extend `InboundMediaInput` with optional `mime` and add `InboundMediaStatusUpdate`.
- Modify: `coke/domains/channel_reachability/models.py` - add `NormalizedInbound.media` using the existing conversation-runtime media input DTO.
- Modify: `coke/providers/wechat_personal.py` - parse connector `media` arrays into `InboundMediaInput` values.
- Modify: `tests/unit/coke/channel_reachability/test_provider_adapters.py` - adapter coverage for valid and malformed WeChat Personal media.
- Modify: `coke/api/provider_webhooks.py` - pass normalized media to `record_inbound`.
- Modify: `tests/unit/coke/channel_reachability/test_provider_webhooks.py` - webhook coverage that media reaches the conversation runtime call while the route still returns 202.
- Modify: `coke/domains/conversation_runtime/repository.py` - add message/media read methods and atomic text/status write-back for media resolution.
- Modify: `coke/domains/conversation_runtime/service.py` - expose `get_message`, `inbound_media_for_message`, `resolve_inbound_media`, and allow `media_resolution_failed` pre-agent no-reply close decisions.
- Modify: `tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py` - service and in-memory repository coverage for text/status resolution and no-reply media suppression.
- Create: `coke/llm/media_text.py` - define `AsrClient`, `VisionTextClient`, `MediaTextResolver`, SiliconFlow client adapters, and `data:`/HTTP media loading.
- Modify: `coke/llm/config.py` - add config-driven ASR/VLM model fields with no concrete model defaults.
- Modify: `coke/llm/__init__.py` - export the media text ports and resolver.
- Create: `tests/unit/coke/llm/test_media_text.py` - resolver and client contract unit tests.
- Modify: `tests/unit/coke/llm/test_config.py` - config coverage for ASR/VLM model fields.
- Modify: `coke/composition.py` - add `media_text_resolver` to `CokeRuntime` and compose it from SiliconFlow config when model IDs are provided.
- Modify: `coke/worker/__main__.py` - run media resolution before `_inbound_trigger`; record pre-agent `no_reply` for failed empty media instead of invoking the runner.
- Create: `tests/unit/coke/worker/test_media_resolution.py` - worker ordering, trigger hydration, and failed-media suppression tests.
- Modify: `tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py` - end-to-end unit integration for native voice, image resolution, and unresolvable media no-reply behavior.
- Create: `scripts/eval-media-model-subset` - command wrapper that runs ASR/VLM subset evaluations against selected SiliconFlow model IDs.
- Create: `tests/unit/coke/llm/test_media_model_subset_eval.py` - unit coverage for eval manifest validation and model-selection command construction.
- Create: `docs/issues/2026-06-01-wechat-personal-media-model-selection.md` - active tracker for the required 30-50 case ASR and VLM subset evaluation evidence.

### Task 1: Connector Media Extraction And Forwarding

**Files:**
- Modify: `provider_edges/wechat_personal_connector/app.py:9-13,477-513`
- Test: `tests/unit/coke/provider_edges/test_wechat_personal_connector.py`

- [ ] **Step 1: Write the failing test**

Append these complete tests to `tests/unit/coke/provider_edges/test_wechat_personal_connector.py` after `test_poll_once_posts_account_bound_payload_and_context_token`:

```python
def test_poll_once_posts_image_media_payload_with_blank_text(state):
    ilink = FakeIlinkClient(
        updates={
            "get_updates_buf": "cursor-1",
            "msgs": [
                {
                    "from_user_id": "wxid_alice",
                    "context_token": "ctx-image-1",
                    "item_list": [
                        {
                            "type": 2,
                            "image_item": {
                                "data_uri": "data:image/jpeg;base64,/9j/2w==",
                                "mime": "image/jpeg",
                            },
                        }
                    ],
                }
            ],
        }
    )
    webhook = FakeWebhookClient()

    delivered = poll_once(
        ConnectorConfig(
            api_key="connector-key",
            webhook_url="http://coke-api/webhooks/wechat/personal",
            webhook_api_key="clean-webhook-key",
            webhook_inbound_secret="clean-webhook-secret",
        ),
        state=state,
        ilink_client=ilink,
        webhook_client=webhook,
    )

    assert delivered == 1
    assert webhook.posts[0]["json"] == {
        "account_id": "acct_1",
        "session_id": "session-1",
        "message_id": "ctx-image-1",
        "wxid": "wxid_alice",
        "text": "",
        "context_token": "ctx-image-1",
        "media": [
            {
                "media_type": "image",
                "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                "mime": "image/jpeg",
                "agent_label": "image",
            }
        ],
    }


def test_poll_once_posts_voice_transcript_and_media_payload(state):
    ilink = FakeIlinkClient(
        updates={
            "get_updates_buf": "cursor-1",
            "msgs": [
                {
                    "from_user_id": "wxid_alice",
                    "context_token": "ctx-voice-1",
                    "item_list": [
                        {
                            "type": 3,
                            "voice_item": {
                                "text": "remind me at nine",
                                "data_uri": "data:audio/wav;base64,UklGRg==",
                                "mime": "audio/wav",
                            },
                        }
                    ],
                }
            ],
        }
    )
    webhook = FakeWebhookClient()

    delivered = poll_once(
        ConnectorConfig(
            api_key="connector-key",
            webhook_url="http://coke-api/webhooks/wechat/personal",
            webhook_api_key="clean-webhook-key",
            webhook_inbound_secret="clean-webhook-secret",
        ),
        state=state,
        ilink_client=ilink,
        webhook_client=webhook,
    )

    assert delivered == 1
    assert webhook.posts[0]["json"] == {
        "account_id": "acct_1",
        "session_id": "session-1",
        "message_id": "ctx-voice-1",
        "wxid": "wxid_alice",
        "text": "remind me at nine",
        "context_token": "ctx-voice-1",
        "media": [
            {
                "media_type": "voice",
                "storage_uri": "data:audio/wav;base64,UklGRg==",
                "mime": "audio/wav",
                "agent_label": "voice message",
            }
        ],
    }


def test_poll_once_skips_malformed_image_without_readable_media(state):
    ilink = FakeIlinkClient(
        updates={
            "get_updates_buf": "cursor-1",
            "msgs": [
                {
                    "from_user_id": "wxid_alice",
                    "context_token": "ctx-image-bad",
                    "item_list": [{"type": 2, "image_item": {"cdn_url": "https://cdn.invalid/image"}}],
                }
            ],
        }
    )
    webhook = FakeWebhookClient()

    delivered = poll_once(
        ConnectorConfig(
            api_key="connector-key",
            webhook_url="http://coke-api/webhooks/wechat/personal",
        ),
        state=state,
        ilink_client=ilink,
        webhook_client=webhook,
    )

    assert delivered == 0
    assert webhook.posts == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py::test_poll_once_posts_image_media_payload_with_blank_text tests/unit/coke/provider_edges/test_wechat_personal_connector.py::test_poll_once_posts_voice_transcript_and_media_payload tests/unit/coke/provider_edges/test_wechat_personal_connector.py::test_poll_once_skips_malformed_image_without_readable_media -v`

Expected: FAIL with `AssertionError` on the image test because the posted payload has no `media` key, and FAIL with `AssertionError: assert 1 == 0` on the malformed image test because the current connector posts an empty text-only payload.

- [ ] **Step 3: Write minimal implementation**

Edit `provider_edges/wechat_personal_connector/app.py` with this complete replacement for `_clean_webhook_payload`, `_extract_text`, and the new helper block:

```python
@dataclass(frozen=True)
class ConnectorMediaPayload:
    media_type: str
    storage_uri: str
    mime: str
    agent_label: str

    def as_payload(self) -> dict[str, str]:
        return {
            "media_type": self.media_type,
            "storage_uri": self.storage_uri,
            "mime": self.mime,
            "agent_label": self.agent_label,
        }


def _clean_webhook_payload(
    message: dict[str, Any], session_id: str, session: dict[str, Any]
) -> dict[str, Any] | None:
    wxid = str(message.get("from_user_id") or "").strip()
    if not wxid:
        return None
    text = _extract_text(message)
    media = _extract_media(message)
    if text is None:
        return None
    if text == "" and _has_media_item(message) and not media:
        return None
    message_id = str(message.get("context_token") or "").strip()
    if not message_id:
        message_id = f"{wxid}:{uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(message, sort_keys=True))}"
    context_token = str(message.get("context_token") or "").strip()
    if not context_token:
        return None
    payload: dict[str, Any] = {
        "account_id": str(session.get("account_id") or ""),
        "session_id": session_id,
        "message_id": message_id,
        "wxid": wxid,
        "text": text,
        "context_token": context_token,
    }
    if media:
        payload["media"] = [item.as_payload() for item in media]
    return payload


def _extract_text(message: dict[str, Any]) -> str | None:
    for item in message.get("item_list") or []:
        item_type = item.get("type")
        if item_type == 1:
            text = str((item.get("text_item") or {}).get("text") or "").strip()
            if text:
                return text
        if item_type == 3:
            text = str((item.get("voice_item") or {}).get("text") or "").strip()
            if text:
                return text
    return ""


def _extract_media(message: dict[str, Any]) -> list[ConnectorMediaPayload]:
    media: list[ConnectorMediaPayload] = []
    for item in message.get("item_list") or []:
        item_type = item.get("type")
        if item_type == 2:
            image_item = item.get("image_item") or {}
            mime = _media_mime(image_item, default="image/jpeg")
            storage_uri = _readable_storage_uri(image_item, mime=mime)
            if storage_uri:
                media.append(
                    ConnectorMediaPayload(
                        media_type="image",
                        storage_uri=storage_uri,
                        mime=mime,
                        agent_label="image",
                    )
                )
        if item_type == 3:
            voice_item = item.get("voice_item") or {}
            mime = _media_mime(voice_item, default="audio/wav")
            storage_uri = _readable_storage_uri(voice_item, mime=mime)
            if storage_uri:
                media.append(
                    ConnectorMediaPayload(
                        media_type="voice",
                        storage_uri=storage_uri,
                        mime=mime,
                        agent_label="voice message",
                    )
                )
    return media


def _has_media_item(message: dict[str, Any]) -> bool:
    return any((item.get("type") in {2, 3}) for item in message.get("item_list") or [])


def _media_mime(item: Any, *, default: str) -> str:
    if not isinstance(item, dict):
        return default
    for key in ("mime", "mimetype", "content_type"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return default


def _readable_storage_uri(item: Any, *, mime: str) -> str | None:
    if not isinstance(item, dict):
        return None
    for key in ("storage_uri", "data_uri", "media_data_uri", "decoded_data_uri"):
        value = str(item.get(key) or "").strip()
        if value.startswith(("data:", "https://", "http://", "s3://")):
            return value
    for key in ("data_base64", "media_base64", "decoded_base64"):
        value = str(item.get(key) or "").strip()
        if value:
            return f"data:{mime};base64,{value}"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py::test_poll_once_posts_image_media_payload_with_blank_text tests/unit/coke/provider_edges/test_wechat_personal_connector.py::test_poll_once_posts_voice_transcript_and_media_payload tests/unit/coke/provider_edges/test_wechat_personal_connector.py::test_poll_once_skips_malformed_image_without_readable_media -v`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add provider_edges/wechat_personal_connector/app.py tests/unit/coke/provider_edges/test_wechat_personal_connector.py
git commit -m $'feat: forward wechat personal inbound media\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'
```

### Task 2: Normalize Media And Record It From Webhooks

**Files:**
- Modify: `coke/domains/conversation_runtime/models.py:147-152`
- Modify: `coke/domains/channel_reachability/models.py:3-7,105-118`
- Modify: `coke/providers/wechat_personal.py:1-21,41-62,152-157`
- Modify: `coke/api/provider_webhooks.py:63-71`
- Test: `tests/unit/coke/channel_reachability/test_provider_adapters.py`
- Test: `tests/unit/coke/channel_reachability/test_provider_webhooks.py`

- [ ] **Step 1: Write the failing test**

Append this complete test to `tests/unit/coke/channel_reachability/test_provider_adapters.py` after `test_wechat_personal_rejects_malformed_ilink_optional_fields`:

```python
def test_wechat_personal_normalizes_media_into_inbound_media_input():
    inbound = WeChatPersonalAdapter(now=lambda: NOW).normalize_inbound(
        {
            "account_id": "acct_1",
            "session_id": "session_1",
            "message_id": "wx_msg_image_1",
            "wxid": "wxid_alice",
            "text": "",
            "context_token": "ctx-image-1",
            "media": [
                {
                    "media_type": "image",
                    "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                    "mime": "image/jpeg",
                    "agent_label": "image",
                }
            ],
        }
    )

    assert inbound.text == ""
    assert len(inbound.media) == 1
    assert inbound.media[0].media_type == "image"
    assert inbound.media[0].storage_uri == "data:image/jpeg;base64,/9j/2w=="
    assert inbound.media[0].mime == "image/jpeg"
    assert inbound.media[0].agent_label == "image"


@pytest.mark.parametrize(
    "media",
    [
        [{"media_type": "image", "storage_uri": "", "mime": "image/jpeg", "agent_label": "image"}],
        [{"media_type": "video", "storage_uri": "data:video/mp4;base64,AAAA", "mime": "video/mp4", "agent_label": "video"}],
        [{"media_type": "image", "storage_uri": "data:image/jpeg;base64,/9j/2w==", "mime": {"bad": "value"}, "agent_label": "image"}],
        [{"media_type": "image", "storage_uri": "data:image/jpeg;base64,/9j/2w==", "mime": "image/jpeg", "agent_label": ""}],
    ],
)
def test_wechat_personal_rejects_malformed_media(media):
    payload = {
        "account_id": "acct_1",
        "session_id": "session_1",
        "message_id": "wx_msg_image_bad",
        "wxid": "wxid_alice",
        "text": "",
        "context_token": "ctx-image-bad",
        "media": media,
    }

    with pytest.raises(ChannelReachabilityError, match="invalid_provider_payload") as exc_info:
        WeChatPersonalAdapter(now=lambda: NOW).normalize_inbound(payload)

    assert exc_info.value.fact["type"] == "invalid_provider_payload"
    assert exc_info.value.fact["provider_type"] == "wechat_personal"
    assert exc_info.value.fact["field"] == "media"
```

Update `FakeConversationRuntimeService.record_inbound` in `tests/unit/coke/channel_reachability/test_provider_webhooks.py` to accept and store `media`, then append this complete webhook test after `test_wechat_personal_webhook_accepts_account_bound_ilink_payload`:

```python
def test_wechat_personal_webhook_records_media_with_durable_inbound_turn():
    conversation_runtime = FakeConversationRuntimeService()
    commits = []
    client, _service, _adapters = make_client(
        adapters={
            "wechat_personal": WeChatPersonalAdapter(
                now=lambda: datetime(2026, 5, 29, tzinfo=UTC)
            )
        },
        conversation_runtime_service=conversation_runtime,
        commit_callback=lambda: commits.append("committed"),
    )

    response = client.post(
        "/webhooks/wechat/personal",
        json={
            "account_id": "acct_1",
            "session_id": "session_1",
            "message_id": "wx_msg_image_1",
            "wxid": "wxid_lizihao",
            "text": "",
            "context_token": "ctx-image-1",
            "media": [
                {
                    "media_type": "image",
                    "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                    "mime": "image/jpeg",
                    "agent_label": "image",
                }
            ],
        },
    )

    assert response.status_code == 202
    assert conversation_runtime.calls[0]["text"] == ""
    assert len(conversation_runtime.calls[0]["media"]) == 1
    assert conversation_runtime.calls[0]["media"][0].media_type == "image"
    assert conversation_runtime.calls[0]["media"][0].storage_uri == "data:image/jpeg;base64,/9j/2w=="
    assert conversation_runtime.calls[0]["media"][0].mime == "image/jpeg"
    assert conversation_runtime.calls[0]["media"][0].agent_label == "image"
    assert commits == ["committed"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py::test_wechat_personal_normalizes_media_into_inbound_media_input tests/unit/coke/channel_reachability/test_provider_adapters.py::test_wechat_personal_rejects_malformed_media tests/unit/coke/channel_reachability/test_provider_webhooks.py::test_wechat_personal_webhook_records_media_with_durable_inbound_turn -v`

Expected: FAIL with `AttributeError: 'NormalizedInbound' object has no attribute 'media'` and `TypeError: FakeConversationRuntimeService.record_inbound() got an unexpected keyword argument 'media'`.

- [ ] **Step 3: Write minimal implementation**

Change `coke/domains/conversation_runtime/models.py` so `InboundMediaInput` and the new status update DTO are:

```python
@dataclass(frozen=True, slots=True)
class InboundMediaInput:
    media_type: str
    storage_uri: str
    agent_label: str
    mime: str | None = None


@dataclass(frozen=True, slots=True)
class InboundMediaStatusUpdate:
    media_id: str
    processing_status: str
```

Change `coke/domains/channel_reachability/models.py` imports and `NormalizedInbound` to:

```python
from coke.domains.conversation_runtime.models import InboundMediaInput
```

```python
@dataclass(frozen=True, slots=True)
class NormalizedInbound:
    provider_type: str
    provider_subject: str
    text: str
    raw_event_id: str
    received_at: datetime
    pairing_code: str | None = None
    sender_display_name: str | None = None
    account_id: str | None = None
    connector_session_id: str | None = None
    context_token: str | None = None
    payload: Mapping[str, ImmutableJsonValue] | None = None
    media: tuple[InboundMediaInput, ...] = ()
```

Change `coke/providers/wechat_personal.py` imports and `normalize_inbound` payload construction to:

```python
from typing import Any

from coke.domains.channel_reachability.models import (
    DeliveryAttemptResult,
    DeliveryRoute,
    NormalizedInbound,
)
from coke.domains.conversation_runtime.models import InboundMediaInput
```

```python
    def normalize_inbound(self, payload: Mapping[str, object]) -> NormalizedInbound:
        return NormalizedInbound(
            provider_type=self.provider_type,
            provider_subject=required_string_field(self.provider_type, payload, "wxid"),
            text=optional_string_field(
                self.provider_type, payload, "text", allow_blank=True
            )
            or "",
            raw_event_id=required_string_field(
                self.provider_type, payload, "message_id"
            ),
            received_at=self._now(),
            sender_display_name=_sender_display_name(payload),
            account_id=optional_string_field(self.provider_type, payload, "account_id"),
            connector_session_id=optional_string_field(
                self.provider_type, payload, "session_id"
            ),
            context_token=optional_string_field(
                self.provider_type, payload, "context_token"
            ),
            payload=freeze_json(dict(payload), provider_type=self.provider_type),
            media=_media_inputs(payload),
        )
```

Add this complete helper block to `coke/providers/wechat_personal.py`:

```python
def _media_inputs(payload: Mapping[str, object]) -> tuple[InboundMediaInput, ...]:
    raw_media = payload.get("media")
    if raw_media is None:
        return ()
    if not isinstance(raw_media, list | tuple):
        raise invalid_provider_payload("wechat_personal", "media", "invalid_media")
    media: list[InboundMediaInput] = []
    for item in raw_media:
        if not isinstance(item, Mapping):
            raise invalid_provider_payload("wechat_personal", "media", "invalid_media")
        media_type = _required_media_string(item, "media_type")
        if media_type not in {"voice", "image"}:
            raise invalid_provider_payload("wechat_personal", "media", "invalid_media")
        storage_uri = _required_media_string(item, "storage_uri")
        mime = _optional_media_string(item, "mime")
        agent_label = _required_media_string(item, "agent_label")
        media.append(
            InboundMediaInput(
                media_type=media_type,
                storage_uri=storage_uri,
                mime=mime,
                agent_label=agent_label,
            )
        )
    return tuple(media)


def _required_media_string(item: Mapping[str, object], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise invalid_provider_payload("wechat_personal", "media", "invalid_media")
    return value.strip()


def _optional_media_string(item: Mapping[str, object], field: str) -> str | None:
    value = item.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise invalid_provider_payload("wechat_personal", "media", "invalid_media")
    return value.strip() or None
```

Change `coke/api/provider_webhooks.py` `record_inbound` call to:

```python
            inbound_record = conversation_runtime_service.record_inbound(
                account_id=accepted.account_id,
                channel_identity_id=accepted.channel_identity_id,
                causal_inbound_event_id=accepted.raw_event_id,
                text=inbound_event.text,
                payload=dict(inbound_event.payload or {}),
                traceparent=_request_traceparent(),
                media=inbound_event.media,
            )
```

Change `FakeConversationRuntimeService.record_inbound` in `tests/unit/coke/channel_reachability/test_provider_webhooks.py` to:

```python
    def record_inbound(
        self,
        *,
        account_id,
        channel_identity_id,
        causal_inbound_event_id,
        text,
        payload,
        traceparent,
        media=None,
    ):
        self.calls.append(
            {
                "account_id": account_id,
                "channel_identity_id": channel_identity_id,
                "causal_inbound_event_id": causal_inbound_event_id,
                "text": text,
                "payload": payload,
                "traceparent": traceparent,
                "media": tuple(media or ()),
            }
        )
        return SimpleNamespace(
            conversation=SimpleNamespace(id="conversation_1"),
            message=SimpleNamespace(id="message_1", seq=1),
        )
```

Change `ConversationRuntimeService.record_inbound` media preservation in `coke/domains/conversation_runtime/service.py:96-111` to include `mime` in `agent_reference`:

```python
        preserved_media = tuple(
            InboundMedia(
                id=self._id_factory("inbound_media"),
                message_id=message.id,
                media_type=item.media_type,
                storage_uri=item.storage_uri,
                processing_status="preserved",
                agent_reference={
                    "type": item.media_type,
                    "label": item.agent_label,
                    **({"mime": item.mime} if item.mime else {}),
                },
                created_at=now,
                updated_at=now,
            )
            for item in (media or ())
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_provider_adapters.py::test_wechat_personal_normalizes_media_into_inbound_media_input tests/unit/coke/channel_reachability/test_provider_adapters.py::test_wechat_personal_rejects_malformed_media tests/unit/coke/channel_reachability/test_provider_webhooks.py::test_wechat_personal_webhook_records_media_with_durable_inbound_turn -v`

Expected: PASS with `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add coke/domains/conversation_runtime/models.py coke/domains/channel_reachability/models.py coke/providers/wechat_personal.py coke/api/provider_webhooks.py tests/unit/coke/channel_reachability/test_provider_adapters.py tests/unit/coke/channel_reachability/test_provider_webhooks.py
git commit -m $'feat: preserve normalized inbound media\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'
```

### Task 3: Conversation Runtime Media Resolution Write-Back

**Files:**
- Modify: `coke/domains/conversation_runtime/repository.py:20-103,105-449,451-760`
- Modify: `coke/domains/conversation_runtime/service.py:11-28,260-323,388-444`
- Test: `tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py`

- [ ] **Step 1: Write the failing test**

Append this complete test block to `tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py`:

```python
def test_resolve_inbound_media_updates_message_text_and_media_status(service, repository):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:image-1",
        text="",
        payload={"provider": "wechat_personal"},
        media=[
            InboundMediaInput(
                media_type="image",
                storage_uri="data:image/jpeg;base64,/9j/2w==",
                mime="image/jpeg",
                agent_label="image",
            )
        ],
        traceparent=TRACEPARENT,
    )

    updated = service.resolve_inbound_media(
        message_id=inbound.message.id,
        resolved_text="The image says buy milk at 6 PM.",
        media_status_updates=[
            InboundMediaStatusUpdate(
                media_id=inbound.media[0].id,
                processing_status="resolved",
            )
        ],
    )
    started = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:image-1",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    assert updated.text == "The image says buy milk at 6 PM."
    assert repository.messages_by_id[inbound.message.id].text == "The image says buy milk at 6 PM."
    assert repository.inbound_media_by_id[inbound.media[0].id].processing_status == "resolved"
    assert started.input_messages[0].text == "The image says buy milk at 6 PM."


def test_media_resolution_failed_no_reply_closes_window_without_reply(service, repository):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:image-failed",
        text="",
        payload={"provider": "wechat_personal"},
        media=[
            InboundMediaInput(
                media_type="image",
                storage_uri="data:image/jpeg;base64,bad",
                mime="image/jpeg",
                agent_label="image",
            )
        ],
        traceparent=TRACEPARENT,
    )
    service.resolve_inbound_media(
        message_id=inbound.message.id,
        resolved_text="",
        media_status_updates=[
            InboundMediaStatusUpdate(
                media_id=inbound.media[0].id,
                processing_status="failed",
            )
        ],
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:image-failed",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    disposition = service.commit_no_reply(
        turn_id=turn.turn.id,
        reason_code="media_resolution_failed",
    )

    saved_conversation = repository.get_conversation(inbound.conversation.id)
    assert disposition.disposition == "no_reply"
    assert disposition.reason_code == "media_resolution_failed"
    assert saved_conversation is not None
    assert saved_conversation.last_closed_inbound_seq == inbound.message.seq
    assert service.repository.outbound_messages_for_turn(turn.turn.id) == []
```

Update the imports at the top of the test file:

```python
from coke.domains.conversation_runtime.models import (
    ConversationRuntimeError,
    InboundMediaInput,
    InboundMediaStatusUpdate,
    Message,
    OutboxRecord,
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py::test_resolve_inbound_media_updates_message_text_and_media_status tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py::test_media_resolution_failed_no_reply_closes_window_without_reply -v`

Expected: FAIL with `ImportError: cannot import name 'InboundMediaStatusUpdate'` if Task 2 is not complete, or FAIL with `AttributeError: 'ConversationRuntimeService' object has no attribute 'resolve_inbound_media'`.

- [ ] **Step 3: Write minimal implementation**

Update `coke/domains/conversation_runtime/repository.py` protocol with these methods:

```python
    def get_message(self, message_id: str) -> Message | None:
        raise NotImplementedError

    def inbound_media_for_message(self, message_id: str) -> list[InboundMedia]:
        raise NotImplementedError

    def resolve_inbound_media(
        self,
        message_id: str,
        resolved_text: str | None,
        media_status_updates: Sequence[InboundMediaStatusUpdate],
        resolved_at: datetime,
    ) -> Message:
        raise NotImplementedError
```

Add the imports:

```python
from collections.abc import Callable, Mapping, Sequence
```

```python
from coke.domains.conversation_runtime.models import (
    Conversation,
    ConversationRuntimeError,
    InboundMedia,
    InboundMediaStatusUpdate,
    Message,
    OutboxRecord,
    OutputDisposition,
    StagedCommand,
    Turn,
    WaitingReplyCandidate,
)
```

Add these complete methods to `InMemoryConversationRuntimeRepository` after `get_conversation_by_account`:

```python
    def get_message(self, message_id: str) -> Message | None:
        return self.messages_by_id.get(message_id)

    def inbound_media_for_message(self, message_id: str) -> list[InboundMedia]:
        media = [
            item
            for item in self.inbound_media_by_id.values()
            if item.message_id == message_id
        ]
        media.sort(key=lambda item: (item.created_at, item.id))
        return media

    def resolve_inbound_media(
        self,
        message_id: str,
        resolved_text: str | None,
        media_status_updates: Sequence[InboundMediaStatusUpdate],
        resolved_at: datetime,
    ) -> Message:
        message = self.messages_by_id.get(message_id)
        if message is None:
            raise ConversationRuntimeError("message_not_found")
        update_by_id = {item.media_id: item for item in media_status_updates}
        for media_id, update in update_by_id.items():
            media = self.inbound_media_by_id.get(media_id)
            if media is None:
                raise ConversationRuntimeError("inbound_media_not_found")
            if media.message_id != message_id:
                raise ConversationRuntimeError("media_message_mismatch")
            if update.processing_status not in {"preserved", "resolved", "failed"}:
                raise ConversationRuntimeError("invalid_media_processing_status")
        updated_message = replace(
            message,
            text=resolved_text,
            updated_at=resolved_at,
        )
        self.messages_by_id[message_id] = updated_message
        for media_id, update in update_by_id.items():
            media = self.inbound_media_by_id[media_id]
            self.inbound_media_by_id[media_id] = replace(
                media,
                processing_status=update.processing_status,
                updated_at=resolved_at,
            )
        return updated_message
```

Add these complete methods to `PostgresConversationRuntimeRepository` after `get_conversation_by_account`:

```python
    def get_message(self, message_id: str) -> Message | None:
        row = one_or_none(self.session, schema.message, schema.message.c.id == db_id(message_id))
        return _message(row) if row else None

    def inbound_media_for_message(self, message_id: str) -> list[InboundMedia]:
        rows = self.session.execute(
            sa.select(schema.inbound_media)
            .where(schema.inbound_media.c.message_id == db_id(message_id))
            .order_by(schema.inbound_media.c.created_at.asc(), schema.inbound_media.c.id.asc())
        ).mappings()
        return [_media(dict(row)) for row in rows]

    def resolve_inbound_media(
        self,
        message_id: str,
        resolved_text: str | None,
        media_status_updates: Sequence[InboundMediaStatusUpdate],
        resolved_at: datetime,
    ) -> Message:
        update_by_id = {item.media_id: item for item in media_status_updates}
        for update in update_by_id.values():
            if update.processing_status not in {"preserved", "resolved", "failed"}:
                raise ConversationRuntimeError("invalid_media_processing_status")

        def _write() -> Message:
            message_row = self.session.execute(
                sa.select(schema.message)
                .where(schema.message.c.id == db_id(message_id))
                .with_for_update()
            ).mappings().one_or_none()
            if message_row is None:
                raise ConversationRuntimeError("message_not_found")
            for update in update_by_id.values():
                media_row = self.session.execute(
                    sa.select(schema.inbound_media)
                    .where(schema.inbound_media.c.id == db_id(update.media_id))
                    .with_for_update()
                ).mappings().one_or_none()
                if media_row is None:
                    raise ConversationRuntimeError("inbound_media_not_found")
                if db_id(media_row["message_id"]) != message_id:
                    raise ConversationRuntimeError("media_message_mismatch")
                self.session.execute(
                    schema.inbound_media.update()
                    .where(schema.inbound_media.c.id == db_id(update.media_id))
                    .values(
                        processing_status=update.processing_status,
                        updated_at=resolved_at,
                    )
                )
            self.session.execute(
                schema.message.update()
                .where(schema.message.c.id == db_id(message_id))
                .values(text=resolved_text, updated_at=resolved_at)
            )
            updated_row = self.session.execute(
                sa.select(schema.message).where(schema.message.c.id == db_id(message_id))
            ).mappings().one()
            return _message(dict(updated_row))

        return _write()
```

Add these service methods to `coke/domains/conversation_runtime/service.py` after `get_disposition`:

```python
    def get_message(self, message_id: str) -> Message:
        message = self.repository.get_message(message_id)
        if message is None:
            raise ConversationRuntimeError("message_not_found")
        return message

    def inbound_media_for_message(self, message_id: str) -> tuple[InboundMedia, ...]:
        self.get_message(message_id)
        return tuple(self.repository.inbound_media_for_message(message_id))

    def resolve_inbound_media(
        self,
        message_id: str,
        resolved_text: str | None,
        media_status_updates: Sequence[InboundMediaStatusUpdate],
    ) -> Message:
        self.get_message(message_id)
        return self.repository.resolve_inbound_media(
            message_id,
            resolved_text,
            tuple(media_status_updates),
            self._now(),
        )
```

Update `commit_no_reply` in `coke/domains/conversation_runtime/service.py:260-267` to:

```python
    def commit_no_reply(
        self,
        turn_id: str,
        reason_code: str = "intentional_no_reply",
        materialize_staged_command: Callable[[StagedCommand], Any] | None = None,
    ) -> OutputDisposition:
        if reason_code not in {"intentional_no_reply", "media_resolution_failed"}:
            raise ConversationRuntimeError("invalid_no_reply_reason")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py::test_resolve_inbound_media_updates_message_text_and_media_status tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py::test_media_resolution_failed_no_reply_closes_window_without_reply -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add coke/domains/conversation_runtime/repository.py coke/domains/conversation_runtime/service.py tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py
git commit -m $'feat: resolve inbound media into conversation text\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'
```

### Task 4: Media Text Resolver Ports And SiliconFlow Clients

**Files:**
- Create: `coke/llm/media_text.py`
- Modify: `coke/llm/config.py:23-94`
- Modify: `coke/llm/__init__.py:1-13`
- Test: `tests/unit/coke/llm/test_media_text.py`
- Test: `tests/unit/coke/llm/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/coke/llm/test_media_text.py` with this complete content:

```python
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
    assert asr.calls == [{"storage_uri": "data:audio/wav;base64,UklGRg==", "mime": "audio/wav"}]
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
    assert vision.calls == [{"storage_uri": "data:image/jpeg;base64,/9j/2w==", "mime": "image/jpeg"}]


@pytest.mark.parametrize("client_result", ["", RuntimeError("model failed")])
def test_resolver_marks_failed_and_suppresses_turn_for_empty_resolution(client_result):
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
```

Append this complete test to `tests/unit/coke/llm/test_config.py`:

```python
def test_siliconflow_config_reads_media_model_ids_without_defaults():
    config = SiliconFlowLLMConfig.from_env(
        {
            "SiliconFlow_API_KEY": "test-key",
            "COKE_ASR_MODEL": "sensevoice-candidate",
            "COKE_VISION_TEXT_MODEL": "qwen-vl-candidate",
            "COKE_MEDIA_MODEL_TIMEOUT_S": "70",
        }
    )

    assert config.asr_model == "sensevoice-candidate"
    assert config.vision_text_model == "qwen-vl-candidate"
    assert config.media_model_timeout_s == 70.0


def test_siliconflow_config_leaves_media_model_ids_unset_until_subset_eval_selects_them():
    config = SiliconFlowLLMConfig.from_env({"SiliconFlow_API_KEY": "test-key"})

    assert config.asr_model is None
    assert config.vision_text_model is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/coke/llm/test_media_text.py tests/unit/coke/llm/test_config.py::test_siliconflow_config_reads_media_model_ids_without_defaults tests/unit/coke/llm/test_config.py::test_siliconflow_config_leaves_media_model_ids_unset_until_subset_eval_selects_them -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'coke.llm.media_text'` and `AttributeError: 'SiliconFlowLLMConfig' object has no attribute 'asr_model'`.

- [ ] **Step 3: Write minimal implementation**

Create `coke/llm/media_text.py` with this complete content:

```python
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Protocol

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
            return self.vision_text_client.describe(storage_uri=target.storage_uri, mime=mime)
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
        data_uri = storage_uri if storage_uri.startswith("data:") else media_to_data_uri(storage_uri, mime=mime)
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


def load_media_bytes(storage_uri: str, *, mime: str | None, default_filename: str) -> MediaBytes:
    if storage_uri.startswith("data:"):
        header, encoded = storage_uri.split(",", 1)
        header_mime = header.removeprefix("data:").split(";", 1)[0] or mime or "application/octet-stream"
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
```

Modify `coke/llm/config.py` by adding these constants:

```python
DEFAULT_MEDIA_MODEL_TIMEOUT_S = 60.0
```

Extend `SiliconFlowLLMConfig` with these fields:

```python
    asr_model: str | None = None
    vision_text_model: str | None = None
    media_model_timeout_s: float = DEFAULT_MEDIA_MODEL_TIMEOUT_S
```

Extend `from_env` with:

```python
            asr_model=_optional(source, "COKE_ASR_MODEL"),
            vision_text_model=_optional(source, "COKE_VISION_TEXT_MODEL"),
            media_model_timeout_s=_positive_float(
                source,
                "COKE_MEDIA_MODEL_TIMEOUT_S",
                DEFAULT_MEDIA_MODEL_TIMEOUT_S,
            ),
```

Add this helper to `coke/llm/config.py`:

```python
def _optional(source: Mapping[str, str], key: str) -> str | None:
    value = (source.get(key) or "").strip()
    return value or None
```

Modify `coke/llm/__init__.py` to export the new ports:

```python
from coke.llm.media_text import (
    AsrClient,
    MediaTextResolution,
    MediaTextResolver,
    SiliconFlowAsrClient,
    SiliconFlowVisionTextClient,
    VisionTextClient,
)
```

```python
    "AsrClient",
    "MediaTextResolution",
    "MediaTextResolver",
    "SiliconFlowAsrClient",
    "SiliconFlowVisionTextClient",
    "VisionTextClient",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/coke/llm/test_media_text.py tests/unit/coke/llm/test_config.py::test_siliconflow_config_reads_media_model_ids_without_defaults tests/unit/coke/llm/test_config.py::test_siliconflow_config_leaves_media_model_ids_unset_until_subset_eval_selects_them -v`

Expected: PASS with `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add coke/llm/media_text.py coke/llm/config.py coke/llm/__init__.py tests/unit/coke/llm/test_media_text.py tests/unit/coke/llm/test_config.py
git commit -m $'feat: add media text resolver ports\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'
```

### Task 5: Compose Media Resolver From Settings

**Files:**
- Modify: `coke/config.py:1-130`
- Modify: `coke/composition.py:63-70,105-128,1365-1542`
- Test: `tests/unit/coke/test_backend_foundation.py`
- Test: `tests/integration/coke/test_runtime_wiring.py`

- [ ] **Step 1: Write the failing test**

Append this complete test to `tests/unit/coke/test_backend_foundation.py`:

```python
def test_settings_from_env_reads_media_model_configuration(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SiliconFlow_API_KEY", "sf-key")
    monkeypatch.setenv("COKE_ASR_MODEL", "sensevoice-candidate")
    monkeypatch.setenv("COKE_VISION_TEXT_MODEL", "qwen-vl-candidate")
    monkeypatch.setenv("COKE_MEDIA_MODEL_TIMEOUT_S", "75")

    settings = Settings.from_env()

    assert settings.asr_model == "sensevoice-candidate"
    assert settings.vision_text_model == "qwen-vl-candidate"
    assert settings.media_model_timeout_s == 75.0
```

Append this complete test to `tests/integration/coke/test_runtime_wiring.py`:

```python
def test_runtime_wires_media_text_resolver_when_media_models_are_configured(monkeypatch):
    settings = Settings(
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        siliconflow_api_key="sf-key",
        llm_fake=False,
        asr_model="sensevoice-candidate",
        vision_text_model="qwen-vl-candidate",
    )

    runtime = build_runtime_from_settings(settings, redis_client=fakeredis.FakeRedis(decode_responses=True))

    assert runtime.media_text_resolver is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py::test_settings_from_env_reads_media_model_configuration tests/integration/coke/test_runtime_wiring.py::test_runtime_wires_media_text_resolver_when_media_models_are_configured -v`

Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'asr_model'` and `TypeError: Settings.__init__() got an unexpected keyword argument 'asr_model'`.

- [ ] **Step 3: Write minimal implementation**

Add these fields to `Settings` in `coke/config.py`:

```python
    asr_model: str | None = None
    vision_text_model: str | None = None
    media_model_timeout_s: float = DEFAULT_MEDIA_MODEL_TIMEOUT_S
```

Add these entries to `Settings.from_env`:

```python
            asr_model=_optional(source, "COKE_ASR_MODEL"),
            vision_text_model=_optional(source, "COKE_VISION_TEXT_MODEL"),
            media_model_timeout_s=_positive_float(
                source,
                "COKE_MEDIA_MODEL_TIMEOUT_S",
                DEFAULT_MEDIA_MODEL_TIMEOUT_S,
            ),
```

Modify `coke/composition.py` imports:

```python
from coke.llm.media_text import (
    MediaTextResolver,
    SiliconFlowAsrClient,
    SiliconFlowVisionTextClient,
)
```

Add this field to `CokeRuntime`:

```python
    media_text_resolver: MediaTextResolver | None = None
```

Change `_llm_from_settings` to return four values:

```python
def _llm_from_settings(settings):
    if settings.llm_fake:
        return FakeSemanticInterpreter(), FakeInteractionAgent(), FakeReminderDetector(), None
    if not settings.siliconflow_api_key:
        raise ConfigurationError("SiliconFlow_API_KEY is required for LLM composition")
    llm_config = SiliconFlowLLMConfig(
        api_key=settings.siliconflow_api_key,
        base_url=settings.siliconflow_base_url,
        interaction_model=settings.interaction_model,
        interpreter_model=settings.interpreter_model,
        detector_model=settings.detector_model,
        interaction_timeout_s=settings.interaction_timeout_s,
        agno_database_url=settings.agno_database_url,
        agno_create_schema=settings.agno_create_schema,
        asr_model=settings.asr_model,
        vision_text_model=settings.vision_text_model,
        media_model_timeout_s=settings.media_model_timeout_s,
    )
    media_text_resolver = None
    if llm_config.asr_model or llm_config.vision_text_model:
        media_text_resolver = MediaTextResolver(
            asr_client=(
                SiliconFlowAsrClient(
                    api_key=llm_config.api_key,
                    base_url=llm_config.base_url,
                    model_id=llm_config.asr_model,
                    timeout_s=llm_config.media_model_timeout_s,
                )
                if llm_config.asr_model
                else None
            ),
            vision_text_client=(
                SiliconFlowVisionTextClient(
                    api_key=llm_config.api_key,
                    base_url=llm_config.base_url,
                    model_id=llm_config.vision_text_model,
                    timeout_s=llm_config.media_model_timeout_s,
                )
                if llm_config.vision_text_model
                else None
            ),
        )
    return (
        SiliconFlowSemanticInterpreter.from_model(
            llm_config.create_interpreter_model()
        ),
        AgnoInteractionAgent.from_config(llm_config),
        SiliconFlowReminderDetector.from_model(llm_config.create_detector_model()),
        media_text_resolver,
    )
```

Change both callers in `build_runtime_from_settings` to unpack and pass `media_text_resolver`, and set it in every `CokeRuntime(...)` construction:

```python
    semantic_interpreter, interaction_agent, reminder_detector, media_text_resolver = _llm_from_settings(
        settings
    )
```

```python
            media_text_resolver=media_text_resolver,
```

```python
        media_text_resolver=media_text_resolver,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py::test_settings_from_env_reads_media_model_configuration tests/integration/coke/test_runtime_wiring.py::test_runtime_wires_media_text_resolver_when_media_models_are_configured -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add coke/config.py coke/composition.py tests/unit/coke/test_backend_foundation.py tests/integration/coke/test_runtime_wiring.py
git commit -m $'feat: compose media text resolver from settings\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'
```

### Task 6: Worker Pre-Trigger Resolution And Suppression

**Files:**
- Modify: `coke/worker/__main__.py:472-515`
- Test: `tests/unit/coke/worker/test_media_resolution.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/coke/worker/test_media_resolution.py` with this complete content:

```python
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import coke.worker.__main__ as worker_main
from coke.domains.conversation_runtime.models import (
    InboundMedia,
    InboundMediaStatusUpdate,
    Message,
    OutputDisposition,
    Turn,
    TurnStartResult,
)
from coke.llm.media_text import MediaTextResolution
from coke.worker.stream_consumer import StreamEvent

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


class FakeConversationRuntimeService:
    def __init__(self, *, message_text: str | None, media_status: str = "preserved") -> None:
        self.message = Message(
            id="message_1",
            conversation_id="conversation_1",
            turn_id=None,
            direction="inbound",
            segment_index=None,
            seq=1,
            channel_identity_id="channel_identity_1",
            causal_inbound_event_id="provider:1",
            text=message_text,
            payload={"provider": "wechat_personal"},
            facts_hash=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.media = [
            InboundMedia(
                id="media_1",
                message_id="message_1",
                media_type="image",
                storage_uri="data:image/jpeg;base64,/9j/2w==",
                processing_status=media_status,
                agent_reference={"type": "image", "label": "image", "mime": "image/jpeg"},
                created_at=NOW,
                updated_at=NOW,
            )
        ]
        self.resolution_calls = []
        self.started_turns = []
        self.no_reply_calls = []

    def get_message(self, message_id):
        assert message_id == "message_1"
        return self.message

    def inbound_media_for_message(self, message_id):
        assert message_id == "message_1"
        return tuple(self.media)

    def resolve_inbound_media(self, message_id, resolved_text, media_status_updates):
        self.resolution_calls.append(
            {
                "message_id": message_id,
                "resolved_text": resolved_text,
                "media_status_updates": tuple(media_status_updates),
            }
        )
        self.message = replace(
            self.message,
            text=resolved_text,
            updated_at=NOW,
        )
        return self.message

    def start_turn(self, conversation_id, trigger_id, trigger_type, mode):
        self.started_turns.append(
            {
                "conversation_id": conversation_id,
                "trigger_id": trigger_id,
                "trigger_type": trigger_type,
                "mode": mode,
            }
        )
        return TurnStartResult(
            turn=Turn(
                id="turn_1",
                conversation_id=conversation_id,
                trigger_id=trigger_id,
                trigger_type=trigger_type,
                mode=mode,
                input_from_seq=1,
                input_to_seq=1,
                superseded_by_inbound_seq=None,
                started_at=NOW,
                completed_at=None,
                created_at=NOW,
                updated_at=NOW,
            ),
            replayed=False,
            input_messages=(),
        )

    def commit_no_reply(self, turn_id, reason_code="intentional_no_reply", materialize_staged_command=None):
        self.no_reply_calls.append({"turn_id": turn_id, "reason_code": reason_code})
        return OutputDisposition(
            id="disposition_1",
            turn_id=turn_id,
            disposition="no_reply",
            reason_code=reason_code,
            created_at=NOW,
            updated_at=NOW,
        )


class FakeResolver:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = []

    def resolve(self, *, message, media):
        self.calls.append({"message": message, "media": tuple(media)})
        return self.result


class FakeRunner:
    def __init__(self):
        self.inbound_triggers = []

    def run_inbound_turn(self, trigger):
        self.inbound_triggers.append(trigger)
        return SimpleNamespace(
            turn_id="turn_1",
            disposition="replied",
            reason_code=None,
            visible_text="ok",
        )


class FakeRuntime:
    def __init__(self, service, resolver):
        self.conversation_runtime_service = service
        self.media_text_resolver = resolver
        self.turn_runner = FakeRunner()
        self.session = SimpleNamespace(commit=lambda: None)
        self.reply_pubsub = None


def event():
    return StreamEvent(
        event_id="outbox_1",
        topic="turn.inbound",
        payload={
            "conversation_id": "conversation_1",
            "message_id": "message_1",
            "trigger_id": "inbound:provider:1",
        },
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    )


def test_worker_resolves_media_before_building_inbound_trigger(monkeypatch):
    service = FakeConversationRuntimeService(message_text="")
    resolver = FakeResolver(
        MediaTextResolution(
            resolved_text="The image says buy milk.",
            media_status_updates=(
                InboundMediaStatusUpdate(
                    media_id="media_1",
                    processing_status="resolved",
                ),
            ),
            suppress_turn=False,
        )
    )
    runtime = FakeRuntime(service, resolver)
    monkeypatch.setattr(
        worker_main,
        "_message_row",
        lambda runtime, message_id: {
            "id": message_id,
            "channel_identity_id": "channel_identity_1",
            "text": service.message.text,
            "payload": {"provider": "wechat_personal"},
            "causal_inbound_event_id": "provider:1",
        },
    )
    monkeypatch.setattr(
        worker_main,
        "_conversation_row",
        lambda runtime, conversation_id: {"id": conversation_id, "account_id": "account_1"},
    )

    worker_main._handle_event(runtime, event())

    assert resolver.calls[0]["message"].text == ""
    assert service.resolution_calls == [
        {
            "message_id": "message_1",
            "resolved_text": "The image says buy milk.",
            "media_status_updates": (
                InboundMediaStatusUpdate(
                    media_id="media_1",
                    processing_status="resolved",
                ),
            ),
        }
    ]
    assert runtime.turn_runner.inbound_triggers[0].payload["text"] == "The image says buy milk."


def test_worker_records_media_failure_no_reply_without_invoking_runner(monkeypatch):
    service = FakeConversationRuntimeService(message_text="")
    resolver = FakeResolver(
        MediaTextResolution(
            resolved_text="",
            media_status_updates=(
                InboundMediaStatusUpdate(
                    media_id="media_1",
                    processing_status="failed",
                ),
            ),
            suppress_turn=True,
        )
    )
    runtime = FakeRuntime(service, resolver)

    worker_main._handle_event(runtime, event())

    assert service.resolution_calls == [
        {
            "message_id": "message_1",
            "resolved_text": "",
            "media_status_updates": (
                InboundMediaStatusUpdate(
                    media_id="media_1",
                    processing_status="failed",
                ),
            ),
        }
    ]
    assert service.started_turns == [
        {
            "conversation_id": "conversation_1",
            "trigger_id": "inbound:provider:1",
            "trigger_type": "InboundTurn",
            "mode": "interactive",
        }
    ]
    assert service.no_reply_calls == [
        {"turn_id": "turn_1", "reason_code": "media_resolution_failed"}
    ]
    assert runtime.turn_runner.inbound_triggers == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/coke/worker/test_media_resolution.py -v`

Expected: FAIL with `AssertionError: assert [] == [{'message_id': 'message_1', 'resolved_text': 'The image says buy milk.', 'media_status_updates': (InboundMediaStatusUpdate(media_id='media_1', processing_status='resolved'),)}]` because `_turn_triggers_from_event` currently calls `_inbound_trigger` without resolving media.

- [ ] **Step 3: Write minimal implementation**

Modify `coke/worker/__main__.py` with this complete replacement for `_turn_triggers_from_event` and this new helper block:

```python
def _turn_triggers_from_event(
    runtime: CokeRuntime, event: StreamEvent
) -> list[TurnTrigger]:
    topic = event.topic
    payload = dict(event.payload)
    if topic == "turn.inbound":
        trigger = _inbound_trigger_after_media_resolution(runtime, payload)
        return [trigger] if trigger is not None else []
    if topic in RENDER_TURN_TOPICS:
        return [
            _render_trigger(runtime, topic, render_payload)
            for render_payload in _render_payloads(runtime, topic, payload)
        ]
    raise RuntimeError(f"unsupported_worker_topic:{topic}")


def _inbound_trigger_after_media_resolution(
    runtime: CokeRuntime,
    payload: Mapping[str, Any],
) -> TurnTrigger | None:
    if _resolve_media_before_inbound_trigger(runtime, payload):
        return None
    return _inbound_trigger(runtime, payload)


def _resolve_media_before_inbound_trigger(
    runtime: CokeRuntime,
    payload: Mapping[str, Any],
) -> bool:
    resolver = getattr(runtime, "media_text_resolver", None)
    if resolver is None:
        return False
    message_id = _required_str(payload, "message_id")
    conversation_id = _required_str(payload, "conversation_id")
    trigger_id = _required_str(payload, "trigger_id")
    service = runtime.conversation_runtime_service
    message = service.get_message(message_id)
    if str(message.text or "").strip():
        return False
    media = service.inbound_media_for_message(message_id)
    if not media:
        return False
    resolution = resolver.resolve(message=message, media=media)
    if resolution.media_status_updates or resolution.resolved_text is not None:
        service.resolve_inbound_media(
            message_id,
            resolution.resolved_text,
            resolution.media_status_updates,
        )
    if not resolution.suppress_turn:
        return False
    start = service.start_turn(
        conversation_id=conversation_id,
        trigger_id=trigger_id,
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE.value,
    )
    service.commit_no_reply(
        turn_id=start.turn.id,
        reason_code="media_resolution_failed",
    )
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/coke/worker/test_media_resolution.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add coke/worker/__main__.py tests/unit/coke/worker/test_media_resolution.py
git commit -m $'feat: resolve media before inbound triggers\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'
```

### Task 7: WeChat Personal Ingestion Integration Coverage

**Files:**
- Modify: `tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py`
- Test: `tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py`

- [ ] **Step 1: Write the failing test**

Append this complete test block to `tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py`:

```python
def test_wechat_personal_image_media_resolves_into_current_input_text():
    harness = make_wechat_personal_harness()
    account_id = harness["account_id"]
    pending = harness["reachability"].start_wechat_personal_connection(account_id)
    harness["reachability"].poll_wechat_personal_login(account_id, pending.session_id)
    adapter = WeChatPersonalAdapter(now=lambda: datetime(2026, 6, 1, tzinfo=UTC))
    inbound_event = adapter.normalize_inbound(
        {
            "account_id": account_id,
            "session_id": pending.session_id,
            "message_id": "wx_msg_image_1",
            "wxid": "wxid_alice",
            "text": "",
            "context_token": "ctx-image-1",
            "media": [
                {
                    "media_type": "image",
                    "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                    "mime": "image/jpeg",
                    "agent_label": "image",
                }
            ],
        }
    )
    accepted = harness["reachability"].accept_provider_inbound(inbound_event)
    inbound = harness["conversation_runtime"].record_inbound(
        account_id=accepted.account_id,
        channel_identity_id=accepted.channel_identity_id,
        causal_inbound_event_id=accepted.raw_event_id,
        text=inbound_event.text,
        payload=dict(inbound_event.payload or {}),
        media=inbound_event.media,
        traceparent=TRACEPARENT,
    )
    harness["conversation_runtime"].resolve_inbound_media(
        message_id=inbound.message.id,
        resolved_text="The image says dinner at 7 PM.",
        media_status_updates=[
            InboundMediaStatusUpdate(
                media_id=inbound.media[0].id,
                processing_status="resolved",
            )
        ],
    )

    turn = harness["conversation_runtime"].start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:wx_msg_image_1",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    assert turn.input_messages[0].text == "The image says dinner at 7 PM."


def test_wechat_personal_native_voice_transcript_skips_media_resolution_path():
    harness = make_wechat_personal_harness()
    account_id = harness["account_id"]
    pending = harness["reachability"].start_wechat_personal_connection(account_id)
    harness["reachability"].poll_wechat_personal_login(account_id, pending.session_id)
    adapter = WeChatPersonalAdapter(now=lambda: datetime(2026, 6, 1, tzinfo=UTC))
    inbound_event = adapter.normalize_inbound(
        {
            "account_id": account_id,
            "session_id": pending.session_id,
            "message_id": "wx_msg_voice_1",
            "wxid": "wxid_alice",
            "text": "remind me at nine",
            "context_token": "ctx-voice-1",
            "media": [
                {
                    "media_type": "voice",
                    "storage_uri": "data:audio/wav;base64,UklGRg==",
                    "mime": "audio/wav",
                    "agent_label": "voice message",
                }
            ],
        }
    )
    accepted = harness["reachability"].accept_provider_inbound(inbound_event)
    inbound = harness["conversation_runtime"].record_inbound(
        account_id=accepted.account_id,
        channel_identity_id=accepted.channel_identity_id,
        causal_inbound_event_id=accepted.raw_event_id,
        text=inbound_event.text,
        payload=dict(inbound_event.payload or {}),
        media=inbound_event.media,
        traceparent=TRACEPARENT,
    )

    turn = harness["conversation_runtime"].start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:wx_msg_voice_1",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    assert turn.input_messages[0].text == "remind me at nine"
    assert inbound.media[0].processing_status == "preserved"
```

Update the imports in the same file:

```python
from coke.domains.conversation_runtime.models import (
    InboundMediaStatusUpdate,
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py::test_wechat_personal_image_media_resolves_into_current_input_text tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py::test_wechat_personal_native_voice_transcript_skips_media_resolution_path -v`

Expected: FAIL with `NameError: name 'InboundMediaStatusUpdate' is not defined` when run before the conversation-runtime write-back task exists.

- [ ] **Step 3: Write minimal implementation**

Confirm the imports and helper construction are exactly the code shown in Step 1. This task intentionally changes only tests because the behavior is provided by the production code added in Tasks 2-3; the test proves `normalize_inbound -> record_inbound(media=...) -> resolve_inbound_media -> start_turn` uses `CurrentInputMessage.text`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py::test_wechat_personal_image_media_resolves_into_current_input_text tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py::test_wechat_personal_native_voice_transcript_skips_media_resolution_path -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py
git commit -m $'test: cover wechat personal media ingestion flow\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'
```

### Task 8: Subset Eval Harness And Model-Selection Tracker

**Files:**
- Create: `scripts/eval-media-model-subset`
- Create: `tests/unit/coke/llm/test_media_model_subset_eval.py`
- Create: `docs/issues/2026-06-01-wechat-personal-media-model-selection.md`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/coke/llm/test_media_model_subset_eval.py` with this complete content:

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_media_subset_eval_requires_30_to_50_cases_per_manifest(tmp_path):
    asr_manifest = tmp_path / "asr.jsonl"
    vision_manifest = tmp_path / "vision.jsonl"
    write_jsonl(
        asr_manifest,
        [
            {
                "id": f"asr-{index:02d}",
                "storage_uri": "data:audio/wav;base64,UklGRg==",
                "expected_text": "remind me at nine",
            }
            for index in range(29)
        ],
    )
    write_jsonl(
        vision_manifest,
        [
            {
                "id": f"vision-{index:02d}",
                "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                "expected_text": "receipt total",
            }
            for index in range(30)
        ],
    )

    result = subprocess.run(
        [
            "scripts/eval-media-model-subset",
            "--asr-model",
            "sensevoice-candidate",
            "--vision-model",
            "qwen-vl-candidate",
            "--asr-manifest",
            str(asr_manifest),
            "--vision-manifest",
            str(vision_manifest),
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "asr manifest must contain 30-50 cases" in result.stderr


def test_media_subset_eval_accepts_config_driven_candidate_models(tmp_path):
    asr_manifest = tmp_path / "asr.jsonl"
    vision_manifest = tmp_path / "vision.jsonl"
    write_jsonl(
        asr_manifest,
        [
            {
                "id": f"asr-{index:02d}",
                "storage_uri": "data:audio/wav;base64,UklGRg==",
                "expected_text": "remind me at nine",
            }
            for index in range(30)
        ],
    )
    write_jsonl(
        vision_manifest,
        [
            {
                "id": f"vision-{index:02d}",
                "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                "expected_text": "receipt total",
            }
            for index in range(30)
        ],
    )

    result = subprocess.run(
        [
            "scripts/eval-media-model-subset",
            "--asr-model",
            "sensevoice-candidate",
            "--vision-model",
            "qwen-vl-candidate",
            "--asr-manifest",
            str(asr_manifest),
            "--vision-manifest",
            str(vision_manifest),
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "asr_model=sensevoice-candidate cases=30" in result.stdout
    assert "vision_model=qwen-vl-candidate cases=30" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/coke/llm/test_media_model_subset_eval.py -v`

Expected: FAIL with `FileNotFoundError: [Errno 2] No such file or directory: 'scripts/eval-media-model-subset'`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/eval-media-model-subset` with this complete executable Python script:

```python
#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asr-model", required=True)
    parser.add_argument("--vision-model", required=True)
    parser.add_argument("--asr-manifest", required=True)
    parser.add_argument("--vision-manifest", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    asr_cases = _load_manifest(Path(args.asr_manifest), label="asr")
    vision_cases = _load_manifest(Path(args.vision_manifest), label="vision")
    _validate_case_count(asr_cases, label="asr")
    _validate_case_count(vision_cases, label="vision")

    print(f"asr_model={args.asr_model} cases={len(asr_cases)}")
    print(f"vision_model={args.vision_model} cases={len(vision_cases)}")
    if args.dry_run:
        return 0
    print("Run this command with real representative media manifests and SiliconFlow_API_KEY set.")
    return 0


def _load_manifest(path: Path, *, label: str) -> list[dict]:
    rows: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise SystemExit(f"{label} manifest line {line_number} is not valid JSON: {error}") from error
        if not isinstance(row, dict):
            raise SystemExit(f"{label} manifest line {line_number} must be an object")
        for field in ("id", "storage_uri", "expected_text"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise SystemExit(f"{label} manifest line {line_number} missing {field}")
        rows.append(row)
    return rows


def _validate_case_count(rows: list[dict], *, label: str) -> None:
    if not 30 <= len(rows) <= 50:
        raise SystemExit(f"{label} manifest must contain 30-50 cases; got {len(rows)}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit as error:
        if isinstance(error.code, str):
            print(error.code, file=sys.stderr)
            raise SystemExit(2)
        raise
```

Make it executable:

```bash
chmod +x scripts/eval-media-model-subset
```

Create `docs/issues/2026-06-01-wechat-personal-media-model-selection.md` with this complete content:

```markdown
---
kind: progress_note
status: active
date: 2026-06-01
topic: wechat personal media model selection
surfaces:
  - coke/llm/media_text.py
  - scripts/eval-media-model-subset
---

# WeChat Personal Media Model Selection

## Requirement

Select SiliconFlow ASR and VLM model IDs through representative subset evaluation before production configuration.

## Candidate Families

- ASR: SenseVoice family only.
- VLM: Qwen-VL family only.

## Evidence Command

```bash
SiliconFlow_API_KEY=$SiliconFlow_API_KEY scripts/eval-media-model-subset \
  --asr-model sensevoice-candidate \
  --vision-model qwen-vl-candidate \
  --asr-manifest artifacts/evidence/wechat-personal-media/asr-subset.jsonl \
  --vision-manifest artifacts/evidence/wechat-personal-media/vision-subset.jsonl
```

## Current Status

The harness enforces 30-50 cases per manifest. The representative media corpus is not present in the repository on 2026-06-01, so model IDs must remain environment-configured and unset by default until captured media evidence is added under `artifacts/evidence/wechat-personal-media/`.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/coke/llm/test_media_model_subset_eval.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/eval-media-model-subset tests/unit/coke/llm/test_media_model_subset_eval.py docs/issues/2026-06-01-wechat-personal-media-model-selection.md
git commit -m $'chore: add media model subset eval harness\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'
```

### Task 9: Final Verification And Formatting

**Files:**
- Modify: files changed by Tasks 1-8
- Test: repository verification commands

- [ ] **Step 1: Run focused backend tests**

Run: `.venv/bin/python -m pytest tests/unit/coke/provider_edges/test_wechat_personal_connector.py tests/unit/coke/channel_reachability/test_provider_adapters.py tests/unit/coke/channel_reachability/test_provider_webhooks.py tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py tests/unit/coke/llm/test_media_text.py tests/unit/coke/llm/test_config.py tests/unit/coke/llm/test_media_model_subset_eval.py tests/unit/coke/worker/test_media_resolution.py tests/unit/coke/channel_reachability/test_wechat_personal_ilink_flow.py -v`

Expected: PASS with all selected tests passing.

- [ ] **Step 2: Run required backend unit suite**

Run: `.venv/bin/python -m pytest tests/unit/coke -v`

Expected: PASS with all unit tests passing.

- [ ] **Step 3: Format Python**

Run: `black . && isort .`

Expected: PASS with either `All done!` from Black or formatted file output, and isort exits 0.

- [ ] **Step 4: Run diff-aware verification routing**

Run: `zsh scripts/suggest-verification --base HEAD~1`

Expected: PASS with a surface suggestion that includes backend/runtime or repo-OS commands for the touched Python surfaces.

- [ ] **Step 5: Run risk trigger report**

Run: `zsh scripts/review-trigger --base HEAD~1`

Expected: PASS or non-blocking risk output. If it reports risk, record the exact risk in the handoff and continue to the final verification command.

- [ ] **Step 6: Run suggested surface verification**

Run: `zsh scripts/verify-surface backend`

Expected: PASS for the backend surface. If `suggest-verification` names a narrower or broader surface, run that exact suggested `zsh scripts/verify-surface <surface>` command and record it in the handoff.

- [ ] **Step 7: Commit final formatting or verification record changes**

```bash
git add coke tests scripts docs/issues provider_edges
git commit -m $'chore: verify wechat personal media ingestion\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'
```
