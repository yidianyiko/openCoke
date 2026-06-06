# Response Contract Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Tracks C and D from the EVA chat RCA: structured social-scheduling reply outcomes and durable friend-correction recovery.

**Architecture:** Keep the Interaction Agent as the single channel-visible prose producer. SocialScheduling supplies typed outcomes and recoverable intent artifacts; The Turn injects those facts and validates structured output claims at close. Friend corrections are opened only by a typed semantic follow-up action, never by runner keyword matching.

**Tech Stack:** Python dataclasses, SQLAlchemy metadata, Alembic migrations, pytest, existing Coke turn/runtime/domain services.

---

## File Structure

- Modify `coke/schema.py`: add `recoverable_scheduling_intent` table and one-open partial index.
- Add `migrations/versions/20260607_0001_recoverable_scheduling_intent.py`: database migration for the new table and index.
- Modify `coke/domains/social_scheduling/models.py`: add `SocialSchedulingOutcome`, status/claim literals, `RecoverableSchedulingIntent`, and resolution result dataclasses.
- Modify `coke/domains/social_scheduling/repository.py`: persist/read/expire/consume recoverable intents in memory and Postgres.
- Modify `coke/domains/social_scheduling/service.py`: build social outcomes, create recoverable intents after blocked closes, resolve corrected friend text, and consume matching artifacts.
- Modify `coke/turn/semantic_interpreter.py` and `coke/llm/semantic_interpreter.py`: add typed follow-up action schema and prompt exposure.
- Modify `coke/turn/output_protocol.py`: parse optional `domain_claim` and validate social-scheduling claims against trusted outcomes.
- Modify `coke/turn/agent.py`: carry tool events/outcomes on `AgentResult`.
- Modify `coke/llm/agno_interaction_agent.py`: propagate tool events, build social-scheduling outcome prompt blocks, enforce structured claim contracts, and remove deterministic friend-follow-up helper branches.
- Modify `coke/composition.py`: return structured social outcomes from social scheduling tool calls and staged previews.
- Modify `coke/turn/runner.py`: inject recoverable-intent trusted facts, create artifacts after fresh blocked closes, and consume artifacts only after fresh materialized recovered commands.
- Modify `docs/ARCHITECTURE.md`: document the new artifact and structured outcome guard without changing the sole-producer invariant.
- Tests:
  - `tests/unit/coke/social_scheduling/test_social_scheduling_schema_contract.py`
  - `tests/unit/coke/social_scheduling/test_recoverable_scheduling_intent.py`
  - `tests/unit/coke/llm/test_semantic_interpreter.py`
  - `tests/unit/coke/turn/test_output_protocol.py`
  - `tests/unit/coke/llm/test_interaction_agent.py`
  - `tests/unit/coke/test_social_scheduling_tool_adapter.py`
  - `tests/unit/coke/turn/test_turn_runner.py`

## Task 1: Recoverable Intent Schema And Repository

**Files:**
- Modify: `coke/schema.py`
- Add: `migrations/versions/20260607_0001_recoverable_scheduling_intent.py`
- Modify: `coke/domains/social_scheduling/models.py`
- Modify: `coke/domains/social_scheduling/repository.py`
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_schema_contract.py`
- Add: `tests/unit/coke/social_scheduling/test_recoverable_scheduling_intent.py`

- [x] **Step 1: Write failing schema contract tests**

Add assertions that `recoverable_scheduling_intent` exists with these columns:

```python
def test_recoverable_scheduling_intent_schema_tracks_single_open_artifact():
    table = schema.metadata.tables["recoverable_scheduling_intent"]
    assert {
        "id",
        "conversation_id",
        "creator_account_id",
        "operation",
        "status",
        "blocker",
        "title",
        "local_trigger_at",
        "captured_timezone",
        "duration_minutes",
        "unresolved_reference_text",
        "source_turn_id",
        "source_input_from_seq",
        "source_input_to_seq",
        "source_message_ids",
        "facts",
        "facts_hash",
        "expires_at",
        "consumed_turn_id",
        "created_at",
        "updated_at",
    }.issubset(set(table.c.keys()))
    index = _index("recoverable_scheduling_intent", "uq_recoverable_intent_one_open_per_conversation")
    assert index.unique is True
    assert tuple(column.name for column in index.columns) == ("conversation_id",)
    assert "recoverable_scheduling_intent.status = 'open'" in _compiled_where(index)
```

- [x] **Step 2: Run schema test and verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_schema_contract.py::test_recoverable_scheduling_intent_schema_tracks_single_open_artifact -v
```

Expected: FAIL with missing `recoverable_scheduling_intent`.

- [x] **Step 3: Add dataclasses and schema**

Add `RecoverableSchedulingIntent` and related literals to `models.py`, the SQLAlchemy table/index to `schema.py`, and the Alembic migration.

Migration revision:

```python
revision = "20260607_0001"
down_revision = "20260531_0001"
```

- [x] **Step 4: Run schema test and verify green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_schema_contract.py::test_recoverable_scheduling_intent_schema_tracks_single_open_artifact -v
```

Expected: PASS.

- [x] **Step 5: Write failing repository tests**

Create tests named
`test_recoverable_intent_open_supersedes_previous_open_for_conversation`,
`test_recoverable_intent_expires_on_read_after_expiry`, and
`test_recoverable_intent_consumes_only_matching_facts_hash`. The first test
creates two open artifacts for one conversation and asserts the older artifact
becomes `superseded`; the second reads after `expires_at` and asserts the
artifact becomes `expired`; the third consumes with a wrong hash and expects an
error, then consumes with the matching hash and asserts `status == "consumed"`.

- [x] **Step 6: Run repository tests and verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_recoverable_scheduling_intent.py -v
```

Expected: FAIL with missing repository/service methods.

- [x] **Step 7: Implement repository methods**

Add protocol, in-memory, and Postgres methods named
`save_recoverable_intent`, `open_recoverable_intent_for_conversation`, and
`consume_recoverable_intent`. `save_recoverable_intent` writes the artifact and
supersedes any previous open artifact for that conversation.
`open_recoverable_intent_for_conversation` returns only an open unexpired
artifact, marking expired artifacts as `expired` before returning `None`.
`consume_recoverable_intent` requires a matching `facts_hash`, writes
`consumed_turn_id`, and returns the consumed artifact.

Postgres reads must return `None` for invalid UUID strings rather than throwing.

- [x] **Step 8: Run repository tests and verify green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_recoverable_scheduling_intent.py tests/unit/coke/social_scheduling/test_social_scheduling_schema_contract.py -v
```

Expected: PASS.

- [x] **Step 9: Commit schema/domain artifact slice**

Commit:

```bash
git add coke/schema.py migrations/versions/20260607_0001_recoverable_scheduling_intent.py coke/domains/social_scheduling/models.py coke/domains/social_scheduling/repository.py tests/unit/coke/social_scheduling/test_social_scheduling_schema_contract.py tests/unit/coke/social_scheduling/test_recoverable_scheduling_intent.py
git commit -m $'feat: add recoverable scheduling intent store\n\nCo-Authored-By: Codex <noreply@openai.com>'
```

## Task 2: Semantic Follow-Up Action

**Files:**
- Modify: `coke/turn/semantic_interpreter.py`
- Modify: `coke/llm/semantic_interpreter.py`
- Modify: `tests/unit/coke/llm/test_semantic_interpreter.py`

- [x] **Step 1: Write failing semantic tests**

Add tests named
`test_interpret_accepts_friend_reference_correction_follow_up_action`,
`test_interpret_rejects_invalid_follow_up_action_type`, and
`test_interpret_prompt_exposes_friend_reference_correction_action`.

The accepted action payload is:

```python
{
    "type": "resolve_friend_reference_correction",
    "prior_reference_text": "zihao",
    "corrected_friend_text": "olivers",
    "scope": "immediately_preceding_unresolved_intent",
}
```

- [x] **Step 2: Run semantic tests and verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_semantic_interpreter.py::test_interpret_accepts_friend_reference_correction_follow_up_action tests/unit/coke/llm/test_semantic_interpreter.py::test_interpret_rejects_invalid_follow_up_action_type tests/unit/coke/llm/test_semantic_interpreter.py::test_interpret_prompt_exposes_friend_reference_correction_action -v
```

Expected: FAIL with missing `follow_up_action`.

- [x] **Step 3: Implement typed action**

Add `FollowUpAction` dataclass and optional `follow_up_action` field to
`SemanticDecision`. Validate optional action mappings in the LLM semantic
interpreter. Add prompt guidance that corrections are semantic actions, not
runner keyword routes.

- [x] **Step 4: Run semantic tests and verify green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_semantic_interpreter.py -v
```

Expected: PASS.

- [x] **Step 5: Commit semantic action slice**

Commit:

```bash
git add coke/turn/semantic_interpreter.py coke/llm/semantic_interpreter.py tests/unit/coke/llm/test_semantic_interpreter.py
git commit -m $'feat: classify friend correction follow ups\n\nCo-Authored-By: Codex <noreply@openai.com>'
```

## Task 3: SocialSchedulingOutcome And Structured Output Claims

**Files:**
- Modify: `coke/domains/social_scheduling/models.py`
- Modify: `coke/turn/output_protocol.py`
- Modify: `tests/unit/coke/turn/test_output_protocol.py`

- [x] **Step 1: Write failing output protocol tests**

Add tests named `test_social_scheduling_claim_matches_created_outcome`,
`test_social_scheduling_claim_rejects_staged_pending_close_success`,
`test_social_scheduling_claim_rejects_missing_claim_when_required`, and
`test_social_scheduling_claim_rejects_blocker_mismatch`.

Each test should call a new validator entry point with trusted outcomes and a
reply object containing optional `domain_claim`.

- [x] **Step 2: Run output protocol tests and verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_output_protocol.py -v
```

Expected: FAIL for missing social-scheduling claim validation.

- [x] **Step 3: Implement outcome and claim validation**

Add `SocialSchedulingOutcome`, status/claim literals, and a helper such as:

```python
def validate_social_scheduling_claim(
    self,
    validated: ValidatedOutput,
    *,
    outcomes: Sequence[Mapping[str, Any]],
) -> ValidatedOutput:
    return validated
```

`ValidatedOutput` should carry `domain_claim` when present. Keep phrase checks
out of production validation.

- [x] **Step 4: Run output protocol tests and verify green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_output_protocol.py -v
```

Expected: PASS.

- [x] **Step 5: Commit output contract slice**

Commit:

```bash
git add coke/domains/social_scheduling/models.py coke/turn/output_protocol.py tests/unit/coke/turn/test_output_protocol.py
git commit -m $'feat: validate social scheduling reply claims\n\nCo-Authored-By: Codex <noreply@openai.com>'
```

## Task 4: Tool Outcomes And Interaction Agent Guard

**Files:**
- Modify: `coke/turn/agent.py`
- Modify: `coke/composition.py`
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `tests/unit/coke/test_social_scheduling_tool_adapter.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`

- [ ] **Step 1: Write failing tool adapter tests**

Add tests named
`test_staged_shared_reminder_tool_result_returns_social_outcome`,
`test_blocked_shared_reminder_tool_result_returns_blocked_outcome`, and
`test_recovered_shared_reminder_command_carries_recovery_ids`.

- [ ] **Step 2: Run tool adapter tests and verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_social_scheduling_tool_adapter.py -v
```

Expected: FAIL for missing `social_scheduling_outcome` facts.

- [ ] **Step 3: Implement tool outcome facts**

Map existing service statuses:

```text
created -> created_active
duplicate -> duplicate_active
blocked + conflicting_participants -> blocked_receiver_conflict
blocked + unreachable_participants -> blocked_unreachable_participant
needs_participants + unmatched reference -> blocked_unmatched_friend
needs_participants + ambiguous reference -> blocked_ambiguous_friend
needs_* -> same needs_* status
staged -> staged_pending_close
```

Return outcome in `facts["social_scheduling_outcome"]` and in
`DomainExecutionResult.reply_contract`.

- [ ] **Step 4: Write failing interaction-agent tests**

Add/update tests named `test_social_scheduling_outcome_block_is_in_prompt`,
`test_created_shared_reminder_rejects_pending_structured_claim`,
`test_no_social_outcome_rejects_structured_success_claim`,
`test_blocked_social_outcome_requires_matching_blocker_claim`, and
`test_deterministic_shared_reminder_friend_helpers_are_removed`.

The deterministic-helper removal test should assert the fake Agno model is
called for ambiguous friend input rather than bypassed by helper code.

- [ ] **Step 5: Run interaction-agent tests and verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_social_scheduling_outcome_block_is_in_prompt tests/unit/coke/llm/test_interaction_agent.py::test_created_shared_reminder_rejects_pending_structured_claim tests/unit/coke/llm/test_interaction_agent.py::test_no_social_outcome_rejects_structured_success_claim tests/unit/coke/llm/test_interaction_agent.py::test_blocked_social_outcome_requires_matching_blocker_claim tests/unit/coke/llm/test_interaction_agent.py::test_deterministic_shared_reminder_friend_helpers_are_removed -v
```

Expected: FAIL before guard/removal.

- [ ] **Step 6: Implement interaction-agent outcome handling**

Carry `tool_events` on `AgentResult`, add prompt blocks for social outcomes,
validate output claims using `OutputProtocolValidator`, and delete
`_try_resolved_shared_reminder_followup`,
`_try_ambiguous_shared_reminder_friend_question`, and their private regex
helpers.

- [ ] **Step 7: Run tool and interaction-agent tests and verify green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit interaction/tool slice**

Commit:

```bash
git add coke/turn/agent.py coke/composition.py coke/llm/agno_interaction_agent.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/llm/test_interaction_agent.py
git commit -m $'feat: enforce social scheduling outcome replies\n\nCo-Authored-By: Codex <noreply@openai.com>'
```

## Task 5: Turn Runner Recovery Creation And Consumption

**Files:**
- Modify: `coke/turn/runner.py`
- Modify: `coke/domains/social_scheduling/service.py`
- Modify: `coke/domains/social_scheduling/repository.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Modify: `tests/unit/coke/social_scheduling/test_recoverable_scheduling_intent.py`

- [ ] **Step 1: Write failing service recovery tests**

Add tests named
`test_create_recoverable_intent_from_blocked_unmatched_outcome`,
`test_resolve_corrected_friend_text_returns_exact_single_match`, and
`test_resolve_corrected_friend_text_reports_ambiguous_matches`.

- [ ] **Step 2: Run service recovery tests and verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_recoverable_scheduling_intent.py -v
```

Expected: FAIL until service helpers exist.

- [ ] **Step 3: Implement service helpers**

Add methods named `create_recoverable_intent_from_outcome`,
`recoverable_intent_for_correction`, `resolve_active_friend_reference`, and
`consume_recoverable_intent`. `resolve_active_friend_reference` takes
`account_id: str` and `text: str` and returns a `FriendResolutionResult` with
`status` set to `matched`, `ambiguous`, or `unmatched`.

Use normalized display name/account id matching only for active friends.

- [ ] **Step 4: Run service recovery tests and verify green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_recoverable_scheduling_intent.py -v
```

Expected: PASS.

- [ ] **Step 5: Write failing runner tests**

Add or replace tests named
`test_blocked_unmatched_friend_close_creates_recoverable_intent`,
`test_friend_alias_correction_injects_recoverable_intent_fact`,
`test_unrelated_friend_correction_does_not_inject_recovery`,
`test_ambiguous_friend_correction_asks_one_agent_confirmation`, and
`test_superseded_consuming_turn_does_not_consume_recoverable_intent`.

Update older tests that expected history-reconstructed
`pending_clarification_resolution` for shared-reminder friend recovery.

- [ ] **Step 6: Run runner tests and verify red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_blocked_unmatched_friend_close_creates_recoverable_intent tests/unit/coke/turn/test_turn_runner.py::test_friend_alias_correction_injects_recoverable_intent_fact tests/unit/coke/turn/test_turn_runner.py::test_unrelated_friend_correction_does_not_inject_recovery tests/unit/coke/turn/test_turn_runner.py::test_ambiguous_friend_correction_asks_one_agent_confirmation tests/unit/coke/turn/test_turn_runner.py::test_superseded_consuming_turn_does_not_consume_recoverable_intent -v
```

Expected: FAIL until runner recovery wiring exists.

- [ ] **Step 7: Implement runner recovery wiring**

Add a SocialScheduling recovery port to `TurnRunner` through constructor or
existing `tool_ports.social_scheduling_tool` service access. Before context
assembly, inspect `semantic_decision.follow_up_action`; if it is the correction
action and an open artifact resolves to exactly one active friend, inject
`recoverable_scheduling_intent`. If ambiguous/stale, inject
`recoverable_scheduling_intent_resolution` and use a constrained profile.

After successful `commit_reply`/fresh close, create blocked artifacts from
agent tool events and consume artifacts only when materialized recovered
commands with matching `recoverable_scheduling_intent_id` and `facts_hash`
closed successfully.

- [ ] **Step 8: Run runner tests and verify green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/social_scheduling/test_recoverable_scheduling_intent.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit runner recovery slice**

Commit:

```bash
git add coke/turn/runner.py coke/domains/social_scheduling/service.py coke/domains/social_scheduling/repository.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/social_scheduling/test_recoverable_scheduling_intent.py
git commit -m $'feat: recover blocked shared reminder friend corrections\n\nCo-Authored-By: Codex <noreply@openai.com>'
```

## Task 6: Architecture Documentation

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/superpowers/plans/2026-06-07-response-contract-recovery.md`

- [ ] **Step 1: Write documentation update**

Document that SocialScheduling owns `recoverable_scheduling_intent`, The Turn
injects social-scheduling outcomes as trusted dynamic facts, and the
Interaction Agent remains the only normal channel-visible prose producer.

- [ ] **Step 2: Run docs/routing check for doc edit**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
```

Expected: command exits 0 and suggests repo/doc/runtime surfaces.

- [ ] **Step 3: Commit docs and completed plan ticks**

Commit:

```bash
git add docs/ARCHITECTURE.md docs/superpowers/plans/2026-06-07-response-contract-recovery.md
git commit -m $'docs: document response outcome recovery contract\n\nCo-Authored-By: Codex <noreply@openai.com>'
```

## Task 7: Final Verification

**Files:**
- All touched files.

- [ ] **Step 1: Run touched unit tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn tests/unit/coke/llm tests/unit/coke/social_scheduling tests/unit/coke/test_social_scheduling_tool_adapter.py -v
```

Expected: PASS.

- [ ] **Step 2: Run requested broader unit command**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke -v
```

Expected: PASS.

- [ ] **Step 3: Run diff-aware verification suggestion**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
```

Expected: exit 0. Follow any suggested `verify-surface` command.

- [ ] **Step 4: Run review trigger report**

Run:

```bash
zsh scripts/review-trigger --base HEAD~1
```

Expected: exit 0 or non-blocking risk report. Record output.

- [ ] **Step 5: Run suggested surface**

Run the exact `zsh scripts/verify-surface <surface>` command printed by Step 3.
Expected: PASS. If the command suggests multiple surfaces, run each.

- [ ] **Step 6: Final git status and commit audit**

Run:

```bash
git status --short
git log --oneline --decorate -8
```

Expected: working tree clean except intentionally uncommitted evidence, and
all workstream commits include `Co-Authored-By: Codex <noreply@openai.com>`.
