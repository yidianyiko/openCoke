# agno Full Migration Design

**Date:** 2026-05-21
**Status:** approved
**Scope:** `agent/agno_agent/` — the AI decision-making layer only

## 1. Problem Statement

The current `agent/agno_agent/` reimplements agno's own features, worse:

| What we built | What agno provides | Why ours is worse |
|---|---|---|
| `_model_input()` text injection of history + `recent_chat_history` string | `add_history_to_context=True` + `MongoDb` db | agno session history never configured; history survives only as unstructured injected text |
| `num_history_messages=15` on `reminder_detect_agent` / `post_analyze_agent`, none on main agent | `Agent(db=MongoDb(...), num_history_messages=N)` | `num_history_messages` is inert without a `db`; config exists but does nothing |
| module-level `reminder_detect_agent`, `reminder_detect_retry_agent`, `post_analyze_agent` | per-invocation Agent instances | `initialize_session()` writes a generated `session_id` back to the shared instance when none is passed, poisoning concurrent calls |
| `_extract_final_text()` parsing `RunResponse.messages` internals | `RunResponse.content` | fragile: walks message list looking for last assistant turn after tool calls |
| `orchestrator_agent` module-level singleton | removed | dead code — never called in the current runtime path |

The main chat `Agent` is already instantiated per turn in `_create_agent()` and is not the race source. The race is in the sub-agent and post-analyze singletons.

The per-turn `tool_results` list is intentionally retained — explained in §4.3.

This is a breaking refactor. There are no existing users. We cut the homegrown reimplementations and use agno properly.

## 2. Scope

**In scope:** `agent/agno_agent/` — agents, capabilities, runtime, schemas, tools, workflows.

**Not in scope (unchanged):**
- `agent/runner/` — Coke message queue, worker orchestration, lock lifecycle
- `agent/reminder/` — APScheduler runtime, reminder scheduler, fire consumer
- `connector/clawscale_bridge/` — protocol adaptation
- `gateway/` — web/API layer
- `dao/`, `entity/`, `util/` — data layer

## 3. What Stays

**`runtime/result.py` — CapabilityResult output contract**
`CapabilityResult` with `durable_write`, `visible_summary`, `requires_response_synthesis`, and `OutputDisposition` decides what gets shown to the user and validates that database writes have user-visible confirmations. Keep as-is, no carrier change.

**`_check_unconfirmed_durable_write_promise()` and `_check_durable_write_contract()`**
Runtime integrity assertions in `agent_runtime.py`. Keep. They operate on `CapabilityResult` objects extracted after `arun()` completes.

## 3a. What Is Removed (Previously Considered Preserved)

**`AgentRunContext` trust validation — removed**
`_trusted_relation_id()` and `_metadata_from_raw()` are deleted. Data provenance is trusted from the runner; the defensive checks add complexity without a real attack surface to protect. `AgentRunContext` itself is kept as a plain data container (current_time, user, character, conversation, platform); only the two validation methods are removed.

**Corrective retry state machine — removed**
The 12-branch reason-based retry in `capabilities/reminder_intent.py` is deleted. Failed reminder detection fails immediately without a retry attempt. Known trade-off: reminder intent recognition accuracy will degrade in edge cases where the model produces a recoverable structured output error. Accepted given the complexity cost.

## 4. New Architecture

### 4.1 Session Persistence

The correct agno 2.5.9 API (verified against installed source at `agno.db.mongo.MongoDb`):

```python
from agno.db.mongo import MongoDb

Agent(
    db=MongoDb(
        session_collection="agent_sessions",
        db_url=MONGO_URI,
        db_name=MONGO_DB_NAME,
    ),
    add_history_to_context=True,
    num_history_messages=20,
    add_session_state_to_context=False,
)
```

`session_id` is always `run_context.conversation.id`. agno's session store uses its own `agent_sessions` collection, separate from Coke's `inputmessages`/`outputmessages`.

**History transition:** This is a breaking refactor. Existing conversation history in Coke's `inputmessages` collection is not seeded into `agent_sessions`. First turns post-migration see an empty agno session. This is intentional — no migration script is planned.

The `MongoDb` instance is created once at worker boot (not per-turn) and shared across `Agent` instances to avoid constructing a new `MongoClient` per call.

### 4.2 Runtime Context Injection

Remove `_model_input()`. Runtime metadata moves into the system `instructions`, which is a string built per turn by extending `chat_response_instructions.py`:

```python
def build_chat_response_instructions(
    run_context: AgentRunContext,
    agent_input: AgentInput,
) -> str:
    # existing character persona instructions
    # + runtime context block:
    #   current_time, user id/nickname, character id/nickname,
    #   platform, input_type, conversation_id
    # + for reminder.fired: reminder payload contract block
    ...
```

The user message passed to `agent.arun(input=...)` is the raw user message only — no prepended metadata envelope.

`recent_chat_history` string injection is deleted. agno's `add_history_to_context=True` with a configured `db` replaces it.

### 4.3 Tool Results

The per-turn `tool_results: list[CapabilityResult]` closure pattern is retained. Each tool closes over a list created fresh at the start of `run_agent_runtime()`. This is already per-turn (not module-level) and race-free.

The retention is deliberate: `RunResponse.tools` stores the model-facing envelope (returned dict), which intentionally omits `CapabilityResult.metadata`. The runtime contract checks (`durable_write`, `visible_summary`) require `metadata`. The closure list is the only way to carry typed `CapabilityResult` objects out of the tool execution.

What changes:
- `_extract_final_text()` is deleted. Use `RunResponse.content` directly.
- `tool_wrappers.py` is merged into `agent_runtime.py`. The `_TOOL_NAMES` registry and `_build_missing_wrapper` pattern are removed.
- `_default_capability_ports()` currently registers `album`, `context_retrieve`, and `usage` ports that are never iterated by `build_capability_tool_wrappers()` (not in `_TOOL_NAMES`) and produce no agno tools. These three entries are removed as dead code. The `context_retrieve_tool` in `tools/context_retrieve_tool.py` is from the retired orchestrator architecture — also deleted.

### 4.4 post_analyze Extraction

`PostAnalyzeWorkflow` is deleted. Its logic is extracted into `runtime/post_analyze.py` as a plain `async def run_post_analyze(session_state: dict, ...) -> None` function.

**Call site stays in `agent_handler.py`.** The current gating — `AgentRunResult.post_analyze_input is not None` and the `COKE_AGENT_RUNTIME_SKIP_POST_ANALYZE` flag — lives in the runner's `_run_post_analyze_background()`. This gating must run after `AgentRunResult` is constructed and runtime contract checks complete. Using an agno post_hook is wrong: hooks fire inside `agent.arun()` before `RunResponse` returns, before contract checks run, and agno swallows hook failures. `agent_handler.py` is not touched; only the implementation it calls changes.

**Mutation path is preserved.** `run_post_analyze(session_state, ...)` mutates `session_state["relation"]` in place, identical to current `PostAnalyzeWorkflow.run()`. `agent_handler._run_post_analyze_background()` continues to do the MongoDB write (`mongo.replace_one("relations", ...)`) after the call returns. Nothing about the handler's MongoDB ownership changes.

**`post_analyze_agent` becomes per-call.** `PostAnalyzeWorkflow` calls the module-level `post_analyze_agent` singleton. After extraction, `run_post_analyze()` instantiates the agent per-call:

```python
agent = Agent(
    model=create_llm_model(role="post_analyze", max_tokens=8000),
    output_schema=PostAnalyzeResponse,
    use_json_mode=True,
    markdown=False,
)
response = await agent.arun(input=rendered_prompt, session_state=session_state)
```

No `db` on the post_analyze agent — it is a stateless single-shot structured output call.

### 4.5 Sub-agents (reminder_intent)

`reminder_detect_agent` and `reminder_detect_retry_agent` are no longer module-level singletons. They are instantiated per-invocation inside `ReminderIntentPort.run()`:

```python
detector = Agent(
    model=create_llm_model(role="reminder_detect", max_tokens=8000),
    output_schema=ReminderDetectDecision,
    structured_outputs=True,
    markdown=False,
)
await detector.arun(
    input=build_reminder_intent_input(...),
    session_state=session_state,
    session_id=run_context.conversation.id,
)
```

No `db` on sub-agents — they are stateless single-shot structured output calls. `session_state` carries the pending workflow context within the turn (already the current pattern).

The corrective retry state machine is removed (see §3a). Failed detection returns a failed `CapabilityResult` immediately.

### 4.6 Delete Dead Code

`orchestrator_agent` and `OrchestratorResponse` are never called in the current runtime. Delete both.

## 5. File Disposition

### Delete
| File | Reason |
|---|---|
| `agents/__init__.py` | module-level singletons — source of the session_id race and dead configs |
| `runtime/tool_wrappers.py` | merged into `agent_runtime.py`; `_build_missing_wrapper` removed |
| `workflows/post_analyze_workflow.py` | replaced by `runtime/post_analyze.py` |
| `schemas/orchestrator_schema.py` | orchestrator is dead code |
| `tools/context_retrieve_tool.py` | dead — from retired orchestrator architecture |

### Rewrite
| File | What changes |
|---|---|
| `runtime/agent_runtime.py` | add `MongoDb` db, `add_history_to_context`; remove `_model_input()`; replace `_extract_final_text()` with `RunResponse.content`; inline tool wrapper construction; remove `album`/`context_retrieve`/`usage` dead port entries from `_default_capability_ports()` |
| `runtime/chat_response_instructions.py` | extend to include dynamic runtime context block (current_time, user, character, platform, reminder payload) |
| `runtime/context.py` | remove `_trusted_relation_id()` and `_metadata_from_raw()`; keep `AgentRunContext` as plain data container |
| `capabilities/reminder_intent.py` | per-call Agent instantiation; delete module-level singleton imports; delete corrective retry state machine |

### Add
| File | Purpose |
|---|---|
| `runtime/session.py` | `MongoDb` instance factory; created once at worker boot, injected into `_create_agent()` |
| `runtime/post_analyze.py` | `async def run_post_analyze(session_state: dict, ...) -> None` extracted from `PostAnalyzeWorkflow`; mutates `session_state["relation"]` in place; instantiates `post_analyze_agent` per-call; agent_handler.py continues to own the MongoDB write |

### Keep Unchanged
- `runtime/result.py` — CapabilityResult contract
- `runtime/inputs.py`, `runtime/errors.py`, `runtime/_immutability.py`
- `capabilities/context_retrieve.py` — RAG + confirmed_reminders split is a future cleanup
- `schemas/reminder_detect_schema.py`, `schemas/post_analyze_schema.py`, `schemas/chat_response_schema.py`
- `prompts/`, `adapters/`, `model_factory.py`, `evals/`
- `tools/reminder_protocol/` — agno tool adapter used by the reminder capability

## 6. Turn Execution Flow After Migration

```
agent_handler._run_post_analyze_background() holds gating and MongoDB write — unchanged.

run_agent_runtime() boundary:

  run_agent_runtime(agent_input, run_context)
    ↓
  tool_results: list[CapabilityResult] = []  ← per-turn accumulator
    ↓
  agent = Agent(
      db=shared_mongo_db,          ← session history persisted across turns
      add_history_to_context=True,
      instructions=build_chat_response_instructions(run_context, agent_input),
      tools=[...closures over tool_results...],
  )
    ↓
  run_output = await agent.arun(
      input=raw_user_message,      ← no metadata envelope, just the message
      session_id=run_context.conversation.id,
  )  ← agno loads history from agent_sessions, runs LLM, calls tools, stores turn
    ↓
  final_text = run_output.content  ← no _extract_final_text() parsing
  captured_tool_results = tuple(tool_results)
    ↓
  _check_durable_write_contract(captured_tool_results)
  _check_unconfirmed_durable_write_promise(agent_input, final_text, captured_tool_results)
  _resolve_visible_text(final_text, captured_tool_results)
    ↓
  return AgentRunResult(post_analyze_input=... if visible output and no contract error)

agent_handler receives AgentRunResult
  ↓
  if result.post_analyze_input is not None and not skip_flag:
      await run_post_analyze(session_state=context)  ← replaces PostAnalyzeWorkflow.run()
      mongo.replace_one("relations", ...)            ← handler owns MongoDB write, unchanged
```

## 7. Out of Scope

**Behavior validation** is deferred. This is a breaking refactor; eval coverage will be built separately after the migration lands.

**context_retrieve RAG refactor** — splitting the RAG search from the confirmed_reminders business query is a separate cleanup.

**AgentKnowledge integration** — the embedding search in `context_retrieve.py` could eventually use agno's Knowledge system, but this is a future step.

**memo capability** — `capabilities/memo.py` is unchanged; it follows the same CapabilityResult contract.
