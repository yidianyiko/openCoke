# Team Runtime Contract Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the Team runtime user-visible contract, keep mid-run interruption, and then clean up dead abstractions without adding runtime heuristics.

**Architecture:** Keep `agent/runner/` as the deterministic reliability shell for locks, interruption, output writes, sync reply behavior, fallback replies, and PostAnalyze scheduling. Keep `agent/agno_agent/runtime/` responsible for a single parseable Team manager protocol; malformed manager output returns a typed empty/error result and never becomes a synthetic capability request. Fix production-path tests first, then remove dead abstractions after B1-B8 are repaired.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, Agno Team fakes, Mongo DAO fakes/mocks, existing Coke runner/runtime dataclasses.

---

## Critical Rules

- Work in an isolated worktree, not the dirty root checkout.
- Do not add parser fallbacks, regex intent detection, or case-specific reminder examples.
- Do not make tests pass by weakening the product contract.
- Preserve mid-run interruption.
- Include abstraction cleanup in the plan, but only after contract blockers and behavior tests pass.
- Do not commit the untracked `artifacts/evidence/reminder-normal/user-view-*.json` files unless a later evidence-cleanup task explicitly chooses them.

## Source Spec

- `docs/superpowers/specs/2026-05-08-team-runtime-contract-repair-design.md`

## File Map

Modify:

- `agent/agno_agent/runtime/team_runtime.py` - remove protocol retries, synthetic recovery, and unconfirmed-promise regex recovery.
- `agent/agno_agent/prompts/manager.py` - remove JSON-output prompt injection and keep only RESPONSE/REQUEST-compatible wording.
- `agent/agno_agent/capabilities/reminder_intent.py` - remove divergent retry action enum; derive or state schema-compatible retry guidance.
- `agent/runner/agent_handler.py` - supervise Team runtime with heartbeat and interruption polling; wire guards and sync first-text behavior; skip PostAnalyze for deferred user reminders.
- `agent/runner/deferred_action_executor.py` - preserve original exceptions when occurrence claim fails; remove duplicate test shadowing.
- `agent/runner/reminder_event_handler.py` - log exception stack traces before returning typed failures.
- `agent/agno_agent/runtime/selector.py` - remove or inline once blocker tests pass.
- `agent/agno_agent/runtime/event_adapter.py` - remove dead context build or pass the built context deliberately.
- `agent/agno_agent/runtime/context.py` - remove trusted-context raw metadata leak if not needed.
- `agent/agno_agent/capabilities/__init__.py` and capability port files - remove unused `ContextPort`; decide adapter naming.
- `agent/agno_agent/adapters/output_disposition.py` - inline or justify.

Tests:

- `tests/unit/agent/test_team_runtime_execution.py`
- `tests/unit/agent/test_team_runtime_plan_parser.py`
- `tests/unit/agent/test_manager_prompt.py`
- `tests/unit/agent/test_agent_handler.py`
- `tests/unit/agent/test_reminder_intent_capability.py`
- `tests/unit/runner/test_deferred_action_executor.py`
- `tests/unit/runner/test_reminder_event_handler.py`
- `tests/unit/agent/test_agent_runtime_selector.py`
- `tests/unit/agent/test_context_port.py`
- `tests/unit/agent/test_output_disposition_adapter.py`
- `tests/unit/agent/test_agent_runtime_types.py`
- `tests/unit/agent/test_team_runtime_parity.py`

Optional docs/evidence:

- `docs/fitness/coke-verification-matrix.md` only if verification policy changes.
- `artifacts/evidence/reminder-normal/` only during Phase 4 evidence cleanup.

---

### Task 0: Isolated Worktree And Baseline

**Files:**
- Read: `AGENTS.md`
- Read: `docs/fitness/coke-verification-matrix.md`
- Modify: none

- [ ] **Step 1: Create an isolated worktree**

Run:

```bash
git status --short
git worktree add .worktrees/team-runtime-contract-repair -b team-runtime-contract-repair
cd .worktrees/team-runtime-contract-repair
```

Expected:

- Root checkout may show untracked evidence files.
- New worktree branch is `team-runtime-contract-repair`.

- [ ] **Step 2: Confirm the worktree is clean**

Run:

```bash
git status --short
git rev-parse --abbrev-ref HEAD
```

Expected:

```text
team-runtime-contract-repair
```

`git status --short` should be empty.

- [ ] **Step 3: Run focused current-state tests to separate baseline from repair**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest \
  tests/unit/agent/test_team_runtime_execution.py \
  tests/unit/agent/test_agent_handler.py \
  tests/unit/runner/test_deferred_action_executor.py \
  tests/unit/runner/test_reminder_event_handler.py -v
```

Expected: record PASS/FAIL in your notes. Do not fix anything yet.

- [ ] **Step 4: Commit nothing**

Run:

```bash
git status --short
```

Expected: clean worktree.

---

### Task 1: Team Runtime Must Not Recover Malformed Manager Output Into Reminder Writes

**Files:**
- Modify: `tests/unit/agent/test_team_runtime_execution.py`
- Modify: `agent/agno_agent/runtime/team_runtime.py`

- [ ] **Step 1: Replace forbidden recovery tests with failing contract tests**

In `tests/unit/agent/test_team_runtime_execution.py`, delete or rewrite these existing tests:

- `test_run_team_runtime_retries_empty_manager_output`
- `test_run_team_runtime_retries_manager_protocol_artifact`
- `test_run_team_runtime_bounds_protocol_retry_timeout`
- `test_run_team_runtime_retries_provider_tool_artifact`
- `test_run_team_runtime_retries_json_response_envelope`
- `test_run_team_runtime_retries_bracket_tool_artifact`
- `test_run_team_runtime_routes_unconfirmed_reminder_response_to_capability`
- `test_run_team_runtime_delegates_reminder_after_failed_protocol_retries`

Add these tests:

```python
@pytest.mark.asyncio
async def test_run_team_runtime_does_not_retry_empty_manager_output(monkeypatch):
    class EmptyTeam(FakeTeam):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls = 0

        async def arun(self, input, **kwargs):
            self.calls += 1
            return types.SimpleNamespace(content="")

    _install_fake_team(monkeypatch, EmptyTeam)
    from agent.agno_agent.runtime import team_runtime

    class FailingReminderPort:
        async def run(self, input_message, run_context, args=None):
            raise AssertionError("empty manager output must not execute reminders")

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="每小时打卡，到晚上8点",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FailingReminderPort()},
    )

    assert EmptyTeam.last_instance.calls == 1
    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.trace["capability_requests"] == ()
    assert "manager_empty_retried" not in result.trace
    assert "manager_recovery_capability" not in result.trace
```

```python
@pytest.mark.asyncio
async def test_run_team_runtime_does_not_convert_protocol_artifact_to_reminder(monkeypatch):
    class ArtifactTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            return types.SimpleNamespace(content="Operation cancelled by user")

    _install_fake_team(monkeypatch, ArtifactTeam)
    from agent.agno_agent.runtime import team_runtime

    class FailingReminderPort:
        async def run(self, input_message, run_context, args=None):
            raise AssertionError("protocol artifact must not execute reminders")

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="17:57提醒我喝水",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FailingReminderPort()},
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.trace["capability_requests"] == ()
    assert result.trace["manager_protocol_artifact"] is True
```

```python
@pytest.mark.asyncio
async def test_run_team_runtime_does_not_convert_direct_reminder_promise_to_write(monkeypatch):
    class DirectPromiseTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            return types.SimpleNamespace(
                content=(
                    "RESPONSE:\n"
                    "好的，已经为你设定了明天早上10:30的提醒，到时候会准时提醒你。"
                )
            )

    _install_fake_team(monkeypatch, DirectPromiseTeam)
    from agent.agno_agent.runtime import team_runtime

    class FailingReminderPort:
        async def run(self, input_message, run_context, args=None):
            raise AssertionError("direct promise must not execute reminders")

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="早上10:30提醒我看毛利分布",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FailingReminderPort()},
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.trace["capability_requests"] == ()
    assert result.trace["manager_unconfirmed_durable_promise"] is True
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest \
  tests/unit/agent/test_team_runtime_execution.py::test_run_team_runtime_does_not_retry_empty_manager_output \
  tests/unit/agent/test_team_runtime_execution.py::test_run_team_runtime_does_not_convert_protocol_artifact_to_reminder \
  tests/unit/agent/test_team_runtime_execution.py::test_run_team_runtime_does_not_convert_direct_reminder_promise_to_write -v
```

Expected: FAIL because current runtime retries/recovers into `reminder_intent`.

- [ ] **Step 3: Remove retry/recovery state from runtime**

In `agent/agno_agent/runtime/team_runtime.py`:

- remove `_DEFAULT_TEAM_MANAGER_RETRY_TIMEOUT_SECONDS`
- remove `_team_manager_retry_timeout_seconds`
- remove `_is_unconfirmed_reminder_commitment`
- remove `manager_protocol_retried`, `manager_empty_retried`, `manager_recovery_capability`, and `manager_unconfirmed_reminder_recovered`
- remove the second `_run_manager_plan(...)` calls after protocol artifacts and empty output
- when `_run_manager_plan` reports a protocol artifact, replace the plan with an empty plan and record trace only

Use this shape inside `run_team_runtime` after `manager_input`:

```python
    manager_timed_out = False
    manager_protocol_artifact = False
    manager_unconfirmed_durable_promise = False
    try:
        plan, protocol_artifact = await _run_manager_plan(
            team,
            manager_input,
            metadata=metadata,
            conversation_id=run_context.conversation.id,
        )
        if protocol_artifact and not plan.capability_requests:
            manager_protocol_artifact = True
            logger.error("Team manager returned protocol artifact")
            plan = TeamPlan(response_text="", capability_requests=())
        if (
            plan.response_text
            and not plan.capability_requests
            and _looks_like_unconfirmed_durable_promise(plan.response_text)
        ):
            manager_unconfirmed_durable_promise = True
            logger.warning("Team manager promised durable action without capability")
            plan = TeamPlan(
                response_text="",
                capability_requests=(),
                rejected_requests=plan.rejected_requests,
            )
    except TimeoutError:
        manager_timed_out = True
        logger.error(
            "Team manager timed out: timeout=%.1fs",
            _team_manager_timeout_seconds(),
        )
        plan = TeamPlan(response_text="", capability_requests=())
```

Add a text-only durable-promise detector that is deliberately not an intent router:

```python
def _looks_like_unconfirmed_durable_promise(text: str) -> bool:
    normalized = str(text or "")
    if not re.search(r"(提醒|叫我|通知|闹钟|\breminder\b|\balarm\b)", normalized, re.I):
        return False
    return bool(
        re.search(
            r"(已|已经|好的|没问题|我会|到时候|准时).{0,24}"
            r"(设定|设置|创建|安排|记下|提醒|通知)|"
            r"(reminder|alarm).{0,24}(set|created|scheduled)",
            normalized,
            re.I,
        )
    )
```

This detector must only reject visible promises with no capability request. It must never create a capability request.

Update both return trace dictionaries to contain only:

```python
                "manager_timeout": manager_timed_out,
                "manager_protocol_artifact": manager_protocol_artifact,
                "manager_unconfirmed_durable_promise": manager_unconfirmed_durable_promise,
                "response_synthesized_after_capabilities": response_synthesized_after_capabilities,
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_team_runtime_execution.py -v
```

Expected: PASS after deleting/updating tests that expected retry behavior.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/agno_agent/runtime/team_runtime.py tests/unit/agent/test_team_runtime_execution.py
git commit -m "fix(agent): stop team runtime heuristic reminder recovery"
```

---

### Task 2: Manager Prompt And Parser Drift Guard

**Files:**
- Modify: `agent/agno_agent/prompts/manager.py`
- Modify: `tests/unit/agent/test_manager_prompt.py`

- [ ] **Step 1: Add prompt/parser cross-check test**

In `tests/unit/agent/test_manager_prompt.py`, add:

```python
def test_manager_prompt_capabilities_match_plan_parser_allowlist():
    from agent.agno_agent.prompts.manager import build_manager_instructions
    from agent.agno_agent.runtime.plan_parser import ALLOWED_CAPABILITIES

    instructions = build_manager_instructions(_run_context())

    for capability in ALLOWED_CAPABILITIES:
        assert f"REQUEST {capability}" in instructions
    assert "Output the result as valid JSON" not in instructions
    assert "Strictly output according to the JSON Schema" not in instructions
    assert "valid JSON" not in instructions
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_manager_prompt.py::test_manager_prompt_capabilities_match_plan_parser_allowlist -v
```

Expected: FAIL because `INSTRUCTIONS_CHAT_RESPONSE` injects JSON/schema wording.

- [ ] **Step 3: Remove incompatible prompt injection**

In `agent/agno_agent/prompts/manager.py`, remove:

```python
from agent.prompt.agent_instructions_prompt import INSTRUCTIONS_CHAT_RESPONSE
```

Replace the `INSTRUCTIONS_CHAT_RESPONSE` entry in `build_manager_instructions` with RESPONSE-compatible dialogue rules:

```python
            "For RESPONSE text, maintain the character's personality.",
            "Reply in the user's current message language.",
            "Keep RESPONSE concise and user-visible.",
            "Do not include JSON unless the user explicitly asks to see JSON as content.",
```

- [ ] **Step 4: Run prompt tests**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_manager_prompt.py tests/unit/agent/test_team_runtime_plan_parser.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/agno_agent/prompts/manager.py tests/unit/agent/test_manager_prompt.py
git commit -m "fix(agent): align manager prompt with team protocol"
```

---

### Task 3: Reminder Retry Must Not Drift From Schema

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py`
- Modify: `tests/unit/agent/test_reminder_intent_capability.py`

- [ ] **Step 1: Add retry prompt schema-action test**

In `tests/unit/agent/test_reminder_intent_capability.py`, add:

```python
def test_reminder_retry_input_does_not_exclude_schema_actions():
    from datetime import UTC, datetime

    from agent.agno_agent.capabilities.reminder_intent import _build_reminder_retry_input
    from agent.agno_agent.runtime.context import (
        AgentRunContext,
        TrustedCharacterContext,
        TrustedConversationContext,
        TrustedRelationContext,
        TrustedUserContext,
    )
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from typing import get_args

    run_context = AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv1", platform="business"),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
    )

    retry_input = _build_reminder_retry_input(
        "取消我的提醒",
        run_context,
        reason="schema validation failed",
    )
    schema_actions = set(get_args(ReminderDetectDecision.model_fields["action"].annotation))

    assert "cancel" in schema_actions
    assert "create, update, delete, complete, batch, list, or empty" not in retry_input
    assert "Use the ReminderDetect system instructions" in retry_input
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_reminder_intent_capability.py::test_reminder_retry_input_does_not_exclude_schema_actions -v
```

Expected: FAIL because retry input hard-codes an action list without `cancel`.

- [ ] **Step 3: Remove divergent action enum from retry input**

In `agent/agno_agent/capabilities/reminder_intent.py`, remove this line from `_build_reminder_retry_input`:

```python
action must be exactly one of create, update, delete, complete, batch, list, or empty.
```

If you want an explicit schema reminder, add wording that does not enumerate actions:

```python
Use only action values accepted by the attached ReminderDetectDecision schema.
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_reminder_intent_capability.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/agno_agent/capabilities/reminder_intent.py tests/unit/agent/test_reminder_intent_capability.py
git commit -m "fix(agent): keep reminder retry aligned with schema"
```

---

### Task 4: Preserve Deferred And Reminder Fire Observability

**Files:**
- Modify: `agent/runner/deferred_action_executor.py`
- Modify: `agent/runner/reminder_event_handler.py`
- Modify: `tests/unit/runner/test_deferred_action_executor.py`
- Modify: `tests/unit/runner/test_reminder_event_handler.py`

- [ ] **Step 1: Add deferred occurrence-claim failure regression test**

In `tests/unit/runner/test_deferred_action_executor.py`, inside `TestDeferredActionExecutor`, add:

```python
    async def test_occurrence_claim_error_reports_original_exception(self):
        now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
        action = build_action()
        occurrence_dao = Mock(
            claim_or_get_occurrence=Mock(side_effect=RuntimeError("mongo claim failed")),
            mark_occurrence_failed=Mock(),
        )
        action_dao = Mock(
            get_action=Mock(return_value=action),
            claim_action_lease=Mock(return_value=True),
            update_action=Mock(return_value=True),
        )
        executor = executor_module.DeferredActionExecutor(
            action_dao=action_dao,
            occurrence_dao=occurrence_dao,
            scheduler=Mock(reschedule_action=Mock(), remove_action=Mock()),
            lock_manager=Mock(
                acquire_lock_async=AsyncMock(return_value="lock-1"),
                release_lock_safe_async=AsyncMock(),
            ),
            handle_message_fn=AsyncMock(),
            context_builder=Mock(return_value=build_context()),
            now_provider=lambda: now,
        )

        result = await executor.execute_due_action(
            action_id="action-1",
            scheduled_for=action["next_run_at"],
            revision=action["revision"],
        )

        assert result == "failed"
        occurrence_dao.mark_occurrence_failed.assert_called_once()
        assert occurrence_dao.mark_occurrence_failed.call_args.args[1] == "mongo claim failed"
        assert action_dao.update_action.call_args.kwargs["updates"]["last_error"] == "mongo claim failed"
```

- [ ] **Step 2: Add reminder-event logging tests**

In `tests/unit/runner/test_reminder_event_handler.py`, add:

```python
@pytest.mark.asyncio
async def test_replay_lookup_exception_logs_stack_before_returning_failure(monkeypatch):
    event = build_event()
    logger = Mock()
    monkeypatch.setattr(reminder_event_handler, "logger", logger)
    handler = build_handler(
        Mock(),
        existing_output_lookup=Mock(side_effect=RuntimeError("lookup exploded")),
    )

    result = await handler.handle(event)

    assert result.ok is False
    assert result.error_code == "ReplayLookupFailed"
    logger.exception.assert_called_once()
```

```python
@pytest.mark.asyncio
async def test_output_exception_logs_stack_before_returning_failure(monkeypatch):
    event = build_event()
    logger = Mock()
    monkeypatch.setattr(reminder_event_handler, "logger", logger)
    handler = build_handler(Mock(side_effect=RuntimeError("output exploded")))

    result = await handler.handle(event)

    assert result.ok is False
    assert result.error_code == "OutputFailed"
    logger.exception.assert_called_once()
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest \
  tests/unit/runner/test_deferred_action_executor.py::TestDeferredActionExecutor::test_occurrence_claim_error_reports_original_exception \
  tests/unit/runner/test_reminder_event_handler.py::test_replay_lookup_exception_logs_stack_before_returning_failure \
  tests/unit/runner/test_reminder_event_handler.py::test_output_exception_logs_stack_before_returning_failure -v
```

Expected: FAIL because `occurrence` may be unbound and reminder handler lacks logger.exception.

- [ ] **Step 4: Initialize deferred occurrence before claim**

In `agent/runner/deferred_action_executor.py`, before the `try:` at line near occurrence claim, initialize:

```python
        occurrence: dict[str, Any] = {}
```

In the `except Exception as exc:` block, keep:

```python
            attempt_count = int(occurrence.get("attempt_count", 1))
```

This now preserves the original `exc` string when claim failed before assignment.

- [ ] **Step 5: Add logger to reminder_event_handler**

In `agent/runner/reminder_event_handler.py`, add:

```python
import logging

logger = logging.getLogger(__name__)
```

Log each broad exception before returning:

```python
        try:
            existing_output = self.existing_output_lookup(event)
        except Exception:
            logger.exception("Reminder replay lookup failed before lock")
            return self._failure(
                event, "ReplayLookupFailed", "reminder replay lookup failed"
            )
```

Inside the in-lock lookup:

```python
            try:
                existing_output = self.existing_output_lookup(event)
            except Exception:
                logger.exception("Reminder replay lookup failed after lock")
                return self._failure(
                    event, "ReplayLookupFailed", "reminder replay lookup failed"
                )
```

Around output/runtime exceptions:

```python
        except Exception as exc:
            logger.exception("Reminder output failed")
            return self._failure(event, "OutputFailed", str(exc))
```

- [ ] **Step 6: Remove duplicate deferred test shadowing**

In `tests/unit/runner/test_deferred_action_executor.py`, keep one `test_executor_consumes_deferred_action_fire_result_success` and delete the duplicate function body. Prefer keeping the later version if it has current formatting fixes.

- [ ] **Step 7: Run focused tests**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/runner/test_deferred_action_executor.py tests/unit/runner/test_reminder_event_handler.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add agent/runner/deferred_action_executor.py agent/runner/reminder_event_handler.py \
  tests/unit/runner/test_deferred_action_executor.py tests/unit/runner/test_reminder_event_handler.py
git commit -m "fix(runner): preserve deferred fire failure observability"
```

---

### Task 5: Reconnect Runner Guards And Sync First Text

**Files:**
- Modify: `agent/runner/agent_handler.py`
- Modify: `tests/unit/agent/test_agent_handler.py`

- [ ] **Step 1: Add production-path guard tests**

In `tests/unit/agent/test_agent_handler.py`, add:

```python
@pytest.mark.asyncio
async def test_handle_message_team_runtime_applies_pending_stop_guard_before_send(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")
    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition, VisibleMessage
    from agent.runner import agent_handler

    sample_context["prepare_reminder_intent_hint"] = "stop_or_cancel"
    sample_context["orchestrator"] = {"need_reminder_detect": True}
    sample_context["tool_results"] = []

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[VisibleMessage(message_type="text", content="已帮你取消提醒。")],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    sent = []
    monkeypatch.setattr(agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda **kwargs: sent.append(kwargs["multimodal_response"]) or (
            {"message": kwargs["multimodal_response"]["content"]},
            kwargs["expect_output_timestamp"],
        ),
    )

    resp_messages, _, is_rollback, _ = await agent_handler.handle_message(
        context=sample_context,
        input_message_str="不要提醒我了",
        message_source="user",
        check_new_message=False,
        worker_tag="[T]",
    )

    assert is_rollback is False
    assert sent[0]["content"] == "你是想停掉哪条提醒？告诉我具体是哪条，我再帮你处理。"
    assert resp_messages[0]["message"] == "你是想停掉哪条提醒？告诉我具体是哪条，我再帮你处理。"
```

```python
@pytest.mark.asyncio
async def test_handle_message_team_runtime_applies_prepare_timeout_guard_before_send(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")
    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition, VisibleMessage
    from agent.runner import agent_handler

    sample_context["prepare_orchestrator_timeout"] = True
    sample_context["tool_results"] = []

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="没问题，我帮你设一个18:00的英语学习提醒。")
            ],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    sent = []
    monkeypatch.setattr(agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda **kwargs: sent.append(kwargs["multimodal_response"]) or (
            {"message": kwargs["multimodal_response"]["content"]},
            kwargs["expect_output_timestamp"],
        ),
    )

    await agent_handler.handle_message(
        context=sample_context,
        input_message_str="18:00提醒我学英语",
        message_source="user",
        check_new_message=False,
        worker_tag="[T]",
    )

    assert sent[0]["content"] == "我这次没能及时整理出回复。你把刚才那句再发我一遍，我可以继续处理。"
```

```python
@pytest.mark.asyncio
async def test_handle_message_team_runtime_stops_after_clawscale_sync_first_text(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")
    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition, VisibleMessage
    from agent.runner import agent_handler

    sample_context["conversation"]["platform"] = "business"
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {
            "metadata": {
                "source": "clawscale",
                "business_protocol": {"delivery_mode": "request_response"},
            }
        }
    ]

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="first"),
                VisibleMessage(message_type="text", content="second"),
            ],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    sent = []
    monkeypatch.setattr(agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda **kwargs: sent.append(kwargs["multimodal_response"]["content"]) or (
            {"message": kwargs["multimodal_response"]["content"]},
            kwargs["expect_output_timestamp"],
        ),
    )

    resp_messages, _, _, _ = await agent_handler.handle_message(
        context=sample_context,
        input_message_str="hello",
        message_source="user",
        check_new_message=False,
        worker_tag="[T]",
    )

    assert sent == ["first"]
    assert resp_messages == [{"message": "first"}]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_applies_pending_stop_guard_before_send \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_applies_prepare_timeout_guard_before_send \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_stops_after_clawscale_sync_first_text -v
```

Expected: FAIL because helpers are not wired to production path and sync first text is ignored.

- [ ] **Step 3: Add response guard helper**

In `agent/runner/agent_handler.py`, add near existing guard helpers:

```python
def _apply_team_response_guards(
    *,
    context: dict,
    input_message: str,
    multimodal_response: dict,
) -> dict:
    guarded = _guard_pending_reminder_stop_response(context, multimodal_response)
    guarded = _guard_unconfirmed_reminder_response_after_prepare_timeout(
        context,
        input_message,
        guarded,
    )
    return guarded
```

- [ ] **Step 4: Apply guards and sync stop in visible-message loop**

In the loop over `result.visible_messages`, before appending/sending:

```python
            multimodal_response = _apply_team_response_guards(
                context=context,
                input_message=input_message_str,
                multimodal_response=multimodal_response,
            )
            is_clawscale_sync_text_reply = _is_clawscale_sync_text_reply_context(
                context,
                message_source,
            )
```

After a successful send:

```python
            if (
                is_clawscale_sync_text_reply
                and multimodal_response.get("type", "text") == "text"
                and outputmessage is not None
            ):
                logger.info(
                    f"{worker_tag} Clawscale request_response first text reply written; stopping Team output loop"
                )
                break
```

- [ ] **Step 5: Run focused handler tests**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_agent_handler.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add agent/runner/agent_handler.py tests/unit/agent/test_agent_handler.py
git commit -m "fix(runner): restore team user-visible guards"
```

---

### Task 6: Preserve Mid-Run Interruption With Runtime Supervision

**Files:**
- Modify: `agent/runner/agent_handler.py`
- Modify: `tests/unit/agent/test_agent_handler.py`

- [ ] **Step 1: Add mid-run interruption test**

In `tests/unit/agent/test_agent_handler.py`, add:

```python
@pytest.mark.asyncio
async def test_handle_message_team_runtime_rolls_back_when_new_message_arrives_mid_run(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")
    monkeypatch.setenv("COKE_TEAM_RUNTIME_POLL_SECONDS", "0.01")
    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition, VisibleMessage
    from agent.runner import agent_handler

    checks = {"count": 0}

    def fake_is_new_message(u_id, c_id, platform, current_message_ids):
        checks["count"] += 1
        return checks["count"] >= 2

    async def slow_runtime(**kwargs):
        await asyncio.sleep(0.1)
        return AgentRunResult(
            visible_messages=[VisibleMessage(message_type="text", content="stale")],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    sent = []
    monkeypatch.setattr(agent_handler, "is_new_message_coming_in", fake_is_new_message)
    monkeypatch.setattr(agent_handler, "_run_agent_runtime_event", slow_runtime)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda **kwargs: sent.append(kwargs),
    )

    resp_messages, _, is_rollback, is_content_blocked = await agent_handler.handle_message(
        context=sample_context,
        input_message_str="你好",
        message_source="user",
        check_new_message=True,
        worker_tag="[T]",
        current_message_ids=["msg-1"],
    )

    assert resp_messages == []
    assert sent == []
    assert is_rollback is True
    assert is_content_blocked is False
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_rolls_back_when_new_message_arrives_mid_run -v
```

Expected: FAIL because current Team path checks new messages only before runtime.

- [ ] **Step 3: Add poll interval helper**

In `agent/runner/agent_handler.py`, add:

```python
def _team_runtime_poll_interval_seconds() -> float:
    raw_value = os.environ.get("COKE_TEAM_RUNTIME_POLL_SECONDS")
    if raw_value is None:
        return min(5.0, max(0.2, _team_lock_heartbeat_interval_seconds()))
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning(
            "COKE_TEAM_RUNTIME_POLL_SECONDS=%r is invalid; using 1.0s",
            raw_value,
        )
        return 1.0
    return value if value > 0 else 1.0
```

- [ ] **Step 4: Replace heartbeat-only await with supervised await**

Replace `_await_with_team_lock_heartbeat` with:

```python
class TeamRuntimeInterrupted(Exception):
    pass


async def _await_with_team_runtime_supervision(
    awaitable,
    *,
    lock_id: Optional[str],
    conversation_id: Optional[str],
    worker_tag: str,
    check_new_message: bool,
    message_source: str,
    context: dict,
    current_message_ids: Optional[List[str]],
):
    runtime_task = asyncio.create_task(awaitable)
    interval = _team_runtime_poll_interval_seconds()
    try:
        while not runtime_task.done():
            await asyncio.sleep(interval)
            if lock_id and conversation_id:
                renewed = lock_manager.renew_lock(
                    "conversation", conversation_id, lock_id, timeout=LOCK_TIMEOUT
                )
                if renewed:
                    logger.debug(f"{worker_tag} 锁续期成功 (Team runtime heartbeat)")
                else:
                    logger.warning(f"{worker_tag} Team runtime heartbeat 续期失败")
            if check_new_message and message_source == "user":
                user = context.get("user", {})
                character = context.get("character", {})
                current_platform = (
                    context.get("platform")
                    or context.get("conversation", {}).get("platform")
                    or "business"
                )
                if is_new_message_coming_in(
                    get_agent_entity_id(user),
                    get_agent_entity_id(character),
                    current_platform,
                    current_message_ids,
                ):
                    runtime_task.cancel()
                    logger.info(f"{worker_tag} rollback: new message during team runtime")
                    raise TeamRuntimeInterrupted()
        return await runtime_task
    finally:
        if not runtime_task.done():
            runtime_task.cancel()
        try:
            await runtime_task
        except (asyncio.CancelledError, TeamRuntimeInterrupted):
            pass
```

Update the call site:

```python
        try:
            result = await _await_with_team_runtime_supervision(
                _run_agent_runtime_event(
                    agent_input=agent_input,
                    context=context,
                    message_source=message_source,
                    metadata=metadata,
                ),
                lock_id=lock_id,
                conversation_id=conversation_id,
                worker_tag=worker_tag,
                check_new_message=check_new_message,
                message_source=message_source,
                context=context,
                current_message_ids=current_message_ids,
            )
        except TeamRuntimeInterrupted:
            context["MultiModalResponses"] = []
            return resp_messages, context, True, False
```

- [ ] **Step 5: Keep existing heartbeat test valid**

Update `test_handle_message_team_runtime_renews_lock_while_runtime_is_running` if needed so it sets:

```python
monkeypatch.setenv("COKE_TEAM_RUNTIME_POLL_SECONDS", "0.01")
```

and still asserts renewals occur during runtime.

- [ ] **Step 6: Run handler tests**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_agent_handler.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add agent/runner/agent_handler.py tests/unit/agent/test_agent_handler.py
git commit -m "fix(runner): preserve team runtime interruption"
```

---

### Task 7: Skip PostAnalyze For Deferred User Reminder Fires

**Files:**
- Modify: `agent/runner/agent_handler.py`
- Modify: `tests/unit/agent/test_agent_handler.py`

- [ ] **Step 1: Add deferred reminder PostAnalyze skip test**

In `tests/unit/agent/test_agent_handler.py`, add:

```python
@pytest.mark.asyncio
async def test_handle_message_team_runtime_skips_post_analyze_for_deferred_user_reminder(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")
    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition, VisibleMessage
    from agent.runner import agent_handler

    scheduled = []

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[VisibleMessage(message_type="text", content="提醒：喝水")],
            post_analyze_input={
                "input_message": "提醒：喝水",
                "message_source": "deferred_action",
            },
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    monkeypatch.setattr(agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime_event)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda **kwargs: ({"_id": "out-1"}, kwargs["expect_output_timestamp"]),
    )
    monkeypatch.setattr(agent_handler.asyncio, "create_task", lambda coro: scheduled.append(coro))

    await agent_handler.handle_message(
        context=sample_context,
        input_message_str="提醒：喝水",
        message_source="deferred_action",
        metadata={"kind": "user_reminder"},
        check_new_message=False,
        worker_tag="[T]",
    )

    assert scheduled == []
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_skips_post_analyze_for_deferred_user_reminder -v
```

Expected: FAIL because current code only checks env skip.

- [ ] **Step 3: Add explicit skip helper**

In `agent/runner/agent_handler.py`, add:

```python
def _team_should_skip_post_analyze_for_message(
    *,
    message_source: str,
    metadata: Optional[Dict[str, Any]],
) -> bool:
    if _team_should_skip_post_analyze():
        return True
    return (
        message_source == "deferred_action"
        and (metadata or {}).get("kind") == "user_reminder"
    )
```

Replace:

```python
            and not _team_should_skip_post_analyze()
```

with:

```python
            and not _team_should_skip_post_analyze_for_message(
                message_source=message_source,
                metadata=metadata,
            )
```

- [ ] **Step 4: Run handler tests**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_agent_handler.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/runner/agent_handler.py tests/unit/agent/test_agent_handler.py
git commit -m "fix(runner): skip post analyze for reminder fires"
```

---

### Task 8: Clean Up Tests That Hide Regressions

**Files:**
- Modify: `tests/unit/agent/test_agent_handler.py`
- Modify: `tests/unit/agent/test_agent_runtime_selector.py`
- Modify: `tests/unit/agent/test_agent_runtime_types.py`
- Modify: `tests/unit/agent/test_team_runtime_parity.py`
- Modify: `tests/unit/agent/test_output_disposition_adapter.py`

- [ ] **Step 1: Delete empty contract-name test**

In `tests/unit/agent/test_agent_handler.py`, delete:

```python
def test_agent_runtime_acceptance_contract_names_are_tracked():
    ...
```

The real contracts are now covered by production-path tests from Tasks 5-7.

- [ ] **Step 2: Reduce selector tests to current behavior**

Replace `tests/unit/agent/test_agent_runtime_selector.py` with:

```python
from agent.agno_agent.runtime.selector import select_runtime


def test_agent_runtime_always_selects_team(monkeypatch):
    monkeypatch.delenv("AGENT_RUNTIME_VERSION", raising=False)

    assert select_runtime() == "team"


def test_agent_runtime_ignores_legacy_env_after_cutover(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "legacy")

    assert select_runtime() == "team"
```

This keeps only behavior that can fail for Coke reasons.

- [ ] **Step 3: Trim dataclass tests**

In `tests/unit/agent/test_agent_runtime_types.py`, keep tests that verify Coke-specific semantics:

- `CapabilityResult.visible_summary`
- `CapabilityResult.requires_response_synthesis`
- `AgentRunResult` preserves output/error disposition semantics
- invalid message type checks if they exist

Delete tests that only assert assigning to a frozen dataclass raises `FrozenInstanceError`, unless the test also verifies nested mapping/sequence freezing used by Coke runtime state.

- [ ] **Step 4: Rename or rewrite parity tests**

In `tests/unit/agent/test_team_runtime_parity.py`, either rename the file to `test_team_capability_ports.py` or rewrite test names so they do not claim full parity. Keep focused adapter behavior tests for URL/timezone/calendar only.

If renaming:

```bash
git mv tests/unit/agent/test_team_runtime_parity.py tests/unit/agent/test_team_capability_ports.py
```

- [ ] **Step 5: Remove output disposition adapter test if adapter is removed in Task 9**

If Task 9 inlines `with_output_references`, delete `tests/unit/agent/test_output_disposition_adapter.py`. If Task 9 keeps the adapter, leave this file unchanged.

- [ ] **Step 6: Run agent unit tests**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/ -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add tests/unit/agent/
git commit -m "test(agent): remove fake team runtime parity gates"
```

---

### Task 9: Abstraction Cleanup After Contract Repair

**Files:**
- Modify/Delete: `agent/agno_agent/runtime/selector.py`
- Modify: `agent/agno_agent/runtime/__init__.py`
- Modify/Delete: `agent/agno_agent/capabilities/context_port.py`
- Modify: `agent/agno_agent/capabilities/__init__.py`
- Modify/Delete: `agent/agno_agent/adapters/output_disposition.py`
- Modify: `agent/agno_agent/adapters/__init__.py`
- Modify: `agent/runner/deferred_action_executor.py`
- Modify: `agent/agno_agent/runtime/event_adapter.py`
- Modify: `agent/agno_agent/runtime/context.py`
- Modify tests from Task 8 as needed.

- [ ] **Step 1: Remove selector indirection if only team exists**

Search:

```bash
rg -n "select_runtime|RuntimeSelectionInput|RuntimeVersion" agent tests
```

If the only meaningful runtime is `team`, replace selector imports with direct `"team"` assumptions and delete `agent/agno_agent/runtime/selector.py`.

Update `agent/agno_agent/runtime/__init__.py` to stop exporting selector names.

- [ ] **Step 2: Remove unused ContextPort**

Search:

```bash
rg -n "ContextPort" agent tests
```

Expected current production usage: none.

Delete:

```bash
git rm agent/agno_agent/capabilities/context_port.py tests/unit/agent/test_context_port.py
```

Remove `ContextPort` export from `agent/agno_agent/capabilities/__init__.py`.

- [ ] **Step 3: Inline output disposition adapter**

In `agent/runner/deferred_action_executor.py`, replace:

```python
        updated_result = with_output_references(
            runtime_result,
            tuple(runtime_result.output_disposition.output_references)
            + tuple(output_references),
        )
```

with:

```python
        from dataclasses import replace
        from agent.agno_agent.runtime.result import OutputDisposition

        updated_result = replace(
            runtime_result,
            output_disposition=OutputDisposition(
                status=runtime_result.output_disposition.status,
                output_references=(
                    tuple(runtime_result.output_disposition.output_references)
                    + tuple(output_references)
                ),
                metadata=dict(runtime_result.output_disposition.metadata),
            ),
        )
```

Then remove `with_output_references` from imports and exports:

```bash
git rm agent/agno_agent/adapters/output_disposition.py tests/unit/agent/test_output_disposition_adapter.py
```

Edit `agent/agno_agent/adapters/__init__.py` to remove `with_output_references`.

- [ ] **Step 4: Remove dead context build in event adapter**

In `agent/agno_agent/runtime/event_adapter.py`, delete the unused call:

```python
    build_agent_run_context(
        context,
        current_time=occurred_at,
        runtime_metadata={"message_source": message_source, **(metadata or {})},
    )
```

Also remove the now-unused import if nothing else uses it.

- [ ] **Step 5: Remove raw untrusted metadata from trusted context unless required**

In `agent/agno_agent/runtime/context.py`, change:

```python
def _metadata_from_raw(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {"raw": raw} if raw else {}
```

to:

```python
def _metadata_from_raw(raw: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    route_key = raw.get("route_key")
    if route_key:
        metadata["route_key"] = str(route_key)
    return metadata
```

Run existing context tests and update expectations that asserted full raw preservation. Do not preserve arbitrary raw dicts inside trusted context.

- [ ] **Step 6: Run cleanup tests**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/ tests/unit/runner/test_deferred_action_executor.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add agent/agno_agent agent/runner/deferred_action_executor.py tests/unit/agent tests/unit/runner/test_deferred_action_executor.py
git commit -m "refactor(agent): remove dead team runtime abstractions"
```

---

### Task 10: Evidence Policy Cleanup

**Files:**
- Modify: `artifacts/evidence/reminder-normal/`
- Optional Modify: `docs/fitness/README.md`
- Optional Modify: `docs/fitness/coke-verification-matrix.md`

- [ ] **Step 1: Inspect tracked evidence size**

Run:

```bash
git ls-files artifacts/evidence/reminder-normal | xargs -r ls -lh
```

Expected current large tracked files include:

- `team-100-pass-gate.json`
- `team-run-all.json`
- `team-100-pass-gate-supplement.json`

- [ ] **Step 2: Create compact manifest**

Create `artifacts/evidence/reminder-normal/team-runtime-contract-repair-manifest.json` with this shape:

```json
{
  "topic": "team-runtime-contract-repair",
  "policy": "Keep small targeted case evidence in git. Store full-run LLM transcripts outside git.",
  "tracked_case_artifacts": [
    "team-case14.json",
    "team-case123.json",
    "team-smoke.json"
  ],
  "full_transcripts_removed_from_git": [
    "team-100-pass-gate.json",
    "team-run-all.json",
    "team-100-pass-gate-supplement.json"
  ],
  "external_transcript_location": "not recorded in repo",
  "created_at": "2026-05-08"
}
```

- [ ] **Step 3: Remove large tracked transcripts**

Run:

```bash
git rm artifacts/evidence/reminder-normal/team-100-pass-gate.json \
  artifacts/evidence/reminder-normal/team-run-all.json \
  artifacts/evidence/reminder-normal/team-100-pass-gate-supplement.json
```

Keep small targeted files such as:

- `team-case14.json`
- `team-case123.json`
- `team-smoke.json`

- [ ] **Step 4: Decide whether to document the evidence rule**

If the evidence policy should be durable, add a short rule to `docs/fitness/README.md`:

```markdown
Full-run LLM transcripts should not be committed as permanent evidence. Commit
compact manifests and small targeted case artifacts; store full transcripts in
external artifact storage or a local non-git path referenced by the manifest.
```

If this is only cleanup for this repair, do not change docs.

- [ ] **Step 5: Run repo-OS checks if docs changed**

If `docs/fitness/README.md` or verification docs changed, run:

```bash
pytest tests/unit/test_repo_os_structure.py -v
pytest tests/unit/test_guardrail_scripts.py -v
zsh scripts/check
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add artifacts/evidence/reminder-normal docs/fitness/README.md docs/fitness/coke-verification-matrix.md
git commit -m "chore(agent): compact team runtime evidence"
```

If docs did not change, omit the docs paths from `git add`.

---

### Task 11: Full Verification Gate

**Files:**
- Modify: none unless evidence manifests are created from this task.

- [ ] **Step 1: Run focused repair verification**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_team_runtime_execution.py \
  tests/unit/agent/test_team_runtime_plan_parser.py \
  tests/unit/agent/test_manager_prompt.py \
  tests/unit/agent/test_agent_handler.py \
  tests/unit/agent/test_reminder_intent_capability.py \
  tests/unit/runner/test_deferred_action_executor.py \
  tests/unit/runner/test_reminder_event_handler.py -v
```

Expected: PASS.

- [ ] **Step 2: Run worker runtime baseline**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/ tests/unit/runner/ -v
```

Expected: PASS. If failures appear outside touched behavior, classify them before patching.

- [ ] **Step 3: Run reminder normal-path eval**

Run:

```bash
AGENT_RUNTIME_VERSION=team python scripts/eval_reminder_normal_path_cases.py
```

Expected: PASS or classified failures. If it fails, classify each failure as one of:

- LLM protocol
- runtime
- evaluator
- environment/provider

Do not add case-specific runtime logic to turn this green.

- [ ] **Step 4: Run repo-OS check if docs/evidence policy changed**

Run only if Task 10 changed docs or repo-OS policy:

```bash
zsh scripts/check
```

Expected: PASS.

- [ ] **Step 5: Record final status**

Run:

```bash
git log --oneline --max-count=12
git status --short
```

Expected:

- branch contains separate commits for contract blockers, runner restoration, test cleanup, abstraction cleanup, and evidence cleanup
- worktree clean except intentionally ignored local artifacts

---

## Plan Self-Review Checklist

- Spec coverage:
  - B1/B7 covered by Tasks 1-2.
  - B6 covered by Task 3.
  - B5/B8 covered by Task 4.
  - B2 covered by Task 5.
  - B3 covered by Task 6.
  - B4 covered by Task 7.
  - test-quality issues covered by Task 8.
  - abstraction cleanup covered by Task 9.
  - evidence transcript policy covered by Task 10.
- Approved user decisions:
  - no rollback by default
  - mid-run interruption retained
  - abstraction cleanup included after blockers
- Placeholder scan:
  - no unresolved implementation markers remain
- Type consistency:
  - uses existing `AgentRunResult`, `OutputDisposition`, `VisibleMessage`,
    `DeferredActionFireResult`, and runner helper names from current code
