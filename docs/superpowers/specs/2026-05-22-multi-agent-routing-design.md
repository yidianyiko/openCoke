# Multi-Agent Routing Architecture Design

**Date:** 2026-05-22  
**Status:** Revised v4 — reminder domain simplified to direct port call  
**Author:** YDYK + Claude

---

## 1. Problem Statement

Coke's current runtime registers **18 tools** on a single LLM agent
(`reminder_intent` + 14 scheduling tools + timezone + calendar_import +
url_context). Research (Manus/Poke internal reports; empirical benchmarks)
shows LLM tool-selection accuracy degrades sharply beyond ~6 tools:
accuracy drops from 43 % at 4 tools to ~2 % at 51 tools. The flat tool
list also makes prompt-boundary guardrails harder to write because every
domain must be described in the same system message.

**Goal:** Keep tool-selection accuracy high by routing through a small
Interaction Agent and delegating deep execution to focused Execution
Agents — following the Poke "Interaction + Execution" pattern — while
preserving every existing runtime contract.

---

## 2. Current Architecture

```
user.turn / reminder.fired
        │
        ▼
  run_agent_runtime()
        │
        ▼
  CokeSingleAgent  (18 tools)
  ┌─────────────────────────────────────┐
  │ reminder_intent                     │
  │ timezone / calendar_import          │
  │ url_context                         │
  │ get_user_link / reset_user_link     │
  │ disable_user_link                   │
  │ open/confirm/query_bookable_windows │
  │ request/confirm/reject/cancel_appt  │
  │ list_pending_requests               │
  │ block/unblock/remove_service_link   │
  └─────────────────────────────────────┘
        │
        ▼
  response → user
```

Key runtime properties today:
- `tool_call_limit=4`; `stop_after_tool_call=True` for `reminder_intent`
- `add_history_to_context=True`, `num_history_messages=20`
- All tools share one `tool_results: list[CapabilityResult]` via closure
- Two post-execution contracts: `durable_write_contract` and
  `unconfirmed_durable_write_promise`
- `reminder.fired` handled inline — system prompt injects `event_contract:
  system reminder delivery` + reminder metadata; agent generates delivery text
  with **no tool calls**

---

## 3. Target Architecture

```
user.turn / reminder.fired
        │
        ▼
  run_agent_runtime()
        │
        ▼
  _create_interaction_agent()  ← same factory for both input types
  ┌──────────────────────────────────────────────────────────────┐
  │  user.turn  → tools = [reminder_domain, scheduling_domain,  │
  │               timezone, calendar_import, url_context]  (5)  │
  │                                                              │
  │  reminder.fired → tools = []                                 │
  │  (event_contract already injected by build_chat_..();        │
  │   model generates delivery text; no tools can be called)     │
  └──────────────────────────────────────────────────────────────┘
        │
        │  reminder_domain call →  ReminderExecutionAgent (1 tool)
        │  scheduling_domain call → SchedulingExecutionAgent (14 tools)
        │
        ▼
  response → user
```

**LLM call budget per scenario (corrected):**

| Scenario | Interaction | Execution | Detector | Total |
|----------|-------------|-----------|----------|-------|
| Pure chat (`user.turn`) | 1 | 0 | 0 | **1** |
| Reminder CRUD (`user.turn`) | 1 | 0 | 1 (direct port call) | **2** |
| Scheduling action (`user.turn`) | 1 | 1 | 0 | **2** |
| Reminder delivery (`reminder.fired`) | 1 (tools=[]) | 0 | 0 | **1** |

> Reminder requests cost 2 LLM calls: Interaction Agent + detector inside
> `ReminderIntentPort`. `run_reminder_domain()` calls the port directly —
> no intermediate Execution Agent LLM call. This matches the current
> single-agent call count (1 chat + 1 detector).

---

## 4. Agno Source Findings (governs all design decisions below)

> All findings are from Agno 2.5.9 installed at
> `.venv/lib/python3.12/site-packages/agno/`.

### 4.1 `tool_choice` is inside the `tools != []` block

`models/openai/chat.py:251-262`:
```python
if tools is not None and len(tools) > 0:
    request_params["tools"] = tools
    if tool_choice is not None:
        request_params["tool_choice"] = tool_choice
```

**Implication:** `tool_choice="none"` is only sent to the API when the tool
list is non-empty. When `tools=[]`, neither tools nor tool_choice is sent.
For `reminder.fired`, passing `tools=[]` is sufficient and more efficient
than `tool_choice="none"` (saves token budget for 5 tool schemas).

### 4.2 Nested `arun()` safety — run_id is per-call UUID

`agent/_run.py:2483`:
```python
run_id = run_id or str(uuid4())
```

Every `arun()` call generates a fresh UUID. The global cancellation registry
(`run/cancel.py`) is keyed by `run_id`, not agent id. Two concurrent
`arun()` calls (outer Interaction + inner Execution) register different
run_ids and cannot cancel each other. **Nested `arun()` is safe.**

### 4.3 `db=None` — stateless execution agents have no persistence side-effects

`agent/_storage.py:298`:
```python
if agent.db is not None and agent.team_id is None and agent.workflow_id is None:
    agent_session = read_session(agent, session_id=session_id, user_id=user_id)
```

When `db=None`, session reads and writes are skipped. An in-memory
`AgentSession` is created for the run but never persisted. **Execution
Agents with `db=None` are truly stateless.**

### 4.4 `asyncio.gather()` parallel tool execution — confirmed concurrency risk

`models/base.py:2613-2615`:
```python
results = await asyncio.gather(
    *(self.arun_function_call(fc) for fc in function_calls_to_run), return_exceptions=True
)
```

When the model emits multiple tool calls in one response, Agno runs them
concurrently. This IS a real write-hazard on the shared `tool_results` list.

**Mitigation (applied in this design):** Each Execution Agent call maintains
its own `domain_results: list[CapabilityResult]` locally. Domain results
are read from `domain_results`, not from `tool_results[-1]`. The shared
`tool_results` only needs append-safety; CPython list `append` is GIL-safe,
and the contract checks iterate all items so ordering is irrelevant.

### 4.5 `stop_after_tool_call` — triggers AFTER `gather()` completes

`models/base.py:810`:
```python
if any(m.stop_after_tool_call for m in function_call_results):
    break
```

The check runs after all parallel tool calls finish. `stop_after_tool_call`
on `reminder_intent` inside the Execution Agent breaks the nested agent's
model loop (correct) and has no effect on the outer Interaction Agent's loop.

---

## 5. Component Responsibilities

### 5.1 `_create_interaction_agent()` — single factory, dual mode

The factory already receives `agent_input`. For `reminder.fired` it passes
`tools=[]`; for `user.turn` it registers 5 tools. Same system prompt builder,
same model, same session config for both.

```python
def _create_interaction_agent(*, run_context, agent_input, input_message,
                               tool_results, session_db=None) -> Agent:
    ...
    if agent_input.input_type == "reminder.fired":
        # event_contract injected by build_chat_response_instructions();
        # tools=[] means the API receives no tool schemas → no tool calls possible
        final_tools = []
    else:
        final_tools = domain_tools + utility_tools  # 5 tools

    return Agent(
        ...
        tools=final_tools,
        tool_call_limit=4,
        add_history_to_context=True,
        num_history_messages=20,
    )
```

`run_agent_runtime()` has **no branching** — it calls `_create_interaction_agent()`
for both input types and the same timeout/contract logic applies.

**`reminder.fired` history policy (intentional, matches current behavior):**
`add_history_to_context=True` and `db=resolved_session_db` are kept for
`reminder.fired`. The delivery text is written into the same Agno conversation
session as `user.turn` messages, matching current single-agent behavior. Future
turns see the delivery as a prior assistant message — this is correct so the
model can refer to "the reminder I just sent you." If this policy changes,
`add_history_to_context=False` on the fired path would be the switch.

### 5.2 Reminder domain — direct port call, no Execution Agent

`run_reminder_domain()` calls `ReminderIntentPort.run()` directly — no
intermediate Agno Agent. This saves one LLM call (reminder CRUD: 2 total
instead of 3) with identical behavior.

`ReminderIntentPort` already handles all classification outcomes:
- **有意图** → 执行 CRUD，返回 `durable_write=True` 的 `CapabilityResult`
- **需澄清** → 返回澄清问题，`durable_write=False`
- **无提醒意图** → 返回 `_no_action_discussion_result()`

Interaction Agent 的 `_DELEGATION_BOUNDARY` 是第一层过滤（prompt 级），
detector 是第二层保险（模型级）。两层职责不重叠，无需额外 Agent 中转。

### 5.3 SchedulingExecutionAgent

- Runs 14 scheduling tools. Stateless (`db=None`, `add_history_to_context=False`).
- Receives `intent: str` from Interaction Agent — required because without
  conversation history, the model cannot resolve follow-ups ("confirm that one")
  from `input_message` alone. The Interaction Agent extracts entity ids from
  its own history and encodes them in `intent`.
- `tool_call_limit=4` within this agent.

### 5.4 `_resolve_visible_text()` and character voice — critical contract

`agent_runtime.py:371-390` decides what text the user sees:

```python
def _resolve_visible_text(final_text, tool_results):
    if tool_results and any(r.requires_response_synthesis for r in tool_results):
        if final_text:
            return final_text          # Interaction Agent synthesis wins
    summaries = [r.visible_summary for r in tool_results if r.visible_summary]
    if summaries:
        return "\n".join(summaries)    # raw port summary wins
    if not tool_results:
        return final_text
    return ""
```

**Problem:** Reminder and scheduling `CapabilityResult` objects have
`requires_response_synthesis=False` by default (not set in port metadata).
After the Interaction Agent generates `final_text` (character-voiced reply),
`_resolve_visible_text()` falls through to `visible_summary` — discarding
the synthesis. Character voice is lost.

**Fix — two options:**

*Option A (preferred):* Capability ports used in Execution Agents set
`metadata={"durable_write": ..., "requires_response_synthesis": True}`.
This requires updating `ReminderIntentPort` result metadata and
`SchedulingCapabilityPort` result metadata. No change to `run_agent_runtime()`.

*Option B (alternative):* In `run_agent_runtime()`, after Interaction Agent
completes, prefer `final_text` when non-empty without checking the flag:

```python
# Multi-agent path: Interaction Agent always produces the canonical reply
visible_text = final_text or _resolve_visible_text("", captured_tool_results)
```

This is backward-compatible: current `reminder_intent` with
`stop_after_tool_call=True` produces empty `final_text`, so fallback to
`visible_summary` still applies. Multi-agent path produces non-empty
`final_text` → used directly.

**Decision:** Option B avoids port changes and preserves single-agent backward
compatibility. Add it as an explicit step in the `run_agent_runtime()` diff.

### 5.5 Contract preservation table

| Contract | Where enforced | Change |
|----------|---------------|--------|
| `durable_write_contract` | `run_agent_runtime()` after `agent.arun()` completes | none |
| `unconfirmed_durable_write_promise` | `run_agent_runtime()` on `final_text`; already skipped for `reminder.fired` at `agent_runtime.py:427` | none |
| `reminder.fired` no-CRUD | `tools=[]` — API-level guarantee; no tool schema sent | **improved** (was prompt-only) |
| `stop_after_tool_call` for reminder_intent | ReminderExecutionAgent wrapper | same semantics, new location |
| `tool_call_limit=4` | Interaction Agent unchanged; also set on Execution Agents | unchanged |
| Character voice | `final_text` preferred when non-empty (Option B) | **new explicit rule** |

---

## 6. File Change Inventory

| File | Change type | Description |
|------|------------|-------------|
| `agent/agno_agent/runtime/scheduling_types.py` | **create** | `SchedulingBookableWindowPreview`, `_compact_scheduling_args()` extracted from `agent_runtime.py` |
| `agent/agno_agent/runtime/execution_agents.py` | **create** | `run_reminder_domain()`, `run_scheduling_domain()` |
| `agent/agno_agent/runtime/agent_runtime.py` | **modify** | `_create_agent()` → `_create_interaction_agent()` (dual-mode); `_utility_capability_ports()`; domain tool wrappers; import from `scheduling_types.py` |
| `agent/agno_agent/runtime/chat_response_instructions.py` | **modify** | Replace `_REMINDER_TOOL_BOUNDARY` + remove `_SCHEDULING_TOOL_BOUNDARY` → `_DELEGATION_BOUNDARY` only |

**Why `scheduling_types.py`:** `execution_agents.py` needs `SchedulingBookableWindowPreview`
(type annotation) and `_compact_scheduling_args()` (arg normalization). Importing these
from `agent_runtime.py` creates a coupling trap — any refactor of `agent_runtime.py`
breaks `execution_agents.py` silently. Extracting them to a thin shared module
(`scheduling_types.py`) breaks the circular dependency and makes both files stable.

---

## 7. Prompt Boundary Changes

### 7.1 `_DELEGATION_BOUNDARY` (replaces `_REMINDER_TOOL_BOUNDARY`)

```
Delegation boundary:
- Use reminder_domain only when the user explicitly requests creating,
  updating, cancelling, completing, or listing a reminder or notification.
- Use scheduling_domain(intent=...) only when the user explicitly requests
  user-link management, bookable-window management, or appointment actions
  (request, confirm, reject, cancel, list). Pass a precise intent string
  naming the action and any entity ids visible in conversation context.
- Use timezone, calendar_import, or url_context directly — no delegation needed.
- For any other input, respond directly without calling a domain tool.
- Do not invent a reminder or scheduling action from casual mention of time,
  plans, or activities.
```

### 7.2 `_SCHEDULING_TOOL_BOUNDARY` — removed from Interaction Agent, moved to Execution Agent

**BLOCKER fixed:** `_SCHEDULING_TOOL_BOUNDARY` currently describes how to use direct
scheduling tools (get_user_link, confirm_appointment, etc.). In the new design,
the Interaction Agent has no direct scheduling tools — only `scheduling_domain(intent)`.
Leaving `_SCHEDULING_TOOL_BOUNDARY` in the Interaction Agent's prompt would confuse
the model with references to tools that don't exist and contradict `_DELEGATION_BOUNDARY`.

Change in `build_chat_response_instructions()`:
```python
# Before:
return "\n\n".join([
    cleaned,
    _runtime_context_block(run_context, agent_input),
    _USER_VISIBLE_REPLY_BOUNDARY,
    _REMINDER_TOOL_BOUNDARY,        # → replaced by _DELEGATION_BOUNDARY
    _SCHEDULING_TOOL_BOUNDARY,      # → removed
    f"Default user timezone: ...",
])

# After:
return "\n\n".join([
    cleaned,
    _runtime_context_block(run_context, agent_input),
    _USER_VISIBLE_REPLY_BOUNDARY,
    _DELEGATION_BOUNDARY,           # covers both reminder and scheduling routing
    f"Default user timezone: ...",
])
```

`_SCHEDULING_TOOL_BOUNDARY`'s guardrails (confirm before irreversible actions,
don't reveal raw user-link codes, etc.) move into `_SCHEDULING_DOMAIN_INSTRUCTIONS_TEMPLATE`
in `execution_agents.py`, where the SchedulingExecutionAgent can apply them
when actually using the tools.

### 7.3 `_runtime_context_block()` — unchanged

`ReminderFirePayload` injection block stays. It is used for both the current
single-agent path and the new Interaction Agent path for `reminder.fired`.

---

## 8. New File: `execution_agents.py`

```python
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

from agno.agent import Agent
from agno.tools import tool

from agent.agno_agent.capabilities import ReminderIntentPort
from agent.agno_agent.capabilities.scheduling import SCHEDULING_TOOL_NAMES
from agent.agno_agent.model_factory import create_llm_model
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult

logger = logging.getLogger(__name__)

_SCHEDULING_DOMAIN_INSTRUCTIONS_TEMPLATE = (
    "You are the scheduling execution worker. The intent is: {intent}. "
    "Call exactly one scheduling tool that matches the intent. "
    "Output only the tool call — do not generate user-visible text."
)


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
    """Rich model-facing dict including visible_summary and synthesis_context."""
    return {
        "name": result.name,
        "ok": result.ok,
        "content": dict(result.content),
        "visible_summary": result.visible_summary,
        "synthesis_context": result.synthesis_context,
        "error": result.error,
    }


# ---------------------------------------------------------------------------
# Reminder domain — direct port call, no intermediate Agent
# ---------------------------------------------------------------------------

async def run_reminder_domain(
    *,
    input_message: str,
    run_context: AgentRunContext,
    tool_results: list[CapabilityResult],
) -> dict[str, Any]:
    """Call ReminderIntentPort directly; append result into shared tool_results.

    No intermediate Agno Agent. ReminderIntentPort handles all outcomes:
    - CRUD intent → executes, durable_write=True
    - Clarification needed → returns clarification, durable_write=False
    - No reminder intent → returns no_action_discussion_result

    Saves one LLM call vs. going through a ReminderExecutionAgent.
    """
    port = ReminderIntentPort()
    result = await _run_port(
        port,
        input_message=input_message,
        run_context=run_context,
        args={},
    )
    tool_results.append(result)  # GIL-safe append; contract checks iterate all items
    return _capability_envelope(result)


# ---------------------------------------------------------------------------
# Scheduling domain
# ---------------------------------------------------------------------------

def _make_scheduling_tool_fn(
    tool_name: str,
    port: Any,
    *,
    input_message: str,
    run_context: AgentRunContext,
    tool_results: list[CapabilityResult],
    domain_results: list[CapabilityResult],
) -> Any:
    from agent.agno_agent.runtime.agent_runtime import (
        SchedulingBookableWindowPreview,
        _compact_scheduling_args,
    )

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
            args=_compact_scheduling_args({
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
            }),
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
    """Run SchedulingExecutionAgent; append result into shared tool_results.

    `intent` is a structured string from the Interaction Agent, e.g.
    'get_user_link' or 'confirm_appointment: id=abc123'.
    Required because the Execution Agent has no conversation history.
    """
    from agent.agno_agent.capabilities import SchedulingCapabilityPort

    domain_results: list[CapabilityResult] = []
    ports = {name: SchedulingCapabilityPort(tool_name=name) for name in SCHEDULING_TOOL_NAMES}
    tools = [
        tool(name=name)(
            _make_scheduling_tool_fn(
                name, port,
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
        db=None,          # stateless: no session persistence (see §4.3)
        add_history_to_context=False,
        tool_call_limit=4,
        markdown=False,
    )
    await agent.arun(input=input_message)
    last = domain_results[-1] if domain_results else None
    if last is None:
        return {
            "ok": False, "domain": "scheduling",
            "visible_summary": None, "synthesis_context": None,
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

---

## 9. Modified: `agent_runtime.py` — key diffs

### 9.1 `_utility_capability_ports()` (new helper)

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
```

### 9.2 `_create_interaction_agent()` — dual-mode, no branching in caller

```python
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

    # reminder.fired: tools=[] — API sends no tool schemas, model cannot call tools.
    # Rationale: tool_choice="none" is INSIDE the tools!=[] guard in Agno's OpenAI
    # model (models/openai/chat.py:251-262), so tools=[] is both sufficient and
    # more token-efficient. event_contract handles delivery via prompt.
    if agent_input.input_type == "reminder.fired":
        final_tools = []
    else:
        # Utility tools — direct, unchanged semantics
        utility_wrappers = build_capability_tool_wrappers(
            ports=_utility_capability_ports(),
            run_context=run_context,
            input_message=input_message,
            tool_results=tool_results,
        )
        utility_tools = [tool(name=name)(fn) for name, fn in utility_wrappers.items()]

        # Domain delegation tools
        # reminder_domain: lock guards against duplicate parallel calls from model.
        # run_reminder_domain() calls ReminderIntentPort directly (no nested Agent).
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

### 9.3 `run_agent_runtime()` — complete diff (one line changed)

Only the `visible_text` assignment changes. All other logic is preserved verbatim.

```python
async def run_agent_runtime(
    *,
    agent_input: AgentInput,
    run_context: AgentRunContext,
) -> AgentRunResult:
    tool_results: list[CapabilityResult] = []
    try:
        if agent_input.input_type not in _SUPPORTED_INPUT_TYPES:
            raise ValueError(f"Unsupported agent input type: {agent_input.input_type}")

        input_message = _input_message(agent_input)
        agent = _create_interaction_agent(          # ← renamed from _create_agent
            run_context=run_context,
            agent_input=agent_input,
            input_message=input_message,
            tool_results=tool_results,
        )
        timeout_seconds = _agent_runtime_timeout_seconds()
        try:
            run_output = await asyncio.wait_for(
                agent.arun(
                    input=input_message,
                    session_id=run_context.conversation.id,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return _timeout_result(
                agent_input=agent_input,
                run_context=run_context,
                input_message=input_message,
                timeout_seconds=timeout_seconds,
                tool_results=tool_results,
            )

        final_text = _string_content(getattr(run_output, "content", None))
        unconfirmed_promise_error = _check_unconfirmed_durable_write_promise(
            agent_input=agent_input,
            final_text=final_text,
            tool_results=tool_results,
        )
        captured_tool_results = tuple(tool_results)
        durable_write_error = _check_durable_write_contract(captured_tool_results)
        runtime_contract_error = durable_write_error or unconfirmed_promise_error

        # ↓ ONLY CHANGED LINE ↓
        # Before: visible_text = _resolve_visible_text(final_text, captured_tool_results)
        # After:  prefer Interaction Agent's synthesized reply when non-empty.
        # Backward-compatible: current reminder path sets stop_after_tool_call=True
        # so final_text="" → falls back to visible_summary as before.
        visible_text = final_text or _resolve_visible_text("", captured_tool_results)
        # ↑ ONLY CHANGED LINE ↑

        if runtime_contract_error is not None:
            visible_text = ""
        visible_messages = (
            (VisibleMessage(message_type="text", content=visible_text),)
            if visible_text
            else ()
        )

        if visible_messages and runtime_contract_error is None:
            return AgentRunResult(
                visible_messages=visible_messages,
                post_analyze_input={
                    "input_message": input_message,
                    "message_source": _message_source(agent_input, run_context),
                },
                tool_results=captured_tool_results,
                metrics={"capability_result_count": len(captured_tool_results)},
                trace={"runtime": "agent"},
                output_disposition=OutputDisposition(status="ok"),
            )

        return AgentRunResult(
            visible_messages=visible_messages,
            post_analyze_input=None,
            tool_results=captured_tool_results,
            metrics={"capability_result_count": len(captured_tool_results)},
            trace={"runtime": "agent", "status": "empty_output"},
            output_disposition=OutputDisposition(status="empty"),
            error_disposition=runtime_contract_error,
        )
    except UnknownToolError as exc:
        return _unknown_tool_result(exc, tool_results)
    except Exception:
        return _exception_result(tool_results)
```

---

## 10. Concurrency Analysis

| Risk | Source | Mitigation |
|------|--------|-----------|
| Parallel tool appends to `tool_results` | `asyncio.gather()` in `models/base.py:2613` | CPython list append is GIL-safe; contract checks iterate all items, ordering irrelevant |
| Wrong `tool_results[-1]` in reminder envelope | `gather()` interleaving | `run_reminder_domain()` calls port directly and returns the result immediately — no list index needed |
| Wrong `tool_results[-1]` in scheduling envelope | `gather()` interleaving | SchedulingExecutionAgent reads from local `domain_results`, not `tool_results[-1]` |
| Duplicate `reminder_domain` calls | Model emits 2 parallel calls | `_reminder_lock` + `_reminder_guard` in outer closure |
| Nested `arun()` cross-cancellation | Shared cancellation registry (scheduling only) | Each `arun()` gets `uuid4()` run_id; registry is keyed by run_id |
| Scheduling agent session leaks | `db=None` SchedulingExecutionAgent | `_storage.py:298` skips DB when `db=None`; in-memory only |

---

## 11. Open Questions

1. **Scheduling follow-up resolution quality.** The `intent` parameter requires
   the Interaction Agent to extract entity ids from its conversation history
   (e.g., "confirm that appointment" → `confirm_appointment: id=abc123`). This
   is a prompt-quality dependency. Must be validated in eval before rollout.

2. **Agno nested `arun()` — background lifecycle overhead.** Each nested
   `arun()` starts Agno's memory/learning background tasks even if disabled in
   config. No correctness risk (§4.2 confirms run_id isolation), but adds
   latency. Measure under load.

3. **`parallel_tool_calls` Agno option.** Agno does not currently expose a
   `parallel_tool_calls=False` flag on `Agent`. The shared-list append risk is
   mitigated by local `domain_results` lists, but belt-and-suspenders disabling
   would require an Agno upstream change or a per-call `arun()` wrapper.

---

## 12. Alternatives Considered

### A. `tool_choice="none"` instead of `tools=[]` for `reminder.fired`

Pros: keeps tool schemas registered (future introspection).  
Cons: still sends all 5 tool schemas to the API on every fired event —
wasted tokens. Also `tool_choice` only takes effect inside the `tools != []`
guard (`models/openai/chat.py:261`) so combining with `tools=[]` is a no-op.
`tools=[]` is strictly better.

### B. Separate `_run_reminder_fired_route()` helper

Separates the route at `run_agent_runtime()` level rather than inside the
factory. No behavioral difference; adds a branch point in the outer function
and a new delivery agent/function. Increases surface area for no benefit.
Rejected in favor of the single-factory dual-mode approach.

### C. Flat tool list with better prompt guardrails (current approach + scheduling)

Zero refactor cost but accuracy degrades at 18 tools. Rejected.

### D. Manus-style logits masking

Not applicable: SiliconFlow API does not expose inference internals. Rejected.

---

## 13. Verification Plan

1. **Unit tests** — `tests/unit/runtime/test_execution_agents.py`:
   - `run_reminder_domain()` calls `ReminderIntentPort.run()` directly (no Agent instantiated)
   - `run_reminder_domain()` appends exactly one `CapabilityResult` to shared `tool_results`
   - `run_reminder_domain()` returns `{ok, visible_summary, synthesis_context, content, error}`
   - `run_scheduling_domain()` appends to shared `tool_results` AND to local `domain_results`
   - `run_scheduling_domain()` returns same envelope shape
   - Duplicate `reminder_domain` calls at Interaction Agent level return cached result (lock test)

2. **Unit tests** — `tests/unit/runtime/test_agent_runtime.py`:
   - `reminder.fired` → `_create_interaction_agent()` returns agent with `tools=[]`
   - `user.turn` → agent has exactly 5 tools
   - `reminder.fired` produces `AgentRunResult` with empty `tool_results`
   - Both input types pass through same timeout/contract logic

3. **Eval** — reminder-intent benchmark (30-case subset per project memory):
   accuracy must not regress below current GLM-5.1 baseline.

4. **Smoke test** — reminder CRUD: "remind me at 3pm" → `CapabilityResult.durable_write=True`,
   `visible_summary` non-empty.

5. **Smoke test** — scheduling: "show me my booking link" → `get_user_link`
   called inside `run_scheduling_domain()`, result in `tool_results`.

6. **Smoke test** — `reminder.fired`: fire a reminder event → delivery text
   produced, `tool_results` empty, no `error_disposition`.

7. **Delivery quality comparison** — `reminder.fired` with `tools=[]` (new) vs
   current 18-tool path: fire the same reminder payload on both paths, compare
   delivery wording. Confirm no behavioral regression from removing tool schemas.
   (Some models respond differently when no tool affordances are present.)

8. **Character voice regression** — send a reminder CRUD request, confirm the
   user-visible reply uses the Interaction Agent's `final_text` (character
   voice), not the raw port `visible_summary`. Verify via the Option B change
   in `run_agent_runtime()`.
