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

## 3. What Stays (Domain Logic, Not Framework)

These are domain invariants, not competing framework choices. They survive as thin logic on top of agno:

**`runtime/context.py` — trust boundary**
`AgentRunContext._trusted_relation_id()` validates uid/cid consistency. `_metadata_from_raw()` always returns `{}` to block untrusted fields. agno's `RunContext` has no concept of trusted vs. untrusted fields. Keep as-is.

**`runtime/result.py` — business contract**
`CapabilityResult` with `durable_write`, `visible_summary`, `requires_response_synthesis`, and `OutputDisposition` encode business rules about what to show the user and which writes are authorized. agno has no equivalent. Keep as-is.

**Corrective retry state machine in `capabilities/reminder_intent.py`**
The 12-branch reason-based retry logic is domain behavior, not a framework feature. agno's `retries` parameter retries the whole agent call, not a structured retry with reason injection. Keep the retry logic; change only how sub-agents are instantiated.

**`_check_unconfirmed_durable_write_promise()` and `_check_durable_write_contract()`**
Runtime integrity assertions in `agent_runtime.py`. Keep. They operate on `CapabilityResult` objects extracted after `arun()` completes.

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

### 4.4 post_analyze as Sequential Step

`PostAnalyzeWorkflow` is deleted. Its logic is extracted into `runtime/post_analyze.py` as a plain async function called directly from `run_agent_runtime()` — not as an agno post_hook.

**Why not agno post_hook:** agno hooks fire inside `agent.arun()` before `RunResponse` is returned, so before `AgentRunResult` is constructed and before runtime contract checks (`_check_durable_write_contract`, `_check_unconfirmed_durable_write_promise`) complete. Post-analyze should only run when the turn produces visible output and passes all contract checks — the same gating that `post_analyze_input` currently encodes. Using a post_hook would bypass this gate. Additionally, agno swallows hook failures rather than propagating them.

```python
# in run_agent_runtime(), after AgentRunResult is built:
if result.post_analyze_input is not None:
    await run_post_analyze(
        post_analyze_input=result.post_analyze_input,
        run_context=run_context,
        tool_results=captured_tool_results,
    )
```

`PostAnalyzeWorkflow.run()` mutates session_state to write back character, user, and relation updates. After extraction to `post_analyze.py`, the same mutation is written directly to MongoDB through the existing DAO calls — session_state as a mutation carrier is removed.

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

The corrective retry branches remain unchanged in logic; only the `Agent(...)` instantiation moves from module-level to per-call.

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

### Rewrite
| File | What changes |
|---|---|
| `runtime/agent_runtime.py` | add `MongoDb` db, `add_history_to_context`; remove `_model_input()`; replace `_extract_final_text()` with `RunResponse.content`; inline tool wrapper construction; call `run_post_analyze()` after `AgentRunResult` is built |
| `runtime/chat_response_instructions.py` | extend to include dynamic runtime context block (current_time, user, character, platform, reminder payload) |
| `capabilities/reminder_intent.py` | per-call Agent instantiation; delete module-level singleton imports |

### Add
| File | Purpose |
|---|---|
| `runtime/session.py` | `MongoDb` instance factory; created once at worker boot, injected into `_create_agent()` |
| `runtime/post_analyze.py` | `run_post_analyze()` async function extracted from `PostAnalyzeWorkflow`; receives run_context, tool_results, post_analyze_input; writes back to MongoDB directly |

### Keep Unchanged
- `runtime/context.py` — trust boundary
- `runtime/result.py` — CapabilityResult contract
- `runtime/inputs.py`, `runtime/errors.py`, `runtime/_immutability.py`
- `capabilities/context_retrieve.py` — RAG + confirmed_reminders split is a future cleanup
- `schemas/reminder_detect_schema.py`, `schemas/post_analyze_schema.py`, `schemas/chat_response_schema.py`
- `prompts/`, `adapters/`, `model_factory.py`, `evals/`
- `tools/reminder_protocol/` — agno tool adapter used by the reminder capability

## 6. Turn Execution Flow After Migration

```
run_agent_runtime() called with agent_input, run_context
  ↓
tool_results: list[CapabilityResult] = []  ← per-turn accumulator
  ↓
agent = Agent(
    db=shared_mongo_db,
    add_history_to_context=True,
    instructions=build_chat_response_instructions(run_context, agent_input),
    tools=[...closures over tool_results...],
)
  ↓
run_output = await agent.arun(
    input=raw_user_message,
    session_id=run_context.conversation.id,
)  ← agno loads session history from agent_sessions, runs LLM, calls tools, stores turn
  ↓
final_text = run_output.content
captured_tool_results = tuple(tool_results)
  ↓
_check_durable_write_contract(captured_tool_results)
_check_unconfirmed_durable_write_promise(agent_input, final_text, captured_tool_results)
_resolve_visible_text(final_text, captured_tool_results)
  ↓
AgentRunResult constructed
  ↓
if result.post_analyze_input:
    await run_post_analyze(run_context, captured_tool_results, result.post_analyze_input)
  ↓
return AgentRunResult
```

## 7. Out of Scope

**Behavior validation** is deferred. This is a breaking refactor; eval coverage will be built separately after the migration lands.

**context_retrieve RAG refactor** — splitting the RAG search from the confirmed_reminders business query is a separate cleanup.

**AgentKnowledge integration** — the embedding search in `context_retrieve.py` could eventually use agno's Knowledge system, but this is a future step.

**memo capability** — `capabilities/memo.py` is unchanged; it follows the same CapabilityResult contract.
