# Timezone User Setting Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to set their timezone via natural language, persisted to MongoDB, used everywhere time is formatted.

**Architecture:** Add `timezone` field to `users` collection written at registration; `context.py` reads it directly (with lazy backfill for legacy users); `set_user_timezone_tool` handles LLM-driven updates; reminder parser/validator accept `user_tz` parameter replacing hardcoded Asia/Shanghai.

**Tech Stack:** Python 3.12, ZoneInfo (stdlib), pymongo, Agno tool decorator

---

### Task 1: Add `update_timezone` to UserDAO

**Files:**
- Modify: `dao/user_dao.py`
- Test: `tests/unit/test_user_dao_timezone.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_user_dao_timezone.py
import pytest
from unittest.mock import MagicMock, patch
from dao.user_dao import UserDAO


def make_dao():
    with patch("dao.user_dao.MongoClient"):
        dao = UserDAO.__new__(UserDAO)
        dao.collection = MagicMock()
        return dao


def test_update_timezone_returns_true_on_success():
    dao = make_dao()
    dao.collection.update_one.return_value = MagicMock(modified_count=1)
    result = dao.update_timezone("507f1f77bcf86cd799439011", "America/New_York")
    assert result is True
    dao.collection.update_one.assert_called_once()
    call_args = dao.collection.update_one.call_args
    assert call_args[0][1] == {"$set": {"timezone": "America/New_York"}}


def test_update_timezone_returns_false_on_invalid_id():
    dao = make_dao()
    result = dao.update_timezone("bad_id", "America/New_York")
    assert result is False
    dao.collection.update_one.assert_not_called()


def test_update_timezone_returns_false_when_not_modified():
    dao = make_dao()
    dao.collection.update_one.return_value = MagicMock(modified_count=0)
    result = dao.update_timezone("507f1f77bcf86cd799439011", "Asia/Tokyo")
    assert result is False
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_user_dao_timezone.py -v
```
Expected: `FAILED` — `update_timezone` does not exist yet.

**Step 3: Implement `update_timezone` in UserDAO**

Add after `update_access` method in `dao/user_dao.py`:

```python
def update_timezone(self, user_id: str, timezone: str) -> bool:
    """
    Update user's timezone.

    Args:
        user_id: User ID
        timezone: IANA timezone string (e.g. "America/New_York")

    Returns:
        bool: True if updated successfully
    """
    try:
        object_id = ObjectId(user_id)
    except (TypeError, ValueError):
        return False

    result = self.collection.update_one(
        {"_id": object_id}, {"$set": {"timezone": timezone}}
    )
    return result.modified_count > 0
```

**Step 4: Run tests to verify pass**

```bash
pytest tests/unit/test_user_dao_timezone.py -v
```
Expected: 3 PASSED.

**Step 5: Commit**

```bash
git add dao/user_dao.py tests/unit/test_user_dao_timezone.py
git commit -m "feat(timezone): add update_timezone method to UserDAO"
```

---

### Task 2: Write timezone into users collection at registration

**Files:**
- Modify: `agent/runner/context.py` (the `context_prepare` function)
- Test: `tests/unit/test_context_timezone.py`

**Background:** Users are not created via a single `create_user` call — they are created on-the-fly by the platform connectors. The `context_prepare` function is the right place to do lazy backfill for legacy users AND to ensure new users always have a timezone.

The existing code already calls `get_user_timezone(user_platform_id)` at line 153. We need to:
1. Check if `user.get("timezone")` exists — if yes, use it
2. If not, infer it and backfill it to DB

**Step 1: Write the failing tests**

```python
# tests/unit/test_context_timezone.py
import pytest
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo


def make_minimal_user(timezone=None, platform_id="8615012345678"):
    user = {
        "_id": "507f1f77bcf86cd799439011",
        "platforms": {"wechat": {"id": platform_id, "nickname": "Test"}},
    }
    if timezone is not None:
        user["timezone"] = timezone
    return user


@patch("agent.runner.context.UserDAO")
@patch("agent.runner.context.MongoDBBase")
def test_context_prepare_uses_stored_timezone(mock_mongo, mock_dao):
    """User with stored timezone uses it, does not call update_timezone."""
    from agent.runner.context import context_prepare

    user = make_minimal_user(timezone="America/New_York")
    # minimal stubs
    mock_mongo.return_value.find_one.return_value = {"relationship": {}, "uid": "x", "cid": "y"}
    dao_instance = MagicMock()
    mock_dao.return_value = dao_instance

    with patch("agent.runner.context.get_character_prompt", return_value=None):
        with patch("agent.runner.context.ConversationDAO"):
            ctx = context_prepare(
                user=user,
                character={"_id": "c1", "name": "Coke", "platforms": {}, "user_info": {}},
                conversation={
                    "_id": "conv1",
                    "platform": "wechat",
                    "conversation_info": {"chat_history": [], "input_messages": []},
                },
            )

    # time_str should be formatted using America/New_York
    time_str = ctx["conversation"]["conversation_info"]["time_str"]
    assert time_str  # non-empty
    dao_instance.update_timezone.assert_not_called()


@patch("agent.runner.context.UserDAO")
@patch("agent.runner.context.MongoDBBase")
def test_context_prepare_backfills_timezone_for_legacy_user(mock_mongo, mock_dao):
    """User without timezone field gets it inferred and written back to DB."""
    from agent.runner.context import context_prepare

    user = make_minimal_user(timezone=None, platform_id="8615012345678")
    mock_mongo.return_value.find_one.return_value = {"relationship": {}, "uid": "x", "cid": "y"}
    dao_instance = MagicMock()
    dao_instance.update_timezone.return_value = True
    mock_dao.return_value = dao_instance

    with patch("agent.runner.context.get_character_prompt", return_value=None):
        with patch("agent.runner.context.ConversationDAO"):
            context_prepare(
                user=user,
                character={"_id": "c1", "name": "Coke", "platforms": {}, "user_info": {}},
                conversation={
                    "_id": "conv1",
                    "platform": "wechat",
                    "conversation_info": {"chat_history": [], "input_messages": []},
                },
            )

    dao_instance.update_timezone.assert_called_once_with(
        "507f1f77bcf86cd799439011", "Asia/Shanghai"
    )
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_context_timezone.py -v
```
Expected: FAILED — `UserDAO` not imported in context.py, `update_timezone` not called.

**Step 3: Modify `context_prepare` in `agent/runner/context.py`**

Replace lines 148-153:
```python
    # Infer user timezone from their platform ID (WhatsApp JID encodes country code)
    user_platform_id = next(
        (v.get("id", "") for v in user.get("platforms", {}).values() if v.get("id")),
        "",
    )
    user_tz = get_user_timezone(user_platform_id)
```

With:
```python
    # Resolve user timezone: stored setting takes priority, otherwise infer from
    # platform ID and backfill once (lazy migration for legacy users).
    user_platform_id = next(
        (v.get("id", "") for v in user.get("platforms", {}).values() if v.get("id")),
        "",
    )
    stored_tz_str = user.get("timezone")
    if stored_tz_str:
        user_tz = ZoneInfo(stored_tz_str)
    else:
        from dao.user_dao import UserDAO as _UserDAO
        user_tz = get_user_timezone(user_platform_id)
        _UserDAO().update_timezone(str(user["_id"]), user_tz.key)
```

Also add `ZoneInfo` to the import at the top of the file (it's already in `time_util` but needs importing here):
```python
from zoneinfo import ZoneInfo
```

**Step 4: Run tests to verify pass**

```bash
pytest tests/unit/test_context_timezone.py -v
```
Expected: 2 PASSED.

**Step 5: Run full unit suite to confirm no regressions**

```bash
pytest -m "not integration" -q
```
Expected: all pass.

**Step 6: Commit**

```bash
git add agent/runner/context.py tests/unit/test_context_timezone.py
git commit -m "feat(timezone): read user.timezone from DB in context_prepare, backfill legacy users"
```

---

### Task 3: Create `set_user_timezone_tool`

This is the new Agno tool that OrchestratorAgent calls when the user says "我在纽约" etc.

**Files:**
- Create: `agent/agno_agent/tools/timezone_tools.py`
- Test: `tests/unit/test_timezone_tools.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_timezone_tools.py
import pytest
from unittest.mock import MagicMock, patch


def make_session_state(user_id="507f1f77bcf86cd799439011"):
    return {
        "user": {"_id": user_id},
    }


@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_tool_success(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    dao_instance = MagicMock()
    dao_instance.update_timezone.return_value = True
    mock_dao_class.return_value = dao_instance

    session_state = make_session_state()
    result = set_user_timezone(
        timezone="America/New_York",
        session_state=session_state,
    )

    assert result["ok"] is True
    assert "纽约" in result["message"] or "America/New_York" in result["message"]
    dao_instance.update_timezone.assert_called_once_with(
        "507f1f77bcf86cd799439011", "America/New_York"
    )


@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_tool_invalid_iana(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    session_state = make_session_state()
    result = set_user_timezone(
        timezone="Not/AValid",
        session_state=session_state,
    )

    assert result["ok"] is False
    mock_dao_class.return_value.update_timezone.assert_not_called()


@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_tool_missing_user(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    result = set_user_timezone(
        timezone="Asia/Tokyo",
        session_state={},
    )

    assert result["ok"] is False
    mock_dao_class.return_value.update_timezone.assert_not_called()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_timezone_tools.py -v
```
Expected: FAILED — module does not exist.

**Step 3: Create `agent/agno_agent/tools/timezone_tools.py`**

```python
# -*- coding: utf-8 -*-
"""
Timezone tool for Agno Agent.

Allows users to update their timezone via natural language.
The LLM is responsible for resolving city/region names to IANA timezone strings.
"""

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agno.tools import tool

from dao.user_dao import UserDAO

logger = logging.getLogger(__name__)

# Mapping of common IANA timezone keys to Chinese display names (UTC offset).
# Used only for the confirmation message — not for lookup logic.
_TZ_DISPLAY: dict[str, str] = {
    "Asia/Shanghai": "北京/上海时间（UTC+8）",
    "Asia/Tokyo": "东京时间（UTC+9）",
    "Asia/Seoul": "首尔时间（UTC+9）",
    "Asia/Singapore": "新加坡时间（UTC+8）",
    "Asia/Bangkok": "曼谷时间（UTC+7）",
    "Asia/Jakarta": "雅加达时间（UTC+7）",
    "Asia/Kolkata": "印度时间（UTC+5:30）",
    "Asia/Dubai": "迪拜时间（UTC+4）",
    "Europe/London": "伦敦时间（UTC+0/+1）",
    "Europe/Berlin": "柏林时间（UTC+1/+2）",
    "Europe/Moscow": "莫斯科时间（UTC+3）",
    "America/New_York": "纽约时间（UTC-5/-4）",
    "America/Chicago": "芝加哥时间（UTC-6/-5）",
    "America/Los_Angeles": "洛杉矶时间（UTC-8/-7）",
    "America/Sao_Paulo": "圣保罗时间（UTC-3/-2）",
    "Africa/Cairo": "开罗时间（UTC+2/+3）",
    "Africa/Johannesburg": "约翰内斯堡时间（UTC+2）",
    "Pacific/Auckland": "奥克兰时间（UTC+12/+13）",
    "Australia/Sydney": "悉尼时间（UTC+10/+11）",
}


@tool(
    stop_after_tool_call=True,
    description="""更新用户的时区设置。当用户提到自己所在城市/国家/地区，或要求切换时区时调用。

参数:
- timezone: IANA 时区名称，例如 "America/New_York"、"Asia/Tokyo"、"Europe/London"
  根据用户提到的城市/地区推断，不要询问用户，直接给出 IANA 名称。
""",
)
def set_user_timezone(
    timezone: str,
    session_state: dict = None,
) -> dict:
    """
    Persist the user's timezone to the database.

    Args:
        timezone: IANA timezone string inferred by the LLM from user's message.
        session_state: Agno-injected session state containing user._id.

    Returns:
        dict with ok: bool and message: str for the agent to relay to the user.
    """
    if not session_state:
        session_state = {}

    user_id = str(session_state.get("user", {}).get("_id", ""))
    if not user_id:
        logger.warning("set_user_timezone: no user_id in session_state")
        return {"ok": False, "message": "无法获取用户信息，时区设置失败"}

    # Validate IANA timezone
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, KeyError):
        logger.warning(f"set_user_timezone: invalid timezone '{timezone}'")
        return {"ok": False, "message": f"无效的时区名称：{timezone}"}

    dao = UserDAO()
    success = dao.update_timezone(user_id, timezone)

    if not success:
        logger.error(f"set_user_timezone: DB update failed for user {user_id}")
        return {"ok": False, "message": "时区更新失败，请稍后重试"}

    display = _TZ_DISPLAY.get(timezone, timezone)
    message = f"已将您的时区更新为{display}。"

    # Write confirmation into session_state so ChatResponseAgent can use it
    if session_state is not None:
        session_state["tool_execution_context"] = {
            "user_intent": "更新时区",
            "action_executed": "set_user_timezone",
            "intent_fulfilled": True,
            "result_summary": message,
        }

    logger.info(f"set_user_timezone: user {user_id} → {timezone}")
    return {"ok": True, "message": message}
```

**Step 4: Run tests to verify pass**

```bash
pytest tests/unit/test_timezone_tools.py -v
```
Expected: 3 PASSED.

**Step 5: Commit**

```bash
git add agent/agno_agent/tools/timezone_tools.py tests/unit/test_timezone_tools.py
git commit -m "feat(timezone): add set_user_timezone_tool for natural language timezone updates"
```

---

### Task 4: Wire `set_user_timezone_tool` into OrchestratorAgent

**Files:**
- Modify: `agent/agno_agent/agents/` — find the OrchestratorAgent definition
- Modify: OrchestratorAgent instructions prompt

**Step 1: Find the OrchestratorAgent file**

```bash
grep -r "OrchestratorAgent\|orchestrator_agent" agent/agno_agent/agents/ --include="*.py" -l
```

**Step 2: Add the tool import and registration**

In the file that builds the OrchestratorAgent, add:
```python
from agent.agno_agent.tools.timezone_tools import set_user_timezone
```

And add `set_user_timezone` to the tools list of OrchestratorAgent.

**Step 3: Update OrchestratorAgent instructions**

In `agent/prompt/agent_instructions_prompt.py`, find the OrchestratorAgent instructions and add a section:

```
## 时区更新
当用户提到自己所在的城市、国家或地区（如"我在纽约"、"我搬到东京了"、"切换到新加坡时间"），
调用 set_user_timezone 工具，自行推断对应的 IANA 时区名称，无需询问用户。
```

**Step 4: Run the full unit suite**

```bash
pytest -m "not integration" -q
```
Expected: all pass.

**Step 5: Commit**

```bash
git add agent/agno_agent/agents/ agent/prompt/agent_instructions_prompt.py
git commit -m "feat(timezone): wire set_user_timezone_tool into OrchestratorAgent"
```

---

### Task 5: Pass `user_tz` into Reminder parser and validator

The two hardcoded `ZoneInfo("Asia/Shanghai")` in `reminder/parser.py` (line 101) and `reminder/validator.py` (lines 204, 507) need to use the session-level timezone.

**Files:**
- Modify: `agent/agno_agent/tools/reminder/parser.py`
- Modify: `agent/agno_agent/tools/reminder/validator.py`
- Modify: `agent/agno_agent/tools/reminder/service.py`
- Modify: `agent/agno_agent/tools/reminder_tools.py`
- Test: `tests/unit/reminder/test_timezone_propagation.py`

**Step 1: Write failing tests**

```python
# tests/unit/reminder/test_timezone_propagation.py
import pytest
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo
import time


def test_parser_format_with_date_uses_injected_tz():
    """format_with_date should use provided tz, not hardcoded Asia/Shanghai."""
    from agent.agno_agent.tools.reminder.parser import TimeParser

    tz = ZoneInfo("America/New_York")
    parser = TimeParser(base_timestamp=int(time.time()), tz=tz)
    # Use a known timestamp: 2024-01-15 08:00 UTC = 03:00 New York (EST)
    ts = 1705305600  # 2024-01-15 08:00:00 UTC
    result = parser.format_with_date(ts)
    # Should show hour 3 (EST), not 16 (Shanghai)
    assert "3" in result or "03" in result


def test_validator_formats_time_with_injected_tz():
    """Validator duplicate check message should use the injected timezone."""
    from agent.agno_agent.tools.reminder.validator import ReminderValidator

    tz = ZoneInfo("America/New_York")
    dao = MagicMock()
    # Simulate existing reminder
    ts = 1705305600  # 2024-01-15 08:00 UTC
    dao.find_by_title_fuzzy.return_value = [
        {"reminder_id": "r1", "next_trigger_time": ts, "title": "test"}
    ]
    validator = ReminderValidator(dao=dao, user_id="u1", tz=tz)
    result = validator.check_duplicate("test", "test")
    assert result is not None
    # New York time should be 3:00, not 16:00
    assert "16" not in result["message"]


def test_service_passes_tz_to_parser_and_validator():
    """ReminderService should propagate user_tz to parser and validator."""
    from agent.agno_agent.tools.reminder.service import ReminderService

    tz = ZoneInfo("America/New_York")
    service = ReminderService(
        user_id="u1", character_id="c1", conversation_id="cv1",
        base_timestamp=int(time.time()), user_tz=tz, dao=MagicMock()
    )
    assert service.parser.tz == tz
    assert service.validator.tz == tz
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/reminder/test_timezone_propagation.py -v
```
Expected: FAILED — `tz` parameter not accepted yet.

**Step 3: Update `TimeParser` in `parser.py`**

Add `tz` parameter to `__init__`:
```python
def __init__(self, base_timestamp=None, tz: ZoneInfo = None):
    self.base_timestamp = base_timestamp
    self.tz = tz or ZoneInfo("Asia/Shanghai")
```

In `format_with_date` (line 101), replace:
```python
dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("Asia/Shanghai"))
```
With:
```python
dt = datetime.fromtimestamp(timestamp, tz=self.tz)
```

**Step 4: Update `ReminderValidator` in `validator.py`**

Add `tz` parameter to `__init__`:
```python
def __init__(self, dao, user_id: str, tz: ZoneInfo = None):
    self.dao = dao
    self.user_id = user_id
    self.tz = tz or ZoneInfo("Asia/Shanghai")
```

Replace both hardcoded `ZoneInfo("Asia/Shanghai")` usages (lines 204 and 507) with `self.tz`.

**Step 5: Update `ReminderService` in `service.py`**

Add `user_tz` parameter to `__init__`:
```python
def __init__(
    self,
    user_id: str,
    character_id: str,
    conversation_id: str,
    base_timestamp: Optional[int] = None,
    session_state: Optional[dict] = None,
    dao: Optional["ReminderDAO"] = None,
    user_tz=None,
) -> None:
    from dao.reminder_dao import ReminderDAO

    self.dao = dao if dao is not None else ReminderDAO()
    self.parser = TimeParser(base_timestamp=base_timestamp, tz=user_tz)
    self.validator = ReminderValidator(dao=self.dao, user_id=user_id, tz=user_tz)
    self.formatter = ReminderFormatter(time_parser=self.parser)
    ...
```

**Step 6: Update `reminder_tools.py` to extract and pass `user_tz`**

After line 297 (`message_timestamp = current_session_state.get("input_timestamp")`), add:
```python
# Resolve user timezone from session_state
_tz_str = current_session_state.get("user", {}).get("timezone")
from zoneinfo import ZoneInfo as _ZoneInfo
from util.time_util import get_user_timezone as _get_user_timezone
if _tz_str:
    _user_tz = _ZoneInfo(_tz_str)
else:
    _user_tz = _get_user_timezone(
        next(
            (v.get("id", "") for v in current_session_state.get("user", {}).get("platforms", {}).values() if v.get("id")),
            "",
        )
    )
```

And pass `user_tz=_user_tz` to `ReminderService(...)` at line 312.

**Step 7: Run all tests**

```bash
pytest tests/unit/reminder/ -v
pytest -m "not integration" -q
```
Expected: all pass.

**Step 8: Commit**

```bash
git add agent/agno_agent/tools/reminder/parser.py \
        agent/agno_agent/tools/reminder/validator.py \
        agent/agno_agent/tools/reminder/service.py \
        agent/agno_agent/tools/reminder_tools.py \
        tests/unit/reminder/test_timezone_propagation.py
git commit -m "feat(timezone): propagate user_tz through ReminderService, parser, and validator"
```

---

### Task 6: Final verification

**Step 1: Run the full test suite**

```bash
pytest -m "not integration" --tb=short -q
```
Expected: all pass, coverage ≥ 70%.

**Step 2: Run formatter**

```bash
black . && isort .
```

**Step 3: Commit if formatter made changes**

```bash
git add -u
git commit -m "style: black/isort formatting"
```

---

## Summary of changed files

| File | Change |
|------|--------|
| `dao/user_dao.py` | Add `update_timezone()` |
| `agent/runner/context.py` | Read `user.timezone`, lazy backfill via UserDAO |
| `agent/agno_agent/tools/timezone_tools.py` | New tool: `set_user_timezone` |
| `agent/agno_agent/agents/<orchestrator>.py` | Register new tool |
| `agent/prompt/agent_instructions_prompt.py` | Add timezone intent instructions |
| `agent/agno_agent/tools/reminder/parser.py` | Accept `tz` param, use it in `format_with_date` |
| `agent/agno_agent/tools/reminder/validator.py` | Accept `tz` param, replace 2 hardcoded usages |
| `agent/agno_agent/tools/reminder/service.py` | Accept `user_tz`, pass to parser + validator |
| `agent/agno_agent/tools/reminder_tools.py` | Extract user_tz from session_state, pass to service |
