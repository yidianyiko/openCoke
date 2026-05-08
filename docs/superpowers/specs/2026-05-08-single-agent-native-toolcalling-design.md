# Single Agent + Native Tool Calling — Design Spec

**Date:** 2026-05-08  
**Status:** Approved for implementation  
**Supersedes:** `2026-04-30-coke-agent-team-redesign.md` (closed; not approved)

---

## Problem

The current runtime uses an Agno `Team` with one LLM (the manager) and zero actual LLM members.
Capabilities are Python functions, not agents. This is a fake Team.

Because the fake Team bypassed Agno's native tool calling, the codebase invented a substitute:

- A self-invented RESPONSE/REQUEST text protocol in the system prompt
- `plan_parser.py` (87 lines) to parse that protocol, silently swallowing `JSONDecodeError`
- `_is_protocol_artifact_response` (lines 196–212 of `team_runtime.py`): substring sniffing for 6 different tool call formats from other models
- Two retry loops plus a `manager_recovery_capability` that fabricates a `CapabilityResult` when the model output does not match expectations (lines 282–353)
- A `selector.py` that only ever selects `"team"` — a single-branch trampoline serving no purpose

The system prompt (`prompts/manager.py`) embeds `INSTRUCTIONS_CHAT_RESPONSE` including "Output as valid JSON" while the runtime parses plain RESPONSE/REQUEST text — a direct contradiction the model sees on every call.

In addition, four communication protocol gaps exist:

1. **Data contracts**: `context: dict[str, Any]` crosses the layer boundary — the trusted `AgentRunContext` is constructed then discarded; untrusted `raw` dict is smuggled in via `metadata={"raw": raw}`
2. **Identifier SSOT**: capability names exist as literal strings in 4+ files with no single authority
3. **Lifecycle**: no cancellation protocol — mid-stream interrupt is checked once before the runtime starts and never again
4. **Dependency direction**: capabilities import from `runtime/` — wrong direction

The Agno `Team` primitive exists for multi-LLM coordination and negotiation. Coke's runtime is a sequential pipeline of five LLMs (Orchestrator, ReminderDetect, PostAnalyze, QueryRewrite, ChatResponse). None of them delegate to each other. Paying Team's coordination overhead for a pipeline provides no benefit and forced the protocol workaround above.

---

## Decision

Replace the fake Team runtime with a single Agno `Agent`. Capabilities become Agno `FunctionTool`s. Agno's native tool calling handles dispatch. No custom protocol, no parser, no fabricated recovery.

---

## Architecture

```
agent_handler.py
    │
    │  AgentInput (typed dataclass)
    ▼
agent_runtime.py                    ← new thin entry point
    │  creates Agent, registers tools, calls agent.run()
    ▼
Agno Agent                          ← replaces Team + manager LLM
    ├── tool: reminder_intent(...)   ← CapabilityResult
    ├── tool: get_timezone(...)      ← CapabilityResult
    ├── tool: import_calendar(...)   ← CapabilityResult
    └── tool: get_url_context(...)   ← CapabilityResult
    │
    │  AgentRunResult (typed dataclass)
    ▼
agent_handler.py

PostAnalyzeWorkflow                 ← unchanged, background task
reminder_event_handler.py          ← unchanged
deferred_action_executor.py        ← unchanged (bugs fixed in same pass)
```

The Agent's system prompt is a clean chat-response prompt with no RESPONSE/REQUEST instructions. Agno handles tool dispatch natively — the model sees standard tool-use schema, not a bespoke text protocol.

---

## Communication Protocol

Every layer boundary uses a typed dataclass. No `dict[str, Any]` crosses a layer boundary after the entry point.

| Boundary | Protocol |
|---|---|
| `agent_handler` → `agent_runtime` | `AgentInput` |
| `agent_runtime` → Agno Agent | `agent.run(message, context_vars=...)` |
| Agno Agent → tool | Python function call with typed args |
| Tool → Agno Agent | `CapabilityResult` |
| `agent_runtime` → `agent_handler` | `AgentRunResult` |

**Context construction rule**: `AgentRunContext` is populated only from explicitly validated fields at the entry boundary. No passthrough of untrusted dicts via `metadata`.

**Capability identifier SSOT**: each tool's Python function name is the single authoritative identifier. No capability name literals scattered across files.

---

## What Is Deleted

| Path | Lines | Reason |
|---|---|---|
| `agent/agno_agent/runtime/team_runtime.py` | 442 | replaced by Agno Agent + tools |
| `agent/agno_agent/runtime/selector.py` | ~30 | single-branch trampoline |
| `agent/agno_agent/runtime/plan_parser.py` | 87 | RESPONSE/REQUEST parser |
| `agent/agno_agent/runtime/context/_immutability.py` | — | unused |
| `agent/agno_agent/capabilities/context_port.py` | 52 | zero production callers |
| `agent/agno_agent/adapters/output_disposition.py` | 20 | single caller; inline at callsite |
| `agent/agno_agent/prompts/manager.py` | — | RESPONSE/REQUEST system prompt |
| Tests for all of the above | — | test deleted behavior |

---

## What Is Preserved

| What | Why |
|---|---|
| `AgentInput`, `AgentRunContext`, `AgentRunResult`, `CapabilityResult` | typed entry/exit contracts |
| `OutputDisposition` logic | inlined into `agent_runtime.py` (no separate module) |
| Fail-closed error mapping | maps all unhandled exceptions to a safe user-visible error |
| `reminder_event_handler.py` | reminder fire entry point — unchanged |
| `deferred_action_executor.py` | deferred action dispatch — bugs fixed, structure unchanged |
| PostAnalyzeWorkflow | background post-analysis — unchanged |
| Hand-written fake test pattern | approved test strategy for Agno boundary |

---

## Ship-Blocker Fixes (same pass)

These bugs are fixed while rewriting the runtime entry point. They are not deferred.

1. **Silent exception swallowing** (`reminder_event_handler.py` lines 65–70, 87–92, 133–134): replace bare `except Exception:` with `logger.exception(...)` before re-raising or returning.
2. **`occurrence` scope bug** (`deferred_action_executor.py` lines 186–203): move `occurrence` binding outside the try block so `NameError` cannot shadow the original exception.
3. **Mid-stream interrupt loss** (`agent_handler.py` lines 648–664): check `is_new_message_coming_in` inside the streaming loop, not only before the runtime call.
4. **Untrusted dict smuggled into context** (`context.py` line 118–119): remove `metadata={"raw": raw}`; expose only validated fields on `AgentRunContext`.
5. **Dead guard functions never called** (`agent_handler.py` lines 440–526): delete `_guard_pending_reminder_stop_response`, `_guard_unconfirmed_reminder_response_after_prepare_timeout`, `_is_clawscale_sync_text_reply_context` — they are defined but never invoked in the production path.
6. **Env-var float parsing duplication** (`reminder_intent.py` lines 24–54): consolidate into one location; remove duplicate in `team_runtime.py` (deleted anyway).
7. **Retry prompt contradicts live schema** (`reminder_intent.py` lines 76–108): `_build_reminder_retry_input` omits `cancel` from the schema shown to the model; align prompt with actual `ReminderIntent` schema.
8. **NLP heuristics in wrong layer** (`reminder_intent.py` lines 285–329): `_should_retry_for_quoted_title_loss` belongs in the capability's validation logic, not as a free-standing NLP heuristic; refactor inline or remove if covered by schema validation.

---

## New Entry Point: `agent_runtime.py`

Replaces `team_runtime.py` and `selector.py`. Responsibilities:

1. Accept `AgentInput` — validate, construct `AgentRunContext`
2. Construct Agno `Agent` with:
   - Model from `model_factory`
   - Tools: `reminder_intent`, `get_timezone`, `import_calendar`, `get_url_context`
   - System prompt from `prompts/chat_response.py` (cleaned — no RESPONSE/REQUEST)
3. Call `agent.run(...)` — Agno handles tool dispatch natively
4. Map result to `AgentRunResult` (fail-closed on exception)
5. Return `AgentRunResult` to `agent_handler`

Agent construction is stateless per call. No global singleton. Tools are pure functions returning `CapabilityResult`.

---

## System Prompt

`prompts/manager.py` is deleted. The Agent uses `prompts/chat_response.py` with:

- No RESPONSE/REQUEST protocol instructions
- No "Output as valid JSON" directive (Agno handles tool schema natively)
- Tool descriptions live on each `@tool` function — not in the prompt

---

## Testing

- Unit tests for each tool function: given typed args, assert `CapabilityResult` shape
- Unit tests for `agent_runtime.py`: mock `agent.run()`, assert `AgentRunResult` construction and fail-closed mapping
- E2E tests: behavior parity against existing E2E suite before any prompt or logic changes
- Hand-written fake tests at the Agno boundary (existing approved pattern)

Tests for deleted modules (`team_runtime`, `selector`, `plan_parser`, `context_port`) are deleted with the modules.

---

## Out of Scope

- PostAnalyzeWorkflow restructuring
- Prompt content improvements beyond removing RESPONSE/REQUEST instructions
- New capabilities
- Gateway, bridge, or deployment changes
- Any behavior change visible to the user (parity first)

---

## Migration Sequence

1. Write `agent_runtime.py` — new thin entry point, Agent + tools wired, returns `AgentRunResult`
2. Wire tool functions — move capability logic from Port classes into Agno `@tool` functions
3. Rewrite system prompt — remove RESPONSE/REQUEST instructions, clean chat-response prompt
4. Fix 8 ship-blockers
5. Verify E2E behavior parity
6. Delete fake Team files and their tests
7. Commit

No feature flags. No compatibility shims. The old runtime is deleted once parity is verified.
