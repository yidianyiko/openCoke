# Inbound Multimodal Delivery

## Status

Spec in progress.

## Context

Outbound multimodal delivery now has an explicit `text` + `mediaUrls` +
`audioAsVoice` contract from Worker through Gateway. The inbound side is still
not a complete product path:

- Gateway `routeInboundMessage` already has an `attachments` concept and stores
  attachments on message metadata.
- Several channel adapters can extract attachments.
- The Python bridge `/bridge/inbound` normalizes inbound payloads down to text
  and drops `messages[-1].attachments`.
- The WhatsApp Evolution webhook path currently ignores non-text media.

This leaves bidirectional multimodal support incomplete.

## Goal

Make inbound media from supported Gateway adapters reach the ClawScale-backed
runtime as a normalized, durable attachment payload without regressing text-only
inbound behavior.

## Scope

- Define the Gateway-to-Bridge inbound attachment contract.
- Define shared Gateway and Bridge attachment normalization limits.
- Normalize inbound attachments in the bridge.
- Preserve attachments in `inputmessages.metadata`.
- Provide a text fallback visible to the existing Python worker prompt path
  without exposing raw `data:` URLs in prompts or logs.
- Add tests for Gateway routing and bridge enqueue behavior.

## Out Of Scope

- Native binary/object storage for inbound media.
- Downloading remote media in the bridge.
- Voice transcription.
- Direct Python model vision/audio invocation beyond existing prompt fallback.
- Native media support for every Gateway adapter.

## Security And Compatibility Notes

- `data:` URLs are accepted only for bounded trusted-adapter/Bridge paths, not
  the generic external Gateway route.
- Normalization must enforce attachment count, URL length, decoded `data:` byte
  limits, total payload limits, and allowed `data:` content types.
- Raw `data:` URLs must not be written into prompt fallback text, logs, or JS
  OpenAI/OpenClaw image payloads.
- Text-only inbound dedupe remains keyed by causal inbound event id and must not
  regress.

## References

- Outbound spec: `docs/superpowers/specs/2026-04-28-outbound-multimodal-delivery-design.md`
- OpenClaw pattern: inbound adapters normalize channel media into attachment
  payloads before the agent sees the message.
