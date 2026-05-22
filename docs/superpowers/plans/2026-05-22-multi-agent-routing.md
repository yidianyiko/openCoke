# Multi-Agent Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `agent_runtime.py` from a single 18-tool agent to a Poke-style Interaction Agent (5 tools) + Execution Agents (reminder: direct port call, scheduling: 14-tool agent), preserving every existing runtime contract.

**Architecture:** The Interaction Agent routes via two domain tools (`reminder_domain`, `scheduling_domain`) and three utility tools. `reminder_domain` calls `ReminderIntentPort` directly (no intermediate agent, same LLM call count as current). `scheduling_domain` spawns a stateless `SchedulingExecutionAgent` with all 14 scheduling tools. For `reminder.fired`, `tools=[]` gives an API-level CRUD guardrail — stronger than the current prompt-only boundary.

**Tech Stack:** Python 3.12, Agno 2.5.9, asyncio, Pydantic v2, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-05-22-multi-agent-routing-design.md` — read it before starting. Section 4 (Agno source findings) governs every design decision.

---

## File Map

| File | Change |
|------|--------|
| `agent/agno_agent/runtime/scheduling_types.py` | **CREATE** — Pydantic models + `_compact_scheduling_args` |
| `agent/agno_agent/runtime/execution_agents.py` | **CREATE** — `run_reminder_domain()`, `run_scheduling_domain()` |
| `agent/agno_agent/runtime/agent_runtime.py` | **MODIFY** — add `_create_interaction_agent()`, remove `_create_agent()` / `_default_capability_ports()` / scheduling branch |
| `agent/agno_agent/runtime/chat_response_instructions.py` | **MODIFY** — `_DELEGATION_BOUNDARY` replaces `_REMINDER_TOOL_BOUNDARY`; `_SCHEDULING_TOOL_BOUNDARY` removed |
| `tests/unit/agent/test_scheduling_types.py` | **CREATE** |
| `tests/unit/agent/test_execution_agents.py` | **CREATE** |
| `tests/unit/agent/test_agent_runtime_construction.py` | **MODIFY** — rename `_create_agent` → `_create_interaction_agent`, dual-mode tests, Option-B test |
| `tests/unit/agent/test_agent_runtime_scheduling_tools.py` | **MODIFY** — remove dead-code tests, fix import, keep wrapper schema tests |
| `tests/unit/agent/test_chat_response_scheduling_instructions.py` | **MODIFY** — replace `_SCHEDULING_TOOL_BOUNDARY` assertion with `_DELEGATION_BOUNDARY` assertion |
| `tests/unit/agent/test_chat_response_instructions.py` | **MODIFY** — update reminder boundary assertion |

---

## Task 1: Create `scheduling_types.py`

Extract three Pydantic models and `_compact_scheduling_args` from `agent_runtime.py` into a new thin shared module. This breaks the circular import that would arise when `execution_agents.py` needs `SchedulingBookableWindowPreview`.

**Files:**
- Create: `agent/agno_agent/runtime/scheduling_types.py`
- Create: `tests/unit/agent/test_scheduling_types.py`
- Modify: `agent/agno_agent/runtime/agent_runtime.py` (import from new module, remove local definitions)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/test_scheduling_types.py
from agent.agno_agent.runtime.scheduling_types import (
    SchedulingBookableWindowPreview,
    SchedulingBookableWindowPreviewItem,
    SchedulingBookableWindowRule,
    _compact_scheduling_args,
)


def test_compact_scheduling_args_strips_none_and_empty_string():
    result = _compact_scheduling_args({"a": None, "b": "", "c": "val", "d": "x"})
    assert result == {"c": "val", "d": "x"}


def test_compact_scheduling_args_serializes_pydantic_preview():
    preview = SchedulingBookableWindowPreview(previewId="bwp_1", windows=[])
    result = _compact_scheduling_args({"preview": preview, "reason": None})
    assert result == {"preview": {"previewId": "bwp_1", "windows": []}}


def test_compact_scheduling_args_passes_through_primitives():
    result = _compact_scheduling_args({"target_account_id": "abc", "timezone": "UTC"})
    assert result == {"target_account_id": "abc", "timezone": "UTC"}


def test_scheduling_bookable_window_preview_round_trips():
    preview = SchedulingBookableWindowPreview(
        previewId="bwp_test",
        windows=[
            SchedulingBookableWindowPreviewItem(
                fingerprint="fp_1",
                rule=SchedulingBookableWindowRule(
                    type="weekly",
                    days_of_week=[1, 3],
                    time_start="09:00",
                    time_end="10:00",
                    timezone="Asia/Shanghai",
                ),
            )
        ],
    )
    dumped = preview.model_dump()
    assert dumped["previewId"] == "bwp_test"
    assert dumped["windows"][0]["fingerprint"] == "fp_1"
    assert dumped["windows"][0]["rule"]["type"] == "weekly"
```

- [ ] **Step 2: Run to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_scheduling_types.py -v
```

Expected: `ModuleNotFoundError: No module named 'agent.agno_agent.runtime.scheduling_types'`

- [ ] **Step 3: Create `scheduling_types.py`**

```python
# agent/agno_agent/runtime/scheduling_types.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel


class SchedulingBookableWindowRule(BaseModel):
    type: str
    days_of_week: list[int] | None = None
    time_start: str | None = None
    time_end: str | None = None
    timezone: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None
    date: str | None = None


class SchedulingBookableWindowPreviewItem(BaseModel):
    rule: SchedulingBookableWindowRule
    fingerprint: str


class SchedulingBookableWindowPreview(BaseModel):
    previewId: str
    windows: list[SchedulingBookableWindowPreviewItem]


def _compact_scheduling_args(args: Mapping[str, Any]) -> dict[str, Any]:
    """Filter None/''/empty values; serialize Pydantic models via model_dump()."""
    out: dict[str, Any] = {}
    for key, value in args.items():
        if value is None or value == "":
            continue
        out[key] = value.model_dump() if isinstance(value, BaseModel) else value
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_scheduling_types.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Update `agent_runtime.py` — replace local definitions with imports**

In `agent/agno_agent/runtime/agent_runtime.py`:

a) At the top of the file, after the existing imports, add:

```python
from agent.agno_agent.runtime.scheduling_types import (
    SchedulingBookableWindowPreview,
    SchedulingBookableWindowPreviewItem,
    SchedulingBookableWindowRule,
    _compact_scheduling_args,
)
```

b) Delete the three class definitions (lines 50–68 in the current file):

```python
# DELETE all of this:
class SchedulingBookableWindowRule(BaseModel):
    type: str
    days_of_week: list[int] | None = None
    time_start: str | None = None
    time_end: str | None = None
    timezone: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None
    date: str | None = None


class SchedulingBookableWindowPreviewItem(BaseModel):
    rule: SchedulingBookableWindowRule
    fingerprint: str


class SchedulingBookableWindowPreview(BaseModel):
    previewId: str
    windows: list[SchedulingBookableWindowPreviewItem]
```

c) Delete the `_compact_scheduling_args` function definition (lines 359–364):

```python
# DELETE all of this:
def _compact_scheduling_args(args: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _jsonable(value)
        for key, value in args.items()
        if value is not None and value != ""
    }
```

d) Also remove `Mapping` from the `collections.abc` import if it is now unused — check first with `grep`:

```bash
grep -n "Mapping" agent/agno_agent/runtime/agent_runtime.py
```

`Mapping` is still used in `_jsonable` and `build_capability_tool_wrappers`, so keep it.

e) Update `test_agent_runtime_scheduling_tools.py` import (line 13–14). Change:

```python
from agent.agno_agent.runtime.agent_runtime import (
    SchedulingBookableWindowPreview,
    build_capability_tool_wrappers,
)
```

to:

```python
from agent.agno_agent.runtime.agent_runtime import build_capability_tool_wrappers
from agent.agno_agent.runtime.scheduling_types import SchedulingBookableWindowPreview
```

- [ ] **Step 6: Run existing tests to verify no regressions**

```bash
.venv/bin/python -m pytest tests/unit/agent/ -v
```

Expected: all existing tests pass (the import change is transparent since `agent_runtime.py` re-exports the names).

- [ ] **Step 7: Commit**

```bash
git add agent/agno_agent/runtime/scheduling_types.py \
        agent/agno_agent/runtime/agent_runtime.py \
        tests/unit/agent/test_scheduling_types.py \
        tests/unit/agent/test_agent_runtime_scheduling_tools.py
git commit -m "feat: extract scheduling_types.py from agent_runtime"
```

---

## Task 2: Create `execution_agents.py` — Reminder Domain

Implement `run_reminder_domain()`: calls `ReminderIntentPort` directly (no intermediate Agno Agent), appends one `CapabilityResult` to the shared `tool_results` list, returns the capability envelope.

**Files:**
- Create: `agent/agno_agent/runtime/execution_agents.py`
- Create: `tests/unit/agent/test_execution_agents.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/test_execution_agents.py
from __future__ import annotations

import pytest
from datetime import UTC, datetime
from unittest.mock import patch

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.execution_agents import run_reminder_domain
from agent.agno_agent.runtime.result import CapabilityResult


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
        runtime_metadata={},
    )


class _FakePort:
    def __init__(self, result: CapabilityResult) -> None:
        self._result = result

    async def run(self, input_message, run_context, args):
        return self._result


@pytest.mark.asyncio
async def test_run_reminder_domain_appends_exactly_one_result_to_tool_results():
    fake_result = CapabilityResult(
        name="reminder",
        ok=True,
        content={"visible_summary": "已为你设好提醒"},
        metadata={"durable_write": True},
    )
    tool_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        await run_reminder_domain(
            input_message="提醒我喝水",
            run_context=_run_context(),
            tool_results=tool_results,
        )

    assert len(tool_results) == 1
    assert tool_results[0] is fake_result


@pytest.mark.asyncio
async def test_run_reminder_domain_returns_full_capability_envelope():
    fake_result = CapabilityResult(
        name="reminder",
        ok=True,
        content={"visible_summary": "已为你设好提醒", "synthesis_context": "ctx"},
        metadata={"durable_write": True},
    )
    tool_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        envelope = await run_reminder_domain(
            input_message="提醒我喝水",
            run_context=_run_context(),
            tool_results=tool_results,
        )

    assert envelope["ok"] is True
    assert envelope["visible_summary"] == "已为你设好提醒"
    assert envelope["synthesis_context"] == "ctx"
    assert "content" in envelope
    assert envelope["error"] is None


@pytest.mark.asyncio
async def test_run_reminder_domain_forwards_failed_port_result():
    fake_result = CapabilityResult(
        name="reminder",
        ok=False,
        content={},
        error="reminder_service_unavailable",
    )
    tool_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        envelope = await run_reminder_domain(
            input_message="set a reminder",
            run_context=_run_context(),
            tool_results=tool_results,
        )

    assert envelope["ok"] is False
    assert envelope["error"] == "reminder_service_unavailable"
    assert len(tool_results) == 1
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_execution_agents.py -v
```

Expected: `ModuleNotFoundError: No module named 'agent.agno_agent.runtime.execution_agents'`

- [ ] **Step 3: Create `execution_agents.py` with reminder domain only**

```python
# agent/agno_agent/runtime/execution_agents.py
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

from agent.agno_agent.capabilities import ReminderIntentPort
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult

logger = logging.getLogger(__name__)


async def _run_port(
    port: Any,
    *,
    input_message: str,
    run_context: AgentRunContext,
    args: dict[str, Any],
) -> CapabilityResult:
    run = port.run
    if inspect.iscoroutinefunction(run):
        return await run(input_message, run_context, args)
    return await asyncio.to_thread(run, input_message, run_context, args)


def _capability_envelope(result: CapabilityResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "ok": result.ok,
        "content": dict(result.content),
        "visible_summary": result.visible_summary,
        "synthesis_context": result.synthesis_context,
        "error": result.error,
    }


async def run_reminder_domain(
    *,
    input_message: str,
    run_context: AgentRunContext,
    tool_results: list[CapabilityResult],
) -> dict[str, Any]:
    """Call ReminderIntentPort directly; append result to shared tool_results.

    No intermediate Agno Agent. Saves one LLM call vs. a ReminderExecutionAgent.
    ReminderIntentPort handles all outcomes: CRUD, clarification, no-intent.
    """
    port = ReminderIntentPort()
    result = await _run_port(
        port,
        input_message=input_message,
        run_context=run_context,
        args={},
    )
    tool_results.append(result)
    return _capability_envelope(result)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_execution_agents.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/runtime/execution_agents.py \
        tests/unit/agent/test_execution_agents.py
git commit -m "feat: add run_reminder_domain() in execution_agents"
```

---

## Task 3: Add `run_scheduling_domain()` to `execution_agents.py`

Implement `run_scheduling_domain()`: spawns a stateless `SchedulingExecutionAgent` with 14 scheduling tools, reads results from a local `domain_results` list (not from `tool_results[-1]` — concurrency-safe), returns an envelope.

**Files:**
- Modify: `agent/agno_agent/runtime/execution_agents.py`
- Modify: `tests/unit/agent/test_execution_agents.py`

- [ ] **Step 1: Add failing tests for `_make_scheduling_tool_fn` and `run_scheduling_domain`**

Append to `tests/unit/agent/test_execution_agents.py`:

```python
from agent.agno_agent.runtime.execution_agents import (
    _make_scheduling_tool_fn,
    run_scheduling_domain,
)


class _SyncPort:
    """Sync port — tests that asyncio.to_thread() path is used."""

    def __init__(self, result: CapabilityResult) -> None:
        self._result = result

    def run(self, input_message, run_context, args):
        return self._result


@pytest.mark.asyncio
async def test_make_scheduling_tool_fn_appends_to_both_lists():
    fake_result = CapabilityResult(
        name="get_user_link",
        ok=True,
        content={"visible_summary": "Your booking link: https://kap.example/u/xyz"},
    )
    tool_results: list[CapabilityResult] = []
    domain_results: list[CapabilityResult] = []

    fn = _make_scheduling_tool_fn(
        "get_user_link",
        _SyncPort(fake_result),
        input_message="show my link",
        run_context=_run_context(),
        tool_results=tool_results,
        domain_results=domain_results,
    )
    envelope = await fn()

    assert tool_results == [fake_result]
    assert domain_results == [fake_result]
    assert envelope["ok"] is True
    assert envelope["visible_summary"] == "Your booking link: https://kap.example/u/xyz"


@pytest.mark.asyncio
async def test_make_scheduling_tool_fn_passes_non_none_args_to_port():
    received_args: list[dict] = []

    class RecordingPort:
        def run(self, input_message, run_context, args):
            received_args.append(args)
            return CapabilityResult(name="confirm_appointment", ok=True, content={})

    fn = _make_scheduling_tool_fn(
        "confirm_appointment",
        RecordingPort(),
        input_message="confirm that",
        run_context=_run_context(),
        tool_results=[],
        domain_results=[],
    )
    await fn(appointment_or_request_id="appt_123", reason=None)

    assert received_args == [{"appointment_or_request_id": "appt_123"}]


@pytest.mark.asyncio
async def test_run_scheduling_domain_returns_no_tool_called_when_agent_calls_nothing():
    """When SchedulingExecutionAgent completes without calling any tool, error envelope returned."""

    class _NoOpAgent:
        def __init__(self, **kwargs):
            pass

        async def arun(self, **kwargs):
            pass  # no tool calls → domain_results stays empty

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _NoOpAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: _SyncPort(
                CapabilityResult(name=tool_name, ok=True, content={})
            ),
        ):
            result = await run_scheduling_domain(
                input_message="show my link",
                intent="get_user_link",
                run_context=_run_context(),
                tool_results=[],
            )

    assert result["ok"] is False
    assert result["error"] == "no_tool_called"
    assert result["domain"] == "scheduling"
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_execution_agents.py -v -k "scheduling"
```

Expected: `ImportError: cannot import name '_make_scheduling_tool_fn'`

- [ ] **Step 3: Add scheduling domain to `execution_agents.py`**

Append to `agent/agno_agent/runtime/execution_agents.py`:

```python
from agno.agent import Agent
from agno.tools import tool

from agent.agno_agent.capabilities import SchedulingCapabilityPort
from agent.agno_agent.capabilities.scheduling import SCHEDULING_TOOL_NAMES
from agent.agno_agent.model_factory import create_llm_model
from agent.agno_agent.runtime.scheduling_types import (
    SchedulingBookableWindowPreview,
    _compact_scheduling_args,
)

_SCHEDULING_DOMAIN_INSTRUCTIONS_TEMPLATE = (
    "You are the scheduling execution worker. The intent is: {intent}. "
    "Call exactly one scheduling tool that matches the intent. "
    "Output only the tool call — do not generate user-visible text."
)


def _make_scheduling_tool_fn(
    tool_name: str,
    port: Any,
    *,
    input_message: str,
    run_context: AgentRunContext,
    tool_results: list[CapabilityResult],
    domain_results: list[CapabilityResult],
) -> Any:
    async def scheduling_tool(
        target_account_id: str | None = None,
        consumer_account_id: str | None = None,
        other_account_id: str | None = None,
        request_id: str | None = None,
        appointment_or_request_id: str | None = None,
        window_instance_id: str | None = None,
        bookable_window_id: str | None = None,
        instance_start: str | None = None,
        instance_end: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        timezone: str | None = None,
        viewer_timezone: str | None = None,
        instruction: str | None = None,
        preview: SchedulingBookableWindowPreview | None = None,
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Use only for the scheduling action specified in the intent."""
        r = await _run_port(
            port,
            input_message=input_message,
            run_context=run_context,
            args=_compact_scheduling_args(
                {
                    "target_account_id": target_account_id,
                    "consumer_account_id": consumer_account_id,
                    "other_account_id": other_account_id,
                    "request_id": request_id,
                    "appointment_or_request_id": appointment_or_request_id,
                    "window_instance_id": window_instance_id,
                    "bookable_window_id": bookable_window_id,
                    "instance_start": instance_start,
                    "instance_end": instance_end,
                    "date_from": date_from,
                    "date_to": date_to,
                    "timezone": timezone,
                    "viewer_timezone": viewer_timezone,
                    "instruction": instruction,
                    "preview": preview,
                    "reason": reason,
                    "idempotency_key": idempotency_key,
                }
            ),
        )
        tool_results.append(r)
        domain_results.append(r)
        return _capability_envelope(r)

    return scheduling_tool


async def run_scheduling_domain(
    *,
    input_message: str,
    intent: str,
    run_context: AgentRunContext,
    tool_results: list[CapabilityResult],
) -> dict[str, Any]:
    """Spawn SchedulingExecutionAgent; append result to shared tool_results.

    `intent` is required because the agent has no conversation history.
    The Interaction Agent must extract entity ids from its own history and
    encode them in `intent`, e.g. 'confirm_appointment: id=abc123'.
    """
    domain_results: list[CapabilityResult] = []
    ports = {name: SchedulingCapabilityPort(tool_name=name) for name in SCHEDULING_TOOL_NAMES}
    tools = [
        tool(name=name)(
            _make_scheduling_tool_fn(
                name,
                port,
                input_message=input_message,
                run_context=run_context,
                tool_results=tool_results,
                domain_results=domain_results,
            )
        )
        for name, port in ports.items()
    ]
    agent = Agent(
        id="coke-scheduling-agent",
        name="CokeSchedulingAgent",
        model=create_llm_model(role="chat_response", max_tokens=1000),
        instructions=_SCHEDULING_DOMAIN_INSTRUCTIONS_TEMPLATE.format(intent=intent),
        tools=tools,
        db=None,
        add_history_to_context=False,
        tool_call_limit=4,
        markdown=False,
    )
    await agent.arun(input=input_message)
    last = domain_results[-1] if domain_results else None
    if last is None:
        return {
            "ok": False,
            "domain": "scheduling",
            "visible_summary": None,
            "synthesis_context": None,
            "error": "no_tool_called",
        }
    return {
        "ok": last.ok,
        "domain": "scheduling",
        "visible_summary": last.visible_summary,
        "synthesis_context": last.synthesis_context,
        "content": dict(last.content),
        "error": last.error,
    }
```

Note: the new imports (`Agent`, `tool`, `SchedulingCapabilityPort`, etc.) go at the top of `execution_agents.py`, after the existing imports from Task 2.

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_execution_agents.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/runtime/execution_agents.py \
        tests/unit/agent/test_execution_agents.py
git commit -m "feat: add run_scheduling_domain() and _make_scheduling_tool_fn"
```

---

## Task 4: Add `_create_interaction_agent()` to `agent_runtime.py`

Add the new dual-mode factory alongside the existing `_create_agent()`. This lets us write and run tests before switching `run_agent_runtime()`. `_create_agent()` stays in place until Task 5.

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`

- [ ] **Step 1: Write failing tests for the new factory**

Append to `tests/unit/agent/test_agent_runtime_construction.py`:

```python
# --- New _create_interaction_agent() tests ---

def test_create_interaction_agent_user_turn_has_exactly_five_tools():
    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        tool_results=[],
    )
    tool_names = [t.name for t in agent.tools]
    assert tool_names == [
        "reminder_domain",
        "scheduling_domain",
        "timezone",
        "calendar_import",
        "url_context",
    ]


def test_create_interaction_agent_reminder_fired_has_no_tools():
    reminder_input = AgentInput(
        input_type="reminder.fired",
        conversation_id="conv-1",
        text="提醒：喝水",
        payload=ReminderFirePayload(
            fire_id="fire-1",
            reminder_id="rem-1",
            title="喝水",
            scheduled_for=datetime(2026, 5, 22, 8, 0, tzinfo=UTC),
        ),
        occurred_at=datetime(2026, 5, 22, 8, 0, tzinfo=UTC),
    )
    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=reminder_input,
        input_message="提醒：喝水",
        tool_results=[],
    )
    assert agent.tools == [] or agent.tools is None or len(agent.tools) == 0


def test_create_interaction_agent_uses_chat_response_model_role(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def fake_create_llm_model(*, role, max_tokens):
        captured.update({"role": role, "max_tokens": max_tokens})
        return object()

    monkeypatch.setattr("agno.agent.Agent", FakeAgent)
    monkeypatch.setattr(
        "agent.agno_agent.model_factory.create_llm_model",
        fake_create_llm_model,
    )

    agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        tool_results=[],
    )

    assert captured == {"role": "chat_response", "max_tokens": 2000}


def test_create_interaction_agent_sets_tool_call_limit_four(monkeypatch):
    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("agno.agent.Agent", FakeAgent)
    monkeypatch.setattr(
        "agent.agno_agent.model_factory.create_llm_model",
        lambda **kwargs: object(),
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        tool_results=[],
    )

    assert agent.kwargs["tool_call_limit"] == 4


def test_create_interaction_agent_uses_injected_session_db(monkeypatch):
    injected_db = object()

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("agno.agent.Agent", FakeAgent)
    monkeypatch.setattr(
        "agent.agno_agent.model_factory.create_llm_model",
        lambda **kwargs: object(),
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        tool_results=[],
        session_db=injected_db,
    )

    assert agent.kwargs["db"] is injected_db
    assert agent.kwargs["add_history_to_context"] is True
    assert agent.kwargs["num_history_messages"] == 20
    assert agent.kwargs["add_session_state_to_context"] is False


def test_create_interaction_agent_domain_tools_have_stop_after_tool_call_false():
    """reminder_domain and scheduling_domain must NOT stop the outer agent loop."""
    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        tool_results=[],
    )
    tool_flags = {t.name: t.stop_after_tool_call for t in agent.tools}
    assert tool_flags["reminder_domain"] is False
    assert tool_flags["scheduling_domain"] is False
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py \
    -v -k "interaction_agent"
```

Expected: `AttributeError: module 'agent.agno_agent.runtime.agent_runtime' has no attribute '_create_interaction_agent'`

- [ ] **Step 3: Add `_utility_capability_ports()` and `_create_interaction_agent()` to `agent_runtime.py`**

Add after the existing `_default_capability_ports()` function (around line 114):

```python
def _utility_capability_ports() -> dict[str, Any]:
    from agent.agno_agent.capabilities import (
        CalendarImportPort,
        TimezoneCapabilityPort,
        UrlContextPort,
    )

    return {
        "timezone": TimezoneCapabilityPort(),
        "calendar_import": CalendarImportPort(),
        "url_context": UrlContextPort(),
    }


def _create_interaction_agent(
    *,
    run_context: AgentRunContext,
    agent_input: AgentInput,
    input_message: str,
    tool_results: list[CapabilityResult],
    session_db: Any | None = None,
) -> Any:
    from agno.agent import Agent
    from agno.tools import tool

    from agent.agno_agent.model_factory import create_llm_model
    from agent.agno_agent.runtime.chat_response_instructions import (
        build_chat_response_instructions,
    )
    from agent.agno_agent.runtime.execution_agents import (
        run_reminder_domain,
        run_scheduling_domain,
    )

    # reminder.fired: tools=[] — API sends no tool schemas; model cannot call tools.
    # Rationale: tool_choice="none" is INSIDE the tools!=[] guard in Agno's OpenAI
    # adapter (models/openai/chat.py:251-262), so tools=[] is sufficient and
    # more token-efficient. event_contract injected by build_chat_response_instructions.
    if agent_input.input_type == "reminder.fired":
        final_tools = []
    else:
        utility_wrappers = build_capability_tool_wrappers(
            ports=_utility_capability_ports(),
            run_context=run_context,
            input_message=input_message,
            tool_results=tool_results,
        )
        utility_tools = [tool(name=name)(fn) for name, fn in utility_wrappers.items()]

        _reminder_guard: dict[str, Any] = {}
        _reminder_lock = asyncio.Lock()

        async def reminder_domain() -> dict[str, Any]:
            """Delegate to the reminder port for CRUD requests."""
            async with _reminder_lock:
                if "result" not in _reminder_guard:
                    _reminder_guard["result"] = await run_reminder_domain(
                        input_message=input_message,
                        run_context=run_context,
                        tool_results=tool_results,
                    )
            return _reminder_guard["result"]

        async def scheduling_domain(intent: str) -> dict[str, Any]:
            """Delegate to the scheduling execution agent.

            Args:
                intent: The scheduling action to perform. Must be one of the
                    following action names, optionally followed by known entity
                    ids from context:
                    get_user_link, reset_user_link, disable_user_link,
                    open_bookable_windows, confirm_bookable_windows,
                    query_bookable_windows, request_appointment,
                    confirm_appointment, reject_appointment, cancel_appointment,
                    list_pending_requests, block_service_link,
                    unblock_service_link, remove_service_link.
                    Include ids when known, e.g.
                    'confirm_appointment: id=abc123' or 'get_user_link'.
            """
            return await run_scheduling_domain(
                input_message=input_message,
                intent=intent,
                run_context=run_context,
                tool_results=tool_results,
            )

        domain_tools = [
            tool(name="reminder_domain", stop_after_tool_call=False)(reminder_domain),
            tool(name="scheduling_domain", stop_after_tool_call=False)(scheduling_domain),
        ]
        final_tools = domain_tools + utility_tools

    resolved_session_db = session_db or get_agent_session_db()
    return Agent(
        id="coke-interaction-agent",
        name="CokeInteractionAgent",
        model=create_llm_model(role="chat_response", max_tokens=2000),
        instructions=build_chat_response_instructions(run_context, agent_input),
        tools=final_tools,
        db=resolved_session_db,
        add_history_to_context=True,
        num_history_messages=20,
        add_session_state_to_context=False,
        tool_call_limit=4,
        markdown=False,
    )
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py \
    -v -k "interaction_agent"
```

Expected: 6 new tests PASS. All existing tests still pass.

- [ ] **Step 5: Run full agent test suite to check for regressions**

```bash
.venv/bin/python -m pytest tests/unit/agent/ -v
```

Expected: all existing tests PASS (we only added code, changed nothing).

- [ ] **Step 6: Commit**

```bash
git add agent/agno_agent/runtime/agent_runtime.py \
        tests/unit/agent/test_agent_runtime_construction.py
git commit -m "feat: add _create_interaction_agent() dual-mode factory"
```

---

## Task 5: Wire `run_agent_runtime()`, Apply Option B, Remove Dead Code, Update Tests

Switch `run_agent_runtime()` from `_create_agent()` to `_create_interaction_agent()`. Apply the one-line `visible_text` fix (Option B from spec §5.4). Remove `_create_agent()`, `_default_capability_ports()`, and the scheduling branch from `_build_capability_tool_wrapper`. Update all tests that reference removed symbols.

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`
- Modify: `tests/unit/agent/test_agent_runtime_scheduling_tools.py`
- Modify: `tests/unit/agent/test_agent_runtime_output_rules.py` (if it references `_create_agent`)

- [ ] **Step 1: Switch `run_agent_runtime()` to use `_create_interaction_agent()`**

In `agent/agno_agent/runtime/agent_runtime.py`, in `run_agent_runtime()`, change this line:

```python
        agent = _create_agent(
            run_context=run_context,
            agent_input=agent_input,
            input_message=input_message,
            tool_results=tool_results,
        )
```

to:

```python
        agent = _create_interaction_agent(
            run_context=run_context,
            agent_input=agent_input,
            input_message=input_message,
            tool_results=tool_results,
        )
```

- [ ] **Step 2: Apply Option B — prefer `final_text` when non-empty**

In `run_agent_runtime()`, change:

```python
        visible_text = _resolve_visible_text(final_text, captured_tool_results)
```

to:

```python
        # Interaction Agent's synthesized reply wins when non-empty (Option B).
        # Backward-compatible: current reminder path sets stop_after_tool_call=True
        # so final_text="" → falls back to visible_summary as before.
        visible_text = final_text or _resolve_visible_text("", captured_tool_results)
```

- [ ] **Step 3: Remove `_create_agent()` and `_default_capability_ports()` from `agent_runtime.py`**

Delete the entire `_default_capability_ports()` function (lines 92–114) and the entire `_create_agent()` function (lines 117–156).

Also remove the scheduling branch from `_build_capability_tool_wrapper`. The scheduling `if` block (lines 268–329) handles tool names in `SCHEDULING_TOOL_NAMES` and can be deleted. After deletion, the function ends at the `url_context` branch and has a final `raise ValueError`. The `raise` stays.

Also clean up imports in `agent_runtime.py` that are no longer needed after removing `_default_capability_ports()`:
- `ReminderIntentPort` — remove from the lazy import block inside `_default_capability_ports`
- `SchedulingCapabilityPort` — remove
- `SCHEDULING_TOOL_NAMES` — remove from the lazy import

Since these were inside a function's local import, they disappear with the function. No top-level import changes needed.

- [ ] **Step 4: Update `test_agent_runtime_construction.py` — fix monkeypatched `_create_agent` references**

In every test that calls `monkeypatch.setattr(agent_runtime, "_create_agent", ...)`, change `"_create_agent"` to `"_create_interaction_agent"`. These are the tests:
- `test_run_agent_runtime_returns_agent_run_result_for_no_tool_run`
- `test_run_agent_runtime_uses_captured_tool_results`
- `test_run_agent_runtime_routes_explicit_reminder_through_agent`
- `test_run_agent_runtime_fails_closed_when_agent_raises`
- `test_run_agent_runtime_times_out_when_agent_hangs`
- `test_run_agent_runtime_timeout_returns_captured_tool_summary`
- `test_reminder_fired_input_passes_raw_input_to_model`

Also update the `fake_create_agent` function name inside each test to `fake_create_interaction_agent` for clarity.

For `test_run_agent_runtime_uses_captured_tool_results` — the agent returns `content="ignored"` and there's a tool result with `visible_summary="已为你设好提醒"`. After Option B, `final_text="ignored"` (non-empty) wins. Update the assertion:

```python
# Before:
assert result.visible_messages[0].content == "已为你设好提醒"
# After:
assert result.visible_messages[0].content == "ignored"
```

Delete `test_create_agent_registers_canonical_capability_tools`, `test_create_agent_uses_chat_response_model_role`, `test_create_agent_sets_tool_call_limit`, `test_create_agent_uses_injected_session_db_and_history_settings`, `test_create_agent_resolves_default_session_db`, and `test_create_agent_stops_after_reminder_tool_call` — these tested the now-deleted `_create_agent()`. The new `_create_interaction_agent()` tests from Task 4 cover the same contracts.

Also delete `test_run_agent_runtime_captures_tool_result_into_run_result` — it monkeypatches `_default_capability_ports` (removed) and uses `build_capability_tool_wrappers` for reminder intent (the reminder path no longer goes through that wrapper). Add a replacement test that monkeypatches `run_reminder_domain` instead:

```python
@pytest.mark.asyncio
async def test_run_agent_runtime_visible_text_prefers_final_text_over_visible_summary(
    monkeypatch,
):
    """Option B: Interaction Agent's final_text wins when non-empty."""

    def fake_create_interaction_agent(**kwargs):
        kwargs["tool_results"].append(
            CapabilityResult(
                name="reminder",
                ok=True,
                content={"visible_summary": "raw port summary"},
                metadata={"durable_write": True},
            )
        )

        class _FakeAgent:
            async def arun(self, **kwargs):
                return SimpleNamespace(
                    content="character voiced reply",
                    messages=[SimpleNamespace(role="assistant", content="")],
                )

        return _FakeAgent()

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert result.visible_messages[0].content == "character voiced reply"
    assert len(result.tool_results) == 1


@pytest.mark.asyncio
async def test_run_agent_runtime_visible_text_falls_back_to_visible_summary_when_final_text_empty(
    monkeypatch,
):
    """Option B backward-compat: empty final_text → use visible_summary."""

    def fake_create_interaction_agent(**kwargs):
        kwargs["tool_results"].append(
            CapabilityResult(
                name="reminder",
                ok=True,
                content={"visible_summary": "port summary used as fallback"},
                metadata={"durable_write": True},
            )
        )

        class _FakeAgent:
            async def arun(self, **kwargs):
                return SimpleNamespace(
                    content="",
                    messages=[SimpleNamespace(role="assistant", content="")],
                )

        return _FakeAgent()

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert result.visible_messages[0].content == "port summary used as fallback"
```

- [ ] **Step 5: Update `test_agent_runtime_scheduling_tools.py` — remove dead-code tests**

Delete `test_default_runtime_exposes_all_scheduling_tools` (tests removed `_default_capability_ports()`).

The remaining tests (`test_runtime_scheduling_wrapper_dispatches_model_args`, `test_runtime_scheduling_tool_schema_exposes_top_level_arguments`, `test_runtime_scheduling_tool_schema_exposes_bookable_window_preview_shape`, `test_runtime_scheduling_wrapper_serializes_preview_model`) use `build_capability_tool_wrappers` with scheduling port names. After removing the scheduling branch from `_build_capability_tool_wrapper`, those calls will raise `ValueError: Unsupported capability tool: request_appointment`.

Replace these tests with equivalent tests that use `_make_scheduling_tool_fn` from `execution_agents.py`:

```python
# tests/unit/agent/test_agent_runtime_scheduling_tools.py
from __future__ import annotations

import pytest
from datetime import UTC, datetime
from types import SimpleNamespace

from agno.tools import tool

from agent.agno_agent.runtime.execution_agents import _make_scheduling_tool_fn
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.runtime.scheduling_types import SchedulingBookableWindowPreview


def _run_context():
    return SimpleNamespace(
        user=SimpleNamespace(id="ck_a", nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        relation=SimpleNamespace(uid="ck_a", cid="char_1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 6, 1, tzinfo=UTC),
    )


class RecordingPort:
    def __init__(self, name="get_user_link"):
        self.name = name
        self.calls = []

    def run(self, input_message, run_context, args):
        self.calls.append((input_message, run_context, args))
        return CapabilityResult(
            name=self.name,
            ok=True,
            content={"url": "https://kap.example/u/AbCdEfGhIjK_"},
        )


@pytest.mark.asyncio
async def test_scheduling_tool_fn_dispatches_model_args():
    port = RecordingPort(name="request_appointment")
    tool_results = []
    domain_results = []
    context = _run_context()

    fn = _make_scheduling_tool_fn(
        "request_appointment",
        port,
        input_message="book that slot",
        run_context=context,
        tool_results=tool_results,
        domain_results=domain_results,
    )
    result = await fn(
        target_account_id="ck_provider",
        window_instance_id="inst_1",
        reason="intro call",
    )

    assert result["ok"] is True
    assert port.calls == [
        (
            "book that slot",
            context,
            {
                "target_account_id": "ck_provider",
                "window_instance_id": "inst_1",
                "reason": "intro call",
            },
        )
    ]
    assert [item.name for item in tool_results] == ["request_appointment"]
    assert [item.name for item in domain_results] == ["request_appointment"]


def test_scheduling_tool_fn_schema_exposes_top_level_arguments():
    fn = _make_scheduling_tool_fn(
        "request_appointment",
        RecordingPort(name="request_appointment"),
        input_message="book that slot",
        run_context=_run_context(),
        tool_results=[],
        domain_results=[],
    )
    function = tool(name="request_appointment")(fn)

    assert "kwargs" not in function.parameters["properties"]
    assert "target_account_id" in function.parameters["properties"]
    assert "window_instance_id" in function.parameters["properties"]
    assert "idempotency_key" in function.parameters["properties"]


def test_scheduling_tool_fn_schema_exposes_bookable_window_preview_shape():
    fn = _make_scheduling_tool_fn(
        "confirm_bookable_windows",
        RecordingPort(name="confirm_bookable_windows"),
        input_message="confirm these windows",
        run_context=_run_context(),
        tool_results=[],
        domain_results=[],
    )
    function = tool(name="confirm_bookable_windows")(fn)

    preview_schema = function.parameters["properties"]["preview"]["anyOf"][0]
    assert preview_schema["properties"]["previewId"]["type"] == "string"
    window_schema = preview_schema["properties"]["windows"]["items"]
    assert "rule" in window_schema["properties"]
    assert window_schema["properties"]["fingerprint"]["type"] == "string"


@pytest.mark.asyncio
async def test_scheduling_tool_fn_serializes_preview_model():
    port = RecordingPort(name="confirm_bookable_windows")
    fn = _make_scheduling_tool_fn(
        "confirm_bookable_windows",
        port,
        input_message="confirm these windows",
        run_context=_run_context(),
        tool_results=[],
        domain_results=[],
    )

    await fn(
        preview=SchedulingBookableWindowPreview(
            previewId="bwp_1",
            windows=[
                {
                    "fingerprint": "fp_1",
                    "rule": {
                        "type": "weekly",
                        "days_of_week": [1],
                        "time_start": "09:00",
                        "time_end": "10:00",
                        "timezone": "Asia/Tokyo",
                        "effective_from": "2026-05-22",
                        "effective_until": None,
                    },
                }
            ],
        )
    )

    assert port.calls[0][2]["preview"]["previewId"] == "bwp_1"
    assert port.calls[0][2]["preview"]["windows"][0]["fingerprint"] == "fp_1"
```

- [ ] **Step 6: Check if `test_agent_runtime_output_rules.py` references `_create_agent`**

```bash
grep "_create_agent\|_default_capability" tests/unit/agent/test_agent_runtime_output_rules.py
```

If any matches: apply the same rename pattern (`_create_agent` → `_create_interaction_agent`).

- [ ] **Step 7: Run the full unit test suite**

```bash
.venv/bin/python -m pytest tests/unit/agent/ -v
```

Expected: all tests PASS, no references to removed functions.

- [ ] **Step 8: Run verify-surface**

```bash
zsh scripts/suggest-verification --base HEAD~1
```

Run whatever surface command is suggested.

- [ ] **Step 9: Commit**

```bash
git add agent/agno_agent/runtime/agent_runtime.py \
        tests/unit/agent/test_agent_runtime_construction.py \
        tests/unit/agent/test_agent_runtime_scheduling_tools.py
git commit -m "feat: switch run_agent_runtime to _create_interaction_agent, apply Option B"
```

---

## Task 6: Update `chat_response_instructions.py` with `_DELEGATION_BOUNDARY`

Replace `_REMINDER_TOOL_BOUNDARY` with `_DELEGATION_BOUNDARY` (covers both reminder and scheduling routing). Remove `_SCHEDULING_TOOL_BOUNDARY` (its guardrails moved to `_SCHEDULING_DOMAIN_INSTRUCTIONS_TEMPLATE` in `execution_agents.py`). Update the assembler and the tests that assert on the old boundary text.

**Files:**
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`
- Modify: `tests/unit/agent/test_chat_response_instructions.py`
- Modify: `tests/unit/agent/test_chat_response_scheduling_instructions.py`

- [ ] **Step 1: Write the failing test for `_DELEGATION_BOUNDARY`**

In `tests/unit/agent/test_chat_response_scheduling_instructions.py`, replace the entire file with:

```python
# tests/unit/agent/test_chat_response_scheduling_instructions.py
from datetime import UTC, datetime
from types import SimpleNamespace

from agent.agno_agent.runtime.chat_response_instructions import (
    build_chat_response_instructions,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload


def _run_context():
    return SimpleNamespace(
        current_time=datetime(2026, 6, 1, tzinfo=UTC),
        user=SimpleNamespace(id="ck_a", nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        platform="business",
    )


def _user_turn_input():
    return AgentInput(
        input_type="user.turn",
        conversation_id="conv_1",
        text="show my user link",
        payload=UserTurnPayload(),
        occurred_at=datetime(2026, 6, 1, tzinfo=UTC),
    )


def test_delegation_boundary_is_present():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Delegation boundary:" in text


def test_delegation_boundary_covers_reminder_routing():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Use reminder_domain only when" in text
    assert "explicitly requests creating" in text


def test_delegation_boundary_covers_scheduling_routing():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Use scheduling_domain(intent=..." in text
    assert "user-link management" in text
    assert "appointment actions" in text


def test_delegation_boundary_blocks_casual_reminder_creation():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Do not invent a reminder or scheduling action" in text
    assert "casual mention of time" in text


def test_scheduling_tool_boundary_is_removed():
    """_SCHEDULING_TOOL_BOUNDARY is now in execution_agents.py, not the Interaction Agent."""
    text = build_chat_response_instructions(_run_context(), _user_turn_input())
    assert "Scheduling tool boundary:" not in text
    assert "A-side link management" not in text
    assert "B-side appointment actions" not in text
```

- [ ] **Step 2: Run to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_chat_response_scheduling_instructions.py -v
```

Expected: `test_delegation_boundary_is_present` FAIL, `test_scheduling_tool_boundary_is_removed` FAIL (both boundaries still present).

- [ ] **Step 3: Update `chat_response_instructions.py`**

In `agent/agno_agent/runtime/chat_response_instructions.py`:

a) Add `_DELEGATION_BOUNDARY` constant after `_REMINDER_TOOL_BOUNDARY`:

```python
_DELEGATION_BOUNDARY = """Delegation boundary:
- Use reminder_domain only when the user explicitly requests creating, \
updating, cancelling, completing, or listing a reminder or notification.
- Use scheduling_domain(intent=...) only when the user explicitly requests \
user-link management, bookable-window management, or appointment actions \
(request, confirm, reject, cancel, list). Pass a precise intent string \
naming the action and any entity ids visible in conversation context.
- Use timezone, calendar_import, or url_context directly — no delegation needed.
- For any other input, respond directly without calling a domain tool.
- Do not invent a reminder or scheduling action from casual mention of time, \
plans, or activities."""
```

b) In `build_chat_response_instructions()`, change:

```python
    return "\n\n".join(
        [
            cleaned,
            _runtime_context_block(run_context, agent_input),
            _USER_VISIBLE_REPLY_BOUNDARY,
            _REMINDER_TOOL_BOUNDARY,
            _SCHEDULING_TOOL_BOUNDARY,
            f"Default user timezone: {_instruction_value(timezone)}",
        ]
    )
```

to:

```python
    return "\n\n".join(
        [
            cleaned,
            _runtime_context_block(run_context, agent_input),
            _USER_VISIBLE_REPLY_BOUNDARY,
            _DELEGATION_BOUNDARY,
            f"Default user timezone: {_instruction_value(timezone)}",
        ]
    )
```

c) Delete the `_REMINDER_TOOL_BOUNDARY` and `_SCHEDULING_TOOL_BOUNDARY` constant definitions (they are no longer referenced anywhere after this change).

- [ ] **Step 4: Update `test_chat_response_instructions.py` — fix assertion on old reminder boundary text**

The test `test_prompt_keeps_plain_schedule_statements_out_of_reminder_tool` asserts:

```python
    assert "Use the reminder tool only when" in prompt
    assert "plain plan, schedule, intention, deadline, or activity statement" in prompt
    assert "without proposing or asking whether to set a reminder" in prompt
    assert "do not turn it into a reminder clarification or reminder setup offer" in prompt
```

These strings are from `_REMINDER_TOOL_BOUNDARY` which is now deleted. Update the test to match `_DELEGATION_BOUNDARY` text:

```python
def test_prompt_keeps_plain_schedule_statements_out_of_reminder_tool():
    prompt = build_chat_response_instructions(_ctx(), _agent_input())

    assert "Delegation boundary:" in prompt
    assert "Use reminder_domain only when" in prompt
    assert "Do not invent a reminder or scheduling action" in prompt
    assert "casual mention of time" in prompt
```

Also update `test_prompt_does_not_roleplay_user_messages_as_due_reminders` if it asserts on text that is in `_REMINDER_TOOL_BOUNDARY`. Check first:

```bash
grep -n "system reminder trigger\|Only speak as if" tests/unit/agent/test_chat_response_instructions.py
```

Those strings are in `_USER_VISIBLE_REPLY_BOUNDARY`... wait, actually they're in `_REMINDER_TOOL_BOUNDARY`. Check:

```bash
grep -n "system reminder trigger\|Only speak as if" \
    agent/agno_agent/runtime/chat_response_instructions.py
```

If the strings appear only in `_REMINDER_TOOL_BOUNDARY` (now deleted), those test assertions will fail. Update them to assert on equivalent `_DELEGATION_BOUNDARY` text:

```python
def test_prompt_does_not_roleplay_user_messages_as_due_reminders():
    prompt = build_chat_response_instructions(_ctx(), _agent_input())

    assert "Delegation boundary:" in prompt
    assert "Use reminder_domain only when" in prompt
```

- [ ] **Step 5: Run all prompt tests**

```bash
.venv/bin/python -m pytest tests/unit/agent/test_chat_response_instructions.py \
    tests/unit/agent/test_chat_response_scheduling_instructions.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Run full unit suite**

```bash
.venv/bin/python -m pytest tests/unit/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add agent/agno_agent/runtime/chat_response_instructions.py \
        tests/unit/agent/test_chat_response_instructions.py \
        tests/unit/agent/test_chat_response_scheduling_instructions.py
git commit -m "feat: replace REMINDER/SCHEDULING boundaries with DELEGATION_BOUNDARY"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
.venv/bin/python -m pytest tests/unit/ -v
```

Expected: all tests PASS.

- [ ] **Run diff-aware surface check**

```bash
zsh scripts/suggest-verification --base HEAD~6
```

Run whatever surfaces are suggested.

- [ ] **Smoke: reminder CRUD path**

Start the runtime and send: "明天早上9点提醒我开会". Verify:
- `CapabilityResult.durable_write=True` in `tool_results`
- `visible_messages[0].content` contains the character-voiced confirmation (not raw `visible_summary`)
- No `error_disposition` on the `AgentRunResult`

- [ ] **Smoke: scheduling path**

Send: "帮我看看我的预约链接". Verify:
- `run_scheduling_domain()` called (check logs)
- `tool_results` contains one `CapabilityResult` from `get_user_link`
- Response contains the link URL

- [ ] **Smoke: `reminder.fired`**

Fire a reminder event. Verify:
- `tool_results` is empty (no tools called)
- `visible_messages[0].content` is non-empty delivery text
- No `error_disposition`

- [ ] **Run eval — reminder-intent benchmark (30-case subset)**

Per project memory: use the 30-case subset, not full corpus. Confirm accuracy does not regress below the GLM-5.1 baseline established 2026-05-12.

- [ ] **Final commit if not already done**

```bash
zsh scripts/review-trigger --base HEAD~6
```
