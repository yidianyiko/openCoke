# Coke Agent Runtime Redesign

**Status:** closed early; not approved for implementation
**Original date:** 2026-04-30
**Rewritten:** 2026-05-01
**Closed:** 2026-05-01
**Surfaces:** `agent/agno_agent/`, `agent/runner/agent_handler.py`,
`agent/runner/reminder_event_handler.py`,
`agent/runner/deferred_action_executor.py`, `agent/prompt/`
**Out of scope:** `gateway/`, `connector/clawscale_bridge/`, reminder durable
storage schema, persona migration to `agno.skills`, Phase 2 TOB ingress

**References:**

- `docs/architecture.md`
- `docs/roadmap.md`
- `docs/design-docs/coke-working-contract.md`
- `docs/fitness/coke-verification-matrix.md`
- `docs/superpowers/specs/2026-04-28-reminder-system-design.md`
- `tasks/2026-04-23-poke-architecture-reconstruction.md`
- Agno 2.5.9 local source under `.venv/lib/python3.12/site-packages/agno/`
- Agno Teams documentation
- Anthropic "Building effective agents" and "Writing effective tools"
- OpenAI practical agent guide
- LangGraph durable execution documentation

## Closure Note

This spec is intentionally ended early. It should be treated as design research
and a possible future reference, not as an active execution plan.

Do not continue implementation from this document as-is. If Coke later resumes
agent-runtime replacement work, open a new smaller spec with a fresh scope,
explicit acceptance criteria, and current verification evidence.

Known reason for closure:

- the active work had drifted beyond the reminder-detect rollback baseline
- the remaining problems are runtime reliability and eval-scope questions, not a
  single coherent Agent Team implementation task
- continuing this spec would encourage a broad rewrite before the smaller
  reminder/runtime risks are bounded

## Summary

This redesign replaces Coke's current
`PrepareWorkflow -> StreamingChatWorkflow -> PostAnalyzeWorkflow` turn pipeline
with a **typed Agent Runtime boundary** and an **Agno manager core**.

The key architectural choice is not "Agno Team owns everything." The key choice
is:

```text
Runner owns reliability.
Agent Runtime owns semantic execution.
Capability ports own side effects.
Domain systems own durable state.
```

Agno `Team` is used inside the Agent Runtime as a manager/leader pattern:

- the leader is the only user-facing agent
- members and ports provide narrow capabilities
- durable writes happen through deterministic Python adapters
- `Team.session_state` is not the Coke source of truth

This is a destructive replacement of the old agent workflow stack, but it is not
a rewrite of gateway, bridge, reminder storage, or deployment topology.

## Why

`PrepareWorkflow`, `OrchestratorAgent`, and `StreamingChatWorkflow` have become
the largest source of maintenance pain in the LLM stack:

- `OrchestratorAgent` makes a serial LLM call before every reply, even for
  trivial greetings.
- Routing is split between LLM flags such as `need_X` and Python helpers such as
  `_should_run_reminder_detect`.
- Context, tool results, search results, timezone state, reminder flags, direct
  replies, and prompt inputs are passed through one mutable `session_state`
  dictionary.
- `PrepareWorkflow` mixes semantic routing, retrieval, reminder detection, URL
  extraction, timezone writes, and calendar-import entrypoint handling.
- `StreamingChatWorkflow` depends on many implicit keys produced by
  `PrepareWorkflow`, which makes small changes hard to reason about.
- New capabilities tend to add another `need_X` field to
  `OrchestratorResponse`.

Coke is pre-production enough that destructive cleanup is acceptable. The
redesign should delete the old implicit pipeline instead of preserving it behind
compatibility shims.

## Design Inputs

### Poke Reference

The Poke reconstruction archive points to a stable lesson:

```text
user-facing interaction layer
    -> execution layer
    -> durable automation / integrations
```

The useful part for Coke is the boundary, not Poke's full product scope.
Coke should borrow:

- user-facing layer separate from execution
- execution results synthesized by one persona-bearing layer
- background automation as durable runtime, not turn-local context
- formal event ingress
- integrations/control-plane state separate from turn execution

Coke should not copy:

- a generic consumer-platform shell before Phase 2 needs it
- prompt wording or "single entity" illusion as architecture
- long-lived execution agents before there is a concrete work-thread product
  need

### Agno Reference

Agno `Team` is appropriate when several specialized agents need narrower context
and a leader must synthesize their outputs. Agno coordinate mode delegates work
through `delegate_task_to_member`, then the leader synthesizes the results.

This is useful for Coke's semantic core, but it has costs:

- each delegated member can add an LLM hop
- streaming events include leader events, member events, tool events, and final
  content
- member session state is copied, not a durable domain boundary
- delegation is model-decided, so it should not be the only guard around writes

Therefore Agno Team should be a semantic orchestration primitive, not Coke's
runtime state container.

### Industry Practice

The external best-practice pattern is consistent:

- use the simplest agent/workflow shape that solves the task
- use deterministic workflows for predictable control flow
- use agents only where model judgment is actually needed
- keep tools narrow, well-described, and high signal
- keep irreversible or durable side effects behind explicit tool/adapter
  boundaries
- make long-running or retryable side effects idempotent and traceable

For Coke this means:

- natural-language understanding and final wording belong in the LLM layer
- reminder writes, timezone writes, output commits, locks, and retries belong in
  deterministic code
- every boundary between runner, agent, and domain systems should be typed

## Goals

1. Replace `PrepareWorkflow`, `OrchestratorAgent`,
   `OrchestratorResponse`, and `StreamingChatWorkflow` with a typed Agent
   Runtime and Agno manager core.
2. Keep `agent/runner/` responsible for queueing, locks, batching, rollback,
   output writes, and PostAnalyze scheduling.
3. Make the runner-to-agent contract explicit:
   `AgentInput -> AgentRunContext -> AgentRunResult`.
4. Use Agno Team only for semantic delegation and user-facing synthesis.
5. Keep the leader as the only user-facing LLM.
6. Keep reminder side effects behind a deterministic
   `ReminderCommandExecutor`.
7. Preserve the reminder evaluation baseline at every migration gate.
8. Leave `gateway/` and `clawscale_bridge/` untouched.

## Non-Goals

- Changing gateway, bridge, or any external delivery path.
- Changing the Reminder System durable schema.
- Replacing the Reminder System command/fired-event protocols.
- Migrating persona/character prompts to `agno.skills`.
- Building a Coke-owned TOB control plane in this phase.
- Building long-lived execution-agent identity.
- Making every capability an Agno member.
- Moving Coke runtime truth into Agno `Team.session_state`.

## Architecture

### Big Picture

```text
Channels / Gateway / Bridge
        |
        v
Mongo inputmessages / runtime events
        |
        v
+------------------------------------------------+
| agent/runner/                                  |
| Deterministic Runtime Shell                    |
|                                                |
| - queue polling / Redis wakeups                |
| - conversation locks                           |
| - input batching                               |
| - context_prepare                              |
| - new-message rollback                         |
| - outputmessages writes                        |
| - PostAnalyze scheduling                       |
+-----------------------+------------------------+
                        |
                        | AgentInput
                        v
+------------------------------------------------+
| AgentRuntime Adapter                           |
|                                                |
| - builds AgentRunContext                       |
| - selects legacy/team runtime                  |
| - applies timeout / guardrails / tracing       |
| - converts AgentRunResult to runner output     |
+-----------------------+------------------------+
                        |
                        v
+------------------------------------------------+
| Agno Manager Core                              |
|                                                |
|  Leader / Manager                              |
|  - Coke persona                                |
|  - user-visible response                       |
|  - semantic task planning                      |
|  - synthesis of capability results             |
|                                                |
|  Capability ports / members                    |
|  - ContextPort                                 |
|  - ReminderIntentMember                        |
|  - SearchPort                                  |
|  - TimezonePort                                |
|  - URLContextPort                              |
+-----------------------+------------------------+
                        |
                        | IntentAndDraftResult
                        v
+------------------------------------------------+
| Post-Team Deterministic Adapters               |
|                                                |
| - ReminderCommandExecutor                      |
| - DeferredActionFireResult mapper              |
| - output disposition mapper                    |
+-----------------------+------------------------+
                        |
                        | AgentRunResult
                        v
+------------------------------------------------+
| agent/runner/ output boundary                  |
|                                                |
| - stream or write visible messages             |
| - renew / release locks                        |
| - record metrics                               |
| - schedule background PostAnalyze              |
+------------------------------------------------+
```

### Layer 1: Deterministic Runtime Shell

`agent/runner/` remains the reliability boundary.

It owns:

- message acquisition from `inputmessages`
- Redis stream wake-up behavior
- conversation lock acquisition, renewal, validation, and release
- batching pending messages for the same conversation
- `context_prepare`
- current-message exclusion during new-message checks
- rollback when newer user messages arrive
- output writing to `outputmessages`
- ClawScale sync-reply first-text behavior
- fallback output when the agent returns no visible content
- background `PostAnalyzeWorkflow` scheduling

It must not own:

- semantic routing
- prompt-specific context assembly
- reminder natural-language interpretation
- search query planning
- user-facing persona generation

The old `handle_message()` should be thinned into a runner shell that calls
`AgentRuntime.handle(input, context)`.

### Layer 2: AgentRuntime Adapter

The adapter is the typed boundary between runner code and the Agno manager core.

New package:

```text
agent/agno_agent/runtime/
  __init__.py
  inputs.py
  context.py
  result.py
  selector.py
  team_runtime.py
  streaming.py
  trace.py
```

Core types:

```python
@dataclass
class AgentInput:
    input_type: Literal[
        "user.turn",
        "reminder.fire",
        "deferred_action.fire",
        "system.event",
    ]
    conversation_id: str
    text: str | None
    payload: UserTurnPayload | ReminderFirePayload | DeferredActionPayload | dict
    occurred_at: datetime


@dataclass
class AgentRunContext:
    user: TrustedUserContext
    character: TrustedCharacterContext
    conversation: TrustedConversationContext
    relation: TrustedRelationContext
    platform: str
    recent_chat_history: str
    current_time: datetime
    runtime_metadata: dict


@dataclass
class AgentRunResult:
    visible_messages: list[VisibleMessage]
    post_analyze_input: dict | None
    tool_results: list[CapabilityResult]
    metrics: dict
    trace: dict
    content_blocked: bool = False
    rollback: bool = False


@dataclass
class VisibleMessage:
    message_type: Literal["text", "voice", "photo"]
    content: str
    emotion: str | None = None
    metadata: dict | None = None


@dataclass
class RuntimeErrorDisposition:
    code: str
    retryable: bool
    user_visible_fallback: str | None


@dataclass
class OutputDisposition:
    status: Literal["ok", "empty", "content_blocked", "rollback", "failed"]
    output_references: list[str]
    error: RuntimeErrorDisposition | None = None
```

`AgentInput` replaces the old `message_source` string plus ad hoc
`system_message_metadata`. It is intentionally more general than the old draft's
`PushEvent`:

- user turns are inputs
- fired reminders are inputs
- deferred follow-up activations are inputs
- future TOB/system events can become inputs without inventing another pathway

### Layer 3: Agno Manager Core

The manager core uses Agno `Team` in coordinate mode for turns that need LLM
semantic delegation.

Leader responsibilities:

- hold the Coke persona and texting style
- decide whether a capability is needed
- delegate to narrow members when model judgment is useful
- request typed capability results through the runtime wrapper
- synthesize all capability results into the final user-visible message
- hide internal tool/member names from the user

Leader non-responsibilities:

- write reminder documents
- choose trusted `owner_user_id`
- choose `agent_output_target`
- write `outputmessages`
- own conversation locks
- own rollback decisions
- persist runtime state
- call durable write adapters directly

Model requirement:

- leader must use a GPT/Claude-tier model until a cheaper model proves equivalent
  on delegation accuracy, response quality, structured-result handling, and
  latency
- DeepSeek can still be used for narrow structured members where evals prove it
  is reliable

### Layer 4: Capability Ports

Capabilities are not all agents. A capability can be:

- deterministic Python port
- Agno member agent
- existing tool wrapper
- domain-system adapter

The default rule:

```text
Use an Agno member only when natural-language judgment or synthesis is required.
Use a deterministic port when the task is stable, typed, or side-effectful.
```

Durable write adapters are not exposed as Agno Team tools. In particular,
`ReminderCommandExecutor` is a post-Team adapter:

```text
Leader / ReminderIntentMember
    -> ReminderDetectDecision
    -> AgentRuntime validates the decision
    -> ReminderCommandExecutor executes through Reminder System
    -> leader receives a typed command result for final wording
```

This prevents model-selected Team tools from becoming the guard around durable
reminder writes.

#### ContextPort

Owns context assembly for the leader.

It replaces the old `context_retrieve` dict and prompt-specific formatter
coupling.

Behavior:

- always provides deterministic base context:
  - current user
  - character
  - relation
  - conversation summary / recent history
  - current time and timezone state
  - confirmed active reminders summary
- optionally runs semantic retrieval for:
  - user profile
  - character setting
  - character knowledge
  - relevant chat history
  - URL content

The first implementation should keep retrieval conservative. It should not give
a free `memory_agent` authority to skip context that existing prompts rely on.

#### ReminderIntentMember

Owns natural-language reminder intent detection only.

Input:

- current user message
- recent conversation context
- current time
- user timezone
- reminder few-shot examples

Output:

- `ReminderDetectDecision`

It must not:

- call the Reminder System directly
- write Mongo documents
- choose trusted owner or output target
- produce final user-facing text

This preserves the current good property of `ReminderDetectAgent`: LLM produces
a structured decision, then deterministic code executes it.

#### ReminderCommandExecutor

Owns deterministic execution of reminder decisions.

Input:

- `ReminderDetectDecision`
- trusted `AgentRunContext`

Responsibilities:

- derive `owner_user_id` from trusted runtime context
- derive `agent_output_target` from conversation/character/route context
- resolve keyword targets for update/cancel/complete/list where needed
- call the Reminder System command protocol
- convert Reminder System results/errors to `tool_results`
- preserve `reminder_created_with_time`-equivalent semantics for PostAnalyze
  suppression

It is a Python adapter, not an Agno member. It must not be registered in
`Team.tools`, exposed through `delegate_task_to_member`, or callable by model
`tool_choice=auto`.

#### SearchPort

Starts as a deterministic wrapper around `web_search_tool`.

It becomes an Agno member only if search work later requires:

- multi-query planning
- source comparison
- result reranking
- summarization before returning to the leader

#### TimezonePort

Owns timezone update behavior.

The leader may identify a timezone intent, but the port must:

- validate IANA timezone values
- distinguish direct set versus proposal
- preserve confirmation and pending-proposal behavior
- update trusted user state
- return a structured result for final wording

#### URLContextPort

Owns URL detection and URL content extraction.

It should return a typed bundle rather than write `url_context` /
`url_context_str` into a shared dict.

## Reminder Fired Flow

Reminder firing is a reliability path, not a normal chat path.

Default V1 behavior:

```text
Reminder System
    |
    | ReminderFiredEvent
    v
agent/runner/reminder_event_handler.py
    |
    | AgentInput(input_type="reminder.fire")
    v
AgentRuntime Adapter
    |
    v
deterministic reminder renderer
    |
    v
runner output boundary
```

The deterministic renderer may output a simple reminder message using event
fields. It does not need the full Agno leader unless a later product decision
requires persona-heavy reminder wording.

Optional future mode:

```text
ReminderFiredEvent -> Leader renders reminder copy
```

That mode must be feature-gated separately because it adds LLM latency and
failure modes to the reminder delivery path.

Fired-event idempotency must be decided before B.3 exits. The Reminder System
design already allows a crash after output but before post-event persistence,
which can replay the same `fire_id`.

V1 must choose one of these policies explicitly:

- accept duplicate visible reminder output on replay, document it as a known V1
  limitation, and keep the Reminder System state transition simple
- or suppress duplicate output at the Agent System output boundary by checking
  prior `outputmessages.metadata.fire_id`

The preferred policy is duplicate suppression by `fire_id`, with a replay test
that calls the handler twice with the same fired event.

## Deferred Action Flow

`deferred_actions` remains separate from the new Reminder System.

For `deferred_action.fire`, the runtime should distinguish:

- visible legacy user reminder actions, where deterministic rendering may be
  enough until migration removes them
- proactive follow-up actions, where leader generation is appropriate

The executor still owns:

- action lease
- occurrence state
- retry/failure policy
- scheduler reschedule/remove behavior

The Agent Runtime owns only the generated output for actions that require
natural-language generation.

`DeferredActionExecutor` needs an explicit result contract before B.3:

```python
@dataclass
class DeferredActionFireResult:
    status: Literal[
        "succeeded",
        "failed",
        "skipped",
        "content_blocked",
        "rollback",
        "no_output",
    ]
    output_references: list[str]
    retryable: bool
    error_code: str | None = None
    error_message: str | None = None
```

Mapping rules:

- `succeeded`: at least one output was committed and no rollback/blocking
  occurred.
- `content_blocked`: map to failed occurrence unless product policy explicitly
  decides to skip.
- `rollback`: do not mark succeeded; retry or reschedule according to executor
  policy.
- `no_output`: retryable failure unless deterministic skip rules apply.
- partial output with later error: preserve output references and mark according
  to whether the executor can safely retry without duplicate user-visible text.

## State Model

The old system has one overloaded object:

```text
session_state[dict]
```

The new system splits it:

```text
AgentRunContext
    trusted input from runner and DAOs

AgentWorkState
    per-run scratch data inside the manager core

CapabilityResult
    typed result from each port/member

AgentRunResult
    typed output back to runner
```

Agno `Team.session_state` may exist inside `AgentWorkState`, but it is not the
durable Coke context and is not the cross-layer contract.

Team construction invariants:

- no Agno persistent DB for Team session state in this phase
- `add_session_state_to_context=False` unless a specific eval proves it is needed
- `enable_agentic_state=False`
- `cache_session=False`
- no trusted owner, conversation route, reminder target, lock id, or output id is
  stored in cross-run Agno state
- tests must prove a second run cannot inherit trusted routing data from the
  previous run through Team state

Keys that disappear as contracts:

- `orchestrator`
- `query_rewrite`
- `prepare_*`
- `context_retrieve`
- `web_search_result`
- `timezone_update_message`
- `url_context_str`

Their semantics move into typed capability results.

## Streaming Contract

The runner still needs only user-visible messages.

`runtime/streaming.py` filters Agno team events and yields only:

- leader final content deltas
- leader final message completion
- explicit content-blocked/error events mapped to `AgentRunResult`

It must not emit:

- member reasoning
- member intermediate content
- tool-call events
- delegate-task implementation details
- internal traces

The adapter must be tested against mixed streams containing leader events,
member events, tool events, and errors.

## Runtime Selection

Environment variables can only provide process defaults.

Valid selectors:

```text
AGENT_RUNTIME_VERSION=legacy|team   # process default
customer runtime setting            # optional per-customer override
conversation runtime metadata       # optional per-conversation override
test/eval CLI flag                  # test-only override
```

Resolution order:

```text
explicit test/eval override
    -> conversation override
    -> customer override
    -> process env default
    -> legacy
```

The old draft's phrase "per-conversation via env" is invalid and must not be
implemented.

## Reminder System Compatibility

This spec supersedes the Agent System runtime-flow subsection of
`docs/superpowers/specs/2026-04-28-reminder-system-design.md`, where it still
describes the old `OrchestratorAgent -> ReminderDetectAgent ->
visible_reminder_tool -> ChatWorkflow` sequence and explicitly made replacement
of that flow a non-goal for the Reminder System V1 scope.

It does not supersede the Reminder System ownership boundary:

- Reminder System still owns reminder state, schedule semantics, lifecycle, and
  fired-event emission.
- Agent System still owns natural-language understanding and user-visible output.
- Agent System still must not write Mongo reminder documents directly.
- Reminder System still must not call an LLM or write chat output directly.

## File Layout

New:

```text
agent/agno_agent/runtime/
  __init__.py
  inputs.py
  context.py
  result.py
  selector.py
  team_runtime.py
  streaming.py
  trace.py

agent/agno_agent/capabilities/
  __init__.py
  context_port.py
  reminder_intent.py
  search_port.py
  timezone_port.py
  url_context_port.py

agent/agno_agent/adapters/
  __init__.py
  reminder_command_executor.py
  deferred_action_result.py
  output_disposition.py

agent/agno_agent/prompts/
  manager.py
  reminder_intent.py
```

Modified:

- `agent/runner/agent_handler.py`
  - thin `handle_message()` into runtime shell + adapter call
- `agent/runner/reminder_event_handler.py`
  - call Agent Runtime with `AgentInput("reminder.fire")` only when needed
  - keep deterministic output path as default
- `agent/runner/deferred_action_executor.py`
  - call Agent Runtime with `AgentInput("deferred_action.fire")` for generated
    proactive follow-up
- `agent/agno_agent/agents/__init__.py`
  - remove `OrchestratorAgent` at cutover
  - keep or move reusable structured agents
- `agent/prompt/`
  - remove orchestrator prompt entries at cutover
  - preserve persona prompt content unless a separate persona migration changes it
- `agent/agno_agent/workflows/post_analyze_workflow.py`
  - accept typed `post_analyze_input` or a compatibility projection from
    `AgentRunResult`

Deleted at final cutover:

- `agent/agno_agent/workflows/prepare_workflow.py`
- `agent/agno_agent/workflows/chat_workflow_streaming.py`
- `agent/agno_agent/schemas/orchestrator_schema.py`
- orchestrator-specific prompt entries

## Migration Phasing

### Phase B.0 - Typed Boundary Scaffold

No behavior change.

- Add runtime type modules.
- Add runtime selector.
- Add capability result schemas.
- Add tests for type conversion from current runner context to
  `AgentRunContext`.
- Legacy path remains default.

Verification:

```bash
pytest tests/unit/agent/ -v
pytest tests/unit/agent/test_agent_handler.py -v
```

### Phase B.1 - Capability Ports Behind Legacy Flow

Behavior should remain equivalent.

- Extract deterministic ports from `PrepareWorkflow` helpers one at a time:
  - B.1a: context
  - B.1b: reminder executor
  - B.1c: search
  - B.1d: timezone
  - B.1e: URL context
- Keep old `PrepareWorkflow` calling those ports.
- Each port extraction needs fixture or golden-output equivalence tests for the
  affected user-visible behavior.
- Reminder eval baseline must stay unchanged after B.1b and at B.1 exit.

Verification:

```bash
python scripts/eval_reminder_normal_path_cases.py
pytest tests/unit/test_tool_results_context.py -v
pytest tests/unit/agent/test_visible_reminder_protocol_tool.py -v
```

### Phase B.2 - Team Runtime For User Turns

Introduce `AGENT_RUNTIME_VERSION=team` for user turns.

- Build Agno manager core.
- Leader generates final visible response.
- ContextPort supplies typed context bundle.
- ReminderIntentMember emits `ReminderDetectDecision`.
- Runtime adapter validates decisions and calls `ReminderCommandExecutor`
  outside the Team.
- Leader receives the typed reminder command result for final wording.
- Streaming adapter emits only user-visible leader output.
- Legacy remains default.

Exit gate:

- team path matches or beats frozen legacy reminder eval baseline
- user-turn E2E passes on team runtime
- p50/p95 latency is measured and accepted
- sync first-text, rollback/new-message interruption, timeout fallback,
  timezone proposal/update, URL context, calendar-import entry surfacing, and
  empty-output fallback have named acceptance tests

Verification:

```bash
python scripts/eval_reminder_normal_path_cases.py --runtime team
pytest tests/e2e/ -v
pytest tests/unit/agent/ -v
```

### Phase B.3 - Runtime Events

Move runtime events to typed inputs.

- `ReminderFiredEvent` maps to `AgentInput("reminder.fire")`.
- Deterministic reminder renderer is default.
- Proactive deferred actions map to `AgentInput("deferred_action.fire")`.
- `DeferredActionFireResult` maps runtime outcomes to occurrence success,
  retry, skip, or failure.
- fired reminder replay by `fire_id` is tested according to the chosen V1 policy.
- Existing action lease and occurrence behavior stays in
  `DeferredActionExecutor`.

Verification:

```bash
pytest tests/unit/runner/test_reminder_event_handler.py -v
pytest tests/unit/runner/test_deferred_action_executor.py -v
pytest tests/e2e/test_reminder_system_flow.py -v
pytest tests/unit/agent/test_agent_handler.py -v
```

Manual smoke:

- create a reminder on team runtime
- wait for fire or advance time
- confirm output arrives
- confirm Reminder System state advances correctly

### Phase B.4 - Cutover And Deletion

- Default runtime becomes `team`.
- Remove legacy runtime branches.
- Delete `PrepareWorkflow`, `StreamingChatWorkflow`, and
  `OrchestratorResponse`.
- Remove orchestrator prompt entries.
- Keep only typed runtime contracts.

Verification:

```bash
pytest tests/unit/ -v
pytest tests/e2e/ -v
python scripts/eval_reminder_normal_path_cases.py
zsh scripts/check
```

## Evaluation Requirements

Reminder eval is the hard gate because reminder regressions have been the
highest-risk failure mode.

At B.2 entry:

- record the legacy baseline at a frozen commit hash
- store pass count, failed case ids, latency, and model config

At B.2 exit:

- team runtime must match or beat legacy pass count
- failures must be classified as harness issue, routing issue, detector issue,
  executor issue, or fixture mismatch
- no regression can be hidden by changing expected fixtures without evidence

Latency:

- record p50/p95 for trivial chat, reminder creation, reminder update/cancel,
  search-needed turn, and context-heavy turn
- a p95 regression over 20% needs explicit approval or a concrete mitigation

Streaming:

- test leader-only visible output filtering
- test member/tool event suppression
- test empty output fallback
- test content-blocked propagation

## Risks

1. **Leader over-delegation**
   - Coordinate mode can call members for simple turns.
   - Mitigation: leader instructions and evals for trivial chat.

2. **Reminder side-effect drift**
   - If reminder writes move too close to LLM control, evals can regress.
   - Mitigation: `ReminderIntentMember` only decides; runtime adapter executes
     after Team completion and the executor is never registered as a Team tool.

3. **Context under-retrieval**
   - A fully autonomous memory agent may skip context current prompts rely on.
   - Mitigation: deterministic base context plus conservative retrieval.

4. **Streaming leakage**
   - Agno streams include member/tool events.
   - Mitigation: strict event filter with regression tests.

5. **State confusion**
   - `Team.session_state` may tempt future code to store runtime truth there.
   - Mitigation: typed `AgentRunContext` and `AgentRunResult` are the only
     cross-layer contracts.

6. **Deferred-action semantic mismatch**
   - Deferred follow-up and visible reminder actions are different concepts.
   - Mitigation: separate `AgentInput` variants, define
     `DeferredActionFireResult`, and preserve executor policy.

## Decision Rules

- If a task is predictable and side-effectful, implement it as a deterministic
  port.
- If a task requires semantic interpretation, use an LLM member with structured
  output.
- If a task requires final user-visible wording, let the leader synthesize it.
- If a path affects delivery reliability, keep deterministic fallback.
- If a capability has durable state, put that state in its domain system, not in
  Agno session state.

## Final Target Shape

```text
Current:

handle_message()
  -> PrepareWorkflow
       -> OrchestratorAgent
       -> context_retrieve_tool
       -> web_search_tool
       -> timezone helpers
       -> URL extraction
       -> ReminderDetectAgent
       -> visible_reminder_tool
  -> StreamingChatWorkflow
  -> PostAnalyzeWorkflow


Target:

runner shell
  -> AgentRuntime Adapter
       -> AgentInput / AgentRunContext
       -> Agno Manager Core
            -> Leader
            -> ContextPort
            -> ReminderIntentMember
            -> SearchPort
            -> TimezonePort
            -> URLContextPort
       -> Post-Team deterministic adapters
            -> ReminderCommandExecutor
            -> DeferredActionFireResult mapper
       -> AgentRunResult
  -> runner output boundary
  -> PostAnalyzeWorkflow
```

This target keeps the useful Poke-style interaction/execution split, uses Agno
where it is strongest, and keeps Coke's reliability paths in deterministic code.
