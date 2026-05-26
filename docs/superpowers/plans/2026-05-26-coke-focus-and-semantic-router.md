# Coke Focus And Semantic Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Coke's deterministic user-utterance scheduling pre-router with typed Focus, trusted prompt blocks, a separate semantic interpreter, and executor freshness checks.

**Architecture:** Focus is computed at run start and exposed through `RunContext.session_state`; the semantic interpreter reads only Focus plus the current utterance and emits a typed intent before any domain mutation. The response LLM receives trusted identity, environment, and focus blocks plus one conversation block, while every write re-queries authoritative domain state immediately before mutation.

**Tech Stack:** Python runtime under `agent/agno_agent/runtime/`, Agno `RunContext.session_state`, Pydantic structured-output schemas, existing scheduling domain executor, pytest, gateway internal scheduling APIs.

---

## Human Approval Gate

Subagents must not start execution until a human reviewer approves this spec and plan. The first implementation session must stop after confirming approval and must not edit product code without that explicit approval.

**Verification command:** `git log -1 --stat -- docs/superpowers/specs/2026-05-26-coke-focus-and-semantic-router-design.md docs/superpowers/plans/2026-05-26-coke-focus-and-semantic-router.md`

**Done criteria:** The latest committed docs include the approved spec and this plan, and the human reviewer has explicitly approved implementation in chat or issue tracker.

## File Structure

- Modify: `agent/agno_agent/runtime/context.py`
  - Owns typed Focus data structures or imports them from a focused runtime module.
- Create: `agent/agno_agent/runtime/focus.py`
  - Computes `FocusChannel` at run start from trusted product context and authoritative scheduling state.
- Create: `agent/agno_agent/runtime/semantic_interpreter.py`
  - Defines semantic intent schemas and runs the separate structured-output LLM call.
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`
  - Renders `<trusted kind="identity">`, `<trusted kind="environment">`, `<trusted kind="focus">`, and `<conversation>` trust framing.
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
  - Removes deterministic preselection, wires Focus, calls the semantic interpreter, invokes executor freshness checks, and passes trusted blocks to response synthesis.
- Modify: `agent/agno_agent/runtime/execution_agents.py`
  - Accepts typed semantic intent and forced args without reclassifying user utterance.
- Modify: scheduling gateway/internal executor files selected by current code ownership.
  - Re-query authoritative DB state immediately before any accept/reject/cancel/write.
- Create: `tests/fixtures/semantic_router_cases.json`
  - Stores the representative 30-50 case eval subset.
- Create: `tests/unit/agent/test_focus_channel.py`
  - Tests Focus construction and ambiguity.
- Create: `tests/unit/agent/test_semantic_interpreter.py`
  - Tests schema parsing, fixture replay, and no keyword-router fallback.
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`
  - Updates runtime wiring expectations and removes deterministic pre-router assertions.
- Modify: `tests/unit/agent/test_chat_response_scheduling_instructions.py`
  - Updates prompt trust framing expectations.
- Modify: `docs/ARCHITECTURE.md`
  - Documents Focus, semantic interpreter, and executor freshness after implementation.

### Task 0: Confirm Approval Gate

**Description:** Confirm that a human reviewer approved implementation before dispatching any subagent or editing product code.

**Files:**
- Read: `docs/superpowers/specs/2026-05-26-coke-focus-and-semantic-router-design.md`
- Read: `docs/superpowers/plans/2026-05-26-coke-focus-and-semantic-router.md`

- [ ] **Step 1: Check the latest docs commit**

Run:

```bash
git log -1 --stat -- docs/superpowers/specs/2026-05-26-coke-focus-and-semantic-router-design.md docs/superpowers/plans/2026-05-26-coke-focus-and-semantic-router.md
```

Expected: The latest relevant commit includes both docs.

- [ ] **Step 2: Confirm reviewer approval**

Run:

```bash
git status --short
```

Expected: No product-code edits have been made for this plan yet.

**Verification command:** `git status --short`

**Done criteria:** Human approval is recorded, no product code has been changed before approval, and the implementation worker can proceed to Task 1.

### Task 1: Write Focus Channel Tests

**Description:** Add focused tests for run-start Focus construction and channel-level ambiguity without implementing Focus yet.

**Files:**
- Create: `tests/unit/agent/test_focus_channel.py`

- [ ] **Step 1: Add tests for single pending focus**

Write tests that construct one trusted pending shared-reminder product action and assert:

```python
assert focus.ambiguity == "none"
assert focus.current.action_id == "req_shared_1"
assert focus.current.kind == "shared_reminder_request"
assert tuple(focus.current.allowed_actions) == ("accept", "reject")
assert focus.current.status == "pending"
assert focus.current.summary_for_llm
```

- [ ] **Step 2: Add tests for multi-pending ambiguity**

Write a test with two pending actions for the same conversation and assert:

```python
assert focus.ambiguity == "multi_pending"
assert focus.current is None
assert len(focus.candidates) == 2
```

- [ ] **Step 3: Add tests for none-actionable and expired focus**

Write tests where no action exists and where an action is expired. Assert:

```python
assert focus.ambiguity == "none_actionable"
assert focus.current is None
```

**Verification command:** `.venv/bin/python -m pytest tests/unit/agent/test_focus_channel.py -q`

**Done criteria:** The new tests fail because `agent.agno_agent.runtime.focus` and `FocusChannel` do not exist yet; failure is limited to missing implementation, not syntax errors.

### Task 2: Implement Focus Channel

**Description:** Implement typed Focus data structures and run-start construction without changing prompt rendering or semantic interpretation.

**Files:**
- Create: `agent/agno_agent/runtime/focus.py`
- Modify: `agent/agno_agent/runtime/context.py`
- Modify: `agent/agno_agent/runtime/agent_runtime.py`

- [ ] **Step 1: Define Focus types**

Implement frozen Pydantic models or dataclasses with these fields:

```python
FocusAmbiguity = Literal["none", "multi_pending", "none_actionable"]

class PendingAction(BaseModel):
    action_id: str
    kind: str
    allowed_actions: tuple[str, ...]
    status: str
    expires_at: datetime | None = None
    summary_for_llm: str

class FocusChannel(BaseModel):
    current: PendingAction | None
    ambiguity: FocusAmbiguity
    candidates: tuple[PendingAction, ...] = ()
```

- [ ] **Step 2: Add run-start Focus construction**

Implement a builder that reads trusted product action inputs and current domain state, returns exactly one of:

```python
FocusChannel(current=action, ambiguity="none", candidates=(action,))
FocusChannel(current=None, ambiguity="multi_pending", candidates=actions)
FocusChannel(current=None, ambiguity="none_actionable", candidates=())
```

- [ ] **Step 3: Expose Focus through session state**

In `run_agent_runtime`, compute Focus before semantic interpretation and expose a JSON-safe representation through `RunContext.session_state` or the repo's current equivalent runtime context container.

**Verification command:** `.venv/bin/python -m pytest tests/unit/agent/test_focus_channel.py -q`

**Done criteria:** `tests/unit/agent/test_focus_channel.py` passes, and no prompt or semantic interpreter behavior has changed yet.

### Task 3: Write Prompt Trust Framing Tests

**Description:** Add prompt tests for trusted identity/environment/focus blocks and the single conversation block.

**Files:**
- Modify: `tests/unit/agent/test_chat_response_scheduling_instructions.py`

- [ ] **Step 1: Assert trusted block shape**

Add assertions that rendered instructions contain:

```python
'<trusted kind="identity">'
'<trusted kind="environment">'
'<trusted kind="focus">'
'<conversation>'
'</conversation>'
```

- [ ] **Step 2: Assert conflict rule**

Add assertions that the prompt includes the rules:

```python
"On conflict, trusted blocks win"
"If focus is empty or ambiguous, ask a clarifying question"
```

- [ ] **Step 3: Assert product notification is not rendered as flat context**

Update existing product-notification tests to assert the old flat line is gone:

```python
assert "product_notification:" not in text
```

**Verification command:** `.venv/bin/python -m pytest tests/unit/agent/test_chat_response_scheduling_instructions.py -q`

**Done criteria:** The new prompt tests fail only because prompt rendering still uses the old flat runtime-context block.

### Task 4: Implement Prompt Trust Framing

**Description:** Replace flat runtime-context rendering with trusted blocks while preserving user-visible reply boundary and domain result contract.

**Files:**
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`

- [ ] **Step 1: Render identity block**

Render user id, user nickname, character id, character nickname, conversation id, and route key inside:

```xml
<trusted kind="identity">
...
</trusted>
```

- [ ] **Step 2: Render environment block**

Render current time, timezone, platform, input type, and reminder-fire event facts inside:

```xml
<trusted kind="environment">
...
</trusted>
```

- [ ] **Step 3: Render focus block**

Render Focus from session state inside:

```xml
<trusted kind="focus">
...
</trusted>
```

If Focus is absent, render `ambiguity: none_actionable`.

- [ ] **Step 4: Render the conversation block contract**

Keep conversation content in one block and include the conflict rule:

```xml
<conversation>
...
</conversation>
```

**Verification command:** `.venv/bin/python -m pytest tests/unit/agent/test_chat_response_scheduling_instructions.py -q`

**Done criteria:** Prompt trust framing tests pass, and existing reply-boundary tests still pass.

### Task 5: Write Semantic Interpreter Tests And Corpus

**Description:** Add the representative 30-50 case corpus and schema-level tests for semantic intent classification.

**Files:**
- Create: `tests/fixtures/semantic_router_cases.json`
- Create: `tests/unit/agent/test_semantic_interpreter.py`

- [ ] **Step 1: Create corpus fixture**

Create 30-50 cases across these categories:

```json
[
  "single_pending_accept",
  "single_pending_reject",
  "multi_pending_ambiguity",
  "ask_detail",
  "request_change",
  "stale_focus",
  "expired_focus",
  "unrelated_utterance",
  "negative_control"
]
```

Include negative controls such as `先不要`, `先不要急着`, and `不要现在处理`.

- [ ] **Step 2: Add schema tests**

Assert the interpreter result accepts:

```python
{"intent": "accept", "confidence": "high"}
{"intent": "request_change", "confidence": "medium"}
{"intent": "ambiguous", "confidence": "low"}
```

and rejects unknown intent names.

- [ ] **Step 3: Add replay tests with a fake interpreter client**

Use a fake structured-output client so tests verify prompt/schema plumbing and fixture expectations without a live model call.

**Verification command:** `.venv/bin/python -m pytest tests/unit/agent/test_semantic_interpreter.py -q`

**Done criteria:** Tests fail because `semantic_interpreter.py` does not exist yet; the fixture is valid JSON and contains 30-50 cases.

### Task 6: Implement Separate Semantic Interpreter

**Description:** Implement the separate fast structured-output interpreter and keep it independent from response synthesis.

**Files:**
- Create: `agent/agno_agent/runtime/semantic_interpreter.py`
- Modify: `agent/agno_agent/runtime/agent_runtime.py`

- [ ] **Step 1: Define structured result schema**

Implement a schema equivalent to:

```python
class SemanticIntentResult(BaseModel):
    intent: Literal[
        "accept",
        "reject",
        "ask_detail",
        "request_change",
        "unrelated",
        "ambiguous",
        "create_shared_reminder",
        "accept_shared_reminder",
        "reject_shared_reminder",
        "cancel_shared_reminder",
        "send_friend_request_by_user_link_code",
        "list_friend_requests",
        "accept_friend_request",
        "reject_friend_request",
        "cancel_friend_request",
        "list_friends",
        "remove_friendship",
        "get_user_link",
        "reset_user_link",
        "disable_user_link",
        "list_friend_calendar_facts",
        "list_shared_reminders",
    ]
    confidence: Literal["low", "medium", "high"]
    args: dict[str, Any] = {}
    clarification_reason: str = ""
```

- [ ] **Step 2: Build interpreter input**

The input must include only:

```python
{
    "focus": focus.model_dump(mode="json") if focus else None,
    "current_utterance": current_utterance,
}
```

- [ ] **Step 3: Add timeout and fail-closed behavior**

On timeout, invalid output, or low-confidence mutation intent, return
`ambiguous` and ask clarification rather than falling back to keyword routing.

**Verification command:** `.venv/bin/python -m pytest tests/unit/agent/test_semantic_interpreter.py -q`

**Done criteria:** Semantic interpreter tests pass with a fake client, and there is no call to `_infer_scheduling_intent_from_message` from new interpreter code.

### Task 7: Remove Deterministic Pre-router Wiring

**Description:** Replace runtime preselected scheduling intent flow with Focus plus semantic interpreter output.

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`

- [ ] **Step 1: Update runtime tests**

Rewrite product-notification short-confirmation tests to assert semantic interpreter invocation and executor dispatch, not keyword preselection.

- [ ] **Step 2: Remove pre-router calls from `run_agent_runtime`**

Remove runtime calls to:

```python
_infer_scheduling_intent_and_args_from_agent_input(...)
_infer_scheduling_intent_from_message(...)
_product_notification_decision(...)
```

- [ ] **Step 3: Keep output guardrails**

Do not remove final-output guardrails such as unconfirmed durable-write and identifier-leak checks.

**Verification command:** `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_semantic_interpreter.py -q`

**Done criteria:** Runtime construction tests pass, semantic interpreter tests pass, and `rg "_infer_scheduling_intent_from_message|_product_notification_decision" agent/agno_agent/runtime/agent_runtime.py` shows no live runtime call path.

### Task 8: Add Executor Freshness Tests

**Description:** Add tests proving domain writes re-query authoritative state immediately before mutation and fail with structured domain errors when state moved.

**Files:**
- Modify: scheduling domain unit tests selected by current executor ownership
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`

- [ ] **Step 1: Test stale accepted action**

Create a test where Focus says `pending`, the fresh DB read says `accepted`, and the executor returns:

```python
outcome == "failed"
safety_boundary == "stale_focus"
operation.ok is False
reply_contract.intent == "report_failure"
```

- [ ] **Step 2: Test expired action**

Create a test where fresh state is expired and assert the visible summary reports that the request is no longer actionable.

- [ ] **Step 3: Test wrong recipient**

Create a test where the action exists but belongs to another recipient and assert no mutation occurs.

**Verification command:** `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -q`

**Done criteria:** Tests fail because executor freshness checks have not been implemented yet; failures are limited to expected stale/expired/wrong-recipient assertions.

### Task 9: Implement Executor Freshness Checks

**Description:** Implement authoritative re-query before domain mutation and structured stale-state failures.

**Files:**
- Modify: `agent/agno_agent/runtime/execution_agents.py`
- Modify: scheduling gateway/internal executor files selected by current ownership

- [ ] **Step 1: Add pre-write state read**

Before accept/reject/cancel/write operations, read the current DB row by `focus.action_id` or typed request id.

- [ ] **Step 2: Validate state transition**

Check current status, recipient, ownership, expiry, and allowed action before writing.

- [ ] **Step 3: Return structured stale failure**

Return a `DomainExecutionResult` with:

```python
outcome="failed"
safety_boundary="stale_focus"
reply_contract.intent="report_failure"
```

and a user-safe visible summary.

**Verification command:** `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -q`

**Done criteria:** Executor freshness tests pass, and no mutation test writes when fresh state is accepted, expired, missing, canceled, or wrong-recipient.

### Task 10: Documentation Update

**Description:** Update canonical docs after behavior changes are implemented and verified.

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/product-specs/FEATURE_TREE.md` if route or API discoverability changes

- [ ] **Step 1: Document Focus and interpreter flow**

Add the runtime sequence:

```text
run start -> Focus construction -> semantic interpreter -> executor freshness check -> response synthesis
```

- [ ] **Step 2: Document no keyword/regex routing policy**

State that user-utterance intent classification is owned by the semantic interpreter, while regexes may remain for output guardrails and typed validation.

- [ ] **Step 3: Document ambiguity behavior**

Document that `multi_pending` and `none_actionable` ask clarification instead of acting on transcript clues.

**Verification command:** `zsh scripts/verify-surface repo-os-docs`

**Done criteria:** Repo-OS docs verification passes, and docs match the implemented runtime behavior.

### Task 11: Representative Corpus Verification

**Description:** Run the representative semantic-router corpus and targeted unit suite.

**Files:**
- Read: `tests/fixtures/semantic_router_cases.json`
- Read: `tests/unit/agent/test_semantic_interpreter.py`
- Read: `tests/unit/agent/test_agent_runtime_construction.py`

- [ ] **Step 1: Run semantic interpreter tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_semantic_interpreter.py -q
```

Expected: PASS.

- [ ] **Step 2: Run runtime construction tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -q
```

Expected: PASS.

- [ ] **Step 3: Run prompt tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_chat_response_scheduling_instructions.py -q
```

Expected: PASS.

**Verification command:** `.venv/bin/python -m pytest tests/unit/agent/test_semantic_interpreter.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_chat_response_scheduling_instructions.py -q`

**Done criteria:** The representative corpus passes, prompt framing tests pass, runtime construction tests pass, and negative-control cases such as `先不要` are not classified as reject.

### Task 12: Diff-Aware Final Verification

**Description:** Run repository verification routing after all implementation and docs tasks have landed.

**Files:**
- Read: `docs/fitness/README.md` only if suggested by the command
- Read: `docs/fitness/coke-verification-matrix.md` only if suggested by the command

- [ ] **Step 1: Run verification suggestion**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
```

Expected: The command suggests runtime and docs surfaces relevant to the diff.

- [ ] **Step 2: Run review trigger**

Run:

```bash
zsh scripts/review-trigger --base HEAD~1
```

Expected: The command reports whether escalation review is required.

- [ ] **Step 3: Run suggested surfaces**

Run each command suggested by `scripts/suggest-verification`. At minimum, expect a worker-runtime surface and `repo-os-docs` if docs changed.

**Verification command:** `zsh scripts/suggest-verification --base HEAD~1 && zsh scripts/review-trigger --base HEAD~1`

**Done criteria:** Suggested verification commands have been run and recorded; failures are classified as product/runtime bug, test/eval bug, environment instability, or plan gap before any further edits.
