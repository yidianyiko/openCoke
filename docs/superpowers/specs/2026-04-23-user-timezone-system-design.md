# User Timezone System (Design)

**Status:** draft for review
**Date:** 2026-04-23
**Surfaces:** `agent/agno_agent/workflows/prepare_workflow.py`,
`agent/agno_agent/tools/timezone_tools.py`, `agent/runner/context.py`,
`agent/agno_agent/tools/deferred_action`, `dao/user_dao.py`,
`gateway/packages/api`, `gateway/packages/web`, future Coke app clients
**References:** `docs/architecture.md`, `docs/roadmap.md`,
`docs/design-docs/coke-working-contract.md`,
`docs/superpowers/specs/2026-04-20-deferred-actions-apscheduler-design.md`,
`docs/superpowers/specs/2026-04-19-whatsapp-evolution-shared-channel-design.md`,
`tasks/2026-04-22-poke-competitive-analysis.md`, `util/time_util.py`,
`agent/agno_agent/workflows/prepare_workflow.py`,
`agent/agno_agent/tools/timezone_tools.py`,
`agent/agno_agent/tools/deferred_action/tool.py`

## Goal

Define Coke's product-level timezone system so every user has one canonical
timezone across channels and every time-dependent capability reads from the same
source of truth.

The design must work for today's WhatsApp Evolution entry path and also scale
to Coke's existing web surface and future app clients.

## Non-Goals

- No per-channel timezone setting.
- No separate per-conversation timezone state.
- No silent post-registration timezone flips from system signals.
- No timezone change history or audit log in v1.
- No requirement that a web settings page exists before the model is useful.
- No attempt to infer exact user timezone from signals the channel does not
  actually expose.

## Product Decisions

The user approved the following product rules during design:

- every user has one global timezone shared across all channels
- the timezone affects reminders, scheduled tasks, all time parsing, and
  time-aware reply context
- registration or first account creation may apply a default inferred timezone
  immediately without asking for confirmation
- user-explicit timezone changes are the highest-priority source
- if the user is actively changing timezone and the target is clear, apply the
  change directly without a second confirmation
- if the user's target timezone is ambiguous, ask a clarifying question instead
  of guessing
- after a user-explicit timezone is set, no system source may override it
- for any non-user signal that would change the current timezone after account
  creation, ask immediately before applying the change
- if the user does not reply to that confirmation, the proposal expires and the
  existing timezone remains in force
- if the user rejects that confirmation, keep the existing timezone
- system-inferred timezone should be disclosed when the user asks what timezone
  Coke is using
- when Coke only has an inferred timezone, the first strongly time-dependent
  interaction may mention which timezone Coke is using
- when a message includes its own explicit timezone or city, that affects only
  that parse or task and does not by itself rewrite the user's global timezone
- future reminders follow the user's current timezone unless the reminder
  explicitly pins a fixed timezone inside the task itself
- tasks with an explicit fixed timezone do not follow later user timezone
  changes
- for countries with multiple timezones, registration may still choose one
  configured country-default "main" timezone and apply it as an inferred
  default
- timezone change history should not be stored

## Current Constraints

### WhatsApp Evolution today

For WhatsApp Evolution users, Coke can reliably get:

- normalized WhatsApp identity / phone number
- message text and message metadata
- optional WhatsApp profile display name

It cannot reliably get from the native webhook:

- end-user device timezone
- end-user device locale
- end-user IP address
- exact device location

This means WhatsApp can provide a weak registration default via phone-region
inference, but it cannot be treated as a precise timezone source.

### Web and future app surfaces

Unlike WhatsApp, Coke web and future app clients can expose stronger timezone
signals such as:

- app-reported device timezone
- web IP or region inference
- future external account integrations that provide a declared timezone

The design therefore must support multiple system sources with different
strengths even if only part of that stack is available today.

## Approaches Considered

### Approach A: Manual-only timezone

Coke would never set a default timezone on its own and would only act after the
user explicitly changes it.

Pros:

- lowest risk of wrong default selection
- minimal product logic

Cons:

- poor first-run experience for reminders and time parsing
- too much friction for WhatsApp-first users
- does not benefit from web or app signals Coke will have later

Decision: reject.

### Approach B: Always-auto-sync timezone from the strongest system signal

Coke would keep overwriting the timezone whenever a stronger system source
appears.

Pros:

- highly automated
- can track travel without user involvement

Cons:

- easy to surprise users
- risky for reminders and local-time semantics
- conflicts with the requirement that user-confirmed timezone must win forever

Decision: reject.

### Approach C: Hybrid canonical timezone with gated updates

Coke sets a default inferred timezone at registration, allows the user to
change timezone directly when they clearly ask, and requires confirmation for
every later system-driven change.

Pros:

- good first-run behavior
- predictable reminder semantics
- scales to WhatsApp, web, and app surfaces
- preserves user control once the user explicitly sets timezone

Cons:

- requires explicit pending-confirmation handling
- more stateful than a pure manual-only model

Decision: recommended.

## Recommended Design

### 1. Canonical timezone model

Each user has exactly one account-level `effective_timezone`.

This value:

- is stored at the user-account layer, not at the channel or conversation layer
- is shared across WhatsApp, web, and future app surfaces
- must be an IANA timezone string
- is the default source of truth for all time-dependent behavior

The runtime also tracks:

- `timezone_source`
- `timezone_status`
- at most one `pending_timezone_change`

`timezone_status` has two product states:

- `user_confirmed`: timezone was set directly by the user or accepted by the
  user through a confirmation prompt
- `system_inferred`: timezone was applied by Coke from an available system
  source without explicit user confirmation

`pending_timezone_change` exists only to handle a proposed post-registration
change that still needs user approval. Coke does not retain a long-term history
of earlier timezone values.

### 2. Source priority

When Coke needs to choose among available system sources, the priority order is:

1. app device timezone
2. web IP or region inference
3. external account timezone from a connected profile or integration
4. WhatsApp phone-region inference
5. deployment default timezone fallback when no better signal exists

This priority governs which system source becomes the current inferred value at
registration and which later source is strong enough to propose a replacement.

For multi-timezone countries where Coke only knows country or region, the
product uses one configured country-default main timezone. This is an inferred
fallback, not a user-confirmed truth.

### 3. Registration and first-account default

At registration or first account creation, Coke should choose the best
available system source and immediately apply an inferred default timezone.

Examples:

- WhatsApp-only user: derive a country or region from the phone identity, map
  it to a default timezone, and apply it immediately
- logged-in web user: prefer web region inference over phone-region inference
- future app user: prefer the app-reported device timezone over weaker signals

This first applied value is:

- active immediately
- tagged as `system_inferred`
- allowed to power reminders, time parsing, and time-aware replies
- not treated as a locked user choice

### 4. User-explicit timezone changes

The model is responsible for deciding whether a user message is an explicit
global timezone change request.

The product contract is:

- if the user is clearly asking Coke to change the ongoing timezone and the
  target is clear, apply the change directly
- if the target is ambiguous, ask a clarifying question first
- if the user is merely describing travel, location, or task context, do not
  automatically treat that as a confirmed global timezone change

Examples:

- "change to Tokyo time" -> direct user-explicit change
- "from now on, talk to me in New York time" -> direct user-explicit change
- "change to CST" -> ambiguous, ask to clarify
- "I am in London now" -> model decides from context whether this is a global
  timezone change request or only a signal
- "I am in Paris this week on a trip" -> not a direct global timezone change

Once a user-explicit timezone is set, it becomes `user_confirmed` and all later
system sources lose the ability to overwrite it automatically.

### 5. System-driven change proposals after registration

After the account already has an `effective_timezone`, any non-user signal that
would change that timezone must go through immediate user confirmation before
it takes effect.

This includes:

- travel or location statements that are not treated as direct timezone-change
  commands
- app device timezone changes
- web region or IP changes
- external account timezone mismatches
- a stronger system source that disagrees with the current inferred timezone

Behavior:

- Coke asks immediately
- the old timezone remains active until the user confirms
- if the user confirms, the new timezone becomes `user_confirmed`
- if the user rejects, the old timezone remains active
- if the user does not reply, the proposal expires and no change is applied

If the user already has a `user_confirmed` timezone, Coke does not prompt about
system-source conflicts and does not auto-change the timezone.

### 6. Minimum chat-side timezone management

Even without a web settings page, the chat product must support:

- the user asking what timezone Coke is using
- the user changing timezone through a direct message

When the user asks for the current timezone:

- if the timezone is `user_confirmed`, answer with the current timezone
- if the timezone is `system_inferred`, answer with the current timezone and
  say that it is Coke's inferred timezone

This keeps the state inspectable without introducing a dedicated "lock" command
or a separate settings UI requirement.

### 7. Time parsing rules

All time parsing follows these rules:

- if the message explicitly contains a timezone or city for the specific task,
  parse that task in the mentioned timezone
- that task-local timezone does not rewrite the user's global
  `effective_timezone`
- if the message does not carry its own timezone, parse the time using the
  user's current `effective_timezone`
- relative expressions such as "in 3 hours", "tomorrow morning", or "tonight"
  are also interpreted from the current `effective_timezone`

This separates one-off task context from the user's long-lived timezone.

### 8. Reminder and scheduled-task semantics

Time-dependent tasks preserve local-time meaning by default.

Rules:

- reminders and scheduled tasks without an explicit fixed timezone follow the
  user's current `effective_timezone`
- if the user later changes timezone, future unexecuted tasks are reinterpreted
  using the new timezone
- reminders and tasks that explicitly pin their own timezone keep that pinned
  timezone and do not follow later user timezone changes

Examples:

- user creates "remind me tomorrow at 9am" in New York, later changes to Tokyo
  -> the reminder follows the user's new timezone semantics
- user creates "remind me at 9am London time" -> the reminder stays pinned to
  London even if the user's timezone later changes

### 9. Messages that combine timezone signal and time-dependent work

If one user message contains both:

- a new timezone signal that would require confirmation, and
- a reminder or time-dependent task

then Coke must resolve the timezone question first.

Behavior:

- ask the timezone confirmation immediately
- do not create the task under the proposed new timezone until the user answers
- if the user confirms, create the task under the new timezone
- if the user rejects, create the task under the old timezone
- if the user does not answer and the proposal expires, do not create the task
  from that message

This rule avoids silently scheduling work against a timezone the user has not
accepted.

If the same message contains a direct user-explicit timezone change with a clear
target, Coke may apply the timezone change immediately and then create the task
in the new timezone without a second confirmation.

### 10. Confirmation UX

Timezone confirmation should use short natural language and make the old and
proposed timezone explicit.

Example:

`It looks like you may be in London now. Change your timezone from Asia/Shanghai to Europe/London?`

Requirements:

- the question should accept short replies such as yes or no
- the confirmation should not block unrelated future conversation turns
- the same expired proposal should not keep repeating unless a new timezone
  signal appears later

### 11. Timezone visibility in time-dependent replies

If Coke is running on a `system_inferred` timezone and the user has not yet
explicitly confirmed a timezone, then the first strongly time-dependent
interaction may mention which timezone Coke is using.

Examples:

- first reminder creation
- first explicit "what time is it" style query
- first explicit local-date or local-time answer

Ordinary conversation should stay quiet about timezone unless it matters.

## Data and Interface Implications

This design requires account-level timezone state, not just a bare timezone
string.

At minimum the product contract needs:

- `effective_timezone`
- `timezone_source`
- `timezone_status`
- `pending_timezone_change` when a post-registration change is awaiting user
  confirmation

The runtime must expose this canonical state consistently to:

- prompt preparation and model context
- timezone update tools
- reminder parsing and scheduling
- proactive follow-up scheduling
- future web and app settings surfaces

The current repository already has account-level settings storage and
time-dependent runtime code. The implementation should extend those surfaces
rather than inventing parallel timezone state elsewhere.

## Error Handling and Edge Cases

- invalid or unresolvable timezone target -> do not change timezone; ask for a
  clearer city or IANA timezone
- ambiguous timezone abbreviation or ambiguous city -> do not guess
- no usable source at registration -> apply the deployment default timezone as
  an inferred fallback
- user-confirmed timezone exists and system sources disagree -> ignore the
  disagreement silently
- task contains its own explicit timezone -> use task-local timezone without
  modifying global timezone

## Testing Expectations

Implementation later should cover at least:

- registration default resolution by source priority
- multi-timezone-country fallback behavior
- explicit user timezone change with and without ambiguity
- post-registration system proposal confirmation flow
- rejection and expiry behavior
- reminder follow-on-change behavior for floating local-time tasks
- pinned-timezone task behavior
- cross-channel shared-account behavior
- user-visible "what timezone am I using" responses for inferred vs
  user-confirmed state

## Summary

Coke should use a single account-level timezone system with one canonical
`effective_timezone`, multiple ranked system sources, and a clear separation
between:

- inferred defaults that help the product work immediately, and
- user-confirmed timezone choices that permanently take priority

This gives Coke a usable WhatsApp-first default today while staying compatible
with stronger app and web signals later, without silently surprising users
after account creation.
