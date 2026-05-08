# Team Runtime Contract Repair Design

**Status:** Draft for review
**Date:** 2026-05-08
**Surfaces:** `worker-runtime`, `repo-os`
**Primary files:** `agent/agno_agent/runtime/`,
`agent/agno_agent/capabilities/`, `agent/agno_agent/prompts/`,
`agent/runner/agent_handler.py`,
`agent/runner/deferred_action_executor.py`,
`agent/runner/reminder_event_handler.py`, `tests/unit/agent/`,
`tests/unit/runner/`, `artifacts/evidence/reminder-normal/`
**Out of scope:** gateway APIs, bridge topology, reminder durable schema,
production deployment, persona migration, new product behavior

## Context

The Team runtime cutover left the repository in a state where typed contracts
exist, but the most important runtime behavior is not protected by those
contracts. The external review of `d1b180d -> 2e3cd2a`, then the local
confirmation against current `main` at `6c6da78`, found the same failure mode:
tests are green while user-visible behavior changed.

The useful parts of the cutover should be kept:

- typed `AgentInput` and `AgentRunResult`
- frozen runtime dataclasses
- deterministic capability adapters
- hand-written fakes instead of broad `MagicMock`
- a single Team manager output protocol that can be parsed by deterministic
  code

The broken parts should be repaired before any deployment:

- runtime-local protocol retries and synthetic `reminder_intent` recovery
- runner guards that exist as helper functions but are not wired to the
  production path
- mid-run interruption behavior removed by awaiting the Team runtime as one
  opaque call
- deferred reminder fires scheduling PostAnalyze again
- exception handling that hides the original deferred-action failure
- prompt/schema drift for reminder retry
- manager prompt instructions that ask for JSON while parser expects
  `RESPONSE` and `REQUEST` text
- silent exception swallowing in reminder fire handling
- tests that pin implementation artifacts instead of production contracts

## Clarifying Assumptions

This spec chooses repair over rollback. The goal is not to restore
`PrepareWorkflow -> StreamingChatWorkflow` as the primary architecture. The goal
is to make the Team runtime obey the same user-visible reliability contract that
the old runner path already had.

The repair must not add parser fallbacks, regex intent detection, case-specific
branches, negative-example prompt accretion, or eval-only behavior changes.
When model output violates the contract, the runtime should surface the failure
as a typed empty/error disposition and let the runner handle it deterministically.

## Goals

1. Restore the runtime contract before deployment.
2. Keep semantic judgment in the LLM layer and durable side effects in
   deterministic adapters.
3. Reconnect runner-level user-visible guards to `handle_message`.
4. Make interruption, lock handling, empty output, and PostAnalyze scheduling
   explicit Team-path contracts.
5. Replace helper-only tests with behavior tests that exercise the production
   path.
6. Remove large transcript artifacts from git history going forward by using
   small evidence files plus manifests.

## Non-Goals

- No new reminder capabilities.
- No change to reminder storage, scheduler semantics, or DAO schemas.
- No fallback to Python NLU for reminder intent.
- No compatibility layer that keeps both old and new runtime protocols alive.
- No broad cleanup of all abstractions before blockers are fixed.
- No production deploy in this design step.

## Approaches Considered

### Option A: Hotfix The Eight Blockers Only

Patch B1-B8 directly and leave the abstraction shape intact.

Benefits:

- smallest immediate code diff
- fastest path to lower production risk
- easy to review if each blocker has a focused test

Costs:

- preserves dead selector/port abstractions that obscure the runtime boundary
- leaves fake parity tests and transcript evidence debt for later
- does not explain why late-cycle hardening drifted into runtime heuristics

### Option B: Contract Repair First, Cleanup Second

Fix B1-B8 as a contract repair, rewrite the tests around production behavior,
and defer dead abstraction cleanup to a second phase.

Benefits:

- restores user-visible behavior without turning the task into another broad
  redesign
- keeps the typed runtime assets that are already valuable
- directly attacks the cause of green tests hiding behavior regressions
- gives the cleanup phase a stable contract to preserve

Costs:

- requires touching both runtime and runner surfaces in one plan
- some dead abstractions remain temporarily
- full confidence depends on behavior-level tests, not just unit tests

This is the recommended approach.

### Option C: Roll Back The Team Runtime Cutover

Revert to the old workflow runtime and restart the Team migration later.

Benefits:

- likely restores known runner behavior quickly
- avoids designing around a partially broken Team path

Costs:

- discards useful typed contract work
- likely conflicts with the merged deletion of legacy workflow files
- delays learning from the current failure mode
- does not produce a better Team contract for the next attempt

Rollback is a fallback only if contract repair cannot pass the behavior gates.

## Architecture

The repaired shape is:

```text
agent/runner/
  owns queueing, locks, interruption, output writes, sync reply rules,
  rollback, fallback replies, and PostAnalyze scheduling
        |
        | AgentInput
        v
agent/agno_agent/runtime/
  owns one Team manager call and one parseable RESPONSE/REQUEST protocol
        |
        | CapabilityRequest
        v
agent/agno_agent/capabilities/
  owns deterministic adapters for reminder, timezone, URL, calendar import
        |
        | CapabilityResult
        v
agent/runner/
  converts AgentRunResult into user-visible output and background work
```

The key boundary rule:

```text
LLM output can request capabilities.
LLM output cannot be repaired into capabilities by runtime heuristics.
```

`run_team_runtime` may parse `REQUEST reminder_intent {}` if the manager emits
that protocol. It must not infer `reminder_intent` from provider tool artifacts,
JSON envelopes, raw cancellation text, empty output, or a direct promise such as
"I already set the reminder". Those are protocol failures. They become
`OutputDisposition(status="empty")` or a typed error disposition.

## Runtime Contract

### Manager Prompt

`build_manager_instructions` should define only the Team manager protocol and
dialogue constraints that are compatible with that protocol.

It must not inject a prompt section that tells the model to output JSON when
`plan_parser.py` expects `RESPONSE` and `REQUEST` lines.

The protocol should be small and auditable:

```text
RESPONSE:
<user visible text>
REQUEST reminder_intent {}
REQUEST url_context {}
REQUEST timezone {"action":"direct_set","timezone":"Asia/Tokyo"}
REQUEST calendar_import {}
```

Manager tests must cross-check prompt capability names with
`ALLOWED_CAPABILITIES`, so prompt/parser drift becomes a failing test.

### Plan Parser

`parse_team_plan` remains the only parser for manager output. It may accept
reasonable whitespace and inline `REQUEST` placement, but it must not parse
provider tool syntax, XML, JSON response envelopes, markdown JSON blocks, or
tool-call artifacts.

Rejected capability names should be recorded in the trace and never executed.

### Runtime Failure Handling

When the manager returns:

- empty visible content
- provider tool syntax
- JSON envelopes
- raw cancellation strings
- malformed protocol
- a direct promise to perform a durable write without a capability request

the runtime returns no visible messages and a typed empty/error disposition.
It does not retry with stronger prompt wording and does not synthesize a
capability request.

The runner fallback path then decides whether to send a neutral retry message,
ask a clarification, or roll back because a newer user message arrived.

### Capability Retry

`ReminderIntentPort` may retry a detector call after schema or model failure,
but the retry input must derive from the same schema/instruction source as the
primary path. It must not hard-code an action list that excludes schema-valid
actions such as `cancel`.

Retry guidance may say:

- use the attached ReminderDetect instructions
- return only a valid `ReminderDetectDecision`
- do not invent schema keys

It should not restate a divergent action enum.

## Runner Contract

### Sync ClawScale Text Reply

Business `delivery_mode=request_response` is a synchronous caller contract. The
Team path must preserve the old behavior: first eligible text output is written
and the streaming/wait path stops early instead of waiting for all Team work to
finish.

If the Team runtime cannot produce a text response before the sync boundary,
the runner should send the same neutral fallback it uses for empty output.

### Reminder Stop Guard

If the user appears to be stopping/canceling a pending reminder and no reminder
tool result exists, the production path must not send a confident cancellation
claim. It should send the existing clarification:

```text
你是想停掉哪条提醒？告诉我具体是哪条，我再帮你处理。
```

This guard must run on the multimodal response just before output write, not
only as a directly tested helper.

### Prepare Timeout Guard

If prepare/orchestration timeout state exists and no reminder tool result exists,
the Team path must not turn an unconfirmed reminder request into "already set".
The existing fallback wording should remain the user-visible behavior.

### Mid-Run Interruption

The Team path must support cooperative interruption. The runner should check
for newer pending user messages while the Team runtime awaitable is in flight,
not only before it starts.

The design target is one runner helper that owns both lock heartbeat and
interruption polling:

```text
await_with_runtime_supervision(
    runtime_task,
    lock_id,
    conversation_id,
    check_new_message,
    current_message_ids,
)
```

If a newer message appears, cancel the runtime task, return rollback, and avoid
sending any stale output.

If cancellation cannot reliably stop the underlying provider request, the
runner still drops the result after cancellation and records the trace.

### Deferred Reminder PostAnalyze

Reminder fires with `message_source == "deferred_action"` and
`metadata.kind == "user_reminder"` must skip PostAnalyze. This was a runtime
cost and behavior optimization in the old path and should be a Team-path
contract, not an environment-only switch.

### Deferred Action Failure Visibility

`DeferredActionExecutor` must preserve the original exception when occurrence
claiming or DAO work fails. Exception handlers may use an initialized
occurrence placeholder, but they must not replace Mongo/DAO failures with a
local `NameError`.

### Reminder Event Observability

`ReminderFireEventHandler` should log stack traces when replay lookup, output
write, context building, or typed runtime handling fails. Returning a typed
failure result is fine, but silent `except Exception` blocks are not.

## Testing Design

Tests should be organized around contracts, not helper existence.

### Required Behavior Tests

- Team manager malformed protocol returns `empty` and does not execute
  `reminder_intent`.
- Team manager empty output returns `empty` and does not retry into
  `reminder_intent`.
- Direct unconfirmed reminder promise returns `empty` or fallback, not a durable
  reminder write.
- `handle_message` applies pending reminder stop guard before sending.
- `handle_message` applies prepare-timeout reminder guard before sending.
- `handle_message` stops after first sync ClawScale request-response text.
- `handle_message` cancels/drops Team runtime output when a newer message
  appears mid-run.
- Deferred `user_reminder` does not schedule PostAnalyze.
- Deferred action occurrence-claim failure reports the original error.
- Reminder fire replay/output failures call `logger.exception`.
- Manager prompt capability list matches `ALLOWED_CAPABILITIES`.
- Reminder retry action set is schema-derived or otherwise includes every
  schema-valid action.

### Tests To Delete Or Rewrite

- Any test that expects protocol artifact retry to execute
  `reminder_intent`.
- Any test that expects runtime recovery from direct reminder promises through
  regex or text matching.
- Helper-only guard tests that do not exercise `handle_message`.
- Literal set equality tests where both sets live in the test body.
- Runtime selector tests that assert precedence among only one possible runtime.
- Dataclass tests that mostly verify Python's `frozen=True` behavior rather
  than Coke behavior.
- Duplicate test functions where pytest collects only the later definition.

### Verification Commands

Focused repair verification:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_team_runtime_execution.py \
  tests/unit/agent/test_team_runtime_plan_parser.py \
  tests/unit/agent/test_manager_prompt.py \
  tests/unit/agent/test_agent_handler.py \
  tests/unit/runner/test_deferred_action_executor.py \
  tests/unit/runner/test_reminder_event_handler.py -v
```

Worker runtime baseline:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/ tests/unit/runner/ -v
```

Reminder behavior gate:

```bash
AGENT_RUNTIME_VERSION=team python scripts/eval_reminder_normal_path_cases.py
```

Repo-OS validation is required only if workflow docs, routing docs, evidence
policy, or guardrail scripts change:

```bash
zsh scripts/check
```

## Evidence Policy

Small targeted evidence files may stay in git when they explain a product
behavior or a regression fix. Full-run LLM transcripts should not be committed
as permanent repo artifacts.

For broad eval runs, write:

- a compact manifest with command, commit, environment, pass/fail summary, and
  relevant case IDs
- small per-case artifacts for failures or representative fixed cases
- an external object-store path or local artifact path for full transcripts

Existing large tracked files under `artifacts/evidence/reminder-normal/` should
be handled in the cleanup phase after the blockers are fixed. New repair work
should not add another large full-run transcript to git.

## Sequencing

### Phase 1: Contract Blockers

1. Fix reminder retry schema drift.
2. Preserve original deferred-action exceptions.
3. Add `logger.exception` to reminder fire failure paths.
4. Remove manager prompt JSON contradiction.
5. Remove Team protocol retry and synthetic capability recovery.
6. Add failing behavior tests first for the removed recovery paths.

Exit criteria:

- malformed Team output cannot execute reminder writes
- reminder retry accepts schema-valid actions
- deferred/reminder failure logs preserve root cause

### Phase 2: Runner Behavior Restoration

1. Reconnect sync ClawScale first-text behavior.
2. Reconnect pending reminder stop guard.
3. Reconnect prepare-timeout unconfirmed reminder guard.
4. Add cooperative interruption polling around Team runtime await.
5. Restore deferred `user_reminder` PostAnalyze skip.

Exit criteria:

- `handle_message` tests cover production path behavior for every restored
  guard
- mid-run newer message causes rollback or result drop
- reminder fires do not burn PostAnalyze tokens

### Phase 3: Test Cleanup

1. Delete tests that pin forbidden recovery behavior.
2. Rewrite fake parity tests as behavior parity tests.
3. Remove duplicate pytest definitions.
4. Replace literal contract-name tests with real behavior checks or delete them.
5. Reduce selector/dataclass tests to behavior that can fail for Coke reasons.

Exit criteria:

- green tests mean a production contract was exercised
- no test asserts runtime heuristic recovery as desired behavior

### Phase 4: Abstraction And Evidence Cleanup

1. Remove or inline `runtime/selector.py` if only `team` exists.
2. Remove unused `ContextPort`.
3. Inline or justify `output_disposition.py`.
4. Decide whether capability ports are real ports or just adapters; move shared
   result/context contracts if needed.
5. Remove dead context builds and trusted-raw metadata leaks.
6. Replace large full-run evidence transcripts with manifests.

Exit criteria:

- reduced import depth
- no dead public abstraction whose only consumer is its test
- evidence policy is reflected in docs or guardrails if it becomes durable

## Acceptance Criteria

The repair is complete only when all of these are true:

- B1-B8 are either fixed or explicitly reclassified with code evidence.
- No Team runtime path can synthesize a reminder capability from malformed
  manager output.
- No runner guard exists only as a helper test; every guard is exercised through
  `handle_message`.
- Mid-run interruption is supported or the product explicitly approves removing
  it and docs/tests are updated accordingly.
- Deferred reminder fires skip PostAnalyze.
- Deferred action and reminder fire failures preserve root-cause observability.
- Team prompt and parser capability names cannot drift silently.
- Reminder retry cannot drift from `ReminderDetectDecision.action`.
- Focused Team runtime tests and worker runtime baseline pass.
- Reminder normal-path eval either passes or failures are classified by layer:
  LLM protocol, runtime, evaluator, or environment.

## Risks

### Risk: Removing recovery retries lowers short-term eval pass rate

Mitigation: classify failures by layer. If the manager fails the protocol, fix
the manager prompt/protocol contract. Do not restore runtime heuristics.

### Risk: Cooperative cancellation cannot stop provider calls

Mitigation: cancellation must at least prevent stale output writes. If provider
requests keep running in the background, record that as observability debt and
preserve lock/result-drop behavior.

### Risk: Tests become broad and slow

Mitigation: use focused production-path unit tests with fakes for external
systems. Full eval remains a gate, not the only feedback loop.

### Risk: Cleanup expands before blockers are fixed

Mitigation: Phase 4 is explicitly blocked on Phase 1-3 exit criteria. Dead
abstractions are real, but they are not the first production risk.

## Implementation Planning Notes

The implementation plan should use an isolated worktree if concurrent work is
possible. It should not start on broad cleanup. The first implementation task
should create failing tests for the forbidden runtime recovery behavior and the
runner guards that are currently disconnected from production.

Each phase should commit separately. The first commit should not touch evidence
cleanup or abstraction deletion unless a blocker fix directly requires it.
