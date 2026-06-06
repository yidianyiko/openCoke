---
title: Response contract and recoverable scheduling intent
date: 2026-06-07
status: approved
kind: design
topic: response-contract-recovery
---

# Response contract and recoverable scheduling intent

## Problem

Track C and Track D in `docs/issues/2026-06-06-eva-chat-rca.md` share one
root cause: the turn runtime lets product truth leak through prose, history, or
pre-close previews instead of carrying typed trusted facts to the single
Interaction Agent and validating the final structured output against those
facts.

For shared reminders, state-changing social-scheduling tools stage commands.
The close boundary materializes those commands, but the reply contract currently
does not carry a canonical social-scheduling outcome. A final reply can imply
success from a staged preview, a tool-call attempt, or generic successful
wording even when no shared reminder became active.

For friend correction recovery, a blocked request such as "help me schedule
with zihao" can close before the user sends "zihao is olivers". The existing
turn-local clarification recovery reconstructs intent from recent assistant
questions and has deterministic regex-like helper behavior in the interaction
agent. That is not durable across workers and violates the design review rule:
classify the correction through the semantic interpreter, then carry a typed
trusted fact rather than re-parsing history.

## Goals

- Preserve the single user-facing producer: the Interaction Agent remains the
  only normal producer of channel-visible prose.
- Add a canonical `SocialSchedulingOutcome` contract for shared-reminder create
  results and validate final structured claims against it.
- Treat `staged_pending_close` as an internal status that is never a
  user-visible success claim.
- Create a narrow durable `recoverable_scheduling_intent` only when a fresh
  close blocks `shared_reminder_create` on an unmatched or ambiguous friend.
- Recover a later friend correction only when the semantic interpreter emits a
  typed follow-up action, an open unexpired artifact matches, and exactly one
  active friend resolves.
- Keep correction aliases turn-local. Do not persist global alias memory.
- Keep close-boundary freshness as the final authority. A superseded consuming
  turn must not consume the artifact or materialize a recovered scheduling
  command.

## Non-goals

- No typed deterministic renderer for user-visible text.
- No phrase denylist in production routing. Banned phrases remain regression
  and eval assertions.
- No pending approval or accept/reject shared-reminder flow.
- No global friend alias memory.
- No recovery for arbitrary blocked scheduling, unrelated `X is Y` statements,
  expired artifacts, or resume-after-unrelated-turns product scope.
- No broad history re-parse to reconstruct title, time, duration, or friend
  reference.

## Options Considered

### Option A: Prompt-only repair

Add stronger instructions telling the model not to claim success until the tool
result succeeds and to handle "X is Y" corrections.

This is rejected. The RCA already showed prompt-only constraints fail in
production. It also does not create durable recovery state across workers.

### Option B: Deterministic response renderer

Materialize social-scheduling commands, then have runtime code emit fixed
success, blocker, or confirmation copy.

This is rejected by D1. It would split channel-visible prose ownership away
from the Interaction Agent.

### Option C: Typed facts plus structural output guard

Have social-scheduling tools emit a structured outcome. The Interaction Agent
receives that outcome as a trusted dynamic block and must include a matching
structured claim in the output protocol. Runtime validates the structured claim
against the outcome status and only then commits/delivers the prose. Friend
corrections become typed semantic follow-up actions that unlock a narrow durable
artifact as a trusted fact block.

This is the selected approach. It keeps the single producer while making the
facts and the guard structural.

## Design

### SocialSchedulingOutcome

Introduce a canonical outcome shape owned by SocialScheduling and carried in
tool events, prompt blocks, staged command preview facts, and close-boundary
materialization facts:

```json
{
  "type": "social_scheduling_outcome",
  "outcome_id": "staged-command-or-domain-id",
  "operation": "shared_reminder_create",
  "status": "created_active",
  "shared_reminder_id": "optional",
  "staged_command_id": "optional",
  "title": "晨跑",
  "local_trigger_at": "2029-01-01T08:30:00",
  "captured_timezone": "Asia/Shanghai",
  "duration_minutes": 15,
  "participants": [
    {"account_id": "friend-account", "display_name": "Oliver"}
  ],
  "blocker": null,
  "facts_hash": "stable-hash"
}
```

Canonical statuses:

- `created_active`: close-time result is an active shared reminder.
- `duplicate_active`: an identical active shared reminder already exists.
- `blocked_unmatched_friend`: the request named a friend reference that does
  not resolve to an active friend.
- `blocked_ambiguous_friend`: the friend reference resolves to more than one
  active friend or is semantically ambiguous.
- `blocked_receiver_conflict`: at least one participant is busy.
- `blocked_unreachable_participant`: at least one participant lacks a usable
  channel.
- `needs_participants`, `needs_title`, `needs_time`, `needs_context`,
  `needs_past_time_confirmation`, `needs_incomplete_date_clarification`: the
  request is missing required facts or needs one user clarification.
- `invalid`: the command cannot be trusted as executable.
- `staged_pending_close`: internal stage result only. It is not a success
  status and must not be claimed as created or active.

Allowed structured claims:

| Outcome status | Allowed claim |
| --- | --- |
| `created_active` | `active_created` |
| `duplicate_active` | `already_active` |
| `blocked_unmatched_friend` | `blocked_unmatched_friend` |
| `blocked_ambiguous_friend` | `blocked_ambiguous_friend` |
| `blocked_receiver_conflict` | `blocked_receiver_conflict` |
| `blocked_unreachable_participant` | `blocked_unreachable_participant` |
| `needs_*` | matching `needs_*` clarification claim |
| `invalid` | `failed` |
| `staged_pending_close` | `no_success_claim` only |

The Interaction Agent remains responsible for the visible words. When a
social-scheduling outcome is present, the output protocol must include a
structured claim:

```json
{
  "type": "reply",
  "segments": ["..."],
  "domain_claim": {
    "domain": "social_scheduling",
    "outcome_id": "same outcome id",
    "status": "created_active",
    "claim": "active_created"
  }
}
```

Production validation checks the claim object, not a phrase denylist. Regression
tests may assert that created replies do not contain approval/pending wording
and blocked/no-materialized replies do not contain known soft-success phrases.

### Close Boundary Binding

Social-scheduling staged writes include a structured outcome in
`preview_facts`. The close-boundary materializer returns a
`MaterializedCommand` with the same outcome shape and a fresh `facts_hash` for
the materialized result. The output guard validates the final structured
`domain_claim` against the trusted outcome and the staged/materialized command
ids.

If a command remains only `staged_pending_close`, a final reply may not claim
creation. If materialization reports blocked or needs status, the final claim
must match that status. If no social-scheduling outcome exists for a
state-changing shared-reminder claim, the output is invalid and the turn retries
or fails closed.

This keeps deterministic behavior in the fact supply and validation layer. It
does not generate user-visible text.

### RecoverableSchedulingIntent

Add a durable `recoverable_scheduling_intent` table in the SocialScheduling
bounded context.

Fields:

- `id`
- `conversation_id`
- `creator_account_id`
- `operation` fixed to `shared_reminder_create`
- `status`: `open`, `consumed`, `expired`, `superseded`
- `blocker`: `unmatched_friend` or `ambiguous_friend`
- `title`
- `local_trigger_at`
- `captured_timezone`
- `duration_minutes`
- `unresolved_reference_text`
- `source_turn_id`
- `source_input_from_seq`
- `source_input_to_seq`
- `source_message_ids` JSON array
- `facts` JSONB with the normalized understood request facts
- `facts_hash`
- `expires_at`
- `consumed_turn_id`
- `created_at`
- `updated_at`

There is at most one `open` artifact per conversation. Creating a new open
artifact supersedes any previous open artifact in that conversation. The default
expiry is short, implemented as a service constant in minutes.

Creation happens only after a fresh blocked turn successfully closes with a
visible reply and a `SocialSchedulingOutcome` status of
`blocked_unmatched_friend` or `blocked_ambiguous_friend`. Failed and superseded
turns create nothing.

The artifact is never materialized directly. It is a trusted input for a later
agent turn.

### Semantic Follow-Up Action

Extend `SemanticDecision` with an optional typed `follow_up_action`.

Supported action for this work:

```json
{
  "type": "resolve_friend_reference_correction",
  "prior_reference_text": "zihao",
  "corrected_friend_text": "olivers",
  "scope": "immediately_preceding_unresolved_intent"
}
```

The semantic interpreter prompt and validator expose this action explicitly.
The runner does not string-match `就是`, `is`, or any other correction marker.
If the interpreter does not emit this action, the recovery path stays closed.

### Consuming Recovery

On a fresh inbound turn:

1. The runner calls the semantic interpreter as usual.
2. If `follow_up_action.type` is
   `resolve_friend_reference_correction`, the runner reads the open
   recoverable intent for the conversation.
3. The runner requires the artifact to be open, unexpired, scoped to
   `shared_reminder_create`, blocked by `unmatched_friend` or
   `ambiguous_friend`, and matching the action's prior reference when supplied.
4. The runner resolves `corrected_friend_text` through active friends owned by
   SocialScheduling. Exact active-friend resolution is deterministic domain
   resolution, not intent routing.
5. If exactly one active friend matches, the runner injects a dynamic trusted
   fact block:

```json
{
  "recoverable_scheduling_intent": {
    "id": "...",
    "facts_hash": "...",
    "title": "晨跑",
    "local_trigger_at": "2029-01-01T08:30:00",
    "captured_timezone": "Asia/Shanghai",
    "duration_minutes": 15,
    "resolved_friend": {
      "account_id": "...",
      "display_name": "Oliver"
    },
    "instruction": "Call social_scheduling_tool to create a fresh shared reminder using these facts."
  }
}
```

6. The Interaction Agent calls `social_scheduling_tool`. Tool defaults add
   `recoverable_scheduling_intent_id` and `facts_hash` to the fresh command.
7. The command stages and materializes through the normal close boundary.
8. Only after a fresh close successfully materializes the recovered command does
   SocialScheduling mark the artifact `consumed` with `consumed_turn_id`.

If the artifact is expired, missing, or ambiguous, the runner injects a
trusted recovery-resolution block and constrains the agent to ask one concise
confirmation. It does not create a shared reminder and does not consume the
artifact.

### Dead Code Removal

Remove deterministic interaction-agent helper branches that recover shared
reminder friend follow-ups or ask friend questions by inspecting message text.
Those behaviors are replaced by semantic follow-up actions, trusted facts, and
agent-produced prose.

Existing pending clarification behavior for non-recovery reminder/focus
clarifications remains only if it does not reconstruct shared-reminder
executable state from history.

## Data Flow

Blocked first turn:

```text
InboundTurn
  -> SemanticInterpreter: scheduling/create_shared_reminder
  -> Interaction Agent calls social_scheduling_tool/list_friends or blocked helper
  -> SocialSchedulingOutcome(blocked_unmatched_friend or blocked_ambiguous_friend)
  -> Interaction Agent replies with matching structured domain_claim
  -> commit_reply closes fresh input window
  -> RecoverableSchedulingIntent(open) is created from the trusted outcome
```

Correction turn:

```text
InboundTurn "zihao is olivers"
  -> SemanticInterpreter emits resolve_friend_reference_correction
  -> runner loads open recoverable intent
  -> SocialScheduling resolves corrected friend text to exactly one active friend
  -> trusted recoverable_scheduling_intent block is injected
  -> Interaction Agent calls social_scheduling_tool/create_shared_reminder
  -> close boundary materializes fresh staged command
  -> artifact consumed only after successful fresh close
```

Superseded correction turn:

```text
Correction turn stages a recovered create command
  -> newer inbound arrives before close
  -> turn becomes superseded
  -> staged command is superseded or left unmaterialized
  -> recoverable_scheduling_intent remains open
```

## Error Handling

- Invalid or missing `domain_claim` when a social-scheduling outcome is required
  makes the output invalid and triggers the existing protocol retry path.
- A retry still using an invalid claim fails closed through the normal output
  protocol failure.
- `staged_pending_close` with a success claim is invalid.
- A blocked outcome with a mismatched claim is invalid.
- Expired recoverable intents are marked expired when read and produce a
  trusted stale-recovery block for one concise agent question.
- Ambiguous corrected friend resolution produces a trusted ambiguous-recovery
  block for one concise agent question.
- Artifact consumption is idempotent and requires matching `facts_hash`.

## Testing

TDD coverage must include:

- Schema contract for `recoverable_scheduling_intent` columns and one-open
  partial unique index.
- Repository/service tests for create-open, supersede-previous-open, expire,
  resolve exactly-one friend, ambiguous friend, consume only matching open
  artifact, and no consumption on superseded turns.
- Semantic interpreter tests for the typed follow-up action and invalid action
  rejection.
- Interaction-agent tests for `SocialSchedulingOutcome` prompt blocks and
  structured `domain_claim` validation.
- Output protocol tests for accepted and rejected social-scheduling claims.
- Turn runner tests for artifact creation after fresh blocked close, correction
  trusted fact injection, unrelated `X is Y` ignored, ambiguous correction
  asks one confirmation through the agent, and superseded consuming turns not
  materializing or consuming.

Regression assertions may check known bad phrases in test fixtures, but
production routing must not depend on a phrase denylist.

## Documentation Updates

Update `docs/ARCHITECTURE.md` to add:

- SocialScheduling now owns `recoverable_scheduling_intent` as a narrow durable
  artifact.
- The Turn carries social-scheduling outcomes as dynamic trusted facts and
  validates structured output claims against them.
- The single Interaction Agent producer invariant is unchanged.

No deployment flow changes are expected.
