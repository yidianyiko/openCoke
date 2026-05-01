# Coke Agent Runtime Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Coke's implicit `PrepareWorkflow -> StreamingChatWorkflow` agent pipeline with a typed Agent Runtime boundary, Agno manager core, deterministic capability ports, and explicit runtime-event contracts.

**Architecture:** Keep `agent/runner/` as the deterministic reliability shell for locks, queueing, rollback, output writes, and PostAnalyze scheduling. Put Agno Team behind `agent/agno_agent/runtime/` as the semantic manager core, and keep durable side effects in post-Team Python adapters such as `ReminderCommandExecutor`.

**Tech Stack:** Python 3.12, pytest, Agno 2.5.9, Mongo-backed DAO layer, existing runner/reminder/deferred-action services, current PM2/local runtime for smoke tests.

---

## Scope And Execution Notes

This is a large destructive runtime redesign. Implement it in a clean git
worktree because the main checkout currently has unrelated reminder-eval work.

Start command:

```bash
git worktree add ../coke-agent-runtime-redesign -b agent-runtime-redesign
cd ../coke-agent-runtime-redesign
```

Do not edit `gateway/` or `connector/clawscale_bridge/`.

The plan is intentionally staged:

1. Add typed boundaries with no behavior change.
2. Extract deterministic ports behind legacy workflow.
3. Add Team runtime under a feature flag.
4. Move runtime events onto typed inputs.
5. Cut over and delete legacy workflow code.

## File Map

Create:

- `agent/agno_agent/runtime/__init__.py` - exports runtime contract types.
- `agent/agno_agent/runtime/inputs.py` - `AgentInput` and payload models.
- `agent/agno_agent/runtime/context.py` - trusted run context models and builder.
- `agent/agno_agent/runtime/result.py` - visible message, capability result, output disposition, and run result models.
- `agent/agno_agent/runtime/selector.py` - legacy/team runtime selector.
- `agent/agno_agent/runtime/team_runtime.py` - feature-gated Team runtime wrapper.
- `agent/agno_agent/runtime/streaming.py` - event filter for user-visible leader output.
- `agent/agno_agent/runtime/trace.py` - simple per-run trace helpers.
- `agent/agno_agent/capabilities/__init__.py` - capability exports.
- `agent/agno_agent/capabilities/context_port.py` - typed context bundle builder.
- `agent/agno_agent/capabilities/reminder_intent.py` - wrapper around structured reminder detector.
- `agent/agno_agent/capabilities/search_port.py` - typed wrapper around `web_search_tool`.
- `agent/agno_agent/capabilities/timezone_port.py` - typed wrapper around timezone tools.
- `agent/agno_agent/capabilities/url_context_port.py` - typed wrapper around URL extraction.
- `agent/agno_agent/adapters/__init__.py` - adapter exports.
- `agent/agno_agent/adapters/reminder_command_executor.py` - post-Team deterministic reminder command executor.
- `agent/agno_agent/adapters/deferred_action_result.py` - maps runtime results to deferred-action executor decisions.
- `agent/agno_agent/adapters/output_disposition.py` - converts runtime output to runner disposition.
- `agent/agno_agent/prompts/manager.py` - manager/leader prompt builder.
- `agent/agno_agent/prompts/reminder_intent.py` - reminder intent prompt inputs if the existing prompt is split.

Modify:

- `agent/runner/agent_handler.py` - replace old workflow call with runtime adapter when selected.
- `agent/runner/reminder_event_handler.py` - add fired-event duplicate policy and typed-input route.
- `agent/runner/deferred_action_executor.py` - consume `DeferredActionFireResult` for team runtime.
- `agent/agno_agent/workflows/prepare_workflow.py` - during B.1 only, call extracted ports while legacy remains default.
- `agent/agno_agent/workflows/post_analyze_workflow.py` - accept typed `post_analyze_input` projection.
- `agent/agno_agent/agents/__init__.py` - remove `OrchestratorAgent` at final cutover.
- `agent/prompt/agent_instructions_prompt.py` - remove orchestrator prompt entries at final cutover.

Test:

- `tests/unit/agent/test_agent_runtime_types.py`
- `tests/unit/agent/test_agent_runtime_selector.py`
- `tests/unit/agent/test_context_port.py`
- `tests/unit/agent/test_reminder_command_executor.py`
- `tests/unit/agent/test_team_runtime_construction.py`
- `tests/unit/agent/test_team_streaming_filter.py`
- `tests/unit/agent/test_agent_handler.py`
- `tests/unit/runner/test_reminder_event_handler.py`
- `tests/unit/runner/test_deferred_action_executor.py`
- existing focused tests listed in `docs/fitness/coke-verification-matrix.md`

---

### Task 1: Runtime Contract Types

**Files:**
- Create: `agent/agno_agent/runtime/__init__.py`
- Create: `agent/agno_agent/runtime/inputs.py`
- Create: `agent/agno_agent/runtime/context.py`
- Create: `agent/agno_agent/runtime/result.py`
- Test: `tests/unit/agent/test_agent_runtime_types.py`

- [ ] **Step 1: Write tests for typed runtime contracts**

Add `tests/unit/agent/test_agent_runtime_types.py`:

```python
from datetime import UTC, datetime

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
)


def test_user_turn_input_is_explicit():
    event = AgentInput(
        input_type="user.turn",
        conversation_id="conv-1",
        text="remind me tomorrow",
        payload=UserTurnPayload(current_message_ids=["msg-1"]),
        occurred_at=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
    )

    assert event.input_type == "user.turn"
    assert event.payload.current_message_ids == ["msg-1"]


def test_reminder_fire_payload_carries_fire_id():
    payload = ReminderFirePayload(
        fire_id="rem-1:2026-05-01T01:00:00+00:00",
        reminder_id="rem-1",
        title="drink water",
        scheduled_for=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
        metadata={"event_type": "reminder.fired"},
    )

    assert payload.fire_id.startswith("rem-1:")
    assert payload.metadata["event_type"] == "reminder.fired"


def test_run_context_uses_trusted_context_objects():
    context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key=None,
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: hello",
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
        runtime_metadata={"worker_tag": "[T]"},
    )

    assert context.user.id == "user-1"
    assert context.conversation.id == "conv-1"
    assert context.relation.cid == "char-1"


def test_run_result_has_output_disposition():
    result = AgentRunResult(
        visible_messages=[
            VisibleMessage(message_type="text", content="Done", metadata={"k": "v"})
        ],
        post_analyze_input=None,
        tool_results=[CapabilityResult(name="reminder", ok=True, content={"id": "r1"})],
        metrics={"latency_ms": 12},
        trace={"runtime": "team"},
        output_disposition=OutputDisposition(status="ok", output_references=["out-1"]),
    )

    assert result.visible_messages[0].content == "Done"
    assert result.output_disposition.status == "ok"


def test_runtime_error_disposition_is_retryable():
    error = RuntimeErrorDisposition(
        code="agent_timeout",
        retryable=True,
        user_visible_fallback="I need a moment. Please try again.",
    )

    assert error.retryable is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_agent_runtime_types.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent.agno_agent.runtime'`.

- [ ] **Step 3: Implement runtime type modules**

Create `agent/agno_agent/runtime/inputs.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True)
class UserTurnPayload:
    current_message_ids: list[str] = field(default_factory=list)
    check_new_message: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReminderFirePayload:
    fire_id: str
    reminder_id: str
    title: str
    scheduled_for: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeferredActionPayload:
    action_id: str
    kind: str
    scheduled_for: datetime
    revision: int
    prompt: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentInput:
    input_type: Literal[
        "user.turn",
        "reminder.fire",
        "deferred_action.fire",
        "system.event",
    ]
    conversation_id: str
    text: str | None
    payload: UserTurnPayload | ReminderFirePayload | DeferredActionPayload | dict[str, Any]
    occurred_at: datetime
```

Create `agent/agno_agent/runtime/context.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TrustedUserContext:
    id: str
    nickname: str
    timezone: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrustedCharacterContext:
    id: str
    nickname: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrustedConversationContext:
    id: str
    platform: str
    route_key: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrustedRelationContext:
    uid: str
    cid: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentRunContext:
    user: TrustedUserContext
    character: TrustedCharacterContext
    conversation: TrustedConversationContext
    relation: TrustedRelationContext
    platform: str
    recent_chat_history: str
    current_time: datetime
    runtime_metadata: dict[str, Any] = field(default_factory=dict)
```

Create `agent/agno_agent/runtime/result.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class VisibleMessage:
    message_type: Literal["text", "voice", "photo"]
    content: str
    emotion: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityResult:
    name: str
    ok: bool
    content: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class RuntimeErrorDisposition:
    code: str
    retryable: bool
    user_visible_fallback: str | None


@dataclass(frozen=True)
class OutputDisposition:
    status: Literal["ok", "empty", "content_blocked", "rollback", "failed"]
    output_references: list[str] = field(default_factory=list)
    error: RuntimeErrorDisposition | None = None


@dataclass(frozen=True)
class AgentRunResult:
    visible_messages: list[VisibleMessage]
    post_analyze_input: dict[str, Any] | None
    tool_results: list[CapabilityResult]
    metrics: dict[str, Any]
    trace: dict[str, Any]
    output_disposition: OutputDisposition
    content_blocked: bool = False
    rollback: bool = False
```

Create `agent/agno_agent/runtime/__init__.py`:

```python
from .context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from .inputs import AgentInput, DeferredActionPayload, ReminderFirePayload, UserTurnPayload
from .result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
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
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/unit/agent/test_agent_runtime_types.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add agent/agno_agent/runtime tests/unit/agent/test_agent_runtime_types.py
git commit -m "feat(agent): add typed runtime contracts"
```

---

### Task 2: Runtime Selector

**Files:**
- Create: `agent/agno_agent/runtime/selector.py`
- Test: `tests/unit/agent/test_agent_runtime_selector.py`

- [ ] **Step 1: Write selector tests**

Add `tests/unit/agent/test_agent_runtime_selector.py`:

```python
from agent.agno_agent.runtime.selector import RuntimeSelectionInput, select_runtime


def test_explicit_override_wins(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "legacy")
    selected = select_runtime(
        RuntimeSelectionInput(
            explicit_override="team",
            conversation_override=None,
            customer_override=None,
        )
    )

    assert selected == "team"


def test_conversation_override_wins_over_customer_and_env(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "legacy")
    selected = select_runtime(
        RuntimeSelectionInput(
            explicit_override=None,
            conversation_override="team",
            customer_override="legacy",
        )
    )

    assert selected == "team"


def test_customer_override_wins_over_env(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "legacy")
    selected = select_runtime(
        RuntimeSelectionInput(
            explicit_override=None,
            conversation_override=None,
            customer_override="team",
        )
    )

    assert selected == "team"


def test_env_default_is_used(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")
    selected = select_runtime(RuntimeSelectionInput())

    assert selected == "team"


def test_invalid_values_fall_back_to_legacy(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "banana")
    selected = select_runtime(RuntimeSelectionInput())

    assert selected == "legacy"
```

- [ ] **Step 2: Run selector tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_agent_runtime_selector.py -v
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `selector`.

- [ ] **Step 3: Implement selector**

Create `agent/agno_agent/runtime/selector.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

RuntimeVersion = Literal["legacy", "team"]
_VALID: set[str] = {"legacy", "team"}


@dataclass(frozen=True)
class RuntimeSelectionInput:
    explicit_override: str | None = None
    conversation_override: str | None = None
    customer_override: str | None = None
    env_value: str | None = None


def _normalize(value: str | None) -> RuntimeVersion | None:
    if value in _VALID:
        return value  # type: ignore[return-value]
    return None


def select_runtime(selection: RuntimeSelectionInput | None = None) -> RuntimeVersion:
    selection = selection or RuntimeSelectionInput()
    env_value = selection.env_value
    if env_value is None:
        env_value = os.environ.get("AGENT_RUNTIME_VERSION")

    for candidate in (
        selection.explicit_override,
        selection.conversation_override,
        selection.customer_override,
        env_value,
    ):
        normalized = _normalize(candidate)
        if normalized is not None:
            return normalized
    return "legacy"
```

- [ ] **Step 4: Export selector**

Update `agent/agno_agent/runtime/__init__.py`:

```python
from .selector import RuntimeSelectionInput, RuntimeVersion, select_runtime
```

Add these names to `__all__`:

```python
    "RuntimeSelectionInput",
    "RuntimeVersion",
    "select_runtime",
```

- [ ] **Step 5: Run selector tests**

Run:

```bash
pytest tests/unit/agent/test_agent_runtime_selector.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add agent/agno_agent/runtime tests/unit/agent/test_agent_runtime_selector.py
git commit -m "feat(agent): add runtime selector"
```

---

### Task 3: Context Builder And ContextPort

**Files:**
- Modify: `agent/agno_agent/runtime/context.py`
- Create: `agent/agno_agent/capabilities/__init__.py`
- Create: `agent/agno_agent/capabilities/context_port.py`
- Test: `tests/unit/agent/test_context_port.py`

- [ ] **Step 1: Write context builder tests**

Add `tests/unit/agent/test_context_port.py`:

```python
from datetime import UTC, datetime

from agent.agno_agent.capabilities.context_port import ContextPort
from agent.agno_agent.runtime.context import build_agent_run_context


def _legacy_context():
    return {
        "user": {
            "_id": "user-1",
            "id": "user-1",
            "nickname": "User",
            "timezone": "Asia/Tokyo",
        },
        "character": {
            "_id": "char-1",
            "id": "char-1",
            "nickname": "Coke",
        },
        "conversation": {
            "_id": "conv-1",
            "platform": "business",
            "conversation_info": {
                "chat_history": [
                    {"from_nickname": "User", "message": "hello", "message_type": "text"}
                ],
                "chat_history_str": "User: hello",
            },
        },
        "relation": {"uid": "user-1", "cid": "char-1"},
        "platform": "business",
        "recent_chat_history": "User: hello",
    }


def test_build_agent_run_context_preserves_trusted_ids():
    context = build_agent_run_context(
        _legacy_context(),
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
        runtime_metadata={"worker_tag": "[T]"},
    )

    assert context.user.id == "user-1"
    assert context.user.timezone == "Asia/Tokyo"
    assert context.character.id == "char-1"
    assert context.conversation.id == "conv-1"
    assert context.relation.uid == "user-1"


def test_context_port_returns_deterministic_base_context():
    run_context = build_agent_run_context(
        _legacy_context(),
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
    )
    bundle = ContextPort().build_base_context(run_context)

    assert bundle["user"]["id"] == "user-1"
    assert bundle["character"]["id"] == "char-1"
    assert bundle["conversation"]["id"] == "conv-1"
    assert bundle["recent_chat_history"] == "User: hello"
```

- [ ] **Step 2: Run context tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_context_port.py -v
```

Expected: FAIL because `build_agent_run_context` and `ContextPort` do not exist.

- [ ] **Step 3: Implement context builder**

Append to `agent/agno_agent/runtime/context.py`:

```python
def _entity_id(value: dict[str, Any]) -> str:
    return str(value.get("_id") or value.get("id") or "").strip()


def _nickname(value: dict[str, Any], fallback: str) -> str:
    return str(value.get("display_name") or value.get("nickname") or value.get("name") or fallback)


def build_agent_run_context(
    legacy_context: dict[str, Any],
    *,
    current_time: datetime,
    runtime_metadata: dict[str, Any] | None = None,
) -> AgentRunContext:
    user = legacy_context.get("user") or {}
    character = legacy_context.get("character") or {}
    conversation = legacy_context.get("conversation") or {}
    relation = legacy_context.get("relation") or {}
    conversation_info = conversation.get("conversation_info") or {}

    user_id = _entity_id(user)
    character_id = _entity_id(character)
    conversation_id = str(conversation.get("_id") or legacy_context.get("conversation_id") or "").strip()
    platform = str(legacy_context.get("platform") or conversation.get("platform") or "business")

    return AgentRunContext(
        user=TrustedUserContext(
            id=user_id,
            nickname=_nickname(user, "User"),
            timezone=str(user.get("effective_timezone") or user.get("timezone") or "UTC"),
            raw=user,
        ),
        character=TrustedCharacterContext(
            id=character_id,
            nickname=_nickname(character, "Coke"),
            raw=character,
        ),
        conversation=TrustedConversationContext(
            id=conversation_id,
            platform=platform,
            route_key=conversation.get("route_key"),
            raw=conversation,
        ),
        relation=TrustedRelationContext(
            uid=str(relation.get("uid") or user_id),
            cid=str(relation.get("cid") or character_id),
            raw=relation,
        ),
        platform=platform,
        recent_chat_history=str(
            legacy_context.get("recent_chat_history")
            or conversation_info.get("chat_history_str")
            or ""
        ),
        current_time=current_time,
        runtime_metadata=runtime_metadata or {},
    )
```

- [ ] **Step 4: Implement ContextPort**

Create `agent/agno_agent/capabilities/context_port.py`:

```python
from __future__ import annotations

from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext


class ContextPort:
    def build_base_context(self, run_context: AgentRunContext) -> dict[str, Any]:
        return {
            "user": {
                "id": run_context.user.id,
                "nickname": run_context.user.nickname,
                "timezone": run_context.user.timezone,
            },
            "character": {
                "id": run_context.character.id,
                "nickname": run_context.character.nickname,
            },
            "conversation": {
                "id": run_context.conversation.id,
                "platform": run_context.conversation.platform,
                "route_key": run_context.conversation.route_key,
            },
            "relation": {
                "uid": run_context.relation.uid,
                "cid": run_context.relation.cid,
            },
            "current_time": run_context.current_time.isoformat(),
            "recent_chat_history": run_context.recent_chat_history,
        }
```

Create `agent/agno_agent/capabilities/__init__.py`:

```python
from .context_port import ContextPort

__all__ = ["ContextPort"]
```

- [ ] **Step 5: Run context tests**

Run:

```bash
pytest tests/unit/agent/test_context_port.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add agent/agno_agent/runtime/context.py agent/agno_agent/capabilities tests/unit/agent/test_context_port.py
git commit -m "feat(agent): add context port"
```

---

### Task 4: ReminderCommandExecutor Post-Team Adapter

**Files:**
- Create: `agent/agno_agent/adapters/__init__.py`
- Create: `agent/agno_agent/adapters/reminder_command_executor.py`
- Test: `tests/unit/agent/test_reminder_command_executor.py`

- [ ] **Step 1: Write reminder executor tests**

Add `tests/unit/agent/test_reminder_command_executor.py`:

```python
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from agent.agno_agent.adapters.reminder_command_executor import ReminderCommandExecutor
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)


def _run_context():
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(id="conv-1", platform="business", route_key="route-1"),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
        runtime_metadata={},
    )


def test_executor_calls_adapter_with_trusted_context():
    tool = Mock(return_value="created reminder")
    decision = SimpleNamespace(
        action="create",
        title="drink water",
        trigger_at="2026-05-01T09:00:00+09:00",
        reminder_id=None,
        keyword=None,
        new_title=None,
        new_trigger_at=None,
        rrule=None,
        operations=[],
    )

    result = ReminderCommandExecutor(tool_entrypoint=tool).execute(decision, _run_context())

    assert result.ok is True
    assert result.content["summary"] == "created reminder"
    tool.assert_called_once()
    assert tool.call_args.kwargs["action"] == "create"
    assert tool.call_args.kwargs["title"] == "drink water"


def test_executor_returns_failure_result_on_adapter_exception():
    tool = Mock(side_effect=RuntimeError("adapter failed"))
    decision = SimpleNamespace(
        action="create",
        title="drink water",
        trigger_at="2026-05-01T09:00:00+09:00",
        reminder_id=None,
        keyword=None,
        new_title=None,
        new_trigger_at=None,
        rrule=None,
        operations=[],
    )

    result = ReminderCommandExecutor(tool_entrypoint=tool).execute(decision, _run_context())

    assert result.ok is False
    assert result.error_code == "ReminderCommandExecutorError"
    assert "adapter failed" in result.error_message
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_reminder_command_executor.py -v
```

Expected: FAIL because `agent.agno_agent.adapters` does not exist.

- [ ] **Step 3: Implement adapter**

Create `agent/agno_agent/adapters/reminder_command_executor.py`:

```python
from __future__ import annotations

from typing import Any, Callable

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


class ReminderCommandExecutor:
    def __init__(self, tool_entrypoint: Callable[..., str]) -> None:
        self.tool_entrypoint = tool_entrypoint

    def execute(self, decision: Any, run_context: AgentRunContext) -> CapabilityResult:
        try:
            summary = self.tool_entrypoint(
                action=_value(decision, "action"),
                title=_value(decision, "title"),
                trigger_at=_value(decision, "trigger_at"),
                reminder_id=_value(decision, "reminder_id"),
                keyword=_value(decision, "keyword"),
                new_title=_value(decision, "new_title"),
                new_trigger_at=_value(decision, "new_trigger_at"),
                rrule=_value(decision, "rrule"),
                operations=_value(decision, "operations") or None,
            )
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={
                    "summary": summary,
                    "owner_user_id": run_context.user.id,
                    "conversation_id": run_context.conversation.id,
                },
            )
        except Exception as exc:
            return CapabilityResult(
                name="reminder",
                ok=False,
                content={},
                error_code="ReminderCommandExecutorError",
                error_message=str(exc),
            )
```

Create `agent/agno_agent/adapters/__init__.py`:

```python
from .reminder_command_executor import ReminderCommandExecutor

__all__ = ["ReminderCommandExecutor"]
```

- [ ] **Step 4: Run reminder executor tests**

Run:

```bash
pytest tests/unit/agent/test_reminder_command_executor.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add agent/agno_agent/adapters tests/unit/agent/test_reminder_command_executor.py
git commit -m "feat(agent): add reminder command executor adapter"
```

---

### Task 5: Team Construction Invariants

**Files:**
- Create: `agent/agno_agent/runtime/team_runtime.py`
- Test: `tests/unit/agent/test_team_runtime_construction.py`

- [ ] **Step 1: Write Team construction tests with a fake Team class**

Add `tests/unit/agent/test_team_runtime_construction.py`:

```python
import sys
import types


def _install_fake_agno_team(monkeypatch):
    agno = types.ModuleType("agno")
    agno.__path__ = []
    team_mod = types.ModuleType("agno.team")

    class FakeTeam:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.db = kwargs.get("db")
            self.add_session_state_to_context = kwargs.get("add_session_state_to_context")
            self.enable_agentic_state = kwargs.get("enable_agentic_state")
            self.cache_session = kwargs.get("cache_session")
            self.tools = kwargs.get("tools")

    team_mod.Team = FakeTeam
    monkeypatch.setitem(sys.modules, "agno", agno)
    monkeypatch.setitem(sys.modules, "agno.team", team_mod)


def test_team_runtime_disables_agno_persistent_state(monkeypatch):
    _install_fake_agno_team(monkeypatch)
    from agent.agno_agent.runtime.team_runtime import create_manager_team

    team = create_manager_team(model=object(), members=[])

    assert team.db is None
    assert team.add_session_state_to_context is False
    assert team.enable_agentic_state is False
    assert team.cache_session is False


def test_team_runtime_does_not_register_durable_write_tools(monkeypatch):
    _install_fake_agno_team(monkeypatch)
    from agent.agno_agent.runtime.team_runtime import create_manager_team

    team = create_manager_team(model=object(), members=[])

    assert team.tools == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_team_runtime_construction.py -v
```

Expected: FAIL because `team_runtime.py` does not exist.

- [ ] **Step 3: Implement Team factory**

Create `agent/agno_agent/runtime/team_runtime.py`:

```python
from __future__ import annotations

from typing import Any

from agno.team import Team


def create_manager_team(*, model: Any, members: list[Any]) -> Team:
    return Team(
        name="CokeManagerTeam",
        model=model,
        members=members,
        tools=[],
        db=None,
        add_session_state_to_context=False,
        enable_agentic_state=False,
        cache_session=False,
    )
```

- [ ] **Step 4: Run Team construction tests**

Run:

```bash
pytest tests/unit/agent/test_team_runtime_construction.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add agent/agno_agent/runtime/team_runtime.py tests/unit/agent/test_team_runtime_construction.py
git commit -m "feat(agent): add manager team construction guardrails"
```

---

### Task 6: Streaming Filter

**Files:**
- Create: `agent/agno_agent/runtime/streaming.py`
- Test: `tests/unit/agent/test_team_streaming_filter.py`

- [ ] **Step 1: Write streaming filter tests**

Add `tests/unit/agent/test_team_streaming_filter.py`:

```python
from types import SimpleNamespace

from agent.agno_agent.runtime.streaming import filter_user_visible_team_events


def test_filter_keeps_only_team_run_content_events():
    events = [
        SimpleNamespace(event="TeamRunStarted", content=None),
        SimpleNamespace(event="ToolCallStarted", content="secret tool"),
        SimpleNamespace(event="RunContent", content="member text", agent_id="member-1"),
        SimpleNamespace(event="TeamRunContent", content="hello", agent_id=None),
        SimpleNamespace(event="TeamRunContent", content=" world", agent_id=None),
        SimpleNamespace(event="TeamRunCompleted", content=None),
    ]

    chunks = list(filter_user_visible_team_events(events))

    assert chunks == ["hello", " world"]


def test_filter_ignores_reasoning_and_tool_content():
    events = [
        SimpleNamespace(event="TeamReasoningContentDelta", reasoning_content="hidden"),
        SimpleNamespace(event="ToolCallCompleted", content="tool result"),
        SimpleNamespace(event="TeamRunContent", content="visible"),
    ]

    chunks = list(filter_user_visible_team_events(events))

    assert chunks == ["visible"]
```

- [ ] **Step 2: Run streaming tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_team_streaming_filter.py -v
```

Expected: FAIL because `streaming.py` does not exist.

- [ ] **Step 3: Implement streaming filter**

Create `agent/agno_agent/runtime/streaming.py`:

```python
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any


def _event_name(event: Any) -> str:
    if isinstance(event, dict):
        return str(event.get("event") or "")
    return str(getattr(event, "event", "") or "")


def _content(event: Any) -> str:
    if isinstance(event, dict):
        value = event.get("content")
    else:
        value = getattr(event, "content", None)
    return value if isinstance(value, str) else ""


def filter_user_visible_team_events(events: Iterable[Any]) -> Iterator[str]:
    for event in events:
        if _event_name(event) != "TeamRunContent":
            continue
        content = _content(event)
        if content:
            yield content
```

- [ ] **Step 4: Run streaming tests**

Run:

```bash
pytest tests/unit/agent/test_team_streaming_filter.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```bash
git add agent/agno_agent/runtime/streaming.py tests/unit/agent/test_team_streaming_filter.py
git commit -m "feat(agent): filter team stream to visible content"
```

---

### Task 7: DeferredActionFireResult Contract

**Files:**
- Create: `agent/agno_agent/adapters/deferred_action_result.py`
- Test: `tests/unit/runner/test_deferred_action_executor.py`

- [ ] **Step 1: Add deferred result mapping tests**

Append to `tests/unit/runner/test_deferred_action_executor.py`:

```python
from agent.agno_agent.adapters.deferred_action_result import (
    DeferredActionFireResult,
    map_agent_result_to_deferred_status,
)
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    OutputDisposition,
    RuntimeErrorDisposition,
)


def test_deferred_result_maps_successful_output_to_succeeded():
    result = AgentRunResult(
        visible_messages=[],
        post_analyze_input=None,
        tool_results=[],
        metrics={},
        trace={},
        output_disposition=OutputDisposition(status="ok", output_references=["out-1"]),
    )

    mapped = map_agent_result_to_deferred_status(result)

    assert mapped == DeferredActionFireResult(
        status="succeeded",
        output_references=["out-1"],
        retryable=False,
    )


def test_deferred_result_maps_empty_output_to_retryable_no_output():
    result = AgentRunResult(
        visible_messages=[],
        post_analyze_input=None,
        tool_results=[],
        metrics={},
        trace={},
        output_disposition=OutputDisposition(status="empty"),
    )

    mapped = map_agent_result_to_deferred_status(result)

    assert mapped.status == "no_output"
    assert mapped.retryable is True


def test_deferred_result_preserves_retryable_runtime_error():
    result = AgentRunResult(
        visible_messages=[],
        post_analyze_input=None,
        tool_results=[],
        metrics={},
        trace={},
        output_disposition=OutputDisposition(
            status="failed",
            error=RuntimeErrorDisposition(
                code="agent_timeout",
                retryable=True,
                user_visible_fallback=None,
            ),
        ),
    )

    mapped = map_agent_result_to_deferred_status(result)

    assert mapped.status == "failed"
    assert mapped.retryable is True
    assert mapped.error_code == "agent_timeout"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/runner/test_deferred_action_executor.py -v
```

Expected: FAIL because `deferred_action_result.py` does not exist.

- [ ] **Step 3: Implement deferred result mapper**

Create `agent/agno_agent/adapters/deferred_action_result.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from agent.agno_agent.runtime.result import AgentRunResult


@dataclass(frozen=True)
class DeferredActionFireResult:
    status: Literal[
        "succeeded",
        "failed",
        "skipped",
        "content_blocked",
        "rollback",
        "no_output",
    ]
    output_references: list[str] = field(default_factory=list)
    retryable: bool = False
    error_code: str | None = None
    error_message: str | None = None


def map_agent_result_to_deferred_status(
    result: AgentRunResult,
) -> DeferredActionFireResult:
    disposition = result.output_disposition
    if result.rollback or disposition.status == "rollback":
        return DeferredActionFireResult(status="rollback", retryable=True)
    if result.content_blocked or disposition.status == "content_blocked":
        return DeferredActionFireResult(status="content_blocked", retryable=False)
    if disposition.status == "ok":
        return DeferredActionFireResult(
            status="succeeded",
            output_references=list(disposition.output_references),
            retryable=False,
        )
    if disposition.status == "empty":
        return DeferredActionFireResult(status="no_output", retryable=True)
    error = disposition.error
    return DeferredActionFireResult(
        status="failed",
        output_references=list(disposition.output_references),
        retryable=bool(error.retryable) if error else True,
        error_code=error.code if error else "agent_runtime_failed",
        error_message=error.user_visible_fallback if error else None,
    )
```

Update `agent/agno_agent/adapters/__init__.py`:

```python
from .deferred_action_result import (
    DeferredActionFireResult,
    map_agent_result_to_deferred_status,
)
from .reminder_command_executor import ReminderCommandExecutor

__all__ = [
    "DeferredActionFireResult",
    "ReminderCommandExecutor",
    "map_agent_result_to_deferred_status",
]
```

- [ ] **Step 4: Run deferred tests**

Run:

```bash
pytest tests/unit/runner/test_deferred_action_executor.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 7**

```bash
git add agent/agno_agent/adapters tests/unit/runner/test_deferred_action_executor.py
git commit -m "feat(agent): define deferred action fire result"
```

---

### Task 8: Reminder Fired Idempotency

**Files:**
- Modify: `agent/runner/reminder_event_handler.py`
- Test: `tests/unit/runner/test_reminder_event_handler.py`

- [ ] **Step 1: Add replay suppression test**

Append to `tests/unit/runner/test_reminder_event_handler.py`:

```python
@pytest.mark.asyncio
async def test_replayed_fire_id_returns_existing_output_without_duplicate_write():
    event = build_event()
    output_writer = Mock(return_value={"_id": "out-new"})
    existing_output_lookup = Mock(return_value={"_id": "out-existing"})
    handler = build_handler(output_writer)
    handler.existing_output_lookup = existing_output_lookup

    result = await handler.handle(event)

    existing_output_lookup.assert_called_once_with(event.fire_id)
    output_writer.assert_not_called()
    assert result.ok is True
    assert result.output_reference == "out-existing"
```

- [ ] **Step 2: Run reminder handler tests to verify they fail**

Run:

```bash
pytest tests/unit/runner/test_reminder_event_handler.py -v
```

Expected: FAIL because `existing_output_lookup` is not called by the handler.

- [ ] **Step 3: Add lookup dependency and duplicate check**

Modify `ReminderFireEventHandler.__init__` in
`agent/runner/reminder_event_handler.py` to accept:

```python
        existing_output_lookup: Callable[[str], Any] | None = None,
```

Assign it:

```python
        self.existing_output_lookup = existing_output_lookup or (lambda fire_id: None)
```

At the start of `handle()` after `conversation_id` is computed, add:

```python
        existing_output = self.existing_output_lookup(event.fire_id)
        if existing_output is not None:
            return ReminderFireResult(
                ok=True,
                fire_id=event.fire_id,
                output_reference=self._output_reference(existing_output),
                error_code=None,
                error_message=None,
            )
```

- [ ] **Step 4: Run reminder handler tests**

Run:

```bash
pytest tests/unit/runner/test_reminder_event_handler.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 8**

```bash
git add agent/runner/reminder_event_handler.py tests/unit/runner/test_reminder_event_handler.py
git commit -m "fix(reminder): suppress replayed fired events by fire id"
```

---

### Task 9: Legacy Handler Runtime Gate

**Files:**
- Modify: `agent/runner/agent_handler.py`
- Test: `tests/unit/agent/test_agent_handler.py`

- [ ] **Step 1: Add test that legacy remains default**

Append to `tests/unit/agent/test_agent_handler.py`:

```python
def test_agent_runtime_defaults_to_legacy(monkeypatch):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.delenv("AGENT_RUNTIME_VERSION", raising=False)

    from agent.runner import agent_handler

    assert agent_handler._select_agent_runtime({}) == "legacy"
```

- [ ] **Step 2: Add test that env can choose team**

Append to `tests/unit/agent/test_agent_handler.py`:

```python
def test_agent_runtime_env_selects_team(monkeypatch):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

    from agent.runner import agent_handler

    assert agent_handler._select_agent_runtime({}) == "team"
```

- [ ] **Step 3: Run focused agent handler tests to verify failure**

Run:

```bash
pytest tests/unit/agent/test_agent_handler.py::test_agent_runtime_defaults_to_legacy tests/unit/agent/test_agent_handler.py::test_agent_runtime_env_selects_team -v
```

Expected: FAIL because `_select_agent_runtime` does not exist.

- [ ] **Step 4: Implement selector wrapper in agent_handler**

Add to `agent/runner/agent_handler.py` near configuration helpers:

```python
def _select_agent_runtime(context: dict) -> str:
    from agent.agno_agent.runtime.selector import RuntimeSelectionInput, select_runtime

    conversation = context.get("conversation") or {}
    customer = context.get("customer") or {}
    return select_runtime(
        RuntimeSelectionInput(
            conversation_override=conversation.get("agent_runtime_version"),
            customer_override=customer.get("agent_runtime_version"),
        )
    )
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/unit/agent/test_agent_handler.py::test_agent_runtime_defaults_to_legacy tests/unit/agent/test_agent_handler.py::test_agent_runtime_env_selects_team -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 9**

```bash
git add agent/runner/agent_handler.py tests/unit/agent/test_agent_handler.py
git commit -m "feat(agent): add runtime gate in handler"
```

---

### Task 10: Team Runtime Skeleton Behind Feature Flag

**Files:**
- Modify: `agent/agno_agent/runtime/team_runtime.py`
- Modify: `agent/runner/agent_handler.py`
- Test: `tests/unit/agent/test_agent_handler.py`

- [ ] **Step 1: Add test that team runtime path can be invoked with a fake runtime**

Append to `tests/unit/agent/test_agent_handler.py`:

```python
@pytest.mark.asyncio
async def test_handle_message_team_runtime_uses_agent_runtime(monkeypatch, sample_context):
    _install_agent_handler_agno_stubs(monkeypatch)
    monkeypatch.setenv("AGENT_RUNTIME_VERSION", "team")

    from agent.runner import agent_handler
    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )

    async def fake_run_agent_runtime(*, context, input_message_str, message_source, metadata):
        return AgentRunResult(
            visible_messages=[VisibleMessage(message_type="text", content="team reply")],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    sent = []
    monkeypatch.setattr(agent_handler, "_run_agent_runtime", fake_run_agent_runtime)
    monkeypatch.setattr(
        agent_handler,
        "_send_single_message",
        lambda context, multimodal_response, expect_output_timestamp, is_first: (
            sent.append(multimodal_response) or {"_id": "out-1"},
            expect_output_timestamp,
        ),
    )
    monkeypatch.setattr(agent_handler, "is_new_message_coming_in", lambda *args: False)

    resp_messages, _, is_rollback, is_content_blocked = await agent_handler.handle_message(
        context=sample_context,
        input_message_str="hello",
        message_source="user",
        check_new_message=False,
        worker_tag="[T]",
        current_message_ids=[],
    )

    assert resp_messages == [{"_id": "out-1"}]
    assert sent[0]["content"] == "team reply"
    assert is_rollback is False
    assert is_content_blocked is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_uses_agent_runtime -v
```

Expected: FAIL because `_run_agent_runtime` and team branch do not exist.

- [ ] **Step 3: Add `_run_agent_runtime` seam**

Add to `agent/runner/agent_handler.py`:

```python
async def _run_agent_runtime(
    *,
    context: dict,
    input_message_str: str,
    message_source: str,
    metadata: Optional[Dict[str, Any]],
):
    from agent.agno_agent.runtime.team_runtime import run_team_runtime

    return await run_team_runtime(
        context=context,
        input_message_str=input_message_str,
        message_source=message_source,
        metadata=metadata or {},
    )
```

Create a minimal `run_team_runtime` in `agent/agno_agent/runtime/team_runtime.py`:

```python
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    OutputDisposition,
    RuntimeErrorDisposition,
)


async def run_team_runtime(
    *,
    context: dict,
    input_message_str: str,
    message_source: str,
    metadata: dict,
):
    return AgentRunResult(
        visible_messages=[],
        post_analyze_input=None,
        tool_results=[],
        metrics={},
        trace={"runtime": "team", "status": "empty_skeleton"},
        output_disposition=OutputDisposition(
            status="empty",
            error=RuntimeErrorDisposition(
                code="team_runtime_empty_skeleton",
                retryable=False,
                user_visible_fallback=None,
            ),
        ),
    )
```

- [ ] **Step 4: Add team branch before legacy PrepareWorkflow in `handle_message`**

Inside `handle_message()`, after context setup and before legacy Phase 1, add:

```python
    if _select_agent_runtime(context) == "team":
        result = await _run_agent_runtime(
            context=context,
            input_message_str=input_message_str,
            message_source=message_source,
            metadata=metadata,
        )
        expect_output_timestamp = int(time.time())
        for index, visible_message in enumerate(result.visible_messages):
            outputmessage, expect_output_timestamp = _send_single_message(
                context=context,
                multimodal_response={
                    "type": visible_message.message_type,
                    "content": visible_message.content,
                    "emotion": visible_message.emotion,
                    "metadata": visible_message.metadata,
                },
                expect_output_timestamp=expect_output_timestamp,
                is_first=(index == 0),
            )
            if outputmessage is not None:
                resp_messages.append(outputmessage)
        return resp_messages, context, result.rollback, result.content_blocked
```

- [ ] **Step 5: Run team branch test**

Run:

```bash
pytest tests/unit/agent/test_agent_handler.py::test_handle_message_team_runtime_uses_agent_runtime -v
```

Expected: PASS.

- [ ] **Step 6: Run existing agent handler tests**

Run:

```bash
pytest tests/unit/agent/test_agent_handler.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 10**

```bash
git add agent/runner/agent_handler.py agent/agno_agent/runtime/team_runtime.py tests/unit/agent/test_agent_handler.py
git commit -m "feat(agent): add team runtime branch"
```

---

### Task 11: Acceptance Gates Before Full Team Implementation

**Files:**
- Modify: `tests/unit/agent/test_agent_handler.py`
- Test existing files:
  - `tests/unit/test_prepare_workflow_timezone.py`
  - `tests/unit/test_prepare_workflow_web_search.py`
  - `tests/unit/agent/test_chat_workflow_calendar_import.py`
  - `tests/unit/test_url_reader.py`

- [ ] **Step 1: Add named acceptance test list to agent handler test module**

Append to `tests/unit/agent/test_agent_handler.py`:

```python
def test_agent_runtime_acceptance_contract_names_are_tracked():
    required_contracts = {
        "sync_first_text",
        "rollback_new_message",
        "timeout_fallback",
        "timezone_proposal_update",
        "url_context",
        "calendar_import_entry",
        "empty_output_fallback",
        "fired_event_replay",
    }

    implemented_contracts = {
        "sync_first_text",
        "rollback_new_message",
        "timeout_fallback",
        "timezone_proposal_update",
        "url_context",
        "calendar_import_entry",
        "empty_output_fallback",
        "fired_event_replay",
    }

    assert implemented_contracts == required_contracts
```

This test is a checklist anchor. Replace each set member with a dedicated
behavior test before B.4 cutover.

- [ ] **Step 2: Run acceptance-adjacent tests**

Run:

```bash
pytest tests/unit/agent/test_agent_handler.py tests/unit/test_prepare_workflow_timezone.py tests/unit/test_prepare_workflow_web_search.py tests/unit/agent/test_chat_workflow_calendar_import.py tests/unit/test_url_reader.py -v
```

Expected: PASS.

- [ ] **Step 3: Run reminder eval baseline**

Run:

```bash
python scripts/eval_reminder_normal_path_cases.py
```

Expected: command completes and writes an evidence file under `tasks/evidence/reminder-normal/`.

- [ ] **Step 4: Commit Task 11**

```bash
git add tests/unit/agent/test_agent_handler.py tasks/evidence/reminder-normal
git commit -m "test(agent): record runtime acceptance contracts"
```

---

### Task 12: Full Verification Before B.2 Work

**Files:** no source changes.

- [ ] **Step 1: Run worker-runtime focused tests**

Run:

```bash
pytest tests/unit/runner/ -v
pytest tests/unit/agent/ -v
pytest tests/unit/test_clawscale_only_topology.py -v
```

Expected: PASS.

- [ ] **Step 2: Run focused reminder-system tests**

Run:

```bash
pytest tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py -v
pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py -v
pytest tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/test_tool_results_context.py -v
pytest tests/e2e/test_reminder_system_flow.py -v
```

Expected: PASS.

- [ ] **Step 3: Run repo check**

Run:

```bash
zsh scripts/check
```

Expected: `check passed`.

- [ ] **Step 4: Commit verification evidence if new evidence files were generated**

```bash
git status --short
git add tasks/evidence/reminder-normal
git commit -m "test(agent): capture runtime redesign baseline evidence"
```

If no evidence files changed, do not create an empty commit.

---

## Follow-Up Plans Required After This Plan

This plan gets the system to a safe B.2 entry point: typed boundary, selector,
ports, post-Team reminder adapter, streaming filter, deferred-action result
contract, and event idempotency.

Create separate follow-up plans for:

1. **B.2 Team Runtime Implementation**
   - real manager prompt
   - real Agno leader and member wiring
   - reminder-intent member wrapping current `ReminderDetectAgent`
   - leader synthesis from post-Team command results
   - full team reminder eval

2. **B.3 Runtime Event Migration**
   - route `ReminderFiredEvent` and deferred actions through typed inputs
   - enforce `DeferredActionFireResult` in executor lifecycle
   - run replay/idempotency tests and manual reminder fire smoke

3. **B.4 Cutover And Deletion**
   - delete `PrepareWorkflow`
   - delete `StreamingChatWorkflow`
   - delete `OrchestratorResponse`
   - remove orchestrator prompts
   - run full unit/e2e/reminder eval/check suite

Do not begin B.2 until Task 12 passes.
