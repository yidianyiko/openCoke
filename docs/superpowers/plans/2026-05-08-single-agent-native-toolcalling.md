# Single Agent + Native Tool Calling Implementation Plan

> **Closeout status (2026-05-09):** this plan has been executed and merged
> locally into `main` as merge commit `7a8ca61`, from
> `feature/single-agent-native-toolcalling` head `a88524e`. The unchecked
> task boxes below are the original execution checklist, kept for audit trail;
> do not treat them as current TODOs without first comparing against `main`.

> **For future agentic workers:** if this plan is reopened, use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans before changing code. Re-verify the current
> code before following any dated step.

**Goal:** Replace the fake-Team runtime with a single Agno `Agent` that uses native tool calling, removing the RESPONSE/REQUEST text protocol, the manager retry loops, and the parser layer — while preserving every user-visible behavior of Phase 1.

**Architecture:** A new `agent/agno_agent/runtime/agent_runtime.py` constructs an Agno `Agent` per turn, registers four async tool wrappers (`reminder_intent`, `timezone`, `calendar_import`, `url_context`) that capture typed `CapabilityResult` objects through a per-run closure, and returns `AgentRunResult` to `event_adapter.run_agent_runtime_event`. `event_adapter` becomes the single dict→typed conversion boundary and the only constructor of `AgentRunContext`. The cutover is a 5-slice rollout: runner reliability fixes → new runtime behind fakes → production cutover → deletion → doc updates.

**Tech Stack:** Python 3.11+, Agno 2.5.9 (`agno.agent.Agent`, native tool calling, `arun`), pytest with hand-written fakes at the Agno boundary, MongoDB-backed reminder DAO (already wired through `ReminderCommandExecutor`).

**Spec source of truth:** `docs/superpowers/specs/2026-05-08-single-agent-native-toolcalling-design.md`. When this plan and the spec disagree on contract definitions, the spec wins; when they disagree on sequencing/PR boundaries, this plan wins.

---

## Current Result

Implemented and merged locally:

- `event_adapter.run_agent_runtime_event` now builds `AgentRunContext` at the
  entry boundary and calls `agent_runtime.run_agent_runtime`.
- `agent/agno_agent/runtime/agent_runtime.py` constructs one Agno `Agent` per
  turn and registers native tool wrappers for `reminder_intent`, `timezone`,
  `calendar_import`, and `url_context`.
- Tool wrappers keep the typed `CapabilityResult` side-channel for durable
  write and visible-output decisions while exposing only a JSON-serializable
  model-facing envelope.
- Deterministic output rules, final-text extraction, durable-write contract
  checks, fail-closed error mapping, async-offload coverage, and unknown-tool
  coverage are represented in focused unit tests.
- Former Team-runtime files and protocol tests were deleted:
  `team_runtime.py`, `selector.py`, `plan_parser.py`, `prompts/manager.py`,
  `capabilities/context_port.py`, `adapters/output_disposition.py`, and their
  obsolete tests.
- Canonical docs were updated to describe the single-Agent runtime:
  `docs/ARCHITECTURE.md`, `docs/design-docs/coke-working-contract.md`,
  `docs/fitness/coke-verification-matrix.md`, and `docs/roadmap.md`.

Latest verification evidence on merged `main`:

```bash
zsh scripts/verify-surface worker-runtime repo-os
```

Result: passed.

Current review result:

- No current canonical-doc references remain for `Agent Runtime Team`,
  `team_runtime`, `AGENT_RUNTIME_VERSION=team`, `run_team_runtime`,
  `selector.py`, `plan_parser.py`, `prompts/manager.py`,
  `capabilities/context_port.py`, or `adapters/output_disposition.py`.
- `agent/agno_agent/capabilities/url_context_port.py` remains intentionally;
  it is the current URL tool port, not the deleted `context_port.py`.
- The local worktree still has unrelated deleted reminder evidence files under
  `artifacts/evidence/`; this closeout does not restore or remove them.

Remaining gap:

- `tests/eval/test_real_model_native_toolcalling_smoke.py` is present, but
  the local verification did not enable `AGENT_RUNTIME_REAL_MODEL_SMOKE=1`.
  Real provider native-tool behavior therefore remains an explicit smoke gap
  until that opt-in gate is run in a configured environment.

---

## File Structure

### Files created in this plan

- `agent/agno_agent/runtime/agent_runtime.py` — new entry point. Owns Agno `Agent` construction, tool registration, `arun` invocation, "Agno final text" extraction from `RunOutput.messages`, deterministic visible-output rule precedence, fail-closed exception mapping, `post_analyze_input` derivation. Public callable: `async def run_agent_runtime(*, agent_input: AgentInput, run_context: AgentRunContext) -> AgentRunResult`.
- `agent/agno_agent/runtime/tool_wrappers.py` — async tool wrappers for each capability, each producing the model-facing JSON envelope and appending the captured `CapabilityResult` to a per-run list passed by closure.
- `agent/agno_agent/runtime/chat_response_instructions.py` — runtime-local prompt builder that imports `INSTRUCTIONS_CHAT_RESPONSE` and applies the keep/remove rules from the **System Prompt** section of the spec.
- `tests/unit/agent/test_agent_runtime_construction.py` — covers Agno boundary construction, fail-closed exception mapping, `post_analyze_input` derivation.
- `tests/unit/agent/test_agent_runtime_output_rules.py` — covers the five output rules in order, including the regression case `requires_response_synthesis=True` + empty Agno final text + prior `visible_summary` → rule 2 fires.
- `tests/unit/agent/test_agent_runtime_envelope.py` — covers model-facing JSON envelope projection (envelope `name` is the tool function name, internal-only fields stripped).
- `tests/unit/agent/test_agent_runtime_async_offload.py` — covers blocking-I/O offload inside async wrappers.
- `tests/unit/agent/test_agent_runtime_unknown_tool.py` — covers fail-closed dispatch when the model emits an unregistered tool name.
- `tests/unit/agent/test_agent_runtime_durable_write_contract.py` — covers durable-write classification rule 5 (success and contract violation).
- `tests/unit/agent/test_agent_runtime_final_text_extraction.py` — covers "Agno final text" extraction from `RunOutput.messages`.
- `tests/unit/agent/test_chat_response_instructions.py` — prompt-cleaning invariant test.
- `tests/unit/agent/test_reminder_intent_retry_schema.py` — covers Related Contract Fix #7 (cancel parity).
- `tests/unit/runner/test_agent_handler_inflight_interrupt.py` — covers Related Contract Fix #3 send-loop and fallback paths.
- `tests/eval/test_real_model_native_toolcalling_smoke.py` — staging real-model smoke for `reminder_intent`, `timezone`, `url_context`.
- `artifacts/evidence/2026-05-XX-pre-cutover-baseline/` — directory holding pre-cutover evidence bundle (focused tests + reminder-normal smoke + grafana / log snapshot).

### Files modified in this plan

- `agent/runner/reminder_event_handler.py:65-70`, `:87-92`, `:133-134` — replace bare `except Exception:` with `logger.exception(...)` (Slice A, Fix 1).
- `agent/runner/deferred_action_executor.py:109-205` — hoist `occurrence` binding outside `try` (Slice A, Fix 2).
- `agent/runner/agent_handler.py:648-768` — re-check `is_new_message_coming_in` before every outbound write, including the empty-output fallback path (Slice A, Fix 3).
- `agent/agno_agent/runtime/context.py:118-119` — drop `_metadata_from_raw`'s `{"raw": raw}` payload; expose only validated metadata (Slice A or Slice B, Fix 4).
- `agent/agno_agent/runtime/event_adapter.py` — call `agent_runtime.run_agent_runtime` instead of `run_team_runtime`; never forward the legacy `context` dict downstream (Slice C).
- `agent/agno_agent/capabilities/reminder_intent.py:76-108` — add `cancel` to the retry-prompt action list (Slice A or Slice B, Fix 7).
- `agent/runner/agent_handler.py:440-526` — delete `_guard_pending_reminder_stop_response`, `_guard_unconfirmed_reminder_response_after_prepare_timeout`, `_is_clawscale_sync_text_reply_context` (Slice D, Fix 5).
- `agent/agno_agent/runtime/result.py` — add `with_output_references` (relocated from `adapters/output_disposition.py`) (Slice D).
- `agent/runner/deferred_action_executor.py` — switch import of `with_output_references` to `agent.agno_agent.runtime.result` (Slice D).
- `agent/agno_agent/runtime/__init__.py` — drop `run_deferred_action_runtime_event` re-export and `select_runtime` / `RuntimeVersion` / `RuntimeSelectionInput` re-exports after Slice C (Slice D).
- `docs/architecture.md:179` — describe single-Agent runtime (Slice E).
- `docs/design-docs/coke-working-contract.md:28` — drop "Agent Runtime Team" terminology (Slice E).
- `docs/fitness/coke-verification-matrix.md:66, :71` — replace Team-specific commands (Slice E).

### Files deleted in this plan

- `agent/agno_agent/runtime/team_runtime.py` (Slice D).
- `agent/agno_agent/runtime/selector.py` (Slice D).
- `agent/agno_agent/runtime/plan_parser.py` (Slice D).
- `agent/agno_agent/prompts/manager.py` (Slice D).
- `agent/agno_agent/capabilities/context_port.py` (Slice D).
- `agent/agno_agent/adapters/output_disposition.py` (Slice D).
- `tests/unit/agent/test_team_runtime_plan_parser.py` (Slice D).
- `tests/unit/agent/test_team_runtime_construction.py` (Slice D).
- `tests/unit/agent/test_team_runtime_execution.py` (Slice D).
- `tests/unit/agent/test_team_runtime_parity.py` (Slice D).
- `tests/unit/agent/test_agent_runtime_selector.py` (Slice D).
- `tests/unit/agent/test_context_port.py` (Slice D).

---

## Pre-flight (one-time, before Slice A)

- [ ] **Step 0.1: Create the worktree**

```bash
git worktree add ../coke-single-agent -b feature/single-agent-native-toolcalling
cd ../coke-single-agent
```

Expected: a clean working tree on the feature branch.

- [ ] **Step 0.2: Verify dependencies and the current parity baseline**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/ tests/unit/runner/ -v --no-header 2>&1 | tee /tmp/baseline-pre-slice-a.log
```

Expected: a record of the current pass/fail set. We do NOT require green — we record the baseline so Slice A can compare against it.

- [ ] **Step 0.3: Confirm Agno version pin**

Run:

```bash
grep '^agno==' requirements.txt
```

Expected: `agno==2.5.9`. The plan's offload assumptions in `Model.arun_function_call` are valid for this exact pin.

---

## Slice A — Runner reliability fixes (no runtime replacement)

**Goal:** narrow Slice C's blast radius by landing reliability fixes that do not depend on the new runtime, and capture a measurable parity baseline.

### Task A1: Capture pre-fix baseline evidence

**Files:**
- Create: `artifacts/evidence/2026-05-XX-pre-cutover-baseline/baseline-team-runtime.txt`

- [ ] **Step 1: Create the evidence directory**

```bash
mkdir -p artifacts/evidence/2026-05-XX-pre-cutover-baseline
```

- [ ] **Step 2: Run the focused worker/runtime tests against current `main` and capture output**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/ tests/unit/runner/ -v 2>&1 \
  | tee artifacts/evidence/2026-05-XX-pre-cutover-baseline/baseline-team-runtime.txt
```

Expected: file contains the pass/fail summary for these directories under the current Team runtime. Failures are recorded, not fixed here.

- [ ] **Step 3: Run the reminder-normal smoke and capture its output**

Run:

```bash
AGENT_RUNTIME_VERSION=team .venv/bin/python scripts/eval_reminder_normal_path_cases.py 2>&1 \
  | tee artifacts/evidence/2026-05-XX-pre-cutover-baseline/baseline-reminder-normal.txt
```

Expected: file contains the smoke result for the current Team runtime. We will diff against this in Slice C.

- [ ] **Step 4: Commit the baseline bundle**

```bash
git add artifacts/evidence/2026-05-XX-pre-cutover-baseline
git commit -m "evidence(agent): capture pre-cutover Team runtime baseline"
```

### Task A2: Fix #1 — `reminder_event_handler.py` exception logging

**Files:**
- Modify: `agent/runner/reminder_event_handler.py:65-70, :87-92, :133-134`
- Test: `tests/unit/runner/test_reminder_event_handler.py`

- [ ] **Step 1: Write a failing test that asserts `logger.exception` is invoked when the replay lookup raises**

Add this test to `tests/unit/runner/test_reminder_event_handler.py` (alongside existing tests; copy the existing fixture pattern for `ReminderFireEventHandler` construction):

```python
def test_replay_lookup_failure_logs_exception(monkeypatch, caplog):
    handler, event = _build_handler_with_failing_replay_lookup(monkeypatch)
    caplog.set_level("ERROR")
    result = asyncio.get_event_loop().run_until_complete(handler.handle(event))
    assert result.ok is False
    assert any(
        "ReplayLookupFailed" in record.message and record.exc_info
        for record in caplog.records
    )
```

The helper `_build_handler_with_failing_replay_lookup` should return a fixture with an `existing_output_lookup` that raises `RuntimeError("boom")` on call. Reuse the existing handler-builder pattern in this file; do not invent a new pattern.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/runner/test_reminder_event_handler.py::test_replay_lookup_failure_logs_exception -v`

Expected: FAIL — current code uses `except Exception:` with no logging.

- [ ] **Step 3: Replace bare `except Exception:` with `logger.exception(...)` at line 67**

In `agent/runner/reminder_event_handler.py:65-70`, change:

```python
        try:
            existing_output = self.existing_output_lookup(event)
        except Exception:
            return self._failure(
                event, "ReplayLookupFailed", "reminder replay lookup failed"
            )
```

to:

```python
        try:
            existing_output = self.existing_output_lookup(event)
        except Exception:
            logger.exception("reminder replay lookup failed before lock")
            return self._failure(
                event, "ReplayLookupFailed", "reminder replay lookup failed"
            )
```

- [ ] **Step 4: Replace the inner replay-lookup `except Exception:` at line 89**

Change:

```python
            try:
                existing_output = self.existing_output_lookup(event)
            except Exception:
                return self._failure(
                    event, "ReplayLookupFailed", "reminder replay lookup failed"
                )
```

to:

```python
            try:
                existing_output = self.existing_output_lookup(event)
            except Exception:
                logger.exception("reminder replay lookup failed under lock")
                return self._failure(
                    event, "ReplayLookupFailed", "reminder replay lookup failed"
                )
```

- [ ] **Step 5: Add `logger.exception` before re-raise / failure-return at line 133**

Change:

```python
        except Exception as exc:
            return self._failure(event, "OutputFailed", str(exc))
```

to:

```python
        except Exception as exc:
            logger.exception("reminder fire output failed")
            return self._failure(event, "OutputFailed", str(exc))
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/runner/test_reminder_event_handler.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add agent/runner/reminder_event_handler.py tests/unit/runner/test_reminder_event_handler.py
git commit -m "fix(runner): log replay-lookup and output failures in reminder fire handler"
```

### Task A3: Fix #2 — `deferred_action_executor.py` `occurrence` scope

**Files:**
- Modify: `agent/runner/deferred_action_executor.py:109-205`
- Test: `tests/unit/runner/test_deferred_action_executor.py`

- [ ] **Step 1: Write a failing test that asserts the executor returns `"failed"` (not raises `NameError`) when `claim_or_get_occurrence` raises**

Add this test to `tests/unit/runner/test_deferred_action_executor.py` (reuse existing fixtures):

```python
def test_occurrence_claim_failure_returns_failed_without_nameerror():
    executor = _build_executor_with_failing_occurrence_dao()
    result = asyncio.run(executor.execute_due_action(action_id="A1", scheduled_for=_NOW, revision=1))
    assert result == "failed"
```

The helper `_build_executor_with_failing_occurrence_dao` configures `occurrence_dao.claim_or_get_occurrence` to raise `RuntimeError("db down")` and ensures the action lock can be acquired. Pattern this on the existing executor fixtures in the same file.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/runner/test_deferred_action_executor.py::test_occurrence_claim_failure_returns_failed_without_nameerror -v`

Expected: FAIL with `NameError: name 'occurrence' is not defined` raised inside the `except Exception` block.

- [ ] **Step 3: Hoist the `occurrence` binding outside the `try`**

In `agent/runner/deferred_action_executor.py:109`, change:

```python
        try:
            occurrence = self.occurrence_dao.claim_or_get_occurrence(
                action_id=action_id,
                trigger_key=trigger_key,
                scheduled_for=scheduled_for,
                started_at=started_at,
            )
            ...
```

to:

```python
        occurrence: dict[str, Any] = {}
        try:
            occurrence = self.occurrence_dao.claim_or_get_occurrence(
                action_id=action_id,
                trigger_key=trigger_key,
                scheduled_for=scheduled_for,
                started_at=started_at,
            )
            ...
```

Then, in the `except Exception as exc:` block at line 186, replace:

```python
            attempt_count = int(occurrence.get("attempt_count", 1))
```

with the safe form (works whether or not the occurrence claim succeeded):

```python
            attempt_count = int((occurrence or {}).get("attempt_count", 1))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/runner/test_deferred_action_executor.py -v`

Expected: PASS, including pre-existing tests.

- [ ] **Step 5: Commit**

```bash
git add agent/runner/deferred_action_executor.py tests/unit/runner/test_deferred_action_executor.py
git commit -m "fix(runner): hoist occurrence binding so NameError cannot shadow original failure"
```

### Task A4: Fix #3 — `agent_handler.py` in-flight interrupt re-checks

**Files:**
- Modify: `agent/runner/agent_handler.py:648-768`
- Create: `tests/unit/runner/test_agent_handler_inflight_interrupt.py`

- [ ] **Step 1: Write the failing test for the per-message send-loop re-check**

Create `tests/unit/runner/test_agent_handler_inflight_interrupt.py`:

```python
import asyncio
from unittest.mock import patch

from agent.runner import agent_handler


def _build_handle_message_kwargs_with_visible_messages(
    monkeypatch,
    *,
    visible_message_count: int,
    output_status: str,
):
    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )

    visible = tuple(
        VisibleMessage(message_type="text", content=f"msg-{i}") for i in range(visible_message_count)
    )
    fake_result = AgentRunResult(
        visible_messages=visible,
        post_analyze_input={"input_message": "hi", "message_source": "user"} if visible else None,
        tool_results=(),
        metrics={},
        trace={},
        output_disposition=OutputDisposition(status=output_status),
    )

    async def _fake_run(**_kwargs):
        return fake_result

    monkeypatch.setattr(agent_handler, "_run_agent_runtime_event", _fake_run)
    monkeypatch.setattr(agent_handler, "_verify_lock_ownership", lambda *_a, **_k: True)
    monkeypatch.setattr(agent_handler, "_team_should_skip_post_analyze", lambda: True)

    return dict(
        context={
            "user": {"id": "u1", "nickname": "Alice"},
            "character": {"id": "c1", "name": "Coke"},
            "conversation": {
                "id": "conv1",
                "platform": "business",
                "conversation_info": {"chat_history": [], "input_messages": []},
            },
            "relation": {"uid": "u1", "cid": "c1"},
            "platform": "business",
        },
        input_message_str="hi",
        message_source="user",
        metadata={},
        check_new_message=True,
        worker_tag="[TEST]",
        lock_id=None,
        conversation_id="conv1",
        current_message_ids=["m1"],
    )


def _build_user_turn_context_with_one_visible_message(monkeypatch):
    return _build_handle_message_kwargs_with_visible_messages(
        monkeypatch, visible_message_count=2, output_status="ok"
    )


def _build_user_turn_context_with_empty_runtime_output(monkeypatch):
    return _build_handle_message_kwargs_with_visible_messages(
        monkeypatch, visible_message_count=0, output_status="empty"
    )


def test_send_loop_aborts_when_new_message_arrives_between_sends(monkeypatch):
    kwargs = _build_user_turn_context_with_one_visible_message(monkeypatch)
    # Order of `is_new_message_coming_in` calls under the new code:
    #   1. pre-runtime check (line ~656): False
    #   2. before first visible-message send: False
    #   3. before second visible-message send: True → rollback
    interrupt_states = iter([False, False, True])
    monkeypatch.setattr(
        agent_handler,
        "is_new_message_coming_in",
        lambda *args, **kw: next(interrupt_states),
    )
    sent: list[str] = []

    def _capture_send(**send_kwargs):
        sent.append(send_kwargs["multimodal_response"]["content"])
        return {"id": f"out-{len(sent)}"}, send_kwargs["expect_output_timestamp"]

    monkeypatch.setattr(agent_handler, "_send_single_message", _capture_send)
    resp_messages, _ctx, is_rollback, _blocked = asyncio.run(
        agent_handler.handle_message(**kwargs)
    )
    assert is_rollback is True
    assert sent == ["msg-0"]


def test_empty_output_fallback_skipped_when_new_message_arrives(monkeypatch):
    kwargs = _build_user_turn_context_with_empty_runtime_output(monkeypatch)
    # Calls: 1. pre-runtime (False), 2. before fallback send (True → rollback)
    interrupt_states = iter([False, True])
    monkeypatch.setattr(
        agent_handler,
        "is_new_message_coming_in",
        lambda *args, **kw: next(interrupt_states),
    )
    fallback_called = {"value": False}

    def _fallback(**_kw):
        fallback_called["value"] = True
        return None, 0

    monkeypatch.setattr(agent_handler, "_send_chat_response_fallback", _fallback)
    _, _ctx, is_rollback, _blocked = asyncio.run(agent_handler.handle_message(**kwargs))
    assert fallback_called["value"] is False
    assert is_rollback is True
```

The two helpers `_build_user_turn_context_with_one_visible_message` and `_build_user_turn_context_with_empty_runtime_output` mirror existing handler fixtures in `tests/unit/runner/`; copy the same patching shape used by `test_typed_runtime_events.py`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/runner/test_agent_handler_inflight_interrupt.py -v`

Expected: FAIL — the second send fires today, and the fallback fires today.

- [ ] **Step 3: Add per-message interrupt re-check in the visible-message send loop**

In `agent/runner/agent_handler.py` around line 721 (the `for visible_message in result.visible_messages:` loop), insert the check before each `_send_single_message` call:

```python
        for visible_message in result.visible_messages:
            multimodal_response = {
                "type": visible_message.message_type,
                "content": visible_message.content,
                "metadata": dict(visible_message.metadata),
            }

            if check_new_message and message_source == "user":
                if is_new_message_coming_in(
                    get_agent_entity_id(user),
                    get_agent_entity_id(character),
                    current_platform,
                    current_message_ids,
                ):
                    logger.info(f"{worker_tag} rollback: new message during send loop")
                    context["MultiModalResponses"] = all_multimodal_responses
                    return resp_messages, context, True, False

            if lock_id and conversation_id:
                if not _verify_lock_ownership(conversation_id, lock_id):
                    logger.warning(f"{worker_tag} 锁已丢失，停止发送 Team 消息")
                    context["MultiModalResponses"] = all_multimodal_responses
                    return resp_messages, context, True, False

            all_multimodal_responses.append(multimodal_response)
            outputmessage, expect_output_timestamp = _send_single_message(
                context=context,
                multimodal_response=multimodal_response,
                expect_output_timestamp=expect_output_timestamp,
                is_first=(len(all_multimodal_responses) == 1),
            )
            if outputmessage is not None:
                resp_messages.append(outputmessage)
```

- [ ] **Step 4: Add the same re-check before the empty-output fallback path**

In `agent/runner/agent_handler.py` around line 744 (`if not resp_messages and not result.visible_messages and result.output_disposition.status == "empty":`), wrap `_send_chat_response_fallback` similarly:

```python
        if (
            not resp_messages
            and not result.visible_messages
            and result.output_disposition.status == "empty"
        ):
            logger.warning(
                f"{worker_tag} AgentRuntime 未产出用户可见回复，发送兜底回复"
            )
            if check_new_message and message_source == "user":
                if is_new_message_coming_in(
                    get_agent_entity_id(user),
                    get_agent_entity_id(character),
                    current_platform,
                    current_message_ids,
                ):
                    logger.info(f"{worker_tag} rollback: new message before fallback send")
                    context["MultiModalResponses"] = all_multimodal_responses
                    return resp_messages, context, True, False

            if (
                lock_id
                and conversation_id
                and not _verify_lock_ownership(conversation_id, lock_id)
            ):
                logger.warning(f"{worker_tag} 锁已丢失，跳过 Team 兜底回复")
                context["MultiModalResponses"] = all_multimodal_responses
                return resp_messages, context, True, False

            outputmessage, expect_output_timestamp = _send_chat_response_fallback(
                context=context,
                input_message=input_message_str,
                expect_output_timestamp=expect_output_timestamp,
                all_multimodal_responses=all_multimodal_responses,
            )
            if outputmessage is not None:
                resp_messages.append(outputmessage)
```

Note: the lock-ownership check stays — lock ownership does not detect a fresh user message arriving while the lock is still held. Both checks are necessary.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/runner/test_agent_handler_inflight_interrupt.py tests/unit/runner/ -v`

Expected: PASS, no regressions in surrounding tests.

- [ ] **Step 6: Commit**

```bash
git add agent/runner/agent_handler.py tests/unit/runner/test_agent_handler_inflight_interrupt.py
git commit -m "fix(runner): re-check new-message interrupt before every outbound write including fallback"
```

### Task A5: Fix #4 — drop raw-dict smuggling in `context.py`

**Files:**
- Modify: `agent/agno_agent/runtime/context.py:118-119`
- Test: `tests/unit/agent/test_agent_runtime_types.py`

This is included in Slice A only because it is small and reviewable; if the diff grows or any caller depends on `metadata["raw"]`, defer to Slice B and re-baseline.

- [ ] **Step 1: Locate every call site that reads `AgentRunContext.user.metadata["raw"]` (or any `metadata.raw`)**

Run: `grep -rn 'metadata\(\["\\\'\)\]\?raw' agent/ tests/ --include='*.py'`

Expected: zero production hits. If any production hit appears, defer this fix to Slice B and skip to Task A6.

- [ ] **Step 2: Write a failing test that constructs `AgentRunContext` and asserts no `raw` key on any metadata mapping**

Add to `tests/unit/agent/test_agent_runtime_types.py`:

```python
def test_agent_run_context_metadata_does_not_smuggle_raw():
    legacy_context = {
        "user": {"id": "u1", "nickname": "Alice", "extra": "untrusted"},
        "character": {"id": "c1", "name": "Coke"},
        "conversation": {"id": "conv1", "platform": "business"},
        "relation": {"uid": "u1", "cid": "c1"},
        "platform": "business",
    }
    ctx = build_agent_run_context(legacy_context, current_time=datetime.now(UTC))
    assert "raw" not in ctx.user.metadata
    assert "raw" not in ctx.character.metadata
    assert "raw" not in ctx.conversation.metadata
    assert "raw" not in ctx.relation.metadata
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_types.py::test_agent_run_context_metadata_does_not_smuggle_raw -v`

Expected: FAIL — current `_metadata_from_raw` returns `{"raw": raw}`.

- [ ] **Step 4: Replace `_metadata_from_raw` body in `agent/agno_agent/runtime/context.py:118`**

Change:

```python
def _metadata_from_raw(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {"raw": raw} if raw else {}
```

to:

```python
def _metadata_from_raw(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Reserved for explicitly validated metadata; never smuggle untrusted dicts."""
    return {}
```

- [ ] **Step 5: Run unit tests**

Run: `.venv/bin/python -m pytest tests/unit/agent/ -v`

Expected: the new test PASSes; pre-existing tests pass except any that explicitly relied on `metadata["raw"]` (none should — verified in Step 1).

- [ ] **Step 6: Commit**

```bash
git add agent/agno_agent/runtime/context.py tests/unit/agent/test_agent_runtime_types.py
git commit -m "fix(runtime): stop smuggling raw legacy dict into AgentRunContext metadata"
```

### Task A6: Land Slice A

- [ ] **Step 1: Run the focused worker/runtime suite**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/ tests/unit/runner/ -v
```

Expected: green.

- [ ] **Step 2: Run repo-OS check**

Run: `zsh scripts/check`

Expected: green. If a check fails, fix it in Slice A before merging.

- [ ] **Step 3: Run the focused reminder-normal smoke**

Run: `AGENT_RUNTIME_VERSION=team .venv/bin/python scripts/eval_reminder_normal_path_cases.py`

Expected: parity with the baseline captured in Task A1.

- [ ] **Step 4: Open PR for Slice A**

```bash
git push -u origin feature/single-agent-native-toolcalling
gh pr create --title "[Slice A] Runner reliability fixes (no runtime replacement)" --body "$(cat <<'EOF'
## Summary
- Fix #1: log exceptions in reminder fire handler before failure return
- Fix #2: hoist occurrence binding so NameError cannot shadow original failure
- Fix #3: re-check new-message interrupt before every outbound write including fallback
- Fix #4: drop raw-dict smuggling in `AgentRunContext`
- Capture pre-cutover Team-runtime baseline evidence

Spec: docs/superpowers/specs/2026-05-08-single-agent-native-toolcalling-design.md
Plan: docs/superpowers/plans/2026-05-08-single-agent-native-toolcalling.md (Slice A)

## Test plan
- [x] tests/unit/agent/ tests/unit/runner/ green
- [x] zsh scripts/check green
- [x] reminder-normal smoke parity vs. baseline
EOF
)"
```

Expected: PR opened. Mark Slice A complete only after merge.

---

## Slice B — New runtime behind fakes + real-model smoke (no production traffic)

**Goal:** prove `agent_runtime.py` works in isolation. No production caller switches in this slice.

### Task B1: Skeleton `agent_runtime.py` and unit-test scaffold

**Files:**
- Create: `agent/agno_agent/runtime/agent_runtime.py`
- Create: `tests/unit/agent/test_agent_runtime_construction.py`

- [ ] **Step 1: Write the failing skeleton test**

Create `tests/unit/agent/test_agent_runtime_construction.py`:

```python
import asyncio
from datetime import UTC, datetime

import pytest

from agent.agno_agent.runtime.agent_runtime import run_agent_runtime
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload
from agent.agno_agent.runtime.result import AgentRunResult


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv1", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
        runtime_metadata={"message_source": "user"},
    )


def _input(text: str = "hi") -> AgentInput:
    return AgentInput(
        input_type="user.turn",
        conversation_id="conv1",
        text=text,
        payload=UserTurnPayload(),
        occurred_at=datetime.now(UTC),
    )


def test_run_agent_runtime_returns_agent_run_result_for_no_tool_run(monkeypatch):
    from agent.agno_agent.runtime import agent_runtime

    class _FakeRunOutput:
        def __init__(self, text: str) -> None:
            self.content = text
            self.messages = [{"role": "assistant", "content": text}]

    class _FakeAgent:
        async def arun(self, input: str, **kwargs):
            return _FakeRunOutput("hi back")

    monkeypatch.setattr(agent_runtime, "_create_agent", lambda **_: _FakeAgent())

    result = asyncio.run(run_agent_runtime(agent_input=_input(), run_context=_ctx()))
    assert isinstance(result, AgentRunResult)
    assert [m.content for m in result.visible_messages] == ["hi back"]
    assert result.output_disposition.status == "ok"
    assert result.tool_results == ()
    assert result.post_analyze_input == {"input_message": "hi", "message_source": "user"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_returns_agent_run_result_for_no_tool_run -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'agent.agno_agent.runtime.agent_runtime'`.

- [ ] **Step 3: Write the minimal `agent_runtime.py` skeleton**

Create `agent/agno_agent/runtime/agent_runtime.py`:

```python
from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.inputs import AgentInput
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
)

logger = logging.getLogger(__name__)


def _create_agent(
    *,
    run_context: AgentRunContext,
    input_message: str,
    tool_results: list[CapabilityResult],
) -> Any:
    """Construct the per-call Agno Agent. Replaced by Task B3 with full registration."""
    raise NotImplementedError  # pragma: no cover - filled in by Task B3


def _extract_final_text(run_output: Any) -> str:
    """Return the content of the last assistant message after the last tool result."""
    messages = list(getattr(run_output, "messages", []) or [])
    if not messages:
        content = getattr(run_output, "content", "") or ""
        return content if isinstance(content, str) else ""
    last_tool_index = -1
    for index, message in enumerate(messages):
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
        if role in {"tool", "tool_result"}:
            last_tool_index = index
    for message in messages[last_tool_index + 1 :][::-1]:
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        if role == "assistant" and isinstance(content, str):
            return content
    return ""


def _resolve_visible_text(
    *,
    final_text: str,
    tool_results: list[CapabilityResult],
) -> str:
    if tool_results and any(r.requires_response_synthesis for r in tool_results) and final_text.strip():
        return final_text
    summaries = [r.visible_summary for r in tool_results if r.visible_summary]
    if summaries:
        return "\n".join(summaries)
    if not tool_results:
        return final_text
    return ""


def _check_durable_write_contract(tool_results: list[CapabilityResult]) -> RuntimeErrorDisposition | None:
    for result in tool_results:
        if result.ok and result.durable_write and not result.visible_summary:
            return RuntimeErrorDisposition(
                code="durable_write_missing_visible_summary",
                retryable=False,
                metadata={"capability_name": result.name},
            )
    return None


async def run_agent_runtime(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
) -> AgentRunResult:
    if agent_input.input_type not in {"user.turn", "reminder.fired", "deferred_action.fire"}:
        raise ValueError(f"unsupported AgentInput.input_type: {agent_input.input_type}")
    input_message = agent_input.text or ""
    tool_results: list[CapabilityResult] = []
    try:
        agent = _create_agent(
            run_context=run_context,
            input_message=input_message,
            tool_results=tool_results,
        )
        run_output = await agent.arun(
            input=input_message,
            session_id=run_context.conversation.id,
        )
    except Exception as exc:  # fail-closed
        logger.exception("agent_runtime.run_agent_runtime failed")
        return AgentRunResult(
            visible_messages=(),
            post_analyze_input=None,
            tool_results=tuple(tool_results),
            metrics={"capability_result_count": len(tool_results)},
            trace={"runtime": "single_agent", "exception": exc.__class__.__name__},
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=RuntimeErrorDisposition(
                code="agent_runtime_exception",
                retryable=True,
            ),
        )

    final_text = _extract_final_text(run_output)
    contract_violation = _check_durable_write_contract(tool_results)
    if contract_violation is not None:
        return AgentRunResult(
            visible_messages=(),
            post_analyze_input=None,
            tool_results=tuple(tool_results),
            metrics={"capability_result_count": len(tool_results)},
            trace={"runtime": "single_agent", "contract_violation": contract_violation.code},
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=contract_violation,
        )

    visible_text = _resolve_visible_text(final_text=final_text, tool_results=tool_results)
    visible_messages = (
        (VisibleMessage(message_type="text", content=visible_text),) if visible_text else ()
    )
    message_source = str(run_context.runtime_metadata.get("message_source") or "user")
    post_analyze_input = (
        {"input_message": input_message, "message_source": message_source}
        if visible_messages
        else None
    )
    return AgentRunResult(
        visible_messages=visible_messages,
        post_analyze_input=post_analyze_input,
        tool_results=tuple(tool_results),
        metrics={"capability_result_count": len(tool_results)},
        trace={"runtime": "single_agent"},
        output_disposition=OutputDisposition(status="ok" if visible_messages else "empty"),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_construction.py
git commit -m "feat(runtime): introduce agent_runtime skeleton with fail-closed exception path"
```

### Task B2: Async tool wrapper module

**Files:**
- Create: `agent/agno_agent/runtime/tool_wrappers.py`
- Test: `tests/unit/agent/test_agent_runtime_envelope.py`

- [ ] **Step 1: Write the failing envelope test**

Create `tests/unit/agent/test_agent_runtime_envelope.py`:

```python
import asyncio
from datetime import UTC, datetime

from agent.agno_agent.capabilities import (
    CalendarImportPort,
    ReminderIntentPort,
    TimezonePort,
    UrlContextPort,
)
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.runtime.tool_wrappers import build_capability_tool_wrappers


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="UTC"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv1", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
    )


def test_reminder_envelope_uses_tool_function_name_not_capability_name():
    captured: list[CapabilityResult] = []

    class _StubReminderPort:
        async def run(self, input_message, run_context, args):
            return CapabilityResult(
                name="reminder",  # internal categorization
                ok=True,
                content={"visible_summary": "已为你设好提醒"},
                metadata={"durable_write": True},
            )

    wrappers = build_capability_tool_wrappers(
        ports={"reminder_intent": _StubReminderPort(),
               "timezone": TimezonePort(handler=lambda *a, **k: {"ok": True, "message": "ok"}),
               "calendar_import": CalendarImportPort(handler=lambda *a, **k: {"ok": True, "message": "ok"}),
               "url_context": UrlContextPort(url_reader=lambda text: {"items": [], "context": ""})},
        run_context=_ctx(),
        input_message="提醒我喝水",
        tool_results=captured,
    )
    envelope = asyncio.run(wrappers["reminder_intent"]())
    assert envelope["name"] == "reminder_intent"  # tool function name, not "reminder"
    assert envelope["ok"] is True
    assert envelope["content"] == {"visible_summary": "已为你设好提醒"}
    assert "durable_write" not in envelope and "metadata" not in envelope
    assert "requires_response_synthesis" not in envelope
    assert captured[0].name == "reminder"
    assert captured[0].durable_write is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_envelope.py -v`

Expected: FAIL — `tool_wrappers` module does not exist.

- [ ] **Step 3: Implement `tool_wrappers.py`**

Create `agent/agno_agent/runtime/tool_wrappers.py`:

```python
from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult

logger = logging.getLogger(__name__)

_TOOL_NAMES = ("reminder_intent", "timezone", "calendar_import", "url_context")


def _envelope(tool_name: str, capability_result: CapabilityResult) -> dict[str, Any]:
    """Project CapabilityResult to the model-facing JSON envelope. Strips internal fields."""
    return {
        "name": tool_name,
        "ok": capability_result.ok,
        "content": dict(capability_result.content),
        "error": capability_result.error,
    }


async def _await_or_offload(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _make_async_wrapper(
    *,
    tool_name: str,
    port: Any,
    run_context: AgentRunContext,
    input_message: str,
    tool_results: list[CapabilityResult],
) -> Callable[..., Awaitable[dict[str, Any]]]:
    async def _wrapper(**model_args: Any) -> dict[str, Any]:
        try:
            run_value = port.run(input_message, run_context, dict(model_args))
            if inspect.isawaitable(run_value):
                result = await run_value
            else:
                # Sync port: offload so blocking I/O does not pin the loop when an
                # async tool_hook routes us through Function.aexecute.
                result = await asyncio.to_thread(
                    lambda: port.run(input_message, run_context, dict(model_args))
                )
        except Exception as exc:
            logger.exception("tool wrapper %s raised", tool_name)
            failure = CapabilityResult(
                name=tool_name,
                ok=False,
                content={},
                error=f"{exc.__class__.__name__}: {exc}",
            )
            tool_results.append(failure)
            return _envelope(tool_name, failure)

        if not isinstance(result, CapabilityResult):
            failure = CapabilityResult(
                name=tool_name,
                ok=False,
                content={},
                error="capability returned non-CapabilityResult",
            )
            tool_results.append(failure)
            return _envelope(tool_name, failure)

        tool_results.append(result)
        return _envelope(tool_name, result)

    _wrapper.__name__ = tool_name
    return _wrapper


def build_capability_tool_wrappers(
    *,
    ports: Mapping[str, Any],
    run_context: AgentRunContext,
    input_message: str,
    tool_results: list[CapabilityResult],
) -> dict[str, Callable[..., Awaitable[dict[str, Any]]]]:
    wrappers: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {}
    for name in _TOOL_NAMES:
        port = ports.get(name)
        if port is None:
            continue
        wrappers[name] = _make_async_wrapper(
            tool_name=name,
            port=port,
            run_context=run_context,
            input_message=input_message,
            tool_results=tool_results,
        )
    return wrappers
```

- [ ] **Step 4: Run the envelope test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_envelope.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/runtime/tool_wrappers.py tests/unit/agent/test_agent_runtime_envelope.py
git commit -m "feat(runtime): add async tool wrappers projecting CapabilityResult to model-facing envelope"
```

### Task B3: Wire tool wrappers into `_create_agent`

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Test: `tests/unit/agent/test_agent_runtime_construction.py`

- [ ] **Step 1: Write a failing test that exercises a tool call**

Append to `tests/unit/agent/test_agent_runtime_construction.py`:

```python
def test_run_agent_runtime_captures_tool_result_into_run_result(monkeypatch):
    from agent.agno_agent.runtime import agent_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    captured: list = []

    class _StubPort:
        async def run(self, input_message, run_context, args):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"visible_summary": "ok"},
                metadata={"durable_write": True},
            )

    monkeypatch.setattr(agent_runtime, "_default_capability_ports", lambda: {"reminder_intent": _StubPort()})

    class _FakeRunOutput:
        def __init__(self, messages):
            self.content = ""
            self.messages = messages

    class _FakeAgent:
        def __init__(self, tools, **_kwargs):
            self.tools = tools

        async def arun(self, input, **kwargs):
            envelope = await self.tools["reminder_intent"]()
            captured.append(envelope)
            return _FakeRunOutput([
                {"role": "user", "content": input},
                {"role": "tool", "content": str(envelope)},
                {"role": "assistant", "content": ""},
            ])

    def _fake_create_agent(*, run_context, input_message, tool_results):
        ports = agent_runtime._default_capability_ports()
        from agent.agno_agent.runtime.tool_wrappers import build_capability_tool_wrappers

        wrappers = build_capability_tool_wrappers(
            ports=ports,
            run_context=run_context,
            input_message=input_message,
            tool_results=tool_results,
        )
        return _FakeAgent(tools=wrappers)

    monkeypatch.setattr(agent_runtime, "_create_agent", _fake_create_agent)

    result = asyncio.run(run_agent_runtime(agent_input=_input("提醒我"), run_context=_ctx()))
    assert len(result.tool_results) == 1
    assert result.tool_results[0].name == "reminder"
    assert result.tool_results[0].durable_write is True
    assert [m.content for m in result.visible_messages] == ["ok"]
    assert captured[0]["name"] == "reminder_intent"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_captures_tool_result_into_run_result -v`

Expected: FAIL — `_default_capability_ports` and the real `_create_agent` are not implemented.

- [ ] **Step 3: Implement `_default_capability_ports` and rewrite `_create_agent` + `run_agent_runtime` to thread `input_message`**

Replace the relevant portion of `agent/agno_agent/runtime/agent_runtime.py` so that:

1. `_default_capability_ports()` returns the four production ports.
2. `_create_agent` accepts `input_message` and passes it into `build_capability_tool_wrappers`.
3. `run_agent_runtime` derives `input_message = agent_input.text or ""` once and forwards it to `_create_agent` and to `agent.arun(input=...)`.

Apply this single replacement (the `_create_agent` placeholder from Task B1 and the original `run_agent_runtime` body are both replaced):

```python
def _default_capability_ports() -> dict[str, Any]:
    from agent.agno_agent.capabilities import (
        CalendarImportPort,
        ReminderIntentPort,
        TimezonePort,
        UrlContextPort,
    )

    return {
        "reminder_intent": ReminderIntentPort(),
        "timezone": TimezonePort(),
        "calendar_import": CalendarImportPort(),
        "url_context": UrlContextPort(),
    }


def _create_agent(
    *,
    run_context: AgentRunContext,
    input_message: str,
    tool_results: list[CapabilityResult],
) -> Any:
    from agno.agent import Agent
    from agno.tools import tool

    from agent.agno_agent.model_factory import create_llm_model
    from agent.agno_agent.runtime.chat_response_instructions import (
        build_chat_response_instructions,
    )
    from agent.agno_agent.runtime.tool_wrappers import build_capability_tool_wrappers

    ports = _default_capability_ports()
    wrappers = build_capability_tool_wrappers(
        ports=ports,
        run_context=run_context,
        input_message=input_message,
        tool_results=tool_results,
    )
    tools = [tool(name=name)(fn) for name, fn in wrappers.items()]
    return Agent(
        id="coke-single-agent",
        name="CokeSingleAgent",
        model=create_llm_model(role="reminder_detect", max_tokens=2000),
        instructions=build_chat_response_instructions(run_context),
        tools=tools,
        markdown=False,
    )


async def run_agent_runtime(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
) -> AgentRunResult:
    if agent_input.input_type not in {"user.turn", "reminder.fired", "deferred_action.fire"}:
        raise ValueError(f"unsupported AgentInput.input_type: {agent_input.input_type}")
    input_message = agent_input.text or ""
    tool_results: list[CapabilityResult] = []
    try:
        agent = _create_agent(
            run_context=run_context,
            input_message=input_message,
            tool_results=tool_results,
        )
        run_output = await agent.arun(input=input_message, session_id=run_context.conversation.id)
    except Exception as exc:
        logger.exception("agent_runtime.run_agent_runtime failed")
        return AgentRunResult(
            visible_messages=(),
            post_analyze_input=None,
            tool_results=tuple(tool_results),
            metrics={"capability_result_count": len(tool_results)},
            trace={"runtime": "single_agent", "exception": exc.__class__.__name__},
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=RuntimeErrorDisposition(code="agent_runtime_exception", retryable=True),
        )
    final_text = _extract_final_text(run_output)
    contract_violation = _check_durable_write_contract(tool_results)
    if contract_violation is not None:
        return AgentRunResult(
            visible_messages=(),
            post_analyze_input=None,
            tool_results=tuple(tool_results),
            metrics={"capability_result_count": len(tool_results)},
            trace={"runtime": "single_agent", "contract_violation": contract_violation.code},
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=contract_violation,
        )
    visible_text = _resolve_visible_text(final_text=final_text, tool_results=tool_results)
    visible_messages = (
        (VisibleMessage(message_type="text", content=visible_text),) if visible_text else ()
    )
    message_source = str(run_context.runtime_metadata.get("message_source") or "user")
    post_analyze_input = (
        {"input_message": input_message, "message_source": message_source}
        if visible_messages
        else None
    )
    return AgentRunResult(
        visible_messages=visible_messages,
        post_analyze_input=post_analyze_input,
        tool_results=tuple(tool_results),
        metrics={"capability_result_count": len(tool_results)},
        trace={"runtime": "single_agent"},
        output_disposition=OutputDisposition(status="ok" if visible_messages else "empty"),
    )
```

The `chat_response_instructions` module is created in Task B5; production import resolution requires B5 to land first. The Task B3 test monkeypatches `_create_agent`, so the test passes without B5.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_construction.py
git commit -m "feat(runtime): wire capability tool wrappers into agent_runtime construction"
```

### Task B4: Output rule precedence — five rules, evaluated in order

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py` (only `_resolve_visible_text` if needed)
- Create: `tests/unit/agent/test_agent_runtime_output_rules.py`

- [ ] **Step 1: Write failing tests for each rule**

Create `tests/unit/agent/test_agent_runtime_output_rules.py`:

```python
import asyncio
from datetime import UTC, datetime

from agent.agno_agent.runtime import agent_runtime
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload
from agent.agno_agent.runtime.result import CapabilityResult


def _ctx():
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="UTC"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv1", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
    )


def _run_with_fake_agent(*, messages, tool_results, monkeypatch, input_text="hi"):
    class _FakeOutput:
        def __init__(self, msgs): self.content = ""; self.messages = msgs

    class _FakeAgent:
        async def arun(self, input, **_): return _FakeOutput(messages)

    def _fake_create_agent(*, run_context, input_message, tool_results: list):
        tool_results.extend(tool_results)  # no-op; populated below
        return _FakeAgent()

    captured: list[CapabilityResult] = list(tool_results)

    def _patched_create(*, run_context, input_message, tool_results):
        for r in captured:
            tool_results.append(r)
        return _FakeAgent()

    monkeypatch.setattr(agent_runtime, "_create_agent", _patched_create)
    return asyncio.run(
        agent_runtime.run_agent_runtime(
            agent_input=AgentInput(
                input_type="user.turn",
                conversation_id="conv1",
                text=input_text,
                payload=UserTurnPayload(),
                occurred_at=datetime.now(UTC),
            ),
            run_context=_ctx(),
        )
    )


def test_rule1_synthesis_with_nonempty_final_text_wins(monkeypatch):
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": "..."},
        {"role": "assistant", "content": "synthesised reply"},
    ]
    url_result = CapabilityResult(
        name="url_context",
        ok=True,
        content={"items": [], "context": "..."},
        metadata={"requires_response_synthesis": True},
    )
    timezone_result = CapabilityResult(
        name="timezone",
        ok=True,
        content={"visible_summary": "已切换时区"},
        metadata={"durable_write": True},
    )
    result = _run_with_fake_agent(
        messages=messages,
        tool_results=[url_result, timezone_result],
        monkeypatch=monkeypatch,
    )
    assert [m.content for m in result.visible_messages] == ["synthesised reply"]


def test_rule2_visible_summary_when_synthesis_text_empty(monkeypatch):
    """Regression guard: synthesis flag set but final text empty → fall through to visible_summary."""
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": "..."},
        {"role": "assistant", "content": ""},
    ]
    url_result = CapabilityResult(
        name="url_context",
        ok=True,
        content={"items": [], "context": "..."},
        metadata={"requires_response_synthesis": True},
    )
    reminder_result = CapabilityResult(
        name="reminder",
        ok=True,
        content={"visible_summary": "已设好提醒"},
        metadata={"durable_write": True},
    )
    result = _run_with_fake_agent(
        messages=messages,
        tool_results=[url_result, reminder_result],
        monkeypatch=monkeypatch,
    )
    assert [m.content for m in result.visible_messages] == ["已设好提醒"]


def test_rule2_joins_multiple_visible_summaries(monkeypatch):
    messages = [{"role": "assistant", "content": ""}]
    a = CapabilityResult(name="reminder", ok=True, content={"visible_summary": "一"}, metadata={"durable_write": True})
    b = CapabilityResult(name="timezone", ok=True, content={"visible_summary": "二"}, metadata={"durable_write": True})
    result = _run_with_fake_agent(messages=messages, tool_results=[a, b], monkeypatch=monkeypatch)
    assert [m.content for m in result.visible_messages] == ["一\n二"]


def test_rule3_no_tool_results_uses_final_text(monkeypatch):
    messages = [{"role": "assistant", "content": "ordinary chat"}]
    result = _run_with_fake_agent(messages=messages, tool_results=[], monkeypatch=monkeypatch)
    assert [m.content for m in result.visible_messages] == ["ordinary chat"]


def test_rule4_empty_disposition_when_nothing_resolves(monkeypatch):
    messages = [{"role": "assistant", "content": ""}]
    no_summary = CapabilityResult(name="reminder", ok=True, content={"action": "none"}, metadata={"durable_write": False})
    result = _run_with_fake_agent(messages=messages, tool_results=[no_summary], monkeypatch=monkeypatch)
    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.post_analyze_input is None
```

- [ ] **Step 2: Run the tests to verify failures (or success — most should pass given the skeleton)**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -v`

Expected: rule 1 likely passes; rule 2 (the regression guard) fails because the current `_resolve_visible_text` ignores the synthesis flag entirely when final text is empty — it does, but only when `tool_results` is non-empty. Verify which rule fails by name and only modify `_resolve_visible_text` if any rule fails. **Do not change the function unless a test fails** — write the change to fix the actual failing case.

- [ ] **Step 3: If rule 2 fails, fix `_resolve_visible_text`**

Replace the function in `agent/agno_agent/runtime/agent_runtime.py`:

```python
def _resolve_visible_text(
    *,
    final_text: str,
    tool_results: list[CapabilityResult],
) -> str:
    if tool_results and any(r.requires_response_synthesis for r in tool_results) and final_text.strip():
        return final_text
    summaries = [r.visible_summary for r in tool_results if r.visible_summary]
    if summaries:
        return "\n".join(summaries)
    if not tool_results:
        return final_text
    return ""
```

(This is the same logic as the skeleton; the test will pass once `_extract_final_text` correctly returns `""` for the empty assistant message — see Task B6.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_output_rules.py
git commit -m "test(runtime): cover all five visible-output rules including synthesis-empty-fallthrough"
```

### Task B5: Runtime-local chat-response prompt builder

**Files:**
- Create: `agent/agno_agent/runtime/chat_response_instructions.py`
- Create: `tests/unit/agent/test_chat_response_instructions.py`

- [ ] **Step 1: Write the failing prompt-cleaning invariant test**

Create `tests/unit/agent/test_chat_response_instructions.py`:

```python
from datetime import UTC, datetime

from agent.agno_agent.runtime.chat_response_instructions import (
    build_chat_response_instructions,
)
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)


def _ctx():
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="UTC"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv1", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
    )


def test_assembled_prompt_excludes_protocol_and_json_schema_artifacts():
    prompt = build_chat_response_instructions(_ctx())
    forbidden = [
        "as valid JSON",
        "JSON Schema",
        "Message types include",
        "structured multi-modal",
        "RESPONSE",
        "REQUEST",
        "[reminder tool message]",
    ]
    for token in forbidden:
        assert token not in prompt, f"forbidden token found in prompt: {token!r}"


def test_prompt_keeps_user_challenges_block_in_general_form():
    prompt = build_chat_response_instructions(_ctx())
    assert "Handling User Challenges" in prompt
    # Replacement: phrasing that does not reference the legacy bracket label.
    assert "reminder tool result" in prompt.lower()


def test_prompt_includes_default_user_timezone():
    prompt = build_chat_response_instructions(_ctx())
    assert "UTC" in prompt
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_chat_response_instructions.py -v`

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the prompt builder**

Create `agent/agno_agent/runtime/chat_response_instructions.py`:

```python
from __future__ import annotations

import re

from agent.agno_agent.runtime.context import AgentRunContext
from agent.prompt.agent_instructions_prompt import INSTRUCTIONS_CHAT_RESPONSE


_FORBIDDEN_LINE_PATTERNS = (
    re.compile(r"^3\.\s*Output structured multi-modal messages.*$", re.MULTILINE),
    re.compile(r"^- Strictly output according to the JSON Schema.*$", re.MULTILINE),
    re.compile(r"^- Message types include:.*$", re.MULTILINE),
    re.compile(r"^Output the result as valid JSON,.*$", re.MULTILINE),
)

_LEGACY_BRACKET_REPLACEMENT = (
    "If there is a [reminder tool message] in context, use it to explain the actual state",
    "If a reminder tool result is available in the conversation, use its content to explain the actual state",
)


def _strip_legacy_artifacts(text: str) -> str:
    for pattern in _FORBIDDEN_LINE_PATTERNS:
        text = pattern.sub("", text)
    text = text.replace(*_LEGACY_BRACKET_REPLACEMENT)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def build_chat_response_instructions(run_context: AgentRunContext) -> str:
    cleaned = _strip_legacy_artifacts(INSTRUCTIONS_CHAT_RESPONSE)
    timezone = run_context.user.timezone or "UTC"
    return "\n\n".join([cleaned, f"Default user timezone: {timezone}"])
```

- [ ] **Step 4: Run the prompt-cleaning tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_chat_response_instructions.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/runtime/chat_response_instructions.py tests/unit/agent/test_chat_response_instructions.py
git commit -m "feat(runtime): add runtime-local chat-response instructions builder"
```

### Task B6: "Agno final text" extraction tests

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py` (only if tests fail)
- Create: `tests/unit/agent/test_agent_runtime_final_text_extraction.py`

- [ ] **Step 1: Write failing tests covering pre-tool prose, no-tool, and empty-final cases**

Create `tests/unit/agent/test_agent_runtime_final_text_extraction.py`:

```python
import pytest

from agent.agno_agent.runtime.agent_runtime import _extract_final_text


class _Out:
    def __init__(self, messages, content=""):
        self.messages = messages
        self.content = content


def test_extracts_post_tool_assistant_message_only():
    out = _Out(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Let me check..."},
            {"role": "tool_use", "content": "calling tool"},
            {"role": "tool", "content": "tool result"},
            {"role": "assistant", "content": "Here is the info."},
        ],
        content="Let me check...Here is the info.",
    )
    assert _extract_final_text(out) == "Here is the info."


def test_no_tool_call_returns_sole_assistant_text():
    out = _Out(messages=[{"role": "assistant", "content": "hi back"}])
    assert _extract_final_text(out) == "hi back"


def test_tool_call_with_empty_final_assistant_returns_empty():
    out = _Out(messages=[
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": "tool result"},
        {"role": "assistant", "content": ""},
    ])
    assert _extract_final_text(out) == ""


def test_no_messages_falls_back_to_content():
    out = _Out(messages=[], content="legacy text")
    assert _extract_final_text(out) == "legacy text"
```

- [ ] **Step 2: Run the tests to verify they pass against the skeleton (or fail and need refinement)**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_final_text_extraction.py -v`

Expected: PASS — the skeleton in Task B1 already implements this. If any case fails, fix `_extract_final_text` until all four tests pass. **Do not introduce model-object-shape special cases not exercised by tests.**

- [ ] **Step 3: Commit**

```bash
git add tests/unit/agent/test_agent_runtime_final_text_extraction.py
git commit -m "test(runtime): cover Agno final-text extraction including pre-tool prose discard"
```

### Task B7: Unknown-tool fail-closed mapping

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py` (add unknown-tool guard)
- Create: `tests/unit/agent/test_agent_runtime_unknown_tool.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/agent/test_agent_runtime_unknown_tool.py`:

```python
import asyncio
from datetime import UTC, datetime

from agent.agno_agent.runtime import agent_runtime
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload


def _ctx():
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="UTC"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv1", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
    )


def test_unknown_tool_call_results_in_failclosed_disposition(monkeypatch):
    class _FakeRunOutput:
        content = ""
        messages = [{"role": "assistant", "content": "..."}]

    class _FakeAgent:
        async def arun(self, input, **_):
            raise agent_runtime.UnknownToolError("bogus_tool")

    def _fake_create(**_kwargs):
        return _FakeAgent()

    monkeypatch.setattr(agent_runtime, "_create_agent", _fake_create)

    result = asyncio.run(
        agent_runtime.run_agent_runtime(
            agent_input=AgentInput(
                input_type="user.turn",
                conversation_id="conv1",
                text="hi",
                payload=UserTurnPayload(),
                occurred_at=datetime.now(UTC),
            ),
            run_context=_ctx(),
        )
    )
    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "agent_runtime_unknown_tool"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_unknown_tool.py -v`

Expected: FAIL — `UnknownToolError` is not defined.

- [ ] **Step 3: Add `UnknownToolError` and special-case its mapping**

In `agent/agno_agent/runtime/agent_runtime.py`, near the top:

```python
class UnknownToolError(Exception):
    """Raised by tool dispatch when the model selects a tool name that is not registered."""
```

Then in `run_agent_runtime`, replace the broad fail-closed `except Exception` to special-case `UnknownToolError`:

```python
    except UnknownToolError as exc:
        logger.error("agent_runtime received unknown tool name: %s", exc)
        return AgentRunResult(
            visible_messages=(),
            post_analyze_input=None,
            tool_results=tuple(tool_results),
            metrics={"capability_result_count": len(tool_results)},
            trace={"runtime": "single_agent", "unknown_tool": str(exc)},
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=RuntimeErrorDisposition(code="agent_runtime_unknown_tool", retryable=False),
        )
    except Exception as exc:
        logger.exception("agent_runtime.run_agent_runtime failed")
        return AgentRunResult(
            visible_messages=(),
            post_analyze_input=None,
            tool_results=tuple(tool_results),
            metrics={"capability_result_count": len(tool_results)},
            trace={"runtime": "single_agent", "exception": exc.__class__.__name__},
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=RuntimeErrorDisposition(code="agent_runtime_exception", retryable=True),
        )
```

Wire `UnknownToolError` into `tool_wrappers.py` so a missing-port lookup raises it deterministically. In `agent/agno_agent/runtime/tool_wrappers.py`, replace `build_capability_tool_wrappers` so it builds a wrapper for **every** declared `_TOOL_NAMES` entry; missing ports produce a wrapper that raises `UnknownToolError`:

```python
def build_capability_tool_wrappers(
    *,
    ports: Mapping[str, Any],
    run_context: AgentRunContext,
    input_message: str,
    tool_results: list[CapabilityResult],
) -> dict[str, Callable[..., Awaitable[dict[str, Any]]]]:
    from agent.agno_agent.runtime.agent_runtime import UnknownToolError

    wrappers: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {}
    for name in _TOOL_NAMES:
        port = ports.get(name)
        if port is None:
            async def _missing(**_args: Any, _name=name) -> dict[str, Any]:
                raise UnknownToolError(_name)

            _missing.__name__ = name
            wrappers[name] = _missing
            continue
        wrappers[name] = _make_async_wrapper(
            tool_name=name,
            port=port,
            run_context=run_context,
            input_message=input_message,
            tool_results=tool_results,
        )
    return wrappers
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_unknown_tool.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/runtime/agent_runtime.py agent/agno_agent/runtime/tool_wrappers.py tests/unit/agent/test_agent_runtime_unknown_tool.py
git commit -m "feat(runtime): map unknown tool dispatch to typed fail-closed disposition"
```

### Task B8: Durable-write contract violation test (rule 5)

**Files:**
- Create: `tests/unit/agent/test_agent_runtime_durable_write_contract.py`

- [ ] **Step 1: Write failing tests for both contract cases**

Create `tests/unit/agent/test_agent_runtime_durable_write_contract.py`:

```python
import asyncio
from datetime import UTC, datetime

from agent.agno_agent.runtime import agent_runtime
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload
from agent.agno_agent.runtime.result import CapabilityResult


def _ctx():
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="UTC"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv1", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
    )


def _run(*, tool_results, monkeypatch, messages=None):
    captured = list(tool_results)

    class _Out:
        content = ""
        def __init__(self): self.messages = messages or [{"role": "assistant", "content": ""}]

    class _Agent:
        async def arun(self, input, **_): return _Out()

    def _fake_create(*, run_context, input_message, tool_results):
        for r in captured: tool_results.append(r)
        return _Agent()

    monkeypatch.setattr(agent_runtime, "_create_agent", _fake_create)
    return asyncio.run(
        agent_runtime.run_agent_runtime(
            agent_input=AgentInput(
                input_type="user.turn",
                conversation_id="conv1",
                text="hi",
                payload=UserTurnPayload(),
                occurred_at=datetime.now(UTC),
            ),
            run_context=_ctx(),
        )
    )


def test_durable_write_with_visible_summary_succeeds(monkeypatch):
    ok = CapabilityResult(
        name="reminder",
        ok=True,
        content={"visible_summary": "已设好提醒"},
        metadata={"durable_write": True},
    )
    result = _run(tool_results=[ok], monkeypatch=monkeypatch)
    assert result.output_disposition.status == "ok"
    assert [m.content for m in result.visible_messages] == ["已设好提醒"]


def test_durable_write_without_visible_summary_is_failclosed(monkeypatch):
    bad = CapabilityResult(
        name="reminder",
        ok=True,
        content={},
        metadata={"durable_write": True},
    )
    result = _run(tool_results=[bad], monkeypatch=monkeypatch)
    assert result.output_disposition.status == "empty"
    assert result.visible_messages == ()
    assert result.error_disposition is not None
    assert result.error_disposition.code == "durable_write_missing_visible_summary"
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_durable_write_contract.py -v`

Expected: PASS — the skeleton in Task B1 already implements `_check_durable_write_contract`. If a test fails, refine the function.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/agent/test_agent_runtime_durable_write_contract.py
git commit -m "test(runtime): cover durable-write classification rule with success and contract violation"
```

### Task B9: Async-wrapper offload contract test

**Files:**
- Create: `tests/unit/agent/test_agent_runtime_async_offload.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/agent/test_agent_runtime_async_offload.py`:

```python
import asyncio
import time
from datetime import UTC, datetime

import pytest

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.runtime.tool_wrappers import build_capability_tool_wrappers


def _ctx():
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="UTC"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv1", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
    )


@pytest.mark.timeout(2)
def test_sync_blocking_port_does_not_starve_concurrent_task():
    class _BlockingPort:
        def run(self, input_message, run_context, args):
            time.sleep(0.4)  # blocking sync I/O
            return CapabilityResult(name="url_context", ok=True, content={"items": []}, metadata={})

    captured: list[CapabilityResult] = []
    wrappers = build_capability_tool_wrappers(
        ports={"url_context": _BlockingPort()},
        run_context=_ctx(),
        input_message="see https://example.com",
        tool_results=captured,
    )

    async def _runner():
        ticks = 0

        async def _ticker():
            nonlocal ticks
            for _ in range(10):
                ticks += 1
                await asyncio.sleep(0.05)

        ticker = asyncio.create_task(_ticker())
        await wrappers["url_context"]()
        await ticker
        return ticks

    ticks = asyncio.run(_runner())
    # If the wrapper had pinned the loop, the ticker would have been blocked
    # for the full 0.4s sleep — fewer than ~6 iterations would complete.
    assert ticks >= 6
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_async_offload.py -v`

Expected: PASS — `_make_async_wrapper` already routes sync `port.run` through `asyncio.to_thread`. If it fails, fix the wrapper so it offloads consistently.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/agent/test_agent_runtime_async_offload.py
git commit -m "test(runtime): assert sync-port async wrapper does not pin event loop"
```

### Task B10: Reminder retry-prompt schema fix (Fix #7)

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py:76-108`
- Create: `tests/unit/agent/test_reminder_intent_retry_schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/agent/test_reminder_intent_retry_schema.py`:

```python
from datetime import UTC, datetime

from agent.agno_agent.capabilities.reminder_intent import _build_reminder_retry_input
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)


def _ctx():
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="UTC"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv1", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
    )


def test_retry_prompt_lists_cancel_action():
    text = _build_reminder_retry_input("取消提醒", _ctx(), reason="primary detector returned no executable decision")
    assert "cancel" in text
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_retry_schema.py -v`

Expected: FAIL — line 94 lists `create, update, delete, complete, batch, list, or empty` (no `cancel`).

- [ ] **Step 3: Update the action list**

In `agent/agno_agent/capabilities/reminder_intent.py:94`, change:

```python
action must be exactly one of create, update, delete, complete, batch, list, or empty.
```

to:

```python
action must be exactly one of create, update, cancel, delete, complete, batch, list, or empty.
```

If `cancel` and `delete` are semantically equivalent in `ReminderDetectDecision`, keep both — the spec calls out alignment with the live schema, and the live schema accepts `cancel`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_retry_schema.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/capabilities/reminder_intent.py tests/unit/agent/test_reminder_intent_retry_schema.py
git commit -m "fix(reminder): include cancel in retry-prompt action list"
```

### Task B11: Real-model smoke (staging only)

**Files:**
- Create: `tests/eval/test_real_model_native_toolcalling_smoke.py`
- Create: `artifacts/evidence/2026-05-XX-pre-cutover-baseline/real-model-smoke.txt`

This task does not run by default in CI; it requires staging credentials.

- [ ] **Step 1: Write the smoke harness**

Create `tests/eval/test_real_model_native_toolcalling_smoke.py`:

```python
"""Real-model smoke for the single-Agent runtime.

Run only with staging credentials:
    AGENT_RUNTIME_REAL_MODEL_SMOKE=1 .venv/bin/python -m pytest tests/eval/test_real_model_native_toolcalling_smoke.py -v -s

This is gated by the env flag because it issues real LLM calls.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import pytest

from agent.agno_agent.runtime.agent_runtime import run_agent_runtime
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload

pytestmark = pytest.mark.skipif(
    os.environ.get("AGENT_RUNTIME_REAL_MODEL_SMOKE") != "1",
    reason="real-model smoke is opt-in via AGENT_RUNTIME_REAL_MODEL_SMOKE=1",
)


def _ctx(timezone="Asia/Tokyo"):
    return AgentRunContext(
        user=TrustedUserContext(id="staging-u", nickname="Smoke", timezone=timezone),
        character=TrustedCharacterContext(id="staging-c", nickname="Coke"),
        conversation=TrustedConversationContext(id="staging-conv", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="staging-u", cid="staging-c"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
        runtime_metadata={"message_source": "user"},
    )


def _input(text: str) -> AgentInput:
    return AgentInput(
        input_type="user.turn",
        conversation_id="staging-conv",
        text=text,
        payload=UserTurnPayload(),
        occurred_at=datetime.now(UTC),
    )


def test_reminder_create_flow_real_model():
    result = asyncio.run(run_agent_runtime(agent_input=_input("明天 8 点提醒我喝水"), run_context=_ctx()))
    assert result.output_disposition.status == "ok"
    assert any(r.name == "reminder" and r.durable_write for r in result.tool_results)


def test_url_context_synthesis_real_model():
    result = asyncio.run(run_agent_runtime(
        agent_input=_input("简单介绍下 https://example.com 这个页面"),
        run_context=_ctx(),
    ))
    assert result.output_disposition.status == "ok"
    assert any(r.name == "url_context" for r in result.tool_results)
    visible = "".join(m.content for m in result.visible_messages)
    for marker in ("RESPONSE", "REQUEST", "<tool_call", "<invoke", "tool_use"):
        assert marker not in visible


def test_timezone_change_real_model():
    result = asyncio.run(run_agent_runtime(agent_input=_input("帮我把时区改成东京"), run_context=_ctx(timezone="UTC")))
    assert result.output_disposition.status == "ok"
    assert any(r.name == "timezone" for r in result.tool_results)
```

- [ ] **Step 2: Run the smoke against staging credentials**

Run:

```bash
AGENT_RUNTIME_REAL_MODEL_SMOKE=1 .venv/bin/python -m pytest tests/eval/test_real_model_native_toolcalling_smoke.py -v -s 2>&1 \
  | tee artifacts/evidence/2026-05-XX-pre-cutover-baseline/real-model-smoke.txt
```

Expected: green; the captured log shows tool calls with the correct names. If any assertion fails, file a blocker — do **not** weaken the assertion; the spec calls this smoke load-bearing.

- [ ] **Step 3: Commit the evidence and the harness**

```bash
git add tests/eval/test_real_model_native_toolcalling_smoke.py artifacts/evidence/2026-05-XX-pre-cutover-baseline/real-model-smoke.txt
git commit -m "test(eval): add real-model smoke for single-Agent runtime"
```

### Task B12: Tool-call-count parity check (M5)

**Files:**
- Create: `tests/eval/test_tool_call_count_parity.py`

- [ ] **Step 1: Write the failing parity test**

Create `tests/eval/test_tool_call_count_parity.py`:

```python
"""Parity check: tool-call counts under native tool calling stay within Team baseline ±1."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("AGENT_RUNTIME_REAL_MODEL_SMOKE") != "1",
    reason="parity smoke is opt-in via AGENT_RUNTIME_REAL_MODEL_SMOKE=1",
)

_BASELINE_PATH = Path("artifacts/evidence/2026-05-XX-pre-cutover-baseline/team-tool-call-counts.json")


def test_native_tool_call_counts_within_baseline_band():
    if not _BASELINE_PATH.exists():
        pytest.skip(f"baseline not present at {_BASELINE_PATH}")
    baseline = json.loads(_BASELINE_PATH.read_text())
    # `baseline` is a dict {scenario_name: tool_call_count} captured under Team runtime.
    # The single-Agent runtime is exercised here with the same scenarios; assert each
    # scenario's count is within baseline ±1.
    for scenario, expected_count in baseline.items():
        observed = _exercise_scenario(scenario)
        assert abs(observed - expected_count) <= 1, (
            f"scenario={scenario} observed={observed} baseline={expected_count}"
        )


def _exercise_scenario(scenario: str) -> int:
    """Run one baseline scenario through `run_agent_runtime` and return the tool-call count.

    Reuses scripts/eval_reminder_normal_path_cases.py as the scenario library:
    each scenario is a (input_text, run_context_overrides) pair stored in the
    eval module's `SCENARIOS` dict. We import that dict, run the single-Agent
    runtime end-to-end, and read `result.metrics["capability_result_count"]`.
    """
    import asyncio
    from datetime import UTC, datetime

    from agent.agno_agent.runtime.agent_runtime import run_agent_runtime
    from agent.agno_agent.runtime.context import (
        AgentRunContext,
        TrustedCharacterContext,
        TrustedConversationContext,
        TrustedRelationContext,
        TrustedUserContext,
    )
    from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload
    from scripts import eval_reminder_normal_path_cases as eval_mod

    case = eval_mod.SCENARIOS[scenario]
    ctx = AgentRunContext(
        user=TrustedUserContext(id="parity-u", nickname="Parity", timezone=case.get("timezone", "Asia/Tokyo")),
        character=TrustedCharacterContext(id="parity-c", nickname="Coke"),
        conversation=TrustedConversationContext(id=f"parity-{scenario}", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="parity-u", cid="parity-c"),
        platform="business",
        recent_chat_history=case.get("recent_chat_history", ""),
        current_time=datetime.now(UTC),
        runtime_metadata={"message_source": "user"},
    )
    agent_input = AgentInput(
        input_type="user.turn",
        conversation_id=f"parity-{scenario}",
        text=case["input_text"],
        payload=UserTurnPayload(),
        occurred_at=datetime.now(UTC),
    )
    result = asyncio.run(run_agent_runtime(agent_input=agent_input, run_context=ctx))
    return int(result.metrics.get("capability_result_count", 0))
```

The baseline file `team-tool-call-counts.json` is captured separately (see Step 2). The scenario harness should reuse `scripts/eval_reminder_normal_path_cases.py` driver code.

- [ ] **Step 2: Capture the Team baseline tool-call counts**

Create `scripts/capture_team_tool_call_counts.py`:

```python
"""One-shot: drive each baseline scenario through the *current* Team runtime
and write a JSON map of {scenario_name: capability_result_count}.

Run BEFORE any cutover so the baseline reflects Team behaviour. The output
file feeds tests/eval/test_tool_call_count_parity.py.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.append(".")
from dotenv import load_dotenv

load_dotenv()

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.team_runtime import run_team_runtime
from scripts import eval_reminder_normal_path_cases as eval_mod

OUTPUT = Path("artifacts/evidence/2026-05-XX-pre-cutover-baseline/team-tool-call-counts.json")


async def _run_one(scenario_name: str) -> int:
    case = eval_mod.SCENARIOS[scenario_name]
    legacy_context = {
        "user": {"id": "parity-u", "nickname": "Parity", "timezone": case.get("timezone", "Asia/Tokyo")},
        "character": {"id": "parity-c", "name": "Coke"},
        "conversation": {"id": f"parity-{scenario_name}", "platform": "business"},
        "relation": {"uid": "parity-u", "cid": "parity-c"},
        "platform": "business",
    }
    result = await run_team_runtime(
        context=legacy_context,
        input_message_str=case["input_text"],
        message_source="user",
        metadata={},
        current_time=datetime.now(UTC),
    )
    return int(result.metrics.get("capability_result_count", 0))


async def _main():
    counts = {}
    for name in (
        "reminder_create",
        "reminder_update",
        "reminder_cancel",
        "reminder_list",
        "timezone_direct_set",
        "timezone_propose_confirm",
        "calendar_import_handoff",
        "url_synthesis",
    ):
        counts[name] = await _run_one(name)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(counts, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
```

Then run it once against the **current** Team runtime, before any cutover, and commit the resulting JSON:

```bash
.venv/bin/python scripts/capture_team_tool_call_counts.py
git add scripts/capture_team_tool_call_counts.py artifacts/evidence/2026-05-XX-pre-cutover-baseline/team-tool-call-counts.json
git commit -m "evidence(agent): capture Team-runtime tool-call counts for parity baseline"
```

If `scripts/eval_reminder_normal_path_cases.SCENARIOS` does not yet expose the eight scenario names listed above, add them in the same commit — pattern them on whatever scenario container exists in that file today.

- [ ] **Step 3: Run the parity test**

Run:

```bash
AGENT_RUNTIME_REAL_MODEL_SMOKE=1 .venv/bin/python -m pytest tests/eval/test_tool_call_count_parity.py -v -s
```

Expected: PASS once the harness is wired and the baseline is recorded. If the band is exceeded, file a blocker — do not relax the band.

- [ ] **Step 4: Commit**

```bash
git add tests/eval/test_tool_call_count_parity.py artifacts/evidence/2026-05-XX-pre-cutover-baseline/team-tool-call-counts.json
git commit -m "test(eval): assert single-Agent tool-call counts stay within Team baseline ±1"
```

### Task B13: Land Slice B

- [ ] **Step 1: Run the unit suite**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/ tests/unit/runner/ -v
```

Expected: green.

- [ ] **Step 2: Run repo-OS check**

Run: `zsh scripts/check`

Expected: green.

- [ ] **Step 3: Confirm no production caller imports `agent_runtime.run_agent_runtime` yet**

Run:

```bash
grep -rn 'agent_runtime\.run_agent_runtime\|from agent\.agno_agent\.runtime\.agent_runtime' agent/ connector/ --include='*.py' \
  | grep -v 'tests/' | grep -v 'test_'
```

Expected: zero hits — Slice C wires the call site.

- [ ] **Step 4: Open PR for Slice B**

```bash
git push
gh pr create --title "[Slice B] agent_runtime + tool wrappers + real-model smoke (no production traffic)" --body "$(cat <<'EOF'
## Summary
- agent_runtime.py: single-Agent entry point with tool result bridge, output rules, fail-closed mapping
- tool_wrappers.py: async wrappers projecting CapabilityResult to model-facing envelope
- chat_response_instructions.py: runtime-local prompt builder with cleaning invariants
- Reminder retry-prompt cancel parity (Fix #7)
- Real-model smoke harness for staging
- Tool-call-count parity guard

Spec: docs/superpowers/specs/2026-05-08-single-agent-native-toolcalling-design.md
Plan: docs/superpowers/plans/2026-05-08-single-agent-native-toolcalling.md (Slice B)

No production caller switches in this PR.

## Test plan
- [x] tests/unit/agent/ tests/unit/runner/ green
- [x] zsh scripts/check green
- [x] real-model smoke green in staging
- [x] tool-call-count parity green
EOF
)"
```

Expected: PR opened.

---

## Slice C — Cutover (production traffic flips)

**Goal:** route production traffic through `agent_runtime.run_agent_runtime`. Old runtime files remain importable so a `git revert` is a viable rollback.

### Task C1: Pre-cutover tag and evidence sync

- [ ] **Step 1: Tag the pre-cutover commit on `main`**

```bash
git fetch origin
git tag pre-single-agent-cutover-$(date +%Y%m%d) origin/main
git push origin pre-single-agent-cutover-$(date +%Y%m%d)
```

Expected: tag pushed. The Slice A baseline bundle in `artifacts/evidence/` corresponds to this tag.

- [ ] **Step 2: Capture the live production Agno pin and worker version into the evidence bundle**

```bash
grep '^agno==' requirements.txt > artifacts/evidence/2026-05-XX-pre-cutover-baseline/production-pin.txt
git rev-parse HEAD >> artifacts/evidence/2026-05-XX-pre-cutover-baseline/production-pin.txt
git add artifacts/evidence/2026-05-XX-pre-cutover-baseline/production-pin.txt
git commit -m "evidence(agent): capture production pin and worker commit pre-cutover"
```

Expected: file captures `agno==2.5.9` plus the current `main` commit hash.

### Task C2: Switch `event_adapter.run_agent_runtime_event` to the new runtime

**Files:**
- Modify: `agent/agno_agent/runtime/event_adapter.py`
- Test: `tests/unit/agent/test_event_adapter_routing.py` (new)

- [ ] **Step 1: Write a failing test that asserts `event_adapter` calls `agent_runtime.run_agent_runtime` and never forwards the legacy `context` dict downstream**

Create `tests/unit/agent/test_event_adapter_routing.py`:

```python
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from agent.agno_agent.runtime import event_adapter
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    OutputDisposition,
)


def _legacy_context():
    return {
        "user": {"id": "u1", "nickname": "Alice"},
        "character": {"id": "c1", "name": "Coke"},
        "conversation": {"id": "conv1", "platform": "business"},
        "relation": {"uid": "u1", "cid": "c1"},
        "platform": "business",
    }


def test_event_adapter_calls_agent_runtime_with_typed_context(monkeypatch):
    captured = {}
    fake_result = AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        tool_results=(),
        metrics={},
        trace={},
        output_disposition=OutputDisposition(status="empty"),
    )

    async def _fake_run_agent_runtime(*, agent_input, run_context):
        captured["agent_input"] = agent_input
        captured["run_context"] = run_context
        return fake_result

    monkeypatch.setattr(event_adapter, "run_agent_runtime", _fake_run_agent_runtime)

    agent_input = AgentInput(
        input_type="user.turn",
        conversation_id="conv1",
        text="hi",
        payload=UserTurnPayload(),
        occurred_at=datetime.now(UTC),
    )
    result = asyncio.run(
        event_adapter.run_agent_runtime_event(
            agent_input=agent_input,
            context=_legacy_context(),
            message_source="user",
        )
    )
    assert result is fake_result
    assert captured["agent_input"] is agent_input
    assert captured["run_context"].user.id == "u1"
    assert captured["run_context"].conversation.id == "conv1"
    assert captured["run_context"].runtime_metadata["message_source"] == "user"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_event_adapter_routing.py -v`

Expected: FAIL — `event_adapter` does not yet expose `run_agent_runtime` and still calls `run_team_runtime`.

- [ ] **Step 3: Rewrite `event_adapter.py`**

Replace the body of `agent/agno_agent/runtime/event_adapter.py` with:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.agno_agent.runtime.agent_runtime import run_agent_runtime
from agent.agno_agent.runtime.context import build_agent_run_context
from agent.agno_agent.runtime.inputs import AgentInput
from agent.agno_agent.runtime.result import AgentRunResult


async def run_agent_runtime_event(
    *,
    agent_input: AgentInput,
    context: dict[str, Any],
    message_source: str,
    metadata: dict[str, Any] | None = None,
    current_time: datetime | None = None,
) -> AgentRunResult:
    occurred_at = current_time or agent_input.occurred_at or datetime.now(UTC)
    run_context = build_agent_run_context(
        context,
        current_time=occurred_at,
        runtime_metadata={"message_source": message_source, **(metadata or {})},
    )
    return await run_agent_runtime(agent_input=agent_input, run_context=run_context)


async def run_deferred_action_runtime_event(
    *,
    agent_input: AgentInput,
    context: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    current_time: datetime | None = None,
):
    from agent.agno_agent.adapters import map_agent_result_to_deferred_status

    result = await run_agent_runtime_event(
        agent_input=agent_input,
        context=context,
        message_source="deferred_action",
        metadata=metadata,
        current_time=current_time,
    )
    return map_agent_result_to_deferred_status(result)
```

`run_deferred_action_runtime_event` is left in place for Slice C; it is removed in Slice D. The legacy `context` dict no longer flows past `event_adapter`.

- [ ] **Step 4: Run the routing test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_event_adapter_routing.py -v`

Expected: PASS.

- [ ] **Step 5: Run the full unit suite**

Run: `.venv/bin/python -m pytest tests/unit/ -v`

Expected: PASS — Team-runtime tests in `tests/unit/agent/test_team_runtime_*` still pass because `team_runtime.py` is left importable. Tests that explicitly assert routing-into-Team-runtime *via* `event_adapter.run_agent_runtime_event` will now break, because the adapter no longer calls `run_team_runtime`. Run `grep -rn 'run_agent_runtime_event' tests/ --include='*.py'` and for each hit, choose one of two adjustments and apply it now (do not defer):

1. If the test exists to validate Team-runtime behaviour, retarget it at `agent.agno_agent.runtime.team_runtime.run_team_runtime` directly so it still proves the legacy code path until Slice D deletes it.
2. If the test is inherently about `event_adapter` routing, monkeypatch `event_adapter.run_agent_runtime` (the new symbol) instead of `event_adapter.run_team_runtime`. Keep the assertion shape; just swap the patched callable.

Tests that exclusively assert deleted-protocol behaviour are removed in Slice D Task D4 step 7; do not delete them in Slice C.

- [ ] **Step 6: Commit**

```bash
git add agent/agno_agent/runtime/event_adapter.py tests/unit/agent/test_event_adapter_routing.py
# Plus any test files updated in Step 5.
git commit -m "feat(runtime): route event_adapter through single-Agent runtime"
```

### Task C3: Staging acceptance matrix

**Files:**
- Create: `artifacts/evidence/2026-05-XX-cutover-staging/`

For each scenario in the spec's **Product Acceptance** matrix, record evidence in `artifacts/evidence/2026-05-XX-cutover-staging/<scenario>.md` with: input, observed visible text, observed `tool_results`, pass/fail, and a regression-grep result for protocol artefact tokens.

- [ ] **Step 1: Run staging deploy and the focused reminder-normal smoke against the new runtime**

```bash
mkdir -p artifacts/evidence/2026-05-XX-cutover-staging
.venv/bin/python scripts/eval_reminder_normal_path_cases.py 2>&1 \
  | tee artifacts/evidence/2026-05-XX-cutover-staging/reminder-normal.txt
```

Expected: parity vs. `artifacts/evidence/2026-05-XX-pre-cutover-baseline/baseline-reminder-normal.txt`.

- [ ] **Step 2: Walk the Product Acceptance matrix in staging**

For each scenario in the spec table (`Ordinary chat`, `Reminder create`, `Reminder update`, `Reminder cancel/delete`, `Reminder list/query`, `Reminder fired`, `Timezone change`, `Calendar import`, `URL synthesis`, `Empty-output fallback`, `New-message interrupt`, `PostAnalyze trigger`, `No protocol artefact leaks`), record evidence in `artifacts/evidence/2026-05-XX-cutover-staging/<scenario>.md`. Each file lists the inputs used and the observed outputs. Reject any scenario that fails — fix the runtime (or revert) before continuing.

- [ ] **Step 3: Run worker-runtime verification commands**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/ tests/unit/runner/ -v
zsh scripts/check
```

Expected: green.

- [ ] **Step 4: Commit the evidence bundle**

```bash
git add artifacts/evidence/2026-05-XX-cutover-staging
git commit -m "evidence(agent): capture staging Product Acceptance matrix for single-Agent cutover"
```

### Task C4: Production deploy

- [ ] **Step 1: Confirm Slice C gate is green**

Required green: real-model smoke (B11), parity (B12), staging acceptance matrix (C3), worker-runtime verification (C3 step 3). If any is red, do not deploy — file a blocker.

- [ ] **Step 2: Deploy via the standard rollout**

```bash
./scripts/deploy-compose-to-gcp.sh --restart
```

Expected: rollout completes; PM2 / compose services running.

- [ ] **Step 3: Watch the rollback failure-detection criteria for at least one full active-traffic window**

The criteria are:

- reminder create/update/cancel parity in production traffic
- empty-output fallback rate vs. baseline noise band
- protocol-artefact regression grep over outbound logs
- operator report of new-message-interrupt failure
- worker error rate / PostAnalyze schedule rate divergence

Capture observed values into `artifacts/evidence/2026-05-XX-cutover-production/observation-window.md`. Maintain the soak before declaring parity.

- [ ] **Step 4: If any criterion trips, execute the rollback playbook**

```bash
git revert <cutover-commit> && git push
./scripts/deploy-compose-to-gcp.sh --restart
.venv/bin/python scripts/eval_reminder_normal_path_cases.py
```

Then open a follow-up incident and stop. Do not retry the cutover until the root cause is named.

- [ ] **Step 5: Land Slice C**

```bash
git push
gh pr create --title "[Slice C] Single-Agent runtime cutover (production traffic flips)" --body "$(cat <<'EOF'
## Summary
- event_adapter now routes user/reminder/deferred turns through agent_runtime.run_agent_runtime
- Legacy context dict no longer flows past the entry boundary
- Old runtime files remain importable so git revert is a viable rollback
- Evidence: pre-cutover baseline, staging acceptance matrix, production observation window

Spec: docs/superpowers/specs/2026-05-08-single-agent-native-toolcalling-design.md
Plan: docs/superpowers/plans/2026-05-08-single-agent-native-toolcalling.md (Slice C)

## Test plan
- [x] real-model smoke green
- [x] tool-call-count parity green
- [x] staging Product Acceptance matrix green
- [x] zsh scripts/check green
- [x] reminder-normal smoke parity vs. baseline
- [x] one-window production soak observed without rollback trigger
EOF
)"
```

Expected: PR opened. Land only after the production soak is clean.

---

## Slice D — Delete the old runtime

**Goal:** retire the Team runtime once Slice C has held in production through at least one rollback-window-sized soak.

### Task D1: Confirm production parity has held

- [ ] **Step 1: Inspect production observation evidence**

Read `artifacts/evidence/2026-05-XX-cutover-production/observation-window.md`. Confirm zero rollback triggers across the soak window.

- [ ] **Step 2: If parity is in question, defer Slice D**

Do not proceed to deletion. Open a follow-up plan once any open production issues are resolved.

### Task D2: Relocate `with_output_references` into `runtime/result.py`

**Files:**
- Modify: `agent/agno_agent/runtime/result.py`
- Modify: `agent/runner/deferred_action_executor.py`
- Test: `tests/unit/agent/test_with_output_references_relocation.py` (new)

- [ ] **Step 1: Write the failing test asserting the new import path works**

Create `tests/unit/agent/test_with_output_references_relocation.py`:

```python
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    OutputDisposition,
    with_output_references,
)


def test_with_output_references_attaches_references():
    base = AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        tool_results=(),
        metrics={},
        trace={},
        output_disposition=OutputDisposition(status="ok"),
    )
    updated = with_output_references(base, ("ref-1",))
    assert updated.output_disposition.output_references == ("ref-1",)
    assert updated.output_disposition.status == "ok"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_with_output_references_relocation.py -v`

Expected: FAIL — `with_output_references` lives in `agent/agno_agent/adapters/output_disposition.py`.

- [ ] **Step 3: Add `with_output_references` to `runtime/result.py`**

Append to `agent/agno_agent/runtime/result.py`:

```python
def with_output_references(
    result: "AgentRunResult",
    output_references: Sequence[str],
) -> "AgentRunResult":
    from dataclasses import replace

    return replace(
        result,
        output_disposition=OutputDisposition(
            status=result.output_disposition.status,
            output_references=tuple(output_references),
            metadata=dict(result.output_disposition.metadata),
        ),
    )
```

- [ ] **Step 4: Update `deferred_action_executor.py` to import from the new location**

In `agent/runner/deferred_action_executor.py:10`, change the import line:

```python
from agent.agno_agent.adapters import (
    map_agent_result_to_deferred_status,
    with_output_references,
)
```

to:

```python
from agent.agno_agent.adapters import map_agent_result_to_deferred_status
from agent.agno_agent.runtime.result import with_output_references
```

(Adjust the exact `from` lines to match the file's current import block.)

- [ ] **Step 5: Run tests to verify the relocation passes**

Run: `.venv/bin/python -m pytest tests/unit/agent/ tests/unit/runner/ -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/agno_agent/runtime/result.py agent/runner/deferred_action_executor.py tests/unit/agent/test_with_output_references_relocation.py
git commit -m "refactor(runtime): relocate with_output_references into runtime.result"
```

### Task D3: Delete dead guards in `agent_handler.py`

**Files:**
- Modify: `agent/runner/agent_handler.py:440-526`

- [ ] **Step 1: Confirm zero callers**

Run:

```bash
grep -rn '_guard_pending_reminder_stop_response\|_guard_unconfirmed_reminder_response_after_prepare_timeout\|_is_clawscale_sync_text_reply_context' agent/ tests/ --include='*.py' | grep -v 'def _guard_pending\|def _guard_unconfirmed\|def _is_clawscale_sync'
```

Expected: zero hits other than tests for the guards themselves. If any production caller exists, stop and reclassify the change.

- [ ] **Step 2: Delete the three functions in `agent/runner/agent_handler.py`**

Remove `_guard_pending_reminder_stop_response`, `_guard_unconfirmed_reminder_response_after_prepare_timeout`, and `_is_clawscale_sync_text_reply_context` (lines 440–526). Also remove the helpers they were the only callers of: `_has_pending_reminder_stop_without_tool_result` and `_mentions_reminder_stop_target_clarification` (lines 529–550) — verify no other caller via:

```bash
grep -rn '_has_pending_reminder_stop_without_tool_result\|_mentions_reminder_stop_target_clarification' agent/ tests/ --include='*.py'
```

If used elsewhere, keep them; otherwise delete.

- [ ] **Step 3: Delete tests that exclusively cover deleted guards**

Run:

```bash
grep -rn '_guard_pending_reminder_stop_response\|_guard_unconfirmed_reminder_response_after_prepare_timeout\|_is_clawscale_sync_text_reply_context' tests/ --include='*.py'
```

Delete each matching test (or whole test file when it exclusively tests these helpers).

- [ ] **Step 4: Run unit tests**

Run: `.venv/bin/python -m pytest tests/unit/runner/ -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/runner/agent_handler.py tests/
git commit -m "refactor(runner): delete dead guard helpers in agent_handler"
```

### Task D4: Delete the old runtime modules

**Files:**
- Delete: `agent/agno_agent/runtime/team_runtime.py`
- Delete: `agent/agno_agent/runtime/selector.py`
- Delete: `agent/agno_agent/runtime/plan_parser.py`
- Delete: `agent/agno_agent/prompts/manager.py`
- Delete: `agent/agno_agent/capabilities/context_port.py`
- Delete: `agent/agno_agent/adapters/output_disposition.py`
- Modify: `agent/agno_agent/runtime/__init__.py`
- Modify: `agent/agno_agent/runtime/event_adapter.py`
- Modify: `agent/agno_agent/capabilities/__init__.py`
- Modify: `agent/agno_agent/adapters/__init__.py`

- [ ] **Step 1: Confirm zero production callers of each module**

Run:

```bash
for symbol in run_team_runtime select_runtime RuntimeVersion RuntimeSelectionInput parse_team_plan TeamPlan CapabilityRequest build_manager_instructions build_manager_input ContextPort with_output_references ; do
  echo "=== $symbol ==="
  grep -rn "$symbol" agent/ connector/ --include='*.py' | grep -v 'team_runtime.py\|selector.py\|plan_parser.py\|prompts/manager.py\|capabilities/context_port.py\|adapters/output_disposition.py'
done
```

Expected: only `with_output_references` shows hits (in `runtime/result.py` and `deferred_action_executor.py`); all others should have zero production hits. Resolve any remaining production caller before deletion.

- [ ] **Step 2: Delete the modules**

```bash
git rm agent/agno_agent/runtime/team_runtime.py \
       agent/agno_agent/runtime/selector.py \
       agent/agno_agent/runtime/plan_parser.py \
       agent/agno_agent/prompts/manager.py \
       agent/agno_agent/capabilities/context_port.py \
       agent/agno_agent/adapters/output_disposition.py
```

- [ ] **Step 3: Update `agent/agno_agent/runtime/__init__.py`**

Replace its body with:

```python
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import (
    AgentInput,
    DeferredActionPayload,
    ReminderFirePayload,
    UserTurnPayload,
)
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
    with_output_references,
)

__all__ = [
    "AgentInput",
    "AgentRunContext",
    "AgentRunResult",
    "CapabilityResult",
    "DeferredActionPayload",
    "OutputDisposition",
    "ReminderFirePayload",
    "RuntimeErrorDisposition",
    "TrustedCharacterContext",
    "TrustedConversationContext",
    "TrustedRelationContext",
    "TrustedUserContext",
    "UserTurnPayload",
    "VisibleMessage",
    "run_agent_runtime_event",
    "with_output_references",
]


def __getattr__(name: str):
    if name != "run_agent_runtime_event":
        raise AttributeError(name)
    from agent.agno_agent.runtime.event_adapter import run_agent_runtime_event

    return run_agent_runtime_event
```

`run_deferred_action_runtime_event`, `select_runtime`, `RuntimeSelectionInput`, and `RuntimeVersion` are removed because no caller uses them post-cutover (verified in Step 1).

- [ ] **Step 4: Update `agent/agno_agent/runtime/event_adapter.py` to drop `run_deferred_action_runtime_event`**

The deferred-action path calls `map_agent_result_to_deferred_status` directly (`agent/runner/deferred_action_executor.py:284`). Delete the unused wrapper:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.agno_agent.runtime.agent_runtime import run_agent_runtime
from agent.agno_agent.runtime.context import build_agent_run_context
from agent.agno_agent.runtime.inputs import AgentInput
from agent.agno_agent.runtime.result import AgentRunResult


async def run_agent_runtime_event(
    *,
    agent_input: AgentInput,
    context: dict[str, Any],
    message_source: str,
    metadata: dict[str, Any] | None = None,
    current_time: datetime | None = None,
) -> AgentRunResult:
    occurred_at = current_time or agent_input.occurred_at or datetime.now(UTC)
    run_context = build_agent_run_context(
        context,
        current_time=occurred_at,
        runtime_metadata={"message_source": message_source, **(metadata or {})},
    )
    return await run_agent_runtime(agent_input=agent_input, run_context=run_context)
```

- [ ] **Step 5: Drop `ContextPort` from `agent/agno_agent/capabilities/__init__.py`**

Edit `agent/agno_agent/capabilities/__init__.py` to remove the `ContextPort` import and from `__all__`:

```python
from agent.agno_agent.capabilities.calendar_import_port import CalendarImportPort
from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort
from agent.agno_agent.capabilities.timezone_port import TimezonePort
from agent.agno_agent.capabilities.url_context_port import UrlContextPort

__all__ = [
    "CalendarImportPort",
    "ReminderIntentPort",
    "TimezonePort",
    "UrlContextPort",
]
```

- [ ] **Step 6: Update `agent/agno_agent/adapters/__init__.py` to drop `with_output_references` (it now lives in `runtime/result.py`)**

Inspect the current `adapters/__init__.py` and remove any re-export of `with_output_references` from the deleted `output_disposition` module.

- [ ] **Step 7: Delete obsolete test modules**

```bash
git rm tests/unit/agent/test_team_runtime_plan_parser.py \
       tests/unit/agent/test_team_runtime_construction.py \
       tests/unit/agent/test_team_runtime_execution.py \
       tests/unit/agent/test_team_runtime_parity.py \
       tests/unit/agent/test_agent_runtime_selector.py \
       tests/unit/agent/test_context_port.py
```

If a test name in this list is missing, list the directory and delete only the files that exist:

```bash
ls tests/unit/agent/ | grep -E 'team_runtime|selector|context_port'
```

- [ ] **Step 8: Run the full unit suite**

Run:

```bash
.venv/bin/python -m pytest tests/unit/ -v
```

Expected: PASS. If any import error surfaces, follow the missing symbol back to its caller and decide whether to delete or rewire.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(runtime): delete Team runtime, selector, plan parser, manager prompt, context port, output_disposition adapter"
```

### Task D5: Land Slice D

- [ ] **Step 1: Run repo-OS check and worker-runtime verification**

```bash
zsh scripts/check
.venv/bin/python -m pytest tests/unit/agent/ tests/unit/runner/ -v
.venv/bin/python scripts/eval_reminder_normal_path_cases.py
```

Expected: green; reminder-normal parity vs. Slice C baseline.

- [ ] **Step 2: Open PR**

```bash
git push
gh pr create --title "[Slice D] Delete Team runtime + dead guards" --body "$(cat <<'EOF'
## Summary
- Delete team_runtime.py, selector.py, plan_parser.py, prompts/manager.py, capabilities/context_port.py, adapters/output_disposition.py
- Relocate with_output_references to runtime.result
- Drop dead handler guards (_guard_pending_reminder_stop_response, _guard_unconfirmed_reminder_response_after_prepare_timeout, _is_clawscale_sync_text_reply_context)
- Drop run_deferred_action_runtime_event wrapper (deferred executor calls map_agent_result_to_deferred_status directly)

Spec: docs/superpowers/specs/2026-05-08-single-agent-native-toolcalling-design.md
Plan: docs/superpowers/plans/2026-05-08-single-agent-native-toolcalling.md (Slice D)

## Test plan
- [x] tests/unit/agent/ tests/unit/runner/ green
- [x] reminder-normal smoke parity vs. Slice C
- [x] zsh scripts/check green
EOF
)"
```

Expected: PR opened. Slice E should follow within a day.

---

## Slice E — Canonical docs + fitness updates

**Goal:** retire "Agent Runtime Team" terminology so canonical docs do not describe code that no longer exists.

### Task E1: Update `docs/architecture.md`

**Files:**
- Modify: `docs/architecture.md:179`

- [ ] **Step 1: Read the current pipeline section**

Run: `sed -n '170,200p' docs/architecture.md`

Expected: confirms current wording references "Agent Runtime Team".

- [ ] **Step 2: Rewrite the pipeline description**

In `docs/architecture.md` line 179, replace `The default turn pipeline is Agent Runtime Team.` with:

```
The default turn pipeline is the single-Agent runtime defined in
`agent/agno_agent/runtime/agent_runtime.py`. The runner constructs an Agno
`Agent` per turn and registers four async tool wrappers (`reminder_intent`,
`timezone`, `calendar_import`, `url_context`) that capture typed
`CapabilityResult` objects for the deterministic visible-output rules.
```

Adjust adjacent paragraphs as needed so the section still reads as a unit. Do not introduce new architecture content beyond replacing the deleted-runtime references.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture.md
git commit -m "docs(architecture): describe single-Agent runtime instead of Team"
```

### Task E2: Update `docs/design-docs/coke-working-contract.md`

**Files:**
- Modify: `docs/design-docs/coke-working-contract.md:28`

- [ ] **Step 1: Replace the line**

In `docs/design-docs/coke-working-contract.md:28`, replace `Agent Runtime Team orchestration, typed runtime events, and capability ports` with:

```
single-Agent runtime, typed runtime events, and capability tool wrappers
```

- [ ] **Step 2: Commit**

```bash
git add docs/design-docs/coke-working-contract.md
git commit -m "docs(working-contract): drop Team terminology in coke working contract"
```

### Task E3: Update `docs/fitness/coke-verification-matrix.md`

**Files:**
- Modify: `docs/fitness/coke-verification-matrix.md:66, :71`

- [ ] **Step 1: Read the current Team-runtime block**

Run: `sed -n '60,80p' docs/fitness/coke-verification-matrix.md`

Expected: lines reference "Team runtime cutover commands" with `AGENT_RUNTIME_VERSION=team` env var.

- [ ] **Step 2: Replace with single-Agent commands**

Change line 66 from:

```
change affects user-visible reminder behavior, Team runtime orchestration, LLM
```

to:

```
change affects user-visible reminder behavior, single-Agent runtime orchestration, LLM
```

Replace lines 71–75 (the `Team runtime cutover commands:` block) with:

````
Single-Agent runtime commands:

```bash
.venv/bin/python -m pytest tests/unit/agent/ tests/unit/runner/ -v
.venv/bin/python scripts/eval_reminder_normal_path_cases.py
```
````

The `AGENT_RUNTIME_VERSION` env var is gone post-cutover.

- [ ] **Step 3: Commit**

```bash
git add docs/fitness/coke-verification-matrix.md
git commit -m "docs(fitness): drop AGENT_RUNTIME_VERSION=team and rename Team commands"
```

### Task E4: Sweep remaining "Agent Runtime Team" / `team_runtime` references

- [ ] **Step 1: Find every doc reference**

```bash
grep -rn "Agent Runtime Team\|team_runtime\|Team runtime" docs/
```

Expected: small list. For each hit:
- If it is a current canonical statement, rewrite to describe the single-Agent runtime.
- If it is in a dated artifact (`2026-04-…`), leave it (those are historical and the canonical docs win).

- [ ] **Step 2: Run the grep until clean for canonical docs**

```bash
grep -rn "Agent Runtime Team\|team_runtime" docs/architecture.md docs/design-docs/ docs/fitness/ docs/roadmap.md docs/deploy.md docs/clawscale_bridge.md
```

Expected: zero hits.

- [ ] **Step 3: Commit any remaining doc edits**

```bash
git add docs/
git commit -m "docs: sweep remaining Team-runtime references in canonical docs"
```

### Task E5: Land Slice E

- [ ] **Step 1: Run final verification**

```bash
zsh scripts/check
.venv/bin/python -m pytest tests/unit/agent/ tests/unit/runner/ -v
```

Expected: green.

- [ ] **Step 2: Open PR**

```bash
git push
gh pr create --title "[Slice E] Drop Team-runtime terminology in canonical docs" --body "$(cat <<'EOF'
## Summary
- docs/architecture.md describes the single-Agent runtime
- docs/design-docs/coke-working-contract.md updated
- docs/fitness/coke-verification-matrix.md drops AGENT_RUNTIME_VERSION=team and renames the command block
- Canonical docs grep clean for "Agent Runtime Team" / "team_runtime"

Spec: docs/superpowers/specs/2026-05-08-single-agent-native-toolcalling-design.md
Plan: docs/superpowers/plans/2026-05-08-single-agent-native-toolcalling.md (Slice E)

## Test plan
- [x] zsh scripts/check green
- [x] grep canonical docs clean
EOF
)"
```

Expected: PR opened. Slice E may land jointly with Slice D when the doc diff is small.

---

## Out of scope (do not touch in this plan)

- PostAnalyzeWorkflow restructuring
- Prompt content improvements beyond keep/remove rules from the spec's **System Prompt** section
- New capabilities
- Gateway, bridge, or deployment changes
- Reminder-detector behavior changes not required for native-toolcalling parity
- NLP heuristics in the wrong layer (Related Contract Fix #8) — deferred to a separate slice; keep `_should_retry_for_quoted_title_loss` as-is unless a test demands a change here.
- Env-var float parsing duplication (Related Contract Fix #6) — resolved naturally when `team_runtime.py` is deleted in Slice D; no separate task.
