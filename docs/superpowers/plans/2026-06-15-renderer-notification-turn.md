# NotificationTurn Renderer Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route `NotificationTurn` system render turns through the stateless Express-style renderer instead of the legacy Interaction Agent.

**Architecture:** Keep the current `Plan -> Execute -> Express -> Close` inbound path unchanged. Add a render port to `TurnRunner` and adapt `NotificationTurn` trusted facts into an `ExpressRequest`, then reuse existing commit, delivery, and notification lifecycle recording. This first stage does not migrate `ReminderFireTurn`; its existing title/time/fact guard stays in place until a later render contract carries equivalent checks.

**Tech Stack:** Python, pytest, Coke clean turn runtime, `ExpressAgent`, `TurnRunner`, `ConversationRuntimeService`.

---

### Task 1: Lock NotificationTurn To Renderer Instead Of Interaction

**Files:**
- Modify: `tests/unit/coke/turn/test_turn_runner.py`

- [ ] **Step 1: Write the failing test**

Replace the old `test_render_turn_stays_on_render_agent_path` expectation with this test:

```python
class RecordingRenderExpress:
    def __init__(self, segments: tuple[str, ...] = ("rendered notification",)) -> None:
        self.segments = segments
        self.requests = []

    def render(self, request):
        self.requests.append(request)
        return self.segments

    async def render_streaming(self, request):
        self.requests.append(request)
        for segment in self.segments:
            yield segment


def test_notification_turn_uses_renderer_not_interaction_agent(harness):
    harness["runner"].turn_pipeline = ExplodingTurnPipeline()
    renderer = RecordingRenderExpress()
    harness["runner"].render_express = renderer
    trigger = TurnTrigger(
        trigger_id="notification:render",
        trigger_type="NotificationTurn",
        mode=TurnMode.RENDER,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        payload={
            "notification_fact_id": "notification_fact_1",
            "notification_fact": {
                "id": "notification_fact_1",
                "type": "shared_reminder_created",
                "facts": {
                    "actor_display_name": "Alice",
                    "title": "Lunch",
                    "status": "created",
                },
                "facts_hash": "hash_1",
            },
        },
    )

    result = harness["runner"].run_render_turn(trigger)

    assert result.disposition == "replied"
    assert result.visible_text == "rendered notification"
    assert harness["agent"].requests == []
    assert len(renderer.requests) == 1
    request = renderer.requests[0]
    assert request.turn_id == result.turn_id
    assert request.account_id == "account_1"
    assert request.payload["trigger_type"] == "NotificationTurn"
    assert request.settled_outcome.outcomes[0].status == "notification"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_notification_turn_uses_renderer_not_interaction_agent -q`

Expected: FAIL because `TurnRunner` has no `render_express` attribute or still invokes `interaction_agent`.

### Task 2: Add NotificationTurn Renderer Adapter

**Files:**
- Modify: `coke/turn/runner.py`

- [ ] **Step 1: Add runner constructor wiring**

Add an optional constructor parameter and field:

```python
render_express: Any | None = None,
```

```python
self.render_express = render_express
```

- [ ] **Step 2: Add a NotificationTurn render branch**

Inside `_run_render_with_gate`, after context assembly and before `_invoke_agent_and_record`, call a new helper when `trigger.trigger_type == "NotificationTurn"` and `self.render_express is not None`:

```python
if trigger.trigger_type == "NotificationTurn" and self.render_express is not None:
    return self._render_notification_with_express(trigger, context)
```

- [ ] **Step 3: Implement `_render_notification_with_express`**

Use `ExpressRequest`, `SettledOutcome`, `ActionOutcome`, and `ValidatedOutput` to render and record a visible reply:

```python
def _render_notification_with_express(self, trigger: TurnTrigger, context: Any) -> TurnRunResult:
    request = ExpressRequest(
        turn_id=context.freshness_guard.turn_id,
        conversation_id=trigger.conversation_id,
        account_id=trigger.account_id,
        current_time=str(context.trusted_facts.get("current_time") or ""),
        default_timezone=str(context.trusted_facts.get("default_timezone") or "UTC"),
        settled_outcome=SettledOutcome(
            outcomes=(
                ActionOutcome(
                    category="done",
                    status="notification",
                    data={
                        "trigger_type": trigger.trigger_type,
                        "notification_fact_id": trigger.payload.get("notification_fact_id"),
                        "notification_fact": trigger.payload.get("notification_fact"),
                        "recipient_account_ids": trigger.payload.get("recipient_account_ids"),
                    },
                ),
            )
        ),
        persona=str(context.trusted_facts.get("persona") or ""),
        assistant_name=str(context.trusted_facts.get("assistant_name") or "Coke"),
        user_address_name=str(context.trusted_facts.get("user_address_name") or ""),
        payload={
            "trigger_type": trigger.trigger_type,
            "trigger_payload": dict(trigger.payload),
            "turn_source": context.trusted_facts.get("turn_source"),
        },
        run_id=_agent_run_id_for_trigger(trigger, fallback=context.freshness_guard.turn_id),
    )
    try:
        segments = tuple(self.render_express.render(request))
    except Exception as error:
        return self._record_invalid_render_output(
            trigger=trigger,
            turn_id=context.freshness_guard.turn_id,
            reason_code=getattr(error, "code", None) or "notification_render_failed",
        )
    validated = ValidatedOutput(
        valid=True,
        kind="reply",
        segments=segments,
        reason_code="reply_ready",
    )
    validated = _validate_for_trigger(trigger, validated)
    return self._record_validated_output(
        turn_id=context.freshness_guard.turn_id,
        trigger=trigger,
        validated=validated,
    )
```

- [ ] **Step 4: Run the focused test**

Run: `.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_notification_turn_uses_renderer_not_interaction_agent -q`

Expected: PASS.

### Task 3: Wire Composition To Use Express For Render Turns

**Files:**
- Modify: `coke/composition.py`
- Modify: `tests/integration/coke/test_runtime_wiring.py`
- Modify: `tests/unit/coke/settings/test_settings_composition.py`

- [ ] **Step 1: Wire `turn_express` into `TurnRunner`**

Pass `render_express=turn_express` when constructing `TurnRunner`.

- [ ] **Step 2: Add composition assertion**

In `test_composition_exposes_active_turn_pipeline`, assert:

```python
assert runtime.turn_runner.render_express is runtime.turn_pipeline._express
```

- [ ] **Step 3: Add runtime wiring assertion**

In `test_runtime_wires_media_text_resolver_when_media_models_are_configured`, assert:

```python
assert runtime.turn_runner.render_express.model.api_key == "deepseek-key"
assert runtime.turn_runner.render_express.model.id == "deepseek-v4-flash"
```

- [ ] **Step 4: Run wiring tests**

Run: `.venv/bin/python -m pytest tests/unit/coke/settings/test_settings_composition.py::test_composition_exposes_active_turn_pipeline tests/integration/coke/test_runtime_wiring.py::test_runtime_wires_media_text_resolver_when_media_models_are_configured -q`

Expected: PASS.

### Task 4: Document The First-Stage Boundary

**Files:**
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Update turn pipeline wording**

State that inbound visible prose and migrated system render turns use the stateless Express-style renderer, while unmigrated render turns still use legacy render-mode Interaction until their facts and guards are ported.

- [ ] **Step 2: Run documentation checks**

Run: `zsh scripts/check`

Expected: PASS.

### Task 5: Targeted Verification And Commit

**Files:**
- Modify: test/code/docs files from prior tasks

- [ ] **Step 1: Run targeted runtime tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/coke/turn/test_turn_runner.py::test_notification_turn_uses_renderer_not_interaction_agent \
  tests/unit/coke/settings/test_settings_composition.py::test_composition_exposes_active_turn_pipeline \
  tests/integration/coke/test_runtime_wiring.py::test_runtime_wires_media_text_resolver_when_media_models_are_configured \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run diff-aware routing**

Run: `zsh scripts/suggest-verification --base HEAD~1`

Expected: suggested surface includes runtime and/or repo docs. Run the suggested command.

- [ ] **Step 3: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-06-15-renderer-notification-turn.md docs/ARCHITECTURE.md coke/turn/runner.py coke/composition.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/settings/test_settings_composition.py tests/integration/coke/test_runtime_wiring.py
git commit -m "refactor(turn): route notifications through renderer"
```
