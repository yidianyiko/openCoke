# Product Feature Tree

This file is the canonical product, route, and API surface index for the Coke
clean rebuild. Product requirements are defined in
`docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`.
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
- SocialScheduling: friend links, friendships, availability queries, shared
  reminders, projections, and product notifications.
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

- `/api/auth/*`
- `/api/account/*`
- `/api/channels/*`
- `/api/reminders/*`
- `/api/friends/*`
- `/api/shared-reminders/*`
- `/api/settings/*`
- `/api/calendar-import/*`
- `/api/subscription/*`
- `/api/claim/*`

## Provider Webhooks

- `/webhooks/whatsapp/evolution`
- `/webhooks/wechat/personal`
- `/webhooks/wechat/ecloud`
- `/webhooks/linq`

## Internal Runtime

- `/internal/outbound/delivery-callback`
- `/internal/reply-wait/:causal_inbound_event_id`

## User Journeys

### Account And Access

- Register, log in, verify email, reset password, maintain session, view account
  access status, and recover from denied access.
- Claim a messaging-first account through a one-time login URL or web-initiated
  claim code.
- Bind a web-first channel through a pairing code.
- Block normal assistant processing, channel connection, and calendar import
  when account access is denied.

### First Activation

- Web-first activation requires login/registration, one usable personal channel,
  and one received personal-channel message.
- Shared WhatsApp messaging-first activation requires trusted sender binding,
  a usable messaging channel, and one received inbound message.
- Creating the first reminder or completing settings is not an activation
  requirement.

### Channel Reachability

- View, connect, retry, remove where allowed, and recover a single personal
  channel.
- Current product channels are personal WeChat and shared WhatsApp.
- Shared WhatsApp is the only messaging-first auto-provisioning path.
- A messaging-first user cannot remove the only sender identity that anchors the
  account.

### Daily Conversation

- Receive text and channel-carried media as processable inbound input.
- Bind every inbound to a trusted account before assistant processing.
- Run an InboundTurn through The Turn.
- Send text replies, intentional no-reply, waiting text for slow processing, and
  asynchronous final replies when needed.
- Preserve observable failure when processing or output validation fails.

### Personal Reminders

- Create, view, edit, complete, delete, schedule, unschedule, and manage
  reminders through conversation and the calendar page.
- Support one-time, no-trigger-time, recurring, proactive, and shared-projection
  reminders.
- Use one global user timezone for interpretation and display; recurring windows
  remain pinned to the timezone captured at creation or last edit.
- Merge same-owner same-time due reminders into one rendered ReminderFireTurn.
- Retain undelivered reminder status and resend after reconnect when applicable.
- Discard failed proactive follow-ups.

### Friendship

- Generate, reset, disable, and share friend links and QR codes.
- Establish active friendship directly after the joiner authenticates or claims
  an account and has a usable personal channel.
- Establish friendship through a friend-link code in conversation.
- View and remove friends.
- No friend request approval flow is part of the current product.

### Shared Reminders

- Create one group shared reminder for one or more active friends.
- Query privacy-safe friend availability.
- Validate required fields, unique active friends, receiver conflicts, and
  participant reachability before creation.
- Create participant projections immediately after validation.
- View participant-scoped shared reminders.
- Cancel the whole group by any participant.
- No shared-reminder accept/reject flow is part of the current product.

### Product Notifications

- Send informational notifications for friendship creation, shared-reminder
  creation/cancellation, and related errors or partial failures.
- Store structured facts and per-recipient state; final visible text is rendered
  through The Turn.
- Notifications never approve, reject, or execute product actions.

### Calendar Import

- Authorize Google Calendar for one-time import.
- Convert future events into Coke-owned reminders.
- Deduplicate by occurrence grain.
- Report imported, skipped, downgraded, and failed items.
- Stop/revoke future authorization without deleting imported reminders.

### Settings And Data Lifecycle

- View/update/reset assistant settings, user profile fields, global timezone,
  proactive switch, and memory switch.
- Remove removable channels, delete/complete reminders, cancel shared reminders,
  remove friends, turn off memory usage, and stop calendar authorization.
- Full account deletion, full export, full erasure, and self-service memory
  clearing are out of scope.

## Superseded Discovery Surfaces

Future-route ownership must not be inferred from `gateway/packages/api` or
`connector/clawscale_bridge`. Those directories describe legacy implementation
surfaces until deleted or rewritten. The clean rebuild's discoverable route
contract is the Python API and webhook list above.
