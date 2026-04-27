# Task: Linq Shared Channel Adapter

## Goal

Add a Linq-backed gateway shared-channel adapter, matching the existing
`whatsapp_evolution` integration shape.

## Work Surfaces

- `gateway-api`
- `gateway-web`
- `deploy` (local `.env` only; production env propagation is out of scope)

## Design

- `docs/superpowers/specs/2026-04-28-linq-shared-channel-design.md`

## Success Criteria

- Admins can create and connect a `linq` shared channel.
- Linq `message.received` webhooks route into `routeInboundMessage()`.
- Immediate replies and proactive `/api/outbound` sends use Linq
  `POST /chats`.
- Linq secrets are stored server-side and hidden from admin API/UI responses.
- Focused gateway API and web tests cover the new adapter.
