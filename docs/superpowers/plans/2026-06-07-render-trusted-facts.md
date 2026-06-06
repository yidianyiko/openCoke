# Render Trusted Facts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Isolate system render turns from chat history and render reminder-fire and availability answers from trusted structured facts.

**Architecture:** Render-mode Agno construction disables chat history while interactive turns keep it. Reminder-fire turns hydrate `fire_ids` into a trusted `domain_result` before the Interaction Agent runs, then a structural guard reconciles the reply against those facts and falls back safely on mismatch. Availability tool facts expose only public display name plus busy/free windows.

**Tech Stack:** Python, pytest, Agno agent construction, Coke TurnRunner, Reminder and SocialScheduling domain services.

---

## File Structure

- Modify `coke/llm/agno_interaction_agent.py`
  - Add a small render-history policy helper.
  - Keep existing prompt blocks and persona behavior.
  - No render-mode tools and no deterministic normal renderer.
- Modify `tests/unit/coke/llm/test_interaction_agent.py`
  - Prove interactive turns keep Agno history.
  - Prove render turns disable Agno history.
  - Prove reminder-fire trusted facts appear in the `domain_result` block.
- Modify `coke/domains/reminder/models.py`
  - Add `ReminderFireRenderFact`.
- Modify `coke/domains/reminder/service.py`
  - Add read-only `reminder_fire_render_facts(...)`.
- Modify `coke/turn/runner.py`
  - Add an injected reminder-fire facts port.
  - Hydrate `ReminderFireTurn` trusted facts during render context assembly.
  - Apply reminder-fire structural validation before recording/delivery.
- Modify `coke/composition.py`
  - Pass `ReminderService` to `TurnRunner`.
  - Include availability `friend_display_name` in public tool facts.
- Modify `coke/domains/social_scheduling/availability.py`
  - Add optional `friend_display_name` to `FriendAvailability`.
- Modify `coke/domains/social_scheduling/service.py`
  - Populate `friend_display_name` from the public display-name resolver.
- Modify `tests/unit/coke/turn/test_turn_runner.py`
  - Add fake reminder-fire facts provider.
  - Cover hydration and guard fail-closed cases.
- Modify `tests/unit/coke/test_social_scheduling_tool_adapter.py`
  - Cover public-only availability fact serialization.
- Modify `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
  - Cover service-level friend display name on availability results.
- Modify `docs/ARCHITECTURE.md`
  - Document render-mode history isolation and trusted render fact blocks.

## Task 1: Render Agent History Isolation

**Files:**
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`
- Modify: `coke/llm/agno_interaction_agent.py`

- [ ] **Step 1: Write failing tests for history policy**

Add tests near the existing Agno construction tests:

```python
def test_interactive_agent_construction_keeps_chat_history_enabled():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_request(memory_enabled=True))

    assert factory.agent_kwargs[0]["add_history_to_context"] is True


def test_render_agent_construction_disables_chat_history_as_fact_source():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_render_request(trigger_type="ReminderFireTurn", payload={"fire_ids": ["fire_1"]}))

    assert factory.agent_kwargs[0]["add_history_to_context"] is False
    assert factory.agent_kwargs[0]["add_memories_to_context"] is True
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_interactive_agent_construction_keeps_chat_history_enabled tests/unit/coke/llm/test_interaction_agent.py::test_render_agent_construction_disables_chat_history_as_fact_source -v
```

Expected: the render test fails because `_build_agent()` still passes
`add_history_to_context=True`.

- [ ] **Step 3: Implement the minimal history policy**

In `coke/llm/agno_interaction_agent.py`, add:

```python
def _add_history_to_context(request: AgentRequest) -> bool:
    return request.mode != TurnMode.RENDER
```

Change `_build_agent()`:

```python
add_history_to_context=_add_history_to_context(request),
```

- [ ] **Step 4: Run the tests and verify GREEN**

Run the same pytest command from Step 2.

Expected: both tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add coke/llm/agno_interaction_agent.py tests/unit/coke/llm/test_interaction_agent.py
git commit -m "fix: isolate render agent chat history" -m "Co-Authored-By: Codex <noreply@openai.com>"
```

## Task 2: Reminder-Fire Trusted Fact Hydration

**Files:**
- Modify: `coke/domains/reminder/models.py`
- Modify: `coke/domains/reminder/service.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`

- [ ] **Step 1: Write a failing service-level hydration test**

Add imports in `tests/unit/coke/turn/test_turn_runner.py`:

```python
from coke.domains.reminder.models import Reminder, ReminderFire
```

Add this focused test near other reminder service tests:

```python
def test_reminder_service_hydrates_fire_ids_for_render_facts():
    now = datetime(2026, 6, 6, 4, 0, tzinfo=UTC)
    repository = InMemoryReminderRepository()
    service = ReminderService(
        repository=repository,
        now=lambda: now,
        friend_identifiers=lambda shared_id, viewer_id: ["Oliver"] if shared_id == "shared_1" and viewer_id == "account_1" else [],
    )
    reminder = Reminder(
        id="reminder_1",
        owner_account_id="account_1",
        content="和Oliver喝咖啡",
        content_hash="hash_1",
        kind="shared_projection",
        next_fire_at=datetime(2026, 6, 6, 6, 0, tzinfo=UTC),
        recurrence_rule={},
        captured_timezone="Asia/Shanghai",
        duration_minutes=45,
        lifecycle="active",
        hidden_from_calendar=False,
        shared_reminder_id="shared_1",
        created_at=now,
        updated_at=now,
    )
    fire = ReminderFire(
        id="fire_1",
        reminder_id="reminder_1",
        occurrence_key="2026-06-06T06:00:00+00:00",
        due_at=datetime(2026, 6, 6, 6, 0, tzinfo=UTC),
        fire_state="claimed",
        delivery_result=None,
        handled_at=None,
        completed_at=None,
        missed_catch_up=False,
        created_at=now,
        updated_at=now,
    )
    repository.add_reminder(reminder)
    repository.add_fire(fire)

    facts = service.reminder_fire_render_facts(
        owner_account_id="account_1",
        fire_ids=["fire_1"],
        viewer_account_id="account_1",
    )

    assert facts[0].fire_id == "fire_1"
    assert facts[0].reminder_id == "reminder_1"
    assert facts[0].title == "和Oliver喝咖啡"
    assert facts[0].local_due_at == "2026-06-06T14:00:00+08:00"
    assert facts[0].timezone == "Asia/Shanghai"
    assert facts[0].duration_minutes == 45
    assert facts[0].kind == "shared_projection"
    assert facts[0].participant_names == ("Oliver",)
```

- [ ] **Step 2: Run the hydration test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_reminder_service_hydrates_fire_ids_for_render_facts -v
```

Expected: fails because `ReminderService.reminder_fire_render_facts` does not exist.

- [ ] **Step 3: Add the render fact dataclass**

In `coke/domains/reminder/models.py`, add:

```python
@dataclass(frozen=True, slots=True)
class ReminderFireRenderFact:
    fire_id: str
    reminder_id: str
    title: str
    owner_account_id: str
    viewer_account_id: str
    due_at: str
    local_due_at: str
    timezone: str
    duration_minutes: int
    kind: ReminderKind
    shared_reminder_id: str | None
    participant_names: tuple[str, ...] = ()
```

Import it in `coke/domains/reminder/service.py`.

- [ ] **Step 4: Add the service hydration method**

In `ReminderService`, add:

```python
def reminder_fire_render_facts(
    self,
    *,
    owner_account_id: str,
    fire_ids: list[str],
    viewer_account_id: str | None = None,
) -> list[ReminderFireRenderFact]:
    if not fire_ids:
        raise ReminderError("reminder_fire_ids_required")
    viewer_id = viewer_account_id or owner_account_id
    facts: list[ReminderFireRenderFact] = []
    for fire_id in fire_ids:
        fire = self._require_fire(fire_id)
        reminder = self._require_reminder(fire.reminder_id)
        if reminder.owner_account_id != owner_account_id:
            raise ReminderError("reminder_fire_not_found")
        timezone_name, timezone = _zoneinfo_or_utc(reminder.captured_timezone)
        due_at = fire.due_at if fire.due_at.tzinfo is not None else fire.due_at.replace(tzinfo=UTC)
        participant_names: tuple[str, ...] = ()
        if reminder.shared_reminder_id and self._friend_identifiers is not None:
            participant_names = tuple(
                self._friend_identifiers(reminder.shared_reminder_id, viewer_id)
            )
        facts.append(
            ReminderFireRenderFact(
                fire_id=fire.id,
                reminder_id=reminder.id,
                title=reminder.content,
                owner_account_id=reminder.owner_account_id,
                viewer_account_id=viewer_id,
                due_at=due_at.isoformat(),
                local_due_at=due_at.astimezone(timezone).isoformat(),
                timezone=timezone_name,
                duration_minutes=reminder.duration_minutes,
                kind=reminder.kind,
                shared_reminder_id=reminder.shared_reminder_id,
                participant_names=participant_names,
            )
        )
    return facts
```

Add helper near existing timezone helpers:

```python
def _zoneinfo_or_utc(timezone_name: str) -> tuple[str, ZoneInfo]:
    try:
        return timezone_name, ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return "UTC", ZoneInfo("UTC")
```

- [ ] **Step 5: Run the hydration test and verify GREEN**

Run the same pytest command from Step 2.

Expected: the hydration test passes.

- [ ] **Step 6: Commit Task 2**

```bash
git add coke/domains/reminder/models.py coke/domains/reminder/service.py tests/unit/coke/turn/test_turn_runner.py
git commit -m "feat: hydrate reminder fire render facts" -m "Co-Authored-By: Codex <noreply@openai.com>"
```

## Task 3: Inject Reminder-Fire Domain Result Into Render Context

**Files:**
- Modify: `coke/turn/runner.py`
- Modify: `coke/composition.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`

- [ ] **Step 1: Write failing runner and prompt tests**

Add a fake provider in `tests/unit/coke/turn/test_turn_runner.py`:

```python
class FakeReminderFireFacts:
    def __init__(self) -> None:
        self.calls = []

    def reminder_fire_render_facts(self, *, owner_account_id, fire_ids, viewer_account_id=None):
        self.calls.append(
            {
                "owner_account_id": owner_account_id,
                "fire_ids": list(fire_ids),
                "viewer_account_id": viewer_account_id,
            }
        )
        return [
            SimpleNamespace(
                fire_id="fire_1",
                reminder_id="reminder_1",
                title="和Oliver喝咖啡",
                owner_account_id="account_1",
                viewer_account_id="account_1",
                due_at="2026-06-06T06:00:00+00:00",
                local_due_at="2026-06-06T14:00:00+08:00",
                timezone="Asia/Shanghai",
                duration_minutes=45,
                kind="shared_projection",
                shared_reminder_id="shared_1",
                participant_names=("Oliver",),
            )
        ]
```

Pass it to the fixture `TurnRunner` and helper constructors as
`reminder_fire_facts=reminder_fire_facts`.

Add a runner test:

```python
def test_reminder_fire_render_turn_injects_trusted_domain_result(harness):
    result = harness["runner"].run_render_turn(
        TurnTrigger(
            trigger_id="reminder_fire:account_1:2026-06-06T06:00:00+00:00",
            trigger_type="ReminderFireTurn",
            mode=TurnMode.RENDER,
            conversation_id=harness["trigger"].conversation_id,
            account_id="account_1",
            payload={"fire_ids": ["fire_1"]},
        )
    )

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    domain_result = request.trusted_facts["domain_result"]
    assert domain_result["reply_contract"] == "render_reminder_fire"
    assert domain_result["facts"]["fire_ids"] == ["fire_1"]
    assert domain_result["facts"]["reminders"][0]["title"] == "和Oliver喝咖啡"
    assert domain_result["facts"]["reminders"][0]["local_due_at"] == "2026-06-06T14:00:00+08:00"
    assert harness["reminder_fire_facts"].calls[-1]["viewer_account_id"] == "account_1"
```

Add an LLM prompt test:

```python
def test_render_reminder_fire_context_exposes_trusted_domain_result_to_agent():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["和Oliver喝咖啡 14:00"]})
    agent = AgnoInteractionAgent(model=object(), agent_factory=FakeAgentFactory(fake_agent))

    result = agent.invoke(
        _render_request(
            trigger_type="ReminderFireTurn",
            payload={"fire_ids": ["fire_1"]},
            trusted_facts={
                "domain_result": {
                    "domain": "reminder",
                    "intent": "render reminder fire fact",
                    "action": "ReminderFireTurn",
                    "effect": "ready",
                    "intent_fulfilled": True,
                    "visible_summary": "和Oliver喝咖啡",
                    "reply_contract": "render_reminder_fire",
                    "facts": {
                        "viewer_account_id": "account_1",
                        "fire_ids": ["fire_1"],
                        "reminders": [
                            {
                                "fire_id": "fire_1",
                                "reminder_id": "reminder_1",
                                "title": "和Oliver喝咖啡",
                                "local_due_at": "2026-06-06T14:00:00+08:00",
                                "timezone": "Asia/Shanghai",
                                "duration_minutes": 45,
                                "kind": "shared_projection",
                            }
                        ],
                    },
                }
            },
        )
    )

    prompt = fake_agent.calls[0]["input"]
    assert "render_reminder_fire" in _block_text(prompt, "domain_result")
    assert "和Oliver喝咖啡" in _block_text(prompt, "domain_result")
    assert "2026-06-06T14:00:00+08:00" in _block_text(prompt, "domain_result")
    assert result.output["type"] == "reply"
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_reminder_fire_render_turn_injects_trusted_domain_result tests/unit/coke/llm/test_interaction_agent.py::test_render_reminder_fire_context_exposes_trusted_domain_result_to_agent -v
```

Expected: runner test fails because `TurnRunner` does not accept or call
`reminder_fire_facts`; prompt test may pass only after trusted facts are injected
manually and should remain a guard against prompt-block regressions.

- [ ] **Step 3: Add the runner port and domain-result builder**

In `coke/turn/runner.py`, add:

```python
class ReminderFireFactsPort(Protocol):
    def reminder_fire_render_facts(
        self,
        *,
        owner_account_id: str,
        fire_ids: list[str],
        viewer_account_id: str | None = None,
    ) -> list[Any]: ...
```

Add `reminder_fire_facts: ReminderFireFactsPort | None = None` to
`TurnRunner.__init__` and assign `self.reminder_fire_facts`.

Add helper:

```python
def _reminder_fire_domain_result(provider: ReminderFireFactsPort | None, trigger: TurnTrigger) -> dict[str, Any] | None:
    if trigger.trigger_type != "ReminderFireTurn":
        return None
    if provider is None:
        raise ValueError("reminder_fire_facts_unavailable")
    fire_ids = _string_list(trigger.payload.get("fire_ids"))
    facts = provider.reminder_fire_render_facts(
        owner_account_id=trigger.account_id,
        fire_ids=fire_ids,
        viewer_account_id=trigger.account_id,
    )
    reminders = [asdict(fact) if is_dataclass(fact) else dict(vars(fact)) for fact in facts]
    return {
        "domain": "reminder",
        "intent": "render reminder fire fact",
        "action": "ReminderFireTurn",
        "effect": "ready",
        "intent_fulfilled": True,
        "visible_summary": "; ".join(str(item.get("title") or "") for item in reminders),
        "reply_contract": "render_reminder_fire",
        "privacy_notes": ["Render only these reminder facts; do not use chat history for title, time, participant, duration, or kind."],
        "facts": {
            "viewer_account_id": trigger.account_id,
            "fire_ids": fire_ids,
            "reminders": reminders,
        },
    }
```

Use it in `_run_render_with_gate()` before `context_assembler.build()`:

```python
domain_result = _reminder_fire_domain_result(self.reminder_fire_facts, trigger)
if domain_result is not None:
    trusted_facts["domain_result"] = domain_result
```

Pass `domain_result=domain_result` into `context_assembler.build(...)`.

If the helper raises, mark the turn failed with that reason code and call
`_record_render_failure_lifecycle(...)`.

- [ ] **Step 4: Wire production composition**

In `coke/composition.py`, pass:

```python
reminder_fire_facts=reminder_service,
```

to the production `TurnRunner`.

- [ ] **Step 5: Run the tests and verify GREEN**

Run the same pytest command from Step 2.

Expected: both tests pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add coke/turn/runner.py coke/composition.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/llm/test_interaction_agent.py
git commit -m "feat: inject reminder fire trusted render facts" -m "Co-Authored-By: Codex <noreply@openai.com>"
```

## Task 4: Reminder-Fire Structural Fail-Closed Guard

**Files:**
- Modify: `coke/turn/runner.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`

- [ ] **Step 1: Write failing guard regression tests**

Add tests:

```python
def test_reminder_fire_wrong_title_falls_back_to_trusted_fact(harness):
    harness["agent"].queued_results = [
        AgentResult.completed({"type": "reply", "segments": ["11:40咖啡快到了"]}),
        AgentResult.completed({"type": "reply", "segments": ["11:40咖啡快到了"]}),
    ]

    result = harness["runner"].run_render_turn(_reminder_fire_trigger(harness))

    assert result.disposition == "replied"
    assert result.visible_text == "和Oliver喝咖啡 2026-06-06 14:00 Asia/Shanghai"
    assert harness["agent"].invocations == 2


def test_reminder_fire_wrong_time_falls_back_to_trusted_fact(harness):
    harness["agent"].queued_results = [
        AgentResult.completed({"type": "reply", "segments": ["和Oliver喝咖啡 11:40"]}),
        AgentResult.completed({"type": "reply", "segments": ["和Oliver喝咖啡 11:40"]}),
    ]

    result = harness["runner"].run_render_turn(_reminder_fire_trigger(harness))

    assert result.visible_text == "和Oliver喝咖啡 2026-06-06 14:00 Asia/Shanghai"


def test_reminder_fire_serialized_tool_call_falls_back_to_trusted_fact(harness):
    harness["agent"].queued_results = [
        AgentResult.completed({"type": "reply", "segments": ["<tool_call>query_reminder</tool_call>"]}),
        AgentResult.completed({"type": "reply", "segments": ["<tool_call>query_reminder</tool_call>"]}),
    ]

    result = harness["runner"].run_render_turn(_reminder_fire_trigger(harness))

    assert result.visible_text == "和Oliver喝咖啡 2026-06-06 14:00 Asia/Shanghai"


def test_reminder_fire_no_reply_falls_back_to_trusted_fact(harness):
    harness["agent"].queued_results = [
        AgentResult.completed({"type": "no_reply", "reason": "intentional_no_reply"}),
        AgentResult.completed({"type": "no_reply", "reason": "intentional_no_reply"}),
    ]

    result = harness["runner"].run_render_turn(_reminder_fire_trigger(harness))

    assert result.visible_text == "和Oliver喝咖啡 2026-06-06 14:00 Asia/Shanghai"
```

Add helper:

```python
def _reminder_fire_trigger(harness):
    return TurnTrigger(
        trigger_id="reminder_fire:account_1:2026-06-06T06:00:00+00:00",
        trigger_type="ReminderFireTurn",
        mode=TurnMode.RENDER,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        payload={"fire_ids": ["fire_1"]},
    )
```

- [ ] **Step 2: Run the guard tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_reminder_fire_wrong_title_falls_back_to_trusted_fact tests/unit/coke/turn/test_turn_runner.py::test_reminder_fire_wrong_time_falls_back_to_trusted_fact tests/unit/coke/turn/test_turn_runner.py::test_reminder_fire_serialized_tool_call_falls_back_to_trusted_fact tests/unit/coke/turn/test_turn_runner.py::test_reminder_fire_no_reply_falls_back_to_trusted_fact -v
```

Expected: tests fail because the runner accepts the model output or fails the
turn instead of retrying and falling back.

- [ ] **Step 3: Implement structural guard helpers**

In `coke/turn/runner.py`, add helpers:

```python
REMINDER_FIRE_VISIBLE_REPLY_REQUIRED = "reminder_fire_requires_visible_reply"
REMINDER_FIRE_FACT_MISMATCH = "reminder_fire_fact_mismatch"

def _validate_reminder_fire_output(request: AgentRequest, validated: ValidatedOutput) -> ValidatedOutput:
    if request.trigger_type != "ReminderFireTurn":
        return validated
    facts = _reminder_fire_guard_facts(request)
    if not facts:
        return ValidatedOutput(valid=False, kind=None, reason_code=REMINDER_FIRE_FACT_MISMATCH, retry_guidance="reminder_fire_trusted_facts_required")
    if not validated.valid or validated.kind != "reply":
        return ValidatedOutput(valid=False, kind=None, reason_code=REMINDER_FIRE_VISIBLE_REPLY_REQUIRED, retry_guidance="reminder_fire_must_reply_from_trusted_facts")
    text = "\n".join(validated.segments)
    if _contains_serialized_tool_call(text):
        return ValidatedOutput(valid=False, kind=None, reason_code=REMINDER_FIRE_FACT_MISMATCH, retry_guidance="serialized_tool_call_output_requires_native_tool_call")
    for fact in facts:
        title = str(fact.get("title") or "").strip()
        if not title or title not in text:
            return ValidatedOutput(valid=False, kind=None, reason_code=REMINDER_FIRE_FACT_MISMATCH, retry_guidance="reminder_fire_title_must_match_trusted_fact")
        if not _has_trusted_time_or_remaining_token(text, fact, request):
            return ValidatedOutput(valid=False, kind=None, reason_code=REMINDER_FIRE_FACT_MISMATCH, retry_guidance="reminder_fire_time_must_match_trusted_fact")
    return validated
```

Add small helpers for extracting facts, detecting serialized tool markers,
computing time labels from `local_due_at`, and computing remaining minutes from
`due_at - current_time`. Keep them token-based; do not add broad prose parsing.

Add fallback helper:

```python
def _minimal_reminder_fire_reply(request: AgentRequest) -> ValidatedOutput | None:
    facts = _reminder_fire_guard_facts(request)
    if not facts:
        return None
    lines = []
    for fact in facts:
        local_due = datetime.fromisoformat(str(fact["local_due_at"]))
        lines.append(
            f'{fact["title"]} {local_due:%Y-%m-%d %H:%M} {fact["timezone"]}'
        )
    return ValidatedOutput(valid=True, kind="reply", segments=tuple(lines), reason_code="reply_ready")
```

Use the guard in sync and async `_invoke_agent_and_record*()` after
`_validate_for_trigger(...)`. After the retry, if the second validation is still
invalid for `ReminderFireTurn`, call `_minimal_reminder_fire_reply(...)`; if it
returns `None`, record the failed disposition.

- [ ] **Step 4: Run guard tests and verify GREEN**

Run the same pytest command from Step 2.

Expected: all guard tests pass.

- [ ] **Step 5: Run focused runner render tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py -k "render or reminder_fire" -v
```

Expected: selected tests pass.

- [ ] **Step 6: Commit Task 4**

```bash
git add coke/turn/runner.py tests/unit/coke/turn/test_turn_runner.py
git commit -m "fix: fail closed on reminder fire render mismatches" -m "Co-Authored-By: Codex <noreply@openai.com>"
```

## Task 5: Availability Public Fact Shape

**Files:**
- Modify: `coke/domains/social_scheduling/availability.py`
- Modify: `coke/domains/social_scheduling/service.py`
- Modify: `coke/composition.py`
- Modify: `tests/unit/coke/test_social_scheduling_tool_adapter.py`
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`

- [ ] **Step 1: Write failing availability tests**

In `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`, add:

```python
def test_availability_result_includes_public_friend_display_name():
    service, _, _, reminder_availability = make_service({"requester", "friend"})
    reminder_availability.intervals["friend"] = []

    result = service.query_availability(
        requester_account_id="requester",
        friend_account_ids=["friend"],
        local_start=datetime(2026, 6, 1, 9, 0),
        local_end=datetime(2026, 6, 1, 10, 0),
        requester_timezone="Asia/Tokyo",
    )

    assert result.friend_display_name == "friend"
```

In `tests/unit/coke/test_social_scheduling_tool_adapter.py`, update the
availability fake to return:

```python
FriendAvailability(
    friend_account_id="friend_1",
    friend_display_name="Oliver",
    windows=[...],
)
```

and update the expected facts:

```python
"friend_display_name": "Oliver",
```

Also assert no private keys are present:

```python
serialized = result.facts["availability"][0]
assert set(serialized) == {"friend_account_id", "friend_display_name", "windows"}
assert set(serialized["windows"][0]) == {"start", "end", "state"}
```

- [ ] **Step 2: Run availability tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_availability_result_includes_public_friend_display_name tests/unit/coke/test_social_scheduling_tool_adapter.py::test_social_scheduling_tool_exposes_privacy_safe_availability_query -v
```

Expected: tests fail because `FriendAvailability` has no display-name field and
`_availability_facts()` omits it.

- [ ] **Step 3: Add display name to availability model and service**

In `coke/domains/social_scheduling/availability.py`, change:

```python
@dataclass(frozen=True, slots=True)
class FriendAvailability:
    friend_account_id: str
    windows: list[AvailabilityWindow]
    friend_display_name: str | None = None
```

In `SocialSchedulingService.query_availability()`, construct:

```python
FriendAvailability(
    friend_account_id=friend_account_id,
    friend_display_name=self.display_name_resolver(friend_account_id),
    windows=build_busy_free_windows(local_start, local_end, intervals),
)
```

- [ ] **Step 4: Serialize only public availability fields**

In `coke/composition.py`, update `_availability_facts()`:

```python
{
    "friend_account_id": item.friend_account_id,
    "friend_display_name": item.friend_display_name or item.friend_account_id,
    "windows": [window.to_public_dict() for window in item.windows],
}
```

- [ ] **Step 5: Run availability tests and verify GREEN**

Run the same pytest command from Step 2.

Expected: both tests pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add coke/domains/social_scheduling/availability.py coke/domains/social_scheduling/service.py coke/composition.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/social_scheduling/test_social_scheduling_service.py
git commit -m "fix: expose only public availability facts" -m "Co-Authored-By: Codex <noreply@openai.com>"
```

## Task 6: Architecture Doc And Focused Verification

**Files:**
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Write the architecture doc update**

In `docs/ARCHITECTURE.md`, update The Turn section after the render-mode
description with:

```markdown
Render-mode Interaction Agent construction disables Agno chat history as a fact
source. Render turns use trusted trigger facts, domain results, and dynamic
prompt blocks for product state; recent interactive chat may not supply title,
time, participant, delivery status, or privacy-bearing facts for system turns.
Reminder-fire render turns hydrate fire ids into trusted reminder facts before
the Interaction Agent runs and fail closed if the visible reply cannot reconcile
with those facts.
```

- [ ] **Step 2: Run docs and focused unit verification**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn tests/unit/coke/llm tests/unit/coke/social_scheduling tests/unit/coke/test_social_scheduling_tool_adapter.py -v
```

Expected: all selected tests pass.

- [ ] **Step 3: Run diff-aware routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: commands complete and identify the required surface. Run the suggested
surface command before final handoff.

- [ ] **Step 4: Commit Task 6**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs: document render trusted fact boundary" -m "Co-Authored-By: Codex <noreply@openai.com>"
```

## Final Verification

- [ ] Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn tests/unit/coke/llm tests/unit/coke/social_scheduling tests/unit/coke/test_social_scheduling_tool_adapter.py -v
```

- [ ] Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
```

- [ ] Run:

```bash
zsh scripts/review-trigger --base HEAD~1
```

- [ ] Run the suggested verification surface from `suggest-verification`.

- [ ] Record exact command outputs in the final report.

## Plan Self-Review

- Spec coverage: Tasks 1, 3, and 4 cover Track I and Track A; Task 5 covers
  Track E; Task 6 covers the canonical architecture-doc update.
- Placeholder scan: no plan steps contain deferred implementation placeholders.
- Type consistency: `ReminderFireRenderFact`, `reminder_fire_render_facts`,
  `friend_display_name`, and `render_reminder_fire` names are used consistently.
