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
- domain parse or execution failures could degrade into generic fallback text
  such as "I could not organize the reply";
- prompts, evals, and traces had no structured execution facts to explain why
  the Interaction Agent's final reply drifted from the domain result.

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
5. what the final user-visible reply should be grounded in.

The Interaction Agent owns the final user-visible text. Domain execution
results make the facts explicit so prompts, model behavior, tests, evals, and
traces can be improved when the reply is poor. Runtime code should not block,
rewrite, or fail closed solely because the final text does not match a
reply expectation.

---

## 3. Non-Goals

- No compatibility layer for `summary`, `visible_summary`, or
  `synthesis_context` as agent-to-agent contract fields.
- No parser that reads facts back out of human-readable text.
- No output-gating repair. Prompts can explain the contract, and tests/evals can
  measure whether the final reply follows it, but runtime delivery does not
  intercept or rewrite Interaction Agent text based on reply expectations.
- No eval loosening before the runtime contract is fixed.
- No generic universal action model. Reminder and Scheduling keep their own
  domain-specific facts while sharing a common result envelope style.
- No removal of `CapabilityResult.visible_summary` for non-domain utility tools
  such as timezone, calendar import, or URL context in this design. This spec
  only replaces the domain-to-Interaction-Agent contract for Reminder and
  Scheduling domain tools.

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

### 4.3 Final Text Has Too Little Structured Grounding

`run_agent_runtime()` currently uses the Interaction Agent's final text when it
is non-empty:

```python
visible_text = final_text or _resolve_visible_text("", captured_tool_results)
```

That ownership is intentional: the Interaction Agent is the user-visible
language owner. The problem is that the model is trying to produce that final
text from text-shaped tool summaries instead of structured domain facts, so bad
or generic wording is hard to prevent through prompt/model improvement and hard
to diagnose after eval failures.

### 4.4 Capability Metadata Is Too Coarse

`metadata["durable_write"]` and
`metadata["requires_response_synthesis"]` are insufficient to express:

- the operation outcome;
- required reply facts;
- missing fields;
- prohibited claims;
- whether the model may rephrase;
- which reply expectations should be used by prompts, tests, evals, and traces.

---

## 5. Target Architecture

```text
Interaction Agent
  -> domain tool call
  -> DomainExecutionResult
     - domain-specific operation facts
     - reply expectations
     - error or safety boundary
  -> Interaction Agent final text
  -> output delivery
```

The domain is the source of execution truth. The Interaction Agent is a
language layer grounded by that truth and owns final user-visible wording. The
runtime transports the final text and captures structured domain facts for
tracing, tests, and evals; it is not a reply-quality gate.

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

Required invariants:

- `executed` has at least one `operations` item with `ok=True`;
- `needs_clarification` has `len(missing_fields) > 0`, `safety_boundary is not None`,
  or both;
- `rejected` has `safety_boundary`;
- `failed` has `error`;
- `no_action` has `operations == ()` — no operations of any kind.

### 6.2 DomainOperationResult

```python
@dataclass(frozen=True)
class DomainOperationResult:
    action: str
    ok: bool
    effect: Literal["none", "read", "write"]
    entity_type: str
    entity_id: str | None
    facts: Mapping[str, Any]
    error: DomainError | None = None
```

`effect` is the shared side-effect classification used by runtime output
rules. `write` means the operation performed a durable mutation, `read` means
it queried domain state without mutation, and `none` means no domain entity was
read or changed. `facts` is domain-specific and structured. It is not display
text.

For a reminder create:

```python
operation = DomainOperationResult(
    action="create",
    ok=True,
    effect="write",
    entity_type="reminder",
    entity_id="rem_123",
    facts={
        "title": "喝水",
        "local_date": "2026-05-22",
        "local_time": "22:06:00",
        "timezone": "Asia/Tokyo",
        "rrule": None,
        "conversation_id": "conv-1",
    },
)
```

For a reminder list:

```python
operation = DomainOperationResult(
    action="list",
    ok=True,
    effect="read",
    entity_type="reminder",
    entity_id=None,
    facts={"count": 2, "reminder_ids": ("rem_1", "rem_2")},
)
```

For a scheduling appointment request:

```python
operation = DomainOperationResult(
    action="request_appointment",
    ok=True,
    effect="write",
    entity_type="appointment_request",
    entity_id="req_123",
    facts={
        "appointment_request_id": "req_123",
        "target_account_id": "acct_provider",
        "consumer_account_id": "acct_consumer",
        "instance_start": "2026-05-23T09:00:00+09:00",
        "instance_end": "2026-05-23T09:30:00+09:00",
        "timezone": "Asia/Tokyo",
    },
)
```

### 6.3 ReplyFactRequirement

```python
@dataclass(frozen=True)
class ReplyFactRequirement:
    path: str          # dot-path into DomainExecutionResult
    label: str | None = None  # optional normalizer key for the resolved value
```

`path` uses zero-based literal indexes, no wildcards. Example:
`"operations[0].facts.title"` resolves to the string value of the first
operation's `title` fact. The only valid path roots in the first implementation
are `operations[N].entity_id`, `operations[N].facts.<key>`, and
`missing_fields[N]`.

### 6.4 ReplyContract

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
    prohibited_claims: tuple[str, ...]  # claim labels resolved by diagnostic config
    allow_rephrase: bool
```

`ReplyContract` is the explicit bridge between execution and language. It
answers: "What should the Interaction Agent communicate to produce a good,
grounded reply?" It is model-facing guidance plus a test/eval expectation, not
a runtime delivery gate.

`required_questions` and `prohibited_claims` are stable labels, not literal
substrings that must appear in model output. Evals and diagnostic checks resolve
them through an explicit phrase-pattern table.

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
)
```

```python
ReplyContract(
    intent="ask_clarification",
    required_facts=(),
    required_questions=("end_time",),
    prohibited_claims=("reminder_created",),
    allow_rephrase=True,
)
```

### 6.5 DomainError

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
- operation `effect`, where `create`, `update`, `cancel`, and `complete` are
  `write`, `list` is `read`, and `none` is `none`;
- missing fields such as `title`, `trigger_at`, `end_time`, `target_reminder`,
  or `advance_offset`;
- safety boundaries such as `high_frequency_requires_end`,
  `date_only_missing_time`, or `ambiguous_target`;
- reply contract requirements.

Reminder must not return display summaries as its execution contract. Optional
reply templates can exist for prompt examples, unit expectations, and eval
diagnostics, but they are not runtime replacements for the Interaction Agent's
final text.

### 7.2 Scheduling

Scheduling execution must report:

- the requested intent and selected scheduling action;
- affected user link, bookable window, request, appointment, or service link;
- target and consumer account ids when relevant;
- previewed time windows or committed appointment times;
- operation `effect`, where existing read-only tools remain `read` and
  state-changing tools are `write`;
- missing role, target account, target appointment, or confirmation fields;
- irreversible-action boundaries and human-confirmation requirements.

The Scheduling Execution Agent may still be an LLM agent, but the selected
scheduling tool result must be converted into `DomainExecutionResult` before it
is returned to the Interaction Agent.

---

## 8. Interaction Agent Contract

The Interaction Agent receives a JSON-serializable view of
`DomainExecutionResult` from each domain tool.

The prompt should tell it:

- treat `operations`, `facts`, `missing_fields`, and `safety_boundary` as
  trusted execution facts;
- follow `reply_contract` when wording the final answer;
- do not claim a write occurred unless `outcome == "executed"` and an operation
  reports `ok=True` with `effect="write"`;
- do not omit required questions;
- do not invent ids, dates, times, recurrence, or confirmation state;
- if unable to complete the requested action, explain the domain failure or ask
  the needed clarification using the structured domain facts.

This prompt guidance is the production control surface for wording quality.
Runtime delivery does not validate and replace the Interaction Agent's final
text based on `reply_contract`.

---

## 9. Runtime Reply Handling And Observability

After the Interaction Agent produces final text, `run_agent_runtime()` delivers
that final text as the user-visible reply when it is non-empty. The domain
execution contract changes what the Interaction Agent sees and what the runtime
records; it does not add a reply-quality interception layer.

Runtime rules:

1. The Interaction Agent's non-empty final text is the output.
2. Domain results are captured as structured facts in runtime traces, metrics,
   manager payloads, and eval evidence.
3. Runtime code does not reject, rewrite, deterministically render over, or
   fail closed solely because final text omits a required fact, misses a
   clarification question, or contains a prohibited claim.
4. Empty final text follows the existing runtime empty-output behavior. This
   spec does not introduce a domain-summary fallback or deterministic domain
   renderer for empty output.
5. Phrase-pattern checks for `required_facts`, `required_questions`, and
   `prohibited_claims` belong in unit tests, eval tooling, trace analysis, and
   prompt/model iteration, not production output gating.

For multi-domain turns, the Interaction Agent receives all
`DomainExecutionResult` values and still owns one final user-visible reply.
Failures to integrate multiple domain results are eval or model-quality issues,
not runtime delivery failures.

---

## 10. Reference Reply Templates

Reference reply templates exist for prompt examples, focused unit expectations,
and eval diagnostics. They do not replace the Interaction Agent's final text at
runtime.

Renderer examples:

- executed reminder create:
  `已创建提醒：{title}（{local_date} {local_time}）`
- high-frequency reminder missing end time:
  `{title}要持续到什么时候结束？请告诉我截止时间。`
- missing target reminder:
  `要{action_text}哪条提醒？请告诉我提醒名称。`
- scheduling no target account:
  `你想对哪个对象执行这个预约操作？请告诉我目标账号或链接。`

Templates read typed facts only. They do not parse model text, and they are not
used as production output repair.

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
- optional reference-template helpers for tests, prompts, and eval diagnostics

### 11.2 Reminder Intent Port, Tool, And Executor

Change reminder execution so the actual reminder objects are preserved.

Required direction:

- `ReminderIntentPort.run()` returns `DomainExecutionResult` for execution,
  clarification, no-action, rejection, and failure paths. `_run_port()` in
  `execution_agents.py` is currently typed `-> CapabilityResult`; update its
  return annotation to `DomainExecutionResult | CapabilityResult` or call the
  reminder port directly in `run_reminder_domain()` without `_run_port()`.
- `visible_reminder_tool` must return a structured dict containing the created or
  affected `Reminder` object(s) (and any error details) instead of a formatted
  display `str`. `ReminderCommandExecutor` builds `DomainOperationResult` from
  this structured return — it must not parse reminder facts out of display text.
- `_execute_one()` returns a `DomainOperationResult` instead of
  `(summary, timed_write)`;
- batch operations return one operation result per selected operation;
- `ReminderCommandExecutor.execute()` returns `DomainExecutionResult` for
  the actual command path, not `CapabilityResult`;
- reminder-specific clarifications become
  `DomainExecutionResult(outcome="needs_clarification", ...)`.

### 11.3 Scheduling Domain

Convert `SchedulingCapabilityPort` results into `DomainExecutionResult`.

Scheduling read-only operations can use `intent="direct_answer"` or a
`DomainExecutionResult(outcome="executed")` containing a
`DomainOperationResult(effect="read", ...)`.
State-changing operations require `confirm_execution` reply contracts. If the
Scheduling Execution Agent calls no scheduling tool, convert that condition to
`DomainExecutionResult(outcome="failed", error=DomainError(code="no_tool_called",
...))` instead of returning a loose error dictionary.

### 11.4 Agent Runtime

Replace `tool_results: list[CapabilityResult]` as the only execution capture
with explicit domain results. In `AgentRunResult` (defined in
`agent/agno_agent/runtime/result.py`), rename `tool_results` to
`capability_results` and add `domain_results`:

```python
domain_results: Sequence[DomainExecutionResult]   # new — one per domain tool call
capability_results: Sequence[CapabilityResult]    # renamed from tool_results — non-domain utility tools only
```

Update every read of `AgentRunResult.tool_results` in `agent_runtime.py` and
other callers to use `capability_results`. `AgentRunResult` must preserve both
collections so timeout, metrics, trace, and manager payloads do not have to
parse domain facts back out of utility `CapabilityResult` objects.

`run_agent_runtime()` visible-output selection must use:

1. Interaction Agent final text as the user-visible output when non-empty;
2. utility capability visible behavior only for non-domain tools, preserving
   the existing utility-tool boundary;
3. structured domain results in trace, metrics, manager payloads, and eval
   evidence;
4. no domain-result-based output rewrite, deterministic render replacement, or
   fail-closed reply-quality gate.

### 11.5 Remove Summary-Based Tool Result Recording

`visible_reminder_tool` currently calls `append_tool_result(...,
result_summary=<formatted str>)` for both success and failure paths. Remove
`result_summary` as the primary reminder execution contract:

- **Success path**: the tool returns a structured dict with the `Reminder` or
  list of `Reminder` objects (and their ids, titles, schedules, etc.) instead of
  a formatted display string. `ReminderCommandExecutor` reads this dict to build
  `DomainOperationResult.facts`.
- **Failure path**: `append_tool_result` may be retained for error signaling
  only if no other structured error channel exists in the session state; prefer
  replacing it with a structured error dict field the executor reads directly.
- After the change, no production path reads `result_summary` to construct the
  user-visible reply or the domain execution contract.

If transient diagnostic logging is needed, use structured debug or trace fields,
not user-facing summary strings.

---

## 12. Tests And Verification

### Unit Tests

Add focused tests for:

- reminder create result includes id, title, local date, local time, timezone,
  recurrence, and target conversation;
- high-frequency reminder without end condition returns
  `outcome="needs_clarification"` with `missing_fields=("end_time",)`;
- reminder list/query operations return `effect="read"` and do not trigger
  durable-write confirmation rules;
- Interaction Agent final text is preserved as the runtime output even when a
  diagnostic check would flag omitted facts;
- diagnostic checks can flag a final text that claims creation during
  clarification without changing delivered output;
- `prohibited_claims` labels are resolved through phrase patterns rather than
  searched as literal labels;
- scheduling state-changing operations produce `confirm_execution` contracts;
- scheduling no-tool-called returns a typed failed domain result instead of a
  loose dict;
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
- Tests, evals, and diagnostics compare Interaction Agent final text against
  domain reply contracts; production delivery does not.
- Interaction Agent final text remains the user-visible output; domain results
  never trigger deterministic rewrite or fail-closed reply-quality interception.
- Read-only domain operations do not trigger durable-write confirmation rules.
- The known regression cases no longer produce generic fallback replies.
- The reminder normal-path eval failures are triaged into genuine runtime
  failures versus repaired scorer/date expectations.
- Canonical architecture docs match the implemented runtime.

---

## 15. Initial Diagnostic Semantics

**`required_facts`**: diagnostics start deterministic and literal. The resolver
walks the `path` on `DomainExecutionResult`, converts the value to its string
representation, and checks that the string (or a synonym from a small explicit
table) appears in the final text. Example synonyms: `"22:06"` matches
`"22:06:00"`; `"喝水"` matches `"喝水"` verbatim.

**`required_questions`**: diagnostic checks resolve each question label in
`required_questions` to a configured set of phrase patterns. Example:
`"end_time"` maps to patterns such as `"截止时间"` and
`"什么时候结束"`. At least one pattern for each label must appear in the final
text.

**`prohibited_claims`**: diagnostic checks resolve each claim label in
`prohibited_claims` to a configured set of phrase patterns. Example:
`"reminder_created"` maps to creation-confirmation phrases such as
`"已创建提醒"` and `"已设好提醒"`. The label itself is never treated as the text
to search for.

**Phrase-pattern table location**: both label-to-pattern mappings (`required_questions`
and `prohibited_claims`) live in a single dedicated module:

```text
agent/agno_agent/runtime/diagnostic_patterns.py
```

That module exports two plain Python dicts: `QUESTION_PATTERNS: dict[str, tuple[str,
...]]` and `CLAIM_PATTERNS: dict[str, tuple[str, ...]]`. Diagnostic helpers and
eval tooling import from this module. No config file, no YAML — just Python.

Do not introduce an LLM judge into production runtime delivery. LLM-based
judging belongs in eval tooling and prompt/model iteration, not output gating.
