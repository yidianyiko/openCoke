# GTD Task System P0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend reminder system to support GTD-style task collection without requiring time

**Architecture:** Add `list_id` field to reminders collection, make `trigger_time` optional, enable quick capture to "inbox" list

**Tech Stack:** Python 3.12+, MongoDB, PyMongo, Pytest

---

## Background

Current reminder system requires `trigger_time` to create a reminder. This prevents quick capture of tasks without specific time requirements, which is a core GTD principle.

**P0 Changes:**
1. Make `trigger_time` optional (can be `None`)
2. Add `list_id` field (default: `"inbox"`)
3. Update DAO layer to support nullable trigger_time
4. Update tool layer to remove trigger_time requirement
5. Update tests

**Out of Scope (P1):**
- Agent prompt modifications (users can't use this yet)
- Daily inbox digest
- Custom list support beyond "inbox"

---

## Task 1: Add Database Migration Script

**Files:**
- Create: `scripts/migrate_add_list_id_to_reminders.py`

**Step 1: Write the migration script**

Create the migration script that adds `list_id="inbox"` to all existing reminders:

```python
# -*- coding: utf-8 -*-
"""
Migration script: Add list_id field to existing reminders

执行时机：P0 上线前运行一次
执行方式：python scripts/migrate_add_list_id_to_reminders.py
"""

import sys
sys.path.append(".")

from dao.reminder_dao import ReminderDAO
from util.log_util import get_logger

logger = get_logger(__name__)


def migrate_add_list_id():
    """给所有现有 reminders 添加 list_id 字段"""
    dao = ReminderDAO()

    try:
        # 查询没有 list_id 字段的文档数量
        count_query = {"list_id": {"$exists": False}}
        count = dao.collection.count_documents(count_query)

        if count == 0:
            logger.info("No reminders need migration (all have list_id field)")
            return True

        logger.info(f"Found {count} reminders without list_id field")

        # 添加 list_id="inbox" 到所有缺少此字段的文档
        result = dao.collection.update_many(
            count_query,
            {"$set": {"list_id": "inbox"}}
        )

        logger.info(f"Migration complete: {result.modified_count} reminders updated")

        # 验证迁移结果
        remaining = dao.collection.count_documents(count_query)
        if remaining > 0:
            logger.error(f"Migration incomplete: {remaining} reminders still missing list_id")
            return False

        logger.info("Migration verification passed: all reminders now have list_id field")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
    finally:
        dao.close()


if __name__ == "__main__":
    success = migrate_add_list_id()
    sys.exit(0 if success else 1)
```

**Step 2: Run the migration script to verify it works**

Run: `python scripts/migrate_add_list_id_to_reminders.py`

Expected: Script runs successfully and reports migration stats

**Step 3: Commit the migration script**

```bash
git add scripts/migrate_add_list_id_to_reminders.py
git commit -m "feat(migration): add script to migrate reminders with list_id field

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Update DAO Layer - Add list_id Field Support

**Files:**
- Modify: `dao/reminder_dao.py:40-46` (create_indexes method)
- Modify: `dao/reminder_dao.py:48-83` (create_reminder method)

**Step 1: Write test for list_id index**

Create test file `tests/unit/test_reminder_dao_list_id.py`:

```python
# -*- coding: utf-8 -*-
import pytest


@pytest.mark.unit
def test_list_id_defaults_to_inbox():
    """测试 list_id 默认值为 inbox"""
    from dao.reminder_dao import ReminderDAO
    import time

    dao = ReminderDAO()

    # 创建提醒时不指定 list_id
    reminder_data = {
        "user_id": "test_user",
        "title": "test reminder",
        "next_trigger_time": int(time.time()) + 3600,
    }

    # 创建前添加 list_id 默认值
    if "list_id" not in reminder_data:
        reminder_data["list_id"] = "inbox"

    inserted_id = dao.create_reminder(reminder_data)

    # 验证创建成功
    assert inserted_id is not None

    # 获取创建的提醒
    reminder = dao.collection.find_one({"_id": dao.collection.find_one({"user_id": "test_user", "title": "test reminder"})["_id"]})

    # 验证 list_id 为 inbox
    assert reminder["list_id"] == "inbox"

    # 清理
    dao.collection.delete_one({"_id": reminder["_id"]})
    dao.close()


@pytest.mark.unit
def test_create_reminder_with_custom_list_id():
    """测试创建提醒时可以指定自定义 list_id"""
    from dao.reminder_dao import ReminderDAO
    import time

    dao = ReminderDAO()

    reminder_data = {
        "user_id": "test_user",
        "title": "test reminder with custom list",
        "next_trigger_time": int(time.time()) + 3600,
        "list_id": "work"  # 自定义 list_id
    }

    inserted_id = dao.create_reminder(reminder_data)
    assert inserted_id is not None

    reminder = dao.collection.find_one({"user_id": "test_user", "title": "test reminder with custom list"})
    assert reminder["list_id"] == "work"

    # 清理
    dao.collection.delete_one({"_id": reminder["_id"]})
    dao.close()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_reminder_dao_list_id.py -v`

Expected: FAIL - list_id field not handled in create_reminder

**Step 3: Update create_indexes to add list_id index**

In `dao/reminder_dao.py`, modify the `create_indexes` method (around line 40-46):

```python
def create_indexes(self):
    """创建必要的索引"""
    self.collection.create_index([("conversation_id", 1)])
    self.collection.create_index([("status", 1), ("next_trigger_time", 1)])
    self.collection.create_index([("reminder_id", 1)], unique=True)
    self.collection.create_index([("user_id", 1), ("status", 1)])
    # 新增：list_id 复合索引
    self.collection.create_index([("list_id", 1), ("user_id", 1), ("status", 1)])
    logger.info("Reminder indexes created")
```

**Step 4: Update create_reminder to add list_id default**

In `dao/reminder_dao.py`, modify the `create_reminder` method (around line 48-83):

```python
def create_reminder(self, reminder_data: Dict) -> str:
    """
    创建新提醒

    Args:
        reminder_data: 提醒数据字典

    Returns:
        str: 插入的提醒ID

    Raises:
        ValueError: 如果 user_id 为空或缺失
    """
    # BUG-009 fix: Validate that user_id is non-empty
    user_id = reminder_data.get("user_id")
    if not user_id or (isinstance(user_id, str) and not user_id.strip()):
        raise ValueError("user_id is required and cannot be empty")

    # 确保必要字段存在
    if "reminder_id" not in reminder_data:
        reminder_data["reminder_id"] = str(uuid.uuid4())

    if "created_at" not in reminder_data:
        reminder_data["created_at"] = int(time.time())

    if "updated_at" not in reminder_data:
        reminder_data["updated_at"] = int(time.time())

    if "triggered_count" not in reminder_data:
        reminder_data["triggered_count"] = 0

    if "status" not in reminder_data:
        reminder_data["status"] = "active"

    # 新增：list_id 默认值
    if "list_id" not in reminder_data:
        reminder_data["list_id"] = "inbox"

    result = self.collection.insert_one(reminder_data)
    return str(result.inserted_id)
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_reminder_dao_list_id.py -v`

Expected: PASS - both tests pass

**Step 6: Commit DAO changes**

```bash
git add dao/reminder_dao.py tests/unit/test_reminder_dao_list_id.py
git commit -m "feat(dao): add list_id field support with inbox default

- Add list_id index (list_id, user_id, status)
- Set list_id='inbox' as default in create_reminder
- Add unit tests for list_id functionality

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Update DAO Layer - Support Nullable trigger_time

**Files:**
- Modify: `dao/reminder_dao.py:97-120` (find_pending_reminders)
- Modify: `dao/reminder_dao.py:131-150` (find_reminders_by_user)
- Modify: `dao/reminder_dao.py:152-205` (filter_reminders)

**Step 1: Write tests for nullable trigger_time**

Add to `tests/unit/test_reminder_dao_list_id.py`:

```python
@pytest.mark.unit
def test_create_reminder_without_trigger_time():
    """测试创建无触发时间的提醒"""
    from dao.reminder_dao import ReminderDAO

    dao = ReminderDAO()

    reminder_data = {
        "user_id": "test_user",
        "title": "buy milk",
        "next_trigger_time": None,  # 无触发时间
        "list_id": "inbox"
    }

    inserted_id = dao.create_reminder(reminder_data)
    assert inserted_id is not None

    reminder = dao.collection.find_one({"user_id": "test_user", "title": "buy milk"})
    assert reminder["next_trigger_time"] is None
    assert reminder["list_id"] == "inbox"

    # 清理
    dao.collection.delete_one({"_id": reminder["_id"]})
    dao.close()


@pytest.mark.unit
def test_find_reminders_by_user_includes_null_trigger_time():
    """测试查询用户提醒时包含无时间的任务"""
    from dao.reminder_dao import ReminderDAO
    import time

    dao = ReminderDAO()

    # 创建一个有时间的提醒
    reminder_with_time = {
        "user_id": "test_user_2",
        "title": "reminder with time",
        "next_trigger_time": int(time.time()) + 3600,
        "list_id": "inbox",
        "status": "active"
    }
    dao.create_reminder(reminder_with_time)

    # 创建一个无时间的提醒
    reminder_no_time = {
        "user_id": "test_user_2",
        "title": "reminder without time",
        "next_trigger_time": None,
        "list_id": "inbox",
        "status": "active"
    }
    dao.create_reminder(reminder_no_time)

    # 查询用户所有提醒
    reminders = dao.find_reminders_by_user("test_user_2", status="active")

    # 应该返回两个提醒
    assert len(reminders) == 2

    titles = [r["title"] for r in reminders]
    assert "reminder with time" in titles
    assert "reminder without time" in titles

    # 清理
    dao.collection.delete_many({"user_id": "test_user_2"})
    dao.close()
```

**Step 2: Run tests to verify current behavior**

Run: `pytest tests/unit/test_reminder_dao_list_id.py::test_create_reminder_without_trigger_time -v`
Run: `pytest tests/unit/test_reminder_dao_list_id.py::test_find_reminders_by_user_includes_null_trigger_time -v`

Expected: Tests should pass (MongoDB naturally supports null values)

**Step 3: Update find_pending_reminders to skip null trigger_time**

In `dao/reminder_dao.py`, the `find_pending_reminders` method already filters by `next_trigger_time: {"$lte": current_time}`, which will naturally exclude null values. Add a comment to clarify:

```python
def find_pending_reminders(
    self, current_time: int, time_window: int = 60
) -> List[Dict]:
    """
    查找待触发的提醒

    Args:
        current_time: 当前时间戳
        time_window: 保留参数以保持API兼容性（不再使用）

    Returns:
        List[Dict]: 待触发的提醒列表

    Note:
        不再限制时间下界，避免错过的提醒永远无法触发。
        重复触发由 mark_as_triggered 的状态变更（active -> triggered）防止。
        阶段二状态重构：confirmed/pending -> active

        trigger_time=None 的任务（inbox 待安排任务）会被自然过滤，
        因为 None 不满足 $lte 比较条件。
    """
    query = {
        "status": "active",
        "next_trigger_time": {"$lte": current_time},  # None 会被自动排除
    }
    # 添加 limit 防止积压过多时一次性加载太多
    return list(self.collection.find(query).sort("next_trigger_time", 1).limit(100))
```

**Step 4: Update find_reminders_by_user to handle sorting with null**

In `dao/reminder_dao.py`, modify `find_reminders_by_user` to handle null trigger_time in sorting:

```python
def find_reminders_by_user(
    self,
    user_id: str,
    status: Optional[str] = None,
    status_list: Optional[List[str]] = None,
) -> List[Dict]:
    """
    查找用户的所有提醒

    Args:
        user_id: 用户ID
        status: 单个状态过滤（向后兼容）
        status_list: 多个状态过滤，如 ["confirmed", "pending"]

    Note:
        支持 trigger_time=None 的任务，排序时 None 值会排在最后
    """
    query = {"user_id": user_id}
    if status_list:
        query["status"] = {"$in": status_list}
    elif status:
        query["status"] = status

    # MongoDB 排序：null 值会排在最后（升序时）
    return list(self.collection.find(query).sort("next_trigger_time", 1))
```

**Step 5: Run all tests to verify changes**

Run: `pytest tests/unit/test_reminder_dao_list_id.py -v`

Expected: All tests pass

**Step 6: Commit DAO nullable trigger_time support**

```bash
git add dao/reminder_dao.py tests/unit/test_reminder_dao_list_id.py
git commit -m "feat(dao): support nullable trigger_time for inbox tasks

- Add comment in find_pending_reminders explaining null filtering
- Update find_reminders_by_user comment to clarify null sorting
- Add tests for creating and querying tasks without trigger_time

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Update Tool Layer - Remove trigger_time Requirement

**Files:**
- Modify: `agent/agno_agent/tools/reminder_tools.py:771-820` (_check_required_fields)
- Modify: `agent/agno_agent/tools/reminder_tools.py:400-467` (docstring)

**Step 1: Write failing test for creating reminder without trigger_time**

Create `tests/unit/test_reminder_tools_gtd.py`:

```python
# -*- coding: utf-8 -*-
import json
import pytest


@pytest.mark.unit
def test_create_reminder_without_trigger_time_succeeds(sample_context, monkeypatch):
    """测试创建无时间提醒成功（不再返回 needs_info）"""
    from agent.agno_agent.tools import reminder_tools
    import time

    created_reminders = []

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def create_reminder(self, reminder_data):
            created_reminders.append(reminder_data)
            return "fake_object_id"

        def find_similar_reminder(self, *args, **kwargs):
            return None

        def find_reminder_at_same_time(self, *args, **kwargs):
            return None

        def close(self):
            pass

    monkeypatch.setattr(reminder_tools, "ReminderDAO", FakeReminderDAO)

    # 设置 session_state
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message": "帮我记一下要买牛奶", "input_timestamp": int(time.time())}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    # 调用工具，不提供 trigger_time
    result = reminder_tools.reminder_tool.entrypoint(
        action="create",
        title="买牛奶",
        trigger_time=None,  # 无时间
        session_state=sample_context
    )

    # 应该成功创建
    assert result["ok"] is True
    assert result["status"] == "success"
    assert len(created_reminders) == 1
    assert created_reminders[0]["title"] == "买牛奶"
    assert created_reminders[0]["next_trigger_time"] is None
    assert created_reminders[0]["list_id"] == "inbox"


@pytest.mark.unit
def test_create_reminder_with_trigger_time_still_works(sample_context, monkeypatch):
    """测试创建有时间提醒仍然正常工作"""
    from agent.agno_agent.tools import reminder_tools
    import time

    created_reminders = []

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def create_reminder(self, reminder_data):
            created_reminders.append(reminder_data)
            return "fake_object_id"

        def find_similar_reminder(self, *args, **kwargs):
            return None

        def find_reminder_at_same_time(self, *args, **kwargs):
            return None

        def close(self):
            pass

    monkeypatch.setattr(reminder_tools, "ReminderDAO", FakeReminderDAO)

    # 使用固定的 base_timestamp 进行时间解析
    base_timestamp = 1737532800  # 2026-01-22 12:00:00 UTC+8

    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message": "明天提醒我", "input_timestamp": base_timestamp}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    result = reminder_tools.reminder_tool.entrypoint(
        action="create",
        title="买牛奶",
        trigger_time="明天09时00分",
        session_state=sample_context
    )

    assert result["ok"] is True
    assert result["status"] == "success"
    assert len(created_reminders) == 1
    assert created_reminders[0]["next_trigger_time"] is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_reminder_tools_gtd.py::test_create_reminder_without_trigger_time_succeeds -v`

Expected: FAIL - returns needs_info for missing trigger_time

**Step 3: Update _check_required_fields to remove trigger_time requirement**

In `agent/agno_agent/tools/reminder_tools.py`, modify `_check_required_fields` (around line 771-820):

```python
def _check_required_fields(
    title: Optional[str], trigger_time: Optional[str]
) -> Optional[dict]:
    """
    检查必要字段是否完整.

    注意：trigger_time 不再是必需字段（GTD P0 支持无时间任务）

    Returns:
        如果缺少字段返回 needs_info 响应，否则返回 None
    """
    missing_fields = []
    draft_info = {}

    if not title:
        missing_fields.append("title")
    else:
        draft_info["title"] = title

    # 移除 trigger_time 必需检查 - GTD P0: 支持无时间任务
    # if not trigger_time:
    #     missing_fields.append("trigger_time")
    # else:
    if trigger_time:
        draft_info["trigger_time"] = trigger_time

    if not missing_fields:
        return None

    logger.info(
        f"Reminder needs more info: missing={missing_fields}, draft={draft_info}"
    )

    missing_desc = "、".join(
        ["提醒内容" if f == "title" else "提醒时间" for f in missing_fields]
    )
    semantic_message = (
        f"信息不足：用户想设置提醒，但缺少【{missing_desc}】，请询问用户补充"
    )
    _save_reminder_result_to_session(
        semantic_message,
        user_intent="创建提醒",
        action_executed="create",
        intent_fulfilled=False,
        details={"missing_fields": missing_fields, "draft": draft_info},
    )

    return {
        "ok": True,
        "status": "needs_info",
        "missing_fields": missing_fields,
        "draft": draft_info,
        "message": _get_missing_info_prompt(missing_fields),
    }
```

**Step 4: Update docstring to reflect optional trigger_time**

In `agent/agno_agent/tools/reminder_tools.py`, update the docstring (around line 400-467):

Find this line:
```python
- trigger_time: 触发时间（必需），格式"xxxx年xx月xx日xx时xx分"或"30分钟后"
```

Change to:
```python
- trigger_time: 触发时间（可选），格式"xxxx年xx月xx日xx时xx分"或"30分钟后"。为 None 时创建无时间任务（存入 inbox）
```

And add to the docstring after the create parameters section:

```python
### GTD 无时间任务支持（P0）
- 创建提醒时 trigger_time 可以为 None，任务会存入 inbox（list_id="inbox"）
- 无时间任务不会被定时触发，需要用户手动查看或通过每日汇总了解（P1 功能）
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_reminder_tools_gtd.py -v`

Expected: Both tests pass

**Step 6: Run full test suite to ensure no regressions**

Run: `pytest tests/unit/test_reminder_tools*.py -v`

Expected: All existing tests still pass

**Step 7: Commit tool layer changes**

```bash
git add agent/agno_agent/tools/reminder_tools.py tests/unit/test_reminder_tools_gtd.py
git commit -m "feat(tools): support creating reminders without trigger_time

- Remove trigger_time requirement in _check_required_fields
- Update docstring to mark trigger_time as optional
- Add GTD inbox task documentation
- Add tests for creating tasks with and without trigger_time

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Update Query Display to Differentiate Inbox Tasks

**Files:**
- Modify: `agent/agno_agent/tools/reminder_tools.py:600-700` (filter operation handler)

**Step 1: Write test for inbox task display**

Add to `tests/unit/test_reminder_tools_gtd.py`:

```python
@pytest.mark.unit
def test_filter_reminders_shows_inbox_tasks_separately(sample_context, monkeypatch):
    """测试查询提醒时区分有时间和无时间任务"""
    from agent.agno_agent.tools import reminder_tools
    import time

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def filter_reminders(self, user_id, status_list=None, **kwargs):
            current_time = int(time.time())
            return [
                {
                    "reminder_id": "r1",
                    "title": "开会",
                    "next_trigger_time": current_time + 3600,
                    "list_id": "inbox",
                    "status": "active"
                },
                {
                    "reminder_id": "r2",
                    "title": "买牛奶",
                    "next_trigger_time": None,
                    "list_id": "inbox",
                    "status": "active"
                },
                {
                    "reminder_id": "r3",
                    "title": "整理书架",
                    "next_trigger_time": None,
                    "list_id": "inbox",
                    "status": "active"
                }
            ]

        def close(self):
            pass

    monkeypatch.setattr(reminder_tools, "ReminderDAO", FakeReminderDAO)

    reminder_tools.set_reminder_session_state(sample_context)

    result = reminder_tools.reminder_tool.entrypoint(
        action="filter",
        session_state=sample_context
    )

    assert result["ok"] is True
    message = result["message"]

    # 应该包含分组标题
    assert "定时提醒" in message or "已安排" in message
    assert "待安排" in message or "Inbox" in message or "收集篮" in message

    # 应该包含所有任务
    assert "开会" in message
    assert "买牛奶" in message
    assert "整理书架" in message
```

**Step 2: Run test to verify current behavior**

Run: `pytest tests/unit/test_reminder_tools_gtd.py::test_filter_reminders_shows_inbox_tasks_separately -v`

Expected: FAIL - current implementation doesn't differentiate

**Step 3: Find the filter operation handler**

Search for the filter operation in `reminder_tools.py`:

Run: `grep -n "action == \"filter\"" agent/agno_agent/tools/reminder_tools.py`

**Step 4: Update filter handler to group by time status**

Locate the filter operation handler (should be around line 600-700) and modify the response formatting:

```python
# In the filter operation handler, after fetching reminders:

# 分组：有时间 vs 无时间
reminders_with_time = [r for r in reminders if r.get("next_trigger_time") is not None]
reminders_inbox = [r for r in reminders if r.get("next_trigger_time") is None]

# 构建返回消息
message_parts = []

if reminders_with_time:
    message_parts.append("📅 定时提醒：")
    for r in reminders_with_time:
        title = r.get("title", "未命名")
        trigger_time = r.get("next_trigger_time")
        time_str = format_time_friendly(trigger_time) if trigger_time else ""
        message_parts.append(f"  • {title} - {time_str}")

if reminders_inbox:
    message_parts.append("\n📥 待安排（Inbox）：")
    for r in reminders_inbox:
        title = r.get("title", "未命名")
        message_parts.append(f"  • {title}")

if not reminders_with_time and not reminders_inbox:
    final_message = "当前没有符合条件的提醒"
else:
    final_message = "\n".join(message_parts)

return {
    "ok": True,
    "status": "success",
    "reminders": reminders,
    "count": len(reminders),
    "message": final_message,
}
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_reminder_tools_gtd.py::test_filter_reminders_shows_inbox_tasks_separately -v`

Expected: PASS

**Step 6: Commit display changes**

```bash
git add agent/agno_agent/tools/reminder_tools.py tests/unit/test_reminder_tools_gtd.py
git commit -m "feat(tools): differentiate inbox tasks in query display

- Group reminders into 'scheduled' and 'inbox' sections
- Show time for scheduled reminders, omit for inbox tasks
- Add test for display differentiation

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Integration Test for End-to-End Flow

**Files:**
- Create: `tests/unit/test_reminder_gtd_integration.py`

**Step 1: Write integration test**

```python
# -*- coding: utf-8 -*-
"""
GTD 任务系统集成测试

测试完整流程：
1. 创建无时间任务
2. 创建有时间任务
3. 查询所有任务并验证分组显示
4. 清理
"""
import pytest


@pytest.mark.unit
def test_gtd_inbox_workflow(sample_context, monkeypatch):
    """测试 GTD Inbox 工作流程"""
    from agent.agno_agent.tools import reminder_tools
    import time

    # 使用真实 DAO 的内存模拟
    class InMemoryReminderDAO:
        def __init__(self, *args, **kwargs):
            self.reminders = []
            self.id_counter = 1

        def create_reminder(self, reminder_data):
            reminder_data["_id"] = str(self.id_counter)
            self.id_counter += 1
            self.reminders.append(reminder_data)
            return reminder_data["_id"]

        def filter_reminders(self, user_id, status_list=None, **kwargs):
            results = []
            for r in self.reminders:
                if r.get("user_id") != user_id:
                    continue
                if status_list and r.get("status") not in status_list:
                    continue
                results.append(r)
            # 按 trigger_time 排序，None 排最后
            return sorted(results, key=lambda x: (x.get("next_trigger_time") is None, x.get("next_trigger_time") or 0))

        def find_similar_reminder(self, *args, **kwargs):
            return None

        def find_reminder_at_same_time(self, *args, **kwargs):
            return None

        def close(self):
            pass

    monkeypatch.setattr(reminder_tools, "ReminderDAO", InMemoryReminderDAO)

    base_timestamp = int(time.time())
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message": "帮我记一下", "input_timestamp": base_timestamp}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    # Step 1: 创建无时间任务
    result1 = reminder_tools.reminder_tool.entrypoint(
        action="create",
        title="买牛奶",
        trigger_time=None,
        session_state=sample_context
    )
    assert result1["ok"] is True
    assert result1["status"] == "success"

    # Step 2: 创建另一个无时间任务
    result2 = reminder_tools.reminder_tool.entrypoint(
        action="create",
        title="整理书架",
        trigger_time=None,
        session_state=sample_context
    )
    assert result2["ok"] is True

    # Step 3: 创建有时间任务
    sample_context["conversation"]["conversation_info"]["input_messages"] = [
        {"message": "明天提醒我", "input_timestamp": base_timestamp}
    ]
    reminder_tools.set_reminder_session_state(sample_context)

    result3 = reminder_tools.reminder_tool.entrypoint(
        action="create",
        title="开会",
        trigger_time="明天09时00分",
        session_state=sample_context
    )
    assert result3["ok"] is True

    # Step 4: 查询所有任务
    result_query = reminder_tools.reminder_tool.entrypoint(
        action="filter",
        session_state=sample_context
    )

    assert result_query["ok"] is True
    assert result_query["count"] == 3

    # 验证分组显示
    message = result_query["message"]
    assert "定时提醒" in message or "已安排" in message
    assert "待安排" in message or "Inbox" in message

    # 验证所有任务都在消息中
    assert "买牛奶" in message
    assert "整理书架" in message
    assert "开会" in message
```

**Step 2: Run integration test**

Run: `pytest tests/unit/test_reminder_gtd_integration.py -v`

Expected: PASS - full workflow works end-to-end

**Step 3: Commit integration test**

```bash
git add tests/unit/test_reminder_gtd_integration.py
git commit -m "test(gtd): add integration test for inbox workflow

- Test creating tasks with and without trigger_time
- Test querying and display grouping
- Verify full GTD P0 workflow

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Documentation Update

**Files:**
- Modify: `CLAUDE.md`
- Create: `doc/plans/gtd-p1-roadmap.md`

**Step 1: Update CLAUDE.md with GTD P0 changes**

Add to the MongoDB Collections section:

```markdown
### MongoDB Collections

`inputmessages`, `outputmessages`, `users`, `conversations`, `relations`, `embeddings`, `reminders`, `locks`

**GTD Support (P0):**
- `reminders` collection now supports GTD-style task collection
- `list_id` field: defaults to "inbox", supports task organization
- `trigger_time` field: can be `None` for tasks without specific time
```

Add a new section after MongoDB Collections:

```markdown
### GTD Task System

**P0 Features (Completed):**
- Quick capture: Create tasks without trigger_time
- Inbox collection: Tasks default to `list_id="inbox"`
- Query differentiation: Displays scheduled vs inbox tasks separately

**P1 Roadmap:**
- Agent prompt adjustments for conversational task creation
- Daily inbox digest (8:30 AM summary)
- Custom list support beyond "inbox"
- Priority and tags
```

**Step 2: Create P1 roadmap document**

```markdown
# GTD Task System P1 Roadmap

## Completed (P0)

✅ Data structure: `list_id` field with "inbox" default
✅ Nullable `trigger_time` support
✅ DAO layer updates
✅ Tool layer updates
✅ Display differentiation for inbox tasks

## P1 Scope

### 1. Agent Prompt Modifications

**Orchestrator Agent:**
- Understand "帮我记一下..." as task creation intent
- Differentiate between "提醒我" (needs time) vs "记一下" (quick capture)

**Chat Response Agent:**
- After creating inbox task: "已记下！要设置提醒时间吗？"
- Don't wait for reply, end conversation naturally

**Estimated Effort:** 2-3 tasks

### 2. Daily Inbox Digest

**Implementation:**
- Integrate APScheduler into main process
- Daily trigger at 8:30 AM (configurable)
- Query: `list_id="inbox" AND trigger_time=None AND status="active"`
- Send message with full task list

**Message Format:**
```
☀️ 早上好！你的收集篮里有 3 个待安排的想法：

📥 待安排：
  • 买牛奶
  • 整理书架
  • 研究新框架

要处理哪一个吗？
```

**Estimated Effort:** 3-4 tasks

### 3. Custom List Support

**Features:**
- Allow `list_id` to be user-defined (e.g., "work", "personal")
- Update tools to accept `list_id` parameter
- Query by list

**Out of Scope for P1:**
- List management UI
- Context-based lists (@home, @office)

**Estimated Effort:** 2-3 tasks

### 4. Priority & Tags (Optional)

**Schema:**
```python
{
    "priority": int,  # 0-5, default 0
    "tags": List[str]  # ["work", "urgent"]
}
```

**Estimated Effort:** 3-4 tasks

## Total P1 Effort

10-14 tasks across 4 features

## Success Criteria

- [ ] Users can create tasks conversationally without explicit time
- [ ] Daily digest delivered reliably at 8:30 AM
- [ ] Users can query inbox separately from scheduled reminders
- [ ] Test coverage maintains 70%+ threshold
```

**Step 3: Commit documentation**

```bash
git add CLAUDE.md doc/plans/gtd-p1-roadmap.md
git commit -m "docs: update for GTD P0 completion and P1 roadmap

- Add GTD section to CLAUDE.md
- Create P1 roadmap document
- Document completed P0 features

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Run Migration and Full Test Suite

**Files:**
- None (verification task)

**Step 1: Run migration script on development database**

Run: `python scripts/migrate_add_list_id_to_reminders.py`

Expected: Migration completes successfully, all existing reminders now have `list_id="inbox"`

**Step 2: Run full unit test suite**

Run: `pytest -m unit -v`

Expected: All unit tests pass

**Step 3: Run integration tests if MongoDB is available**

Run: `pytest -m integration -v`

Expected: All integration tests pass (or skip if MongoDB not available)

**Step 4: Run coverage report**

Run: `pytest --cov --cov-report=html`

Expected: Coverage remains above 70% threshold

**Step 5: Verify no regressions in existing functionality**

Run: `pytest tests/unit/test_reminder_tools*.py -v`
Run: `pytest tests/e2e/test_reminder*.py -v`

Expected: All reminder-related tests pass

**Step 6: Create final verification commit**

```bash
git add -A
git commit -m "chore(gtd): verify P0 implementation complete

- Migration script tested
- All unit tests passing
- Integration tests passing
- Coverage threshold maintained

GTD P0 Complete:
✅ list_id field with inbox default
✅ Nullable trigger_time support
✅ DAO layer updates
✅ Tool layer updates
✅ Display differentiation
✅ Tests and documentation

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Completion Checklist

- [ ] Task 1: Migration script created and tested
- [ ] Task 2: DAO layer supports list_id field
- [ ] Task 3: DAO layer supports nullable trigger_time
- [ ] Task 4: Tool layer removed trigger_time requirement
- [ ] Task 5: Query display differentiates inbox tasks
- [ ] Task 6: Integration test passes
- [ ] Task 7: Documentation updated
- [ ] Task 8: Migration run, full test suite passes

**Ready for P1:** Agent prompt modifications and daily digest

---

## Notes for Executor

- Each task is designed to be 2-5 minutes of focused work
- Tests are written before implementation (TDD)
- Commits are frequent and atomic
- P0 does NOT modify agent prompts - users can't use this feature yet
- P1 will add the conversational interface and daily digest
