# Internal Follow-up Reminder Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store agent-created proactive follow-ups as internal reminders in MongoDB `reminders`, fire them through the Reminder System, and remove the old `deferred_actions.kind=proactive_followup` runtime path.

**Architecture:** The Reminder System remains the only scheduling substrate for visible reminders and internal follow-ups. `Reminder` gains explicit `origin`, `visibility`, `fire_mode`, `prompt`, and `metadata` fields with no legacy missing-field compatibility; visible management paths filter `visibility="visible"` and internal follow-up helpers filter `visibility="internal"` plus `fire_mode="followup"`. `PostAnalyzeWorkflow` writes internal reminders through `ReminderService`, and `ReminderFireEventHandler` routes `fire_mode="followup"` into the normal typed agent runtime using the stored prompt.

**Tech Stack:** Python 3.12, dataclasses, PyMongo, APScheduler, pytest, Flask bridge, existing gateway API/web tests, Mongo-backed runtime state.

---

## Pre-Reading

- `AGENTS.md`
- `docs/design-docs/index.md`
- `docs/design-docs/human-ai-working-contract.md`
- `docs/ARCHITECTURE.md`
- `docs/product-specs/FEATURE_TREE.md`
- `docs/fitness/coke-verification-matrix.md`
- `docs/superpowers/specs/2026-05-13-internal-followup-reminder-unification-design.md`

## File Map

- Modify: `agent/reminder/models.py` - add reminder classification fields and pass them through fired events.
- Modify: `agent/reminder/service.py` - write required fields, validate visible/internal combinations, add internal follow-up create/replace/clear helpers, and keep user-facing operations visible-only.
- Modify: `dao/reminder_dao.py` - add explicit visibility filters, active internal follow-up lookup/update helpers, and the partial unique index.
- Modify: `agent/runner/reminder_scheduler.py` - include `fire_mode`, `prompt`, and `metadata` on `ReminderFiredEvent`.
- Modify: `agent/runner/reminder_event_handler.py` - branch `notify` versus `followup`; follow-up fires via typed runtime with stored prompt and internal metadata.
- Modify: `agent/agno_agent/workflows/post_analyze_workflow.py` - replace `DeferredActionService` usage with `ReminderService`.
- Modify: `agent/agno_agent/runtime/inputs.py` only if existing `ReminderFirePayload` lacks fields needed for `prompt` and metadata.
- Modify: `connector/clawscale_bridge/reminder_management_service.py` - serialize new fields when useful, but visible management must not expose internal reminders.
- Modify: `agent/agno_agent/tools/deferred_action/service.py` - remove proactive follow-up create/clear helpers after the new path is green.
- Modify: `dao/deferred_action_dao.py` - remove `find_active_internal_followup` after callers are gone.
- Modify: `agent/runner/deferred_action_executor.py` - remove the proactive-specific input branch after no runtime caller depends on it.
- Modify: `docs/ARCHITECTURE.md` and `docs/product-specs/FEATURE_TREE.md` - move proactive follow-up ownership from `deferred_actions` to `reminders`.
- Tests: `tests/unit/reminder/test_service.py`, `tests/unit/dao/test_reminder_dao.py`, `tests/unit/runner/test_reminder_scheduler.py`, `tests/unit/runner/test_reminder_event_handler.py`, `tests/unit/agent/test_post_analyze_deferred_actions.py`, `tests/e2e/test_reminder_system_flow.py`, deferred-action tests that remain relevant, bridge and gateway reminder-management tests.

## Commit Plan

Commit after each task:

1. `feat(reminders): classify visible and internal reminders`
2. `feat(reminders): add internal followup service path`
3. `feat(agent): write followups through reminder service`
4. `feat(reminders): fire internal followups through runtime`
5. `refactor(deferred-actions): remove proactive followup path`
6. `docs(reminders): update followup ownership docs`

## Task 1: Add Required Reminder Classification Fields

**Files:**
- Modify: `agent/reminder/models.py`
- Modify: `agent/reminder/service.py`
- Modify: `dao/reminder_dao.py`
- Test: `tests/unit/reminder/test_service.py`
- Test: `tests/unit/dao/test_reminder_dao.py`

- [ ] **Step 1: Add failing service tests for visible reminder fields and missing-field exclusion**

Append to `tests/unit/reminder/test_service.py`:

```python
def test_create_visible_reminder_writes_required_classification_fields():
    service, dao, _ = make_service()

    reminder = service.create(owner_user_id="user-1", command=create_command())

    assert reminder.origin == "user"
    assert reminder.visibility == "visible"
    assert reminder.fire_mode == "notify"
    assert reminder.prompt is None
    assert reminder.metadata == {}
    assert dao.documents[reminder.id]["origin"] == "user"
    assert dao.documents[reminder.id]["visibility"] == "visible"
    assert dao.documents[reminder.id]["fire_mode"] == "notify"
    assert dao.documents[reminder.id]["prompt"] is None
    assert dao.documents[reminder.id]["metadata"] == {}


def test_list_for_user_excludes_internal_and_missing_visibility_rows():
    service, dao, _ = make_service()
    visible = service.create(
        owner_user_id="user-1",
        command=create_command(title="visible"),
    )
    internal_doc = {
        **dao.documents[visible.id],
        "_id": "rem-internal",
        "title": "internal",
        "origin": "agent",
        "visibility": "internal",
        "fire_mode": "followup",
        "prompt": "ask about progress",
        "metadata": {"proactive_times": 0},
    }
    legacy_doc = {
        **dao.documents[visible.id],
        "_id": "rem-legacy",
        "title": "legacy without visibility",
    }
    for key in ("origin", "visibility", "fire_mode", "prompt", "metadata"):
        legacy_doc.pop(key, None)
    dao.documents["rem-internal"] = internal_doc
    dao.documents["rem-legacy"] = legacy_doc

    reminders = service.list_for_user(
        owner_user_id="user-1",
        query=ReminderQuery(lifecycle_states=["active"]),
    )

    assert [reminder.title for reminder in reminders] == ["visible"]
```

- [ ] **Step 2: Run the new service tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/reminder/test_service.py::test_create_visible_reminder_writes_required_classification_fields \
  tests/unit/reminder/test_service.py::test_list_for_user_excludes_internal_and_missing_visibility_rows \
  -v
```

Expected: FAIL because `Reminder` has no `origin`, `visibility`, `fire_mode`, `prompt`, or `metadata`, and list filtering does not exclude missing visibility rows.

- [ ] **Step 3: Add DAO tests for explicit visible filters and index shape**

Update `tests/unit/dao/test_reminder_dao.py`.

In `test_create_indexes_creates_required_indexes`, assert a partial internal follow-up index:

```python
        assert (
            (
                [
                    ("owner_user_id", 1),
                    ("agent_output_target.conversation_id", 1),
                ],
            ),
            {
                "unique": True,
                "partialFilterExpression": {
                    "visibility": "internal",
                    "fire_mode": "followup",
                    "lifecycle_state": "active",
                },
            },
        ) in calls
```

Change `test_list_for_owner_filters_by_owner_and_lifecycle_states` expected selector to:

```python
        mock_collection.find.assert_called_once_with(
            {
                "owner_user_id": "user_1",
                "visibility": "visible",
                "lifecycle_state": {"$in": ["active", "paused"]},
            }
        )
```

Change `test_list_for_owner_all_states_when_lifecycle_states_omitted` expected selector to:

```python
        mock_collection.find.assert_called_once_with(
            {"owner_user_id": "user_1", "visibility": "visible"}
        )
```

Change `test_list_for_owner_in_local_date_range_filters_owner_state_and_dates` expected selector to include visible-only:

```python
        mock_collection.find.assert_called_once_with(
            {
                "owner_user_id": "user_1",
                "visibility": "visible",
                "lifecycle_state": {"$in": ["active"]},
                "schedule.local_date": {
                    "$gte": "2026-05-13",
                    "$lte": "2026-05-19",
                },
            }
        )
```

- [ ] **Step 4: Run DAO tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/dao/test_reminder_dao.py::TestReminderDAO::test_create_indexes_creates_required_indexes \
  tests/unit/dao/test_reminder_dao.py::TestReminderDAO::test_list_for_owner_filters_by_owner_and_lifecycle_states \
  tests/unit/dao/test_reminder_dao.py::TestReminderDAO::test_list_for_owner_all_states_when_lifecycle_states_omitted \
  tests/unit/dao/test_reminder_dao.py::TestReminderDAO::test_list_for_owner_in_local_date_range_filters_owner_state_and_dates \
  -v
```

Expected: FAIL because DAO selectors and indexes are not yet explicit about `visibility`.

- [ ] **Step 5: Implement model fields**

In `agent/reminder/models.py`, update `Reminder`:

```python
    created_by_system: Literal["agent"]
    origin: Literal["user", "agent", "web"]
    visibility: Literal["visible", "internal"]
    fire_mode: Literal["notify", "followup"]
    prompt: str | None
    metadata: dict | None
    lifecycle_state: Literal["active", "completed", "cancelled", "failed"]
```

Update `ReminderFiredEvent`:

```python
    agent_output_target: AgentOutputTarget
    fire_mode: Literal["notify", "followup"]
    prompt: str | None
    metadata: dict | None
```

- [ ] **Step 6: Implement visible defaults in service create and strict mapping**

In `agent/reminder/service.py`, add to the created document in `create()`:

```python
            "origin": "user",
            "visibility": "visible",
            "fire_mode": "notify",
            "prompt": None,
            "metadata": {},
```

In `_map_document()`, pass required fields without `.get()` defaults:

```python
            created_by_system=document["created_by_system"],
            origin=document["origin"],
            visibility=document["visibility"],
            fire_mode=document["fire_mode"],
            prompt=document["prompt"],
            metadata=document["metadata"],
            lifecycle_state=document["lifecycle_state"],
```

This intentionally raises if a reminder row lacks the new fields; do not add schema-on-read defaults.

- [ ] **Step 7: Implement visible-only DAO filters and internal index**

In `dao/reminder_dao.py`, add the internal index to `create_indexes()`:

```python
        self.collection.create_index(
            [
                ("owner_user_id", 1),
                ("agent_output_target.conversation_id", 1),
            ],
            unique=True,
            partialFilterExpression={
                "visibility": "internal",
                "fire_mode": "followup",
                "lifecycle_state": "active",
            },
        )
```

Update `list_for_owner()` selector:

```python
        selector: Dict = {"owner_user_id": owner_user_id, "visibility": "visible"}
```

Update `list_for_owner_in_local_date_range()` selector:

```python
        selector: Dict = {
            "owner_user_id": owner_user_id,
            "visibility": "visible",
            "lifecycle_state": {"$in": lifecycle_states},
            "schedule.local_date": {
                "$gte": from_date.isoformat(),
                "$lte": to_date.isoformat(),
            },
        }
```

- [ ] **Step 8: Update in-memory DAO test double**

In `tests/unit/reminder/test_service.py`, update `InMemoryReminderDAO.list_for_owner()`:

```python
        results = [
            dict(document)
            for document in self.documents.values()
            if document["owner_user_id"] == owner_user_id
            and document.get("visibility") == "visible"
        ]
```

Update `list_for_owner_in_local_date_range()`:

```python
            if document.get("visibility") != "visible":
                continue
```

- [ ] **Step 9: Run Task 1 tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_service.py tests/unit/dao/test_reminder_dao.py -v
```

Expected: PASS.

- [ ] **Step 10: Commit Task 1**

```bash
git add agent/reminder/models.py agent/reminder/service.py dao/reminder_dao.py tests/unit/reminder/test_service.py tests/unit/dao/test_reminder_dao.py
git commit -m "feat(reminders): classify visible and internal reminders"
```

## Task 2: Add Internal Follow-up DAO And Service Helpers

**Files:**
- Modify: `dao/reminder_dao.py`
- Modify: `agent/reminder/service.py`
- Test: `tests/unit/dao/test_reminder_dao.py`
- Test: `tests/unit/reminder/test_service.py`

- [ ] **Step 1: Add DAO tests for active internal follow-up lookup**

Append to `tests/unit/dao/test_reminder_dao.py`:

```python
    @pytest.mark.unit
    def test_find_active_internal_followup_filters_owner_conversation_and_internal_shape(
        self, reminder_dao, mock_collection
    ):
        expected = [{"_id": ObjectId(), "title": "ask progress"}]
        mock_collection.find_one.return_value = expected[0]

        result = reminder_dao.find_active_internal_followup(
            owner_user_id="user_1",
            conversation_id="conv_1",
        )

        assert result == expected[0]
        mock_collection.find_one.assert_called_once_with(
            {
                "owner_user_id": "user_1",
                "agent_output_target.conversation_id": "conv_1",
                "visibility": "internal",
                "fire_mode": "followup",
                "lifecycle_state": "active",
            }
        )
```

- [ ] **Step 2: Add failing service tests for create, replace, clear, and RRULE rejection**

Append to `tests/unit/reminder/test_service.py`:

```python
def test_create_internal_followup_writes_internal_reminder_and_registers_scheduler():
    service, dao, scheduler = make_service()

    reminder = service.create_or_replace_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
        character_id="char-1",
        route_key="wechat_personal:primary",
        title="check progress",
        prompt="ask whether the user started",
        schedule=schedule(),
        metadata={"proactive_times": 0},
    )

    assert reminder.origin == "agent"
    assert reminder.visibility == "internal"
    assert reminder.fire_mode == "followup"
    assert reminder.prompt == "ask whether the user started"
    assert reminder.metadata == {"proactive_times": 0}
    assert dao.documents[reminder.id]["agent_output_target"]["conversation_id"] == "conv-1"
    scheduler.register_reminder.assert_called_once_with(reminder)


def test_create_internal_followup_replaces_existing_owner_conversation_followup():
    service, dao, scheduler = make_service()
    first = service.create_or_replace_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
        character_id="char-1",
        route_key=None,
        title="first",
        prompt="first prompt",
        schedule=schedule(),
        metadata={"proactive_times": 0},
    )
    later = ReminderSchedule(
        anchor_at=datetime(2026, 4, 30, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 30),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule=None,
    )

    second = service.create_or_replace_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
        character_id="char-1",
        route_key=None,
        title="second",
        prompt="second prompt",
        schedule=later,
        metadata={"proactive_times": 1},
    )

    assert second.id == first.id
    assert second.title == "second"
    assert second.prompt == "second prompt"
    assert second.metadata == {"proactive_times": 1}
    scheduler.reschedule_reminder.assert_called_once_with(second)


def test_clear_internal_followup_requires_owner_and_cancels_scheduler_job():
    service, dao, scheduler = make_service()
    reminder = service.create_or_replace_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
        character_id="char-1",
        route_key=None,
        title="check",
        prompt="ask",
        schedule=schedule(),
    )

    cleared = service.clear_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
    )

    assert cleared.id == reminder.id
    assert cleared.lifecycle_state == "cancelled"
    scheduler.remove_reminder.assert_called_once_with(reminder.id)


def test_internal_followup_rejects_rrule():
    service, _, _ = make_service()

    with pytest.raises(InvalidArgument):
        service.create_or_replace_internal_followup(
            owner_user_id="user-1",
            conversation_id="conv-1",
            character_id="char-1",
            route_key=None,
            title="check",
            prompt="ask",
            schedule=schedule(rrule="FREQ=DAILY"),
        )
```

- [ ] **Step 3: Run new tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/dao/test_reminder_dao.py::TestReminderDAO::test_find_active_internal_followup_filters_owner_conversation_and_internal_shape \
  tests/unit/reminder/test_service.py::test_create_internal_followup_writes_internal_reminder_and_registers_scheduler \
  tests/unit/reminder/test_service.py::test_create_internal_followup_replaces_existing_owner_conversation_followup \
  tests/unit/reminder/test_service.py::test_clear_internal_followup_requires_owner_and_cancels_scheduler_job \
  tests/unit/reminder/test_service.py::test_internal_followup_rejects_rrule \
  -v
```

Expected: FAIL because DAO and service helpers do not exist.

- [ ] **Step 4: Implement DAO helpers**

In `dao/reminder_dao.py`, add:

```python
    def find_active_internal_followup(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
    ) -> Optional[Dict]:
        return self.collection.find_one(
            {
                "owner_user_id": owner_user_id,
                "agent_output_target.conversation_id": conversation_id,
                "visibility": "internal",
                "fire_mode": "followup",
                "lifecycle_state": "active",
            }
        )
```

- [ ] **Step 5: Update in-memory DAO with internal lookup**

In `tests/unit/reminder/test_service.py`, add to `InMemoryReminderDAO`:

```python
    def find_active_internal_followup(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
    ) -> dict | None:
        for document in self.documents.values():
            if (
                document["owner_user_id"] == owner_user_id
                and document.get("visibility") == "internal"
                and document.get("fire_mode") == "followup"
                and document.get("lifecycle_state") == "active"
                and document.get("agent_output_target", {}).get("conversation_id") == conversation_id
            ):
                return dict(document)
        return None
```

- [ ] **Step 6: Implement service helpers**

In `agent/reminder/service.py`, add public methods before `execute_batch()`:

```python
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
        self._validate_title(title)
        self._validate_prompt(prompt)
        self._validate_output_target(
            AgentOutputTarget(
                conversation_id=conversation_id,
                character_id=character_id,
                route_key=route_key,
            )
        )
        if schedule.rrule is not None:
            raise InvalidArgument(
                "Internal follow-up reminders do not support RRULE",
                detail={"field": "schedule.rrule"},
            )
        now = self._now()
        next_fire_at = compute_initial_next_fire_at(schedule, now)
        existing = self.reminder_dao.find_active_internal_followup(
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
        )
        updates = {
            "title": title,
            "schedule": self._schedule_to_document(schedule),
            "agent_output_target": self._target_to_document(
                AgentOutputTarget(conversation_id, character_id, route_key)
            ),
            "origin": "agent",
            "visibility": "internal",
            "fire_mode": "followup",
            "prompt": prompt,
            "metadata": metadata or {},
            "next_fire_at": next_fire_at,
            "updated_at": now,
        }
        if existing:
            reminder_id = str(existing["_id"])
            if not self.reminder_dao.replace_reminder(
                reminder_id,
                owner_user_id,
                updates,
                lifecycle_state="active",
            ):
                raise InvalidArgument(
                    "Active internal follow-up mutation was rejected",
                    detail={"conversation_id": conversation_id},
                )
            updated = self.get(reminder_id=reminder_id, owner_user_id=owner_user_id)
            if updated.next_fire_at is not None:
                self._call_scheduler("reschedule_reminder", updated)
            return updated

        document = {
            "owner_user_id": owner_user_id,
            "created_by_system": "agent",
            "lifecycle_state": "active",
            "last_fired_at": None,
            "last_event_ack_at": None,
            "last_error": None,
            "created_at": now,
            "completed_at": None,
            "cancelled_at": None,
            "failed_at": None,
            **updates,
        }
        reminder_id = self.reminder_dao.insert_reminder(document)
        document["_id"] = reminder_id
        reminder = self._map_document(document)
        if reminder.next_fire_at is not None:
            self._call_scheduler("register_reminder", reminder)
        return reminder

    def clear_internal_followup(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
    ) -> Reminder | None:
        existing = self.reminder_dao.find_active_internal_followup(
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
        )
        if existing is None:
            return None
        now = self._now()
        reminder_id = str(existing["_id"])
        if not self.reminder_dao.replace_reminder(
            reminder_id,
            owner_user_id,
            {
                "lifecycle_state": "cancelled",
                "cancelled_at": now,
                "next_fire_at": None,
                "updated_at": now,
            },
            lifecycle_state="active",
        ):
            raise InvalidArgument(
                "Active internal follow-up mutation was rejected",
                detail={"conversation_id": conversation_id, "action": "clear"},
            )
        self._call_scheduler("remove_reminder", reminder_id)
        return self.get(reminder_id=reminder_id, owner_user_id=owner_user_id)
```

Add helper:

```python
    def _validate_prompt(self, prompt: str) -> None:
        if not prompt or not prompt.strip():
            raise InvalidArgument(
                "Internal follow-up prompt must be non-empty",
                detail={"field": "prompt"},
            )
```

- [ ] **Step 7: Run Task 2 tests and full reminder service/DAO tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_service.py tests/unit/dao/test_reminder_dao.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add agent/reminder/service.py dao/reminder_dao.py tests/unit/reminder/test_service.py tests/unit/dao/test_reminder_dao.py
git commit -m "feat(reminders): add internal followup service path"
```

## Task 3: Switch PostAnalyzeWorkflow To ReminderService

**Files:**
- Modify: `agent/agno_agent/workflows/post_analyze_workflow.py`
- Modify: `tests/unit/agent/test_post_analyze_deferred_actions.py`

- [ ] **Step 1: Rename or update post-analyze tests to assert ReminderService usage**

In `tests/unit/agent/test_post_analyze_deferred_actions.py`, update tests to monkeypatch `ReminderService` instead of `DeferredActionService`.

For `test_post_analyze_creates_internal_followup`, use:

```python
    service = Mock(
        create_or_replace_internal_followup=Mock(),
        clear_internal_followup=Mock(),
    )
    monkeypatch.setattr(workflow_module, "ReminderService", lambda: service)
```

Then assert:

```python
    kwargs = service.create_or_replace_internal_followup.call_args.kwargs
    assert kwargs["owner_user_id"] == "user-1"
    assert kwargs["conversation_id"] == "conv-1"
    assert kwargs["character_id"] == "char-1"
    assert kwargs["route_key"] is None
    assert kwargs["title"] == "中午记得汇报进度"
    assert kwargs["prompt"] == "中午记得汇报进度"
    assert kwargs["schedule"].timezone == "UTC"
    assert kwargs["metadata"] == {"proactive_times": 0}
```

For clear assertions, replace:

```python
    service.clear_internal_followup.assert_called_once_with("conv-1")
```

with:

```python
    service.clear_internal_followup.assert_called_once_with(
        owner_user_id="user-1",
        conversation_id="conv-1",
    )
```

For proactive replacement, set:

```python
    state["message_source"] = "reminder"
    state["system_message_metadata"] = {"kind": "internal_followup"}
```

and assert `metadata == {"proactive_times": 2}`.

- [ ] **Step 2: Run post-analyze tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_post_analyze_deferred_actions.py -v
```

Expected: FAIL because production code still imports and instantiates `DeferredActionService`.

- [ ] **Step 3: Replace import and service construction**

In `agent/agno_agent/workflows/post_analyze_workflow.py`, replace:

```python
from agent.agno_agent.tools.deferred_action.service import DeferredActionService
```

with:

```python
from agent.reminder.models import ReminderSchedule
from agent.reminder.service import ReminderService
```

In `_handle_followup_plan()`, replace:

```python
        service = DeferredActionService()
```

with:

```python
        service = ReminderService()
        owner_user_id = str(session_state.get("user", {}).get("id", "")).strip()
        character_id = str(session_state.get("character", {}).get("_id", "")).strip()
```

For every clear call, use:

```python
            service.clear_internal_followup(
                owner_user_id=owner_user_id,
                conversation_id=conversation_id,
            )
```

When creating/replacing, build `ReminderSchedule`:

```python
        dtstart = datetime.fromtimestamp(followup_timestamp, tz=resolved_tz)
        reminder_schedule = ReminderSchedule(
            anchor_at=dtstart.astimezone(timezone.utc),
            local_date=dtstart.date(),
            local_time=dtstart.time().replace(tzinfo=None),
            timezone=getattr(resolved_tz, "key", str(resolved_tz)),
            rrule=None,
        )
```

Then call:

```python
        service.create_or_replace_internal_followup(
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            character_id=character_id,
            route_key=None,
            title=followup_prompt[:48],
            prompt=followup_prompt,
            schedule=reminder_schedule,
            metadata={"proactive_times": next_proactive_times},
        )
```

Change proactive count detection to:

```python
            if message_source == "reminder" and deferred_kind == "internal_followup"
```

If the file currently imports `datetime` but not `timezone`, add:

```python
from datetime import timezone
```

- [ ] **Step 4: Run post-analyze tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_post_analyze_deferred_actions.py -v
```

Expected: PASS.

- [ ] **Step 5: Add negative grep check for deferred-action writes from PostAnalyzeWorkflow**

Run:

```bash
rg -n "DeferredActionService|create_or_replace_internal_followup|clear_internal_followup\\(" agent/agno_agent/workflows/post_analyze_workflow.py
```

Expected: no `DeferredActionService`; internal follow-up method names are allowed only on `ReminderService`.

- [ ] **Step 6: Commit Task 3**

```bash
git add agent/agno_agent/workflows/post_analyze_workflow.py tests/unit/agent/test_post_analyze_deferred_actions.py
git commit -m "feat(agent): write followups through reminder service"
```

## Task 4: Fire Internal Follow-ups Through ReminderFireEventHandler

**Files:**
- Modify: `agent/reminder/models.py`
- Modify: `agent/runner/reminder_scheduler.py`
- Modify: `agent/runner/reminder_event_handler.py`
- Modify: `tests/unit/runner/test_reminder_scheduler.py`
- Modify: `tests/unit/runner/test_reminder_event_handler.py`
- Modify: `tests/unit/reminder/test_models.py`
- Modify: `tests/unit/runner/test_typed_runtime_events.py`

- [ ] **Step 1: Update event-building tests with new event fields**

In `tests/unit/runner/test_reminder_event_handler.py`, update `build_event()` to include:

```python
        fire_mode=overrides.pop("fire_mode", "notify"),
        prompt=overrides.pop("prompt", None),
        metadata=overrides.pop("metadata", {}),
```

Do the same in helper functions in `tests/unit/reminder/test_models.py` and `tests/unit/runner/test_typed_runtime_events.py`.

- [ ] **Step 2: Add failing follow-up runtime test**

Append to `tests/unit/runner/test_reminder_event_handler.py`:

```python
@pytest.mark.asyncio
async def test_followup_fire_uses_prompt_and_internal_followup_metadata_in_typed_runtime():
    event = build_event(
        fire_mode="followup",
        prompt="ask whether the user started",
        metadata={"proactive_times": 1},
    )
    runtime_event_handler = Mock(
        return_value=SimpleNamespace(
            visible_messages=[
                SimpleNamespace(
                    content="你开始了吗？",
                    message_type="text",
                    metadata={},
                )
            ]
        )
    )
    output_writer = Mock(return_value={"_id": "out-1"})
    handler = build_handler(output_writer)
    handler.runtime_event_handler = runtime_event_handler

    result = await handler.handle(event)

    assert result.ok is True
    agent_input = runtime_event_handler.call_args.kwargs["agent_input"]
    assert agent_input.input_type == "reminder.fired"
    assert agent_input.text == "ask whether the user started"
    assert agent_input.payload.title == "drink water"
    assert agent_input.payload.metadata["kind"] == "internal_followup"
    assert agent_input.payload.metadata["proactive_times"] == 1
    assert runtime_event_handler.call_args.kwargs["message_source"] == "reminder"
    output_writer.assert_called_once()
    assert output_writer.call_args.args[1] == "你开始了吗？"
```

Add imports:

```python
from types import SimpleNamespace
```

- [ ] **Step 3: Run follow-up event handler test and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/runner/test_reminder_event_handler.py::test_followup_fire_uses_prompt_and_internal_followup_metadata_in_typed_runtime -v
```

Expected: FAIL because `ReminderFireEventHandler` does not branch by `fire_mode` and event constructors do not yet pass those fields everywhere.

- [ ] **Step 4: Update scheduler event construction**

In `agent/runner/reminder_scheduler.py`, when constructing `ReminderFiredEvent`, add:

```python
            fire_mode=reminder.fire_mode,
            prompt=reminder.prompt,
            metadata=reminder.metadata or {},
```

In `_map_reminder()`, pass:

```python
            origin=document["origin"],
            visibility=document["visibility"],
            fire_mode=document["fire_mode"],
            prompt=document["prompt"],
            metadata=document["metadata"],
```

- [ ] **Step 5: Update ReminderFireEventHandler metadata and text**

In `_handle_with_typed_runtime()`, build metadata like:

```python
        event_metadata = {
            "event_type": event.event_type,
            "event_id": event.event_id,
            "fire_id": event.fire_id,
            "reminder_id": event.reminder_id,
            "scheduled_for": event.scheduled_for.isoformat(),
            "fire_at": event.fire_at.isoformat(),
            "fire_mode": event.fire_mode,
        }
        if event.fire_mode == "followup":
            event_metadata["kind"] = "internal_followup"
            event_metadata.update(event.metadata or {})
            input_text = event.prompt or event.title
        else:
            input_text = f"提醒：{event.title}"
```

Then use `input_text` in `AgentInput`:

```python
            text=input_text,
```

and payload metadata:

```python
                metadata=event_metadata,
```

In the non-typed fallback branch, keep visible notify behavior and make follow-up fail explicitly:

```python
            if event.fire_mode == "followup":
                return self._failure(
                    event,
                    "RuntimeRequired",
                    "internal follow-up fire requires typed runtime handler",
                )
```

Place that before `self.output_writer(context, f"提醒：{event.title}", ...)`.

- [ ] **Step 6: Run reminder scheduler and event handler tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py tests/unit/runner/test_typed_runtime_events.py tests/unit/reminder/test_models.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add agent/reminder/models.py agent/runner/reminder_scheduler.py agent/runner/reminder_event_handler.py tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py tests/unit/runner/test_typed_runtime_events.py tests/unit/reminder/test_models.py
git commit -m "feat(reminders): fire internal followups through runtime"
```

## Task 5: Remove Old Proactive Follow-up From Deferred Actions

**Files:**
- Modify: `agent/agno_agent/tools/deferred_action/service.py`
- Modify: `dao/deferred_action_dao.py`
- Modify: `agent/runner/deferred_action_executor.py`
- Modify: `tests/unit/agent/test_deferred_action_service.py`
- Modify: `tests/unit/dao/test_deferred_action_dao.py`
- Modify: `tests/e2e/test_deferred_actions_flow.py`
- Test: `tests/unit/agent/test_post_analyze_deferred_actions.py`
- Test: `tests/e2e/test_reminder_system_flow.py`

- [ ] **Step 1: Inspect local and production active proactive rows**

Run local inspection:

```bash
.venv/bin/python - <<'PY'
from dao.deferred_action_dao import DeferredActionDAO

dao = DeferredActionDAO()
rows = list(dao.collection.find(
    {"kind": "proactive_followup", "lifecycle_state": "active"},
    {"_id": 1, "conversation_id": 1, "user_id": 1, "next_run_at": 1},
))
print({"active_proactive_followup_count": len(rows), "rows": rows[:20]})
dao.close()
PY
```

Expected: Capture the count in the task notes. If count is non-zero, stop before deletion and ask for explicit operator confirmation to cancel/delete those rows. Do not migrate them by default.

If production inspection is available through the normal deployment host, run the same query there in read-only mode and record the count in the commit message body or a follow-up evidence file.

- [ ] **Step 2: Add grep-based guard test**

Create `tests/unit/agent/test_internal_followup_no_deferred_action_path.py`:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_proactive_followup_no_longer_has_deferred_action_runtime_path():
    forbidden_paths = [
        ROOT / "agent" / "agno_agent" / "workflows" / "post_analyze_workflow.py",
        ROOT / "agent" / "agno_agent" / "tools" / "deferred_action" / "service.py",
        ROOT / "agent" / "runner" / "deferred_action_executor.py",
        ROOT / "dao" / "deferred_action_dao.py",
    ]
    offenders = []
    for path in forbidden_paths:
        text = path.read_text()
        if "proactive_followup" in text or "find_active_internal_followup" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
```

- [ ] **Step 3: Run guard test and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_internal_followup_no_deferred_action_path.py -v
```

Expected: FAIL because old proactive follow-up strings still exist in deferred-action files.

- [ ] **Step 4: Remove DeferredActionService internal follow-up methods**

In `agent/agno_agent/tools/deferred_action/service.py`, delete:

- `create_or_replace_internal_followup`
- `clear_internal_followup`
- `_create_internal_followup`
- `_update_internal_followup`

Keep visible `user_reminder` and imported calendar paths intact.

- [ ] **Step 5: Remove DeferredActionDAO proactive lookup and index**

In `dao/deferred_action_dao.py`, remove:

- proactive partial index for `kind=proactive_followup`
- `find_active_internal_followup`

Do not remove indexes or methods used by visible user reminders or calendar import.

- [ ] **Step 6: Remove deferred executor proactive input branch**

In `agent/runner/deferred_action_executor.py`, replace:

```python
        if action.get("kind") == "proactive_followup":
            return f"[系统延迟跟进触发] {prompt}"
        return f"[系统提醒触发] {prompt}"
```

with:

```python
        return f"[系统提醒触发] {prompt}"
```

The internal follow-up trigger now lives in `ReminderFireEventHandler`, not in deferred actions.

- [ ] **Step 7: Delete or rewrite tests that only prove old proactive deferred behavior**

Remove assertions in:

- `tests/unit/agent/test_deferred_action_service.py` that call `create_or_replace_internal_followup` or `clear_internal_followup`
- `tests/unit/dao/test_deferred_action_dao.py` that assert `find_active_internal_followup`
- `tests/e2e/test_deferred_actions_flow.py` section asserting internal proactive follow-up remains on legacy `deferred_actions`

Keep tests for visible deferred reminders, calendar import, scheduler policy, leases, occurrences, and generic deferred-action execution.

- [ ] **Step 8: Run deferred-action and reminder follow-up tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_internal_followup_no_deferred_action_path.py \
  tests/unit/agent/test_deferred_action_service.py \
  tests/unit/dao/test_deferred_action_dao.py \
  tests/unit/runner/test_deferred_action_executor.py \
  tests/e2e/test_deferred_actions_flow.py \
  tests/unit/agent/test_post_analyze_deferred_actions.py \
  tests/e2e/test_reminder_system_flow.py \
  -v
```

Expected: PASS, except tests that require external services should be classified before editing. Do not weaken runtime contracts just to turn this command green.

- [ ] **Step 9: Commit Task 5**

```bash
git add agent/agno_agent/tools/deferred_action/service.py dao/deferred_action_dao.py agent/runner/deferred_action_executor.py tests/unit/agent/test_internal_followup_no_deferred_action_path.py tests/unit/agent/test_deferred_action_service.py tests/unit/dao/test_deferred_action_dao.py tests/e2e/test_deferred_actions_flow.py
git commit -m "refactor(deferred-actions): remove proactive followup path"
```

## Task 6: Update Docs, Bridge/Gateway Boundaries, And Verification Evidence

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/product-specs/FEATURE_TREE.md`
- Modify: `connector/clawscale_bridge/reminder_management_service.py` if serialization or visible filters need alignment.
- Modify: gateway tests only if exposed reminder JSON changes.
- Create: `artifacts/evidence/2026-05-14-internal-followup-reminder-unification.md`

- [ ] **Step 1: Update architecture docs**

In `docs/ARCHITECTURE.md`, replace the bullet that says `deferred_actions` stores internal proactive follow-up state with:

```markdown
- `reminders` stores both visible user reminders and internal agent follow-ups.
  Internal follow-ups use `visibility=internal` and `fire_mode=followup`, are
  hidden from customer management surfaces, and fire through
  `ReminderFireEventHandler` into the normal Agent System runtime.
```

Keep `deferred_actions` documented only for remaining non-proactive consumers such as imported calendar reminders or historical deferred-action flows.

- [ ] **Step 2: Update feature tree**

In `docs/product-specs/FEATURE_TREE.md`, update the Reminder System section to include:

```markdown
  - internal agent follow-up state in MongoDB `reminders` with
    `visibility=internal` and `fire_mode=followup`
```

Remove any statement that proactive follow-up is currently stored in `deferred_actions`.

- [ ] **Step 3: Confirm customer reminder management remains visible-only**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_reminder_management_service.py \
  tests/unit/connector/clawscale_bridge/test_bridge_app.py \
  -k "reminder or reminders" -v
```

Expected: PASS. If a test starts exposing internal reminders, fix the Python service/DAO visibility filter rather than changing the test to accept internal reminders.

- [ ] **Step 4: Run gateway customer reminder tests**

Run:

```bash
cd gateway/packages/api && npm test -- src/lib/reminder-runtime-client.test.ts src/routes/customer-reminder-routes.test.ts
```

Expected: PASS.

Run:

```bash
cd gateway/packages/web && npm test -- lib/customer-reminders.test.ts app/'(customer)'/account/reminders/page.test.tsx app/'(customer)'/account/layout.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Write evidence file**

Create `artifacts/evidence/2026-05-14-internal-followup-reminder-unification.md` with this structure, replacing the example command blocks with the exact commands run and their observed results:

~~~markdown
# Internal Follow-up Reminder Unification Evidence

- Date: 2026-05-14
- Scope: internal proactive follow-up moved from `deferred_actions` to internal reminders.
- Commit range: replace with the actual base and head commit SHAs used for verification

## Data Inspection

- Local active `deferred_actions.kind=proactive_followup` count: replace with the measured integer from Step 1
- Production active `deferred_actions.kind=proactive_followup` count: replace with the measured integer, or write `not run` plus the exact access limitation
- Operator action: write `none`, `cancelled rows`, or `deleted rows`, followed by the row ids when rows were changed

## Verification

```bash
replace with the exact command that was run
```

Result: replace with the observed pass/fail summary and failure classification when relevant.

## Limits

- Write any commands not run and the concrete reason.
~~~
```

- [ ] **Step 6: Commit docs and evidence**

```bash
git add docs/ARCHITECTURE.md docs/product-specs/FEATURE_TREE.md artifacts/evidence/2026-05-14-internal-followup-reminder-unification.md
git commit -m "docs(reminders): update internal followup ownership"
```

## Final Verification

- [ ] **Step 1: Run diff-aware routing**

```bash
zsh scripts/suggest-verification --base HEAD~6
```

Expected: suggested surfaces include worker-runtime, reminder-system, customer reminder management, deferred-action regression, and repo docs when those files changed.

- [ ] **Step 2: Run focused reminder system tests**

```bash
.venv/bin/python -m pytest tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py -v
.venv/bin/python -m pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py -v
.venv/bin/python -m pytest tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/test_tool_results_context.py -v
.venv/bin/python -m pytest tests/e2e/test_reminder_system_flow.py -v
```

Expected: PASS.

- [ ] **Step 3: Run focused deferred-action regression tests**

```bash
.venv/bin/python -m pytest tests/unit/runner/test_deferred_action_policy.py tests/unit/runner/test_deferred_action_scheduler.py tests/unit/runner/test_agent_runner_deferred_actions.py tests/unit/runner/test_deferred_action_executor.py tests/unit/runner/test_deferred_action_message_source.py tests/unit/runner/test_background_handler_deferred_only.py tests/unit/runner/test_background_conversation_participants.py -v
.venv/bin/python -m pytest tests/unit/agent/test_deferred_action_service.py tests/unit/test_context_retrieve_deferred_reminders.py tests/unit/agent/test_agent_handler.py tests/unit/test_clawscale_only_topology.py -v
.venv/bin/python -m pytest tests/e2e/test_deferred_actions_flow.py -v
```

Expected: PASS for remaining non-proactive deferred-action behavior.

- [ ] **Step 4: Run customer reminder management tests**

```bash
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_reminder_management_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -k "reminder or reminders" -v
cd gateway/packages/api && npm test -- src/lib/reminder-runtime-client.test.ts src/routes/customer-reminder-routes.test.ts
cd gateway/packages/web && npm test -- lib/customer-reminders.test.ts app/'(customer)'/account/reminders/page.test.tsx app/'(customer)'/account/layout.test.tsx
cd gateway/packages/api && npm run build
cd gateway/packages/web && npm run lint -- app/'(customer)'/account/reminders/page.tsx lib/customer-reminders.ts components/customer-shell.tsx app/'(customer)'/account/layout.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Run repo checks and review routing**

```bash
zsh scripts/check
zsh scripts/review-trigger --base HEAD~6
git status --short --branch
git -C gateway status --short --branch
```

Expected: `scripts/check` passes. `review-trigger` may require human review because this changes runtime boundaries and docs; report that as a gate, not a test failure. Both worktrees should be clean before handoff.

## Self-Review Notes

- Spec coverage: data model fields, no legacy compatibility, visible-only user queries, internal follow-up service helpers, owner-scoped clear, RRULE rejection, post-analyze write path, fire handling, old deferred-action deletion, docs, and verification are mapped to tasks.
- No intentional compatibility fallback is included. Missing-field legacy reminder rows are excluded by query selectors and strict mapping.
- The plan intentionally does not migrate old proactive rows by default. It requires data inspection and explicit cancellation/deletion if rows exist.
- Review risk: `ReminderFireEventHandler` follow-up behavior depends on typed runtime availability. The plan makes non-typed follow-up fire fail explicitly rather than silently emitting technical text.
