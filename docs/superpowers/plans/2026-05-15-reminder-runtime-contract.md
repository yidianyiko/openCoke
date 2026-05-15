# Reminder Runtime Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the post-unification Reminder runtime expose an explicit domain contract that existing Agno, PostAnalyze, bridge HTTP, and web-management paths call instead of depending directly on scattered reminder service behavior.

**Architecture:** Add a thin `ReminderRuntimeContract` facade over the existing `ReminderService` and scheduler/fire-event model. Keep the runtime in-process and preserve current user-visible behavior. Existing adapters migrate to the contract without adding MCP, CLI, new public APIs, idempotency storage, or a scheduler rewrite.

**Tech Stack:** Python dataclasses, existing `agent.reminder` models/service/DAO, existing Agno tool adapters, Flask bridge service, pytest.

---

## Scope

This plan implements the first contract extraction only.

Included:

- explicit runtime-contract module for visible reminder operations
- explicit runtime-contract methods for internal follow-up operations
- adapter migration for Agno reminder tool path, PostAnalyze follow-up path, and bridge reminder management service
- focused tests that prove adapters call the contract boundary
- documentation updates to mark the Reminder Runtime Contract as implemented in-process

Excluded:

- MCP adapter
- CLI adapter
- public external API
- idempotency storage
- trace propagation storage
- durable outbox, claim, retry, or multi-worker scheduler changes
- natural-language time parser changes
- `origin=web` semantics

## File Map

- Create: `agent/reminder/runtime_contract.py`
  - Owns the explicit in-process Reminder Runtime Contract facade.
  - Delegates persistence and scheduler hooks to `ReminderService`.
  - Provides visible reminder methods and internal follow-up methods.
- Create: `tests/unit/reminder/test_runtime_contract.py`
  - Contract-level unit tests with fake services.
- Modify: `agent/agno_agent/tools/reminder_protocol/tool.py`
  - Replace direct `ReminderService` dependency with the contract facade.
- Modify: `agent/agno_agent/workflows/post_analyze_workflow.py`
  - Replace direct `ReminderService` construction with the contract facade.
- Modify: `connector/clawscale_bridge/reminder_management_service.py`
  - Replace direct `ReminderService` dependency with the contract facade.
- Modify: `tests/unit/agent/test_post_analyze_deferred_actions.py`
  - Patch `ReminderRuntimeContract` instead of `ReminderService`.
- Modify: `tests/unit/connector/clawscale_bridge/test_reminder_management_service.py`
  - Assert bridge management uses contract methods.
- Modify: `docs/superpowers/specs/2026-05-14-reminder-runtime-contract-design.md`
  - Update status after implementation.
- Modify: `docs/ARCHITECTURE.md`
  - Mention the in-process contract module in the Reminder System section.

## Contract Shape

The first implementation should expose these methods:

```python
class ReminderRuntimeContract:
    def create_visible_reminder(
        self,
        *,
        owner_user_id: str,
        title: str,
        schedule: ReminderSchedule,
        target: AgentOutputTarget,
    ) -> Reminder: ...

    def update_visible_reminder(
        self,
        *,
        owner_user_id: str,
        reminder_id: str,
        patch: ReminderPatch,
    ) -> Reminder: ...

    def cancel_visible_reminder(
        self,
        *,
        owner_user_id: str,
        reminder_id: str,
    ) -> Reminder: ...

    def complete_visible_reminder(
        self,
        *,
        owner_user_id: str,
        reminder_id: str,
    ) -> Reminder: ...

    def list_visible_reminders(
        self,
        *,
        owner_user_id: str,
        query: ReminderQuery,
    ) -> list[Reminder]: ...

    def list_visible_reminders_in_local_date_range(
        self,
        *,
        owner_user_id: str,
        from_date: date,
        to_date: date,
        lifecycle_states: list[str],
    ) -> list[Reminder]: ...

    def create_or_replace_internal_followup(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
        character_id: str,
        route_key: str | None,
        title: str,
        prompt: str,
        schedule: ReminderSchedule,
        metadata: dict | None = None,
    ) -> Reminder: ...

    def clear_internal_followup(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
    ) -> Reminder | None: ...
```

The facade intentionally forwards to existing `ReminderService` methods. Do not move business logic into adapters.

---

### Task 1: Add Reminder Runtime Contract Facade

**Files:**
- Create: `agent/reminder/runtime_contract.py`
- Create: `tests/unit/reminder/test_runtime_contract.py`

- [ ] **Step 1: Write contract tests**

Create `tests/unit/reminder/test_runtime_contract.py`:

```python
from __future__ import annotations

from datetime import UTC, date, datetime, time

from agent.reminder.models import (
    AgentOutputTarget,
    ReminderPatch,
    ReminderQuery,
    ReminderSchedule,
)
from agent.reminder.runtime_contract import ReminderRuntimeContract


class RecordingReminderService:
    def __init__(self):
        self.calls = []
        self.result = object()

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return self.result

    def update(self, **kwargs):
        self.calls.append(("update", kwargs))
        return self.result

    def cancel(self, **kwargs):
        self.calls.append(("cancel", kwargs))
        return self.result

    def complete(self, **kwargs):
        self.calls.append(("complete", kwargs))
        return self.result

    def list_for_user(self, **kwargs):
        self.calls.append(("list_for_user", kwargs))
        return [self.result]

    def list_for_user_in_local_date_range(self, **kwargs):
        self.calls.append(("list_for_user_in_local_date_range", kwargs))
        return [self.result]

    def create_or_replace_internal_followup(self, **kwargs):
        self.calls.append(("create_or_replace_internal_followup", kwargs))
        return self.result

    def clear_internal_followup(self, **kwargs):
        self.calls.append(("clear_internal_followup", kwargs))
        return self.result


def sample_schedule() -> ReminderSchedule:
    return ReminderSchedule(
        anchor_at=datetime(2026, 5, 16, 1, 0, tzinfo=UTC),
        local_date=date(2026, 5, 16),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule=None,
    )


def sample_target() -> AgentOutputTarget:
    return AgentOutputTarget(
        conversation_id="conv-1",
        character_id="char-1",
        route_key="route-1",
    )


def test_create_visible_reminder_builds_visible_create_command():
    service = RecordingReminderService()
    contract = ReminderRuntimeContract(reminder_service=service)

    result = contract.create_visible_reminder(
        owner_user_id="user-1",
        title="写周报",
        schedule=sample_schedule(),
        target=sample_target(),
    )

    assert result is service.result
    assert service.calls[0][0] == "create"
    kwargs = service.calls[0][1]
    assert kwargs["owner_user_id"] == "user-1"
    assert kwargs["command"].title == "写周报"
    assert kwargs["command"].schedule == sample_schedule()
    assert kwargs["command"].agent_output_target == sample_target()
    assert kwargs["command"].created_by_system == "agent"


def test_visible_mutation_methods_delegate_to_service():
    service = RecordingReminderService()
    contract = ReminderRuntimeContract(reminder_service=service)
    patch = ReminderPatch(title="新标题")
    query = ReminderQuery(lifecycle_states=["active"])

    assert contract.update_visible_reminder(
        owner_user_id="user-1",
        reminder_id="rem-1",
        patch=patch,
    ) is service.result
    assert contract.cancel_visible_reminder(
        owner_user_id="user-1",
        reminder_id="rem-1",
    ) is service.result
    assert contract.complete_visible_reminder(
        owner_user_id="user-1",
        reminder_id="rem-1",
    ) is service.result
    assert contract.list_visible_reminders(
        owner_user_id="user-1",
        query=query,
    ) == [service.result]

    assert service.calls[0] == (
        "update",
        {"owner_user_id": "user-1", "reminder_id": "rem-1", "patch": patch},
    )
    assert service.calls[1] == (
        "cancel",
        {"owner_user_id": "user-1", "reminder_id": "rem-1"},
    )
    assert service.calls[2] == (
        "complete",
        {"owner_user_id": "user-1", "reminder_id": "rem-1"},
    )
    assert service.calls[3] == (
        "list_for_user",
        {"owner_user_id": "user-1", "query": query},
    )


def test_list_visible_reminders_in_local_date_range_delegates_to_service():
    service = RecordingReminderService()
    contract = ReminderRuntimeContract(reminder_service=service)

    result = contract.list_visible_reminders_in_local_date_range(
        owner_user_id="user-1",
        from_date=date(2026, 5, 11),
        to_date=date(2026, 5, 17),
        lifecycle_states=["active"],
    )

    assert result == [service.result]
    assert service.calls == [
        (
            "list_for_user_in_local_date_range",
            {
                "owner_user_id": "user-1",
                "from_date": date(2026, 5, 11),
                "to_date": date(2026, 5, 17),
                "lifecycle_states": ["active"],
            },
        )
    ]


def test_internal_followup_methods_delegate_to_service():
    service = RecordingReminderService()
    contract = ReminderRuntimeContract(reminder_service=service)

    assert contract.create_or_replace_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
        character_id="char-1",
        route_key="route-1",
        title="检查进展",
        prompt="问用户有没有开始",
        schedule=sample_schedule(),
        metadata={"proactive_times": 1},
    ) is service.result
    assert contract.clear_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
    ) is service.result

    assert service.calls[0][0] == "create_or_replace_internal_followup"
    assert service.calls[0][1]["owner_user_id"] == "user-1"
    assert service.calls[0][1]["conversation_id"] == "conv-1"
    assert service.calls[0][1]["metadata"] == {"proactive_times": 1}
    assert service.calls[1] == (
        "clear_internal_followup",
        {"owner_user_id": "user-1", "conversation_id": "conv-1"},
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_runtime_contract.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent.reminder.runtime_contract'`.

- [ ] **Step 3: Create the contract facade**

Create `agent/reminder/runtime_contract.py`:

```python
from __future__ import annotations

from datetime import date

from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderCreateCommand,
    ReminderPatch,
    ReminderQuery,
    ReminderSchedule,
)


class ReminderRuntimeContract:
    """In-process domain contract for reminder runtime adapters."""

    def __init__(self, *, reminder_service=None) -> None:
        if reminder_service is None:
            from agent.reminder.service import ReminderService

            reminder_service = ReminderService()
        self.reminder_service = reminder_service

    def create_visible_reminder(
        self,
        *,
        owner_user_id: str,
        title: str,
        schedule: ReminderSchedule,
        target: AgentOutputTarget,
    ) -> Reminder:
        command = ReminderCreateCommand(
            title=title,
            schedule=schedule,
            agent_output_target=target,
            created_by_system="agent",
        )
        return self.reminder_service.create(
            owner_user_id=owner_user_id,
            command=command,
        )

    def update_visible_reminder(
        self,
        *,
        owner_user_id: str,
        reminder_id: str,
        patch: ReminderPatch,
    ) -> Reminder:
        return self.reminder_service.update(
            owner_user_id=owner_user_id,
            reminder_id=reminder_id,
            patch=patch,
        )

    def cancel_visible_reminder(
        self,
        *,
        owner_user_id: str,
        reminder_id: str,
    ) -> Reminder:
        return self.reminder_service.cancel(
            owner_user_id=owner_user_id,
            reminder_id=reminder_id,
        )

    def complete_visible_reminder(
        self,
        *,
        owner_user_id: str,
        reminder_id: str,
    ) -> Reminder:
        return self.reminder_service.complete(
            owner_user_id=owner_user_id,
            reminder_id=reminder_id,
        )

    def list_visible_reminders(
        self,
        *,
        owner_user_id: str,
        query: ReminderQuery,
    ) -> list[Reminder]:
        return self.reminder_service.list_for_user(
            owner_user_id=owner_user_id,
            query=query,
        )

    def list_visible_reminders_in_local_date_range(
        self,
        *,
        owner_user_id: str,
        from_date: date,
        to_date: date,
        lifecycle_states: list[str],
    ) -> list[Reminder]:
        return self.reminder_service.list_for_user_in_local_date_range(
            owner_user_id=owner_user_id,
            from_date=from_date,
            to_date=to_date,
            lifecycle_states=lifecycle_states,
        )

    def create_or_replace_internal_followup(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
        character_id: str,
        route_key: str | None,
        title: str,
        prompt: str,
        schedule: ReminderSchedule,
        metadata: dict | None = None,
    ) -> Reminder:
        return self.reminder_service.create_or_replace_internal_followup(
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            character_id=character_id,
            route_key=route_key,
            title=title,
            prompt=prompt,
            schedule=schedule,
            metadata=metadata,
        )

    def clear_internal_followup(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
    ) -> Reminder | None:
        return self.reminder_service.clear_internal_followup(
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_runtime_contract.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/reminder/runtime_contract.py tests/unit/reminder/test_runtime_contract.py
git commit -m "refactor(reminders): add runtime contract facade"
```

---

### Task 2: Migrate Agno Reminder Tool Adapter

**Files:**
- Modify: `agent/agno_agent/tools/reminder_protocol/tool.py`
- Test: `tests/unit/reminder/test_runtime_contract.py`
- Existing tests: `tests/unit/agent/test_reminder_intent_capability.py`

- [ ] **Step 1: Add adapter test for contract injection**

Append to `tests/unit/reminder/test_runtime_contract.py`:

```python
def test_reminder_protocol_builds_runtime_contract_with_current_time(monkeypatch):
    from agent.agno_agent.tools.reminder_protocol import tool as reminder_tool

    captured = {}

    class FakeContract:
        def __init__(self, *, reminder_service):
            captured["service"] = reminder_service

    monkeypatch.setattr(reminder_tool, "ReminderRuntimeContract", FakeContract)

    runtime = reminder_tool._build_reminder_runtime(
        {"current_time": "2026-05-15T10:00:00+09:00"}
    )

    assert isinstance(runtime, FakeContract)
    assert captured["service"].now_provider().isoformat() == "2026-05-15T01:00:00+00:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_runtime_contract.py::test_reminder_protocol_builds_runtime_contract_with_current_time -v
```

Expected: FAIL with `AttributeError` for `_build_reminder_runtime` or missing `ReminderRuntimeContract`.

- [ ] **Step 3: Update imports and builder in the adapter**

In `agent/agno_agent/tools/reminder_protocol/tool.py`, replace the direct service import:

```python
from agent.reminder.service import ReminderService
```

with:

```python
from agent.reminder.runtime_contract import ReminderRuntimeContract
from agent.reminder.service import ReminderService
```

Replace `_build_reminder_service` with:

```python
def _build_reminder_runtime(session_state: dict) -> ReminderRuntimeContract:
    current_time = _parse_current_time(session_state.get("current_time"))
    if current_time is None:
        return ReminderRuntimeContract()
    try:
        service = ReminderService(now_provider=lambda: current_time)
    except TypeError as exc:
        if "now_provider" not in str(exc):
            raise
        service = ReminderService()
    return ReminderRuntimeContract(reminder_service=service)
```

In `_execute_visible_reminder_tool_action`, replace:

```python
service = _build_reminder_service(session_state)
```

with:

```python
runtime = _build_reminder_runtime(session_state)
```

Then pass `runtime=runtime` instead of `service=service` into `_execute_batch_operations` and `_run_operation`.

- [ ] **Step 4: Rename helper parameters and call contract methods**

In `agent/agno_agent/tools/reminder_protocol/tool.py`, update helper signatures:

```python
def _execute_batch_operations(
    *,
    runtime: ReminderRuntimeContract,
    session_state: dict,
    operations: list[dict[str, Any]],
) -> str:
```

```python
def _run_operation(
    *,
    runtime: ReminderRuntimeContract,
    session_state: dict,
    action: str,
    title: str | None = None,
    trigger_at: str | None = None,
    reminder_id: str | None = None,
    keyword: str | None = None,
    new_title: str | None = None,
    new_trigger_at: str | None = None,
    rrule: str | None = None,
) -> str:
```

```python
def _execute_one(
    *,
    runtime: ReminderRuntimeContract,
    session_state: dict,
    action: str,
    title: str | None,
    trigger_at: str | None,
    reminder_id: str | None,
    keyword: str | None,
    new_title: str | None,
    new_trigger_at: str | None,
    rrule: str | None,
) -> tuple[str, bool]:
```

In `_execute_one`, replace visible operations:

```python
created = runtime.create_visible_reminder(
    owner_user_id=context.owner_user_id,
    title=title,
    schedule=_schedule_from_iso(trigger_at, context.timezone, rrule),
    target=context.target,
)
```

```python
reminders = runtime.list_visible_reminders(
    owner_user_id=context.owner_user_id,
    query=ReminderQuery(lifecycle_states=["active"]),
)
```

```python
updated = runtime.update_visible_reminder(
    reminder_id=target_id,
    owner_user_id=context.owner_user_id,
    patch=patch,
)
```

```python
cancelled = runtime.cancel_visible_reminder(
    reminder_id=target_id,
    owner_user_id=context.owner_user_id,
)
```

```python
completed = runtime.complete_visible_reminder(
    reminder_id=target_id,
    owner_user_id=context.owner_user_id,
)
```

Update `_resolve_reminder_id` to accept `runtime: ReminderRuntimeContract` and call `runtime.list_visible_reminders(...)`.

- [ ] **Step 5: Run focused reminder adapter tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/reminder/test_runtime_contract.py \
  tests/unit/agent/test_reminder_intent_capability.py \
  -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/agno_agent/tools/reminder_protocol/tool.py tests/unit/reminder/test_runtime_contract.py
git commit -m "refactor(reminders): route agno adapter through runtime contract"
```

---

### Task 3: Migrate PostAnalyze Internal Follow-Up Adapter

**Files:**
- Modify: `agent/agno_agent/workflows/post_analyze_workflow.py`
- Modify: `tests/unit/agent/test_post_analyze_deferred_actions.py`

- [ ] **Step 1: Update tests to patch contract boundary**

In `tests/unit/agent/test_post_analyze_deferred_actions.py`, replace the monkeypatch target for reminder follow-up service construction with:

```python
monkeypatch.setattr(
    "agent.agno_agent.workflows.post_analyze_workflow.ReminderRuntimeContract",
    lambda: service,
)
```

Keep the fake service methods named:

```python
create_or_replace_internal_followup=Mock()
clear_internal_followup=Mock()
```

Update assertions to keep the current keyword shape:

```python
service.clear_internal_followup.assert_called_once_with(
    owner_user_id="user-1",
    conversation_id="conv-1",
)
```

```python
kwargs = service.create_or_replace_internal_followup.call_args.kwargs
assert kwargs["owner_user_id"] == "user-1"
assert kwargs["conversation_id"] == "conv-1"
assert kwargs["character_id"] == "char-1"
assert kwargs["metadata"] == {"proactive_times": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_post_analyze_deferred_actions.py -v
```

Expected: FAIL because production code still constructs `ReminderService`.

- [ ] **Step 3: Update PostAnalyze import and construction**

In `agent/agno_agent/workflows/post_analyze_workflow.py`, replace:

```python
from agent.reminder.service import ReminderService
```

with:

```python
from agent.reminder.runtime_contract import ReminderRuntimeContract
```

Replace:

```python
service = ReminderService()
```

with:

```python
service = ReminderRuntimeContract()
```

Do not change the existing calls to `create_or_replace_internal_followup` and `clear_internal_followup`; they already match the contract method names.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_post_analyze_deferred_actions.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/workflows/post_analyze_workflow.py tests/unit/agent/test_post_analyze_deferred_actions.py
git commit -m "refactor(reminders): route post analyze followup through runtime contract"
```

---

### Task 4: Migrate Bridge Reminder Management Adapter

**Files:**
- Modify: `connector/clawscale_bridge/reminder_management_service.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_reminder_management_service.py`
- Existing tests: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`

- [ ] **Step 1: Update service construction test doubles**

In `tests/unit/connector/clawscale_bridge/test_reminder_management_service.py`, rename fake reminder-service variables that represent the runtime boundary to `runtime_contract`.

Ensure the fake implements:

```python
def list_visible_reminders_in_local_date_range(self, **kwargs): ...
def create_visible_reminder(self, **kwargs): ...
def update_visible_reminder(self, **kwargs): ...
def complete_visible_reminder(self, **kwargs): ...
def cancel_visible_reminder(self, **kwargs): ...
```

Update construction to pass:

```python
ReminderManagementService(
    reminder_runtime=runtime_contract,
    conversation_dao=conversation_dao,
    character_id_provider=lambda: "char-1",
)
```

- [ ] **Step 2: Run bridge management tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_reminder_management_service.py -v
```

Expected: FAIL because `ReminderManagementService` does not accept `reminder_runtime`.

- [ ] **Step 3: Update bridge management service constructor**

In `connector/clawscale_bridge/reminder_management_service.py`, import the contract:

```python
from agent.reminder.runtime_contract import ReminderRuntimeContract
```

Change constructor parameters:

```python
def __init__(
    self,
    *,
    reminder_runtime=None,
    reminder_service=None,
    conversation_dao=None,
    character_id_provider=None,
    now_provider=None,
) -> None:
```

Initialize with backward-compatible test support:

```python
if reminder_runtime is None:
    if reminder_service is None:
        reminder_runtime = ReminderRuntimeContract()
    else:
        reminder_runtime = ReminderRuntimeContract(reminder_service=reminder_service)
self.reminder_runtime = reminder_runtime
```

Remove assignments to `self.reminder_service`.

- [ ] **Step 4: Route bridge operations through contract methods**

In `list_reminders`, replace:

```python
reminders = self.reminder_service.list_for_user_in_local_date_range(...)
```

with:

```python
reminders = self.reminder_runtime.list_visible_reminders_in_local_date_range(...)
```

In `create_reminder`, replace:

```python
reminder = self.reminder_service.create(
    owner_user_id=customer_id,
    command=command,
)
```

with:

```python
reminder = self.reminder_runtime.create_visible_reminder(
    owner_user_id=customer_id,
    title=command.title,
    schedule=command.schedule,
    target=command.agent_output_target,
)
```

In update, complete, and cancel paths, replace service calls with:

```python
self.reminder_runtime.update_visible_reminder(...)
self.reminder_runtime.complete_visible_reminder(...)
self.reminder_runtime.cancel_visible_reminder(...)
```

- [ ] **Step 5: Run bridge tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_reminder_management_service.py \
  tests/unit/connector/clawscale_bridge/test_bridge_app.py \
  -k "reminder or reminders" \
  -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add connector/clawscale_bridge/reminder_management_service.py tests/unit/connector/clawscale_bridge/test_reminder_management_service.py
git commit -m "refactor(reminders): route bridge management through runtime contract"
```

---

### Task 5: Document Contract Boundary

**Files:**
- Modify: `docs/superpowers/specs/2026-05-14-reminder-runtime-contract-design.md`
- Modify: `docs/ARCHITECTURE.md`
- Optional if route surface wording changes: `docs/product-specs/FEATURE_TREE.md`

- [ ] **Step 1: Update spec status**

In `docs/superpowers/specs/2026-05-14-reminder-runtime-contract-design.md`, change:

```markdown
**Status:** draft, reviewed against internal follow-up unification
```

to:

```markdown
**Status:** implemented as in-process contract facade
```

Add this sentence to the Summary:

```markdown
The first implementation keeps Reminder in-process and routes current Agno,
PostAnalyze, and bridge/web management adapters through
`agent/reminder/runtime_contract.py`.
```

- [ ] **Step 2: Update architecture**

In `docs/ARCHITECTURE.md`, in the Reminder System bullet list, add:

```markdown
- `agent/reminder/runtime_contract.py` is the in-process Reminder Runtime
  Contract. Agno tools, PostAnalyze follow-up creation, and bridge reminder
  management adapters call this contract instead of owning reminder business
  behavior.
```

- [ ] **Step 3: Run docs checks**

Run:

```bash
zsh scripts/check
zsh scripts/verify-surface repo-os-docs
```

Expected: both PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-05-14-reminder-runtime-contract-design.md docs/ARCHITECTURE.md docs/product-specs/FEATURE_TREE.md
git commit -m "docs(reminders): describe runtime contract boundary"
```

If `docs/product-specs/FEATURE_TREE.md` was not modified, omit it from `git add`.

---

### Task 6: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused reminder contract and adapter tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/reminder/test_runtime_contract.py \
  tests/unit/reminder/test_service.py \
  tests/unit/agent/test_reminder_intent_capability.py \
  tests/unit/agent/test_post_analyze_deferred_actions.py \
  tests/unit/runner/test_reminder_event_handler.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run bridge reminder tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_reminder_management_service.py \
  tests/unit/connector/clawscale_bridge/test_bridge_app.py \
  -k "reminder or reminders" \
  -v
```

Expected: PASS.

- [ ] **Step 3: Run diff-aware routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected:

- `suggest-verification` returns surfaces that include worker/runtime and repo-os docs.
- `review-trigger` may require human review for sensitive architecture docs; that is acceptable and must be reported.

- [ ] **Step 4: Run suggested surfaces**

Run every command suggested by `scripts/suggest-verification`. If it suggests `worker-runtime`, run:

```bash
zsh scripts/verify-surface worker-runtime
```

Expected: PASS.

- [ ] **Step 5: Commit final verification notes if docs changed**

If verification results require a docs evidence note, add it to
`artifacts/evidence/2026-05-15-reminder-runtime-contract.md` and commit:

```bash
git add artifacts/evidence/
git commit -m "docs(reminders): record runtime contract verification"
```

If no evidence file is needed, do not create one.

---

## Implementation Notes

- Keep `ReminderService` as the behavioral owner for persistence, validation,
  and scheduler hooks in this first pass.
- Keep `ReminderFireEventHandler` and `ReminderScheduler` behavior unchanged
  except for docs and tests that describe the contract boundary.
- Do not add `origin=web` behavior in this plan.
- Do not add idempotency storage in this plan.
- Do not move natural-language parsing into `agent/reminder`.
- Do not route Coke's internal Agent through MCP or HTTP.

## Plan Self-Review

Spec coverage:

- Visible reminder CRUD maps to Tasks 1, 2, and 4.
- Internal follow-up create/replace/clear maps to Tasks 1 and 3.
- Adapter ownership maps to Tasks 2, 3, and 4.
- Docs and architecture updates map to Task 5.
- Verification maps to Task 6.

Deferred from this implementation:

- MCP adapter
- CLI adapter
- idempotency storage
- durable execution/outbox
- external target kinds
- `origin=web` product distinction
