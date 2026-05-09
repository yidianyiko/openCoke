# Generalized Pending Workflow Design

**Date:** 2026-05-09
**Status:** Draft approved for implementation planning

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
- calendar-style scheduling clarification if a future implementation uses the
  same protocol
- user-goal or task-planning drafts when they need follow-up before execution

The protocol must not encode narrow phrase rules. It should represent the
state produced by LLM interpretation, not replace interpretation with parser
logic.

## Non-Goals

- Build a general workflow engine.
- Add deterministic natural-language parsers for reminder phrases.
- Introduce a compatibility layer for the retired Team runtime.
- Make every tool use this protocol in the first implementation.
- Add domain examples that are not part of the near-term product surface.

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
  - `calendar_event`
  - `user_goal`
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

## LLM Decision Contract

LLM agents interpret the user message and return structured decisions. They do
not write directly to MongoDB.

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

## Runtime Responsibilities

The runtime owns workflow lifecycle:

1. Load an active pending workflow for the current user and conversation.
2. Include the workflow in the relevant detector/tool input.
3. Persist new or updated workflows returned by the capability.
4. Expire stale workflows.
5. Clear completed, cancelled, or failed workflows.
6. Ensure only one active workflow per conversation for the first
   implementation.

The first implementation should store the active workflow in the existing user
state slot currently named `pending_task_draft`, then migrate the name to
`pending_workflow` in a focused schema cleanup. During the migration, code may
read both names, but writes should use the new name once the canonical field is
introduced.

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
  "user_summary": "已创建整点打卡提醒，下一次是 11:00。",
  "next_steps": ["show_confirmation", "offer_modification"]
}
```

Envelope fields:

- `status`: `success`, `partial_success`, `needs_user`, or `error`.
- `operation`: stable operation id, for example `create_reminder`.
- `entities`: created, changed, listed, or affected domain entities.
- `user_summary`: deterministic user-visible summary when the capability owns
  the acknowledgement.
- `next_steps`: same enum family as workflow next steps.
- `error`: structured error object when `status="error"`.

`CapabilityResult.visible_summary` should prefer `user_summary` once the
envelope is adopted. Until then, the existing `summary` and `message` fallback
remains for compatibility.

## Reminder Clarification Example

User:

> 每个整点喊我打卡吧

Detector result:

```json
{
  "intent_type": "clarify",
  "action": "",
  "workflow": {
    "kind": "reminder_create",
    "status": "awaiting_user",
    "goal": "Set up whole-hour check-in reminders",
    "slots": {
      "title": {"value": "打卡", "status": "filled"},
      "cadence": {"value": "whole_hour", "status": "filled"},
      "start_at": {"value": null, "status": "missing"},
      "deadline_at": {"value": null, "status": "missing"}
    },
    "missing_fields": ["start_at", "deadline_at"],
    "next_steps": ["ask_user"]
  },
  "clarification_question": "每个整点打卡要从什么时候开始，持续到什么时候结束？"
}
```

The runtime persists the workflow and sends the clarification question. It does
not create reminders.

Follow-up:

> 从现在到晚上七点

The detector receives the pending workflow and may return a completed
`reminder_create` decision with `status="ready_to_execute"`. Only then does the
reminder executor create reminders and return a deterministic execution
envelope.

## Data Boundaries

```
user message
  -> single Agent
  -> reminder_intent tool
  -> ReminderDetectAgent
       input: current message + active pending workflow
       output: decision + optional workflow update
  -> runtime workflow store
  -> executor only when ready_to_execute
  -> CapabilityResult execution envelope
  -> deterministic user-visible summary
```

The single Agent may read model-facing tool envelopes, but durable state and
visible acknowledgements are controlled through typed side channels:

- pending workflow documents
- `CapabilityResult`
- deterministic `user_summary` / `visible_summary`

## Validation Rules

- A workflow with `missing_fields` must not execute.
- A workflow with `next_steps=["ask_user"]` must produce a user-visible
  clarification question.
- A durable write result must include a deterministic `user_summary` or
  compatible visible summary.
- A follow-up answer must be evaluated with the active workflow included in the
  LLM input.
- If the active workflow is expired or from another conversation, it must not
  be used to interpret the current message.
- Runtime code may validate lifecycle shape and required fields, but must not
  classify user language with phrase-specific rules.

## Testing

Unit tests:

- workflow envelope validation
- pending workflow load/store/expiry
- detector input includes active workflow
- clarify decision persists workflow and returns user-visible question
- follow-up answer updates workflow instead of starting a new one
- workflow with missing fields does not execute
- execution envelope maps to `CapabilityResult.visible_summary`
- durable write without `user_summary` fails the existing runtime contract

Runtime tests:

- one-turn reminder create still works without pending workflow
- incomplete reminder request asks a clarification and persists workflow
- second-turn completion creates reminders and clears workflow
- cancellation of a pending workflow clears it without durable reminder writes
- expired workflow is ignored and removed

Eval cases:

- `每个整点喊我打卡吧` asks for start/end rather than creating reminders.
- Follow-up `从现在到晚上七点` completes the same workflow and creates the
  expected bounded reminders.
- Ordinary chat after a pending workflow does not accidentally execute it.

## Migration Plan

1. Add workflow dataclasses or Pydantic models under the Agent runtime or a
   small shared workflow module.
2. Add workflow persistence helpers over the existing user state field.
3. Extend reminder detector input with the active workflow.
4. Extend `ReminderDetectDecision` to carry optional workflow updates.
5. Persist clarify workflow updates before returning the user-visible question.
6. Teach reminder execution results to emit the shared execution envelope.
7. Add two-turn true-path reminder tests through `business-clawscale`.
8. Rename `pending_task_draft` to `pending_workflow` after compatibility tests
   pass.

## Acceptance Criteria

- Missing reminder details produce a durable pending workflow and a visible
  follow-up question.
- User follow-up can complete the same workflow without relying only on recent
  chat text.
- No phrase-specific parser is introduced for the motivating reminder cases.
- Successful reminder writes return deterministic execution envelopes.
- Existing one-turn reminder CRUD behavior remains intact.
- Normal-path eval includes at least one two-turn clarification case.
