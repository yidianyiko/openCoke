# Product Feature Tree

This file is the canonical product, route, and API surface index for the Coke
clean rebuild. Product requirements are defined in
`docs/product-requirements/current.md`.
Runtime ownership is defined in `docs/ARCHITECTURE.md`.

## Product Modules

- IdentityAccess: account identity, access gate, activation, credentials,
  sessions, channel identity, and claim/auth artifacts.
- ChannelReachability: one reachable personal channel, connection state,
  delivery route, and delivery attempts.
- ConversationRuntime: conversations, messages, inbound media references, turns,
  output disposition, waiting/async reply, and stale-reply safety.
- Reminder: personal reminders, proactive follow-ups, recurrence, due fires,
  nightly summaries, undelivered reminders, and reminder calendar read models.
- SocialScheduling: friend links, public active/reachable friend-link
  resolution, authenticated friendship creation, availability queries, shared
  reminders, shared reminder rescheduling, projections, and product
  notifications.
- CalendarImport: Google authorization, import runs, per-occurrence import
  items, and imported Coke reminders.

## Public Web

- `/`
- `/faqs`
- `/demos`
- `/privacy`
- `/terms`
- `/u/:code`

## Customer Web

- `/account/*`
- `/channels`
- `/reminders`
- `/friends`
- `/shared-reminders`
- `/settings`
- `/calendar-import`
- `/subscription`
- `/claim`

## Python Public API

- `/api/public/user-links/:code`
- `/api/auth/*`
  - `/api/auth/email-verification/resend`
- `/api/account/*`
- `/api/channels/*`
- `/api/reminders/*`
- `/api/friends/*`
- `/api/shared-reminders/*`
- `/api/settings/*`
- `/api/calendar-import/*`
- `/api/subscription/*`
- `/api/claim/*`
  - `/api/claim/email`

The public user-link route resolves active reachable friend links for the
public `/u/:code` web landing. Authenticated friendship creation remains
`/api/friends/join`; successful join responses include the friendship status,
friendship id, and counterpart account/display identity needed for immediate
user feedback.

## Provider Webhooks

- `/webhooks/whatsapp/evolution`
- `/webhooks/wechat/personal`
- `/webhooks/wechat/ecloud`
- `/webhooks/linq`

## Internal Runtime

- `/internal/outbound/delivery-callback`
- `/internal/reply-wait/:causal_inbound_event_id`

## Superseded Discovery Surfaces

Route ownership must not be inferred from deleted legacy Gateway or bridge
surfaces. The clean rebuild's discoverable route contract is the Python API and
webhook list above.
