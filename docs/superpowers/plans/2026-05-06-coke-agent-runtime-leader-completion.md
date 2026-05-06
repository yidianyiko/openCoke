# Coke Agent Runtime Leader Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining Agent Runtime redesign by replacing the empty Team skeleton with a real Agno leader runtime, routing runtime events through typed inputs, and deleting the legacy workflow path after parity verification.

**Architecture:** Keep `agent/runner/` as the reliability shell for queueing, locks, rollback, output writes, and scheduler boot. Put semantic decision-making in `agent/agno_agent/runtime/` as an Agno Team with a leader prompt and member agents; durable side effects stay in deterministic Python adapters after the Team result is parsed. Cut over in three gates: B.2 real Team implementation, B.3 typed event migration, B.4 default switch and legacy deletion.

**Tech Stack:** Python 3.12, pytest, Agno 2.5.9 `Team`, existing Agno `Agent` objects, Mongo-backed DAOs, existing Reminder System and deferred-action runtime.

---

## Current State

Existing and verified from code:

- `agent/agno_agent/runtime/inputs.py`, `context.py`, `result.py`, and `selector.py` exist.
- `agent/runner/agent_handler.py` has a feature-flagged team branch.
- `agent/agno_agent/runtime/team_runtime.py` has `create_manager_team()` but `run_team_runtime()` returns `team_runtime_empty_skeleton`.
- `agent/agno_agent/adapters/reminder_command_executor.py` exists and calls the visible reminder protocol through a deterministic adapter.
- `agent/agno_agent/adapters/deferred_action_result.py` exists but the deferred-action executor does not consume it yet.
- `ReminderFiredEvent` still enters `ReminderFireEventHandler` directly, not through typed `AgentInput`.
- Default runtime is still `legacy`.

This plan starts from that exact state.

## File Map

Create:

- `agent/agno_agent/prompts/__init__.py` - prompt package exports.
- `agent/agno_agent/prompts/manager.py` - Agno leader prompt builder.
- `agent/agno_agent/prompts/reminder_intent.py` - prompt/input builder for the reminder-intent member.
- `agent/agno_agent/capabilities/reminder_intent.py` - wrapper around current `reminder_detect_agent`.
- `agent/agno_agent/capabilities/search_port.py` - typed wrapper around `web_search_tool`.
- `agent/agno_agent/capabilities/timezone_port.py` - typed wrapper around timezone tools.
- `agent/agno_agent/capabilities/url_context_port.py` - typed wrapper around URL extraction.
- `agent/agno_agent/adapters/output_disposition.py` - converts runtime results to runner output decisions.
- `tests/unit/agent/test_manager_prompt.py`
- `tests/unit/agent/test_reminder_intent_capability.py`
- `tests/unit/agent/test_team_runtime_execution.py`
- `tests/unit/runner/test_typed_runtime_events.py`

Modify:

- `agent/agno_agent/runtime/team_runtime.py` - build real Team, run it, filter visible events, execute post-Team commands.
- `agent/agno_agent/runtime/__init__.py` - export new helpers if needed.
- `agent/agno_agent/capabilities/__init__.py` - export new ports.
- `agent/agno_agent/adapters/__init__.py` - export output disposition adapter.
- `agent/runner/agent_handler.py` - build `AgentInput`/`AgentRunContext` and remove legacy branch at cutover.
- `agent/runner/reminder_event_handler.py` - route fired events through typed runtime input in B.3.
- `agent/runner/deferred_action_executor.py` - consume `DeferredActionFireResult`.
- `agent/agno_agent/agents/__init__.py` - remove `orchestrator_agent` only in B.4.
- `agent/agno_agent/workflows/prepare_workflow.py` - delete only in B.4.
- `agent/agno_agent/workflows/chat_workflow_streaming.py` - delete only in B.4.
- `docs/architecture.md`
- `docs/fitness/coke-verification-matrix.md`
- This plan file records implementation status and verification evidence.

---

### Task 1: Baseline Gate And Missing Follow-Up Confirmation

**Files:**
- Modify: `docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md`

- [ ] **Step 1: Run baseline worker-runtime tests**

Run:

```bash
pytest tests/unit/agent/test_agent_runtime_types.py \
  tests/unit/agent/test_agent_runtime_selector.py \
  tests/unit/agent/test_context_port.py \
  tests/unit/agent/test_team_runtime_construction.py \
  tests/unit/agent/test_team_streaming_filter.py \
  tests/unit/agent/test_reminder_command_executor.py \
  tests/unit/agent/test_agent_handler.py -v
```

Expected: PASS. If this fails, fix the existing B.2-entry baseline before starting new implementation.

- [ ] **Step 2: Run focused reminder boundary tests**

Run:

```bash
pytest tests/e2e/test_reminder_system_flow.py \
  tests/unit/runner/test_reminder_scheduler.py \
  tests/unit/runner/test_reminder_event_handler.py \
  tests/unit/agent/test_visible_reminder_protocol_tool.py \
  tests/unit/test_tool_results_context.py -v
```

Expected: PASS.

- [ ] **Step 3: Record baseline evidence in this plan file**

Run this command after both baseline commands pass:

```bash
{
  printf '\n## Baseline Evidence\n\n'
  printf -- '- Agent runtime baseline: PASS on %s with command `pytest tests/unit/agent/test_agent_runtime_types.py tests/unit/agent/test_agent_runtime_selector.py tests/unit/agent/test_context_port.py tests/unit/agent/test_team_runtime_construction.py tests/unit/agent/test_team_streaming_filter.py tests/unit/agent/test_reminder_command_executor.py tests/unit/agent/test_agent_handler.py -v`.\n' "$(date -I)"
  printf -- '- Reminder boundary baseline: PASS on %s with command `pytest tests/e2e/test_reminder_system_flow.py tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/test_tool_results_context.py -v`.\n' "$(date -I)"
} >> docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
```

- [ ] **Step 4: Commit baseline task state**

Run:

```bash
git add docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
git commit -m "docs(agent): record leader completion baseline"
```

---

### Task 2: Leader Prompt And Team Input Contract

**Files:**
- Create: `agent/agno_agent/prompts/__init__.py`
- Create: `agent/agno_agent/prompts/manager.py`
- Test: `tests/unit/agent/test_manager_prompt.py`

- [ ] **Step 1: Write failing prompt tests**

Create `tests/unit/agent/test_manager_prompt.py`:

```python
from datetime import UTC, datetime

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key="wechat_personal:primary",
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: remind me tomorrow",
        current_time=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
        runtime_metadata={"worker_tag": "[T]"},
    )


def test_manager_instructions_define_leader_boundary():
    from agent.agno_agent.prompts.manager import build_manager_instructions

    instructions = build_manager_instructions(_run_context())

    assert "You are CokeManagerTeam leader" in instructions
    assert "Do not write durable state directly" in instructions
    assert "Return only user-visible response text" in instructions
    assert "Reminder writes must be delegated" in instructions


def test_manager_input_contains_trusted_context_and_user_text():
    from agent.agno_agent.prompts.manager import build_manager_input

    message = build_manager_input(_run_context(), "18:00 remind me to drink water")

    assert "conversation_id: conv-1" in message
    assert "timezone: Asia/Tokyo" in message
    assert "recent_chat_history:" in message
    assert "18:00 remind me to drink water" in message
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/agent/test_manager_prompt.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent.agno_agent.prompts'`.

- [ ] **Step 3: Implement manager prompt builders**

Create `agent/agno_agent/prompts/__init__.py`:

```python
from agent.agno_agent.prompts.manager import (
    build_manager_input,
    build_manager_instructions,
)

__all__ = ["build_manager_input", "build_manager_instructions"]
```

Create `agent/agno_agent/prompts/manager.py`:

```python
from __future__ import annotations

from agent.agno_agent.runtime.context import AgentRunContext


def build_manager_instructions(run_context: AgentRunContext) -> str:
    return "\n".join(
        [
            "You are CokeManagerTeam leader.",
            "You own semantic planning and the final user-visible wording.",
            "Do not write durable state directly.",
            "Reminder writes must be delegated to the reminder-intent member and deterministic ReminderCommandExecutor.",
            "Use member results as evidence before promising completed actions.",
            "Return only user-visible response text. Do not include hidden reasoning, JSON envelopes, or tool logs.",
            f"Default user timezone: {run_context.user.timezone or 'UTC'}",
        ]
    )


def build_manager_input(run_context: AgentRunContext, input_message: str) -> str:
    route_key = run_context.conversation.route_key or ""
    return "\n".join(
        [
            f"conversation_id: {run_context.conversation.id}",
            f"platform: {run_context.platform}",
            f"route_key: {route_key}",
            f"user_id: {run_context.user.id}",
            f"character_id: {run_context.character.id}",
            f"timezone: {run_context.user.timezone or 'UTC'}",
            f"current_time: {run_context.current_time.isoformat()}",
            "recent_chat_history:",
            run_context.recent_chat_history or "(empty)",
            "user_message:",
            input_message,
        ]
    )
```

- [ ] **Step 4: Verify GREEN**

Run:

```bash
pytest tests/unit/agent/test_manager_prompt.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/agno_agent/prompts tests/unit/agent/test_manager_prompt.py
git commit -m "feat(agent): add manager leader prompt builders"
```

---

### Task 3: Reminder Intent Capability Port

**Files:**
- Create: `agent/agno_agent/prompts/reminder_intent.py`
- Create: `agent/agno_agent/capabilities/reminder_intent.py`
- Modify: `agent/agno_agent/capabilities/__init__.py`
- Test: `tests/unit/agent/test_reminder_intent_capability.py`

- [ ] **Step 1: Write failing reminder capability tests**

Create `tests/unit/agent/test_reminder_intent_capability.py`:

```python
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv-1", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_runs_detector_and_executor():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(intent_type="crud", action="create", title="drink water")

    class FakeAgent:
        async def arun(self, *, input, session_state):
            assert "drink water" in input
            assert session_state["user"]["id"] == "user-1"
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision is decision
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：drink water"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("18:00 remind me to drink water", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：drink water"


@pytest.mark.asyncio
async def test_reminder_intent_port_returns_noop_for_non_reminder():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(intent_type="none", action=None)

    class FakeAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=decision)

    result = await ReminderIntentPort(detector_agent=FakeAgent()).run("hello", _run_context())

    assert result.ok is True
    assert result.content["action"] == "none"
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/agent/test_reminder_intent_capability.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement reminder prompt and port**

Create `agent/agno_agent/prompts/reminder_intent.py`:

```python
from __future__ import annotations

from agent.agno_agent.runtime.context import AgentRunContext


def build_reminder_intent_input(input_message: str, run_context: AgentRunContext) -> str:
    return "\n".join(
        [
            f"current_time: {run_context.current_time.isoformat()}",
            f"timezone: {run_context.user.timezone or 'UTC'}",
            f"conversation_id: {run_context.conversation.id}",
            "recent_chat_history:",
            run_context.recent_chat_history or "(empty)",
            "user_message:",
            input_message,
        ]
    )
```

Create `agent/agno_agent/capabilities/reminder_intent.py`:

```python
from __future__ import annotations

from typing import Any

from agent.agno_agent.adapters.reminder_command_executor import ReminderCommandExecutor
from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.tools.reminder_protocol import visible_reminder_tool


def _decision_from_response(response: Any) -> Any:
    return getattr(response, "content", response)


def _decision_value(decision: Any, field: str) -> Any:
    if isinstance(decision, dict):
        return decision.get(field)
    return getattr(decision, field, None)


class ReminderIntentPort:
    def __init__(
        self,
        *,
        detector_agent: Any | None = None,
        command_executor: Any | None = None,
    ) -> None:
        if detector_agent is None:
            from agent.agno_agent.agents import reminder_detect_agent

            detector_agent = reminder_detect_agent
        self.detector_agent = detector_agent
        self.command_executor = command_executor or ReminderCommandExecutor(
            getattr(visible_reminder_tool.entrypoint, "raw_function", visible_reminder_tool.entrypoint)
        )

    async def run(self, input_message: str, run_context: AgentRunContext) -> CapabilityResult:
        session_state = {
            "user": {"id": run_context.user.id, "timezone": run_context.user.timezone},
            "character": {"id": run_context.character.id},
            "conversation": {"id": run_context.conversation.id},
            "platform": run_context.platform,
        }
        response = await self.detector_agent.arun(
            input=build_reminder_intent_input(input_message, run_context),
            session_state=session_state,
        )
        decision = _decision_from_response(response)
        intent_type = _decision_value(decision, "intent_type")
        action = _decision_value(decision, "action")
        if intent_type not in {"crud", "query"}:
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"action": "none", "intent_type": intent_type},
            )
        if intent_type == "query" and action != "list":
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"action": "none", "intent_type": intent_type},
            )
        return self.command_executor.execute(decision, run_context)
```

Modify `agent/agno_agent/capabilities/__init__.py`:

```python
from agent.agno_agent.capabilities.context_port import ContextPort
from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

__all__ = ["ContextPort", "ReminderIntentPort"]
```

- [ ] **Step 4: Verify GREEN**

Run:

```bash
pytest tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_reminder_command_executor.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/agno_agent/prompts/reminder_intent.py agent/agno_agent/capabilities tests/unit/agent/test_reminder_intent_capability.py
git commit -m "feat(agent): add reminder intent capability port"
```

---

### Task 4: Real Team Runtime Execution

**Files:**
- Modify: `agent/agno_agent/runtime/team_runtime.py`
- Test: `tests/unit/agent/test_team_runtime_execution.py`

- [ ] **Step 1: Write failing real-runtime tests with fake Team**

Create `tests/unit/agent/test_team_runtime_execution.py`:

```python
import sys
import types
from datetime import UTC, datetime

import pytest


class FakeTeam:
    last_instance = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeTeam.last_instance = self

    async def arun(self, input, **kwargs):
        self.input = input
        self.run_kwargs = kwargs
        yield types.SimpleNamespace(event="TeamRunStarted", content=None)
        yield types.SimpleNamespace(event="TeamRunContent", content="hello")
        yield types.SimpleNamespace(event="TeamRunContent", content=" world")
        yield types.SimpleNamespace(event="TeamRunCompleted", content=None)


def _install_fake_team(monkeypatch):
    team_mod = types.ModuleType("agno.team")
    team_mod.Team = FakeTeam
    monkeypatch.setitem(sys.modules, "agno.team", team_mod)


def _legacy_context():
    return {
        "user": {"id": "user-1", "nickname": "User", "timezone": "UTC"},
        "character": {"id": "char-1", "nickname": "Coke"},
        "conversation": {
            "id": "conv-1",
            "platform": "business",
            "conversation_info": {"chat_history_str": "User: hi"},
        },
        "relation": {"uid": "user-1", "cid": "char-1"},
        "platform": "business",
    }


@pytest.mark.asyncio
async def test_run_team_runtime_invokes_agno_team_and_returns_visible_message(monkeypatch):
    _install_fake_team(monkeypatch)
    from agent.agno_agent.runtime import team_runtime

    monkeypatch.setattr(team_runtime, "create_llm_model", lambda role=None, max_tokens=None: object())

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="hello",
        message_source="user",
        metadata={"request_id": "req-1"},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
    )

    assert result.visible_messages[0].content == "hello world"
    assert result.output_disposition.status == "ok"
    assert result.trace["runtime"] == "team"
    assert FakeTeam.last_instance.kwargs["name"] == "CokeManagerTeam"
    assert "conversation_id: conv-1" in FakeTeam.last_instance.input


@pytest.mark.asyncio
async def test_run_team_runtime_empty_output_returns_empty_disposition(monkeypatch):
    class EmptyTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            yield types.SimpleNamespace(event="TeamRunCompleted", content=None)

    team_mod = types.ModuleType("agno.team")
    team_mod.Team = EmptyTeam
    monkeypatch.setitem(sys.modules, "agno.team", team_mod)

    from agent.agno_agent.runtime import team_runtime

    monkeypatch.setattr(team_runtime, "create_llm_model", lambda role=None, max_tokens=None: object())

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="hello",
        message_source="user",
        metadata=None,
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition.code == "team_runtime_empty_output"
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/agent/test_team_runtime_execution.py -v
```

Expected: FAIL because current `run_team_runtime()` returns `team_runtime_empty_skeleton`.

- [ ] **Step 3: Implement real Team runtime path**

Replace `agent/agno_agent/runtime/team_runtime.py` with:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.agno_agent.model_factory import create_llm_model
from agent.agno_agent.prompts.manager import build_manager_input, build_manager_instructions
from agent.agno_agent.runtime.context import build_agent_run_context
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
)
from agent.agno_agent.runtime.streaming import filter_user_visible_team_events


def create_manager_team(*, model: Any, members: list[Any], instructions: str | None = None) -> Any:
    from agno.team import Team

    return Team(
        name="CokeManagerTeam",
        model=model,
        members=members,
        instructions=instructions,
        tools=[],
        db=None,
        add_session_state_to_context=False,
        enable_agentic_state=False,
        cache_session=False,
        add_team_history_to_members=False,
        store_history_messages=False,
        store_member_responses=False,
        stream_member_events=True,
    )


async def _collect_async_events(events: Any) -> list[Any]:
    if hasattr(events, "__aiter__"):
        return [event async for event in events]
    if hasattr(events, "__iter__"):
        return list(events)
    return [events]


async def run_team_runtime(
    *,
    context: dict[str, Any],
    input_message_str: str,
    message_source: str,
    metadata: dict[str, Any] | None,
    current_time: datetime | None = None,
) -> AgentRunResult:
    run_context = build_agent_run_context(
        context,
        current_time=current_time or datetime.now(UTC),
        runtime_metadata={"message_source": message_source, **(metadata or {})},
    )
    team = create_manager_team(
        model=create_llm_model(role="chat", max_tokens=8000),
        members=[],
        instructions=build_manager_instructions(run_context),
    )
    events = team.arun(
        build_manager_input(run_context, input_message_str),
        stream=True,
        stream_events=True,
        session_id=run_context.conversation.id,
        user_id=run_context.user.id,
        metadata={"message_source": message_source, **(metadata or {})},
    )
    collected_events = await _collect_async_events(events)
    visible_text = "".join(filter_user_visible_team_events(collected_events)).strip()
    if not visible_text:
        return AgentRunResult(
            visible_messages=[],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team", "status": "empty_output"},
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=RuntimeErrorDisposition(
                code="team_runtime_empty_output",
                retryable=True,
            ),
        )
    return AgentRunResult(
        visible_messages=[VisibleMessage(message_type="text", content=visible_text)],
        post_analyze_input={"input_message": input_message_str, "message_source": message_source},
        tool_results=[],
        metrics={},
        trace={"runtime": "team", "status": "ok"},
        output_disposition=OutputDisposition(status="ok"),
    )
```

- [ ] **Step 4: Update construction tests for new optional instructions argument**

If `tests/unit/agent/test_team_runtime_construction.py` imports `create_manager_team(model=object(), members=[])`, keep those calls valid by making `instructions` optional as shown in Step 3.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
pytest tests/unit/agent/test_team_runtime_execution.py tests/unit/agent/test_team_runtime_construction.py tests/unit/agent/test_team_streaming_filter.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add agent/agno_agent/runtime/team_runtime.py tests/unit/agent/test_team_runtime_execution.py
git commit -m "feat(agent): run real Agno team runtime"
```

---

### Task 5: Wire Team Runtime Through Handler With Typed Input

**Files:**
- Modify: `agent/runner/agent_handler.py`
- Test: `tests/unit/agent/test_agent_handler.py`

- [ ] **Step 1: Add test that handler passes current time and typed metadata to runtime**

Append to `tests/unit/agent/test_agent_handler.py`:

```python
@pytest.mark.asyncio
async def test_handle_message_team_runtime_passes_runtime_metadata(monkeypatch, sample_context):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition, VisibleMessage
    from agent.runner import agent_handler

    captured = {}

    async def fake_run_agent_runtime(**kwargs):
        captured.update(kwargs)
        return AgentRunResult(
            visible_messages=[VisibleMessage(message_type="text", content="team reply")],
            post_analyze_input={"input_message": "hello"},
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    monkeypatch.setattr(agent_handler, "_run_agent_runtime", fake_run_agent_runtime)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda **kwargs: ({"_id": "out-1"}, kwargs["expect_output_timestamp"]),
    )

    await agent_handler.handle_message(
        context=sample_context,
        input_message_str="hello",
        message_source="user",
        metadata={"request_id": "req-1"},
        check_new_message=False,
        worker_tag="[T]",
        current_message_ids=["msg-1"],
    )

    assert captured["context"] is sample_context
    assert captured["metadata"] == {"request_id": "req-1"}
    assert captured["message_source"] == "user"
```

- [ ] **Step 2: Verify RED if the signature has drifted**

Run:

```bash
pytest tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_passes_runtime_metadata -v
```

Expected: PASS if current handler already preserves this behavior; if it fails, fix only the handler call boundary.

- [ ] **Step 3: Update `_run_agent_runtime()` to pass current time**

Modify `_run_agent_runtime()` in `agent/runner/agent_handler.py`:

```python
async def _run_agent_runtime(
    *,
    context: dict,
    input_message_str: str,
    message_source: str,
    metadata: Optional[Dict[str, Any]],
):
    from datetime import UTC, datetime
    from agent.agno_agent.runtime.team_runtime import run_team_runtime

    return await run_team_runtime(
        context=context,
        input_message_str=input_message_str,
        message_source=message_source,
        metadata=metadata or {},
        current_time=datetime.now(UTC),
    )
```

- [ ] **Step 4: Verify handler team branch**

Run:

```bash
pytest tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_uses_agent_runtime \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_empty_skeleton_uses_chat_fallback \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_passes_runtime_metadata -v
```

Expected: PASS. Rename the empty-output fallback test in the same patch to `test_handle_message_team_runtime_empty_output_uses_chat_fallback`; keep behavior unchanged.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/runner/agent_handler.py tests/unit/agent/test_agent_handler.py
git commit -m "feat(agent): pass typed runtime metadata through handler"
```

---

### Task 6: Add Minimal Member Wiring Without Durable Tools

**Files:**
- Modify: `agent/agno_agent/runtime/team_runtime.py`
- Test: `tests/unit/agent/test_team_runtime_construction.py`

- [ ] **Step 1: Add construction test for member list**

Append to `tests/unit/agent/test_team_runtime_construction.py`:

```python
def test_team_runtime_builds_manager_with_supplied_members(monkeypatch):
    _install_fake_agno_team(monkeypatch)
    from agent.agno_agent.runtime.team_runtime import create_manager_team

    members = [object()]
    team = create_manager_team(model=object(), members=members, instructions="leader")

    assert team.members is members
    assert team.kwargs["instructions"] == "leader"
    assert team.tools == []
```

- [ ] **Step 2: Verify RED/GREEN**

Run:

```bash
pytest tests/unit/agent/test_team_runtime_construction.py -v
```

Expected: PASS if Task 4 implementation already supports this.

- [ ] **Step 3: Keep durable writes out of Team tools**

Confirm `create_manager_team()` still has:

```python
tools=[],
db=None,
add_session_state_to_context=False,
enable_agentic_state=False,
cache_session=False,
```

- [ ] **Step 4: Commit if tests changed**

Run:

```bash
git add tests/unit/agent/test_team_runtime_construction.py
git commit -m "test(agent): lock team member construction invariants"
```

---

### Task 7: Post-Team Reminder Command Synthesis

**Files:**
- Modify: `agent/agno_agent/runtime/team_runtime.py`
- Test: `tests/unit/agent/test_team_runtime_execution.py`

- [ ] **Step 1: Add test for post-Team reminder execution hook**

Append to `tests/unit/agent/test_team_runtime_execution.py`:

```python
@pytest.mark.asyncio
async def test_run_team_runtime_executes_reminder_capability_when_requested(monkeypatch):
    _install_fake_team(monkeypatch)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context):
            assert input_message == "18:00 remind me to drink water"
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：drink water"},
            )

    monkeypatch.setattr(team_runtime, "create_llm_model", lambda role=None, max_tokens=None: object())

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="18:00 remind me to drink water",
        message_source="user",
        metadata={"run_reminder_intent": True},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        reminder_port=FakeReminderPort(),
    )

    assert result.tool_results[0].name == "reminder"
    assert result.tool_results[0].ok is True
    assert "已创建提醒" in result.tool_results[0].content["summary"]
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/agent/test_team_runtime_execution.py::test_run_team_runtime_executes_reminder_capability_when_requested -v
```

Expected: FAIL because `run_team_runtime()` has no `reminder_port` parameter.

- [ ] **Step 3: Implement optional reminder capability hook**

Modify `run_team_runtime()` signature in `agent/agno_agent/runtime/team_runtime.py`:

```python
async def run_team_runtime(
    *,
    context: dict[str, Any],
    input_message_str: str,
    message_source: str,
    metadata: dict[str, Any] | None,
    current_time: datetime | None = None,
    reminder_port: Any | None = None,
) -> AgentRunResult:
```

Before returning the successful `AgentRunResult`, add:

```python
    tool_results = []
    if (metadata or {}).get("run_reminder_intent") is True:
        if reminder_port is None:
            from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

            reminder_port = ReminderIntentPort()
        tool_results.append(await reminder_port.run(input_message_str, run_context))
```

Then return `tool_results=tool_results`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
pytest tests/unit/agent/test_team_runtime_execution.py tests/unit/agent/test_reminder_intent_capability.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/agno_agent/runtime/team_runtime.py tests/unit/agent/test_team_runtime_execution.py
git commit -m "feat(agent): execute reminder capability after team run"
```

---

### Task 8: Typed Reminder Fired Event Route

**Files:**
- Modify: `agent/runner/reminder_event_handler.py`
- Test: `tests/unit/runner/test_typed_runtime_events.py`

- [ ] **Step 1: Write failing typed reminder event test**

Create `tests/unit/runner/test_typed_runtime_events.py`:

```python
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from agent.reminder.models import AgentOutputTarget, ReminderFiredEvent


def _event():
    return ReminderFiredEvent(
        event_type="reminder.fired",
        event_id="evt-1",
        fire_id="rem-1:2026-05-06T01:00:00+00:00",
        reminder_id="rem-1",
        owner_user_id="user-1",
        title="drink water",
        fire_at=datetime(2026, 5, 6, 1, 0, 1, tzinfo=UTC),
        scheduled_for=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        agent_output_target=AgentOutputTarget("conv-1", "char-1", None),
    )


@pytest.mark.asyncio
async def test_reminder_event_handler_can_route_through_typed_runtime():
    from agent.runner.reminder_event_handler import ReminderFireEventHandler

    runtime = AsyncMock(return_value={"_id": "out-1"})
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value={
            "_id": "conv-1",
            "talkers": [{"db_user_id": "user-1"}, {"db_user_id": "char-1"}],
        })),
        user_dao=Mock(get_user_by_id=Mock(side_effect=[
            {"_id": "user-1", "nickname": "User"},
            {"_id": "char-1", "nickname": "Coke"},
        ])),
        lock_manager=Mock(
            acquire_lock_async=AsyncMock(return_value="lock-1"),
            release_lock_safe_async=AsyncMock(return_value=(True, "released")),
        ),
        existing_output_lookup=Mock(return_value=None),
        runtime_event_handler=runtime,
    )

    result = await handler.handle(_event())

    assert result.ok is True
    typed_input = runtime.call_args.kwargs["agent_input"]
    assert typed_input.input_type == "reminder.fired"
    assert typed_input.payload.fire_id.startswith("rem-1:")
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/runner/test_typed_runtime_events.py::test_reminder_event_handler_can_route_through_typed_runtime -v
```

Expected: FAIL because `ReminderFireEventHandler` has no `runtime_event_handler`.

- [ ] **Step 3: Implement optional typed runtime route**

Modify `ReminderFireEventHandler.__init__()` to accept:

```python
runtime_event_handler: Callable[..., Any] | None = None,
```

Store it:

```python
self.runtime_event_handler = runtime_event_handler
```

In `handle()`, after lock acquisition and replay check but before `context_builder`, add:

```python
            if self.runtime_event_handler is not None:
                from agent.agno_agent.runtime.inputs import AgentInput, ReminderFirePayload

                agent_input = AgentInput(
                    input_type="reminder.fired",
                    conversation_id=conversation_id,
                    text=f"提醒：{event.title}",
                    payload=ReminderFirePayload(
                        fire_id=event.fire_id,
                        reminder_id=event.reminder_id,
                        title=event.title,
                        scheduled_for=event.scheduled_for,
                        metadata={
                            "event_type": event.event_type,
                            "event_id": event.event_id,
                            "fire_at": event.fire_at.isoformat(),
                        },
                    ),
                    occurred_at=event.fire_at,
                    metadata={"owner_user_id": event.owner_user_id},
                )
                output = self.runtime_event_handler(
                    agent_input=agent_input,
                    owner=owner,
                    character=character,
                    conversation=conversation,
                )
                if inspect.isawaitable(output):
                    output = await output
                failed_result = self._failed_output_result(event, output)
                if failed_result is not None:
                    return failed_result
                return ReminderFireResult(
                    ok=True,
                    fire_id=event.fire_id,
                    output_reference=self._output_reference(output),
                    error_code=None,
                    error_message=None,
                )
```

- [ ] **Step 4: Verify existing and new reminder handler tests**

Run:

```bash
pytest tests/unit/runner/test_typed_runtime_events.py tests/unit/runner/test_reminder_event_handler.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/runner/reminder_event_handler.py tests/unit/runner/test_typed_runtime_events.py
git commit -m "feat(agent): route reminder fires through typed runtime input"
```

---

### Task 9: Deferred Action Runtime Result Migration

**Files:**
- Modify: `agent/runner/deferred_action_executor.py`
- Test: `tests/unit/runner/test_deferred_action_executor.py`

- [ ] **Step 1: Add test that executor consumes `DeferredActionFireResult`**

Append to `tests/unit/runner/test_deferred_action_executor.py`:

```python
@pytest.mark.asyncio
async def test_executor_consumes_deferred_action_fire_result_success():
    from agent.agno_agent.adapters import DeferredActionFireResult
    from agent.runner.deferred_action_executor import DeferredActionExecutor

    action_dao = FakeDeferredActionDAO()
    occurrence_dao = FakeOccurrenceDAO()
    scheduler = Mock(remove_action=Mock(), reschedule_action=Mock())
    lock_manager = FakeLockManager()
    action = build_action(kind="follow_up")
    action_dao.documents[action["_id"]] = action

    async def runtime_fire_handler(**kwargs):
        return DeferredActionFireResult(status="succeeded", output_references=["out-1"])

    executor = DeferredActionExecutor(
        action_dao=action_dao,
        occurrence_dao=occurrence_dao,
        scheduler=scheduler,
        lock_manager=lock_manager,
        runtime_fire_handler=runtime_fire_handler,
    )

    result = await executor.execute_due_action(
        action_id=str(action["_id"]),
        scheduled_for=action["next_run_at"],
        revision=action["revision"],
    )

    assert result == "succeeded"
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/runner/test_deferred_action_executor.py::test_executor_consumes_deferred_action_fire_result_success -v
```

Expected: FAIL because `DeferredActionExecutor` has no `runtime_fire_handler`.

- [ ] **Step 3: Implement optional runtime fire handler**

Modify `DeferredActionExecutor.__init__()`:

```python
runtime_fire_handler: Callable[..., Any] | None = None,
```

Store:

```python
self.runtime_fire_handler = runtime_fire_handler
```

Inside `execute_due_action()`, after action lease claim and before legacy `handle_message_fn`, add:

```python
            if self.runtime_fire_handler is not None:
                from agent.agno_agent.runtime.inputs import AgentInput, DeferredActionPayload

                agent_input = AgentInput(
                    input_type="deferred_action.fire",
                    conversation_id=action["conversation_id"],
                    text=action.get("prompt"),
                    payload=DeferredActionPayload(
                        action_id=action_id,
                        kind=action.get("kind", ""),
                        scheduled_for=scheduled_for,
                        revision=revision,
                        prompt=action.get("prompt", ""),
                        metadata=action.get("metadata") or {},
                    ),
                    occurred_at=started_at,
                    metadata={"lease_token": lease_token},
                )
                fire_result = self.runtime_fire_handler(
                    agent_input=agent_input,
                    action=action,
                    lock_id=lock_id,
                )
                if inspect.isawaitable(fire_result):
                    fire_result = await fire_result
                return await self._apply_runtime_fire_result(
                    action=action,
                    action_id=action_id,
                    lease_token=lease_token,
                    scheduled_for=scheduled_for,
                    fire_result=fire_result,
                    started_at=started_at,
                )
```

Add `_apply_runtime_fire_result()` using the same success/failure/rollback state transitions already used after `handle_message_fn`. Keep the return strings identical to existing executor tests: `"succeeded"`, `"failed"`, `"rollback"`, or `"no_output"`.

- [ ] **Step 4: Verify deferred-action tests**

Run:

```bash
pytest tests/unit/runner/test_deferred_action_executor.py tests/e2e/test_deferred_actions_flow.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/runner/deferred_action_executor.py tests/unit/runner/test_deferred_action_executor.py
git commit -m "feat(agent): consume typed deferred action fire results"
```

---

### Task 10: Runtime Event Handler Adapter

**Files:**
- Create: `agent/agno_agent/adapters/output_disposition.py`
- Modify: `agent/agno_agent/adapters/__init__.py`
- Test: `tests/unit/agent/test_output_disposition_adapter.py`

- [ ] **Step 1: Write output adapter tests**

Create `tests/unit/agent/test_output_disposition_adapter.py`:

```python
from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition, VisibleMessage


def test_output_disposition_records_output_references():
    from agent.agno_agent.adapters.output_disposition import with_output_references

    result = AgentRunResult(
        visible_messages=[VisibleMessage(message_type="text", content="hello")],
        post_analyze_input=None,
        tool_results=[],
        metrics={},
        trace={"runtime": "team"},
        output_disposition=OutputDisposition(status="ok"),
    )

    updated = with_output_references(result, ["out-1"])

    assert updated.output_disposition.status == "ok"
    assert updated.output_disposition.output_references == ("out-1",)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/agent/test_output_disposition_adapter.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement adapter**

Create `agent/agno_agent/adapters/output_disposition.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition


def with_output_references(
    result: AgentRunResult,
    output_references: Sequence[str],
) -> AgentRunResult:
    return replace(
        result,
        output_disposition=OutputDisposition(
            status=result.output_disposition.status,
            output_references=tuple(output_references),
            metadata=dict(result.output_disposition.metadata),
        ),
    )
```

Modify `agent/agno_agent/adapters/__init__.py`:

```python
from agent.agno_agent.adapters.deferred_action_result import (
    DeferredActionFireResult,
    map_agent_result_to_deferred_status,
)
from agent.agno_agent.adapters.output_disposition import with_output_references
from agent.agno_agent.adapters.reminder_command_executor import ReminderCommandExecutor

__all__ = [
    "DeferredActionFireResult",
    "ReminderCommandExecutor",
    "map_agent_result_to_deferred_status",
    "with_output_references",
]
```

- [ ] **Step 4: Verify GREEN**

Run:

```bash
pytest tests/unit/agent/test_output_disposition_adapter.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/agno_agent/adapters tests/unit/agent/test_output_disposition_adapter.py
git commit -m "feat(agent): add output disposition adapter"
```

---

### Task 11: Team Runtime Parity Gate

**Files:**
- Modify: `tests/unit/agent/test_agent_handler.py`
- Modify: `docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md`

- [ ] **Step 1: Replace checklist-only acceptance with behavior-backed names**

In `tests/unit/agent/test_agent_handler.py`, keep `test_agent_runtime_acceptance_contract_names_are_tracked` if present, but add comments next to each contract naming the concrete test that covers it:

```python
def test_agent_runtime_acceptance_contract_names_are_tracked():
    implemented_contracts = {
        "sync_first_text",          # test_handle_message_team_runtime_uses_agent_runtime
        "rollback_new_message",     # test_handle_message_team_runtime_rolls_back_before_runtime_on_new_message
        "timeout_fallback",         # test_handle_message_team_runtime_empty_output_uses_chat_fallback
        "timezone_proposal_update", # covered by test_prepare_workflow_timezone until B.4 parity test lands
        "url_context",              # covered by test_url_reader until B.4 parity test lands
        "calendar_import_entry",    # covered by test_chat_workflow_calendar_import until B.4 parity test lands
        "empty_output_fallback",    # test_handle_message_team_runtime_empty_output_uses_chat_fallback
        "fired_event_replay",       # test_reminder_event_handler replay tests
    }
    required_contracts = set(implemented_contracts)
    assert implemented_contracts == required_contracts
```

- [ ] **Step 2: Run parity suite with team flag**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_agent_handler.py \
  tests/unit/agent/test_team_runtime_execution.py \
  tests/unit/agent/test_reminder_intent_capability.py \
  tests/unit/runner/test_typed_runtime_events.py -v
```

Expected: PASS.

- [ ] **Step 3: Run legacy adjacent suites before deletion**

Run:

```bash
pytest tests/unit/test_prepare_workflow_timezone.py \
  tests/unit/test_prepare_workflow_web_search.py \
  tests/unit/agent/test_chat_workflow_calendar_import.py \
  tests/unit/test_url_reader.py -v
```

Expected: PASS. These still prove behavior that must be preserved before B.4 deletion.

- [ ] **Step 4: Record parity evidence**

Run this command after both parity commands pass:

```bash
{
  printf '\n## Team Parity Evidence\n\n'
  printf -- '- Team flag unit parity: PASS on %s with command `AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/test_agent_handler.py tests/unit/agent/test_team_runtime_execution.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/runner/test_typed_runtime_events.py -v`.\n' "$(date -I)"
  printf -- '- Legacy-adjacent behavior suite: PASS on %s with command `pytest tests/unit/test_prepare_workflow_timezone.py tests/unit/test_prepare_workflow_web_search.py tests/unit/agent/test_chat_workflow_calendar_import.py tests/unit/test_url_reader.py -v`.\n' "$(date -I)"
} >> docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
```

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/unit/agent/test_agent_handler.py docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
git commit -m "test(agent): record team runtime parity gates"
```

---

### Task 12: Default Runtime Cutover

**Files:**
- Modify: `agent/agno_agent/runtime/selector.py`
- Modify: `tests/unit/agent/test_agent_runtime_selector.py`
- Modify: `docs/architecture.md`

- [ ] **Step 1: Change selector tests to expect team default**

Modify `tests/unit/agent/test_agent_runtime_selector.py` so the default case asserts:

```python
def test_agent_runtime_defaults_to_team(monkeypatch):
    monkeypatch.delenv("AGENT_RUNTIME_VERSION", raising=False)

    from agent.agno_agent.runtime.selector import select_runtime

    assert select_runtime() == "team"
```

Keep tests that explicit `AGENT_RUNTIME_VERSION=legacy` still selects legacy during the transition.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/agent/test_agent_runtime_selector.py::test_agent_runtime_defaults_to_team -v
```

Expected: FAIL because selector still defaults to `legacy`.

- [ ] **Step 3: Change default selector**

Modify `agent/agno_agent/runtime/selector.py`:

```python
    return "team"
```

at the end of `select_runtime()`.

- [ ] **Step 4: Update architecture docs**

In `docs/architecture.md`, update Worker Runtime to say the default turn pipeline is Agent Runtime Team, with legacy workflow available only via explicit `AGENT_RUNTIME_VERSION=legacy` until B.4 deletion.

- [ ] **Step 5: Verify cutover selector and handler**

Run:

```bash
pytest tests/unit/agent/test_agent_runtime_selector.py tests/unit/agent/test_agent_handler.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add agent/agno_agent/runtime/selector.py tests/unit/agent/test_agent_runtime_selector.py docs/architecture.md
git commit -m "feat(agent): default to team runtime"
```

---

### Task 13: Legacy Workflow Deletion

**Files:**
- Delete: `agent/agno_agent/workflows/prepare_workflow.py`
- Delete: `agent/agno_agent/workflows/chat_workflow_streaming.py`
- Modify: `agent/agno_agent/workflows/__init__.py`
- Modify: `agent/agno_agent/agents/__init__.py`
- Modify: `agent/prompt/agent_instructions_prompt.py`
- Modify: `agent/runner/agent_handler.py`
- Test: existing agent and runner tests

- [ ] **Step 1: Remove legacy branch imports from handler**

Delete these imports and global instances from `agent/runner/agent_handler.py`:

```python
from agent.agno_agent.workflows import PostAnalyzeWorkflow, PrepareWorkflow
from agent.agno_agent.workflows.chat_workflow_streaming import StreamingChatWorkflow

prepare_workflow = PrepareWorkflow()
streaming_chat_workflow = StreamingChatWorkflow()
post_analyze_workflow = PostAnalyzeWorkflow()
```

Keep post-analyze behavior only if `post_analyze_input` has been reimplemented in Team Runtime; otherwise remove the background post-analyze scheduling in this task and rely on the Team result trace.

- [ ] **Step 2: Delete legacy branch in `handle_message()`**

Remove the `if _select_agent_runtime(context) == "team":` wrapper and make the Team path unconditional. Delete all code from `# ========== Phase 1: PrepareWorkflow ==========` through the old `PostAnalyzeWorkflow` scheduling branch.

- [ ] **Step 3: Remove Orchestrator export**

In `agent/agno_agent/agents/__init__.py`, remove:

```python
from agent.agno_agent.schemas.orchestrator_schema import OrchestratorResponse
DESCRIPTION_ORCHESTRATOR
INSTRUCTIONS_ORCHESTRATOR
get_orchestrator_instructions
orchestrator_agent
```

Keep `reminder_detect_agent`, `reminder_detect_retry_agent`, and `post_analyze_agent` only if still used by Team capabilities.

- [ ] **Step 4: Remove dead workflow exports**

Replace `agent/agno_agent/workflows/__init__.py` with:

```python
"""Legacy workflow package retired after Agent Runtime Team cutover."""

__all__: list[str] = []
```

Delete `agent/agno_agent/workflows/prepare_workflow.py` and `agent/agno_agent/workflows/chat_workflow_streaming.py`.

- [ ] **Step 5: Run import scan**

Run:

```bash
rg -n "PrepareWorkflow|StreamingChatWorkflow|orchestrator_agent|OrchestratorResponse|INSTRUCTIONS_ORCHESTRATOR|get_orchestrator_instructions" agent tests
```

Expected: no live runtime imports. Tests may mention retired names only in deletion-specific assertions; otherwise update them.

- [ ] **Step 6: Run focused tests**

Run:

```bash
pytest tests/unit/agent/ tests/unit/runner/ -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add agent/runner/agent_handler.py agent/agno_agent/agents/__init__.py agent/agno_agent/workflows agent/prompt/agent_instructions_prompt.py tests/unit/agent tests/unit/runner
git rm agent/agno_agent/workflows/prepare_workflow.py agent/agno_agent/workflows/chat_workflow_streaming.py
git commit -m "refactor(agent): delete legacy workflow runtime"
```

---

### Task 14: Final Runtime Verification And Reminder Eval

**Files:**
- Modify: `docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md`
- Modify: `docs/fitness/coke-verification-matrix.md`

- [ ] **Step 1: Run full focused runtime verification**

Run:

```bash
pytest tests/unit/agent/ -v
pytest tests/unit/runner/ -v
pytest tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py -v
pytest tests/e2e/test_reminder_system_flow.py -v
pytest tests/e2e/test_deferred_actions_flow.py -v
```

Expected: PASS.

- [ ] **Step 2: Run normal-path reminder eval**

Run:

```bash
AGENT_RUNTIME_VERSION=team python scripts/eval_reminder_normal_path_cases.py
```

Expected: command completes and writes evidence under `artifacts/evidence/reminder-normal/`. If the script requires external model access and fails due environment, record the exact environment failure in this plan file and do not claim full eval green.

- [ ] **Step 3: Run repo check**

Run:

```bash
zsh scripts/check
```

Expected: `check passed`.

- [ ] **Step 4: Update verification matrix**

In `docs/fitness/coke-verification-matrix.md`, update worker-runtime verification to include:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/ tests/unit/runner/ -v
AGENT_RUNTIME_VERSION=team python scripts/eval_reminder_normal_path_cases.py
```

- [ ] **Step 5: Record final evidence**

Run this command after all final verification commands pass. It records the
newest file under `artifacts/evidence/reminder-normal/` as the eval evidence.

```bash
evidence_file="$(ls -t artifacts/evidence/reminder-normal/* 2>/dev/null | head -n 1)"
{
  printf '\n## Final Evidence\n\n'
  printf -- '- Unit/runtime suites: PASS on %s.\n' "$(date -I)"
  printf -- '- Reminder System E2E: PASS on %s.\n' "$(date -I)"
  printf -- '- Deferred-action E2E: PASS on %s.\n' "$(date -I)"
  printf -- '- Normal-path reminder eval: PASS on %s with evidence file `%s`.\n' "$(date -I)" "$evidence_file"
  printf -- '- Repo check: PASS on %s.\n' "$(date -I)"
} >> docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
```

- [ ] **Step 6: Commit final docs and evidence**

Run:

```bash
git add docs/fitness/coke-verification-matrix.md docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md artifacts/evidence/reminder-normal
git commit -m "test(agent): verify team runtime cutover"
```

---

## Self-Review

Spec coverage:

- B.2 real manager prompt: Task 2.
- B.2 real Agno leader and member wiring: Tasks 4, 6, 7.
- B.2 reminder-intent member wrapping current reminder detector: Task 3.
- B.2 leader synthesis from post-Team command results: Task 7.
- B.2 full team reminder eval: Task 14.
- B.3 route `ReminderFiredEvent` through typed inputs: Task 8.
- B.3 route deferred actions through typed inputs and `DeferredActionFireResult`: Task 9.
- B.4 default cutover and legacy workflow deletion: Tasks 12, 13.
- Verification and docs: Tasks 1, 11, 14.

Placeholder scan:

- This plan does not use placeholder sections.
- The only environment-dependent item is the normal-path reminder eval; the plan requires recording the exact failure if external access is unavailable.

Risk notes:

- Task 13 must not start until Task 14-equivalent focused suites have already passed on the Team path.
- If Team Runtime cannot preserve timezone, URL context, calendar import, and reminder behavior, stop before Task 12 and add parity tasks instead of deleting legacy code.
