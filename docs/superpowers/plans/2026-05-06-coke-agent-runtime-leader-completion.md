# Coke Agent Runtime Leader Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the Agent Runtime Team path without losing current runtime behavior, then cut over only after behavior-level parity is proven.

**Architecture:** Keep `agent/runner/` as the deterministic reliability shell for queueing, locks, replay checks, output writes, rollback, scheduler boot, occurrence state transitions, and post-analyze scheduling. Put semantic planning in `agent/agno_agent/runtime/` behind one typed `AgentInput` entrypoint that adapts user turns, reminder fires, and deferred-action fires into `AgentRunResult`; durable effects happen only through deterministic Python capability adapters after Team output is parsed. The legacy prepare/chat workflow remains selectable until Team path parity is proven for reminder CRUD, timezone proposal/update, URL context, calendar import entry, sync first text, rollback, reminder fired delivery, deferred-action delivery, and post-analyze scheduling.

**Tech Stack:** Python 3.12, pytest, Agno 2.5.9 `Team`, existing Agno `Agent` objects, Mongo-backed DAOs, existing Reminder System and deferred-action runtime.

---

## Critical Rules For Executors

- Do not start implementation on `main`; create an isolated worktree first.
- Do not delete `PrepareWorkflow` or `StreamingChatWorkflow` until Task 12 passes and Task 13 explicitly records the deletion evidence.
- Do not default to `team` until the Team path has behavior-level tests for every contract listed in Task 9.
- Do not use metadata-only switches such as `run_reminder_intent=True` as the only path for reminder behavior; real user text must trigger the reminder capability through the Team runtime plan parser.
- Do not claim reminder eval green if the eval fails because of external model access, judge timeout, or runtime instability. Record the exact failure and stop before default cutover.

## Current State

Verified from code before this plan was rewritten:

- `agent/agno_agent/runtime/inputs.py`, `context.py`, `result.py`, `selector.py`, and `streaming.py` exist.
- `agent/agno_agent/runtime/team_runtime.py` has `create_manager_team()` but `run_team_runtime()` returns `team_runtime_empty_skeleton`.
- `agent/runner/agent_handler.py` has a feature-flagged Team branch and a legacy `PrepareWorkflow -> StreamingChatWorkflow -> PostAnalyzeWorkflow` branch.
- `agent/agno_agent/adapters/reminder_command_executor.py` exists and calls the visible reminder protocol through a deterministic adapter.
- `agent/agno_agent/adapters/deferred_action_result.py` exists and maps `AgentRunResult` to `DeferredActionFireResult`, but `DeferredActionExecutor` does not consume a typed runtime result yet.
- `ReminderFiredEvent` is still handled directly by `ReminderFireEventHandler`.
- `select_runtime()` still defaults to `legacy`.

## File Map

Create:

- `agent/agno_agent/prompts/__init__.py` - prompt package exports.
- `agent/agno_agent/prompts/manager.py` - leader instruction and input builders.
- `agent/agno_agent/prompts/reminder_intent.py` - reminder capability input builder.
- `agent/agno_agent/capabilities/reminder_intent.py` - deterministic wrapper around current `reminder_detect_agent` and `ReminderCommandExecutor`.
- `agent/agno_agent/capabilities/url_context_port.py` - Team runtime URL context adapter using the existing URL reader path.
- `agent/agno_agent/capabilities/timezone_port.py` - Team runtime timezone proposal/update adapter using existing timezone behavior.
- `agent/agno_agent/capabilities/calendar_import_port.py` - Team runtime calendar-import entry adapter using the existing calendar import entry path.
- `agent/agno_agent/runtime/plan_parser.py` - converts Team-visible output commands and JSON arguments into deterministic capability requests.
- `agent/agno_agent/runtime/event_adapter.py` - one typed runtime entrypoint for `AgentInput`.
- `agent/agno_agent/adapters/output_disposition.py` - copies output references into immutable `AgentRunResult`.
- `tests/unit/agent/test_manager_prompt.py`
- `tests/unit/agent/test_reminder_intent_capability.py`
- `tests/unit/agent/test_team_runtime_execution.py`
- `tests/unit/agent/test_team_runtime_plan_parser.py`
- `tests/unit/agent/test_team_runtime_parity.py`
- `tests/unit/agent/test_output_disposition_adapter.py`
- `tests/unit/runner/test_typed_runtime_events.py`

Modify:

- `agent/agno_agent/runtime/team_runtime.py` - build real Team, parse capability commands, execute deterministic capabilities, and return `AgentRunResult`.
- `agent/agno_agent/runtime/__init__.py` - export event adapter helpers.
- `agent/agno_agent/capabilities/__init__.py` - export new capability ports.
- `agent/agno_agent/adapters/__init__.py` - export output disposition adapter.
- `agent/runner/agent_handler.py` - build `AgentInput` for user turns and call the typed runtime adapter in the Team branch.
- `agent/runner/reminder_event_handler.py` - optionally route reminder fire through typed runtime while preserving replay and lock behavior.
- `agent/runner/deferred_action_executor.py` - optionally route deferred action fire through typed runtime and consume `DeferredActionFireResult`.
- `agent/agno_agent/runtime/selector.py` - change default only in Task 12.
- `docs/architecture.md`
- `docs/fitness/coke-verification-matrix.md`
- This plan file for evidence sections.

Defer deletion until Task 13 only:

- `agent/agno_agent/workflows/prepare_workflow.py`
- `agent/agno_agent/workflows/chat_workflow_streaming.py`
- legacy exports from `agent/agno_agent/workflows/__init__.py`

---

### Task 1: Baseline Gate

**Files:**
- Modify: `docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md`

- [x] **Step 1: Run baseline worker-runtime tests**

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

Expected: PASS. If this fails, stop and fix the existing baseline before starting Team work.

- [x] **Step 2: Run baseline behavior suites that must survive cutover**

Run:

```bash
pytest tests/e2e/test_reminder_system_flow.py \
  tests/unit/runner/test_reminder_scheduler.py \
  tests/unit/runner/test_reminder_event_handler.py \
  tests/unit/agent/test_visible_reminder_protocol_tool.py \
  tests/unit/test_tool_results_context.py \
  tests/unit/test_prepare_workflow_timezone.py \
  tests/unit/test_prepare_workflow_web_search.py \
  tests/unit/agent/test_chat_workflow_calendar_import.py \
  tests/unit/test_url_reader.py \
  tests/e2e/test_deferred_actions_flow.py -v
```

Expected: PASS. If this fails, stop and fix the baseline behavior first.

- [x] **Step 3: Record baseline evidence**

Run:

```bash
{
  printf '\n## Baseline Evidence\n\n'
  printf -- '- Worker-runtime baseline: PASS on %s.\n' "$(date -I)"
  printf -- '- Legacy behavior baseline: PASS on %s.\n' "$(date -I)"
} >> docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
```

- [x] **Step 4: Commit baseline evidence**

Run:

```bash
git add docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
git commit -m "docs(agent): record runtime leader baseline"
```

---

## Baseline Evidence

- Worker-runtime baseline: PASS on 2026-05-07 with command `pytest tests/unit/agent/test_agent_runtime_types.py tests/unit/agent/test_agent_runtime_selector.py tests/unit/agent/test_context_port.py tests/unit/agent/test_team_runtime_construction.py tests/unit/agent/test_team_streaming_filter.py tests/unit/agent/test_reminder_command_executor.py tests/unit/agent/test_agent_handler.py -v` (57 passed).
- Legacy behavior baseline: PASS on 2026-05-07 with command `pytest tests/e2e/test_reminder_system_flow.py tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/test_tool_results_context.py tests/unit/test_prepare_workflow_timezone.py tests/unit/test_prepare_workflow_web_search.py tests/unit/agent/test_chat_workflow_calendar_import.py tests/unit/test_url_reader.py tests/e2e/test_deferred_actions_flow.py -v` (114 passed).

---

### Task 2: Leader Prompt And Command Contract

**Files:**
- Create: `agent/agno_agent/prompts/__init__.py`
- Create: `agent/agno_agent/prompts/manager.py`
- Create: `agent/agno_agent/runtime/plan_parser.py`
- Test: `tests/unit/agent/test_manager_prompt.py`
- Test: `tests/unit/agent/test_team_runtime_plan_parser.py`

- [ ] **Step 1: Write failing manager prompt tests**

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
    assert "Return user-visible text in the RESPONSE block" in instructions
    assert "REQUEST reminder_intent {}" in instructions
    assert "REQUEST url_context {}" in instructions
    assert "REQUEST timezone" in instructions
    assert "REQUEST calendar_import {}" in instructions


def test_manager_input_contains_trusted_context_and_user_text():
    from agent.agno_agent.prompts.manager import build_manager_input

    message = build_manager_input(_run_context(), "18:00 remind me to drink water")

    assert "conversation_id: conv-1" in message
    assert "timezone: Asia/Tokyo" in message
    assert "recent_chat_history:" in message
    assert "18:00 remind me to drink water" in message
```

- [ ] **Step 2: Write failing plan parser tests**

Create `tests/unit/agent/test_team_runtime_plan_parser.py`:

```python
def test_parse_response_and_capability_requests():
    from agent.agno_agent.runtime.plan_parser import parse_team_plan

    plan = parse_team_plan(
        "RESPONSE:\n我来处理。\n"
        "REQUEST reminder_intent {}\n"
        "REQUEST url_context {}\n"
        "REQUEST timezone {\"action\":\"direct_set\",\"timezone\":\"Asia/Tokyo\"}\n"
    )

    assert plan.response_text == "我来处理。"
    assert [request.name for request in plan.capability_requests] == [
        "reminder_intent",
        "url_context",
        "timezone",
    ]
    assert plan.capability_requests[2].args == {
        "action": "direct_set",
        "timezone": "Asia/Tokyo",
    }


def test_parse_plain_text_as_response_only():
    from agent.agno_agent.runtime.plan_parser import parse_team_plan

    plan = parse_team_plan("你好，我在。")

    assert plan.response_text == "你好，我在。"
    assert plan.capability_requests == ()


def test_parser_rejects_unknown_capability():
    from agent.agno_agent.runtime.plan_parser import parse_team_plan

    plan = parse_team_plan("RESPONSE:\nok\nREQUEST shell {}")

    assert plan.response_text == "ok"
    assert plan.capability_requests == ()
    assert plan.rejected_requests == ("shell",)
```

- [ ] **Step 3: Verify RED**

Run:

```bash
pytest tests/unit/agent/test_manager_prompt.py tests/unit/agent/test_team_runtime_plan_parser.py -v
```

Expected: FAIL with missing modules.

- [ ] **Step 4: Implement manager prompt and parser**

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
            "You own semantic planning and final user-visible wording.",
            "Do not write durable state directly.",
            "Durable writes must be requested through deterministic capability requests.",
            "Return user-visible text in the RESPONSE block.",
            "Use one REQUEST line per deterministic capability you need.",
            "REQUEST reminder_intent {} when the user asks to create, update, cancel, complete, or list reminders.",
            "REQUEST url_context {} when the user message contains URLs or asks about linked content.",
            "REQUEST timezone {\"action\":\"direct_set\",\"timezone\":\"Asia/Tokyo\"} when the user explicitly asks to use a timezone.",
            "REQUEST timezone {\"action\":\"proposal\",\"timezone\":\"Asia/Tokyo\"} when a timezone change should be confirmed first.",
            "REQUEST timezone {\"action\":\"confirm\",\"decision\":\"yes\"} or REQUEST timezone {\"action\":\"confirm\",\"decision\":\"no\"} for short confirmation replies.",
            "REQUEST calendar_import {} when the user asks to import calendar data.",
            "Allowed capability names: reminder_intent, url_context, timezone, calendar_import.",
            "Never include hidden reasoning, JSON envelopes, tool logs, or database instructions.",
            f"Default user timezone: {run_context.user.timezone or 'UTC'}",
        ]
    )


def build_manager_input(run_context: AgentRunContext, input_message: str) -> str:
    return "\n".join(
        [
            f"conversation_id: {run_context.conversation.id}",
            f"platform: {run_context.platform}",
            f"route_key: {run_context.conversation.route_key or ''}",
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

Create `agent/agno_agent/runtime/plan_parser.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

ALLOWED_CAPABILITIES = {
    "reminder_intent",
    "url_context",
    "timezone",
    "calendar_import",
}


@dataclass(frozen=True)
class CapabilityRequest:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TeamPlan:
    response_text: str
    capability_requests: tuple[CapabilityRequest, ...]
    rejected_requests: tuple[str, ...] = ()


def parse_team_plan(content: str) -> TeamPlan:
    text = str(content or "").strip()
    if not text:
        return TeamPlan(response_text="", capability_requests=())

    response_lines: list[str] = []
    accepted: list[CapabilityRequest] = []
    rejected: list[str] = []
    in_response = False
    saw_structured_marker = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "RESPONSE:":
            saw_structured_marker = True
            in_response = True
            continue
        if line.startswith("REQUEST "):
            saw_structured_marker = True
            in_response = False
            remainder = line.removeprefix("REQUEST ").strip()
            name, _, raw_args = remainder.partition(" ")
            args: dict[str, Any] = {}
            if raw_args.strip():
                try:
                    parsed_args = json.loads(raw_args)
                    if isinstance(parsed_args, dict):
                        args = parsed_args
                    else:
                        rejected.append(name)
                        continue
                except json.JSONDecodeError:
                    rejected.append(name)
                    continue
            if name in ALLOWED_CAPABILITIES:
                accepted.append(CapabilityRequest(name=name, args=args))
            elif name:
                rejected.append(name)
            continue
        if in_response:
            response_lines.append(raw_line)

    if not saw_structured_marker:
        return TeamPlan(response_text=text, capability_requests=())

    return TeamPlan(
        response_text="\n".join(response_lines).strip(),
        capability_requests=tuple(accepted),
        rejected_requests=tuple(rejected),
    )
```

- [ ] **Step 5: Verify GREEN**

Run:

```bash
pytest tests/unit/agent/test_manager_prompt.py tests/unit/agent/test_team_runtime_plan_parser.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add agent/agno_agent/prompts agent/agno_agent/runtime/plan_parser.py tests/unit/agent/test_manager_prompt.py tests/unit/agent/test_team_runtime_plan_parser.py
git commit -m "feat(agent): define manager prompt command contract"
```

---

### Task 3: Deterministic Capability Ports

**Files:**
- Create: `agent/agno_agent/prompts/reminder_intent.py`
- Create: `agent/agno_agent/capabilities/reminder_intent.py`
- Create: `agent/agno_agent/capabilities/url_context_port.py`
- Create: `agent/agno_agent/capabilities/timezone_port.py`
- Create: `agent/agno_agent/capabilities/calendar_import_port.py`
- Modify: `agent/agno_agent/capabilities/__init__.py`
- Test: `tests/unit/agent/test_reminder_intent_capability.py`
- Test: `tests/unit/agent/test_team_runtime_parity.py`

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

- [ ] **Step 2: Write failing parity-port smoke tests**

Create `tests/unit/agent/test_team_runtime_parity.py`:

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
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv-1", platform="business", route_key=None),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
    )


def test_url_context_port_is_explicitly_not_a_durable_writer():
    from agent.agno_agent.capabilities.url_context_port import UrlContextPort

    port = UrlContextPort(url_reader=lambda text: {"urls": ["https://example.com"]})

    result = port.run("read https://example.com", _run_context())

    assert result.name == "url_context"
    assert result.ok is True
    assert result.metadata["durable_write"] is False


def test_timezone_port_returns_capability_result():
    from agent.agno_agent.capabilities.timezone_port import TimezonePort

    port = TimezonePort(handler=lambda text, context, args: {"ok": True, "timezone": "Asia/Tokyo", "state": {"timezone": "Asia/Tokyo"}})

    result = port.run("set timezone to Tokyo", _run_context(), {"action": "direct_set", "timezone": "Asia/Tokyo"})

    assert result.name == "timezone"
    assert result.ok is True
    assert result.content["timezone"] == "Asia/Tokyo"


def test_calendar_import_port_returns_capability_result():
    from agent.agno_agent.capabilities.calendar_import_port import CalendarImportPort

    port = CalendarImportPort(handler=lambda text, context, args: {"ok": True, "status": "queued"})

    result = port.run("import my calendar", _run_context(), {})

    assert result.name == "calendar_import"
    assert result.ok is True
    assert result.content["status"] == "queued"
```

- [ ] **Step 3: Verify RED**

Run:

```bash
pytest tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_team_runtime_parity.py -v
```

Expected: FAIL with missing modules.

- [ ] **Step 4: Implement ports**

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

Create `agent/agno_agent/capabilities/reminder_intent.py` using the existing command executor:

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
        entrypoint = getattr(
            visible_reminder_tool.entrypoint,
            "raw_function",
            visible_reminder_tool.entrypoint,
        )
        self.command_executor = command_executor or ReminderCommandExecutor(entrypoint)

    async def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        response = await self.detector_agent.arun(
            input=build_reminder_intent_input(input_message, run_context),
            session_state={
                "user": {"id": run_context.user.id, "timezone": run_context.user.timezone},
                "character": {"id": run_context.character.id},
                "conversation": {"id": run_context.conversation.id},
                "platform": run_context.platform,
            },
        )
        decision = _decision_from_response(response)
        intent_type = _decision_value(decision, "intent_type")
        action = _decision_value(decision, "action")
        if intent_type not in {"crud", "query"}:
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"action": "none", "intent_type": intent_type},
                metadata={"durable_write": False},
            )
        if intent_type == "query" and action != "list":
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"action": "none", "intent_type": intent_type},
                metadata={"durable_write": False},
            )
        result = self.command_executor.execute(decision, run_context)
        return CapabilityResult(
            name=result.name,
            ok=result.ok,
            content=dict(result.content),
            error=result.error,
            metadata={**dict(result.metadata), "durable_write": True},
        )
```

Create `agent/agno_agent/capabilities/url_context_port.py`:

```python
from __future__ import annotations

from typing import Any, Callable

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult


class UrlContextPort:
    def __init__(self, url_reader: Callable[[str], dict[str, Any]] | None = None) -> None:
        self.url_reader = url_reader

    def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        if self.url_reader is None:
            from agent.agno_agent.tools.url_reader import extract_urls_content, format_url_context

            def _default_reader(text: str) -> dict[str, Any]:
                url_contents = extract_urls_content(text)
                return {
                    "items": [item.to_dict() for item in url_contents],
                    "context": format_url_context(url_contents),
                }

            self.url_reader = _default_reader
        content = self.url_reader(input_message)
        return CapabilityResult(
            name="url_context",
            ok=True,
            content=content,
            metadata={"durable_write": False, "conversation_id": run_context.conversation.id},
        )
```

Create `agent/agno_agent/capabilities/timezone_port.py`:

```python
from __future__ import annotations

from typing import Any, Callable

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult


class TimezonePort:
    def __init__(self, handler: Callable[[str, AgentRunContext, dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.handler = handler

    def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        args = args or {}
        if self.handler is None:
            from agent.agno_agent.tools.timezone_tools import (
                consume_timezone_confirmation,
                set_user_timezone,
                store_timezone_proposal,
            )

            def _default_handler(text: str, context: AgentRunContext, request_args: dict[str, Any]) -> dict[str, Any]:
                session_state = {
                    "user": {"id": context.user.id, "timezone": context.user.timezone},
                    "conversation": {"_id": context.conversation.id},
                }
                action = str(request_args.get("action") or "").strip()
                if action == "direct_set":
                    return set_user_timezone.entrypoint(
                        timezone=str(request_args.get("timezone") or ""),
                        session_state=session_state,
                    )
                if action == "proposal":
                    return store_timezone_proposal.entrypoint(
                        timezone=str(request_args.get("timezone") or ""),
                        session_state=session_state,
                    )
                if action == "confirm":
                    return consume_timezone_confirmation.entrypoint(
                        decision=str(request_args.get("decision") or ""),
                        session_state=session_state,
                    )
                return {"ok": False, "message": f"unsupported timezone action: {action}"}

            self.handler = _default_handler
        content = self.handler(input_message, run_context, args)
        return CapabilityResult(
            name="timezone",
            ok=bool(content.get("ok", True)),
            content=content,
            metadata={"durable_write": bool(content.get("state"))},
        )
```

Create `agent/agno_agent/capabilities/calendar_import_port.py`:

```python
from __future__ import annotations

from typing import Any, Callable

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult


class CalendarImportPort:
    def __init__(self, handler: Callable[[str, AgentRunContext, dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.handler = handler

    def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        args = args or {}
        if self.handler is None:
            import os

            from agent.agno_agent.tools.calendar_import_handoff import (
                create_calendar_import_handoff_link,
            )

            def _fallback_web_url(path: str) -> str:
                for key in (
                    "DOMAIN_CLIENT",
                    "NEXT_PUBLIC_COKE_API_URL",
                    "NEXT_PUBLIC_API_URL",
                    "COKE_WEB_ALLOWED_ORIGIN",
                ):
                    base_url = os.environ.get(key, "").strip().rstrip("/")
                    if base_url:
                        return f"{base_url}{path}"
                return path

            def _default_handler(text: str, context: AgentRunContext, request_args: dict[str, Any]) -> dict[str, Any]:
                payload = request_args.get("handoff_payload")
                if isinstance(payload, dict) and payload:
                    try:
                        link = create_calendar_import_handoff_link(payload)
                    except Exception as exc:
                        return {"ok": False, "message": str(exc) or exc.__class__.__name__}
                else:
                    link = _fallback_web_url("/account/calendar-import")
                return {
                    "ok": True,
                    "link": link,
                    "message": (
                        "用户想导入 Google Calendar。请把这个入口链接发给用户："
                        f"{link}。说明打开后登录或验证邮箱，然后点击 Start Google Calendar import 授权 Google。"
                        "不要说导入已经完成。"
                    ),
                }

            self.handler = _default_handler
        content = self.handler(input_message, run_context, args)
        return CapabilityResult(
            name="calendar_import",
            ok=bool(content.get("ok", True)),
            content=content,
            metadata={"durable_write": False},
        )
```

Modify `agent/agno_agent/capabilities/__init__.py`:

```python
from agent.agno_agent.capabilities.calendar_import_port import CalendarImportPort
from agent.agno_agent.capabilities.context_port import ContextPort
from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort
from agent.agno_agent.capabilities.timezone_port import TimezonePort
from agent.agno_agent.capabilities.url_context_port import UrlContextPort

__all__ = [
    "CalendarImportPort",
    "ContextPort",
    "ReminderIntentPort",
    "TimezonePort",
    "UrlContextPort",
]
```

- [ ] **Step 5: Verify GREEN or stop on missing legacy helper imports**

Run:

```bash
pytest tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_team_runtime_parity.py tests/unit/agent/test_reminder_command_executor.py -v
```

Expected: PASS. The default imports must resolve to existing helpers: `extract_urls_content`, `format_url_context`, `set_user_timezone`, `store_timezone_proposal`, `consume_timezone_confirmation`, and `create_calendar_import_handoff_link`.

- [ ] **Step 6: Commit**

Run:

```bash
git add agent/agno_agent/prompts/reminder_intent.py agent/agno_agent/capabilities tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_team_runtime_parity.py
git commit -m "feat(agent): add deterministic team capability ports"
```

---

### Task 4: Real Team Runtime Execution

**Files:**
- Modify: `agent/agno_agent/runtime/team_runtime.py`
- Test: `tests/unit/agent/test_team_runtime_execution.py`

- [ ] **Step 1: Write failing Team runtime execution tests**

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
        yield types.SimpleNamespace(event="TeamRunContent", content="RESPONSE:\n我来处理。\nREQUEST reminder_intent {}")


def _install_fake_team(monkeypatch, team_cls=FakeTeam):
    team_mod = types.ModuleType("agno.team")
    team_mod.Team = team_cls
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
async def test_run_team_runtime_invokes_team_and_executes_requested_capability(monkeypatch):
    _install_fake_team(monkeypatch)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            assert input_message == "18:00 remind me to drink water"
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：drink water"},
                metadata={"durable_write": True},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="18:00 remind me to drink water",
        message_source="user",
        metadata={"request_id": "req-1"},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FakeReminderPort()},
    )

    assert result.visible_messages[0].content == "我来处理。"
    assert result.tool_results[0].name == "reminder"
    assert result.output_disposition.status == "ok"
    assert result.post_analyze_input == {
        "input_message": "18:00 remind me to drink water",
        "message_source": "user",
    }
    assert result.trace["runtime"] == "team"
    assert result.trace["capability_requests"] == ("reminder_intent",)
    assert FakeTeam.last_instance.kwargs["name"] == "CokeManagerTeam"
    assert "conversation_id: conv-1" in FakeTeam.last_instance.input


@pytest.mark.asyncio
async def test_run_team_runtime_builds_default_capability_ports(monkeypatch):
    _install_fake_team(monkeypatch)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "default reminder port used"},
            )

    monkeypatch.setattr(team_runtime, "ReminderIntentPort", FakeReminderPort)

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="18:00 remind me to drink water",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
    )

    assert result.tool_results[0].content["summary"] == "default reminder port used"


@pytest.mark.asyncio
async def test_run_team_runtime_empty_output_returns_empty_disposition(monkeypatch):
    class EmptyTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            yield types.SimpleNamespace(event="TeamRunCompleted", content=None)

    _install_fake_team(monkeypatch, EmptyTeam)
    from agent.agno_agent.runtime import team_runtime

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

- [ ] **Step 3: Implement Team runtime with parsed requests**

Replace `agent/agno_agent/runtime/team_runtime.py` with an implementation that preserves the existing `create_manager_team(model=object(), members=[])` call compatibility and adds `instructions` plus capability execution. The implementation must:

- call `create_llm_model(role="chat", max_tokens=8000)`;
- pass `members=[]` until real Agno member objects are added in a later plan;
- collect visible Team events through `filter_user_visible_team_events()`;
- parse the collected text with `parse_team_plan()`;
- when `capability_ports is None`, build a default map with `ReminderIntentPort`, `UrlContextPort`, `TimezonePort`, and `CalendarImportPort`;
- execute only capability names from `TeamPlan.capability_requests`;
- pass each request's JSON `args` into `port.run(input_message_str, run_context, request.args)`;
- set `post_analyze_input={"input_message": input_message_str, "message_source": message_source}` on successful user-visible output;
- return `RuntimeErrorDisposition(code="team_runtime_empty_output", retryable=True)` on empty response and no tool result.

Use this signature:

```python
async def run_team_runtime(
    *,
    context: dict[str, Any],
    input_message_str: str,
    message_source: str,
    metadata: dict[str, Any] | None,
    current_time: datetime | None = None,
    capability_ports: dict[str, Any] | None = None,
) -> AgentRunResult:
```

- [ ] **Step 4: Verify Team runtime and construction invariants**

Run:

```bash
pytest tests/unit/agent/test_team_runtime_execution.py \
  tests/unit/agent/test_team_runtime_construction.py \
  tests/unit/agent/test_team_streaming_filter.py \
  tests/unit/agent/test_team_runtime_plan_parser.py \
  tests/unit/agent/test_reminder_intent_capability.py \
  tests/unit/agent/test_team_runtime_parity.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/agno_agent/runtime/team_runtime.py tests/unit/agent/test_team_runtime_execution.py
git commit -m "feat(agent): execute parsed team capability requests"
```

---

### Task 5: Typed User-Turn Runtime Adapter

**Files:**
- Create: `agent/agno_agent/runtime/event_adapter.py`
- Modify: `agent/agno_agent/runtime/__init__.py`
- Modify: `agent/runner/agent_handler.py`
- Test: `tests/unit/agent/test_agent_handler.py`

- [ ] **Step 1: Add handler test for typed user turn**

Append to `tests/unit/agent/test_agent_handler.py`:

```python
@pytest.mark.asyncio
async def test_handle_message_team_runtime_passes_typed_user_turn(monkeypatch, sample_context):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition, VisibleMessage
    from agent.runner import agent_handler

    captured = {}

    async def fake_run_agent_runtime_event(**kwargs):
        captured.update(kwargs)
        return AgentRunResult(
            visible_messages=[VisibleMessage(message_type="text", content="team reply")],
            post_analyze_input=None,
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

    await agent_handler.handle_message(
        context=sample_context,
        input_message_str="hello",
        message_source="user",
        metadata={"request_id": "req-1"},
        check_new_message=False,
        worker_tag="[T]",
        current_message_ids=["msg-1"],
    )

    agent_input = captured["agent_input"]
    assert agent_input.input_type == "user.turn"
    assert agent_input.text == "hello"
    assert agent_input.payload.current_message_ids == ("msg-1",)
    assert captured["context"] is sample_context
```

Append this post-analyze scheduling test to the same file:

```python
@pytest.mark.asyncio
async def test_handle_message_team_runtime_schedules_post_analyze(monkeypatch, sample_context):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition, VisibleMessage
    from agent.runner import agent_handler

    scheduled = []

    async def fake_run_agent_runtime_event(**kwargs):
        return AgentRunResult(
            visible_messages=[VisibleMessage(message_type="text", content="team reply")],
            post_analyze_input={"input_message": "hello", "message_source": "user"},
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
        input_message_str="hello",
        message_source="user",
        metadata={},
        check_new_message=False,
        worker_tag="[T]",
    )

    assert scheduled
    scheduled[0].close()
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_passes_typed_user_turn -v
```

Expected: FAIL because `_run_agent_runtime_event` does not exist.

- [ ] **Step 3: Implement event adapter**

Create `agent/agno_agent/runtime/event_adapter.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.agno_agent.runtime.context import build_agent_run_context
from agent.agno_agent.runtime.inputs import AgentInput
from agent.agno_agent.runtime.result import AgentRunResult
from agent.agno_agent.runtime.team_runtime import run_team_runtime


async def run_agent_runtime_event(
    *,
    agent_input: AgentInput,
    context: dict[str, Any],
    message_source: str,
    metadata: dict[str, Any] | None = None,
    current_time: datetime | None = None,
) -> AgentRunResult:
    occurred_at = current_time or agent_input.occurred_at or datetime.now(UTC)
    build_agent_run_context(
        context,
        current_time=occurred_at,
        runtime_metadata={"message_source": message_source, **(metadata or {})},
    )
    return await run_team_runtime(
        context=context,
        input_message_str=agent_input.text or "",
        message_source=message_source,
        metadata=metadata or {},
        current_time=occurred_at,
    )


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

Modify `agent/agno_agent/runtime/__init__.py` to export `run_agent_runtime_event` and `run_deferred_action_runtime_event`.

- [ ] **Step 4: Modify handler Team branch**

In `agent/runner/agent_handler.py`, add `_run_agent_runtime_event()` that imports and calls `run_agent_runtime_event()`. In the Team branch, build:

```python
from datetime import UTC, datetime
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload

agent_input = AgentInput(
    input_type="user.turn",
    conversation_id=str(context.get("conversation", {}).get("_id") or context.get("conversation", {}).get("id") or conversation_id or ""),
    text=input_message_str,
    payload=UserTurnPayload(
        current_message_ids=tuple(current_message_ids or ()),
        check_new_message=check_new_message,
        metadata=metadata or {},
    ),
    occurred_at=datetime.now(UTC),
    metadata={"message_source": message_source, "worker_tag": worker_tag},
)
```

Then call `_run_agent_runtime_event(agent_input=agent_input, context=context, message_source=message_source, metadata=metadata)`.

After Team visible messages and fallback handling, if `result.post_analyze_input` is not `None`, schedule the existing background post-analyze path:

```python
if result.post_analyze_input is not None:
    post_context = copy.deepcopy(context)
    asyncio.create_task(
        _run_post_analyze_background(
            post_context,
            str(post_context.get("conversation", {}).get("_id") or conversation_id or ""),
            worker_tag,
        )
    )
```

- [ ] **Step 5: Verify handler Team branch**

Run:

```bash
pytest tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_uses_agent_runtime \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_empty_skeleton_uses_chat_fallback \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_passes_typed_user_turn \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_schedules_post_analyze -v
```

Expected: PASS. Rename the empty-skeleton test to `test_handle_message_team_runtime_empty_output_uses_chat_fallback` in the same patch if its assertion now checks `team_runtime_empty_output`.

- [ ] **Step 6: Commit**

Run:

```bash
git add agent/agno_agent/runtime/__init__.py agent/agno_agent/runtime/event_adapter.py agent/runner/agent_handler.py tests/unit/agent/test_agent_handler.py
git commit -m "feat(agent): route team user turns through typed runtime input"
```

---

### Task 6: Typed Reminder Fire Route

**Files:**
- Modify: `agent/runner/reminder_event_handler.py`
- Modify: `agent/runner/agent_runner.py`
- Test: `tests/unit/runner/test_typed_runtime_events.py`

- [ ] **Step 1: Write typed reminder fire test**

Create `tests/unit/runner/test_typed_runtime_events.py`:

```python
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition, VisibleMessage
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

    captured = {}

    async def runtime_event_handler(**kwargs):
        captured.update(kwargs)
        return AgentRunResult(
            visible_messages=[VisibleMessage(message_type="text", content="提醒：drink water")],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

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
        context_builder=Mock(return_value={"conversation": {"_id": "conv-1"}}),
        output_writer=Mock(return_value={"_id": "out-1"}),
        existing_output_lookup=Mock(return_value=None),
        runtime_event_handler=runtime_event_handler,
    )

    result = await handler.handle(_event())

    assert result.ok is True
    assert result.output_reference == "out-1"
    typed_input = captured["agent_input"]
    assert typed_input.input_type == "reminder.fired"
    assert typed_input.text == "提醒：drink water"
    assert typed_input.payload.fire_id.startswith("rem-1:")
    assert typed_input.payload.title == "drink water"
    assert typed_input.metadata["owner_user_id"] == "user-1"
    assert captured["message_source"] == "reminder"
    assert captured["context"]["conversation"]["_id"] == "conv-1"
    assert captured["context"]["message_source"] == "deferred_action"
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/runner/test_typed_runtime_events.py::test_reminder_event_handler_can_route_through_typed_runtime -v
```

Expected: FAIL because `ReminderFireEventHandler` has no `runtime_event_handler`.

- [ ] **Step 3: Implement optional typed route**

Modify `ReminderFireEventHandler.__init__()` to accept and store `runtime_event_handler: Callable[..., Any] | None = None`.

In `handle()`, after lock acquisition and second replay check, build `context = self.context_builder(owner, character, conversation)` as today. Before any typed runtime call or direct output write, preserve the existing proactive delivery marker:

```python
if isinstance(context, dict):
    context.setdefault("message_source", "deferred_action")
```

If `self.runtime_event_handler` is not `None`, build `AgentInput(input_type="reminder.fired", ...)` and call:

```python
runtime_result = self.runtime_event_handler(
    agent_input=agent_input,
    context=context,
    message_source="reminder",
    metadata={
        "event_type": event.event_type,
        "event_id": event.event_id,
        "fire_id": event.fire_id,
        "reminder_id": event.reminder_id,
        "scheduled_for": event.scheduled_for.isoformat(),
        "fire_at": event.fire_at.isoformat(),
    },
)
```

If the result is awaitable, await it. For each `VisibleMessage` in the returned `AgentRunResult`, call `self.output_writer(context, visible_message.content, message_type=visible_message.message_type, metadata={...event metadata...})`. The same `context` passed to `output_writer` must still have `message_source == "deferred_action"` so `send_message_via_context()` uses the proactive output path. Return a successful `ReminderFireResult` using the first output reference. If no visible message is returned, return `_failure(event, "OutputUnavailable", "runtime produced no reminder output")`. Preserve `_failed_output_result()`, `_output_reference()`, replay checks, and `finally` lock release behavior exactly.

In `agent/runner/agent_runner.py`, wire production reminder runtime:

```python
from agent.agno_agent.runtime import run_agent_runtime_event

handler = ReminderFireEventHandler(runtime_event_handler=run_agent_runtime_event)
```

- [ ] **Step 4: Verify reminder handler behavior**

Run:

```bash
pytest tests/unit/runner/test_typed_runtime_events.py tests/unit/runner/test_reminder_event_handler.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/runner/reminder_event_handler.py agent/runner/agent_runner.py tests/unit/runner/test_typed_runtime_events.py
git commit -m "feat(agent): route reminder fires through typed runtime input"
```

---

### Task 7: Typed Deferred Action Route

**Files:**
- Modify: `agent/runner/deferred_action_executor.py`
- Modify: `agent/runner/agent_runner.py`
- Test: `tests/unit/runner/test_deferred_action_executor.py`

- [ ] **Step 1: Add deferred action runtime result test**

Append to `tests/unit/runner/test_deferred_action_executor.py`:

```python
@pytest.mark.asyncio
async def test_executor_consumes_deferred_action_fire_result_success():
    from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition, VisibleMessage
    from agent.runner.deferred_action_executor import DeferredActionExecutor

    action_dao = FakeDeferredActionDAO()
    occurrence_dao = FakeOccurrenceDAO()
    scheduler = Mock(remove_action=Mock(), reschedule_action=Mock())
    lock_manager = FakeLockManager()
    action = build_action(kind="follow_up")
    action_dao.documents[action["_id"]] = action

    async def runtime_fire_handler(**kwargs):
        agent_input = kwargs["agent_input"]
        assert agent_input.input_type == "deferred_action.fire"
        assert agent_input.payload.action_id == str(action["_id"])
        return AgentRunResult(
            visible_messages=[VisibleMessage(message_type="text", content="follow up")],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    output_writer = Mock(return_value={"_id": "out-1"})

    executor = DeferredActionExecutor(
        action_dao=action_dao,
        occurrence_dao=occurrence_dao,
        scheduler=scheduler,
        lock_manager=lock_manager,
        runtime_fire_handler=runtime_fire_handler,
        output_writer=output_writer,
    )

    result = await executor.execute_due_action(
        action_id=str(action["_id"]),
        scheduled_for=action["next_run_at"],
        revision=action["revision"],
    )

    assert result == "succeeded"
    output_writer.assert_called_once()
    assert output_writer.call_args.kwargs["message"] == "follow up"
    output_context = output_writer.call_args.args[0]
    assert output_context["message_source"] == "deferred_action"
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/runner/test_deferred_action_executor.py::test_executor_consumes_deferred_action_fire_result_success -v
```

Expected: FAIL because `DeferredActionExecutor` has no `runtime_fire_handler`.

- [ ] **Step 3: Implement runtime fire handler**

Modify `DeferredActionExecutor.__init__()` to accept and store:

```python
runtime_fire_handler: Callable[..., Any] | None = None
output_writer: Callable[..., Any] | None = None
```

Default `output_writer` to `agent.util.message_util.send_message_via_context`.

Inside `execute_due_action()`, after occurrence claim and before legacy `handle_message_fn`, if `self.runtime_fire_handler` is not `None`, build `context = self._build_context(action)`, `input_message = self._build_input_message(action)`, and `metadata` exactly as the legacy branch does. Before the typed runtime call or direct output write, set `context["message_source"] = "deferred_action"` so `send_message_via_context()` uses the proactive output path. Build `AgentInput(input_type="deferred_action.fire", payload=DeferredActionPayload(...))`, call:

```python
runtime_result = self.runtime_fire_handler(
    agent_input=agent_input,
    context=context,
    message_source="deferred_action",
    metadata=metadata,
)
```

Await it if needed. If the handler returns `AgentRunResult`, write each `VisibleMessage` through `self.output_writer(context, message=visible_message.content, message_type=visible_message.message_type, metadata={"deferred_action_id": action_id, "scheduled_for": scheduled_for.isoformat()})`, collect returned output references, and copy those references into `runtime_result.output_disposition` before mapping. If the runtime result has status `ok` but has no visible messages and no output references, treat it as `DeferredActionFireResult(status="no_output", retryable=True)`. Convert the updated `AgentRunResult` through `map_agent_result_to_deferred_status()` from `agent.agno_agent.adapters`; if the handler already returns `DeferredActionFireResult`, use it directly. Then apply the `DeferredActionFireResult`:

- `succeeded`: only after at least one output reference exists; mark occurrence succeeded, call `_handle_success()`, return `"succeeded"`.
- `failed`: mark occurrence failed with `error_message or error_code or "runtime fire failed"`, call `_handle_failure()`, return `"failed"`.
- `rollback`: release lease, return `"rollback"`.
- `no_output`: mark occurrence failed with `"runtime produced no output"`, call `_handle_failure()`, return `"no_output"`.
- `skipped`: release lease, return `"skipped"`.

In `agent/runner/agent_runner.py`, wire production deferred-action runtime:

```python
from agent.agno_agent.runtime import run_agent_runtime_event

executor = DeferredActionExecutor(
    action_dao=action_dao,
    occurrence_dao=occurrence_dao,
    scheduler=None,
    runtime_fire_handler=run_agent_runtime_event,
)
```

- [ ] **Step 4: Verify deferred-action suites**

Run:

```bash
pytest tests/unit/runner/test_deferred_action_executor.py tests/e2e/test_deferred_actions_flow.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/runner/deferred_action_executor.py agent/runner/agent_runner.py tests/unit/runner/test_deferred_action_executor.py
git commit -m "feat(agent): consume typed deferred action fire results"
```

---

### Task 8: Output Reference Adapter

**Files:**
- Create: `agent/agno_agent/adapters/output_disposition.py`
- Modify: `agent/agno_agent/adapters/__init__.py`
- Test: `tests/unit/agent/test_output_disposition_adapter.py`

- [ ] **Step 1: Write adapter test**

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

Expected: FAIL with missing module.

- [ ] **Step 3: Implement adapter and exports**

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

Modify `agent/agno_agent/adapters/__init__.py` to export `with_output_references`, `DeferredActionFireResult`, `map_agent_result_to_deferred_status`, and `ReminderCommandExecutor`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
pytest tests/unit/agent/test_output_disposition_adapter.py tests/unit/agent/test_agent_runtime_types.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/agno_agent/adapters tests/unit/agent/test_output_disposition_adapter.py
git commit -m "feat(agent): add runtime output disposition adapter"
```

---

### Task 9: Behavior-Level Team Parity Gate

**Files:**
- Modify: `docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md`

- [ ] **Step 1: Collect exact parity test node IDs**

Run:

```bash
pytest --collect-only -q \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_uses_agent_runtime \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_rolls_back_before_runtime_on_new_message \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_empty_output_uses_chat_fallback \
  tests/unit/agent/test_team_runtime_execution.py::test_run_team_runtime_invokes_team_and_executes_requested_capability \
  tests/unit/runner/test_typed_runtime_events.py::test_reminder_event_handler_can_route_through_typed_runtime \
  tests/unit/runner/test_deferred_action_executor.py::test_executor_consumes_deferred_action_fire_result_success \
  tests/unit/agent/test_team_runtime_parity.py::test_timezone_port_returns_capability_result \
  tests/unit/agent/test_team_runtime_parity.py::test_url_context_port_is_explicitly_not_a_durable_writer \
  tests/unit/agent/test_team_runtime_parity.py::test_calendar_import_port_returns_capability_result \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_schedules_post_analyze
```

Expected: all ten node IDs are collected. If any node is missing, stop and add the missing behavior test before cutover.

- [ ] **Step 2: Run exact Team parity suite**

Run:

```bash
AGENT_RUNTIME_VERSION=team pytest -v \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_uses_agent_runtime \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_rolls_back_before_runtime_on_new_message \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_empty_output_uses_chat_fallback \
  tests/unit/agent/test_team_runtime_execution.py::test_run_team_runtime_invokes_team_and_executes_requested_capability \
  tests/unit/runner/test_typed_runtime_events.py::test_reminder_event_handler_can_route_through_typed_runtime \
  tests/unit/runner/test_deferred_action_executor.py::test_executor_consumes_deferred_action_fire_result_success \
  tests/unit/agent/test_team_runtime_parity.py::test_timezone_port_returns_capability_result \
  tests/unit/agent/test_team_runtime_parity.py::test_url_context_port_is_explicitly_not_a_durable_writer \
  tests/unit/agent/test_team_runtime_parity.py::test_calendar_import_port_returns_capability_result \
  tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_schedules_post_analyze
```

Expected: PASS.

- [ ] **Step 3: Run legacy-adjacent suites as regression comparison**

Run:

```bash
pytest tests/unit/test_prepare_workflow_timezone.py \
  tests/unit/test_prepare_workflow_web_search.py \
  tests/unit/agent/test_chat_workflow_calendar_import.py \
  tests/unit/test_url_reader.py -v
```

Expected: PASS. These are not sufficient for cutover by themselves; they only prove the old path still works.

- [ ] **Step 4: Record parity evidence**

Run:

```bash
{
  printf '\n## Team Parity Evidence\n\n'
  printf -- '- Team behavior parity suite: PASS on %s.\n' "$(date -I)"
  printf -- '- Legacy-adjacent regression suite: PASS on %s.\n' "$(date -I)"
} >> docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
```

- [ ] **Step 5: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
git commit -m "test(agent): record behavior-backed team parity"
```

---

### Task 10: Normal-Path Reminder Eval Gate

**Files:**
- Modify: `docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md`

- [ ] **Step 1: Run single-case reminder smoke before broad eval**

Run one known reminder-create case with Team runtime using the repo's current eval selector:

```bash
AGENT_RUNTIME_VERSION=team python scripts/eval_reminder_normal_path_cases.py \
  --offset 0 \
  --limit 1 \
  --case-timeout-seconds 180 \
  --output artifacts/evidence/reminder-normal/team-smoke.json
```

Expected: command exits 0. Then verify the JSON summary:

```bash
python - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("artifacts/evidence/reminder-normal/team-smoke.json").read_text())
assert payload["summary"]["failed"] == 0, payload["summary"]
assert payload["summary"]["passed"] == payload["summary"]["total"] == 1, payload["summary"]
PY
```

If either command fails, stop before cutover and record the exact command, exit status, and top-level failure category.

- [ ] **Step 2: Run full normal-path reminder eval**

Run:

```bash
AGENT_RUNTIME_VERSION=team python scripts/eval_reminder_normal_path_cases.py \
  --run-all \
  --batch-size 1 \
  --case-timeout-seconds 180 \
  --output artifacts/evidence/reminder-normal/team-run-all.json
```

Expected: command exits 0. Then verify the JSON summary:

```bash
python - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("artifacts/evidence/reminder-normal/team-run-all.json").read_text())
assert payload["summary"]["failed"] == 0, payload["summary"]
assert payload["summary"]["passed"] == payload["summary"]["total"], payload["summary"]
PY
```

- [ ] **Step 3: Record eval evidence**

Run:

```bash
{
  printf '\n## Reminder Eval Evidence\n\n'
  printf -- '- Team one-case reminder smoke: PASS on %s with evidence file `artifacts/evidence/reminder-normal/team-smoke.json`.\n' "$(date -I)"
  printf -- '- Team normal-path reminder eval: PASS on %s with evidence file `artifacts/evidence/reminder-normal/team-run-all.json`.\n' "$(date -I)"
} >> docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
```

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md artifacts/evidence/reminder-normal/team-smoke.json artifacts/evidence/reminder-normal/team-run-all.json
git commit -m "test(agent): record team reminder eval gate"
```

---

### Task 11: Default Runtime Cutover

**Files:**
- Modify: `agent/agno_agent/runtime/selector.py`
- Modify: `tests/unit/agent/test_agent_runtime_selector.py`
- Modify: `docs/architecture.md`

- [ ] **Step 1: Change selector test to expect Team default**

Modify `tests/unit/agent/test_agent_runtime_selector.py`:

```python
def test_agent_runtime_defaults_to_team(monkeypatch):
    monkeypatch.delenv("AGENT_RUNTIME_VERSION", raising=False)

    from agent.agno_agent.runtime.selector import select_runtime

    assert select_runtime() == "team"
```

Keep tests proving explicit `AGENT_RUNTIME_VERSION=legacy`, conversation override, and customer override still select `legacy` during the transition.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/agent/test_agent_runtime_selector.py::test_agent_runtime_defaults_to_team -v
```

Expected: FAIL because selector still defaults to `legacy`.

- [ ] **Step 3: Change default selector**

Modify the final fallback in `agent/agno_agent/runtime/selector.py`:

```python
return "team"
```

- [ ] **Step 4: Update architecture docs**

In `docs/architecture.md`, update Worker Runtime to say:

```markdown
The default turn pipeline is Agent Runtime Team. The runner remains responsible for locks, rollback, output writes, replay checks, scheduler boot, and delivery state transitions. The legacy workflow path is still selectable only through explicit `AGENT_RUNTIME_VERSION=legacy`, conversation override, or customer override until the legacy deletion task lands.
```

- [ ] **Step 5: Verify cutover**

Run:

```bash
pytest tests/unit/agent/test_agent_runtime_selector.py tests/unit/agent/test_agent_handler.py tests/unit/agent/test_team_runtime_parity.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add agent/agno_agent/runtime/selector.py tests/unit/agent/test_agent_runtime_selector.py docs/architecture.md
git commit -m "feat(agent): default to team runtime"
```

---

### Task 12: Post-Cutover Verification

**Files:**
- Modify: `docs/fitness/coke-verification-matrix.md`
- Modify: `docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md`

- [ ] **Step 1: Run focused runtime verification**

Run:

```bash
pytest tests/unit/agent/ -v
pytest tests/unit/runner/ -v
pytest tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py -v
pytest tests/e2e/test_reminder_system_flow.py -v
pytest tests/e2e/test_deferred_actions_flow.py -v
```

Expected: PASS.

- [ ] **Step 2: Run repo check**

Run:

```bash
zsh scripts/check
```

Expected: `check passed`.

- [ ] **Step 3: Update verification matrix**

In `docs/fitness/coke-verification-matrix.md`, update worker-runtime verification to include:

```bash
AGENT_RUNTIME_VERSION=team pytest tests/unit/agent/ tests/unit/runner/ -v
AGENT_RUNTIME_VERSION=team python scripts/eval_reminder_normal_path_cases.py
```

- [ ] **Step 4: Record final pre-deletion evidence**

Run:

```bash
{
  printf '\n## Post-Cutover Evidence\n\n'
  printf -- '- Unit/runtime suites: PASS on %s.\n' "$(date -I)"
  printf -- '- Reminder and deferred-action E2E suites: PASS on %s.\n' "$(date -I)"
  printf -- '- Repo check: PASS on %s.\n' "$(date -I)"
} >> docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
```

- [ ] **Step 5: Commit**

Run:

```bash
git add docs/fitness/coke-verification-matrix.md docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
git commit -m "test(agent): verify team runtime cutover"
```

---

### Task 13: Legacy Workflow Deletion

**Files:**
- Delete: `agent/agno_agent/workflows/prepare_workflow.py`
- Delete: `agent/agno_agent/workflows/chat_workflow_streaming.py`
- Modify: `agent/agno_agent/workflows/__init__.py`
- Modify: `agent/agno_agent/runtime/selector.py`
- Modify: `tests/unit/agent/test_agent_runtime_selector.py`
- Modify: `docs/architecture.md`
- Modify: `agent/runner/agent_handler.py`
- Modify: tests that imported deleted workflows

- [ ] **Step 1: Confirm deletion gate**

Run:

```bash
rg -n "## Team Parity Evidence|## Reminder Eval Evidence|## Post-Cutover Evidence" \
  docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
test -f artifacts/evidence/reminder-normal/team-smoke.json
test -f artifacts/evidence/reminder-normal/team-run-all.json
python - <<'PY'
import json
from pathlib import Path
for path in [
    Path("artifacts/evidence/reminder-normal/team-smoke.json"),
    Path("artifacts/evidence/reminder-normal/team-run-all.json"),
]:
    payload = json.loads(path.read_text())
    assert payload["summary"]["failed"] == 0, (path, payload["summary"])
    assert payload["summary"]["passed"] == payload["summary"]["total"], (path, payload["summary"])
PY
pytest tests/unit/agent/test_agent_runtime_selector.py tests/unit/agent/test_agent_handler.py tests/unit/agent/test_team_runtime_parity.py -v
```

Expected: all commands pass. If any command fails, stop and do not delete legacy workflows.

- [ ] **Step 2: Remove legacy imports and branch from handler**

In `agent/runner/agent_handler.py`, remove imports and global instances for `PrepareWorkflow` and `StreamingChatWorkflow`. Keep `PostAnalyzeWorkflow` and `post_analyze_workflow = PostAnalyzeWorkflow()` because Team runtime still uses the existing background post-analyze path. Remove the legacy prepare/chat branch after the Team branch and make the Team path unconditional inside `handle_message()`.

Also remove any runtime selection check from `handle_message()` because `legacy` is no longer a runnable prepare/chat branch after this task.

- [ ] **Step 3: Retire legacy selector values**

Modify `agent/agno_agent/runtime/selector.py` so `RuntimeVersion = Literal["team"]`, `_VALID_RUNTIME_VERSIONS = {"team"}`, and `select_runtime()` always falls back to `"team"`. Remove tests that expect explicit `legacy` to be accepted, and add:

```python
def test_agent_runtime_rejects_legacy_after_deletion(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "legacy")

    from agent.agno_agent.runtime.selector import select_runtime

    assert select_runtime() == "team"
```

Update `docs/architecture.md` to remove the sentence that says explicit `AGENT_RUNTIME_VERSION=legacy` remains selectable.

- [ ] **Step 4: Retire workflow exports and files**

Replace `agent/agno_agent/workflows/__init__.py` with:

```python
"""Legacy workflow package retired after Agent Runtime Team cutover."""

__all__: list[str] = []
```

Run:

```bash
git rm agent/agno_agent/workflows/prepare_workflow.py agent/agno_agent/workflows/chat_workflow_streaming.py
```

- [ ] **Step 5: Import scan**

Run:

```bash
rg -n "PrepareWorkflow|StreamingChatWorkflow|orchestrator_agent|OrchestratorResponse|INSTRUCTIONS_ORCHESTRATOR|get_orchestrator_instructions" \
  agent/runner agent/agno_agent/workflows tests
```

Expected: no live runtime imports for retired prepare/chat/orchestrator names in runner, workflow exports, or tests. `PostAnalyzeWorkflow` imports are allowed because post-analyze remains active after this deletion task.

- [ ] **Step 6: Verify deletion**

Run:

```bash
pytest tests/unit/agent/ tests/unit/runner/ tests/e2e/test_reminder_system_flow.py tests/e2e/test_deferred_actions_flow.py -v
zsh scripts/check
```

Expected: PASS and `check passed`.

- [ ] **Step 7: Commit**

Run:

```bash
git add agent/runner/agent_handler.py agent/agno_agent/runtime/selector.py agent/agno_agent/workflows tests/unit/agent tests/unit/runner docs/architecture.md docs/superpowers/plans/2026-05-06-coke-agent-runtime-leader-completion.md
git commit -m "refactor(agent): delete legacy workflow runtime"
```

---

## Self-Review

Spec coverage:

- Real manager prompt and command contract: Task 2.
- Real Team runtime that parses leader requests and executes deterministic capabilities: Task 4.
- Reminder-intent wrapping current reminder detector and command executor: Task 3.
- Typed user turn, reminder fire, and deferred action routes: Tasks 5, 6, 7.
- Output reference propagation for deferred-action status: Task 8.
- Behavior-backed parity gate: Task 9.
- Reminder eval gate before default switch: Task 10.
- Default runtime cutover: Task 11.
- Final verification and matrix update: Task 12.
- Legacy workflow deletion only after cutover evidence: Task 13.

Placeholder scan:

- No `TBD`, `TODO`, `implement later`, or unspecified test-writing steps are present.
- Capability default imports in Task 3 are explicit but may need adjustment if the real helper names differ; the task explicitly stops on missing imports and requires replacing them with the helper identified from existing legacy tests before continuing.

Type consistency:

- `AgentInput`, `UserTurnPayload`, `ReminderFirePayload`, `DeferredActionPayload`, `AgentRunResult`, `OutputDisposition`, `RuntimeErrorDisposition`, `VisibleMessage`, and `CapabilityResult` match the existing runtime dataclasses.
- `run_team_runtime()` and `run_agent_runtime_event()` keep keyword-only signatures.
- `DeferredActionFireResult.status` values match the existing adapter: `succeeded`, `failed`, `skipped`, `rollback`, and `no_output`.

Review history:

- Reviewer pass 1 found blocking issues in fake parity checks, typed event adapter signatures, deferred production wiring, helper imports, eval commands, and deletion gates; this plan was revised to address them.
- Reviewer pass 2 found blocking issues in deferred output delivery, reminder production wiring staging, and default capability port construction; this plan was revised to address them.
- Reviewer final confirmation found blocking issues in proactive delivery markers for reminder/deferred typed output and a weaker deletion eval recheck; this plan was revised to address them.
