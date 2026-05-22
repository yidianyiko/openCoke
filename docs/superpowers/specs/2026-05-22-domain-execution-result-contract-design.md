# Domain Execution Result Contract Design

**Date:** 2026-05-22  
**Status:** Draft — approved direction, implementation plan pending  
**Author:** YDYK + Codex

---

## 1. Problem Statement

The multi-agent runtime split introduced an Interaction Agent that routes user
turns to domain tools such as `reminder_domain` and `scheduling_domain`. That
shape is correct, but the data crossing the agent boundary is not strong
enough.

The current domain tool result is a loose dictionary derived from
`CapabilityResult`: `name`, `ok`, `content`, `visible_summary`,
`synthesis_context`, and `error`. For reminder execution, the actual created
reminder object is flattened into a formatted text string before it reaches
the Interaction Agent. The Interaction Agent can see text about an execution,
but not the execution facts or the reply constraints that make the text
correct.

This caused real normal-path eval regressions after the multi-agent routing
change:

- successful writes could be rephrased into replies that the scorer could not
  verify;
- high-frequency reminder clarifications could lose the required end-condition
  question;
- domain parse or validation failures could degrade into generic fallback text
  such as "I could not organize the reply";
- the runtime had no structured way to decide whether the Interaction Agent's
  final reply was faithful to the domain execution.

The root issue is architectural: **agent-to-agent data is currently text-shaped
instead of fact-shaped**.

---

## 2. Design Goal

Replace summary-based agent communication with a typed domain execution
contract.

The Interaction Agent should receive:

1. what the domain actually did;
2. which durable entities were created, changed, or queried;
3. what information is missing if execution cannot proceed;
4. which safety boundary or policy blocked execution;
5. what the final user-visible reply is required to communicate.

The Interaction Agent may phrase the reply naturally, but it must not invent,
omit, or contradict domain facts. Runtime code performs final contract
validation before any reply is delivered.

---

## 3. Non-Goals

- No compatibility layer for `summary`, `visible_summary`, or
  `synthesis_context` as agent-to-agent contract fields.
- No parser that reads facts back out of human-readable text.
- No prompt-only repair. Prompts can explain the contract, but the contract is
  enforced by typed structures and runtime validation.
- No eval loosening before the runtime contract is fixed.
- No generic universal action model. Reminder and Scheduling keep their own
  domain-specific facts while sharing a common result envelope style.

---

## 4. Current Failure Points

### 4.1 Domain Envelopes Are Loose Dictionaries

`agent/agno_agent/runtime/execution_agents.py` currently converts
`CapabilityResult` into a dict:

```python
{
    "name": result.name,
    "ok": result.ok,
    "content": dict(result.content),
    "visible_summary": result.visible_summary,
    "synthesis_context": result.synthesis_context,
    "error": result.error,
}
```

That envelope does not say whether the domain result is an executed write, a
clarification, a safe rejection, a no-op, or a failure. It also does not say
who owns the final reply.

### 4.2 Reminder Facts Are Flattened Into Text

The visible reminder tool creates or mutates reminder objects, but returns only
formatted text such as:

```text
已创建提醒：喝水（2026-05-22 22:06）
```

`ReminderCommandExecutor` then keeps that text in `CapabilityResult.content`.
The created reminder id, title, local date, local time, timezone, recurrence,
and target conversation are not propagated as structured execution facts.

### 4.3 Runtime Lets Final Text Override Domain Truth

`run_agent_runtime()` currently prefers the Interaction Agent's final text when
it is non-empty:

```python
visible_text = final_text or _resolve_visible_text("", captured_tool_results)
```

This makes the outer model the effective owner of final user-visible truth,
even after a domain has performed a durable write or selected a safety
clarification.

### 4.4 Capability Metadata Is Too Coarse

`metadata["durable_write"]` and
`metadata["requires_response_synthesis"]` are insufficient to express:

- the operation outcome;
- required reply facts;
- missing fields;
- prohibited claims;
- whether the model may rephrase;
- whether the runtime should reject or deterministically render on violation.

---

## 5. Target Architecture

```text
Interaction Agent
  -> domain tool call
  -> DomainExecutionResult
     - domain-specific operation facts
     - reply contract
     - error or safety boundary
  -> Interaction Agent final text
  -> runtime reply contract validator
  -> output delivery
```

The domain is the source of execution truth. The Interaction Agent is a
language layer constrained by that truth. The runtime is the final gate.

---

## 6. Core Types

### 6.1 DomainExecutionResult

```python
@dataclass(frozen=True)
class DomainExecutionResult:
    domain: Literal["reminder", "scheduling"]
    outcome: Literal[
        "executed",
        "needs_clarification",
        "no_action",
        "rejected",
        "failed",
    ]
    operations: tuple[DomainOperationResult, ...]
    missing_fields: tuple[str, ...]
    safety_boundary: str | None
    reply_contract: ReplyContract
    error: DomainError | None = None
```

`outcome` is the first-class interpretation of the result. Consumers should not
infer outcome from text, `ok`, or missing fields.

### 6.2 DomainOperationResult

```python
@dataclass(frozen=True)
class DomainOperationResult:
    action: str
    ok: bool
    entity_type: str
    entity_id: str | None
    facts: Mapping[str, Any]
    error: DomainError | None = None
```

`facts` is domain-specific and structured. It is not display text.

For a reminder create:

```python
facts = {
    "title": "喝水",
    "local_date": "2026-05-22",
    "local_time": "22:06:00",
    "timezone": "Asia/Tokyo",
    "rrule": None,
    "conversation_id": "conv-1",
}
```

For a scheduling appointment request:

```python
facts = {
    "appointment_request_id": "req_123",
    "target_account_id": "acct_provider",
    "consumer_account_id": "acct_consumer",
    "instance_start": "2026-05-23T09:00:00+09:00",
    "instance_end": "2026-05-23T09:30:00+09:00",
    "timezone": "Asia/Tokyo",
}
```

### 6.3 ReplyContract

```python
@dataclass(frozen=True)
class ReplyContract:
    intent: Literal[
        "confirm_execution",
        "ask_clarification",
        "report_no_target",
        "report_rejection",
        "report_failure",
        "direct_answer",
    ]
    required_facts: tuple[ReplyFactRequirement, ...]
    required_questions: tuple[str, ...]
    prohibited_claims: tuple[str, ...]
    allow_rephrase: bool
    violation_action: Literal["render_deterministic", "fail_closed"]
```

`ReplyContract` is the explicit bridge between execution and language. It
answers: "What must the final reply communicate to be true?"

Examples:

```python
ReplyContract(
    intent="confirm_execution",
    required_facts=(
        ReplyFactRequirement(path="operations[0].facts.title"),
        ReplyFactRequirement(path="operations[0].facts.local_time"),
    ),
    required_questions=(),
    prohibited_claims=("not_created", "needs_more_info"),
    allow_rephrase=True,
    violation_action="render_deterministic",
)
```

```python
ReplyContract(
    intent="ask_clarification",
    required_facts=(),
    required_questions=("end_time",),
    prohibited_claims=("reminder_created",),
    allow_rephrase=True,
    violation_action="render_deterministic",
)
```

### 6.4 DomainError

```python
@dataclass(frozen=True)
class DomainError:
    code: str
    message: str
    retryable: bool
    detail: Mapping[str, Any]
```

Errors are structured. The Interaction Agent should not classify errors from
free-text exception messages.

---

## 7. Domain-Specific Result Requirements

### 7.1 Reminder

Reminder execution must report:

- action: `create`, `update`, `cancel`, `complete`, `list`, or `none`;
- outcome: executed, needs clarification, no action, rejected, or failed;
- written or affected reminders with id, title, schedule, timezone, recurrence,
  lifecycle state, and target conversation;
- missing fields such as `title`, `trigger_at`, `end_time`, `target_reminder`,
  or `advance_offset`;
- safety boundaries such as `high_frequency_requires_end`,
  `date_only_missing_time`, or `ambiguous_target`;
- reply contract requirements.

Reminder must not return display summaries as its execution contract. A
deterministic renderer can generate text from `DomainExecutionResult` when the
Interaction Agent reply violates the contract.

### 7.2 Scheduling

Scheduling execution must report:

- the requested intent and selected scheduling action;
- affected user link, bookable window, request, appointment, or service link;
- target and consumer account ids when relevant;
- previewed time windows or committed appointment times;
- whether the action was read-only or state-changing;
- missing role, target account, target appointment, or confirmation fields;
- irreversible-action boundaries and human-confirmation requirements.

The Scheduling Execution Agent may still be an LLM agent, but its final output
is not trusted as user-visible text. The selected scheduling tool result must
be converted into `DomainExecutionResult`.

---

## 8. Interaction Agent Contract

The Interaction Agent receives a JSON-serializable view of
`DomainExecutionResult` from each domain tool.

The prompt should tell it:

- treat `operations`, `facts`, `missing_fields`, and `safety_boundary` as
  trusted execution facts;
- satisfy `reply_contract` exactly;
- do not claim a write occurred unless `outcome == "executed"` and an operation
  reports `ok=True`;
- do not omit required questions;
- do not invent ids, dates, times, recurrence, or confirmation state;
- if unable to phrase the answer, return an empty final text rather than a
  generic apology.

This prompt guidance is secondary. Runtime validation is authoritative.

---

## 9. Runtime Reply Validation

After the Interaction Agent produces final text, `run_agent_runtime()` validates
it against every `DomainExecutionResult.reply_contract`.

Rules:

1. `confirm_execution` requires all `required_facts` to appear or be
   semantically represented.
2. `ask_clarification` requires each `required_questions` field to be asked.
3. `prohibited_claims` must not appear.
4. Durable writes cannot be reported as tentative.
5. Clarifications cannot claim that an entity was created.
6. Failures cannot be rephrased as success.

If validation passes, the runtime may deliver the Interaction Agent's final
text. If validation fails:

- `violation_action == "render_deterministic"`: render a deterministic reply
  from `DomainExecutionResult`;
- `violation_action == "fail_closed"`: return an empty output with a structured
  runtime error disposition.

There is no fallback to `summary` or `visible_summary`.

---

## 10. Deterministic Rendering

Deterministic rendering exists for safety and contract repair, not as the
primary conversation style.

Renderer examples:

- executed reminder create:
  `已创建提醒：{title}（{local_date} {local_time}）`
- high-frequency reminder missing end time:
  `{title}要持续到什么时候结束？请告诉我截止时间。`
- missing target reminder:
  `要{action_text}哪条提醒？请告诉我提醒名称。`
- scheduling no target account:
  `你想对哪个对象执行这个预约操作？请告诉我目标账号或链接。`

The renderer reads typed facts only. It does not parse model text.

---

## 11. Required Code Changes

### 11.1 New Runtime Types

Add a new runtime module, for example:

```text
agent/agno_agent/runtime/domain_results.py
```

It owns:

- `DomainExecutionResult`
- `DomainOperationResult`
- `ReplyContract`
- `ReplyFactRequirement`
- `DomainError`
- JSON conversion helpers
- deterministic render helpers or renderer interfaces

### 11.2 Reminder Tool And Executor

Change reminder execution so the actual reminder objects are preserved.

Required direction:

- `_execute_one()` returns structured operation results instead of
  `(summary, timed_write)`;
- batch operations return one operation result per selected operation;
- `ReminderCommandExecutor.execute()` returns a reminder-domain result or a
  typed reminder operation bundle, not `CapabilityResult`;
- reminder-specific clarifications become
  `DomainExecutionResult(outcome="needs_clarification", ...)`.

### 11.3 Scheduling Domain

Convert `SchedulingCapabilityPort` results into `DomainExecutionResult`.

Scheduling read-only operations can use `intent="direct_answer"` or a
domain-specific read outcome. State-changing operations require
`confirm_execution` reply contracts.

### 11.4 Agent Runtime

Replace `tool_results: list[CapabilityResult]` as the only execution capture
with explicit domain results:

```python
domain_results: list[DomainExecutionResult]
capability_results: list[CapabilityResult]  # only for non-domain utility tools
```

`run_agent_runtime()` visible-output selection must use:

1. domain reply contract validation;
2. deterministic domain renderer when configured;
3. utility capability visible behavior only for non-domain tools;
4. final text only when no domain contract constrains the reply.

### 11.5 Remove Summary-Based Tool Result Recording

Remove `append_tool_result(... result_summary=...)` as a reminder execution
contract. If transient diagnostic logging is needed, use structured debug or
trace fields, not user-facing summary strings.

---

## 12. Tests And Verification

### Unit Tests

Add focused tests for:

- reminder create result includes id, title, local date, local time, timezone,
  recurrence, and target conversation;
- high-frequency reminder without end condition returns
  `outcome="needs_clarification"` with `missing_fields=("end_time",)`;
- Interaction Agent final text that omits required facts is replaced by the
  deterministic renderer;
- Interaction Agent final text that claims creation during clarification is
  rejected or rendered deterministically;
- scheduling state-changing operations produce `confirm_execution` contracts;
- no code path reads `summary`, `visible_summary`, or `synthesis_context` from
  domain results.

### Runtime/Eval Tests

Use the known regression cases as focused gates:

- case 7: English relative reminder creation should preserve executed facts;
- case 12: approximate-time reminder creation should preserve title and time;
- case 18: concrete start-time reminder should not fall to generic apology;
- case 19/21/27: unbounded hourly reminders must ask for end condition;
- case 22: relative delay reminder should not fall to generic apology.

Then run the 30-case reminder normal-path eval with local Mongo and PM2 worker.

### Eval Rule Repair After Runtime Fix

Only after the runtime contract is in place:

- allow natural confirmations that are backed by structured created-reminder
  facts;
- make expected local dates dynamic relative to replay timestamp;
- keep high-frequency end-condition expectations strict.

---

## 13. Documentation Updates Required During Implementation

Implementation changes the runtime protocol shape and ownership boundary. The
same change set must update:

- `docs/ARCHITECTURE.md` turn-processing pipeline;
- `docs/design-docs/agent-capability-contract.md` if the shared contract rule
  needs to name domain execution results explicitly;
- any tests or docs that still describe `CapabilityResult.visible_summary` as
  the domain-to-interaction contract.

---

## 14. Acceptance Criteria

- Domain tools no longer return or require `summary`, `visible_summary`, or
  `synthesis_context` as agent-to-agent contract fields.
- Reminder and Scheduling domain calls return typed execution facts plus reply
  contracts.
- Runtime validates Interaction Agent final text against domain reply
  contracts.
- Contract violations use deterministic rendering or fail closed according to
  `ReplyContract.violation_action`.
- The known regression cases no longer produce generic fallback replies.
- The reminder normal-path eval failures are triaged into genuine runtime
  failures versus repaired scorer/date expectations.
- Canonical architecture docs match the implemented runtime.

---

## 15. Open Implementation Choice

`ReplyContract.required_facts` validation can start deterministic and literal
for the first implementation: title, local date, local time, and required
question labels must appear in text or map to a small explicit synonym table.

Do not introduce an LLM judge into runtime contract validation. LLM-based
judging belongs in eval tooling, not production reply gating.
