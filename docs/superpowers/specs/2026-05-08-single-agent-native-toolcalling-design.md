# Single Agent + Native Tool Calling — Design Spec

**Date:** 2026-05-08
**Status:** Implemented on local `main`; design background remains the contract reference.
**Supersedes:** the closed 2026-04-30 Agent Team redesign line of work.

**Repo-OS placement:** this spec is the design document. The current
execution work driven by this design must live at:

- `docs/superpowers/plans/2026-05-08-single-agent-native-toolcalling.md` —
  multi-step execution plan with sliced PRs, owners, and gates (Slice A–E
  in Migration Sequence below). This is the canonical plan location per
  AGENTS.md and ADR 0003.
- `docs/adr/` (optional) — a durable ADR if the single-Agent topology
  decision should be recorded as a repository-level rule.

This spec captures the design rationale, contracts, and verifiable claims.
The plan owns sequencing, PR boundaries, and rollout gates. They must stay
consistent; if they drift, the plan wins for execution decisions and this
spec wins for contract definitions.

**Implementation closeout (2026-05-09):** the single-Agent native-toolcalling
cutover has been merged locally into `main` as merge commit `7a8ca61` from
branch `feature/single-agent-native-toolcalling` head `a88524e`. The current
runtime entry point is `agent/agno_agent/runtime/agent_runtime.py`; the
former `team_runtime.py`, selector, plan parser, manager prompt, context port,
and output-disposition adapter have been deleted. Canonical docs now describe
the single-Agent runtime in `docs/ARCHITECTURE.md`,
`docs/design-docs/coke-working-contract.md`, `docs/fitness/coke-verification-matrix.md`,
and `docs/roadmap.md`.

Fresh local verification after the merge:

- `zsh scripts/verify-surface worker-runtime repo-os` passed on local `main`.
- Canonical docs grep is clean for `Agent Runtime Team`, `team_runtime`,
  `AGENT_RUNTIME_VERSION=team`, `run_team_runtime`, selector, plan-parser,
  manager-prompt, context-port, and output-disposition adapter references.

Known remaining evidence gap: the real-model native-toolcalling smoke exists
as `tests/eval/test_real_model_native_toolcalling_smoke.py`, but the local
merge verification did not enable `AGENT_RUNTIME_REAL_MODEL_SMOKE=1`; therefore
real provider/tool-schema behavior remains unproven in this closeout.

---

## Problem

The current runtime uses an Agno `Team` with one LLM (the manager) and zero actual LLM members.
Capabilities are Python functions, not agents. This is a fake Team.

Because the fake Team bypassed Agno's native tool calling, the codebase invented a substitute:

- A self-invented RESPONSE/REQUEST text protocol in the system prompt
- `plan_parser.py` (92 lines) to parse that protocol, silently swallowing `JSONDecodeError`
- `_is_protocol_artifact_response` (lines 197–215 of `team_runtime.py`): substring sniffing for 10 different tool-call markers plus a JSON-envelope artifact check, to recognise other models' tool-call formats leaking into the RESPONSE channel
- Two retry loops plus a `manager_recovery_capability` that fabricates a `CapabilityResult` when the model output does not match expectations (lines 326–407 of `team_runtime.py`)
- A `selector.py` that only ever selects `"team"` — a single-branch trampoline serving no purpose
- An `event_adapter.py` that constructs an `AgentRunContext` and immediately discards it before delegating to `team_runtime.run_team_runtime`, where the same context is rebuilt

The system prompt (`prompts/manager.py`) embeds `INSTRUCTIONS_CHAT_RESPONSE` including "Output as valid JSON" while the runtime parses plain RESPONSE/REQUEST text — a direct contradiction the model sees on every call.

In addition, four communication protocol gaps exist:

1. **Data contracts**: `context: dict[str, Any]` crosses the layer boundary — the trusted `AgentRunContext` is constructed then discarded; untrusted `raw` dict is smuggled in via `metadata={"raw": raw}`
2. **Identifier SSOT**: capability names exist as literal strings in 4+ files with no single authority
3. **Lifecycle**: no cancellation protocol — `is_new_message_coming_in` is checked once before `_run_agent_runtime_event` and never again, so a new user message arriving while the runtime is still running cannot pre-empt the in-flight reply
4. **Dependency direction**: capabilities import from `runtime/` — wrong direction

The Agno `Team` primitive exists for multi-LLM coordination and negotiation. Coke's runtime is a sequential pipeline of five LLMs (Orchestrator, ReminderDetect, PostAnalyze, QueryRewrite, ChatResponse). None of them delegate to each other. Paying Team's coordination overhead for a pipeline provides no benefit and forced the protocol workaround above.

---

## Decision

Replace the fake Team runtime with a single Agno `Agent`. Capabilities become Agno function tools. Agno's native tool calling handles dispatch. No custom protocol, no parser, no fabricated recovery.

---

## Architecture

```
agent_handler.py
    │
    │  AgentInput (typed dataclass) + legacy context dict
    ▼
event_adapter.run_agent_runtime_event   ← entry boundary: dict→typed conversion happens here
    │  build_agent_run_context(context, …) → AgentRunContext
    │  AgentInput + AgentRunContext
    ▼
agent_runtime.py                    ← new thin entry point
    │  creates Agent, registers tools, awaits agent.arun(input=...)
    ▼
Agno Agent                          ← replaces Team + manager LLM
    ├── tool: reminder_intent(...)
    ├── tool: timezone(...)
    ├── tool: calendar_import(...)
    └── tool: url_context(...)
    │
    │  Agno RunOutput + collected CapabilityResult list
    ▼
agent_handler.py

PostAnalyzeWorkflow                 ← runtime semantics preserved
reminder_event_handler.py          ← fire-entry semantics preserved
deferred_action_executor.py        ← dispatch semantics preserved
```

`event_adapter.run_agent_runtime_event` is the entry boundary. Today its
`build_agent_run_context` call is dead because `run_team_runtime` rebuilds the
context internally; after the cutover the adapter is the *only* site that
constructs `AgentRunContext`, and it forwards the typed context (alongside
`AgentInput`) into `agent_runtime.py`. It must not call `run_team_runtime` or
re-emit the legacy `context` dict after the cutover.

The Agent's system prompt is a clean chat-response prompt with no RESPONSE/REQUEST instructions. Agno handles tool dispatch natively — the model sees standard tool-use schema, not a bespoke text protocol.

---

## Communication Protocol

Every layer boundary uses a typed dataclass. No `dict[str, Any]` crosses a
layer boundary after the entry point. The entry point — where the legacy
`context: dict[str, Any]` is consumed and converted — is
`event_adapter.run_agent_runtime_event`.

| Boundary | Protocol |
|---|---|
| `agent_handler` → `event_adapter` | `(AgentInput, context: dict[str, Any])` — explicitly tolerated as the dict-to-typed conversion boundary. `event_adapter` calls `build_agent_run_context(context, …)` and never forwards the dict further. |
| `event_adapter` → `agent_runtime` | `(AgentInput, AgentRunContext)` — both passed as typed positional/keyword arguments. `AgentInput` stays focused on input-event shape (`input_type`, `conversation_id`, `text`, typed `payload`, `occurred_at`). Identity, persona, and conversation history live on `AgentRunContext`. |
| `agent_runtime` → Agno Agent | `await agent.arun(input=input_message_str, session_id=run_context.conversation.id)` — `AgentRunContext` is captured by each tool wrapper's per-run closure; do not pass it via Agno's `session_state` kwarg. Pass `session_state` only if a specific Agno feature requires it (e.g. an inner detector agent that reads it), and document the entry per tool. |
| Agno Agent → tool | Python function call with typed args |
| Tool → Agno Agent | JSON-serializable capability envelope |
| `agent_runtime` → `agent_handler` | `AgentRunResult` |

`AgentInput` is intentionally not expanded with user/character/timezone/
platform/chat-history fields, because those values are normalised upstream
by `context_prepare`. Note this is *normalisation*, not strict schema
validation: `agent_handler.handle_message` further mutates the resulting
context (e.g. injecting `message_source`, `recent_chat_history`,
`proactive_times`, `lock_id`, `input_messages_str`) before the adapter sees
it. The integrity guarantee comes from `event_adapter` building a typed
`AgentRunContext` only from explicitly named fields at the entry boundary,
not from `context_prepare` being a global single source of truth. The
single-Agent migration does not require expanding `AgentInput`; a future
spec may revisit the entry boundary if the legacy `context` dict is removed
upstream.

**Context construction rule**: `AgentRunContext` is populated only from explicitly validated fields at the entry boundary. No passthrough of untrusted dicts via `metadata`.

**Capability identifier SSOT**: each tool's Python function name is the
single authoritative identifier on the *model-facing* surface and on the
captured envelope. The canonical names for this migration are the existing
runtime names: `reminder_intent`, `timezone`, `calendar_import`, and
`url_context`. Do not introduce `get_timezone`, `import_calendar`, or
`get_url_context` aliases unless a later spec explicitly renames the whole
surface.

`CapabilityResult.name` is a separate, internal categorization (e.g. the
reminder capability stores `name="reminder"` while its tool function is
`reminder_intent`). The model never sees `CapabilityResult.name`. The tool
wrapper sets the envelope's `name` field to the tool function name, not to
`CapabilityResult.name`, so the two concepts cannot drift visible to the
model. Internal tests and downstream consumers may continue to read
`CapabilityResult.name` for categorization; renaming it is out of scope.

---

## Context Isolation Rule

Single Agent does not mean one big prompt.

The Agno Agent owns only turn-level orchestration:

- interpret the current user turn
- decide whether to call tools
- read tool results returned through native tool calling
- produce ordinary final chat text when deterministic tool output does not own
  the response

Specialized reasoning remains behind typed tools:

- ReminderDetectAgent remains inside `reminder_intent`
- reminder command validation and execution remain inside the reminder
  capability
- timezone, calendar import, and URL retrieval logic remain inside their tool
  wrappers
- durable-write acknowledgement remains governed by `CapabilityResult` and
  `agent_runtime.py`

`ChatResponseAgent` is retired as an independent LLM call in the main user-turn
path. Its persona, language, and safety dialogue rules are preserved only as
prompt source for the single Agent after JSON-schema output requirements are
removed.

Do not collapse specialized detector prompts, validation rules, or
durable-write logic into the single Agent system prompt.

---

## Agno Tool Result Bridge

Agno native tool calling is used for dispatch, but Agno does not preserve Coke's
typed `CapabilityResult` object as the tool boundary. In the current local Agno
runtime, tool results are ultimately represented as string tool output on
`ToolExecution`. Therefore Coke must keep its own typed result bridge.

`agent_runtime.py` owns this bridge:

1. Construct an empty per-run `tool_results: list[CapabilityResult]`.
2. Register each Agno tool as a thin wrapper around the existing capability
   implementation. **Default to `async def` wrappers.** Sync wrappers are
   tolerated because Agno 2.5.9's `Model.arun_function_call`
   (`agno/models/base.py` line ~2419) routes sync entrypoints through
   `await asyncio.to_thread(function_call.execute)` automatically, so a sync
   wrapper does not pin the event loop in the standard dispatch path. Two
   constraints make `async def` the safer default:
   - If the capability has *any* async dependency that must be awaited
     (e.g. `reminder_intent`'s inner `ReminderDetectAgent` running a model
     call), the wrapper must be async to await it without nested event loops.
   - If a wrapper attaches an async `tool_hook`, Agno routes the entire call
     through `Function.aexecute`, which calls the entrypoint inline (see
     `agno/tools/function.py` around the `entrypoint(**args)` site). In that
     branch a sync wrapper that does I/O *would* pin the loop. Async
     wrappers avoid this footgun even if the project later adds async hooks.
   Inside an async wrapper, sync I/O (e.g. `UrlContextPort.run` and the
   default URL reader, calendar import network calls, blocking timezone DAO
   work) should be offloaded with `asyncio.to_thread` or an explicit
   executor. Already-async capability logic is awaited directly.
3. The wrapper accepts only model-facing typed arguments.
4. The wrapper calls the capability with `input_message`, `AgentRunContext`, and
   tool args from the per-run closure.
5. The wrapper appends the returned `CapabilityResult` to `tool_results`.
6. The wrapper returns a JSON-serializable capability envelope to Agno containing
   only the model-facing subset: `name`, `ok`, `content`, and a public `error`
   message when present. Internal-only `CapabilityResult` fields
   (`requires_response_synthesis`, `visible_summary`, `metadata.durable_write`,
   any internal trace) are stripped from the model-facing envelope and are read
   only from the typed side-channel.
7. After `agent.arun(...)`, `agent_runtime.py` builds `AgentRunResult` from both
   Agno's `RunOutput` and the collected `tool_results`.

The model may read the JSON envelope, but Coke does not reconstruct durable
state or output disposition by reparsing the model-visible tool output. The
typed side-channel is the source of truth.

Tool wrappers may be implemented as Agno `Function` objects or plain callables,
but the tests must prove that `CapabilityResult` metadata survives into
`AgentRunResult.tool_results`, especially:

- `durable_write`
- `requires_response_synthesis`
- `visible_summary`
- `error`

---

## Deterministic User-Visible Output

Native tool calling removes the RESPONSE/REQUEST parser, but it must not make
durable acknowledgements depend on free-form LLM rewriting.

**Defining "Agno final text".** Agno's `RunOutput.content` accumulates *all*
assistant text emitted across the entire `arun` call, including any pre-tool
"reasoning preface" the model emits before a `tool_use` block (Anthropic
Claude routinely emits short pre-tool prose). Reading `RunOutput.content`
directly would leak that preface to the user. "Agno final text" in the rules
below means specifically the content of the last assistant message that
follows the last tool result — equivalently, the content of the final
post-tool model turn within `RunOutput.messages`, with any pre-tool
assistant text discarded. `agent_runtime.py` must extract this from
`RunOutput.messages` (or by filtering the streamed event sequence to keep
only the final `assistant_response` chunk after the last tool result), not
by reading `RunOutput.content`. If there were no tool calls in the run, the
sole assistant message *is* the final text.

`agent_runtime.py` uses these output rules, evaluated in order. The first
matching rule wins:

1. If any executed result has `requires_response_synthesis=True` AND Agno
   final text (as defined above) is non-empty, the visible response is Agno
   final text. This takes precedence over `visible_summary` so synthesizing
   tools (URL/context-reading flows) can override deterministic summaries
   from the same turn.
2. If one or more executed tool results expose `visible_summary` (rule 1 did
   not fire, OR rule 1 wanted to fire but Agno final text was empty), the
   final visible text is the joined `visible_summary` values. Agno final text
   is ignored for this purpose. This preserves the current `team_runtime`
   behavior where a successful durable write plus a synthesizing tool with no
   model text still produces a deterministic acknowledgement instead of an
   empty reply.
3. If there are no tool results, Agno final text is the visible response.
4. If none of the above produced visible text, return
   `OutputDisposition(status="empty")` so `agent_handler.py` can use the
   existing fallback behavior.
5. A durable write tool must not be considered successful unless the captured
   `CapabilityResult` says `ok=True` and exposes a non-empty
   `visible_summary`. This rule is enforced primarily as a **capability-layer
   developer contract** verified by tests, not as a runtime guard that can
   roll state back. By the time `agent_runtime.py` sees the
   `CapabilityResult`, the durable write has already happened inside the
   capability body (e.g. `ReminderCommandExecutor.execute` writes to MongoDB
   before constructing the result). A `CapabilityResult` with
   `metadata["durable_write"] is True`, `ok=True`, and no `visible_summary`
   is therefore a contract violation that `agent_runtime.py` cannot undo: it
   must (a) emit a typed runtime error disposition for telemetry/alerting,
   (b) avoid silently presenting `status="ok"` with empty `visible_messages`
   to the handler, and (c) accept that the underlying durable state may be
   inconsistent until manually reconciled. Each capability that sets
   `durable_write=True` owns the responsibility to always populate
   `visible_summary` in its success path; per-capability tests must cover
   this for every action that can produce `durable_write=True`.

   This migration does not support "successful but intentionally invisible"
   durable writes. None of the current native-toolcalling ports need that
   behavior: reminder and timezone writes must acknowledge deterministically,
   calendar import returns a handoff summary (and is not classified as a
   `durable_write` because it does not write Coke-owned durable state — it
   hands off to Google Calendar), and URL context is not a durable write. If
   a future capability needs a durable write with no user-visible
   acknowledgement, it requires a separate spec that defines handler and
   deferred-action status mapping explicitly.

**Status mapping**: when rules 1–3 resolve a non-empty visible text,
`agent_runtime.py` returns `OutputDisposition(status="ok")` with that text in
`AgentRunResult.visible_messages`. Rule 4 returns
`OutputDisposition(status="empty")` and an empty `visible_messages`. Rule 5
contract violations are mapped through the fail-closed exception path
(`OutputDisposition(status="empty")` plus a `RuntimeErrorDisposition` carrying
the violation code), not as `status="ok"` with empty `visible_messages`.

This preserves the current contract where reminder/timezone/calendar state
changes produce deterministic acknowledgements, while URL context and ordinary
chat can still use the model's final wording.

---

## What Is Deleted

| Path | Lines | Reason |
|---|---|---|
| `agent/agno_agent/runtime/team_runtime.py` | 498 | replaced by Agno Agent + tools |
| `agent/agno_agent/runtime/selector.py` | 42 | single-branch trampoline |
| `agent/agno_agent/runtime/plan_parser.py` | 92 | RESPONSE/REQUEST parser |
| `agent/agno_agent/capabilities/context_port.py` | 52 | zero production callers (only re-exported in `capabilities/__init__.py` and used by its own unit test) |
| `agent/agno_agent/adapters/output_disposition.py` | 20 | move `with_output_references` into `result.py` first (current caller: `deferred_action_executor.py`; after migration `agent_runtime.py` becomes the second caller); delete module after relocation |
| `agent/agno_agent/prompts/manager.py` | 49 | RESPONSE/REQUEST system prompt builder |
| `agent/agno_agent/runtime/event_adapter.run_deferred_action_runtime_event` | — | function defined but called only by its own re-exports — `deferred_action_executor.py` calls `map_agent_result_to_deferred_status` directly. Delete the function and its re-exports in `runtime/__init__.py`. |
| Tests for all of the above | — | test deleted behavior |

---

## What Is Preserved

| What | Why |
|---|---|
| `AgentInput`, `AgentRunContext`, `AgentRunResult`, `CapabilityResult` | typed entry/exit contracts |
| `agent/agno_agent/runtime/_immutability.py` | live helper used by frozen runtime dataclasses |
| `agent/agno_agent/runtime/event_adapter.py` | reduced to thin `AgentInput`-to-`agent_runtime` shim; current dead `build_agent_run_context` call and `run_team_runtime` dispatch are removed |
| `OutputDisposition` logic | inlined into `agent_runtime.py` (no separate module) |
| Fail-closed error mapping | maps all unhandled exceptions to a safe user-visible error |
| `reminder_event_handler.py` | reminder fire-entry semantics preserved; reliability logging fixes allowed |
| `deferred_action_executor.py` | deferred action dispatch semantics preserved; occurrence error fix allowed |
| PostAnalyzeWorkflow | background post-analysis — unchanged |
| Hand-written fake test pattern | approved test strategy for Agno boundary |

---

## Related Contract Fixes

These bugs are real, but they are not all part of the native-toolcalling
cutover. They must be sequenced so runtime replacement, runner reliability, and
reminder-detector cleanup can be verified independently.

1. **Silent exception swallowing** (`reminder_event_handler.py` lines 65–70, 87–92, 133–134): replace bare `except Exception:` with `logger.exception(...)` before re-raising or returning.
2. **`occurrence` scope bug** (`deferred_action_executor.py` lines 186–203): move `occurrence` binding outside the try block so `NameError` cannot shadow the original exception.
3. **In-flight runtime interrupt loss** (`agent_handler.py` lines 648–664): `is_new_message_coming_in` is checked once before `_run_agent_runtime_event` and never again. Re-check it before *every* outbound write that follows the runtime call — both the per-`visible_message` `_send_single_message` invocations and the empty-output `_send_chat_response_fallback` path at lines 744–768 — so a newer user message can pre-empt before any reply (including a fallback reply) is sent. The existing lock-ownership check on the fallback path is necessary but not sufficient: lock ownership does not detect a fresh user message arriving while the lock is still held.
4. **Untrusted dict smuggled into context** (`context.py` line 118–119): remove `metadata={"raw": raw}`; expose only validated fields on `AgentRunContext`.
5. **Dead guard functions never called** (`agent_handler.py` lines 440–526): delete `_guard_pending_reminder_stop_response`, `_guard_unconfirmed_reminder_response_after_prepare_timeout`, `_is_clawscale_sync_text_reply_context` — they are defined but never invoked in the production path.
6. **Env-var float parsing duplication** (`reminder_intent.py` lines 24–54): consolidate into one location; remove duplicate in `team_runtime.py` (deleted anyway).
7. **Retry prompt contradicts live schema** (`reminder_intent.py` lines 76–108): `_build_reminder_retry_input` omits `cancel` from the schema shown to the model; align prompt with actual `ReminderIntent` schema.
8. **NLP heuristics in wrong layer** (`reminder_intent.py` lines 285–329): `_should_retry_for_quoted_title_loss` belongs in the capability's validation logic, not as a free-standing NLP heuristic; refactor inline or remove if covered by schema validation.

Minimum sequencing:

- Fix runner reliability items 1-3 before or alongside the runtime entry point.
- Fix typed context item 4 inside the runtime entry point slice.
- Delete dead guards and adapters only after focused production-path tests prove
  they are unused.
- Keep reminder-detector retry/schema cleanup in a separate focused slice unless
  native tool wrappers cannot be tested without it.

---

## New Entry Point: `agent_runtime.py`

Replaces `team_runtime.py` and `selector.py`. Public callable:
`async def run_agent_runtime(*, agent_input: AgentInput, run_context:
AgentRunContext) -> AgentRunResult`. Responsibilities:

1. Accept `(AgentInput, AgentRunContext)` from `event_adapter`. Validate
   `AgentInput`'s typed payload shape; treat `AgentRunContext` as already
   trusted (constructed from the validated entry boundary). Do not accept the
   legacy `context` dict.
2. Construct Agno `Agent` with:
   - Model from `model_factory`
   - Tools: `reminder_intent`, `timezone`, `calendar_import`, `url_context`,
     each registered as an async wrapper (see Agno Tool Result Bridge)
   - Chat-response instructions produced by the runtime-local builder
     described in System Prompt
3. Await `agent.arun(...)`. Agno's native tool dispatch is itself non-blocking
   *only* when each tool wrapper is async (see "Agno Tool Result Bridge"
   above); blocking I/O inside a sync wrapper would still pin the worker event
   loop, so `agent_runtime.py` must register every tool as an async wrapper.
4. Map Agno `RunOutput` plus captured `CapabilityResult` list to `AgentRunResult` (fail-closed on exception)
   - Set `post_analyze_input` to `{"input_message": input_message_str, "message_source": message_source}` when the run produces visible output (i.e., the resolved visible text from the rules above is non-empty, equivalently `AgentRunResult.visible_messages` is non-empty and `output_disposition.status == "ok"`). Set it to `None` when output is empty or suppressed. This mirrors the existing `team_runtime.py` behaviour so `agent_handler.py` triggers `PostAnalyzeWorkflow` on the same conditions. (`OutputDisposition` has no `visible_text` field; do not introduce one — read `visible_messages` directly.)
5. Return `AgentRunResult` to `agent_handler`

Agent construction is stateless per call. No global singleton. Tools are thin
wrappers around capability logic and must capture typed `CapabilityResult`
objects before returning JSON-serializable output to Agno.

---

## System Prompt

`prompts/manager.py` is deleted. The Agent uses a runtime-local chat-response
instruction builder that imports the existing
`agent.prompt.agent_instructions_prompt.INSTRUCTIONS_CHAT_RESPONSE` as source
material and produces the single-Agent system prompt by:

**Keeping** these subsections from `INSTRUCTIONS_CHAT_RESPONSE` verbatim or
near-verbatim, since they remain correct for free-form chat output:

- The persona/role intro lines except those mentioning structured/JSON output
- The "## Handling User Challenges" block (acknowledgement, no-blame, neutral
  facts) — kept, **but rewritten to remove the line "If there is a `[reminder
  tool message]` in context, use it to explain the actual state."** That
  sentence references a labelled prompt block from the structured
  `ChatResponseAgent` path; under native tool calling the model receives
  reminder results as protocol-level tool messages, not as a
  `[reminder tool message]` segment in the system prompt. Replace with
  general guidance like "If a reminder tool result is available in the
  conversation, use its content to explain the actual state" — phrased so it
  works for native tool-result messages.
- The factual content rules: language match, character voice, no fabricated
  reminder/notification commitments, no bracket-style action text

**Removing or rewriting** these subsections, which are artifacts of the old
structured `ChatResponseAgent` path and are wrong for the single Agent:

- The opening list item `3. Output structured multi-modal messages` — removed;
  the single Agent emits free chat text and any non-text user-visible output
  comes through the deterministic tool side-channel.
- `## Output Requirements` line `- Strictly output according to the JSON
  Schema` — removed.
- `## Output Requirements` line `- Message types include: text` — removed (the
  Agent does not author message-type metadata; the side-channel envelope does).
- The trailing `Output the result as valid JSON, strictly following the
  defined schema.` — removed.
- Any RESPONSE/REQUEST wording — must not appear, since none exists in this
  source today and none must be added.

The builder must not invent new persona instructions, reasoning hints, or
tool-routing rules. Tool descriptions live on each `@tool` function — not in
the prompt. Do not create a second independent chat prompt.

A unit test asserts that the assembled prompt contains none of:
`"as valid JSON"`, `"JSON Schema"`, `"Message types include"`,
`"structured multi-modal"`, `"RESPONSE"`, `"REQUEST"`.

---

## Testing

- Unit tests for each tool function: given typed args, assert `CapabilityResult` shape
- Unit tests for `agent_runtime.py`: fake `agent.arun()`, assert
  `AgentRunResult` construction, captured `CapabilityResult` preservation,
  deterministic visible-output rule precedence — including the specific case
  where `requires_response_synthesis=True` AND Agno final text is empty AND a
  prior `visible_summary` exists: rule 2 must fire and the
  `visible_summary` must be the visible text (regression guard against
  current `team_runtime` behaviour) — fail-closed mapping, and
  `post_analyze_input` is non-`None` when `visible_messages` is non-empty and
  `None` when it is empty
- Unit test for the model-facing tool envelope: assert `requires_response_synthesis`,
  `visible_summary`, and `metadata.durable_write` are NOT present in the JSON
  envelope returned to Agno, while remaining present on the captured
  `CapabilityResult` in `tool_results`
- Unit test for unknown-tool dispatch: when the model emits a tool call name
  that is not registered, `agent_runtime.py` produces a fail-closed
  `AgentRunResult` (no fabricated `CapabilityResult`, no silent swallow) and
  surfaces a typed error disposition rather than a free-form chat reply
- Unit test for blocking-I/O offload inside async wrappers: when a wrapper
  is `async def` and its underlying capability does sync I/O, assert the
  wrapper uses `asyncio.to_thread` (or equivalent) for that I/O so a
  concurrent `asyncio` task can make progress while the wrapper runs.
  This guards the project's "default-async wrapper" convention, not Agno's
  own offload — Agno itself routes sync wrappers through `asyncio.to_thread`
  in `Model.arun_function_call`, so a synthetic test that "sync wrapper
  blocks the loop" would fail to reproduce the issue. Inspecting
  `inspect.iscoroutinefunction` is *not* a valid substitute, since an
  `async def` wrapper that calls blocking sync code directly (e.g. a naive
  port over `UrlContextPort.run`) passes the inspect check while still
  pinning the loop.
- Unit test for prompt-cleaning invariants: `INSTRUCTIONS_CHAT_RESPONSE` is
  imported, run through the runtime-local builder, and the resulting string
  must not contain any of `"as valid JSON"`, `"JSON Schema"`, `"Message types
  include"`, `"structured multi-modal"`, `"RESPONSE"`, `"REQUEST"`.
- Unit test for envelope identifier: the JSON envelope returned to Agno from
  the reminder wrapper has `name == "reminder_intent"` (the tool function
  name), not `"reminder"` (the internal `CapabilityResult.name`).
- Unit test for cancel-action retry parity (Related Contract Fix #7): given a
  validation-failure retry path, the retry input includes `cancel` in the
  allowed-action list so the model is not prompted with a schema that diverges
  from `ReminderDetectDecision`
- Unit test for durable-write classification (rule 5): two cases — (i)
  `ok=True` + `metadata["durable_write"] is True` + non-empty
  `visible_summary` → success; (ii) `ok=True` +
  `metadata["durable_write"] is True` + no `visible_summary` → fail-closed
  runtime contract violation (`OutputDisposition(status="empty")` plus typed
  error disposition, not `status="ok"` with empty `visible_messages`).
- Unit test for in-flight interrupt on the empty-output fallback path:
  fake the runtime to return `OutputDisposition(status="empty")` with no
  visible messages, simulate `is_new_message_coming_in == True` between the
  runtime call and the fallback send, and assert
  `_send_chat_response_fallback` is NOT invoked and the handler returns with
  `is_rollback=True`.
- Unit test for "Agno final text" extraction (B1): given a `RunOutput` whose
  `messages` are `[user, assistant("Let me check..."), tool_use, tool_result,
  assistant("Here is the info.")]`, assert `agent_runtime.py` resolves "Agno
  final text" to `"Here is the info."` and never to the concatenation
  `"Let me check...Here is the info."` that `RunOutput.content` would
  contain. Cover the no-tool-call case (single assistant message →
  that message is the final text) and the tool-call-then-empty-final-turn
  case (rule 1 falls through to rule 2).
- Real-model smoke against the current production model: drive the
  configured `reminder_intent`, `timezone`, and `url_context` tools through
  a real Agno `Agent` (not a fake) using the production model from
  `model_factory`. Verify (i) Agno actually emits a tool-use schema the
  model honours; (ii) `RunOutput.messages` shape matches the assumptions in
  the "Agno final text" extraction rule; (iii) error structure when a tool
  raises is consistent with the typed result-bridge contract; (iv)
  streaming and non-streaming runs return equivalent visible text. Fake
  tests cannot prove model behaviour; this smoke is required before
  cutover.
- Known parity divergence to watch (M5): the current `team_runtime`
  synthesis prompt explicitly tells the model "Do not request capabilities
  again unless the result shows a missing required input." Native tool
  calling drops that guard; the model may issue extra tool calls under
  retry. Agno's `tool_call_limit` provides a safety net. Parity tests must
  assert tool-call counts for representative reminder/timezone flows stay
  within `team_runtime` baseline ±1, not just that visible text matches.
- Send-loop interrupt + rollback retry interaction (L2): when a per-message
  interrupt re-check trips mid-stream after one or more visible messages
  have already been sent, assert (a) `_send_single_message` is not invoked
  for any subsequent message, (b) `is_rollback=True` is returned, (c) the
  rollback retry path's existing `turn_sent_contents` dedupe prevents the
  already-sent messages from being re-sent on the retry pass. If
  `turn_sent_contents` is not populated until after the function returns,
  surface that gap as a separate fix before this rule ships.
- Baseline parity before implementation: run current Team runtime focused tests and record failures before changing prompt or runtime logic
- Focused parity after each migration slice: reminder create/update/cancel/list, timezone, calendar import, URL synthesis, empty-output fallback, and in-flight runtime interruption (covering both the visible-message send loop and the empty-output fallback send)
- E2E tests: behavior parity against existing E2E suite before deleting the old runtime
- Hand-written fake tests at the Agno boundary (existing approved pattern)

Tests for deleted modules (`team_runtime`, `selector`, `plan_parser`, `context_port`) are deleted with the modules.

---

## Product Acceptance

Runtime contract tests prove `agent_runtime.py` *can* behave correctly. They
do not prove the user-perceived product still works. Before the cutover ships
to production, the following user-path acceptance matrix must pass against
the new runtime in a staging environment, recorded as evidence under
`artifacts/evidence/`. These mirror Phase 1's product value: personal
supervision, reminders, conversation continuity, channel reliability.

| Scenario | Acceptance |
|---|---|
| Ordinary chat | Reply is natural and in-persona; no JSON, RESPONSE/REQUEST, tool envelope, or `[reminder tool message]` artifacts in user-visible text. |
| Reminder create | "明天 8 点提醒我喝水" → durable write happens AND the user-visible confirmation is the capability's `visible_summary` (not free-form LLM rewriting). No false confirmation when the write fails. |
| Reminder update | Existing reminder modified; visible summary reflects the new state from the capability. |
| Reminder cancel / delete | Cancellation deterministically acknowledged from `visible_summary`; never "我已取消" without a successful capability call. |
| Reminder list / query | All matching reminders surfaced from the capability result; no fabricated entries. |
| Reminder fired | End-to-end: scheduler tick → `reminder_event_handler.handle` → typed runtime → user receives reminder text via the configured channel. Replay/idempotency preserved (no duplicate fire). |
| Timezone change | Both direct-set and propose-then-confirm flows produce deterministic acknowledgement; "current_time appears in context" alone does not trigger a timezone tool call. |
| Calendar import | Import handoff returns the expected link/summary; URL is not auto-synthesised over by the model. |
| URL synthesis | Message containing a URL produces a model-synthesised reply that uses URL content; deterministic summary does not override synthesis (rule 1 fires when applicable). |
| Empty-output fallback | When the runtime returns `status="empty"`, the handler sends the existing fallback text. |
| New-message interrupt | While the runtime is processing a turn and a fresh user message arrives, the in-flight reply is suppressed before send — including the empty-output fallback path. The user does not see a stale reply layered after their newer message. |
| PostAnalyze trigger | `PostAnalyzeWorkflow` fires on the same conditions as today (visible output produced, `status="ok"`); does not fire for empty/rollback turns. Background scheduling still completes. |
| No protocol artefact leaks | Across all of the above: regression-grep user-visible outputs for `RESPONSE`, `REQUEST`, `<tool_call`, `<invoke`, ```` ```json `, `tool_use`, and `[reminder tool message]`. None present. |

Minimum user-visible bars (must hold across all scenarios above):

- A reminder confirmation in user-visible text must originate from a
  successful durable write's `visible_summary`. No free-form "我已经帮你设
  好啦" without a capability acknowledgement behind it.
- A newer user message always wins over an older runtime's pending reply,
  including fallback replies. No stale message is delivered after a fresh
  user turn has been observed.
- Tool envelopes, system-prompt protocol markers, and prompt-shape labels
  never appear in user-visible text.
- State-changing capabilities (reminder, timezone, calendar) produce
  deterministic acknowledgements; URL context and ordinary chat may use
  natural-language synthesis.
- Reminder fire is verified end-to-end (scheduler → fire handler →
  user-visible output), not only at create time.

---

## Rollback Playbook

The spec rule "no feature flags" rejects long-lived compatibility shims; it
does *not* eliminate the need for rollback. Phase 1 personal supervision is
running in production, so a parity gap surfaced after cutover must be
recoverable in minutes, not hours.

Pre-cutover (part of Slice C below):

- Tag the last commit on the old runtime as
  `pre-single-agent-cutover-<YYYYMMDD>` and push the tag.
- Record current `requirements.txt` Agno pin (`agno==2.5.9`) and the
  PM2/compose service version of the running workers.
- Capture a fresh baseline of focused worker/runtime tests and one
  reminder-normal smoke as evidence under `artifacts/evidence/`.

Cutover gate (must pass before traffic flips):

- Slice B real-model smoke green for `reminder_intent`, `timezone`,
  `url_context`.
- Product-acceptance matrix above green in staging.
- Worker-runtime verification commands from
  `docs/fitness/coke-verification-matrix.md` green.

Failure detection criteria after cutover (any one trips rollback):

- Reminder create/update/cancel parity test in production traffic shows a
  silent-write or false-acknowledgement.
- Empty-output fallback rate exceeds the pre-cutover baseline by more than
  the noise band recorded in the evidence bundle.
- Tool-envelope or protocol artefact appears in any user-visible message
  (regression grep over recent outbound logs).
- Operator report of new-message-interrupt failure (stale reply layered
  after newer user turn).
- Worker error rate or PostAnalyze schedule rate diverges from baseline.

Rollback procedure:

1. `git revert` the cutover commit (Slice C) and any dependent commits up
   to the pre-cutover tag. Do not delete `team_runtime.py` etc. before
   this rollback window closes — Slice D deletion only ships after the
   rollback window expires.
2. Redeploy via the standard `./scripts/deploy-compose-to-gcp.sh
   --restart` (or PM2 equivalent) on the worker fleet. The old
   `event_adapter` → `run_team_runtime` path is restored.
3. Verify with the same reminder-normal smoke captured pre-cutover.
4. Open a follow-up incident with evidence, do not retry the cutover until
   the root cause is named.

The "old runtime files importable until Slice D" provision exists
specifically so this revert is a code revert, not a re-implementation.

---

## Out of Scope

- PostAnalyzeWorkflow restructuring
- Prompt content improvements beyond the keep/remove rules in the **System Prompt** section (i.e. removing the structured-multi-modal opening item, the JSON-schema and message-types lines, the trailing JSON-schema sentence, and never re-introducing RESPONSE/REQUEST wording). No new persona, reasoning, or tool-routing instructions.
- New capabilities
- Gateway, bridge, or deployment changes
- Any behavior change visible to the user (parity first)
- Reminder-detector behavior changes not required to preserve native toolcalling parity

---

## Migration Sequence

The work is split into **five independently mergeable slices**, each with
its own PR. The blast radius of any single review is bounded by the slice.
A single mega-PR is explicitly rejected: a reviewer should be able to read
Slice A without paging in the runtime replacement, and Slice C (cutover)
without paging in the deletion churn.

Worktree-zero step (applies to every slice): create an isolated worktree;
the root checkout may contain unrelated evidence changes.

### Slice A — Runner reliability fixes (no runtime replacement)

**Goal:** ensure the parity baseline is measurable and the in-flight
interrupt path is correct *before* runtime replacement begins. None of
these depend on the new runtime; shipping them first makes Slice C's
cutover narrower and de-risks Phase 1 traffic immediately.

1. Baseline current Team behavior with focused worker/runtime tests and one
   focused reminder-normal smoke. Record failures as evidence under
   `artifacts/evidence/`.
2. Apply Related Contract Fixes 1–3:
   - `reminder_event_handler.py` exception logging (Fix 1).
   - `deferred_action_executor.py` `occurrence` scope (Fix 2).
   - `agent_handler.py` in-flight interrupt re-checks before *every*
     outbound write — both `_send_single_message` invocations and the
     empty-output `_send_chat_response_fallback` path (Fix 3).
3. Apply Related Contract Fix 4 (`context.py` raw-dict smuggling) only if
   the change is small and reviewable in this slice; otherwise defer to
   Slice B where the typed entry boundary is built. Do not bundle larger
   touch-ups.
4. Run focused worker/runtime tests + reminder-normal smoke. Land.

### Slice B — New runtime behind fakes + real-model smoke (no production traffic)

**Goal:** prove `agent_runtime.py` works in isolation before any
production wire-up. No production caller switches in this slice.

1. Write `agent_runtime.py` with public callable
   `async def run_agent_runtime(*, agent_input: AgentInput, run_context:
   AgentRunContext) -> AgentRunResult`. Behind focused tests using a fake
   Agno Agent, prove: `AgentInput` payload-shape validation; acceptance of
   a typed `AgentRunContext` (no dict input); captured `CapabilityResult`
   preservation; deterministic visible-output rule precedence (including
   the "Agno final text" extraction rule from B1 and the
   synthesis-empty-falls-through-to-`visible_summary` regression guard);
   model-facing envelope projection (including envelope `name` set to the
   tool function name, not `CapabilityResult.name`); blocking-I/O offload
   inside async wrappers; unknown-tool fail-closed mapping; empty-output
   fallback; durable-write classification rule 5 surfacing typed runtime
   error; fail-closed exception mapping.
2. Wire native Agno tool wrappers for `reminder_intent`, `timezone`,
   `calendar_import`, and `url_context`. Keep capability logic
   behaviour-equivalent first; do not rewrite detector semantics in this
   slice.
3. Build the runtime-local chat-response instruction builder. The builder
   reads `agent.prompt.agent_instructions_prompt.INSTRUCTIONS_CHAT_RESPONSE`
   and applies the keep/remove rules from the **System Prompt** section.
   The prompt-cleaning invariant unit test from **Testing** guards it. Do
   not edit `prompts/manager.py` (deleted in Slice D) and do not introduce
   a second independent chat prompt.
4. Run the **real-model smoke** described under **Testing** against a
   staging model, exercising `reminder_intent`, `timezone`, and
   `url_context` end to end through a real Agno `Agent`. Record evidence
   under `artifacts/evidence/`. Fake tests cannot prove model-driven tool
   schema or output structure.
5. Land. Production traffic still runs the Team runtime.

### Slice C — Cutover (production traffic flips)

**Goal:** route production traffic through `agent_runtime.py`. Old
runtime files remain importable so a `git revert` is a viable rollback.

1. Tag the pre-cutover commit per **Rollback Playbook**.
2. Change `event_adapter.run_agent_runtime_event` to:
   - keep building `AgentRunContext` via `build_agent_run_context` (no
     longer dead);
   - call `agent_runtime.run_agent_runtime(agent_input=…, run_context=…)`
     instead of `run_team_runtime`;
   - never forward the legacy `context` dict into `agent_runtime`.
3. Run the full **Product Acceptance** matrix from this spec in staging.
   Run `zsh scripts/check` and the worker-runtime verification commands
   from `docs/fitness/coke-verification-matrix.md`. Run the focused
   reminder-normal smoke. All must be green before traffic flips.
4. Deploy to production. Watch the **Rollback Playbook** failure-detection
   criteria for at least one full active-traffic window before declaring
   parity. If any criterion trips, execute the rollback procedure.
5. Land.

No feature flag. The change is gated by Slice B + the Product Acceptance
matrix + staging verification. Rollback is a `git revert` of the cutover
commit, not a runtime switch.

### Slice D — Delete the old runtime

**Goal:** retire the Team runtime once Slice C has held in production
through at least one rollback-window-sized soak.

1. Confirm Slice C parity in production has held; no rollback was
   triggered.
2. Delete `team_runtime.py`, `selector.py`, `plan_parser.py`,
   `prompts/manager.py`, `capabilities/context_port.py`, and
   `event_adapter.run_deferred_action_runtime_event` plus its
   re-exports. Move `with_output_references` into `runtime/result.py` and
   delete `adapters/output_disposition.py`.
3. Delete dead guard helpers in `agent_handler.py`
   (`_guard_pending_reminder_stop_response`,
   `_guard_unconfirmed_reminder_response_after_prepare_timeout`,
   `_is_clawscale_sync_text_reply_context`) per Related Contract Fix 5.
4. Delete tests that exclusively assert deleted protocol behaviour
   (Team runtime, selector, plan parser, context port).
5. Land.

### Slice E — Canonical docs + fitness updates

**Goal:** retire "Agent Runtime Team" terminology so canonical docs do
not describe code that no longer exists.

1. Update `docs/architecture.md` §4 ("Turn Processing Pipeline" —
   currently line 179: "The default turn pipeline is Agent Runtime
   Team.") to describe the single-Agent runtime.
2. Update `docs/design-docs/coke-working-contract.md` (currently line 28:
   "Agent Runtime Team orchestration, typed runtime events, and
   capability ports").
3. Update `docs/fitness/coke-verification-matrix.md` if any entry refers
   to Team-specific commands.
4. Run `grep -rn "Agent Runtime Team\|team_runtime" docs/` and resolve
   every hit.
5. Run `zsh scripts/check` and the worker-runtime verification.
6. Land.

Slice E may land jointly with Slice D in a single PR if the diff is small;
splitting is preferred when the doc change is non-trivial. Slice E must
not lag Slice D into a separate sprint — leaving canonical docs
inconsistent for more than a day is itself a repo-OS contract break.

No feature flags. No compatibility shims. The old runtime is deleted
(Slice D) only after parity holds in production (Slice C).
