# Coke Clean Rebuild Turn Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build The Turn orchestration slice with injected Agno/LLM/domain ports, the real Task 6 conversation ledger, and the required interactive/render mode contracts.

**Architecture:** The runner owns the pipeline shape and delegates all business work to injected ports. ConversationRuntimeService remains the ledger/disposition source, ConversationLockManager remains the per-conversation lock source, and this slice only defines the narrow turn-time ports that later T13 wiring will bind to real domains and Agno. The modules stay focused: gate, context, interpreter, focus, reference resolution, freshness, memory, agent, output protocol, and runner.

**Tech Stack:** Python 3.12, dataclasses, Protocol ports, pytest, in-memory fakes, Task 6 `coke.domains.conversation_runtime`, Task 6 `coke.turn.locks`.

---

**Plan Status:** complete
**Status Date:** 2026-05-31
**Freshness Check:** Checked against current `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md` Task 7 and architecture-watch notes, requirements §5.4, target architecture §1/§3.3/§4/§9 invariants, `coke/schema.py`, Task 6 conversation runtime, and existing domain layering patterns.
**Verification Note:** Turn implementation and backend unit surface pass. The routed `repo-os-docs` check is blocked by existing ownership-registry references to removed legacy `memo-runtime` and nested `gateway` files; that cleanup is outside Task 7's allowed file scope.
**Live Debugging Addendum (2026-05-30):** The local live stack showed real GLM-5.1 Interaction Agent turns failing before reminder creation because fenced JSON was rejected and the actual inbound text was buried inside a JSON context blob. Live verification also exposed an Agno `kwargs` tool-argument wrapper and a detector prompt-shape issue for non-recurring reminders. This addendum keeps the fix inside the turn-runtime/Interaction Agent + detector/tool boundary: strict output validation remains unchanged, reminder field extraction remains inside the reminder tool, and no fallback prose or regex intent routing is added.
**Notification Render Bugfix Addendum (2026-05-31):** Live testing found two product-prose regressions inside the turn-runtime/Interaction Agent boundary: shared-reminder creation replies described a receiver confirmation step, and `NotificationTurn` render mode produced generic placeholder copy even when notification facts contained the creator/title/time/timezone/duration. This addendum keeps the single-prose-producer invariant: the Interaction Agent still generates final text, render mode still has no mutation tools, and the runtime only injects trusted structured facts.
**Current-Time Prompt Addendum (2026-05-31):** The reminder detector already receives authoritative account-local `now`; this task only injects fresh account-local `current_time` into Interaction Agent trusted facts for interactive and render turns so the existing prompt environment block can render it. Do not change time parsing, detector behavior, schemas, fallback prose, routing, or domain contracts.

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

## Task 6: Notification Render Prose Bugfix

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-turn-runtime.md`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`
- Modify: `tests/unit/coke/worker/test_notification_render_trigger.py`
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `coke/worker/__main__.py`

- [x] **Step 1: Write failing Interaction Agent prompt tests**

Add tests that invoke `AgnoInteractionAgent` with fake Agno output and assert the generated system instructions:

```python
def test_shared_reminder_success_prompt_forbids_confirmation_flow_language():
    instructions = "\n".join(factory.agent_kwargs[0]["instructions"])
    assert "immediately active" in instructions
    assert "waiting for confirmation" in instructions
    assert "accept/reject" in instructions

def test_notification_render_prompt_requires_structured_fact_grounding():
    instructions = "\n".join(factory.agent_kwargs[0]["instructions"])
    assert "Render mode" in instructions
    assert "notification facts" in instructions
    assert "generic placeholder" in instructions
```

- [x] **Step 2: Write failing notification render facts test**

Add a render-mode unit test that passes a `NotificationTurn` request with structured facts:

```python
request = _render_request(
    payload={
        "notification_fact": {
            "type": "shared_reminder_created",
            "facts": {
                "actor_display_name": "Alice",
                "title": "Lunch",
                "time": "2026-06-01T12:00:00",
                "timezone": "Asia/Tokyo",
                "duration_minutes": 45,
            },
            "facts_hash": "hash_1",
        }
    }
)
```

Assert the agent input has a dedicated render context section containing `Alice`, `Lunch`, `2026-06-01T12:00:00`, `Asia/Tokyo`, and `45`, so a model cannot miss the facts inside a generic payload blob.

- [x] **Step 3: Write failing worker hydration test**

Add `tests/unit/coke/worker/test_notification_render_trigger.py` with an in-memory runtime fake whose social-scheduling repository returns a `NotificationFact`. Call `_turn_trigger_from_event()` for topic `turn.notification` with only `notification_fact_id`, `facts_hash`, and recipient ids. Assert the resulting `TurnTrigger.payload["notification_fact"]["facts"]` contains title/time/timezone/duration and no prose keys.

- [x] **Step 4: Implement minimal render context and prompt fix**

In `coke/llm/agno_interaction_agent.py`, add render-mode instructions requiring:

```text
Render mode must not call tools or imply business mutation.
For NotificationTurn, render only from notification facts and error_facts.
Include actor/who, title/object, time, timezone, duration, and status when present.
Do not use generic placeholder copy such as "go check it out".
Shared-reminder creation is immediately active; never say receivers must confirm, accept, reject, or approve it.
```

Also add a concise `Render context:` block before `Trusted context:` that extracts `notification_fact`, `facts`, `error_facts`, and `facts_hash` from the request payload when present.

- [x] **Step 5: Implement notification fact hydration in the render trigger path**

In `coke/worker/__main__.py`, when handling `turn.notification`, use the existing social-scheduling repository to find the `notification_fact_id` from `list_notification_facts()`. Add a `notification_fact` payload object with `id`, `type`, `actor_account_id`, `object_type`, `object_id`, `status`, `facts`, and `facts_hash`. If the fact is not found, leave the payload unchanged so the turn fails through existing missing-context behavior instead of inventing facts.

- [x] **Step 6: Run red tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_shared_reminder_success_prompt_forbids_confirmation_flow_language tests/unit/coke/llm/test_interaction_agent.py::test_notification_render_prompt_requires_structured_fact_grounding tests/unit/coke/llm/test_interaction_agent.py::test_render_notification_context_exposes_structured_facts_to_agent tests/unit/coke/worker/test_notification_render_trigger.py::test_notification_render_trigger_hydrates_structured_facts_from_repository -v
```

Expected before implementation: the tests fail because the instructions do not name these contracts and the notification render trigger does not hydrate the structured fact.

- [x] **Step 7: Run green focused tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/worker/test_notification_render_trigger.py -v
```

Expected after implementation: all focused tests pass.

- [x] **Step 8: Run required full unit surface and diff-aware routing**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: the backend unit surface passes. Review-trigger is a non-blocking risk report; record any suggested extra checks or blockers before commit.

- [x] **Step 9: Mark plan complete and commit**

After verification passes, set:

```markdown
**Plan Status:** complete
```

Then commit the plan, tests, and implementation together:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-turn-runtime.md tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/worker/test_notification_render_trigger.py coke/llm/agno_interaction_agent.py coke/worker/__main__.py
git commit -m "fix: ground notification render prose in facts"
```

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

## Task 6: Inject Account-Local Current Time Into Interaction Agent Prompt

**Files:**
- Modify: `coke/turn/runner.py`
- Modify: `coke/composition.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-turn-runtime.md`

- [x] **Step 1: Write failing tests for interactive, dynamic, and render trusted facts**

In `tests/unit/coke/turn/test_turn_runner.py`, add a mutable clock, let `FakeGatePort` expose `default_timezone`, and add tests with fixed UTC instants that must render as account-local ISO strings:

```python
class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def test_inbound_agent_trusted_facts_include_account_local_current_time_and_prompt_environment(harness):
    harness["clock"].value = datetime(2026, 5, 31, 6, 2, tzinfo=UTC)
    harness["gate_port"].trust_facts["default_timezone"] = "Asia/Shanghai"

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    assert request.trusted_facts["default_timezone"] == "Asia/Shanghai"
    assert request.trusted_facts["current_time"] == "2026-05-31T14:02:00+08:00"
    rendered = agno_agent_module.render_prompt_blocks(
        agno_agent_module.build_prompt_blocks(request)
    )
    assert '<trusted_block name="environment">' in rendered
    assert '"default_timezone": "Asia/Shanghai"' in rendered
    assert '"current_time": "2026-05-31T14:02:00+08:00"' in rendered


def test_each_inbound_turn_uses_fresh_current_time(harness):
    harness["gate_port"].trust_facts["default_timezone"] = "Asia/Shanghai"
    harness["clock"].value = datetime(2026, 5, 31, 6, 2, tzinfo=UTC)
    harness["runner"].run_inbound_turn(harness["trigger"])

    harness["runtime"].record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="second",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    harness["clock"].value = datetime(2026, 5, 31, 6, 7, tzinfo=UTC)
    second_trigger = TurnTrigger(
        trigger_id="inbound:provider:message-2",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={"text": "second"},
    )
    harness["runner"].run_inbound_turn(second_trigger)

    assert harness["agent"].requests[-2].trusted_facts["current_time"] == (
        "2026-05-31T14:02:00+08:00"
    )
    assert harness["agent"].requests[-1].trusted_facts["current_time"] == (
        "2026-05-31T14:07:00+08:00"
    )


def test_render_turn_trusted_facts_include_account_local_current_time(harness):
    harness["clock"].value = datetime(2026, 5, 31, 6, 2, tzinfo=UTC)

    result = harness["runner"].run_render_turn(
        TurnTrigger(
            trigger_id="reminder_fire:account_1:2026-05-31T06:02:00+00:00",
            trigger_type="ReminderFireTurn",
            mode=TurnMode.RENDER,
            conversation_id=harness["trigger"].conversation_id,
            account_id="account_1",
            payload={"fire_ids": ["fire_1"]},
        )
    )

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    assert request.trusted_facts["default_timezone"] == "Asia/Shanghai"
    assert request.trusted_facts["current_time"] == "2026-05-31T14:02:00+08:00"
```

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py -q
```

Expected before implementation: failures show `current_time` is missing from trusted facts and the prompt environment block.

- [x] **Step 2: Implement fresh account-local time facts in the runner**

In `coke/turn/runner.py`, inject the composition clock and optional account-timezone resolver:

```python
from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

class TurnRunner:
    def __init__(..., now: Callable[[], datetime] | None = None,
                 account_timezone: Callable[[str], str | None] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self._account_timezone = account_timezone

def _trusted_facts_for_agent(..., now: Callable[[], datetime],
                             account_timezone: Callable[[str], str | None] | None = None,
                             semantic_decision: SemanticDecision | None = None) -> dict[str, Any]:
    facts = {**dict(trust_facts), "turn_source": _turn_source_for_trigger(trigger)}
    facts.update(_current_time_facts(facts, trigger=trigger, now=now, account_timezone=account_timezone))
    if semantic_decision is not None:
        facts["semantic_decision"] = _semantic_decision_fact(semantic_decision)
```

Use `_trusted_facts_for_agent(...)` for both `run_inbound_turn` and `_run_render_with_gate`. `_current_time_facts` must choose `default_timezone` from trusted facts, payload, account resolver, then `UTC`; convert `now()` to that timezone; return `{"default_timezone": timezone_name, "current_time": local_now.isoformat()}`. If `now()` is naive, treat it as UTC. Invalid timezone names fall back to `UTC`.

- [x] **Step 3: Pass the composition clock and account timezone resolver**

In `coke/composition.py`, pass the existing runtime `now` callable into `TurnRunner` and provide an account timezone resolver from IdentityAccess:

```python
turn_runner = TurnRunner(
    ...,
    now=now,
    account_timezone=lambda account_id: _account_default_timezone(
        identity_access_service, account_id
    ),
)


def _account_default_timezone(
    identity_access_service: IdentityAccessService, account_id: str
) -> str:
    account = identity_access_service.repository.get_account(account_id)
    return account.default_timezone if account is not None else "UTC"
```

- [x] **Step 4: Verify focused tests pass**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py -q
```

Expected after implementation: turn-runner tests pass, including the different-now proof and render-turn proof.

- [x] **Step 5: Run required local verification**

Run from the worktree root:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: unit and integration tests pass; verification routing and risk report complete. `review-trigger` is non-blocking.

- [x] **Step 6: Commit the local fix**

After local verification passes, commit:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-turn-runtime.md coke/turn/runner.py coke/composition.py tests/unit/coke/turn/test_turn_runner.py
git commit -m "fix: inject current time into agent environment"
```

- [x] **Step 7: Redeploy and live-verify gcp-coke coke-clean**

Before deploy, take a rollback snapshot and preserve `coke-clean/.env`, connected accounts, connected channels, and `evolution-*` / connector state. Redeploy current `main` non-disruptively using `docs/deploy.md`: run alembic upgrade head, deployment checks, restart only Coke clean services, and do not recreate accounts or channels.

On the box, verify:

```bash
curl -fsS http://127.0.0.1:8000/api/auth/me
curl -fsS http://127.0.0.1:8000/api/channels
```

Drive one inbound turn through the existing connected channel, then inspect `ai.agno_sessions` or the available debug/store path for the latest Interaction Agent prompt. Expected: the prompt contains `<trusted_block name="environment">` with non-empty `current_time` and `default_timezone`, both channels are still `connected`, and connector `session_count=2`.

Live verification passed on `gcp-coke` `coke-clean`: rollback snapshot `20260531T070559Z` exists; `.env` hash stayed `889fb8a770a0bba2d40c26748190962c4861812f30a15febee127890c1fef2e3`; alembic upgrade/check passed; API health and web login returned 200; connector health reported `connected_session_count=2`; the marked live turn `time-smoke-direct-20260531T071443Z` produced an Agno prompt environment block with `default_timezone` `Asia/Shanghai` and `current_time` `2026-05-31T15:15:00.735866+08:00`.

- [x] **Step 8: Mark plan complete**

After verification and live proof pass, set:

```markdown
**Plan Status:** complete
```

Commit the final plan checkbox update if it was not included in the fix commit.
