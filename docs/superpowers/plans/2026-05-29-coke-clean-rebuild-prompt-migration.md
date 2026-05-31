---
status: complete
created_at: 2026-05-31
updated_at: 2026-05-31
owner: agent-runtime
kind: implementation_plan
plan_status: complete
---

# Prompt Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Selectively migrate legacy prompt strengths into Coke's clean Turn runtime without reintroducing legacy ownership, fallback prose, parser repair, keyword routing, or domain leakage.

**Architecture:** Keep SemanticInterpreter as the LLM-semantic front gate and detector as the domain-owned precise extraction path. Replace Interaction Agent's flat user-message-plus-JSON prompt with ordered trusted prompt blocks, and represent tool/domain facts through a domain-neutral narration shape that the agent renders without inferring success from transcript text.

**Tech Stack:** Python dataclasses and protocols, Agno agent wrapper, in-memory unit tests, pytest, existing Coke clean-rebuild Turn/runtime modules.

---

## File Structure

- Modify `coke/turn/semantic_interpreter.py`: add typed `IntentAction`, `AmbiguityState`, `RequiredClarification`, and enrich `SemanticDecision`.
- Modify `coke/llm/semantic_interpreter.py`: validate the enriched model output, pass allowed action/ambiguity/clarification values, and add field-specific few-shot examples.
- Modify `coke/llm/reminder_detector.py`: add field-specific positive and negative extraction examples without moving detector ownership into the interpreter.
- Modify `coke/turn/context.py`: add prompt-facing context facts: `turn_source`, optional `domain_result`, and optional ordered block helper data.
- Modify `coke/turn/runner.py`: construct trusted `turn_source`, pass required clarification to the agent, expose trusted domain result facts, and preserve fail-closed output retry behavior.
- Modify `coke/turn/agent.py`: extend `ToolExecutionResult` with optional domain-neutral narration fields while preserving existing tool contracts.
- Modify `coke/llm/agno_interaction_agent.py`: introduce `CokeVoicePolicy`, ordered prompt block builder, structured turn-source framing, domain-result narration, and prompt tests seams.
- Keep composition adapters unchanged unless a service already provides a domain result; the LLM tool wrapper adapts existing tool facts into the common narration shape without changing service contracts.
- Modify `tests/unit/coke/llm/test_semantic_interpreter.py`: add deterministic semantic-decision tests for intent actions, ambiguity, required clarification, examples, and invalid output.
- Modify `tests/unit/coke/llm/test_reminder_detector.py`: add detector prompt tests for vague time, follow-up time, batch, and no regex repair.
- Modify `tests/unit/coke/llm/test_interaction_agent.py`: add prompt-builder block-order, turn-source, voice-policy, domain-result, challenge, no-success-without-domain-result, and invalid-output tests.
- Modify `tests/unit/coke/turn/test_turn_runner.py`: add required-clarification and render-source framing tests.
- Modify `tests/unit/coke/test_clean_rebuild_no_legacy_imports.py` only if the no-legacy import guard needs the new prompt module allowlist adjusted; otherwise leave it untouched.

## Task 1: Enrich Semantic Decision Contract

- [x] **Step 1: Write failing semantic interpreter tests**

Add tests to `tests/unit/coke/llm/test_semantic_interpreter.py` that expect:

```python
decision.intent_action == "create_reminder"
decision.ambiguity == "missing_time"
decision.required_clarification == "ask_trigger_time"
```

Also assert the prompt includes allowed `intent_action`, `ambiguity`, and `required_clarification` values plus examples for vague time, batch operations, follow-up time, and new-topic no-reopen.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_semantic_interpreter.py -v
```

Expected: new tests fail because `SemanticDecision` has no enriched fields and the prompt lacks those allowed sets/examples.

- [x] **Step 2: Implement enriched semantic decision shape**

Add these literals in `coke/turn/semantic_interpreter.py`:

```python
IntentAction = Literal[
    "create_reminder", "update_reminder", "complete_reminder", "delete_reminder",
    "list_reminders", "batch_reminder_ops", "schedule_unscheduled",
    "clear_trigger_time", "create_shared_reminder", "cancel_shared_reminder",
    "list_shared", "availability_query", "get_friend_link", "add_via_code",
    "list_friends", "remove_friend", "update_settings", "set_timezone",
    "toggle_proactive", "toggle_memory", "calendar_import", "claim_identity",
    "chit_chat", "none",
]
AmbiguityState = Literal[
    "clear", "missing_time", "missing_content", "missing_participant",
    "missing_title", "missing_context", "ambiguous_reference",
    "vague_time", "follow_up_time", "new_topic_after_confirmation",
    "domain_failure", "none",
]
RequiredClarification = Literal[
    "none", "ask_trigger_time", "ask_reminder_content", "ask_participant",
    "ask_shared_title", "ask_context", "ask_reference_choice",
    "ask_friend_identity", "ask_timezone_confirmation",
]
```

Extend `SemanticDecision` with default-compatible fields:

```python
intent_action: IntentAction = "none"
ambiguity: AmbiguityState = "none"
required_clarification: RequiredClarification = "none"
```

Update `coke/llm/semantic_interpreter.py` to validate these fields fail-closed with no fallback, and to keep the interpreter LLM-semantic rather than keyword-based.

- [x] **Step 3: Run semantic interpreter tests green**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_semantic_interpreter.py -v
```

Expected: all tests in that file pass.

## Task 2: Route Required Clarification Through The Turn

- [x] **Step 1: Write failing Turn runner clarification tests**

Add a test to `tests/unit/coke/turn/test_turn_runner.py` where the fake semantic interpreter returns:

```python
SemanticDecision(
    reply_necessity="reply_needed",
    intent_family="reminder_op",
    intent_action="create_reminder",
    ambiguity="missing_time",
    required_clarification="ask_trigger_time",
    language_hint="zh",
)
```

Assert the Interaction Agent is invoked once, no state-changing tool is auto-executed by the runner, and the agent request trusted/context facts contain the required clarification signal exactly.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_required_clarification_is_passed_as_trusted_agent_instruction -v
```

Expected: fail because no clarification signal is currently exposed to the agent.

- [x] **Step 2: Implement clarification propagation**

In `coke/turn/runner.py`, add the semantic decision into trusted request facts for the agent and include `required_clarification` as a trusted instruction when it is not `"none"`. Do not synthesize deterministic user-visible prose in the runner.

In `coke/turn/context.py`, make the semantic decision and required clarification serializable in the context payload.

- [x] **Step 3: Run Turn runner tests green**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py -v
```

Expected: all Turn runner tests pass.

## Task 3: Build Ordered Prompt Blocks And Voice Policy

- [x] **Step 1: Write failing Interaction Agent prompt-builder tests**

Add tests to `tests/unit/coke/llm/test_interaction_agent.py` that assert:

```python
block_names == [
    "turn_source", "current_input", "identity", "persona", "environment",
    "semantic_decision", "focus", "domain_result", "memory", "conversation",
    "voice_policy", "output_contract",
]
```

The tests should also assert empty optional blocks are omitted, `output_contract` is last, `ReminderFireTurn` and `ProactiveFireTurn` say the trigger is not user speech, voice policy forbids generic closers and internal tool/log/architecture exposure, and user persona/speaking style/extra rules are layered in the persona block.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py -v
```

Expected: new prompt-builder tests fail because the current input is still `User message` plus `Trusted context` JSON.

- [x] **Step 2: Implement prompt builder and CokeVoicePolicy**

In `coke/llm/agno_interaction_agent.py`, add small functions or dataclasses for:

```python
CokeVoicePolicy
PromptBlock
build_prompt_blocks(request: AgentRequest) -> tuple[PromptBlock, ...]
render_prompt_blocks(blocks: tuple[PromptBlock, ...]) -> str
```

Keep the JSON output envelope and one-to-three segment limit exactly as today. Move final-prose prompt text out of ad-hoc flat JSON and into ordered named blocks. Keep business mutation and field extraction rules out of the voice block.

- [x] **Step 3: Run Interaction Agent tests green**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py -v
```

Expected: all Interaction Agent tests pass.

## Task 4: Add Turn-Source Framing And Domain Result Narration

- [x] **Step 1: Write failing domain-result and source-framing tests**

Add tests across `tests/unit/coke/llm/test_interaction_agent.py` and `tests/unit/coke/turn/test_turn_runner.py` that assert:

```python
domain_result = {
    "domain": "reminder",
    "intent": "create reminder",
    "action": "create_reminder",
    "effect": "created",
    "intent_fulfilled": True,
    "visible_summary": "Created reminder pay rent at 2026-06-01T09:00:00+09:00.",
    "reply_contract": "confirm_success",
    "privacy_notes": [],
}
```

The prompt must render this as trusted fact. A requested operation without this trusted result must be described as not yet confirmed. Domain failure or missing-info results must not allow a success claim. ReminderFireTurn title and ProactiveFireTurn planned action must not appear as a user message.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/test_turn_runner.py -v
```

Expected: fail before the common domain-result shape and source framing exist.

- [x] **Step 2: Implement DomainExecutionResult adaptation**

Add a `DomainExecutionResult` dataclass in `coke/turn/agent.py` and extend `ToolExecutionResult` with an optional `domain_result`.

In `coke/llm/agno_interaction_agent.py`, return tool results with a `domain_result` object from either the provided tool result or a wrapper-level adaptation of existing `ok`/`facts`/`reason_code`. Render any `trusted_facts["domain_result"]`, context domain result, or notification render fact as trusted.

- [x] **Step 3: Run source/domain tests green**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/test_turn_runner.py -v
```

Expected: both files pass.

## Task 5: Strengthen Detector Few-Shots Without Ownership Regression

- [x] **Step 1: Write failing detector prompt tests**

Add tests to `tests/unit/coke/llm/test_reminder_detector.py` for these prompt facts:

```python
"待会/晚点/过一会" in system
"must not become a concrete trigger_time" in system
"batch" in system
"a follow-up that only supplies the missing time" in system
"new topic does not reopen" in system
```

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_reminder_detector.py -v
```

Expected: fail because the detector prompt lacks the new few-shot boundary examples.

- [x] **Step 2: Add detector examples only to detector prompt**

Update `coke/llm/reminder_detector.py` prompt text to include field-specific positive and negative examples for vague time, explicit relative time, batch operations, follow-up time completion, and new-topic no-reopen. Do not add keyword routing, regex repair, or interpreter-owned field extraction.

- [x] **Step 3: Run detector tests green**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_reminder_detector.py -v
```

Expected: all detector tests pass.

## Task 6: Add Deterministic Eval-Style Coverage

- [x] **Step 1: Write failing eval/unit cases**

Add deterministic fake-based unit cases covering the required gate:

```text
create-reminder-with-time
vague-time-clarify
batch
update/delete/complete/list intent
time-only follow-up after Coke asked
new topic after confirmed reminder
shared-reminder create with friend-name resolution
friend-list query
availability query
reminder fire title is not user message
proactive Coke-initiated render
domain success confirmation
domain failure/missing info
user challenge "我没设过这个"
no success without trusted domain result
invalid final output fails closed
no duplicate proactive after timed reminder
```

Place cases in existing focused test files rather than a broad live-LLM corpus. Use fake JSON clients and fake Agno outputs only.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm tests/unit/coke/turn -v
```

Expected: new cases fail until prompt and decision contracts are implemented.

- [x] **Step 2: Implement the minimum code needed for the eval cases**

Keep changes inside `coke/llm/`, `coke/turn/`, and existing composition adapters. Do not edit other domain internals, add schema, import legacy modules, or add fallback prose.

- [x] **Step 3: Run focused eval/unit set green**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm tests/unit/coke/turn -v
```

Expected: all focused prompt/turn tests pass.

## Task 7: Final Verification And Commit

- [x] **Step 1: Run required unit verification**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all unit tests pass.

- [x] **Step 2: Run required integration verification**

Run:

```bash
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
```

Expected: all integration tests pass or a concrete environment blocker is captured.

- [x] **Step 3: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: commands complete and any extra required surface is either verified or explicitly reported.

- [x] **Step 4: Update plan status and commit**

After verification passes, update this file:

```yaml
plan_status: complete
status: complete
```

Then commit all scoped changes:

```bash
git add coke/llm coke/turn coke/composition.py tests/unit/coke/llm tests/unit/coke/turn docs/superpowers/plans/2026-05-29-coke-clean-rebuild-prompt-migration.md
git commit -m "feat: migrate prompt decision and voice contracts"
```

Expected: `git log --oneline main..HEAD` shows the new commit on `opt/prompt-migration`.

## Self-Review

- Spec coverage: Tasks 1-6 map to borrowings 1-6 and the required eval/unit cases from `2026-05-31-legacy-prompt-selective-migration-design.md`.
- Ownership check: SemanticInterpreter owns typed routing and clarification; detector owns precise fields; Interaction Agent owns prose; domain/result facts own success truth.
- Contract check: No legacy imports, no schema changes, no fallback prose, no keyword/regex routing, no deterministic user-visible clarification text outside the Interaction Agent.
