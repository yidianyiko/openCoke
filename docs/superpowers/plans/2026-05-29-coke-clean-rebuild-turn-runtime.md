# Coke Clean Rebuild Turn Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build The Turn orchestration slice with injected Agno/LLM/domain ports, the real Task 6 conversation ledger, and the required interactive/render mode contracts.

**Architecture:** The runner owns the pipeline shape and delegates all business work to injected ports. ConversationRuntimeService remains the ledger/disposition source, ConversationLockManager remains the per-conversation lock source, and this slice only defines the narrow turn-time ports that later T13 wiring will bind to real domains and Agno. The modules stay focused: gate, context, interpreter, focus, reference resolution, freshness, memory, agent, output protocol, and runner.

**Tech Stack:** Python 3.12, dataclasses, Protocol ports, pytest, in-memory fakes, Task 6 `coke.domains.conversation_runtime`, Task 6 `coke.turn.locks`.

---

**Plan Status:** complete
**Status Date:** 2026-05-30
**Freshness Check:** Checked against current `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md` Task 7 and architecture-watch notes, requirements §5.4, target architecture §1/§3.3/§4/§9 invariants, `coke/schema.py`, Task 6 conversation runtime, and existing domain layering patterns.
**Verification Note:** Turn implementation and backend unit surface pass. The routed `repo-os-docs` check is blocked by existing ownership-registry references to removed legacy `memo-runtime` and nested `gateway` files; that cleanup is outside Task 7's allowed file scope.
**Live Debugging Addendum (2026-05-30):** The local live stack showed real GLM-5.1 Interaction Agent turns failing before reminder creation because fenced JSON was rejected and the actual inbound text was buried inside a JSON context blob. Live verification also exposed an Agno `kwargs` tool-argument wrapper and a detector prompt-shape issue for non-recurring reminders. This addendum keeps the fix inside the turn-runtime/Interaction Agent + detector/tool boundary: strict output validation remains unchanged, reminder field extraction remains inside the reminder tool, and no fallback prose or regex intent routing is added.

**Source Specs:**
- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`
- `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md`

## File Structure

- Create `coke/turn/pre_llm_gate.py`: pre-LLM gate request/result models and injected identity/access/reachability/handoff ports.
- Create `coke/turn/context.py`: trigger/context models, tool profiles, and context assembly over trust, semantic, focus, reference, freshness, and memory inputs.
- Create `coke/turn/semantic_interpreter.py`: SemanticInterpreter port plus decision model; no keyword/regex routing.
- Create `coke/turn/focus.py`: durable rendered-message subject model and focus resolver.
- Create `coke/turn/reference_resolver.py`: per-reference resolver models with clarify-without-mutating outcomes.
- Create `coke/turn/freshness.py`: wrapper around `ConversationRuntimeService.guard_state_change`.
- Create `coke/turn/memory.py`: short-term always-on and long-term memory-switch-gated memory manager.
- Create `coke/turn/agent.py`: InteractionAgent port, tool-surface ports, agent request/result models, and timeout signal.
- Create `coke/turn/output_protocol.py`: first-answer-only structured output validator; no rewrite/fallback behavior.
- Create `coke/turn/runner.py`: orchestration runner that binds the gate, lock, context, agent, output protocol, runtime dispositions, delivery, and async completion path.
- Create `tests/unit/coke/turn/`: self-contained fakes and unit tests, no Postgres/Redis/LLM/live Agno.

## Task 1: Red Tests

**Files:**
- Create: `tests/unit/coke/turn/test_turn_runner.py`
- Create: `tests/unit/coke/turn/test_output_protocol.py`
- Create: `tests/unit/coke/turn/test_context_components.py`

- [x] **Step 1: Write failing orchestration tests**

Cover the required behaviors with fakes:

```python
def test_intentional_no_reply_skips_interaction_agent(...):
    semantic.next_decision = SemanticDecision(reply_necessity="intentional_no_reply", intent_family="chit_chat")
    result = runner.run_inbound_turn(inbound_trigger)
    assert result.disposition == "no_reply"
    assert agent.invocations == 0

def test_malformed_agent_output_fails_closed_without_rewrite(...):
    agent.next_result = AgentResult.completed({"invalid": "shape"})
    result = runner.run_inbound_turn(inbound_trigger)
    assert result.disposition == "failed"
    assert result.reason_code == "invalid_output_protocol"
    assert output_protocol.rewrite_invocations == 0
    assert result.visible_text is None
```

- [x] **Step 2: Add stale, denied, render, and timeout tests**

Cover supersession, AccessDeniedTurn constrained render, render-mode tool profile, and pending async transition:

```python
def test_superseded_inbound_blocks_state_changing_commit(...):
    domain_tool.commit_callback = lambda turn: freshness.guard_state_change(turn)
    runtime.record_inbound(... newer event ...)
    result = runner.run_inbound_turn(inbound_trigger)
    assert result.disposition == "superseded"
    assert domain_tool.committed == 0

def test_denied_access_gate_yields_access_denied_turn_rendered_in_constrained_mode(...):
    gate.next_allowed = False
    result = runner.run_inbound_turn(inbound_trigger)
    assert result.trigger_type == "AccessDeniedTurn"
    assert agent.requests[-1].mode == "render"
    assert agent.requests[-1].tool_profile.intent_tools_enabled is False

def test_render_mode_exposes_no_intent_or_business_mutation_tools(...):
    result = runner.run_render_turn(render_trigger)
    assert agent.requests[-1].tool_profile.tool_names == ()

def test_timeout_yields_waiting_text_pending_async_then_replied(...):
    agent.next_result = AgentResult.timeout(task_id="async-1")
    result = runner.run_inbound_turn(inbound_trigger)
    assert result.disposition == "pending_async_reply"
    assert delivery.delivered_texts[-1].message_type == "waiting"
    agent.next_result = AgentResult.completed({"type": "reply", "segments": ["done"]})
    final = runner.complete_async_reply(result.async_task)
    assert final.disposition == "replied"
```

- [x] **Step 3: Run red tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn -v
```

Expected: FAIL during import or missing implementation, proving the new tests target absent behavior.

## Task 2: Turn Component Modules

**Files:**
- Create: `coke/turn/pre_llm_gate.py`
- Create: `coke/turn/context.py`
- Create: `coke/turn/semantic_interpreter.py`
- Create: `coke/turn/focus.py`
- Create: `coke/turn/reference_resolver.py`
- Create: `coke/turn/freshness.py`
- Create: `coke/turn/memory.py`
- Create: `coke/turn/agent.py`
- Create: `coke/turn/output_protocol.py`

- [x] **Step 1: Implement narrow dataclasses and Protocol ports**

Define only injected ports in this slice:

```python
class ReminderToolPort(Protocol):
    def execute(self, command: Mapping[str, Any], guard: FreshnessGuard) -> ToolExecutionResult: ...

class SocialSchedulingToolPort(Protocol):
    def execute(self, command: Mapping[str, Any], guard: FreshnessGuard) -> ToolExecutionResult: ...

class CalendarImportToolPort(Protocol):
    def execute(self, command: Mapping[str, Any], guard: FreshnessGuard) -> ToolExecutionResult: ...
```

Do not import reminder, social scheduling, calendar import, live Agno, LLM providers, Mongo, gateway, dao, connector, or memo_runtime.

- [x] **Step 2: Implement output protocol validation**

Accept only first-answer structured output:

```python
{"type": "reply", "segments": ["text", "..."]}
{"type": "no_reply", "reason": "intentional_no_reply"}
```

Return invalid results for empty, malformed, too many segments, blank text, structurally blocked output, or unknown types. Do not provide a rewrite API.

- [x] **Step 3: Implement context assembly**

Build interactive contexts from trusted gate facts, SemanticInterpreter decision, Focus subject, ReferenceResolver outcomes, FreshnessGuard, and MemoryManager. Build render contexts from trusted facts and constrained/empty tool profiles.

## Task 3: Runner Integration

**Files:**
- Create: `coke/turn/runner.py`

- [x] **Step 1: Implement inbound orchestration**

Use this order:

```text
pre-LLM gate -> ConversationRuntimeService.start_turn -> ConversationLockManager.acquire
-> ContextAssembler -> SemanticInterpreter no-reply short-circuit
-> InteractionAgent -> OutputProtocolValidator -> ConversationRuntimeService disposition
-> FreshnessGuard before delivery -> OutboundDeliveryPort
```

- [x] **Step 2: Implement render orchestration**

Render triggers use the same InteractionAgent port with `mode="render"` and no intent/business mutation tools. Access-denied facts are rendered as `AccessDeniedTurn` in constrained render mode.

- [x] **Step 3: Implement timeout and async completion**

On `AgentTimedOut`, deliver the typed waiting text, record `pending_async_reply`, keep enough async state for `complete_async_reply`, then transition to `replied` or `failed` after first-answer validation.

- [x] **Step 4: Preserve stale safety**

Before each state-changing tool commit and before outbound delivery, use `ConversationRuntimeService.guard_state_change` through `FreshnessGuard`. If Task 6 raises `turn_superseded`, return the distinct `superseded` disposition and do not deliver stale output.

## Task 4: Green Verification And Commit

**Files:**
- Modify plan checkboxes in `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-turn-runtime.md`

- [x] **Step 1: Run focused turn tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn -v
```

Expected: all turn tests pass.

- [x] **Step 2: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: commands complete and identify any additional relevant checks.

- [x] **Step 3: Run routed checks**

At minimum rerun the focused turn tests and any suggested clean-rebuild/backend surface checks that apply to `coke/turn`, tests, and the child plan.

- [ ] **Step 4: Mark plan complete**

Set:

```markdown
**Plan Status:** complete
```

Only after verification passes.

- [ ] **Step 5: Commit**

## Task 5: Live GLM-5.1 Interaction Agent Debugging

**Files:**
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-turn-runtime.md`

- [x] **Step 1: Add failing tests for fenced JSON output and primary user input**

Add tests that prove:

```python
def test_fenced_json_agno_response_maps_to_output():
    fake_agent = FakeAgentInstance(
        content='```json\n{"type":"reply","segments":["ok"]}\n```'
    )
    agent = AgnoInteractionAgent(model=object(), agent_factory=FakeAgentFactory(fake_agent))

    result = agent.invoke(_request(memory_enabled=True))

    assert result.output == {"type": "reply", "segments": ["ok"]}


def test_inbound_text_is_sent_as_primary_agent_input_with_context_supporting():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agent),
    )

    agent.invoke(_request(memory_enabled=True, text="提醒我明天早上9点跑步"))

    prompt = fake_agent.calls[0]["input"]
    assert prompt.startswith("User message:\n提醒我明天早上9点跑步")
    assert "Trusted context:" in prompt
    assert '"payload"' not in prompt.split("Trusted context:", 1)[0]
```

- [x] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py -v
```

Expected: the fenced JSON test fails with `result.output is None`; the primary input test fails because the prompt is the whole JSON payload.

- [x] **Step 3: Implement minimal Interaction Agent fix**

Change only the agent side:

```python
def _agent_input(request: AgentRequest) -> str:
    user_text = _user_text(request)
    support_payload = _input_payload(request)
    return "\n\n".join(
        (
            f"User message:\n{user_text}",
            "Trusted context:\n"
            + json.dumps(support_payload, ensure_ascii=False, default=str),
        )
    )
```

Use `_agent_input(request)` in `agent.run(...)`, add a narrow helper that extracts `request.payload["text"]` when it is a string, and update `_mapping_or_none` to strip a markdown JSON code fence or surrounding prose before `json.loads`. Do not change `coke/turn/output_protocol.py`.

- [x] **Step 4: Verify the focused tests pass**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py -v
```

Expected: all interaction-agent unit tests pass.

- [x] **Step 5: Run full unit verification**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: full unit suite passes.

- [x] **Step 6: Restart the live worker and verify live reminder and greeting turns**

Run the worker restart commands from the live-debugging request, then post:

```bash
TS=$(date +%s); curl -sS -X POST http://127.0.0.1:8000/webhooks/whatsapp/evolution -H 'Content-Type: application/json' -d "{\"event\":\"messages.upsert\",\"instance\":\"coke\",\"data\":{\"key\":{\"remoteJid\":\"15551239001@s.whatsapp.net\",\"fromMe\":false,\"id\":\"MSG_${TS}\"},\"pushName\":\"olivers\",\"message\":{\"conversation\":\"提醒我明天早上9点跑步\"},\"messageTimestamp\":${TS}}}"
```

Then inspect:

```bash
psql -h /var/run/postgresql -d coke_local -c "SELECT kind,content,next_fire_at FROM reminder; SELECT disposition,reason_code FROM output_disposition ORDER BY created_at DESC LIMIT 3; SELECT direction,substring(text,1,120) FROM message WHERE direction='outbound' ORDER BY created_at DESC LIMIT 3;"
```

Expected: exactly one new timed running reminder around tomorrow 09:00, latest turn disposition `replied`, and an outbound message row. Repeat with `你好`; expected: `replied`, outbound message row, and no new reminder.

- [x] **Step 7: Mark plan complete and commit**

After unit and live verification pass, set:

```markdown
**Plan Status:** complete
```

Then commit the plan, test, and agent changes in one coherent commit.

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-turn-runtime.md coke/turn tests/unit/coke/turn
git commit -m "feat: implement clean turn orchestration"
```
