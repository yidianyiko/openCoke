# Generalized Pending Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first reminder-focused pending workflow protocol so incomplete reminder turns persist durable workflow state, follow-up turns complete the same workflow, and reminder execution can expose a structured result envelope while preserving the existing visible-summary contract.

**Architecture:** Keep LLM interpretation inside `ReminderDetectAgent`, but move workflow lifecycle ownership into typed runtime side channels. Add a dedicated `pending_workflows` Mongo store, validate workflow updates with Pydantic models before persistence, and integrate the store through the existing `ReminderIntentPort` without reintroducing retired workflow runtimes or phrase-specific parsers.

**Tech Stack:** Python 3.12, Pydantic v2, PyMongo, pytest, Agno single-Agent runtime, Coke reminder protocol tool.

---

## Constraints

- Work in `/data/projects/coke/.worktrees/generalized-pending-workflow`.
- Do not add phrase-specific parser branches, prompt examples, or case hacks for `每个整点喊我打卡吧` or its follow-up.
- Keep `pending_task_draft` untouched. Pending reminder workflow state must live in `pending_workflows`.
- Preserve `CapabilityResult.visible_summary` and durable-write fail-closed behavior.
- Keep the Phase A feature flag default off: `pending_workflow.reminders.enabled=false`.
- Keep Phase B behind a separate flag: `pending_workflow.reminders.execution_envelope.enabled=false`.

## File Structure

- Create `agent/agno_agent/runtime/pending_workflow.py`: Pydantic envelope models, transition validation, invariant normalization, serialization helpers, and constants.
- Create `dao/pending_workflow_dao.py`: Mongo collection access, indexes, active load, insert/upsert, CAS update, terminal clear helpers, and close.
- Create `tests/unit/agent/test_pending_workflow_models.py`: model, transition, invariant, and serialization tests.
- Create `tests/unit/dao/test_pending_workflow_dao.py`: index and DAO behavior tests using mocked PyMongo collections.
- Modify `agent/agno_agent/schemas/reminder_detect_schema.py`: add optional `workflow_update` with the pending workflow model.
- Modify `agent/agno_agent/prompts/reminder_intent.py`: include active workflow JSON and revision in detector input only when provided by runtime.
- Modify `agent/agno_agent/runtime/context.py`: allow trusted runtime metadata to carry pending workflow data into capabilities.
- Modify `agent/agno_agent/capabilities/reminder_intent.py`: load/persist workflow state when enabled, handle invalid schema and illegal transitions, pass active workflow to the detector, execute only ready workflows, and keep legacy clarify behavior byte-for-byte when disabled.
- Modify `agent/agno_agent/adapters/reminder_command_executor.py`: optionally emit the Phase B execution envelope in `CapabilityResult.content` while preserving `summary`.
- Modify `conf/config.json`: add default-off feature flags under `features.pending_workflow.reminders`.
- Modify `tests/unit/agent/test_reminder_intent_capability.py`: flag-off legacy behavior, flag-on clarify persistence, follow-up execution, invalid schema fallback, stale CAS drop, and detector input assertions.
- Modify `tests/unit/agent/test_reminder_command_executor.py`: Phase B envelope tests.
- Modify `tests/evals/test_reminder_normal_path_eval.py` or `scripts/eval_reminder_normal_path_cases.py`: add a small two-turn pending-workflow eval hook that can run with high-frequency guards enabled and bypassed.
- Update `docs/superpowers/specs/2026-05-09-generalized-pending-workflow-design.md`: append implementation evidence and any intentionally deferred Phase A/Phase B evidence.

---

### Task 1: Pending Workflow Models

**Files:**
- Create: `agent/agno_agent/runtime/pending_workflow.py`
- Create: `tests/unit/agent/test_pending_workflow_models.py`

- [x] **Step 1: Write failing model tests**

Add `tests/unit/agent/test_pending_workflow_models.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError


def _workflow_payload(**overrides):
    now = datetime(2026, 5, 9, 1, 0, tzinfo=UTC)
    payload = {
        "id": "workflow_1",
        "kind": "reminder_create",
        "status": "awaiting_user",
        "origin": {
            "conversation_id": "conv-1",
            "message_ids": ["msg-1"],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
        },
        "goal": "Set up hourly check-in reminders",
        "slots": {
            "title": {"value": "打卡", "status": "filled"},
            "start_at": {"value": None, "status": "missing"},
            "deadline_at": {"value": None, "status": "missing"},
        },
        "missing_fields": ["start_at", "deadline_at"],
        "assumptions": [],
        "constraints": [],
        "next_steps": ["ask_user"],
        "payload": {"reminder": {"draft_operations": []}},
    }
    payload.update(overrides)
    return payload


def test_pending_workflow_model_accepts_spec_shape():
    from agent.agno_agent.runtime.pending_workflow import PendingWorkflowEnvelope

    workflow = PendingWorkflowEnvelope.model_validate(_workflow_payload())

    assert workflow.id == "workflow_1"
    assert workflow.kind == "reminder_create"
    assert workflow.missing_fields == ("start_at", "deadline_at")
    assert workflow.payload.reminder.draft_operations == ()


def test_pending_workflow_model_rejects_unknown_fields():
    from agent.agno_agent.runtime.pending_workflow import PendingWorkflowEnvelope

    with pytest.raises(ValidationError):
        PendingWorkflowEnvelope.model_validate(
            _workflow_payload(unexpected="not allowed")
        )


def test_ready_with_missing_fields_is_normalized_to_awaiting_user():
    from agent.agno_agent.runtime.pending_workflow import (
        PendingWorkflowEnvelope,
        normalize_workflow_invariants,
    )

    workflow = PendingWorkflowEnvelope.model_validate(
        _workflow_payload(status="ready_to_execute")
    )

    normalized, violations = normalize_workflow_invariants(workflow)

    assert normalized.status == "awaiting_user"
    assert violations == ("ready_with_missing_fields",)


def test_illegal_status_transition_is_rejected():
    from agent.agno_agent.runtime.pending_workflow import (
        PendingWorkflowEnvelope,
        validate_status_transition,
    )

    current = PendingWorkflowEnvelope.model_validate(_workflow_payload())
    proposed = PendingWorkflowEnvelope.model_validate(
        _workflow_payload(status="completed", missing_fields=[])
    )

    assert validate_status_transition(current.status, proposed.status) is False


def test_legal_ready_to_executing_transition_is_allowed():
    from agent.agno_agent.runtime.pending_workflow import validate_status_transition

    assert validate_status_transition("ready_to_execute", "executing") is True
```

- [x] **Step 2: Run the model tests and confirm they fail**

Run:

```bash
pytest tests/unit/agent/test_pending_workflow_models.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'agent.agno_agent.runtime.pending_workflow'`.

- [x] **Step 3: Implement pending workflow models**

Create `agent/agno_agent/runtime/pending_workflow.py` with:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

WorkflowKind = Literal[
    "reminder_create",
    "reminder_update",
    "reminder_cancel",
    "reminder_complete",
    "reminder_plan",
]
WorkflowStatus = Literal[
    "draft",
    "awaiting_user",
    "ready_to_execute",
    "executing",
    "completed",
    "cancelled",
    "expired",
    "failed",
]
SlotStatus = Literal[
    "missing",
    "filled",
    "assumed",
    "needs_confirmation",
    "invalid",
]
NextStep = Literal[
    "ask_user",
    "display_preview",
    "execute_now",
    "show_confirmation",
    "offer_modification",
    "notify_error",
    "no_action",
]

ACTIVE_WORKFLOW_STATUSES = (
    "draft",
    "awaiting_user",
    "ready_to_execute",
    "executing",
)
TERMINAL_WORKFLOW_STATUSES = ("completed", "cancelled", "expired", "failed")

_LEGAL_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"awaiting_user", "ready_to_execute"},
    "awaiting_user": {"awaiting_user", "ready_to_execute", "cancelled", "expired"},
    "ready_to_execute": {"executing", "awaiting_user", "expired"},
    "executing": {"completed", "failed", "awaiting_user"},
    "completed": set(),
    "cancelled": set(),
    "expired": set(),
    "failed": set(),
}


class WorkflowOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    message_ids: tuple[str, ...] = Field(default_factory=tuple)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class WorkflowSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any = None
    status: SlotStatus


class ReminderWorkflowPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_operations: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class WorkflowPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reminder: ReminderWorkflowPayload


class PendingWorkflowEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: WorkflowKind
    status: WorkflowStatus
    origin: WorkflowOrigin
    goal: str
    slots: dict[str, WorkflowSlot]
    missing_fields: tuple[str, ...] = Field(default_factory=tuple)
    assumptions: tuple[str, ...] = Field(default_factory=tuple)
    constraints: tuple[str, ...] = Field(default_factory=tuple)
    next_steps: tuple[NextStep, ...] = Field(default_factory=tuple)
    payload: WorkflowPayload

    @model_validator(mode="after")
    def enforce_conversation_and_slots(self) -> "PendingWorkflowEnvelope":
        if not self.id.strip():
            raise ValueError("workflow id is required")
        if not self.origin.conversation_id.strip():
            raise ValueError("origin.conversation_id is required")
        for field_name in self.missing_fields:
            slot = self.slots.get(field_name)
            if slot is None:
                raise ValueError(f"missing field {field_name!r} has no slot")
        return self


def validate_status_transition(current: str | None, proposed: str) -> bool:
    if current is None:
        return proposed in {"draft", "awaiting_user", "ready_to_execute"}
    return proposed in _LEGAL_STATUS_TRANSITIONS.get(current, set())


def normalize_workflow_invariants(
    workflow: PendingWorkflowEnvelope,
) -> tuple[PendingWorkflowEnvelope, tuple[str, ...]]:
    violations: list[str] = []
    has_unusable_slot = any(
        slot.status in {"missing", "invalid"} for slot in workflow.slots.values()
    )
    if workflow.status == "ready_to_execute" and (
        workflow.missing_fields or has_unusable_slot
    ):
        workflow = workflow.model_copy(update={"status": "awaiting_user"})
        violations.append("ready_with_missing_fields")
    return workflow, tuple(violations)


def workflow_to_document(workflow: PendingWorkflowEnvelope) -> dict[str, Any]:
    return workflow.model_dump(mode="json")
```

- [x] **Step 4: Run the model tests and confirm they pass**

Run:

```bash
pytest tests/unit/agent/test_pending_workflow_models.py -q
```

Expected: all tests pass.

- [x] **Step 5: Commit Task 1**

Run:

```bash
git add agent/agno_agent/runtime/pending_workflow.py tests/unit/agent/test_pending_workflow_models.py
git commit -m "feat: add pending workflow envelope models"
```

---

### Task 2: Pending Workflow DAO And Flags

**Files:**
- Create: `dao/pending_workflow_dao.py`
- Create: `tests/unit/dao/test_pending_workflow_dao.py`
- Modify: `conf/config.json`

- [x] **Step 1: Write failing DAO and flag tests**

Add `tests/unit/dao/test_pending_workflow_dao.py`:

```python
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock


def _document(status="awaiting_user", revision=0):
    now = datetime(2026, 5, 9, 1, 0, tzinfo=UTC)
    return {
        "id": "workflow_1",
        "owner_user_id": "user-1",
        "conversation_id": "conv-1",
        "kind": "reminder_create",
        "status": status,
        "revision": revision,
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(days=1),
        "document": {
            "id": "workflow_1",
            "kind": "reminder_create",
            "status": status,
            "origin": {
                "conversation_id": "conv-1",
                "message_ids": ["msg-1"],
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "expires_at": (now + timedelta(days=1)).isoformat(),
            },
            "goal": "Set up reminder",
            "slots": {"title": {"value": "打卡", "status": "filled"}},
            "missing_fields": [],
            "assumptions": [],
            "constraints": [],
            "next_steps": ["execute_now"],
            "payload": {"reminder": {"draft_operations": []}},
        },
    }


def test_create_indexes_uses_partial_unique_active_index(mock_collection):
    from dao.pending_workflow_dao import PendingWorkflowDAO

    dao = PendingWorkflowDAO()
    dao.collection = mock_collection

    dao.create_indexes()

    calls = mock_collection.create_index.call_args_list
    assert any(
        call.args[0] == [("owner_user_id", 1), ("conversation_id", 1)]
        and call.kwargs["unique"] is True
        and call.kwargs["partialFilterExpression"]["status"]["$in"]
        == ["draft", "awaiting_user", "ready_to_execute", "executing"]
        for call in calls
    )
    assert any(call.args[0] == [("expires_at", 1)] for call in calls)
    assert any(call.args[0] == [("status", 1), ("updated_at", 1)] for call in calls)


def test_load_active_for_conversation_filters_active_statuses(mock_collection):
    from dao.pending_workflow_dao import PendingWorkflowDAO

    dao = PendingWorkflowDAO()
    dao.collection = mock_collection
    mock_collection.find_one.return_value = _document()

    result = dao.load_active_for_conversation("user-1", "conv-1")

    assert result["id"] == "workflow_1"
    mock_collection.find_one.assert_called_once_with(
        {
            "owner_user_id": "user-1",
            "conversation_id": "conv-1",
            "status": {"$in": ["draft", "awaiting_user", "ready_to_execute", "executing"]},
        },
        sort=[("updated_at", -1)],
    )


def test_upsert_new_active_workflow_sets_revision_zero(mock_collection):
    from dao.pending_workflow_dao import PendingWorkflowDAO

    dao = PendingWorkflowDAO()
    dao.collection = mock_collection
    document = _document(revision=7)

    dao.upsert_new_active_workflow(document)

    written = mock_collection.update_one.call_args.args[1]
    assert written["$set"]["revision"] == 0
    assert written["$set"]["id"] == "workflow_1"


def test_cas_update_requires_expected_revision_and_increments(mock_collection):
    from dao.pending_workflow_dao import PendingWorkflowDAO

    dao = PendingWorkflowDAO()
    dao.collection = mock_collection
    mock_collection.update_one.return_value = MagicMock(matched_count=1)

    assert dao.cas_update_workflow("workflow_1", 3, _document(revision=3)) is True

    selector, update = mock_collection.update_one.call_args.args
    assert selector == {"id": "workflow_1", "revision": 3}
    assert update["$set"]["revision"] == 4


def test_cas_update_returns_false_on_stale_revision(mock_collection):
    from dao.pending_workflow_dao import PendingWorkflowDAO

    dao = PendingWorkflowDAO()
    dao.collection = mock_collection
    mock_collection.update_one.return_value = MagicMock(matched_count=0)

    assert dao.cas_update_workflow("workflow_1", 3, _document(revision=3)) is False


def test_pending_workflow_flags_default_off():
    from conf.config import CONF

    flags = CONF["features"]["pending_workflow"]["reminders"]
    assert flags["enabled"] is False
    assert flags["execution_envelope"]["enabled"] is False
```

Also add this fixture to the file:

```python
import pytest


@pytest.fixture
def mock_collection(monkeypatch):
    from dao import pending_workflow_dao as dao_module

    collection = MagicMock()
    db = MagicMock()
    db.get_collection.return_value = collection
    client = MagicMock()
    client.__getitem__.return_value = db
    monkeypatch.setattr(dao_module, "MongoClient", MagicMock(return_value=client))
    return collection
```

- [x] **Step 2: Run the DAO tests and confirm they fail**

Run:

```bash
pytest tests/unit/dao/test_pending_workflow_dao.py -q
```

Expected: fail until `dao.pending_workflow_dao` and flags exist.

- [x] **Step 3: Add feature flags**

In `conf/config.json`, add under top-level `features`:

```json
"pending_workflow": {
  "reminders": {
    "enabled": false,
    "execution_envelope": {
      "enabled": false
    }
  }
}
```

- [x] **Step 4: Implement the DAO**

Create `dao/pending_workflow_dao.py` with:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection

from agent.agno_agent.runtime.pending_workflow import ACTIVE_WORKFLOW_STATUSES
from conf.config import CONF


class PendingWorkflowDAO:
    COLLECTION = "pending_workflows"

    def __init__(
        self,
        mongo_uri: str = "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/",
        db_name: str = CONF["mongodb"]["mongodb_name"],
    ) -> None:
        self.client = MongoClient(mongo_uri, tz_aware=True)
        self.db = self.client[db_name]
        self.collection: Collection = self.db.get_collection(self.COLLECTION)

    def create_indexes(self) -> None:
        self.collection.create_index(
            [("owner_user_id", 1), ("conversation_id", 1)],
            unique=True,
            partialFilterExpression={"status": {"$in": list(ACTIVE_WORKFLOW_STATUSES)}},
        )
        self.collection.create_index([("expires_at", 1)], expireAfterSeconds=0)
        self.collection.create_index([("status", 1), ("updated_at", 1)])

    def load_active_for_conversation(
        self, owner_user_id: str, conversation_id: str
    ) -> dict[str, Any] | None:
        return self.collection.find_one(
            {
                "owner_user_id": owner_user_id,
                "conversation_id": conversation_id,
                "status": {"$in": list(ACTIVE_WORKFLOW_STATUSES)},
            },
            sort=[("updated_at", -1)],
        )

    def upsert_new_active_workflow(self, document: dict[str, Any]) -> bool:
        write_doc = dict(document)
        write_doc["revision"] = 0
        result = self.collection.update_one(
            {
                "owner_user_id": write_doc["owner_user_id"],
                "conversation_id": write_doc["conversation_id"],
                "status": {"$in": list(ACTIVE_WORKFLOW_STATUSES)},
            },
            {"$set": write_doc},
            upsert=True,
        )
        return result.matched_count > 0 or result.upserted_id is not None

    def cas_update_workflow(
        self,
        workflow_id: str,
        expected_revision: int,
        document: dict[str, Any],
    ) -> bool:
        write_doc = dict(document)
        write_doc["revision"] = expected_revision + 1
        write_doc["updated_at"] = write_doc.get("updated_at") or datetime.now().astimezone()
        result = self.collection.update_one(
            {"id": workflow_id, "revision": expected_revision},
            {"$set": write_doc},
        )
        return result.matched_count > 0

    def close(self) -> None:
        self.client.close()
```

- [x] **Step 5: Run the DAO tests**

Run:

```bash
pytest tests/unit/dao/test_pending_workflow_dao.py -q
```

Expected: all tests pass.

- [x] **Step 6: Commit Task 2**

Run:

```bash
git add conf/config.json dao/pending_workflow_dao.py tests/unit/dao/test_pending_workflow_dao.py
git commit -m "feat: add pending workflow store"
```

---

### Task 3: Detector Schema And Prompt Input

**Files:**
- Modify: `agent/agno_agent/schemas/reminder_detect_schema.py`
- Modify: `agent/agno_agent/prompts/reminder_intent.py`
- Modify: `agent/agno_agent/runtime/context.py`
- Modify: `tests/unit/test_reminder_detect_structured_output.py`
- Modify: `tests/unit/agent/test_reminder_intent_capability.py`

- [x] **Step 1: Add failing schema and prompt tests**

Append to `tests/unit/test_reminder_detect_structured_output.py`:

```python
def test_reminder_detect_schema_accepts_workflow_update():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="clarify",
        action="",
        clarification_question="每个整点打卡要从什么时候开始，持续到什么时候结束？",
        workflow_update={
            "id": "workflow_1",
            "kind": "reminder_create",
            "status": "awaiting_user",
            "origin": {
                "conversation_id": "conv-1",
                "message_ids": ["msg-1"],
                "created_at": "2026-05-09T01:00:00+00:00",
                "updated_at": "2026-05-09T01:00:00+00:00",
                "expires_at": "2026-05-10T01:00:00+00:00",
            },
            "goal": "Set up hourly check-in reminders",
            "slots": {
                "title": {"value": "打卡", "status": "filled"},
                "start_at": {"value": None, "status": "missing"},
            },
            "missing_fields": ["start_at"],
            "assumptions": [],
            "constraints": [],
            "next_steps": ["ask_user"],
            "payload": {"reminder": {"draft_operations": []}},
        },
    )

    assert decision.workflow_update is not None
    assert decision.workflow_update.id == "workflow_1"


def test_reminder_detect_schema_rejects_free_form_workflow_key():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="clarify",
            action="",
            clarification_question="还需要结束时间。",
            workflow={"id": "wrong"},
        )
```

Append to `tests/unit/agent/test_reminder_intent_capability.py`:

```python
def test_build_reminder_intent_input_includes_active_pending_workflow_from_metadata():
    from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input

    context = _run_context()
    context = type(context)(
        user=context.user,
        character=context.character,
        conversation=context.conversation,
        relation=context.relation,
        platform=context.platform,
        recent_chat_history=context.recent_chat_history,
        current_time=context.current_time,
        runtime_metadata={
            "pending_workflow": {
                "revision": 2,
                "document": {"id": "workflow_1", "status": "awaiting_user"},
            }
        },
    )

    prompt = build_reminder_intent_input("从现在到晚上七点", context)

    assert "### Active Pending Workflow" in prompt
    assert '"revision": 2' in prompt
    assert '"id": "workflow_1"' in prompt
```

- [x] **Step 2: Run the tests and confirm they fail**

Run:

```bash
pytest tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_schema_accepts_workflow_update tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_schema_rejects_free_form_workflow_key tests/unit/agent/test_reminder_intent_capability.py::test_build_reminder_intent_input_includes_active_pending_workflow_from_metadata -q
```

Expected: fail until `workflow_update` and prompt metadata are implemented.

- [x] **Step 3: Extend the schema**

In `agent/agno_agent/schemas/reminder_detect_schema.py`, import:

```python
from agent.agno_agent.runtime.pending_workflow import PendingWorkflowEnvelope
```

Add this field to `ReminderDetectDecision`:

```python
workflow_update: PendingWorkflowEnvelope | None = Field(
    default=None,
    description="Validated pending workflow envelope for clarification lifecycle.",
)
```

Do not add `workflow` or allow unknown keys.

- [x] **Step 4: Include active workflow in prompt input**

In `agent/agno_agent/prompts/reminder_intent.py`, import `json` and build optional workflow text:

```python
import json
```

Inside `build_reminder_intent_input`, before the return:

```python
    pending_workflow = run_context.runtime_metadata.get("pending_workflow")
    workflow_lines: list[str] = []
    if pending_workflow:
        workflow_lines = [
            "",
            "### Active Pending Workflow",
            json.dumps(pending_workflow, ensure_ascii=False, sort_keys=True),
        ]
```

Insert `*workflow_lines` before `"### 当前用户消息"`.

- [x] **Step 5: Run the focused tests**

Run:

```bash
pytest tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py::test_build_reminder_intent_input_includes_active_pending_workflow_from_metadata -q
```

Expected: all selected tests pass.

- [x] **Step 6: Commit Task 3**

Run:

```bash
git add agent/agno_agent/schemas/reminder_detect_schema.py agent/agno_agent/prompts/reminder_intent.py tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py
git commit -m "feat: pass pending workflow through reminder detector"
```

---

### Task 4: Phase A Runtime Lifecycle Integration

**Files:**
- Modify: `agent/agno_agent/capabilities/reminder_intent.py`
- Modify: `tests/unit/agent/test_reminder_intent_capability.py`

- [x] **Step 1: Add failing runtime lifecycle tests**

Append to `tests/unit/agent/test_reminder_intent_capability.py`:

```python
@pytest.mark.asyncio
async def test_pending_workflow_flag_off_keeps_legacy_clarify_behavior(monkeypatch):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            assert "Active Pending Workflow" not in input
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "什么时候开始？",
                }
            )

    result = await ReminderIntentPort(detector_agent=PrimaryAgent(), retry_agent=None).run(
        "每个整点喊我打卡吧",
        _run_context(),
    )

    assert result.content == {
        "action": "clarify",
        "intent_type": "clarify",
        "summary": "什么时候开始？",
    }
    assert result.metadata["durable_write"] is False


@pytest.mark.asyncio
async def test_pending_workflow_flag_on_persists_clarify_workflow(monkeypatch):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    saved = []

    class FakeDAO:
        def load_active_for_conversation(self, owner_user_id, conversation_id):
            return None

        def upsert_new_active_workflow(self, document):
            saved.append(document)
            return True

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "每个整点打卡要从什么时候开始，持续到什么时候结束？",
                    "workflow_update": {
                        "id": "workflow_1",
                        "kind": "reminder_create",
                        "status": "awaiting_user",
                        "origin": {
                            "conversation_id": "conv-1",
                            "message_ids": ["msg-1"],
                            "created_at": "2026-05-06T01:00:00+00:00",
                            "updated_at": "2026-05-06T01:00:00+00:00",
                            "expires_at": "2026-05-07T01:00:00+00:00",
                        },
                        "goal": "Set up whole-hour check-in reminders",
                        "slots": {
                            "title": {"value": "打卡", "status": "filled"},
                            "start_at": {"value": None, "status": "missing"},
                        },
                        "missing_fields": ["start_at"],
                        "assumptions": [],
                        "constraints": [],
                        "next_steps": ["ask_user"],
                        "payload": {"reminder": {"draft_operations": []}},
                    },
                }
            )

    port = ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    )

    result = await port.run("每个整点喊我打卡吧", _run_context())

    assert result.content["summary"] == "每个整点打卡要从什么时候开始，持续到什么时候结束？"
    assert saved[0]["id"] == "workflow_1"
    assert saved[0]["owner_user_id"] == "user-1"
    assert saved[0]["conversation_id"] == "conv-1"
    assert saved[0]["revision"] == 0


@pytest.mark.asyncio
async def test_pending_workflow_followup_uses_loaded_workflow_and_cas_updates(monkeypatch):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    active = {
        "id": "workflow_1",
        "owner_user_id": "user-1",
        "conversation_id": "conv-1",
        "kind": "reminder_create",
        "status": "awaiting_user",
        "revision": 4,
        "created_at": _run_context().current_time,
        "updated_at": _run_context().current_time,
        "expires_at": _run_context().current_time,
        "document": {
            "id": "workflow_1",
            "kind": "reminder_create",
            "status": "awaiting_user",
            "origin": {
                "conversation_id": "conv-1",
                "message_ids": ["msg-1"],
                "created_at": "2026-05-06T01:00:00+00:00",
                "updated_at": "2026-05-06T01:00:00+00:00",
                "expires_at": "2026-05-07T01:00:00+00:00",
            },
            "goal": "Set up whole-hour check-in reminders",
            "slots": {"start_at": {"value": None, "status": "missing"}},
            "missing_fields": ["start_at"],
            "assumptions": [],
            "constraints": [],
            "next_steps": ["ask_user"],
            "payload": {"reminder": {"draft_operations": []}},
        },
    }
    updates = []

    class FakeDAO:
        def load_active_for_conversation(self, owner_user_id, conversation_id):
            return active

        def cas_update_workflow(self, workflow_id, expected_revision, document):
            updates.append((workflow_id, expected_revision, document))
            return True

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            assert '"revision": 4' in input
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "打卡",
                    "trigger_at": "2026-05-06T02:00:00+00:00",
                    "workflow_update": {
                        **active["document"],
                        "status": "ready_to_execute",
                        "slots": {"start_at": {"value": "now", "status": "filled"}},
                        "missing_fields": [],
                        "next_steps": ["execute_now"],
                    },
                }
            )

    class FakeExecutor:
        def execute(self, decision, run_context):
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：打卡"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("从现在到晚上七点", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：打卡"
    assert updates[0][0] == "workflow_1"
    assert updates[0][1] == 4
    assert updates[0][2]["status"] == "ready_to_execute"


@pytest.mark.asyncio
async def test_pending_workflow_illegal_transition_preserves_existing_workflow():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    active = {
        "id": "workflow_1",
        "owner_user_id": "user-1",
        "conversation_id": "conv-1",
        "status": "awaiting_user",
        "revision": 2,
        "document": {
            "id": "workflow_1",
            "kind": "reminder_create",
            "status": "awaiting_user",
            "origin": {
                "conversation_id": "conv-1",
                "message_ids": [],
                "created_at": "2026-05-06T01:00:00+00:00",
                "updated_at": "2026-05-06T01:00:00+00:00",
                "expires_at": "2026-05-07T01:00:00+00:00",
            },
            "goal": "Set up reminder",
            "slots": {"title": {"value": "打卡", "status": "filled"}},
            "missing_fields": [],
            "assumptions": [],
            "constraints": [],
            "next_steps": ["ask_user"],
            "payload": {"reminder": {"draft_operations": []}},
        },
    }

    class FakeDAO:
        def load_active_for_conversation(self, owner_user_id, conversation_id):
            return active

        def cas_update_workflow(self, workflow_id, expected_revision, document):
            raise AssertionError("illegal transition must not be persisted")

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "还需要什么？",
                    "workflow_update": {**active["document"], "status": "completed"},
                }
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("继续", _run_context())

    assert result.content["summary"] == "还需要什么？"
```

- [x] **Step 2: Run the lifecycle tests and confirm they fail**

Run:

```bash
pytest tests/unit/agent/test_reminder_intent_capability.py::test_pending_workflow_flag_off_keeps_legacy_clarify_behavior tests/unit/agent/test_reminder_intent_capability.py::test_pending_workflow_flag_on_persists_clarify_workflow tests/unit/agent/test_reminder_intent_capability.py::test_pending_workflow_followup_uses_loaded_workflow_and_cas_updates tests/unit/agent/test_reminder_intent_capability.py::test_pending_workflow_illegal_transition_preserves_existing_workflow -q
```

Expected: flag-off test passes or fails only on constructor signature; others fail until lifecycle integration exists.

- [x] **Step 3: Implement lifecycle support in `ReminderIntentPort`**

In `agent/agno_agent/capabilities/reminder_intent.py`:

- import `CONF`, `PendingWorkflowDAO`, and pending workflow helpers
- add optional constructor args `pending_workflow_enabled: bool | None = None` and `pending_workflow_dao: Any | None = None`
- resolve default flag from `CONF["features"]["pending_workflow"]["reminders"]["enabled"]`
- when enabled, load active workflow before detector call
- copy `run_context` with `runtime_metadata={"pending_workflow": {"revision": revision, "document": document}}`
- after detector output, validate and persist `workflow_update`
- for new workflows call `upsert_new_active_workflow`
- for existing workflows call `cas_update_workflow(id, revision, document)`
- reject illegal transitions and log `workflow_invariant_violation`
- on stale CAS failure, log `workflow_concurrent_write_dropped`
- keep `_clarification_result(decision)` as the rendered clarify response

Use this helper shape inside the file:

```python
def _pending_workflow_flags() -> dict[str, Any]:
    return (
        CONF.get("features", {})
        .get("pending_workflow", {})
        .get("reminders", {})
    )
```

Use this document builder:

```python
def _workflow_storage_document(workflow, run_context, *, revision: int) -> dict[str, Any]:
    document = workflow_to_document(workflow)
    return {
        "id": workflow.id,
        "owner_user_id": run_context.user.id,
        "conversation_id": run_context.conversation.id,
        "kind": workflow.kind,
        "status": workflow.status,
        "revision": revision,
        "created_at": workflow.origin.created_at,
        "updated_at": workflow.origin.updated_at,
        "expires_at": workflow.origin.expires_at,
        "document": document,
    }
```

- [x] **Step 4: Run lifecycle tests**

Run:

```bash
pytest tests/unit/agent/test_reminder_intent_capability.py -q
```

Expected: all tests in the file pass.

- [x] **Step 5: Commit Task 4**

Run:

```bash
git add agent/agno_agent/capabilities/reminder_intent.py tests/unit/agent/test_reminder_intent_capability.py
git commit -m "feat: persist pending reminder workflows"
```

---

### Task 5: Phase B Execution Envelope

**Files:**
- Modify: `agent/agno_agent/adapters/reminder_command_executor.py`
- Modify: `tests/unit/agent/test_reminder_command_executor.py`

- [x] **Step 1: Add failing envelope tests**

Append to `tests/unit/agent/test_reminder_command_executor.py`:

```python
def test_execution_envelope_flag_adds_structured_content_without_losing_summary():
    def tool_entrypoint(**kwargs):
        return "已创建提醒：hydrate（2026-05-01 09:00）"

    result = ReminderCommandExecutor(
        tool_entrypoint,
        session_state_setter=lambda session_state: None,
        execution_envelope_enabled=True,
    ).execute(
        SimpleNamespace(
            action="create",
            title="hydrate",
            trigger_at="2026-05-01T09:00:00+09:00",
        ),
        _run_context(),
    )

    assert result.visible_summary == "已创建提醒：hydrate（2026-05-01 09:00）"
    assert result.content["execution"]["status"] == "success"
    assert result.content["execution"]["operation"] == "create_reminder"
    assert result.content["execution"]["visible_summary"] == "已创建提醒：hydrate（2026-05-01 09:00）"
    assert result.content["execution"]["next_steps"] == [
        "show_confirmation",
        "offer_modification",
    ]


def test_execution_envelope_flag_off_keeps_existing_content_shape():
    def tool_entrypoint(**kwargs):
        return "Reminder created."

    result = ReminderCommandExecutor(
        tool_entrypoint,
        session_state_setter=lambda session_state: None,
    ).execute(
        SimpleNamespace(action="create", title="hydrate", trigger_at="2026-05-01T09:00:00+09:00"),
        _run_context(),
    )

    assert "execution" not in result.content
    assert result.content["summary"] == "Reminder created."
```

- [x] **Step 2: Run the envelope tests and confirm they fail**

Run:

```bash
pytest tests/unit/agent/test_reminder_command_executor.py::test_execution_envelope_flag_adds_structured_content_without_losing_summary tests/unit/agent/test_reminder_command_executor.py::test_execution_envelope_flag_off_keeps_existing_content_shape -q
```

Expected: fail until the constructor flag and envelope are implemented.

- [x] **Step 3: Implement optional execution envelope**

In `agent/agno_agent/adapters/reminder_command_executor.py`, add constructor argument:

```python
execution_envelope_enabled: bool | None = None
```

Resolve the default from:

```python
CONF["features"]["pending_workflow"]["reminders"]["execution_envelope"]["enabled"]
```

For successful execution, keep the existing keys and add:

```python
"execution": {
    "status": "success",
    "operation": f"{action}_reminder" if action else "reminder_operation",
    "entities": [],
    "visible_summary": summary,
    "next_steps": ["show_confirmation", "offer_modification"],
}
```

Do not remove `summary`, `owner_user_id`, or `conversation_id`.

- [x] **Step 4: Run command executor tests**

Run:

```bash
pytest tests/unit/agent/test_reminder_command_executor.py -q
```

Expected: all tests in the file pass.

- [x] **Step 5: Commit Task 5**

Run:

```bash
git add agent/agno_agent/adapters/reminder_command_executor.py tests/unit/agent/test_reminder_command_executor.py
git commit -m "feat: add optional reminder execution envelope"
```

---

### Task 6: Eval Hook, Evidence Notes, And Verification Routing

**Files:**
- Modify: `scripts/eval_reminder_normal_path_cases.py` or `tests/evals/test_reminder_normal_path_eval.py`
- Modify: `docs/superpowers/specs/2026-05-09-generalized-pending-workflow-design.md`
- Modify: `docs/superpowers/plans/2026-05-09-generalized-pending-workflow.md`

- [x] **Step 1: Add an eval/test marker for two-turn pending workflow**

If the eval runner already supports multi-turn cases, add a case named:

```text
pending-workflow-hourly-checkin-two-turn
```

with user turns:

```text
每个整点喊我打卡吧
从现在到晚上七点
```

If the runner cannot support the two-turn case in this change, add a pytest-level test in `tests/evals/test_reminder_normal_path_eval.py` that asserts the case manifest exists and documents that real-model corpus evidence remains open.

- [x] **Step 2: Record implementation evidence fields in the spec**

Append this section to `docs/superpowers/specs/2026-05-09-generalized-pending-workflow-design.md`:

```markdown
## Implementation Evidence

Implementation branch: `generalized-pending-workflow`

Fresh evidence produced during implementation:

- Pending workflow model tests: `pytest tests/unit/agent/test_pending_workflow_models.py -q`
- Pending workflow DAO tests: `pytest tests/unit/dao/test_pending_workflow_dao.py -q`
- Reminder detector schema and capability tests: `pytest tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py -q`
- Reminder execution envelope tests: `pytest tests/unit/agent/test_reminder_command_executor.py -q`

Open evidence before Phase A GA:

- two-turn runtime/eval proof path through `business-clawscale`
- ablation run with high-frequency guards bypassed via test harness
- `workflow_schema_invalid` rate across at least 50 representative two-turn decisions
```

- [x] **Step 3: Mark completed plan tasks as checked**

As tasks complete, replace each completed checkbox in this plan from `- [ ]` to `- [x]` only after its command evidence exists.

- [x] **Step 4: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: worker-runtime and repo-os surfaces are suggested; review trigger may flag non-trivial runtime/docs changes.

- [x] **Step 5: Commit Task 6**

Run:

```bash
git add scripts/eval_reminder_normal_path_cases.py tests/evals/test_reminder_normal_path_eval.py docs/superpowers/specs/2026-05-09-generalized-pending-workflow-design.md docs/superpowers/plans/2026-05-09-generalized-pending-workflow.md
git commit -m "test: add pending workflow eval evidence hooks"
```

---

### Task 7: Final Verification

**Files:**
- No new files unless verification reveals a defect.

- [ ] **Step 1: Run focused worker-runtime tests**

Run:

```bash
pytest tests/unit/agent/test_pending_workflow_models.py tests/unit/dao/test_pending_workflow_dao.py tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_reminder_command_executor.py tests/unit/agent/test_agent_runtime_durable_write_contract.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run repo structure and workflow checks**

Run:

```bash
zsh scripts/check
```

Expected: exits 0.

- [ ] **Step 3: Run verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: output names worker-runtime and repo-os surfaces; record any review trigger in the final response.

- [ ] **Step 4: Inspect diff for forbidden shortcuts**

Run:

```bash
git diff --check
rg -n "每个整点|从现在到晚上七点|high.frequency|phrase|parser shortcut|pending_task_draft" agent dao tests scripts docs/superpowers/specs/2026-05-09-generalized-pending-workflow-design.md
```

Expected: no phrase-specific runtime branch or prompt example added; any `pending_task_draft` hit is from existing tests/docs or the spec explaining why it is not used.

- [ ] **Step 5: Commit any final fixes**

If Step 1-4 required changes, commit them:

```bash
git add <changed-files>
git commit -m "fix: close pending workflow verification gaps"
```

If no changes were required, do not create an empty commit.
