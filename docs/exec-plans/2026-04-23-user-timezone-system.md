# User Timezone System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production slice of Coke's account-level timezone
system so current runtime paths share one canonical timezone state, user-driven
changes behave predictably, and reminder scheduling follows the approved
timezone semantics.

**Architecture:** Keep `timezone` as the backward-compatible effective IANA
timezone string in `coke_settings`, but add sibling account-level state fields
for source, status, pending proposal, and pending task draft. Centralize the
state machine in a dedicated Python service, then wire current worker-runtime
entry points, prompt preparation, and reminder scheduling to that service.
Future web/app timezone producers should call the same service later; this plan
does not build new UI for them.

**Tech Stack:** Python 3.12, Mongo business collections via `dao.user_dao`,
Agno prepare/chat workflows, existing deferred-action reminder runtime, pytest,
mock-based unit tests.

---

### Task 1: Add Canonical Timezone State Persistence And Service

**Files:**
- Create: `agent/timezone_service.py`
- Modify: `dao/user_dao.py`
- Test: `tests/unit/test_user_dao_timezone.py`
- Test: `tests/unit/agent/test_timezone_service.py`

- [ ] **Step 1: Write the failing DAO and service tests**

```python
# tests/unit/test_user_dao_timezone.py
def test_update_timezone_state_upserts_settings_document():
    dao = make_dao()
    dao.settings_collection.update_one.return_value = MagicMock(
        modified_count=0,
        upserted_id="new-settings",
    )

    state = {
        "timezone": "America/New_York",
        "timezone_source": "messaging_identity_region",
        "timezone_status": "system_inferred",
    }

    result = dao.update_timezone_state("acct_123456", state)

    assert result is True
    dao.settings_collection.update_one.assert_called_once_with(
        {"account_id": "acct_123456"},
        {
            "$set": state,
            "$setOnInsert": {"account_id": "acct_123456"},
        },
        upsert=True,
    )


def test_get_timezone_state_returns_only_timezone_fields():
    dao = make_dao()
    dao.settings_collection.find_one.return_value = {
        "account_id": "acct_123456",
        "timezone": "Asia/Tokyo",
        "timezone_source": "user_explicit",
        "timezone_status": "user_confirmed",
        "pending_timezone_change": None,
        "access": {"order_no": "keep-out"},
    }

    result = dao.get_timezone_state("acct_123456")

    assert result == {
        "timezone": "Asia/Tokyo",
        "timezone_source": "user_explicit",
        "timezone_status": "user_confirmed",
        "pending_timezone_change": None,
        "pending_task_draft": None,
    }
```

```python
# tests/unit/agent/test_timezone_service.py
from agent.timezone_service import TimezoneService


def test_build_initial_inferred_state_prefers_higher_priority_source():
    service = TimezoneService()

    result = service.build_initial_state(
        existing_state=None,
        candidates=[
            {"timezone": "Asia/Shanghai", "source": "messaging_identity_region"},
            {"timezone": "Europe/London", "source": "web_region"},
        ],
        fallback_timezone="Asia/Shanghai",
    )

    assert result["timezone"] == "Europe/London"
    assert result["timezone_status"] == "system_inferred"
    assert result["timezone_source"] == "web_region"


def test_apply_user_explicit_change_clears_pending_state():
    service = TimezoneService()
    current = {
        "timezone": "Asia/Shanghai",
        "timezone_source": "messaging_identity_region",
        "timezone_status": "system_inferred",
        "pending_timezone_change": {"timezone": "Europe/London"},
        "pending_task_draft": {"kind": "visible_reminder"},
    }

    result = service.apply_user_explicit_change(current, "Asia/Tokyo")

    assert result["timezone"] == "Asia/Tokyo"
    assert result["timezone_status"] == "user_confirmed"
    assert result["timezone_source"] == "user_explicit"
    assert result["pending_timezone_change"] is None
    assert result["pending_task_draft"] is None
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run:

```bash
pytest tests/unit/test_user_dao_timezone.py tests/unit/agent/test_timezone_service.py -v
```

Expected:

- `AttributeError` for missing `update_timezone_state`, `get_timezone_state`,
  and `TimezoneService`

- [ ] **Step 3: Implement the state fields and service**

```python
# agent/timezone_service.py
from __future__ import annotations

from copy import deepcopy


SOURCE_PRIORITY = {
    "app_device_timezone": 100,
    "web_region": 90,
    "external_account_timezone": 80,
    "messaging_identity_region": 70,
    "deployment_default": 10,
}


class TimezoneService:
    def _base_state(self, timezone: str, source: str, status: str) -> dict:
        return {
            "timezone": timezone,
            "timezone_source": source,
            "timezone_status": status,
            "pending_timezone_change": None,
            "pending_task_draft": None,
        }

    def build_initial_state(
        self,
        *,
        existing_state: dict | None,
        candidates: list[dict],
        fallback_timezone: str,
    ) -> dict:
        if existing_state and existing_state.get("timezone"):
            merged = deepcopy(existing_state)
            merged.setdefault("pending_timezone_change", None)
            merged.setdefault("pending_task_draft", None)
            return merged

        ranked = sorted(
            [c for c in candidates if c.get("timezone") and c.get("source")],
            key=lambda item: SOURCE_PRIORITY.get(item["source"], 0),
            reverse=True,
        )
        if ranked:
            selected = ranked[0]
            return self._base_state(
                selected["timezone"],
                selected["source"],
                "system_inferred",
            )

        return self._base_state(
            fallback_timezone,
            "deployment_default",
            "system_inferred",
        )

    def apply_user_explicit_change(self, current_state: dict | None, timezone: str) -> dict:
        state = self.build_initial_state(
            existing_state=current_state,
            candidates=[],
            fallback_timezone=timezone,
        )
        state.update(
            {
                "timezone": timezone,
                "timezone_source": "user_explicit",
                "timezone_status": "user_confirmed",
                "pending_timezone_change": None,
                "pending_task_draft": None,
            }
        )
        return state
```

```python
# dao/user_dao.py
TIMEZONE_STATE_FIELDS = (
    "timezone",
    "timezone_source",
    "timezone_status",
    "pending_timezone_change",
    "pending_task_draft",
)


def get_timezone_state(self, account_id: str) -> Optional[Dict]:
    normalized_account_id = _normalize_account_id(account_id)
    if normalized_account_id is None:
        return None

    doc = self.settings_collection.find_one({"account_id": normalized_account_id}) or {}
    if not doc.get("timezone"):
        return None

    return {
        "timezone": doc.get("timezone"),
        "timezone_source": doc.get("timezone_source", "legacy_preserved"),
        "timezone_status": doc.get("timezone_status", "user_confirmed"),
        "pending_timezone_change": doc.get("pending_timezone_change"),
        "pending_task_draft": doc.get("pending_task_draft"),
    }


def update_timezone_state(self, account_id: str, state: Dict) -> bool:
    normalized_account_id = _normalize_account_id(account_id)
    if normalized_account_id is None:
        return False

    set_fields = {key: state.get(key) for key in TIMEZONE_STATE_FIELDS}
    result = self.settings_collection.update_one(
        {"account_id": normalized_account_id},
        {"$set": set_fields, "$setOnInsert": {"account_id": normalized_account_id}},
        upsert=True,
    )
    return bool(result.modified_count or result.upserted_id)
```

- [ ] **Step 4: Run the tests to confirm the new state layer passes**

Run:

```bash
pytest tests/unit/test_user_dao_timezone.py tests/unit/agent/test_timezone_service.py -v
```

Expected:

- all targeted tests pass

- [ ] **Step 5: Commit the foundation**

```bash
git add agent/timezone_service.py dao/user_dao.py tests/unit/test_user_dao_timezone.py tests/unit/agent/test_timezone_service.py
git commit -m "feat: add account timezone state service"
```

### Task 2: Wire Initial Resolution Into Identity And Context

**Files:**
- Modify: `agent/runner/identity.py`
- Modify: `agent/runner/context.py`
- Test: `tests/unit/runner/test_identity.py`
- Test: `tests/unit/test_context_timezone.py`

Context rule for this task:
- Surface `timezone` only when canonical or legacy-persisted timezone state
  actually exists.
- When the runtime is only using a fallback for this request, expose
  `effective_timezone`, `timezone_source`, and `timezone_status`, but do not
  fabricate a canonical `timezone` field.

- [ ] **Step 1: Write failing runtime tests for first-touch inference and legacy preservation**

```python
# tests/unit/runner/test_identity.py
def test_resolve_agent_user_context_persists_first_touch_timezone_state_from_phone_like_external_identity():
    from agent.runner.identity import resolve_agent_user_context

    user_dao = MagicMock()
    user_dao.get_user_by_account_id.return_value = {
        "account_id": "ck_user_1",
        "id": "ck_user_1",
        "_id": "ck_user_1",
        "nickname": "User 1",
    }
    user_dao.get_timezone_state.return_value = None
    user_dao.update_timezone_state.return_value = True

    context = resolve_agent_user_context(
        "ck_user_1",
        {
            "platform": "business",
            "metadata": {
                "source": "clawscale",
                "customer": {"id": "ck_user_1"},
                "external_id": "8617807028761",
            },
        },
        user_dao,
    )

    assert context["timezone"] == "Asia/Shanghai"
    assert context["timezone_status"] == "system_inferred"
    user_dao.update_timezone_state.assert_called_once()
```

```python
# tests/unit/test_context_timezone.py
def test_context_prepare_uses_effective_timezone_from_state(mock_mongo, mock_dao):
    from agent.runner.context import context_prepare

    user = {
        "_id": "acct-1",
        "id": "acct-1",
        "display_name": "Test User",
        "timezone": "Europe/London",
        "timezone_status": "system_inferred",
        "timezone_source": "web_region",
    }
    mock_mongo.return_value.find_one.return_value = {"relationship": {}, "uid": "x", "cid": "y"}
    mock_dao.return_value = MagicMock()

    with patch("agent.runner.context.get_character_prompt", return_value=None):
        with patch("agent.runner.context.ConversationDAO"):
            ctx = context_prepare(
                user=user,
                character={"_id": "c1", "name": "Coke", "platforms": {}, "user_info": {}},
                conversation={"_id": "conv1", "platform": "wechat", "conversation_info": {"chat_history": [], "input_messages": []}},
            )

    assert ctx["user"]["timezone"] == "Europe/London"
    assert ctx["user"]["effective_timezone"] == "Europe/London"
    assert ctx["conversation"]["conversation_info"]["time_str"]
```

- [ ] **Step 2: Run the failing runtime tests**

Run:

```bash
pytest tests/unit/runner/test_identity.py tests/unit/test_context_timezone.py -v
```

Expected:

- failing assertions because first-touch inference and state propagation do not
  exist yet

- [ ] **Step 3: Implement first-touch inference and context propagation**

```python
# agent/runner/identity.py
from agent.timezone_service import TimezoneService
from util.time_util import get_default_timezone


def _build_messaging_timezone_candidates(input_message: Mapping) -> list[dict]:
    metadata = input_message.get("metadata") if isinstance(input_message, Mapping) else {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    external = metadata.get("external")
    if not isinstance(external, Mapping):
        external = {}

    wa_id = str(external.get("wa_id", "")).strip()
    if wa_id.startswith("1"):
        return [{"timezone": "America/New_York", "source": "messaging_identity_region"}]
    if wa_id.startswith("81"):
        return [{"timezone": "Asia/Tokyo", "source": "messaging_identity_region"}]
    return []


def _hydrate_timezone_state(account_id: str, input_message, user_dao, user: dict) -> dict:
    service = TimezoneService()
    current_state = user_dao.get_timezone_state(account_id)
    if current_state:
        user.update(current_state)
        return user

    inferred_state = service.build_initial_state(
        existing_state=None,
        candidates=_build_messaging_timezone_candidates(input_message),
        fallback_timezone=get_default_timezone().key,
    )
    user_dao.update_timezone_state(account_id, inferred_state)
    user.update(inferred_state)
    return user
```

```python
# agent/runner/context.py
timezone_context = _resolve_user_timezone_context(context["user"])
user_tz = timezone_context.pop("zoneinfo")
if "timezone" not in timezone_context and "timezone" in context["user"]:
    context["user"].pop("timezone", None)
context["user"].update(timezone_context)
```

- [ ] **Step 4: Run the runtime tests again**

Run:

```bash
pytest tests/unit/runner/test_identity.py tests/unit/test_context_timezone.py -v
```

Expected:

- targeted tests pass

- [ ] **Step 5: Commit the runtime wiring**

```bash
git add agent/runner/identity.py agent/runner/context.py tests/unit/runner/test_identity.py tests/unit/test_context_timezone.py
git commit -m "feat: resolve account timezone state on runtime load"
```

### Task 3: Implement Direct Changes And Pending Confirmation Flow

**Files:**
- Modify: `agent/agno_agent/schemas/orchestrator_schema.py`
- Modify: `agent/prompt/agent_instructions_prompt.py`
- Modify: `agent/agno_agent/workflows/prepare_workflow.py`
- Modify: `agent/agno_agent/tools/timezone_tools.py`
- Test: `tests/unit/test_timezone_tools.py`
- Test: `tests/unit/test_prepare_workflow_timezone.py`

- [ ] **Step 1: Write failing tests for direct change, proposal creation, and confirmation consumption**

```python
# tests/unit/test_prepare_workflow_timezone.py
@pytest.mark.asyncio
async def test_prepare_workflow_applies_direct_timezone_change(monkeypatch):
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    session_state = {
        "user": {
            "id": "ck_user_1",
            "timezone": "Asia/Shanghai",
            "timezone_status": "system_inferred",
            "timezone_source": "messaging_identity_region",
        },
        "conversation": {"_id": "conv-1"},
    }

    monkeypatch.setattr(
        workflow,
        "_run_orchestrator",
        AsyncMock(side_effect=lambda _msg, state: state.update({"orchestrator": {
            "need_timezone_update": True,
            "timezone_value": "Asia/Tokyo",
            "timezone_action": "direct_set",
        }})),
    )
    monkeypatch.setattr(
        "agent.agno_agent.workflows.prepare_workflow.set_user_timezone.entrypoint",
        lambda **kwargs: {"ok": True, "message": "已切换到东京时间"},
    )

    result = await workflow.run("改成东京时间", session_state)

    assert result["session_state"]["timezone_update_message"] == "已切换到东京时间"


@pytest.mark.asyncio
async def test_prepare_workflow_stores_pending_timezone_proposal(monkeypatch):
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    session_state = {
        "user": {
            "id": "ck_user_1",
            "timezone": "Asia/Shanghai",
            "timezone_status": "system_inferred",
            "timezone_source": "messaging_identity_region",
        },
        "conversation": {"_id": "conv-1"},
    }

    monkeypatch.setattr(
        workflow,
        "_run_orchestrator",
        AsyncMock(side_effect=lambda _msg, state: state.update({"orchestrator": {
            "need_timezone_update": True,
            "timezone_value": "Europe/London",
            "timezone_action": "proposal",
        }})),
    )

    result = await workflow.run("我现在在伦敦", session_state)

    pending = result["session_state"]["user"]["pending_timezone_change"]
    assert pending["timezone"] == "Europe/London"
    assert pending["origin_conversation_id"] == "conv-1"
```

```python
# tests/unit/test_timezone_tools.py
@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_consume_pending_timezone_confirmation_rejects_other_conversation(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import consume_timezone_confirmation

    dao_instance = MagicMock()
    dao_instance.get_timezone_state.return_value = {
        "timezone": "Asia/Shanghai",
        "timezone_source": "messaging_identity_region",
        "timezone_status": "system_inferred",
        "pending_timezone_change": {
            "timezone": "Europe/London",
            "origin_conversation_id": "conv-1",
            "expires_at": 1770000000,
        },
        "pending_task_draft": None,
    }
    mock_dao_class.return_value = dao_instance

    result = consume_timezone_confirmation.entrypoint(
        decision="yes",
        session_state={"user": {"id": "acct-1"}, "conversation": {"_id": "conv-2"}},
    )

    assert result["ok"] is False
    dao_instance.update_timezone_state.assert_not_called()
```

- [ ] **Step 2: Run the new workflow tests and confirm failure**

Run:

```bash
pytest tests/unit/test_prepare_workflow_timezone.py tests/unit/test_timezone_tools.py -v
```

Expected:

- schema and workflow failures for missing `timezone_action`
- missing confirmation-consumption helper

- [ ] **Step 3: Implement direct-set vs proposal flow and same-conversation confirmation**

```python
# agent/agno_agent/schemas/orchestrator_schema.py
timezone_action: str = Field(
    default="none",
    description=(
        "时区动作类型。可选值：none / direct_set / proposal。"
        "direct_set 表示用户明确要求修改时区；proposal 表示检测到新的时区信号，需要立即确认。"
    ),
)
```

```python
# agent/agno_agent/tools/timezone_tools.py
@tool(stop_after_tool_call=True)
def consume_timezone_confirmation(decision: str, session_state: dict = None) -> dict:
    user_id = str((session_state or {}).get("user", {}).get("id", ""))
    conversation_id = str((session_state or {}).get("conversation", {}).get("_id", ""))
    dao = UserDAO()
    state = dao.get_timezone_state(user_id) or {}
    pending = state.get("pending_timezone_change") or {}
    if pending.get("origin_conversation_id") != conversation_id:
        return {"ok": False, "message": "当前没有可确认的时区变更"}

    if decision == "yes":
        state.update(
            {
                "timezone": pending["timezone"],
                "timezone_source": "user_confirmation",
                "timezone_status": "user_confirmed",
                "pending_timezone_change": None,
            }
        )
    else:
        state["pending_timezone_change"] = None

    dao.update_timezone_state(user_id, state)
    return {"ok": True, "message": "时区状态已更新", "state": state}
```

```python
# agent/agno_agent/workflows/prepare_workflow.py
timezone_action = orchestrator.get("timezone_action", "none")
if timezone_action == "direct_set" and timezone_value:
    self._run_timezone_update(session_state, timezone_value)
elif timezone_action == "proposal" and timezone_value:
    self._store_pending_timezone_change(session_state, timezone_value)
```

- [ ] **Step 4: Re-run the timezone workflow tests**

Run:

```bash
pytest tests/unit/test_prepare_workflow_timezone.py tests/unit/test_timezone_tools.py -v
```

Expected:

- targeted tests pass

- [ ] **Step 5: Commit the timezone state machine**

```bash
git add agent/agno_agent/schemas/orchestrator_schema.py agent/prompt/agent_instructions_prompt.py agent/agno_agent/workflows/prepare_workflow.py agent/agno_agent/tools/timezone_tools.py tests/unit/test_prepare_workflow_timezone.py tests/unit/test_timezone_tools.py
git commit -m "feat: add timezone confirmation state machine"
```

### Task 4: Integrate Prompt Visibility And Reminder Time Semantics

**Files:**
- Modify: `agent/prompt/chat_contextprompt.py`
- Modify: `agent/agno_agent/workflows/chat_workflow_streaming.py`
- Modify: `agent/agno_agent/tools/deferred_action/time_parser.py`
- Modify: `agent/agno_agent/tools/deferred_action/tool.py`
- Modify: `agent/agno_agent/tools/deferred_action/service.py`
- Test: `tests/unit/test_tool_results_context.py`
- Test: `tests/unit/agent/test_deferred_action_service.py`
- Test: `tests/unit/agent/test_visible_reminder_time_parser.py`

- [ ] **Step 1: Write failing tests for inferred-timezone disclosure and reminder semantics**

```python
# tests/unit/test_tool_results_context.py
def test_timezone_context_mentions_inferred_state_when_user_asks():
    from agent.prompt.chat_contextprompt import get_tool_results_context

    state = {
        "user": {
            "timezone": "Europe/London",
            "timezone_status": "system_inferred",
            "timezone_source": "web_region",
        },
        "tool_results": [],
    }

    output = get_tool_results_context(state)

    assert "Europe/London" in output or output == ""
```

```python
# tests/unit/agent/test_visible_reminder_time_parser.py
def test_parse_visible_reminder_time_marks_absolute_delay():
    from agent.agno_agent.tools.deferred_action.time_parser import parse_visible_reminder_time

    parsed = parse_visible_reminder_time(
        "3小时后",
        timezone="Asia/Tokyo",
        base_timestamp=1770000000,
    )

    assert parsed["schedule_kind"] == "absolute_delay"
    assert parsed["dtstart"].tzinfo is not None


def test_parse_visible_reminder_time_marks_floating_local_for_named_time():
    from agent.agno_agent.tools.deferred_action.time_parser import parse_visible_reminder_time

    parsed = parse_visible_reminder_time(
        "明天早上9点",
        timezone="Asia/Tokyo",
        base_timestamp=1770000000,
    )

    assert parsed["schedule_kind"] == "floating_local"
```

- [ ] **Step 2: Run the reminder/context tests and confirm failure**

Run:

```bash
pytest tests/unit/test_tool_results_context.py tests/unit/agent/test_deferred_action_service.py tests/unit/agent/test_visible_reminder_time_parser.py -v
```

Expected:

- parser tests fail because `parse_visible_reminder_time` returns bare
  `datetime`
- reminder service tests fail because schedule kind is not stored

- [ ] **Step 3: Implement prompt visibility and schedule-kind support**

```python
# agent/agno_agent/tools/deferred_action/time_parser.py
def parse_visible_reminder_time(... ) -> dict:
    ...
    relative_timestamp = parse_relative_time(...)
    if relative_timestamp is not None:
        return {
            "dtstart": datetime.fromtimestamp(relative_timestamp, tz=resolved_tz),
            "schedule_kind": "absolute_delay",
            "fixed_timezone": False,
        }

    return {
        "dtstart": parsed_datetime,
        "schedule_kind": "floating_local",
        "fixed_timezone": False,
    }
```

```python
# agent/agno_agent/tools/deferred_action/service.py
def create_visible_reminder(..., schedule_kind: str = "floating_local", fixed_timezone: bool = False):
    action = {
        ...
        "timezone": timezone,
        "schedule_kind": schedule_kind,
        "fixed_timezone": fixed_timezone,
        ...
    }
```

```python
# agent/prompt/chat_contextprompt.py
def get_timezone_state_context(session_state: dict) -> str:
    user = session_state.get("user") or {}
    timezone = user.get("timezone")
    if not timezone:
        return ""
    status = user.get("timezone_status")
    source = user.get("timezone_source")
    if status == "system_inferred":
        return f"### 当前时区\n当前按 {timezone} 理解时间（系统推断，来源：{source}）"
    return f"### 当前时区\n当前按 {timezone} 理解时间"
```

- [ ] **Step 4: Run the updated reminder and prompt tests**

Run:

```bash
pytest tests/unit/test_tool_results_context.py tests/unit/agent/test_deferred_action_service.py tests/unit/agent/test_visible_reminder_time_parser.py -v
```

Expected:

- all targeted tests pass

- [ ] **Step 5: Commit the consumer integration**

```bash
git add agent/prompt/chat_contextprompt.py agent/agno_agent/workflows/chat_workflow_streaming.py agent/agno_agent/tools/deferred_action/time_parser.py agent/agno_agent/tools/deferred_action/tool.py agent/agno_agent/tools/deferred_action/service.py tests/unit/test_tool_results_context.py tests/unit/agent/test_deferred_action_service.py tests/unit/agent/test_visible_reminder_time_parser.py
git commit -m "feat: integrate timezone state with reminders and prompts"
```

### Task 5: Run Full Targeted Verification And Final Review

**Files:**
- Modify: `tasks/2026-04-23-user-timezone-system-implementation.md`

- [ ] **Step 1: Run the focused verification suite**

Run:

```bash
pytest \
  tests/unit/test_user_dao_timezone.py \
  tests/unit/agent/test_timezone_service.py \
  tests/unit/runner/test_identity.py \
  tests/unit/test_context_timezone.py \
  tests/unit/test_prepare_workflow_timezone.py \
  tests/unit/test_timezone_tools.py \
  tests/unit/test_tool_results_context.py \
  tests/unit/agent/test_deferred_action_service.py \
  tests/unit/agent/test_visible_reminder_time_parser.py -v
```

Expected:

- all targeted timezone-system tests pass

- [ ] **Step 2: Run repository structure verification**

Run:

```bash
pytest tests/unit/test_repo_os_structure.py -v
zsh scripts/check
```

Expected:

- repo-OS tests pass
- `check passed`

- [ ] **Step 3: Request final code review on the implementation branch**

Run:

```bash
BASE_SHA=$(git rev-parse HEAD~4)
HEAD_SHA=$(git rev-parse HEAD)
```

Then dispatch a review subagent with:

```text
WHAT_WAS_IMPLEMENTED: Account-level timezone state, direct/proposed timezone updates, runtime integration, and reminder schedule semantics
PLAN_OR_REQUIREMENTS: docs/exec-plans/2026-04-23-user-timezone-system.md
BASE_SHA: $BASE_SHA
HEAD_SHA: $HEAD_SHA
DESCRIPTION: First production slice of the account-level timezone system
```

Expected:

- no blocking review findings remain

- [ ] **Step 4: Mark the implementation task complete and commit the task status**

```markdown
# tasks/2026-04-23-user-timezone-system-implementation.md
- Status: Complete
```

Run:

```bash
git add tasks/2026-04-23-user-timezone-system-implementation.md
git commit -m "chore: mark timezone implementation task complete"
```
