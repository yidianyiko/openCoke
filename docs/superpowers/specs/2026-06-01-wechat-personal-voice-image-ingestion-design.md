---
kind: design_spec
status: draft
date: 2026-06-01
topic: wechat-personal voice and image ingestion
surfaces:
  - provider_edges/wechat_personal_connector/app.py
  - coke/providers/wechat_personal.py
  - coke/api/provider_webhooks.py
  - coke/domains/channel_reachability/models.py
  - coke/domains/conversation_runtime
  - coke/worker/__main__.py
  - coke/turn/runner.py
  - coke/llm
---

# WeChat Personal (iLink) Voice and Image Ingestion — Design

## Problem

Coke's downstream turn pipeline is text-only. For the `wechat_personal`
channel, image messages never reach the agent at all, and voice depends
entirely on WeChat's native transcript with no fallback.

We want voice and image on `wechat_personal` to reach the existing text
pipeline (semantic interpreter + Agno interaction agent + reminder /
social-scheduling domains) as if the user had typed equivalent text, **without
making the turn runner multimodal**.

This spec covers `wechat_personal` only.

## Current state (verified against `main`)

This is a **partially-built** feature, not a greenfield one. The relevant
scaffolding already exists; the gaps are specific.

- The iLink connector is **in-repo**:
  `provider_edges/wechat_personal_connector/app.py`. Its `_extract_text`
  already reads message item `type: 1` (text) **and `type: 3` voice transcript
  (`voice_item.text`)**, and posts a text-only JSON
  (`account_id, session_id, message_id, wxid, text, context_token`) to
  `POST /webhooks/wechat/personal`. It does **not** handle image (`type: 2`)
  and does **not** forward any media bytes.
- `coke/domains/conversation_runtime/models.py` already defines an inbound
  media model: `InboundMedia(id, message_id, media_type, storage_uri,
  processing_status, agent_reference, ...)` and the input DTO
  `InboundMediaInput(media_type, storage_uri, agent_label)`.
- `ConversationRuntimeService.record_inbound(..., media: Sequence[
  InboundMediaInput] | None = None)` already stores media rows, hard-coding
  `processing_status="preserved"` and `agent_reference={type, label}`
  (service.py:96–111), via
  `repository.add_inbound_message_with_media_and_outbox`.

What is **missing**:

1. The connector does not extract image messages or forward media.
2. `WeChatPersonalAdapter.normalize_inbound` (and `NormalizedInbound`) do not
   carry media; `provider_webhooks._handle_inbound` calls `record_inbound`
   without media.
3. Nothing advances `processing_status` past `"preserved"` — there is no
   resolver and no repository method to update a recorded inbound's text or
   media status.
4. The agent does not consume `agent_reference`; inbound text reaches the agent
   only through `Message.text` → `CurrentInputMessage.text` and the worker
   trigger payload.

The design below fills exactly these gaps and reuses the existing media model.
It does **not** add a parallel media type.

## Findings (iLink protocol)

The iLink WeChat-personal protocol is community-reverse-engineered, not
vendor-documented; treat as an assumption to validate against the live
connector.

- **Voice** — item `type: 3`, SILK-encoded, with WeChat's own transcription
  attached (already surfaced by the connector as `voice_item.text`). Raw audio
  is CDN-stored, AES-128-ECB encrypted, needs `aes_key`.
- **Image** — item `type: 2`, CDN-stored, AES-128-ECB encrypted, needs
  `aes_key`.
- Neither is base64 or plain-URL at the raw layer.

Consequences:

1. WeChat's native voice transcript means **ASR is usually unnecessary** — the
   common voice path already works end-to-end today. A self-hosted ASR model
   is only a fallback for when `voice_item.text` is empty.
2. CDN download + AES-128-ECB decrypt (+ SILK→WAV for voice) is **connector
   work** — the connector already holds the WeChat session, `base_url`, token,
   and `aes_key`. Coke does not implement CDN/AES/SILK.

Sources: reverse-engineered iLink protocol notes
(`hao-ji-xing/openclaw-weixin`, `zongrongjin/weixin-ilink`); the latter's
Python SDK converts inbound voice SILK→WAV.

## Goals

- Image messages on `wechat_personal` produce inbound text that flows through
  the unchanged downstream text pipeline.
- Voice keeps WeChat's native transcript as the primary path; self-hosted ASR
  is a fallback only when the native transcript is empty.
- Image is converted to text by a vision-language model (VLM); the VLM output
  subsumes OCR (no separate OCR branch).
- The HTTP webhook stays fast (202). Media→text transcoding never runs in the
  webhook request path.
- Reuse the existing `InboundMedia` / `processing_status` scaffolding.
- All model usage stays within the SiliconFlow Chinese-model catalog.

## Non-goals

- No multimodal turn runner or semantic interpreter. They stay text-only.
- No CDN download, AES decryption, or SILK decoding inside Coke (connector
  responsibility).
- No clarification / follow-up prompt on transcoding failure (best-effort).
- No separate OCR pipeline; no new parallel media model.
- No model lock-in; concrete model IDs chosen later by subset eval.
- Other channels (`whatsapp_evolution`, `wechat_ecloud`, `linq`) — out of scope.

## Design

### Principle: media → text before the turn

The downstream contract for *inbound user text* is `Message.text` →
`CurrentInputMessage.text` and the worker trigger payload `text`. (`visible_text`
in `runner.py` is the **outbound reply**, not inbound input — this spec never
uses `visible_text` for inbound.) Multimodality is contained in an ingestion
preprocessing stage that produces inbound text; nothing in the runner or
interpreter changes.

### Connector → Coke contract (prerequisite surface)

`provider_edges/wechat_personal_connector` is a real surface this feature must
extend. It performs CDN download, AES-128-ECB decrypt, and SILK→WAV.

For **voice** the connector posts (as today) `text` = WeChat's native
transcript when present, plus, when bytes are available, a media reference:

- `media`: `[{ "media_type": "voice", "storage_uri": "<ref>",
  "mime": "audio/wav", "agent_label": "voice message" }]`

For **image** the connector posts `text` empty and:

- `media`: `[{ "media_type": "image", "storage_uri": "<ref>",
  "mime": "image/jpeg", "agent_label": "image" }]`

`storage_uri` is a reference Coke can read to obtain the decoded bytes. The
connector MAY deliver bytes inline as a `data:` URI (base64) or upload to
shared object storage and pass an `https`/`s3` URI; this spec treats the bytes
as available at `storage_uri` and does not require a particular scheme. The
inline-base64 form is acceptable for the first iteration.

If the connector cannot deliver readable media (only a CDN ref + `aes_key`),
that is a contract violation for this iteration; Coke treats it as an
unresolvable media message (see Failure handling). Coke does not implement the
CDN/AES/SILK fallback.

### NormalizedInbound: carry media input

`WeChatPersonalAdapter.normalize_inbound` parses the connector `media` array
into the existing `InboundMediaInput` shape and attaches it to
`NormalizedInbound`. Add one field to `NormalizedInbound`
(`coke/domains/channel_reachability/models.py`):

```
media: tuple[InboundMediaInput-equivalent, ...] = ()
```

(Field carries `media_type`, `storage_uri`, `mime`, `agent_label`. Reuse the
conversation-runtime `InboundMediaInput` shape rather than defining a second
media type; if a channel-reachability-local mirror is needed for layering, it
maps 1:1.) `normalize_inbound` stays a **pure parse** — no transcoding, no
storage I/O.

`provider_webhooks._handle_inbound` passes `inbound_event.media` straight into
`record_inbound(..., media=...)`. The webhook still returns 202 immediately;
recorded media rows start at `processing_status="preserved"` exactly as today.

### Media-resolution stage (worker, before trigger build)

Placement is dictated by two verified facts:

- The webhook enqueues `turn.inbound` and returns 202; the turn runs in the
  async worker. ASR/VLM latency must live here, not in the webhook.
- `_inbound_trigger` (`coke/worker/__main__.py`) reads the message row **fresh**
  and copies `message.text` into `TurnTrigger.payload["text"]`, which the
  runner's semantic layer then consumes (`runner.py` semantic interpretation /
  follow-up heuristics). Therefore resolution must complete **before**
  `_inbound_trigger` builds the trigger, so both the DB message text and the
  trigger payload carry the resolved text. Updating the DB after trigger build
  would desync the agent input from the semantic layer.

Stage: a resolver runs at the start of inbound-event handling in the worker,
before `_inbound_trigger`. Per inbound:

1. If `Message.text` is already non-empty → **skip** (text message, or voice
   with a usable native transcript). No model call. Common path. Any media rows
   are left `preserved`.
2. Else if a `voice` media row is present → call the SiliconFlow ASR client on
   the bytes at `storage_uri`; on success, set the resolved transcript as the
   message text and advance that media row to `processing_status="resolved"`.
3. Else if an `image` media row is present → call the SiliconFlow VLM client on
   the bytes at `storage_uri`; on success, set the VLM's contextual text
   (description + extracted in-image text) as the message text and advance the
   row to `"resolved"`.
4. On model failure / empty output / contract violation → advance the row to
   `processing_status="failed"` and leave the message text empty (see Failure
   handling).

This requires a **new conversation-runtime method** (no such method exists
today), e.g.
`resolve_inbound_media(message_id, resolved_text, media_status_updates)`,
backed by a repository update that sets `Message.text` and the relevant
`InboundMedia.processing_status` atomically. `start_turn` and `_inbound_trigger`
must observe the resolved text.

### Voice path

- Primary: WeChat native transcript (arrives as `message.text`; resolver
  step 1 skips all model calls). Already works today.
- Fallback: SiliconFlow ASR (SenseVoice family) on the connector-provided WAV,
  only when the native transcript is empty.
- The transcript is treated as the user's text verbatim; no extra framing.

### Image path

- SiliconFlow VLM (Qwen-VL family) converts the image to contextual text that
  includes any in-image text. This subsumes OCR.
- The description is treated as the user's text for the turn.

### Failure handling — best-effort, no follow-up, no empty turn

Per product decision, transcoding is best-effort and never asks the user to
retry. But an empty-text inbound must not run a degenerate turn: today an empty
inbound is still an `InboundTurn`, and `_turn_source_for_trigger`
(`runner.py`) tells the agent this is a real user message to reply to — which
would make the agent reply to nothing.

Therefore, when resolution yields empty text (model failure, empty output, or
contract violation):

- The media row is marked `processing_status="failed"`.
- The inbound produces **no agent turn**: the resolver suppresses trigger
  creation for this inbound (or records a `no_reply` disposition for it).
- Coke injects **no** clarification ("please type it") turn.

The exact suppression mechanism (skip `_inbound_trigger` for the inbound vs.
emit a `no_reply` disposition) is a plan-level decision, but the spec requires:
empty resolution ⇒ no agent reply, no clarification, recorded `failed` status.

### Model surface and selection

New ports in `coke/llm`, named explicitly (none exist today —
`coke/llm/config.py` exposes only interaction/interpreter/detector text
models):

- `AsrClient` — voice bytes → transcript.
- `VisionTextClient` — image bytes → contextual text.
- `MediaTextResolver` — orchestrates the per-inbound algorithm above over the
  two clients.

Both clients target the SiliconFlow catalog (ASR: SenseVoice family; VLM:
Qwen-VL family). Whether they reuse `SiliconFlowLLMConfig` or get separate
model/env config is settled in the plan; either way concrete model IDs are
**not** locked here — they are chosen by a 30–50 case representative subset
eval (one for ASR, one for VLM), per the subset-eval convention.

## Integration points (named, verified)

- `provider_edges/wechat_personal_connector/app.py` — extend `_extract_text` /
  payload build for image (`type: 2`) and media forwarding. **Prerequisite.**
- `coke/providers/wechat_personal.py` — `normalize_inbound` parses `media`.
- `coke/domains/channel_reachability/models.py` — `NormalizedInbound.media`.
- `coke/api/provider_webhooks.py` — `_handle_inbound` passes `media` to
  `record_inbound`; unchanged 202.
- `coke/domains/conversation_runtime/{service,repository}.py` — new
  `resolve_inbound_media` (text + `processing_status` write-back). Reuses
  existing `InboundMedia` / `add_inbound_message_with_media_and_outbox`.
- `coke/worker/__main__.py` — resolver stage before `_inbound_trigger`.
- `coke/llm` — `AsrClient`, `VisionTextClient`, `MediaTextResolver`.

## Open questions / risks

1. **Connector capability (top risk)** — does the live iLink connector actually
   deliver readable decoded media (CDN-decrypted, SILK→WAV)? The whole feature
   is gated on this prerequisite. The connector currently forwards text only.
2. **Native transcript quality** — ASR fallback triggers only on *empty* native
   text, not *low-quality* text. Quality-based fallback is out of scope.
3. **Storage scheme for `storage_uri`** — inline `data:` base64 vs object
   storage. First iteration may use inline base64; revisit if payload size
   becomes a problem.
4. **Suppression seam** — skip-trigger vs `no_reply` disposition for empty
   resolution; settle in the plan against the actual `_inbound_trigger` /
   runner ordering.
5. **Latency / cost** — image VLM adds per-message latency and SiliconFlow
   cost; acceptable because it is off the webhook path and gated behind
   "no native text".

## Verification

- Unit: connector extracts image (`type: 2`) and emits the `media` array;
  rejects malformed items.
- Unit: `wechat_personal.normalize_inbound` parses `media` into the inbound
  media shape; rejects malformed media (mirrors existing
  `test_provider_adapters.py` malformed-field coverage).
- Unit: resolver skips the model when `Message.text` is non-empty; calls ASR
  for voice-with-empty-text; calls VLM for image; on failure marks media
  `failed`, produces no agent turn, injects no clarification.
- Unit: `resolve_inbound_media` updates `Message.text` and
  `InboundMedia.processing_status`; resolved text is visible to `start_turn`
  and to `_inbound_trigger`'s `payload["text"]`.
- Integration: extend `test_wechat_personal_ilink_flow.py` — a voice inbound
  (native transcript) and an image inbound (VLM text) each produce a turn whose
  inbound `CurrentInputMessage.text` is the resolved text; an unresolvable
  media inbound produces no agent reply.
- Eval: 30–50 case subset each for ASR and VLM model choice (SiliconFlow
  catalog only).
- Routing: `zsh scripts/suggest-verification --base HEAD~1` and
  `zsh scripts/review-trigger --base HEAD~1` before commit.
