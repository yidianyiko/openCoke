# Eva Regression Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Track J regression tests and evidence that bind Eva's production failures to visible text and durable runtime state without changing the integrated fixes.

**Architecture:** Add one dedicated conversation/runtime corpus file under the existing Python unit test surface. The tests use the real in-memory runtime, TurnRunner, output protocol, SocialSchedulingToolAdapter, ReminderService, SocialSchedulingService, and staged-command materializer; only provider, agent, semantic, and clock ports are faked.

**Tech Stack:** Python 3, pytest, in-memory Coke repositories/services, existing `TurnRunner` runtime seam, `artifacts/evidence/` for generated command output.

---

## Files

- Create: `tests/unit/coke/turn/test_eva_regression_corpus.py`
  - Owns the Track J Eva-shaped regression corpus.
  - Keeps compact local fakes for agent, delivery, semantic interpreter, gate,
    memory, Redis lock, reachability, and availability ports.
  - Uses real in-memory repositories and domain services for durable-state
    assertions.
- Create: `artifacts/evidence/2026-06-07-eva-regression-corpus/`
  - Stores targeted corpus pytest output and any additional smoke/eval output
    used for completion claims.
- Modify: `docs/superpowers/plans/2026-06-07-eva-regression-corpus.md`
  - Tick each checkbox as it is completed.

No production files should be modified. If a new regression fails because the
integrated runtime accepts the production-bad behavior, stop and report the
failing case instead of weakening the test.

### Task 1: Add Corpus Scaffolding And Reminder-Fire Cases

**Files:**
- Create: `tests/unit/coke/turn/test_eva_regression_corpus.py`
- Modify: `docs/superpowers/plans/2026-06-07-eva-regression-corpus.md`

- [ ] **Step 1: Write the corpus scaffolding and reminder-fire regression test**

Create `tests/unit/coke/turn/test_eva_regression_corpus.py` with these imports and helper classes:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import count
from types import SimpleNamespace
from typing import Any

import pytest

from coke.composition import SocialSchedulingToolAdapter
from coke.domains.conversation_runtime.repository import InMemoryConversationRuntimeRepository
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.domains.reminder.models import Reminder, ReminderFire
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService
from coke.domains.social_scheduling.availability import BusyInterval, ParticipantReachabilityPort, ReminderAvailabilityPort
from coke.domains.social_scheduling.models import Friendship, RecoverableSchedulingIntent
from coke.domains.social_scheduling.repository import InMemorySocialSchedulingRepository
from coke.domains.social_scheduling.service import SocialSchedulingService
from coke.turn.agent import AgentResult, AgentToolPorts
from coke.turn.context import TurnMode, TurnTrigger
from coke.turn.locks import ConversationLockManager
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.runner import DeliveryOutcome, TurnRunner
from coke.turn.semantic_interpreter import FollowUpAction, SemanticDecision
from coke.turn.staged_commands import StagedCommandMaterializer

EVA_NOW = datetime(2026, 6, 6, 2, 51, 34, tzinfo=UTC)
TRACEPARENT = "00-eva00000000000000000000000000000-1111111111111111-01"

class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

def id_factory():
    counter = count(1)
    return lambda prefix: f"{prefix}_{next(counter)}"

class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
    def set(self, name, value, nx=False, px=None):
        if nx and name in self.values:
            return False
        self.values[name] = value
        return True
    def get(self, name):
        return self.values.get(name)
    def pexpire(self, name, ttl_ms):
        return name in self.values
    def delete(self, name):
        existed = name in self.values
        self.values.pop(name, None)
        return 1 if existed else 0
    def acquire_lock(self, name: str, token: str, ttl_ms: int) -> bool:
        return bool(self.set(name, token, nx=True, px=ttl_ms))
    def get_token(self, name: str) -> str | None:
        return self.get(name)
    def extend_if_owned(self, name: str, token: str, ttl_ms: int) -> bool:
        return self.get(name) == token and bool(self.pexpire(name, ttl_ms))
    def release_if_owned(self, name: str, token: str) -> bool:
        if self.get(name) != token:
            return False
        return bool(self.delete(name))
```

Add `FakeGatePort`, `FakeSemanticInterpreter`, `FakeMemoryPort`,
`ScriptedAgent`, `CapturingDelivery`, `FakeReachability`,
`FakeReminderAvailability`, `_runtime_fixture()`, `_turn_runner()`,
`_record_inbound()`, `_inbound_trigger()`, and `_render_trigger()` local helpers.
The helpers must invoke real services and repositories, not mocked domain
results.

Add the reminder-fire test:

```python
@pytest.mark.parametrize(
    "title,due_at,local_due_at,bad_segments,expected_text",
    [
        (
            "和eva约11:30的午饭",
            datetime(2026, 6, 6, 3, 30, tzinfo=UTC),
            "2026-06-06T11:30:00+08:00",
            ["和 olivers 的咖啡快到啦，11:40 见~"],
            "和eva约11:30的午饭 2026-06-06 11:30 Asia/Shanghai",
        ),
        (
            "和Olivers约下午两点喝咖啡",
            datetime(2026, 6, 6, 6, 0, tzinfo=UTC),
            "2026-06-06T14:00:00+08:00",
            ["下午3点和 Oliver 喝咖啡在你可约范围内，没问题~"],
            "和Olivers约下午两点喝咖啡 2026-06-06 14:00 Asia/Shanghai",
        ),
        (
            "约olivers下午三点散步",
            datetime(2026, 6, 6, 7, 0, tzinfo=UTC),
            "2026-06-06T15:00:00+08:00",
            ["到时间啦，你和 Oliver 的咖啡局现在开始"],
            "约olivers下午三点散步 2026-06-06 15:00 Asia/Shanghai",
        ),
    ],
)
def test_eva_reminder_fire_uses_hydrated_fact_not_recent_wrong_chat(
    title: str,
    due_at: datetime,
    local_due_at: str,
    bad_segments: list[str],
    expected_text: str,
):
    env = _runtime_fixture(initial_text="下午3点和 Oliver 喝咖啡")
    _add_reminder_fire(
        env.reminder_repository,
        reminder_id="reminder_1",
        fire_id="fire_1",
        title=title,
        due_at=due_at,
        local_timezone="Asia/Shanghai",
    )
    env.agent.queued_results = [
        AgentResult.completed({"type": "reply", "segments": bad_segments}),
        AgentResult.completed({"type": "reply", "segments": bad_segments}),
    ]
    runner = _turn_runner(env)

    result = runner.run_render_turn(
        _render_trigger(env, fire_ids=["fire_1"], trigger_id=f"reminder_fire:{title}")
    )

    assert result.disposition == "replied"
    assert result.visible_text == expected_text
    request = env.agent.requests[-1]
    reminder_fact = request.trusted_facts["domain_result"]["facts"]["reminders"][0]
    assert reminder_fact["title"] == title
    assert reminder_fact["local_due_at"] == local_due_at
```

- [ ] **Step 2: Run the reminder-fire test**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_eva_regression_corpus.py::test_eva_reminder_fire_uses_hydrated_fact_not_recent_wrong_chat -q
```

Expected on this integration branch: either PASS because Tracks A/I are already
integrated, or FAIL exposing a real integrated defect. If it fails because the
test scaffolding is wrong, fix only test scaffolding.

- [ ] **Step 3: Tick Task 1 checkboxes in this plan**

Update this file so Task 1 completed steps use `- [x]`.

### Task 2: Add Friend-Correction And Availability Cases

**Files:**
- Modify: `tests/unit/coke/turn/test_eva_regression_corpus.py`
- Modify: `docs/superpowers/plans/2026-06-07-eva-regression-corpus.md`

- [ ] **Step 1: Add the `zihao就是olivers` recovery test**

Add a test that creates an open `RecoverableSchedulingIntent`, one active friend
named `Olivers`, a typed semantic follow-up action, and a scripted agent that
calls the real social-scheduling tool with the injected recovery facts:

```python
def test_eva_zihao_correction_recovers_shared_reminder_without_generic_refusal():
    env = _runtime_fixture(initial_text="zihao就是olivers")
    service, repo, _, _ = _social_service(names={"friend_olivers": "Olivers"}, reachable={"account_1", "friend_olivers"})
    _add_friend(repo, "account_1", "friend_olivers")
    intent = _open_recoverable_intent(repo, conversation_id=env.trigger.conversation_id, title="11:40的午饭")
    social_tool = SocialSchedulingToolAdapter(service)
    env.semantic.next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
        follow_up_action=FollowUpAction(
            type="resolve_friend_reference_correction",
            prior_reference_text="zihao",
            corrected_friend_text="olivers",
            scope="immediately_preceding_unresolved_intent",
        ),
    )
    env.agent = RecoveringEvaAgent()
    runner = _turn_runner(env, social_tool=social_tool, social_service=service)

    result = runner.run_inbound_turn(env.trigger)

    assert result.disposition == "replied"
    assert "我没法查看" not in result.visible_text
    assert repo.get_recoverable_intent(intent.id).status == "consumed"
    assert env.repository.staged_commands_for_turn(result.turn_id)[0].status == "materialized"
    assert repo.list_shared_reminders_for_participant("account_1")
```

- [ ] **Step 2: Add the availability privacy test**

Add a test that creates shared-reminder context, configures a private busy
interval with labels in unavailable fields only, uses
`SocialSchedulingToolAdapter` to query availability, and asserts both facts and
visible text exclude labels:

```python
def test_eva_availability_reply_has_windows_without_activity_labels():
    env = _runtime_fixture(initial_text="看看 olivers 下午有没有空")
    service, repo, _, availability = _social_service(names={"friend_olivers": "Olivers"}, reachable={"account_1", "friend_olivers"})
    _add_friend(repo, "account_1", "friend_olivers")
    availability.intervals["friend_olivers"] = [
        BusyInterval("friend_olivers", datetime(2026, 6, 6, 14, 0), datetime(2026, 6, 6, 14, 15), "shared", detail_id="和Olivers约下午两点喝咖啡"),
        BusyInterval("friend_olivers", datetime(2026, 6, 6, 15, 0), datetime(2026, 6, 6, 15, 15), "shared", detail_id="约olivers下午三点散步"),
    ]
    social_tool = SocialSchedulingToolAdapter(service)
    env.agent = AvailabilityEvaAgent()
    runner = _turn_runner(env, social_tool=social_tool, social_service=service)

    result = runner.run_inbound_turn(env.trigger)

    assert result.disposition == "replied"
    assert "14:00-14:15忙" in result.visible_text
    assert "15:00-15:15忙" in result.visible_text
    for forbidden in ("散步", "咖啡", "你们约了散步"):
        assert forbidden not in str(env.agent.tool_result.facts)
        assert forbidden not in result.visible_text
```

- [ ] **Step 3: Run the new recovery and availability tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_eva_regression_corpus.py::test_eva_zihao_correction_recovers_shared_reminder_without_generic_refusal tests/unit/coke/turn/test_eva_regression_corpus.py::test_eva_availability_reply_has_windows_without_activity_labels -q
```

Expected on this integration branch: PASS unless Track C/D/E integration has a
real defect. If a real defect appears, stop and report it.

- [ ] **Step 4: Tick Task 2 checkboxes in this plan**

Update this file so Task 2 completed steps use `- [x]`.

### Task 3: Add Waiting-Failure And No-Soft-Success Cases

**Files:**
- Modify: `tests/unit/coke/turn/test_eva_regression_corpus.py`
- Modify: `docs/superpowers/plans/2026-06-07-eva-regression-corpus.md`

- [ ] **Step 1: Add the waiting provider failure plus final reply test**

Add a test whose delivery fake returns `DeliveryOutcome(status="failed",
error_code="provider_network_error")` for waiting messages and records the
request:

```python
def test_eva_waiting_provider_failure_is_observable_and_final_reply_closes_turn():
    env = _runtime_fixture(initial_text="hey？")
    initial_closed_seq = env.repository.get_conversation(env.trigger.conversation_id).last_closed_inbound_seq
    env.agent.next_result = AgentResult.timeout(task_id="eva-async")
    env.agent.next_async_result = AgentResult.completed({"type": "reply", "segments": ["最终回复"]})
    env.delivery.fail_waiting_with = "provider_network_error"
    runner = _turn_runner(env)

    pending = runner.run_inbound_turn(env.trigger)
    final = runner.complete_async_reply(pending.async_task_id)

    assert pending.disposition == "pending_async_reply"
    assert env.delivery.deliveries[0].message_type == "waiting"
    assert env.delivery.outcomes[0].status == "failed"
    assert env.delivery.outcomes[0].error_code == "provider_network_error"
    assert env.repository.get_conversation(env.trigger.conversation_id).last_closed_inbound_seq == initial_closed_seq
    assert final.disposition == "replied"
    assert final.visible_text == "最终回复"
```

- [ ] **Step 2: Add the no-soft-success without materialization test**

Add a supersession test where the agent attempts a shared-reminder command and
returns production-bad soft-success prose after a newer inbound arrives:

```python
def test_eva_superseded_shared_reminder_soft_success_does_not_materialize_or_send():
    env = _runtime_fixture(initial_text="帮我和 olivers 约下午三点咖啡")
    service, repo, _, _ = _social_service(names={"friend_olivers": "Olivers"}, reachable={"account_1", "friend_olivers"})
    _add_friend(repo, "account_1", "friend_olivers")
    social_tool = SocialSchedulingToolAdapter(service)
    env.agent = SupersedingSoftSuccessAgent(env.runtime)
    runner = _turn_runner(env, social_tool=social_tool, social_service=service)

    result = runner.run_inbound_turn(env.trigger)

    assert result.disposition == "superseded"
    assert result.visible_text is None
    assert repo.list_shared_reminders_for_participant("account_1") == []
    assert [command.status for command in env.repository.staged_commands_for_turn(result.turn_id)] != ["materialized"]
    assert all("等他确认" not in delivery.visible_text for delivery in env.delivery.deliveries)
    assert all("邀约" not in delivery.visible_text for delivery in env.delivery.deliveries)
```

- [ ] **Step 3: Run the waiting and soft-success tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_eva_regression_corpus.py::test_eva_waiting_provider_failure_is_observable_and_final_reply_closes_turn tests/unit/coke/turn/test_eva_regression_corpus.py::test_eva_superseded_shared_reminder_soft_success_does_not_materialize_or_send -q
```

Expected on this integration branch: PASS unless Track B/C close-boundary
integration has a real defect. If the soft-success text is delivered without
materialized state, stop and report it.

- [ ] **Step 4: Tick Task 3 checkboxes in this plan**

Update this file so Task 3 completed steps use `- [x]`.

### Task 4: Evidence, Verification, And Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-06-07-eva-regression-corpus.md`
- Create: `artifacts/evidence/2026-06-07-eva-regression-corpus/pytest-eva-corpus.txt`
- Create: `artifacts/evidence/2026-06-07-eva-regression-corpus/suggest-verification.txt`
- Create: `artifacts/evidence/2026-06-07-eva-regression-corpus/review-trigger.txt`

- [ ] **Step 1: Run the full Eva corpus and save evidence**

Run:

```bash
mkdir -p artifacts/evidence/2026-06-07-eva-regression-corpus
```

Then run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_eva_regression_corpus.py -q > artifacts/evidence/2026-06-07-eva-regression-corpus/pytest-eva-corpus.txt 2>&1
```

Expected: all Eva corpus tests pass, with output saved in
`pytest-eva-corpus.txt`.

- [ ] **Step 2: Run required full backend verification**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: the full `tests/unit/coke` baseline remains green.

- [ ] **Step 3: Run diff-aware routing and suggested surface**

Run:

```bash
zsh scripts/suggest-verification --base main
zsh scripts/review-trigger --base main
```

Then run the surface command recommended by `suggest-verification`. For this
tests/docs-only runtime corpus, the expected suggested command is one of:

```bash
zsh scripts/verify-surface backend
zsh scripts/verify-surface repo-os-docs
zsh scripts/check
```

Use the actual suggestion, not this expectation, as the source of truth.

- [ ] **Step 4: Tick all remaining plan checkboxes**

Update every completed step in this plan to `- [x]`.

- [ ] **Step 5: Commit the corpus, plan updates, and evidence**

Run:

```bash
git status --short
git add tests/unit/coke/turn/test_eva_regression_corpus.py docs/superpowers/plans/2026-06-07-eva-regression-corpus.md artifacts/evidence/2026-06-07-eva-regression-corpus
git commit -m "test: add eva regression corpus" -m "Co-Authored-By: Codex <noreply@openai.com>"
```

Expected: a small coherent commit containing only the Track J corpus, the ticked
plan, and generated evidence.

## Plan Self-Review

- Spec coverage: every Track J minimum case maps to a named test.
- Placeholder scan: no unfinished placeholder language remains.
- Type consistency: the plan uses existing `TurnRunner`, `AgentResult`,
  `SocialSchedulingToolAdapter`, `RecoverableSchedulingIntent`,
  `DeliveryOutcome`, and in-memory repository types.
- Scope discipline: no production-code changes are planned.
