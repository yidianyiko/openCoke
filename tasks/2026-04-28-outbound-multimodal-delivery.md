# Task: Outbound Multimodal Delivery

- Status: Draft
- Owner: Codex
- Date: 2026-04-28

## Goal

Make ClawScale outbound delivery handle Coke-generated image and voice outputs
through an explicit media payload contract instead of silently depending on a
text-only gateway route.

## Scope

- In scope:
  - Normalize Coke `image` and `voice` output messages into gateway outbound
    payload media fields.
  - Preserve text outbound behavior and idempotency semantics.
  - Add gateway delivery behavior for media-capable and text-only channels.
  - Add focused worker/bridge/gateway tests.
- Out of scope:
  - Changing Coke prompt behavior that decides when to emit photos or voice.
  - Adding a new durable media store.
  - Replacing ClawScale delivery route resolution.
  - Proving a native WeChat media-send API beyond the adapter contract already
    present in this repository.

## Touched Surfaces

- worker-runtime
- bridge
- gateway-api

## Acceptance Criteria

- Bridge sends `mediaUrls` for output messages whose `metadata.url` points to
  generated image or voice assets.
- Bridge marks voice outputs with `audioAsVoice: true`.
- Gateway `/api/outbound` accepts text-only, media-only, and text-with-media
  payloads.
- Gateway idempotency comparison includes the media fields.
- Gateway delivery passes a structured payload to channel delivery logic.
- Text-only channels deliver media as visible attachment links instead of
  silently dropping media.
- Media URLs must be absolute HTTP(S) URLs; local paths, relative paths,
  `file://`, and data URLs fail validation.
- Unsupported or malformed media payloads fail with explicit errors.

## Verification

- Command: `pytest tests/unit/connector/clawscale_bridge/ -v`
- Expected evidence: bridge outbound client and dispatcher tests pass.
- Command: `pnpm --dir gateway/packages/api test -- src/routes/outbound.test.ts src/lib/outbound-delivery.test.ts`
- Expected evidence: focused gateway outbound tests pass.

## Notes

This task follows the OpenClaw pattern observed in `/data/projects/openclaw`:
agent/channel output is represented as text plus optional media URLs, and each
channel adapter decides whether to send media natively or degrade to visible
attachment links.
