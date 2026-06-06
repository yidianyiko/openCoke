---
status: approved-for-autonomous-implementation
created_at: 2026-06-07
scope:
  - Track I: Render-history isolation for system turns
  - Track A: Trusted reminder-fire rendering
  - Track E: Availability privacy through isolated render facts
---

# Render Trusted Facts Design

## Context

Eva's reminder-fire and availability failures came from the same runtime
anti-pattern: render turns allowed recent chat history to compete with durable
facts. Reminder fires had only raw trigger payloads, so the Interaction Agent
borrowed a different title and time from recent chat. Availability facts were
already privacy-safe, but the Interaction Agent still had chat history that
contained a shared-activity label.

The 2026-06-07 design review sets two binding architecture decisions for this
work:

- D1: Keep the single user-facing producer. The Interaction Agent remains the
  only normal channel-visible prose producer. Typed helpers may supply facts or
  validation, but must not become independent user-visible renderers.
- D2: Isolate render history structurally at agent construction. Prompt wording
  alone already failed in production.

This design implements only Tracks I, A, and E. It does not implement waiting
delivery recovery, shared-reminder response enforcement, alias recovery,
notification lifecycle reconciliation, onboarding, default availability ranges,
lead-time semantics, or activity-based durations.

## Design Alternatives

### Recommended: render-specific agent construction plus trusted fact blocks

Construct the Agno agent with chat history disabled whenever
`request.mode == TurnMode.RENDER`. Keep inbound turns unchanged. Hydrate
`ReminderFireTurn` fire ids before invoking the Interaction Agent and expose
those facts through the existing `domain_result` prompt block. Availability tool
results keep flowing through tool facts, but the public fact shape is tightened
to include only window start/end/state and the queried friend's public display
name. A structural guard validates reminder-fire render output before delivery
and falls back to a safe minimal reply if the single producer output cannot be
reconciled with the trusted facts.

Trade-off: the fallback is runtime-owned fail-closed behavior after a single
producer failure. It is acceptable because it is a safety path, not a competing
normal prose producer.

### Rejected: stronger render prompts

Adding more instructions to ignore chat history would be cheap, but production
already had equivalent render instructions and still failed. This option leaves
the contaminating source in the context window and violates D2.

### Rejected: typed deterministic notification/reminder renderers

A deterministic renderer could guarantee exact reminder text, but it would add a
second user-facing prose producer and fragment persona ownership. This violates
D1 and the architecture invariant in `docs/ARCHITECTURE.md`.

## Architecture

### Render history policy

`AgnoInteractionAgent._build_agent()` will derive a history policy from the
`AgentRequest`:

- interactive inbound turns keep `add_history_to_context=True`
- render turns use `add_history_to_context=False`

The structural switch is made in agent construction, not in a prompt block.
Existing voice/persona settings, long-term memory settings, JSON protocol, and
tool exposure rules stay unchanged. Render tool profiles remain tool-less.

Render turns covered by this policy include `ReminderFireTurn`,
`NotificationTurn`, `UndeliveredResendTurn`, `AccessDeniedTurn`, and any future
render-mode availability turn represented as `TurnMode.RENDER`.

### Reminder-fire trusted fact hydration

`ReminderService` will expose a read-only method that hydrates fire ids into
trusted reminder-fire facts. The method reads the `ReminderFire` and `Reminder`
rows, verifies that each fire belongs to the render viewer, and computes a local
due time using the reminder's captured timezone.

Each fact includes:

- `fire_id`
- `reminder_id`
- `title`
- `owner_account_id`
- `viewer_account_id`
- `due_at`
- `local_due_at`
- `timezone`
- `duration_minutes`
- `kind`
- `shared_reminder_id`
- `participant_names`

The participant names are supplied through the existing
`ReminderService.friend_identifiers` callback, which already resolves names
visible to the viewer for shared-reminder calendar entries.

`TurnRunner` will hydrate these facts while assembling render context for
`ReminderFireTurn`. It will add a `domain_result` to trusted facts and context
with:

- `domain="reminder"`
- `intent="render reminder fire fact"`
- `action="ReminderFireTurn"`
- `intent_fulfilled=True`
- `reply_contract="render_reminder_fire"`
- `facts={"viewer_account_id", "fire_ids", "reminders"}`

The raw render payload remains present in the current-input block, but title,
time, participant, duration, and kind truth come from the trusted domain result.
No render-mode reminder lookup tool is added.

### Reminder-fire structural guard

After the Interaction Agent returns a valid JSON reply and before output is
recorded or delivered, `TurnRunner` will apply a reminder-fire render guard when
the request carries `reply_contract="render_reminder_fire"`.

The guard validates structure, not free-prose contradictions:

- trusted reminder facts are present
- each fact has subject ids, title, due time, local due time, timezone, duration,
  and kind
- `due_at - current_time` is computable
- no segment contains serialized tool-call markup
- when the reply includes normalized fact-bearing tokens for title, local time,
  or remaining minutes, those tokens match trusted tokens

To avoid a free-prose contradiction parser, the guard looks for exact trusted
tokens and exact known-bad alternatives already available in structured test
fixtures. It does not try to understand arbitrary natural language. If the
single producer output omits all trusted title/time tokens, uses a wrong token
from the render context, emits serialized tool markup, or returns no reply, the
guard fails closed.

Fail-closed behavior is:

1. retry once through the existing protocol-retry path with structural guidance;
2. if the retry still fails the guard, replace the output with a minimal safe
   reminder-fire reply assembled from trusted facts.

The fallback is deliberately small and factual. It exists only after a failed
single-producer render attempt and preserves delivery correctness over persona
richness for this safety path.

### Availability privacy fact block

Availability data remains owned by SocialScheduling. The domain already strips
detail ids while building busy/free windows. This change tightens the adapter
fact shape to expose:

- `friend_account_id`
- `friend_display_name`
- `windows[].start`
- `windows[].end`
- `windows[].state`

No titles, locations, prompts, detail ids, participant names, or private
metadata are exposed. The display name is resolved from the already-visible
friend list in the service result. The Interaction Agent continues to render
availability replies from tool facts during an interactive turn. If availability
is rendered by a future system render turn, the render history policy prevents
chat history from becoming an alternate fact source.

This work intentionally does not add a default date range. Current behavior
continues to require explicit `local_start` and `local_end` unless the product
requirements baseline changes first.

## Data Flow

### Reminder fire

1. Scheduler/outbox emits a `ReminderFireTurn` with `fire_ids`.
2. `TurnRunner` starts a render turn and builds gate facts.
3. `ReminderService.reminder_fire_render_facts()` hydrates the fire ids.
4. `TurnRunner` injects the reminder-fire `domain_result`.
5. `AgnoInteractionAgent` constructs the render agent with
   `add_history_to_context=False`.
6. The Interaction Agent renders a JSON reply from trusted blocks.
7. `TurnRunner` validates reminder-fire structure and fact tokens.
8. Valid output is recorded and delivered. Invalid output retries once, then
   falls back to a minimal trusted-fact reply.

### Availability

1. Interactive user asks for friend availability with an explicit range.
2. The Interaction Agent calls `social_scheduling_tool.query_availability`.
3. SocialScheduling returns `FriendAvailability` windows.
4. The tool adapter serializes only public friend display name and window
   start/end/state.
5. The Interaction Agent replies from the tool facts. No render history
   isolation is needed for this interactive tool turn, but any future
   render-mode availability turn inherits the render history policy.

## Error Handling

- Missing or unauthorized reminder fire facts make the render turn fail closed
  with a structured reason before any outbound message is recorded.
- Invalid model protocol continues to use the existing one-retry behavior.
- Reminder-fire `no_reply`, serialized tool-call markup, wrong title tokens,
  wrong local-time tokens, and non-computable due/current time fail the
  reminder-fire guard.
- A failed reminder-fire guard retry falls back to a minimal trusted-fact reply.
- Availability fact serialization drops any non-public fields instead of trying
  to redact generated prose.

## Testing

Tests will be added before implementation under the existing unit surfaces:

- `tests/unit/coke/llm/test_interaction_agent.py`
  - interactive construction keeps history enabled
  - render construction disables history
  - reminder-fire prompt includes trusted domain result with title and local due
    time
  - availability tool facts expose public display name and busy/free windows only
- `tests/unit/coke/turn/test_turn_runner.py`
  - `ReminderFireTurn` hydrates `fire_ids` into trusted facts
  - recent chat with a different title/time cannot override trusted facts
  - wrong title, wrong local time, serialized tool markup, and `no_reply` fail
    closed for reminder-fire render turns
- `tests/unit/coke/social_scheduling/test_social_scheduling_service.py` or
  existing adapter tests
  - availability facts contain only public fields

Verification will run the touched unit tests first, then the repository routing
commands:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn tests/unit/coke/llm tests/unit/coke/social_scheduling tests/unit/coke/test_social_scheduling_tool_adapter.py -v
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

The suggested surface from `scripts/suggest-verification` will be run before
handoff.

## Out Of Scope

- no typed deterministic user-visible renderers
- no prompt-only history isolation
- no render-mode business lookup tools
- no free-prose contradiction or privacy parser
- no default availability range
- no changes to shared-reminder approval wording enforcement
- no notification recipient lifecycle reconciliation
- no production deployment

## Spec Self-Review

- Placeholder scan: no placeholders remain.
- Consistency check: the design keeps D1's single user-facing producer for normal
  output and uses fallback only as a fail-closed safety path after invalid render
  output.
- Scope check: the work is limited to Tracks I, A, and E.
- Ambiguity check: availability default-range behavior is explicitly unchanged.
