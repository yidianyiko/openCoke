# Generalized Pending Workflow Design

**Date:** 2026-05-09
**Status:** Ready for implementation planning

Spec-level blockers resolved inline:

- pending-workflow persistence API, partial unique index, TTL, and
  revision-based optimistic concurrency (see "Persistence Boundary",
  "Concurrency")
- exact `ReminderDetectDecision` schema extension and validation-failure
  handling (see "LLM Decision Contract", "Schema Validation and Failure
  Handling")
- explicit workflow status and slot transition table (see "State Transitions")
- two-phase migration with feature flags and rollback (see "Migration
  Phasing", "Feature Flag and Rollback")
- ablation protocol that makes the "no phrase rules" claim falsifiable
  (see "Validation Rules")
- deprecation policy for the legacy clarify-without-workflow path (see
  "Migration Phasing")

Open evidence (produced during implementation, not before the plan):

- first two-turn runtime/eval proof path through `business-clawscale`
- ablation run showing the new path holds without high-frequency safety
  guards

## Problem

Coke already supports reminder clarification at the decision level:
`ReminderDetectDecision` can return `intent_type="clarify"` with a
`clarification_question`, and the runtime can show that question to the user.

That is not enough for a stable product workflow. When a user provides
incomplete information, the system can ask a follow-up question, but it does
not keep a durable, structured record of what it is waiting for. The next user
message is interpreted mostly from recent chat context instead of from a
first-class pending workflow.

This causes three problems:

- The system can lose the relationship between a follow-up answer and the
  original task.
- The runtime cannot tell which fields are missing, which assumptions were
  made, or whether a draft is ready to execute.
- Execution results are still shaped per capability, without a shared envelope
  for follow-up actions such as confirmation, preview, modification, or error
  reporting.

The fix is not to add natural-language rules for individual phrases. LLMs
should continue to interpret user intent. Runtime code should own durable
workflow state and lifecycle.

## Decision

Introduce a generalized pending workflow protocol.

The protocol has a generic outer envelope for lifecycle, missing information,
and next interaction steps. Domain-specific details live inside typed payloads.

First implementation scope:

- reminder creation, update, cancellation, and completion clarification
- reminder plans that may expand into multiple reminder operations

Future domains may adopt the same envelope only after reminder V1 proves the
contract. Calendar events, user-goal drafts, and task-planning drafts are not
part of the first implementation.

The protocol must not encode narrow phrase rules. It should represent the
state produced by LLM interpretation, not replace interpretation with parser
logic.

### Generality Scope for V1

The envelope is named "generalized" because lifecycle, slots, and `next_steps`
are domain-agnostic. It is **not** validated as a cross-domain contract until a
second domain adopts it. To prevent generality from becoming dead weight:

- The V1 envelope shape is provisional. When a second domain (calendar,
  user-goal, task-planning) adopts it, the envelope may need a breaking
  change. Treat the current shape as "reminder-shaped, written generically",
  not as a frozen public contract.
- Do **not** add envelope fields, slot statuses, or `next_steps` values
  motivated only by hypothetical future domains. Add them when a real domain
  needs them.
- Reminder-only structure lives in `payload.reminder`. Anything truly
  reminder-specific stays inside the typed payload, not in the outer envelope.

## Non-Goals

- Build a general workflow engine.
- Add deterministic natural-language parsers for reminder phrases.
- Introduce a compatibility layer for the retired Team runtime.
- Make every tool use this protocol in the first implementation.
- Add domain examples that are not part of the near-term product surface.
- Store first-class workflow state in timezone/user-settings fields.

## Workflow Envelope

Pending workflow documents use one generic envelope:

```json
{
  "id": "workflow_...",
  "kind": "reminder_create",
  "status": "awaiting_user",
  "origin": {
    "conversation_id": "...",
    "message_ids": ["..."],
    "created_at": "2026-05-09T10:00:00+09:00",
    "updated_at": "2026-05-09T10:00:00+09:00",
    "expires_at": "2026-05-10T10:00:00+09:00"
  },
  "goal": "Set up an hourly check-in reminder",
  "slots": {
    "title": {"value": "打卡", "status": "filled"},
    "cadence": {"value": "hourly", "status": "filled"},
    "start_at": {"value": null, "status": "missing"},
    "deadline_at": {"value": null, "status": "missing"}
  },
  "missing_fields": ["start_at", "deadline_at"],
  "assumptions": [],
  "constraints": [],
  "next_steps": ["ask_user"],
  "payload": {
    "reminder": {
      "draft_operations": []
    }
  }
}
```

### Required Fields

- `id`: stable workflow id.
- `kind`: typed workflow kind. Initial values:
  - `reminder_create`
  - `reminder_update`
  - `reminder_cancel`
  - `reminder_complete`
  - `reminder_plan`
- `status`: lifecycle state. Initial values:
  - `draft`
  - `awaiting_user`
  - `ready_to_execute`
  - `executing`
  - `completed`
  - `cancelled`
  - `expired`
  - `failed`
- `origin`: where the workflow came from and when it expires.
- `goal`: short natural-language description for LLM and developer inspection.
- `slots`: field-level state. Each slot has `value` and `status`.
- `missing_fields`: field names that must be filled before execution.
- `assumptions`: explicit assumptions the model made.
- `constraints`: explicit constraints from the user or product policy.
- `next_steps`: enum list describing what should happen next.
- `payload`: typed domain payload.

Slot statuses:

- `missing`: required and not known.
- `filled`: known enough to use.
- `assumed`: filled by an assumption that may need user confirmation.
- `needs_confirmation`: known but must be confirmed before execution.
- `invalid`: supplied but not usable.

`next_steps` is intentionally small:

- `ask_user`
- `display_preview`
- `execute_now`
- `show_confirmation`
- `offer_modification`
- `notify_error`
- `no_action`

New enum values require a spec update.

### State Transitions

The runtime accepts only the following workflow `status` transitions:

```
draft            -> awaiting_user        (clarify needed)
draft            -> ready_to_execute     (all slots filled in one turn)
awaiting_user    -> awaiting_user        (more clarification needed)
awaiting_user    -> ready_to_execute     (missing slots filled)
awaiting_user    -> cancelled            (user cancels or starts unrelated workflow)
awaiting_user    -> expired              (TTL elapsed)
ready_to_execute -> executing            (runtime begins execution)
ready_to_execute -> awaiting_user        (executor returns needs_user)
ready_to_execute -> expired              (TTL elapsed)
executing        -> completed            (success)
executing        -> failed               (capability error)
executing        -> awaiting_user        (capability returns needs_user)
```

`completed`, `cancelled`, `expired`, and `failed` are terminal. Any other
transition is illegal. If the LLM returns a `workflow_update` whose status
does not match a legal transition from the current persisted state, the
runtime rejects the update and keeps the previous workflow document.

Slot status transitions:

```
missing            -> filled | assumed | needs_confirmation | invalid
assumed            -> filled (user confirmed) | invalid (corrected to bad value)
needs_confirmation -> filled (confirmed) | invalid
invalid            -> filled (re-supplied) | missing (cleared by user)
filled             -> needs_confirmation | invalid (later contradicted)
```

If `workflow_update.status="ready_to_execute"` but `missing_fields` is
non-empty, or any slot is `missing`/`invalid`, the runtime overrides status
to `awaiting_user` and logs `workflow_invariant_violation`. The executor
must not run.

## LLM Decision Contract

LLM agents interpret the user message and return structured decisions. They do
not write directly to MongoDB.

V1 extends `ReminderDetectDecision` with one optional field:

- `workflow_update`: a validated pending workflow envelope, or `null`.

The current `ReminderDetectDecision` model forbids unknown fields, so
implementation must add this field explicitly before any detector prompt asks
for workflow output. The field name is `workflow_update`, not a free-form
`workflow` key.

For incomplete tasks, the decision should include:

- the workflow kind
- the current slot values
- missing fields
- a concise clarification question
- next steps, usually `["ask_user"]`

For follow-up user messages, the decision input includes the active pending
workflow for that conversation. The LLM decides whether the new message:

- fills missing slots
- changes a filled slot
- cancels the workflow
- confirms execution
- starts a separate workflow
- is unrelated ordinary chat

The runtime must not infer this relationship with phrase matching. It may use
strict ids, conversation boundaries, expiry, and lifecycle state to decide
which pending workflow is eligible for the LLM to inspect.

### Schema Validation and Failure Handling

The runtime must validate `workflow_update` against the envelope schema (via
the same Pydantic model used for persistence) before storing. If validation
fails:

1. Log a structured `workflow_schema_invalid` event with the validation
   errors, raw decision excerpt, and conversation id.
2. Discard the invalid `workflow_update`.
3. Preserve the existing pending workflow (if any) unchanged.
4. Continue with `intent_type` and `clarification_question` as the V0 path,
   so the user is not blocked by a model formatting error.

V1 acceptance requires `workflow_schema_invalid` rate ≤ 5% across the
two-turn reminder eval corpus (≥ 50 representative decisions). Higher rates
block Phase A GA.

The runtime must additionally reject any `workflow_update` whose
`status` change is not a legal transition (see "State Transitions") or whose
`status="ready_to_execute"` contradicts non-empty `missing_fields`. Such
rejections are logged as `workflow_invariant_violation` and counted toward
operational SLOs separately from schema invalidity.

## Runtime Responsibilities

The runtime owns workflow lifecycle:

1. Load an active pending workflow for the current user and conversation,
   including its `revision` counter.
2. Include the workflow in the relevant detector/tool input.
3. Validate any returned `workflow_update` (schema, transitions, invariants)
   before persisting.
4. Persist accepted updates with a CAS condition on `(id, revision)`,
   incrementing `revision` on success.
5. Expire stale workflows via TTL on `expires_at`.
6. Clear completed, cancelled, or failed workflows from the active set
   (terminal documents may remain in the collection until TTL removes them).
7. Ensure only one active workflow per conversation for the first
   implementation.

### Concurrency

Multiple turns of the same conversation may overlap when the user sends
messages quickly:

- The runtime reads the workflow with its `revision` (a monotonically
  increasing integer stored on the document).
- The detector input carries this revision alongside the workflow document.
- On write, the runtime issues a conditional update keyed by `(id, revision)`.
  If another turn already advanced the document, the conditional update
  fails. The runtime drops the new `workflow_update`, logs
  `workflow_concurrent_write_dropped`, and answers the user from the freshly
  observed workflow state.

This gives at-most-once application of an LLM update. Losing one update
under contention is preferred over corrupting workflow state with
out-of-order writes.

### Persistence Boundary

V1 must use a dedicated pending-workflow store, not `pending_task_draft`.

`pending_task_draft` currently lives in the timezone/user-settings state shape
and is cleared by timezone confirmation flows. Reusing it for reminder
workflow state would let an unrelated timezone operation erase a pending
reminder workflow and would not satisfy the conversation-scoped active workflow
rule.

The implementation plan must choose one concrete store before coding. The
preferred shape is a MongoDB `pending_workflows` collection with:

- `id`
- `owner_user_id`
- `conversation_id`
- `kind`
- `status`
- `revision` (monotonic integer for optimistic concurrency)
- `created_at`
- `updated_at`
- `expires_at`
- `document` (the full envelope)

Required indexes:

- partial unique index on `(owner_user_id, conversation_id)` filtered to
  active statuses, so terminal documents do not block new workflows:
  ```
  db.pending_workflows.createIndex(
    {owner_user_id: 1, conversation_id: 1},
    {
      unique: true,
      partialFilterExpression: {
        status: {$in: ["draft", "awaiting_user", "ready_to_execute", "executing"]}
      }
    }
  )
  ```
- TTL index on `expires_at` for automatic cleanup of expired and terminal
  documents.
- secondary index on `(status, updated_at)` for operational inspection.

The runtime uses `(id, revision)` as the CAS condition on every write (see
"Concurrency" above).

If the implementation instead stores the document under conversation state, it
must still enforce conversation scoping, expiry cleanup, and one active
workflow per conversation. It must not write pending-workflow state into
timezone fields.

## Capability Result Envelope

Capability results should converge on a shared execution envelope inside
`CapabilityResult.content`:

```json
{
  "status": "success",
  "operation": "create_reminder",
  "entities": [
    {
      "entity_type": "reminder",
      "entity_id": "...",
      "title": "打卡",
      "next_fire_at": "2026-05-09T11:00:00+09:00"
    }
  ],
  "visible_summary": "已创建整点打卡提醒，下一次是 11:00。",
  "next_steps": ["show_confirmation", "offer_modification"]
}
```

Envelope fields:

- `status`: `success`, `partial_success`, `needs_user`, or `error`.
- `operation`: stable operation id, for example `create_reminder`.
- `entities`: created, changed, listed, or affected domain entities.
- `visible_summary`: deterministic user-visible summary when the capability owns
  the acknowledgement.
- `next_steps`: same enum family as workflow next steps.
- `error`: structured error object when `status="error"`.

`CapabilityResult.visible_summary` remains the runtime contract. The shared
execution envelope may add structure around it, but durable writes must still
expose a non-empty `visible_summary` or compatible existing summary field until
the runtime contract is deliberately changed.

## Reminder Clarification Example

User:

> 每个整点喊我打卡吧

Detector result:

```json
{
  "intent_type": "clarify",
  "action": "",
  "workflow_update": {
    "id": "workflow_...",
    "kind": "reminder_create",
    "status": "awaiting_user",
    "origin": {
      "conversation_id": "...",
      "message_ids": ["..."],
      "created_at": "2026-05-09T10:00:00+09:00",
      "updated_at": "2026-05-09T10:00:00+09:00",
      "expires_at": "2026-05-10T10:00:00+09:00"
    },
    "goal": "Set up whole-hour check-in reminders",
    "slots": {
      "title": {"value": "打卡", "status": "filled"},
      "cadence": {"value": "whole_hour", "status": "filled"},
      "start_at": {"value": null, "status": "missing"},
      "deadline_at": {"value": null, "status": "missing"}
    },
    "missing_fields": ["start_at", "deadline_at"],
    "assumptions": [],
    "constraints": [],
    "next_steps": ["ask_user"],
    "payload": {
      "reminder": {
        "draft_operations": []
      }
    }
  },
  "clarification_question": "每个整点打卡要从什么时候开始，持续到什么时候结束？"
}
```

The runtime persists the workflow and sends the clarification question. It does
not create reminders.

Follow-up:

> 从现在到晚上七点

The detector receives the pending workflow and may return a completed
`reminder_create` decision with `workflow_update.status="ready_to_execute"`
and executable reminder fields or batch operations. Only then does the reminder
executor create reminders and return a deterministic execution envelope.

## Data Boundaries

```
user message
  -> single Agent
  -> reminder_intent tool
  -> ReminderDetectAgent
       input: current message + active pending workflow
       output: decision + optional workflow_update
  -> runtime workflow store
  -> executor only when ready_to_execute
  -> CapabilityResult execution envelope
  -> deterministic user-visible summary
```

The single Agent may read model-facing tool envelopes, but durable state and
visible acknowledgements are controlled through typed side channels:

- pending workflow documents
- `CapabilityResult`
- deterministic `visible_summary`

## Validation Rules

- A workflow with `missing_fields` must not execute.
- A workflow with `next_steps=["ask_user"]` must produce a user-visible
  clarification question.
- A durable write result must include a deterministic `visible_summary` or
  compatible visible summary.
- A follow-up answer must be evaluated with the active workflow included in the
  LLM input.
- If the active workflow is expired or from another conversation, it must not
  be used to interpret the current message.
- Runtime code may validate lifecycle shape and required fields, but must not
  classify user language with phrase-specific rules.
- The motivating two-turn reminder cases must be satisfied by the pending
  workflow protocol. New phrase-specific branches, prompt examples, or parser
  shortcuts may not be added to rescue those cases.
- Existing high-frequency safety guards may remain during the first migration,
  but acceptance evidence must include an ablation that proves the new
  two-turn path holds without them.

### Ablation Protocol for "No Phrase Rules"

To make the "no phrase-specific rules" claim falsifiable:

1. Define an ablation eval subset: at minimum, the two-turn reminder cases in
   the "Eval cases" list, plus any reminder phrases the high-frequency safety
   guards currently match.
2. Run the subset twice — once with all current guards enabled, once with
   them disabled (guards bypassed via test harness, not removed from prod).
3. Phase A acceptance requires the disabled-guards run to clear **either**
   bar — meeting either is sufficient:
   - ≥ 90% absolute success on the ablation subset, **or**
   - ≥ 95% of the with-guards baseline success rate (covers cases where
     baseline itself is below 95% for unrelated reasons).
4. Record both rates and the gap in the acceptance evidence; do not collapse
   the comparison into a single pass/fail bit.

If neither bar is cleared, Phase A is not done: the new path is relying on
the guards. Either improve detector behavior or revisit the spec.

## Testing

Unit tests:

- workflow envelope validation
- pending workflow load/store/expiry
- detector input includes active workflow and current `revision`
- clarify decision persists workflow and returns user-visible question
- follow-up answer updates workflow instead of starting a new one
- workflow with missing fields does not execute
- illegal status transition is rejected; previous workflow is preserved
- `status="ready_to_execute"` with non-empty `missing_fields` is overridden
  to `awaiting_user` and logs `workflow_invariant_violation`
- invalid `workflow_update` schema is dropped; existing workflow preserved;
  `workflow_schema_invalid` metric incremented; legacy clarify path still
  answers the user
- partial unique index allows a new active workflow once the prior one is
  terminal
- CAS-on-`revision` rejects stale writes and increments the
  `workflow_concurrent_write_dropped` metric
- TTL index reaps expired and terminal documents
- execution envelope maps to `CapabilityResult.visible_summary`
- durable write without `visible_summary` fails the existing runtime contract
- detector rejects unknown workflow keys until `workflow_update` is added to
  the schema, then accepts only validated `workflow_update` documents
- timezone or user-settings updates do not clear pending reminder workflows
- `pending_workflow.reminders.enabled=false` disables the new path
  end-to-end; legacy clarify behavior is byte-for-byte unchanged

Runtime tests:

- one-turn reminder create still works without pending workflow
- incomplete reminder request asks a clarification and persists workflow
- second-turn completion creates reminders and clears workflow
- cancellation of a pending workflow clears it without durable reminder writes
- expired workflow is ignored and removed
- two concurrent turns of the same conversation: one update lands, the other
  is dropped with the concurrency metric incremented; user-visible response
  is consistent with the persisted state

Eval cases:

- `每个整点喊我打卡吧` asks for start/end rather than creating reminders.
- Follow-up `从现在到晚上七点` completes the same workflow and creates the
  expected bounded reminders.
- Ordinary chat after a pending workflow does not accidentally execute it.
- A timezone confirmation or cancellation while a reminder workflow is pending
  does not erase or execute the reminder workflow.
- Ablation run: the two-turn cases above, executed with high-frequency safety
  guards bypassed via the test harness, must meet the thresholds in
  "Ablation Protocol for No Phrase Rules".

## Migration Phasing

The two protocol changes (pending workflow input and capability result
envelope) ship in independent phases so they can be flagged and rolled back
separately.

### Phase A — Pending Workflow (input contract)

- Adds `workflow_update` to `ReminderDetectDecision`.
- Adds the `pending_workflows` store and runtime lifecycle code.
- Existing `clarification_question` remains the rendered user-visible output;
  the workflow envelope is durable state behind it.
- Acceptance: missing-detail reminder cases produce a durable workflow,
  follow-up answers complete it, no phrase-specific parser added, and the
  ablation protocol passes.

After Phase A has been GA-stable for at least 14 days with
`workflow_schema_invalid` rate ≤ 5% and the ablation protocol passing, every
`intent_type="clarify"` decision must include a `workflow_update`. The
standalone clarify-without-workflow path is then deprecated and removed in a
follow-up cleanup change.

### Phase B — Execution Envelope (output contract)

- Reminder executor emits the structured `CapabilityResult.content` envelope
  with `status`, `operation`, `entities`, and `next_steps`.
- `CapabilityResult.visible_summary` contract preserved.
- Acceptance: durable reminder writes carry the envelope; no behavior
  regression on existing one-turn cases.

Phase B is independent of Phase A. It may ship after Phase A or be
deferred entirely if Phase A's evidence reveals other risks. Phase A is the
prerequisite for the motivating two-turn product behavior.

## Feature Flag and Rollback

Phase A is gated by a runtime flag `pending_workflow.reminders.enabled`
(default `false` on first deploy, flipped on per-environment after smoke).
Phase B is gated by a separate flag
`pending_workflow.reminders.execution_envelope.enabled` so the two contracts
roll back independently.

When `pending_workflow.reminders.enabled=false`:

- The runtime does not load or persist pending workflows.
- The detector receives no workflow input.
- A `workflow_update` returned by the model (if any) is ignored.
- The legacy clarify-without-workflow path runs unchanged.

Rollback procedure:

1. Set the relevant flag to `false` and redeploy (or hot-reload if
   supported).
2. Existing pending workflow documents become inert. The TTL index removes
   them via `expires_at`. No data migration is required.
3. Re-enabling later resumes the new path; in-flight legacy clarify
   conversations are unaffected either way.

## Migration Plan

Phase A:

1. Add workflow dataclasses or Pydantic models under the Agent runtime or a
   small shared workflow module.
2. Add the `pending_workflow.reminders.enabled` flag (default off) and
   surface it through runtime config.
3. Add the `pending_workflows` collection, partial unique index, TTL index,
   and CAS-on-`revision` write helper.
4. Extend reminder detector input with the active workflow and revision.
5. Extend `ReminderDetectDecision` to carry optional `workflow_update`,
   reject unknown keys until then, accept only validated documents after.
6. Persist clarify workflow updates before returning the user-visible
   question; enforce state-transition and invariant checks.
7. Add two-turn true-path reminder tests through `business-clawscale`.
8. Add a real-model/tool-call smoke for the two-turn clarification path.
9. Run the ablation protocol; record both rates as acceptance evidence.
10. Roll the flag on per environment after smoke. Watch
    `workflow_schema_invalid`, `workflow_invariant_violation`, and
    `workflow_concurrent_write_dropped` metrics.

Phase A cleanup (after 14-day GA + acceptance):

11. Require `workflow_update` on every `intent_type="clarify"` decision.
12. Remove the legacy clarify-without-workflow code path.

Phase B:

13. Add the `pending_workflow.reminders.execution_envelope.enabled` flag.
14. Teach reminder execution results to emit the shared execution envelope
    while preserving `CapabilityResult.visible_summary`.
15. Roll the Phase B flag on per environment after smoke.

Future:

16. Only after Phase A and Phase B evidence passes, decide whether calendar
    or user-goal domains should adopt this protocol in separate specs.

## Acceptance Criteria

- Missing reminder details produce a durable pending workflow and a visible
  follow-up question.
- User follow-up can complete the same workflow without relying only on recent
  chat text.
- No phrase-specific parser is introduced for the motivating reminder cases.
- Successful reminder writes return deterministic execution envelopes.
- Existing one-turn reminder CRUD behavior remains intact.
- Normal-path eval includes at least one two-turn clarification case.
- The pending workflow store is conversation-scoped and cannot be cleared by
  timezone/user-settings flows.
- The implementation preserves the current single-Agent typed side-channel
  boundary: LLMs interpret; runtime validates, persists, executes, and owns
  deterministic user-visible acknowledgements.
- Phase A is gated by `pending_workflow.reminders.enabled` and is rollback-able
  by flipping the flag; pending documents become inert and are removed by
  TTL.
- The ablation protocol has been executed and recorded; the disabled-guards
  run meets ≥ 90% absolute or ≥ 95% of the with-guards baseline.
- `workflow_schema_invalid` rate ≤ 5% on the eval corpus.
