# agno Full Migration Design

**Date:** 2026-05-21
**Status:** approved
**Scope:** `agent/agno_agent/` — the AI decision-making layer only

## 1. Problem Statement

The current `agent/agno_agent/` reimplements agno's own features, worse:

| What we built | What agno provides | Why ours is worse |
|---|---|---|
| `_model_input()` text injection of history | `add_history_to_context=True` + `MongoDb` | history never actually persists; string injection has no structure |
| `num_history_messages=15` on all agents | `Agent(db=MongoDb(...))` | dead config — no `db` means no history mechanism at all |
| module-level singleton agents | per-invocation Agent instances | race condition: `initialize_session()` writes `session_id` back to the shared instance |
| external `tool_results` list side-channel | `RunResponse.tools` | bypasses agno's native tool result tracking |
| `_extract_final_text()` parsing `RunResponse.messages` | `RunResponse.content` | fragile internal parsing |
| `PostAnalyzeWorkflow` as external orchestration step | `post_hooks` | post_analyze runs outside agno's session lifecycle |
| `orchestrator_agent` module-level singleton | dead code, never called | noise |

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

Three things are domain invariants, not competing framework choices. They survive as thin logic on top of agno:

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

```python
from agno.storage.mongodb import MongoDbStorage

Agent(
    db=MongoDbStorage(
        collection_name="agent_sessions",
        db_url=MONGO_URI,
        db_name=MONGO_DB_NAME,
    ),
    add_history_to_context=True,
    num_history_messages=20,
    add_session_state_to_context=False,  # session_state is tool-specific, not for LLM context
)
```

`session_id` is always `run_context.conversation.id`. agno's session store is separate from Coke's `inputmessages`/`outputmessages` collections — it uses its own `agent_sessions` collection for LLM turn history only.

### 4.2 Runtime Context Injection

Remove `_model_input()`. Runtime metadata moves into the system `instructions`, passed as a callable that closes over `AgentRunContext`:

```python
def _build_instructions(run_context: AgentRunContext, agent_input: AgentInput) -> str:
    # static character persona + dynamic runtime context block
    # (current_time, user id/nickname, character id/nickname, platform, input_type)
    # for reminder.fired: add reminder payload contract block
    ...

Agent(
    instructions=_build_instructions(run_context, agent_input),
    ...
)
```

The user message passed to `agent.arun(input=...)` becomes the raw user message only — no prepended metadata envelope.

`recent_chat_history` string injection is deleted. agno's `add_history_to_context=True` provides actual session history from the `agent_sessions` collection.

### 4.3 Tool Results

The per-turn `tool_results: list[CapabilityResult]` closure pattern is retained — tools close over a list created fresh each turn in `run_agent_runtime()`. This is already per-turn (not module-level) and thread-safe.

What changes:
- `_extract_final_text()` is deleted. Use `RunResponse.content` directly.
- `tool_wrappers.py` is merged into `agent_runtime.py` — the `_TOOL_NAMES` registry and `_build_missing_wrapper` pattern are removed.

### 4.4 post_analyze as Post-Hook

`PostAnalyzeWorkflow` is deleted as a standalone orchestration step. `post_analyze` runs as an agno `post_hook` registered on the main agent:

```python
async def _post_analyze_hook(agent: Agent, run_response: RunResponse) -> None:
    # same logic as PostAnalyzeWorkflow.run(), but triggered by agno
    ...

Agent(post_hooks=[_post_analyze_hook], ...)
```

The hook receives `agent.session_state`. During the turn, each tool writes its `CapabilityResult` into `session_state["_capability_results"]` in addition to the per-turn accumulator list. The post_hook reads from there. This is the one deliberate use of `session_state` as a within-turn side channel — scoped to a single `session_id` and therefore safe.

### 4.5 Sub-agents (reminder_intent)

`reminder_detect_agent` and `reminder_detect_retry_agent` are no longer module-level singletons. They are instantiated per-invocation inside `ReminderIntentPort.run()`:

```python
detector = Agent(
    model=create_llm_model(role="reminder_detect", max_tokens=8000),
    output_schema=ReminderDetectDecision,
    structured_outputs=True,
    ...
)
await detector.arun(
    input=build_reminder_intent_input(...),
    session_state=session_state,
    session_id=run_context.conversation.id,
)
```

No `db` on sub-agents — they are stateless single-shot structured output calls. No history needed. `session_state` carries the pending workflow context within the turn.

The corrective retry branches remain unchanged in logic; only the `Agent(...)` instantiation moves from module-level to per-call.

### 4.6 Delete Dead Code

`orchestrator_agent` and `OrchestratorResponse` are never called in the current runtime. Delete both.

## 5. File Disposition

### Delete
| File | Reason |
|---|---|
| `agents/__init__.py` | module-level singletons — the source of the race condition and dead configs |
| `runtime/tool_wrappers.py` | absorbed into `agent_runtime.py`; `_build_missing_wrapper` removed |
| `workflows/post_analyze_workflow.py` | replaced by agno post_hook in `runtime/post_hooks.py` |
| `schemas/orchestrator_schema.py` | orchestrator is dead code |

### Rewrite
| File | What changes |
|---|---|
| `runtime/agent_runtime.py` | add MongoDb db, add_history_to_context; remove _model_input(); replace _extract_final_text() with RunResponse.content; inline tool wrapper construction |
| `capabilities/reminder_intent.py` | per-call Agent instantiation; delete module-level imports of singletons |

### Add
| File | Purpose |
|---|---|
| `runtime/session.py` | agno MongoDb session config factory (db_url, db_name, collection) |
| `runtime/post_hooks.py` | post_analyze as agno post_hook, extracted from PostAnalyzeWorkflow |

### Keep Unchanged
- `runtime/context.py` — trust boundary
- `runtime/result.py` — CapabilityResult contract
- `runtime/inputs.py`, `runtime/errors.py`, `runtime/_immutability.py`
- `runtime/chat_response_instructions.py` — will be extended to include runtime context block
- `capabilities/context_retrieve.py` — keep as-is for now; RAG + confirmed_reminders split is a future cleanup
- `schemas/reminder_detect_schema.py`, `schemas/post_analyze_schema.py`
- `schemas/chat_response_schema.py`
- `prompts/`, `adapters/`, `model_factory.py`
- `evals/`
- `tools/reminder_protocol/` — still the agno tool adapter used by the capability

## 6. Key Integration Point: CapabilityResult Extraction

After migration, the flow is:

```
agent.arun(input=user_message, session_id=conversation.id)
  → tools execute, each closing over per-turn tool_results list
  → RunResponse returned
  → final_text = run_response.content
  → tool_results already populated by tool closures
  → _check_durable_write_contract(tool_results)
  → _check_unconfirmed_durable_write_promise(final_text, tool_results)
  → _resolve_visible_text(final_text, tool_results)
  → AgentRunResult constructed
  → post_hook fires (post_analyze)
```

The per-turn `tool_results` list remains the extraction mechanism. This is not a side-channel in the harmful sense — it's a per-turn accumulator, not shared mutable state.

## 7. Out of Scope

**Behavior validation** is deferred. This is a breaking refactor; eval coverage will be built separately after the migration lands.

**context_retrieve RAG refactor** — splitting the RAG search from the confirmed_reminders business query is a separate cleanup, not part of this migration.

**AgentKnowledge integration** — the embedding search in `context_retrieve.py` could eventually use agno's Knowledge system, but this is a future step.

**memo capability** — `capabilities/memo.py` is unchanged; it follows the same CapabilityResult contract and doesn't need migration now.
