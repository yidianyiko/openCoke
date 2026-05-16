# Reminder Python Plugin Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the smallest in-process Reminder plugin boundary while preserving current visible reminder and internal follow-up behavior.

**Architecture:** Coke owns runtime wiring and Coke continuation. Reminder owns the runtime contract, scheduling lifecycle, and fired-event production. Phase one adds explicit runtime and fire-consumer seams, plus a narrow Coke adapter for Agno/PostAnalyze context mapping; bridge management remains its own transport adapter over the runtime contract.

**Tech Stack:** Python 3.12, dataclasses, pytest, APScheduler, Mongo-backed DAOs in production.

---

## Surfaces

- `worker-runtime`: reminder runtime, scheduler, agent runner, Agno reminder tool, PostAnalyze follow-up path.
- `bridge`: reminder management keeps behavior unchanged but may accept a runtime object.
- `repo-os`: design spec, architecture doc, and this execution plan.

## File Structure

- Create `agent/reminder/runtime.py`: `ReminderRuntime` object, current-runtime registry, and lifecycle delegation.
- Create `agent/reminder/fire_consumer.py`: `ReminderFireConsumer` protocol for `handle_fire_event()`.
- Create `agent/runner/reminder_fire_consumer.py`: Coke wrapper delegating to `ReminderFireEventHandler.handle()`.
- Create `agent/agno_agent/adapters/coke_reminder_adapter.py`: shared Coke context mapper and runtime selector for Agno/PostAnalyze paths.
- Modify `agent/reminder/service.py`: default scheduler lookup reads the current `ReminderRuntime`, not `agent.runner.reminder_scheduler`.
- Modify `agent/runner/reminder_scheduler.py`: constructor accepts `fire_consumer`; `_fire_event()` calls `handle_fire_event()`.
- Modify `agent/runner/agent_runner.py`: bootstrap and shutdown a `ReminderRuntime`.
- Modify `agent/agno_agent/tools/reminder_protocol/tool.py`: replace local context/runtime mapping with `CokeReminderAdapter`.
- Modify `agent/agno_agent/workflows/post_analyze_workflow.py`: use `CokeReminderAdapter` for owner/target/runtime mapping while preserving proactive metadata behavior.
- Modify tests under `tests/unit/reminder/`, `tests/unit/runner/`, and `tests/unit/agent/`.
- Modify `docs/ARCHITECTURE.md` after code is verified.

### Task 1: Reminder Runtime Object And Scheduler Registry

**Files:**
- Create: `agent/reminder/runtime.py`
- Modify: `agent/reminder/service.py`
- Test: `tests/unit/reminder/test_runtime_contract.py`

- [ ] **Step 1: Add failing runtime lifecycle tests**

Append these tests to `tests/unit/reminder/test_runtime_contract.py`:

```python
def test_reminder_runtime_starts_loads_and_shuts_down_scheduler():
    from agent.reminder.runtime import ReminderRuntime

    class RecordingScheduler:
        def __init__(self):
            self.calls = []

        def start(self):
            self.calls.append("start")

        def load_from_storage(self):
            self.calls.append("load_from_storage")

        def shutdown(self):
            self.calls.append("shutdown")

    scheduler = RecordingScheduler()
    runtime = ReminderRuntime(
        contract=ReminderRuntimeContract(reminder_service=RecordingReminderService()),
        scheduler=scheduler,
        fire_consumer=object(),
    )

    runtime.start()
    runtime.load_from_storage()
    runtime.shutdown()

    assert scheduler.calls == ["start", "load_from_storage", "shutdown"]


def test_current_reminder_runtime_registry_is_used_by_default_service_scheduler():
    from agent.reminder.runtime import (
        ReminderRuntime,
        get_reminder_runtime_instance,
        set_reminder_runtime_instance,
    )
    from agent.reminder.service import ReminderService

    previous = get_reminder_runtime_instance()
    scheduler = object()
    runtime = ReminderRuntime(
        contract=ReminderRuntimeContract(reminder_service=RecordingReminderService()),
        scheduler=scheduler,
        fire_consumer=object(),
    )
    try:
        set_reminder_runtime_instance(runtime)
        service = ReminderService(reminder_dao=object())
        assert service.scheduler is scheduler
    finally:
        set_reminder_runtime_instance(previous)
```

- [ ] **Step 2: Verify tests fail before implementation**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_runtime_contract.py -q
```

Expected: failure because `agent.reminder.runtime` does not exist.

- [ ] **Step 3: Implement `ReminderRuntime` and registry**

Create `agent/reminder/runtime.py`:

```python
from __future__ import annotations

from typing import Any


class ReminderRuntime:
    """In-process Reminder capability object owned by Coke runtime wiring."""

    def __init__(self, *, contract: Any, scheduler: Any, fire_consumer: Any) -> None:
        self.contract = contract
        self.scheduler = scheduler
        self.fire_consumer = fire_consumer

    def start(self) -> None:
        self.scheduler.start()

    def load_from_storage(self) -> None:
        self.scheduler.load_from_storage()

    def shutdown(self) -> None:
        self.scheduler.shutdown()


_runtime_instance: ReminderRuntime | None = None


def set_reminder_runtime_instance(runtime: ReminderRuntime | None) -> None:
    global _runtime_instance
    _runtime_instance = runtime


def get_reminder_runtime_instance() -> ReminderRuntime | None:
    return _runtime_instance
```

Modify `ReminderService._get_runtime_scheduler()` in `agent/reminder/service.py`:

```python
    def _get_runtime_scheduler(self):
        try:
            from agent.reminder.runtime import get_reminder_runtime_instance

            runtime = get_reminder_runtime_instance()
            return runtime.scheduler if runtime is not None else None
        except Exception:
            return None
```

- [ ] **Step 4: Verify runtime tests pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_runtime_contract.py -q
```

Expected: all tests pass.

### Task 2: Fire Consumer Callback Boundary

**Files:**
- Create: `agent/reminder/fire_consumer.py`
- Create: `agent/runner/reminder_fire_consumer.py`
- Modify: `agent/runner/reminder_scheduler.py`
- Modify: `agent/runner/agent_runner.py`
- Test: `tests/unit/runner/test_reminder_scheduler.py`

- [ ] **Step 1: Add failing consumer dispatch test**

Append this test to `tests/unit/runner/test_reminder_scheduler.py`:

```python
@pytest.mark.asyncio
async def test_scheduler_dispatches_fired_event_to_fire_consumer_handle_fire_event():
    scheduled_for = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    finished_at = datetime(2026, 4, 29, 1, 0, 3, tzinfo=UTC)
    stored_reminder = reminder_document(build_reminder(next_fire_at=scheduled_for))
    consumer = Mock()
    consumer.handle_fire_event = AsyncMock(return_value=fire_result())
    dao = Mock(
        get_reminder=Mock(return_value=stored_reminder),
        atomic_apply_fire_success=Mock(return_value=True),
    )
    scheduler = ReminderScheduler(
        reminder_dao=dao,
        fire_consumer=consumer,
        scheduler=Mock(),
        now_provider=lambda: finished_at,
    )
    scheduler.remove_reminder = Mock()

    await scheduler._execute_job("rem-1", scheduled_for)

    consumer.handle_fire_event.assert_awaited_once()
    event = consumer.handle_fire_event.call_args.args[0]
    assert event.fire_id == "rem-1:2026-04-29T01:00:00+00:00"
    assert event.fire_at == finished_at
```

- [ ] **Step 2: Verify test fails before implementation**

Run:

```bash
.venv/bin/python -m pytest tests/unit/runner/test_reminder_scheduler.py::test_scheduler_dispatches_fired_event_to_fire_consumer_handle_fire_event -q
```

Expected: failure because `ReminderScheduler.__init__()` has no `fire_consumer` argument.

- [ ] **Step 3: Add consumer protocol and Coke wrapper**

Create `agent/reminder/fire_consumer.py`:

```python
from __future__ import annotations

from typing import Protocol

from agent.reminder.models import ReminderFiredEvent, ReminderFireResult


class ReminderFireConsumer(Protocol):
    async def handle_fire_event(
        self,
        event: ReminderFiredEvent,
    ) -> ReminderFireResult:
        ...
```

Create `agent/runner/reminder_fire_consumer.py`:

```python
from __future__ import annotations

import inspect
from typing import Any

from agent.reminder.models import ReminderFiredEvent, ReminderFireResult


class CokeReminderFireConsumer:
    def __init__(self, handler: Any) -> None:
        self.handler = handler

    async def handle_fire_event(
        self,
        event: ReminderFiredEvent,
    ) -> ReminderFireResult:
        result = self.handler.handle(event)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, ReminderFireResult):
            raise RuntimeError("invalid reminder fire result")
        return result
```

- [ ] **Step 4: Migrate scheduler dispatch**

Modify `ReminderScheduler.__init__()` and `_fire_event()` in `agent/runner/reminder_scheduler.py`:

```python
    def __init__(
        self,
        reminder_dao: Any,
        fire_consumer: Any,
        scheduler: AsyncIOScheduler | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.reminder_dao = reminder_dao
        self.fire_consumer = fire_consumer
        self.scheduler = scheduler or AsyncIOScheduler(timezone=UTC)
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
```

```python
    async def _fire_event(self, event: ReminderFiredEvent) -> ReminderFireResult:
        result = self.fire_consumer.handle_fire_event(event)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, ReminderFireResult):
            raise RuntimeError("invalid reminder fire result")
        return result
```

Update existing tests in `tests/unit/runner/test_reminder_scheduler.py` to pass `fire_consumer=consumer` and assert `consumer.handle_fire_event` instead of calling a bare handler.

- [ ] **Step 5: Wire agent runner through runtime and consumer**

Modify `agent/runner/agent_runner.py` imports and `bootstrap_reminder_runtime()`:

```python
from agent.reminder.runtime import (
    ReminderRuntime,
    get_reminder_runtime_instance,
    set_reminder_runtime_instance,
)
from agent.reminder.runtime_contract import ReminderRuntimeContract
from agent.reminder.service import ReminderService
from agent.runner.reminder_fire_consumer import CokeReminderFireConsumer
```

```python
def bootstrap_reminder_runtime():
    existing = get_reminder_runtime_instance()
    if existing is not None:
        return existing

    reminder_dao = ReminderDAO()
    handler = ReminderFireEventHandler(runtime_event_handler=run_agent_runtime_event)
    fire_consumer = CokeReminderFireConsumer(handler)
    scheduler = ReminderScheduler(
        reminder_dao=reminder_dao,
        fire_consumer=fire_consumer,
    )
    contract = ReminderRuntimeContract(
        reminder_service=ReminderService(reminder_dao=reminder_dao, scheduler=scheduler)
    )
    runtime = ReminderRuntime(
        contract=contract,
        scheduler=scheduler,
        fire_consumer=fire_consumer,
    )
    set_reminder_runtime_instance(runtime)
    set_reminder_scheduler_instance(scheduler)
    try:
        runtime.start()
    except Exception:
        _shutdown_runtime(
            "reminder runtime",
            runtime,
            set_reminder_runtime_instance,
        )
        set_reminder_scheduler_instance(None)
        raise
    return runtime
```

Update shutdown call in `main()` to clear both runtime and legacy scheduler registry.

- [ ] **Step 6: Verify scheduler lifecycle behavior**

Run:

```bash
.venv/bin/python -m pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py -q
```

Expected: all tests pass, including success, failure, exception, one-shot completion, and recurring reschedule.

### Task 3: Narrow Coke Reminder Adapter

**Files:**
- Create: `agent/agno_agent/adapters/coke_reminder_adapter.py`
- Modify: `agent/agno_agent/tools/reminder_protocol/tool.py`
- Modify: `agent/agno_agent/workflows/post_analyze_workflow.py`
- Test: `tests/unit/agent/test_visible_reminder_protocol_tool.py`
- Test: `tests/unit/agent/test_internal_followup_no_deferred_action_path.py`

- [ ] **Step 1: Add adapter unit tests**

Create or append tests proving:

```python
from datetime import UTC, datetime

from agent.agno_agent.adapters.coke_reminder_adapter import CokeReminderAdapter


def test_coke_reminder_adapter_derives_context_from_session_state():
    context = CokeReminderAdapter().derive_context(
        {
            "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
            "character": {"id": "char-1"},
            "conversation": {"id": "conv-1", "route_key": "route-1"},
            "current_time": "2026-05-15T10:00:00+09:00",
        }
    )

    assert context.owner_user_id == "user-1"
    assert context.target.conversation_id == "conv-1"
    assert context.target.character_id == "char-1"
    assert context.target.route_key == "route-1"
    assert context.timezone == "Asia/Tokyo"
    assert context.current_time == datetime(2026, 5, 15, 1, 0, tzinfo=UTC)
```

- [ ] **Step 2: Implement adapter**

Create `agent/agno_agent/adapters/coke_reminder_adapter.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent.reminder.errors import InvalidArgument, InvalidOutputTarget
from agent.reminder.models import AgentOutputTarget, ReminderSchedule
from agent.reminder.runtime import get_reminder_runtime_instance
from agent.reminder.runtime_contract import ReminderRuntimeContract
from agent.reminder.service import ReminderService
from util.time_util import get_default_timezone


@dataclass(frozen=True)
class CokeReminderContext:
    owner_user_id: str
    target: AgentOutputTarget
    timezone: str
    current_time: datetime | None


class CokeReminderAdapter:
    def derive_context(self, session_state: dict[str, Any]) -> CokeReminderContext:
        user = session_state.get("user") or {}
        character = session_state.get("character") or {}
        conversation = session_state.get("conversation") or {}
        owner_user_id = self._string_value(user.get("id") or user.get("_id"))
        character_id = self._string_value(character.get("_id") or character.get("id"))
        conversation_id = self._string_value(
            conversation.get("_id")
            or conversation.get("id")
            or session_state.get("conversation_id")
        )
        route_key = (
            session_state.get("route_key")
            or session_state.get("delivery_route_key")
            or conversation.get("route_key")
        )
        timezone = self._string_value(
            user.get("effective_timezone")
            or user.get("timezone")
            or get_default_timezone().key
        )
        if not owner_user_id:
            raise InvalidArgument(
                "Reminder owner_user_id is missing",
                detail={"field": "owner_user_id"},
            )
        if not conversation_id:
            raise InvalidOutputTarget(
                "Reminder output target conversation_id must be non-empty",
                detail={"field": "conversation_id"},
            )
        if not character_id:
            raise InvalidOutputTarget(
                "Reminder output target character_id must be non-empty",
                detail={"field": "character_id"},
            )
        return CokeReminderContext(
            owner_user_id=owner_user_id,
            target=AgentOutputTarget(
                conversation_id=conversation_id,
                character_id=character_id,
                route_key=self._string_value(route_key) if route_key else None,
            ),
            timezone=timezone,
            current_time=self.parse_current_time(session_state.get("current_time")),
        )

    def reminder_contract(self, session_state: dict[str, Any]) -> ReminderRuntimeContract:
        runtime = get_reminder_runtime_instance()
        if runtime is not None:
            return runtime.contract
        current_time = self.parse_current_time(session_state.get("current_time"))
        if current_time is None:
            return ReminderRuntimeContract(reminder_service=ReminderService())
        return ReminderRuntimeContract(
            reminder_service=ReminderService(now_provider=lambda: current_time)
        )

    def create_or_replace_internal_followup(
        self,
        *,
        session_state: dict[str, Any],
        title: str,
        prompt: str,
        schedule: ReminderSchedule,
        metadata: dict | None = None,
    ):
        context = self.derive_context(session_state)
        return self.reminder_contract(session_state).create_or_replace_internal_followup(
            owner_user_id=context.owner_user_id,
            conversation_id=context.target.conversation_id,
            character_id=context.target.character_id,
            route_key=context.target.route_key,
            title=title,
            prompt=prompt,
            schedule=schedule,
            metadata=metadata,
        )

    def clear_internal_followup(self, *, session_state: dict[str, Any]):
        context = self.derive_context(session_state)
        return self.reminder_contract(session_state).clear_internal_followup(
            owner_user_id=context.owner_user_id,
            conversation_id=context.target.conversation_id,
        )

    def parse_current_time(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)

    def _string_value(self, value: Any) -> str:
        return "" if value is None else str(value)
```

- [ ] **Step 3: Wire visible reminder tool to adapter**

In `agent/agno_agent/tools/reminder_protocol/tool.py`, import `CokeReminderAdapter`, replace `_derive_runtime_context()` body with `return CokeReminderAdapter().derive_context(session_state)`, and replace `_build_reminder_runtime()` with `return CokeReminderAdapter().reminder_contract(session_state)`. Keep `_RuntimeContext`, `_parse_current_time()`, and `_string_value()` only if tests still need them; otherwise remove duplicates.

- [ ] **Step 4: Wire PostAnalyze follow-up to adapter**

In `agent/agno_agent/workflows/post_analyze_workflow.py`, replace direct `ReminderRuntimeContract()` calls in `_handle_followup_plan()` with `adapter = CokeReminderAdapter()` and call `adapter.clear_internal_followup(session_state=session_state)` or `adapter.create_or_replace_internal_followup(session_state=session_state, ...)`.

- [ ] **Step 5: Verify user-visible paths**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/agent/test_internal_followup_no_deferred_action_path.py -q
```

Expected: all tests pass.

### Task 4: Docs And Routed Verification

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/superpowers/specs/2026-05-15-reminder-python-plugin-boundary-design.md` only if implementation reveals more phase-one constraints.

- [ ] **Step 1: Update architecture reminder section**

Change the reminder bullets in `docs/ARCHITECTURE.md` so they state:

```markdown
- `agent/reminder/runtime.py` is the in-process Reminder Runtime object owned by the worker runtime. It holds the runtime contract, scheduler, and fire consumer.
- `ReminderScheduler` emits `ReminderFiredEvent` objects to a `ReminderFireConsumer`; Coke wires `CokeReminderFireConsumer` to the existing `ReminderFireEventHandler` so conversation lookup, locks, Agno `AgentInput`, and output delivery remain Coke continuation concerns.
```

- [ ] **Step 2: Run diff-aware routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: commands complete and identify `worker-runtime`, `bridge`, or `repo-os` checks relevant to the diff.

- [ ] **Step 3: Run focused verification**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_runtime_contract.py tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/agent/test_internal_followup_no_deferred_action_path.py tests/unit/connector/clawscale_bridge/test_reminder_management_service.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run structure check**

Run:

```bash
zsh scripts/check
```

Expected: passes. If it fails, classify whether the failure is repo-OS structure, stale generated evidence, or a real doc/code issue before editing.
