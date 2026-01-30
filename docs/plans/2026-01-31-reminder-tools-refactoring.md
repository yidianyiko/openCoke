# Reminder Tools Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor `reminder_tools.py` (2939 lines) into a layered architecture for better maintainability while preserving all existing behavior and LLM interface.

**Architecture:** Extract business logic from tool layer into service layer with supporting modules for parsing, validation, and formatting. Keep single `@tool` entry point with same interface.

**Tech Stack:** Python 3.12, Agno 2.x, MongoDB (via existing ReminderDAO), contextvars for async isolation

**Key Constraints:**
- Tool interface must remain unchanged (LLM compatibility)
- contextvars session state isolation must be preserved
- All existing behavior preserved (including GTD inbox, side-effect guards, batch operations)
- Follow TDD: write tests first, then implementation

---

## Task 1: Create Reminder Subdirectory Structure

**Files:**
- Create: `agent/agno_agent/tools/reminder/__init__.py`

**Step 1: Create the reminder subdirectory and init file**

```bash
mkdir -p agent/agno_agent/tools/reminder
```

**Step 2: Create __init__.py**

```python
# agent/agno_agent/tools/reminder/__init__.py
"""
Reminder tool modules.

Provides a layered architecture for reminder management:
- TimeParser: Time parsing and formatting utilities
- ReminderValidator: Validation rules and side-effect guards
- ReminderFormatter: Response message building
- ReminderService: Business logic orchestration
"""

from .parser import TimeParser
from .validator import ReminderValidator
from .formatter import ReminderFormatter
from .service import ReminderService

__all__ = [
    "TimeParser",
    "ReminderValidator",
    "ReminderFormatter",
    "ReminderService",
]
```

**Step 3: Commit**

```bash
git add agent/agno_agent/tools/reminder/__init__.py
git commit -m "feat(tools): create reminder subdirectory for refactoring"
```

---

## Task 2: Implement TimeParser Module

**Files:**
- Create: `agent/agno_agent/tools/reminder/parser.py`
- Test: `tests/unit/reminder/test_parser.py`

**Step 1: Write failing tests for TimeParser**

Create test file:

```python
# tests/unit/reminder/test_parser.py
import pytest
from agent.agno_agent.tools.reminder.parser import TimeParser


class TestTimeParser:
    def test_parse_relative_time_minutes(self):
        parser = TimeParser(base_timestamp=1704067200)  # 2024-01-01 00:00:00
        result = parser.parse("30分钟后")
        assert result == 1704069000  # +30 minutes

    def test_parse_relative_time_hours(self):
        parser = TimeParser(base_timestamp=1704067200)
        result = parser.parse("2小时后")
        assert result == 1704074400  # +2 hours

    def test_parse_absolute_time(self):
        parser = TimeParser()
        result = parser.parse("2024年12月25日09时00分")
        assert result is not None
        assert result > 1703500800  # After 2024-12-25

    def test_parse_none_returns_none(self):
        parser = TimeParser()
        result = parser.parse(None)
        assert result is None

    def test_parse_empty_string_returns_none(self):
        parser = TimeParser()
        result = parser.parse("")
        assert result is None

    def test_format_friendly_time(self):
        parser = TimeParser()
        result = parser.format_friendly(1704067200)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_with_date(self):
        parser = TimeParser()
        result = parser.format_with_date(1704067200)  # 2024-01-01 00:00:00 Monday
        assert "1月" in result
        assert "1日" in result
        assert "星期" in result

    def test_parse_period_config_simple(self):
        parser = TimeParser()
        result = parser.parse_period_config("09:00", "18:00", "1,2,3,4,5")
        assert result is not None
        assert result["start_time"] == "09:00"
        assert result["end_time"] == "18:00"
        assert result["active_days"] == [1, 2, 3, 4, 5]

    def test_parse_period_config_none(self):
        parser = TimeParser()
        result = parser.parse_period_config(None, None, None)
        assert result is None
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/reminder/test_parser.py -v
```

Expected: `ModuleNotFoundError: No module named 'agent.agno_agent.tools.reminder.parser'`

**Step 3: Implement TimeParser**

```python
# agent/agno_agent/tools/reminder/parser.py
"""Time parsing and formatting utilities for reminders."""

import logging
from datetime import datetime
from typing import Optional

from util.time_util import format_time_friendly, parse_relative_time, str2timestamp

logger = logging.getLogger(__name__)


class TimeParser:
    """Parse and format time strings for reminder operations."""

    def __init__(self, base_timestamp: Optional[int] = None):
        """
        Initialize TimeParser.

        Args:
            base_timestamp: Base timestamp for relative time calculations.
                          Defaults to current time if None.
        """
        self.base_timestamp = base_timestamp

    def parse(self, time_str: Optional[str]) -> Optional[int]:
        """
        Parse time string to Unix timestamp.

        Supports:
        - Relative time: "30分钟后", "2小时后", "明天", "后天", "下周"
        - Absolute time: "2024年12月25日09时00分"

        Args:
            time_str: Time string to parse

        Returns:
            Unix timestamp or None if parsing fails
        """
        if not time_str:
            return None

        # Try relative time first
        timestamp = parse_relative_time(time_str, self.base_timestamp)
        if timestamp:
            return timestamp

        # Try absolute time
        timestamp = str2timestamp(time_str)
        if timestamp:
            return timestamp

        return None

    def format_friendly(self, timestamp: int) -> str:
        """
        Format timestamp to user-friendly string.

        Args:
            timestamp: Unix timestamp

        Returns:
            Formatted time string
        """
        return format_time_friendly(timestamp)

    def format_with_date(self, timestamp: int) -> str:
        """
        Format timestamp with full date and weekday.

        Args:
            timestamp: Unix timestamp

        Returns:
            Formatted string like "12月30日 星期二 下午4点45分"
        """
        dt = datetime.fromtimestamp(timestamp)

        # Date part
        date_str = f"{dt.month}月{dt.day}日"

        # Weekday part
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_str = weekdays[dt.weekday()]

        # Time part
        hour = dt.hour
        minute = dt.minute
        if hour < 12:
            period = "上午"
        elif hour < 18:
            period = "下午"
            if hour > 12:
                hour = hour - 12
        else:
            period = "晚上"
            if hour > 12:
                hour = hour - 12

        time_str = f"{period}{hour}点"
        if minute > 0:
            time_str += f"{minute}分"

        return f"{date_str} {weekday_str} {time_str}"

    def parse_period_config(
        self,
        period_start: Optional[str],
        period_end: Optional[str],
        period_days: Optional[str],
    ) -> Optional[dict]:
        """
        Parse time period configuration.

        Args:
            period_start: Start time in "HH:MM" format
            period_end: End time in "HH:MM" format
            period_days: Comma-separated day numbers (1-7, Monday=1)

        Returns:
            Period config dict or None if no period config
        """
        if not period_start or not period_end:
            return None

        # Parse active days
        active_days = None
        if period_days:
            try:
                days_str = period_days.replace("，", ",")
                active_days = [int(d.strip()) for d in days_str.split(",") if d.strip()]
                active_days = sorted(set(active_days))
            except (ValueError, AttributeError):
                logger.warning(f"Invalid period_days: {period_days}")
                active_days = None

        return {
            "start_time": period_start,
            "end_time": period_end,
            "active_days": active_days or [1, 2, 3, 4, 5, 6, 7],
            "timezone": "Asia/Shanghai",
        }
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/reminder/test_parser.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add agent/agno_agent/tools/reminder/parser.py tests/unit/reminder/test_parser.py
git commit -m "feat(tools): implement TimeParser module with tests"
```

---

## Task 3: Implement ReminderFormatter Module

**Files:**
- Create: `agent/agno_agent/tools/reminder/formatter.py`
- Test: `tests/unit/reminder/test_formatter.py`

**Step 1: Write failing tests for ReminderFormatter**

```python
# tests/unit/reminder/test_formatter.py
import pytest
from agent.agno_agent.tools.reminder.formatter import ReminderFormatter


class TestReminderFormatter:
    def test_create_success_with_time(self):
        formatter = ReminderFormatter()
        reminder = {
            "reminder_id": "test-123",
            "title": "Test Reminder",
            "next_trigger_time": 1704067200,
        }
        result = formatter.create_success(reminder)
        assert result["ok"] is True
        assert result["status"] == "created"
        assert "Test Reminder" in result["message"]

    def test_create_success_inbox(self):
        formatter = ReminderFormatter()
        reminder = {
            "reminder_id": "test-456",
            "title": "Inbox Task",
            "next_trigger_time": None,
            "list_id": "inbox",
        }
        result = formatter.create_success(reminder)
        assert result["ok"] is True
        assert "收集箱" in result["message"]

    def test_update_success(self):
        formatter = ReminderFormatter()
        reminder = {
            "reminder_id": "test-789",
            "title": "Updated Title",
            "next_trigger_time": 1704067200,
        }
        result = formatter.update_success(reminder, {"title": "Updated Title"})
        assert result["ok"] is True
        assert "更新" in result["message"]

    def test_delete_success_single(self):
        formatter = ReminderFormatter()
        result = formatter.delete_success(count=1, keyword="Test")
        assert result["ok"] is True
        assert "删除" in result["message"]

    def test_delete_success_all(self):
        formatter = ReminderFormatter()
        result = formatter.delete_success(count=5, keyword="*")
        assert result["ok"] is True
        assert "全部" in result["message"]

    def test_filter_result_empty(self):
        formatter = ReminderFormatter()
        result = formatter.filter_result([])
        assert result["ok"] is True
        assert result["count"] == 0
        assert "没有" in result["message"]

    def test_filter_result_with_reminders(self):
        formatter = ReminderFormatter()
        reminders = [
            {
                "reminder_id": "r1",
                "title": "Task 1",
                "status": "active",
                "next_trigger_time": 1704067200,
            },
            {
                "reminder_id": "r2",
                "title": "Task 2",
                "status": "active",
                "next_trigger_time": None,
            },
        ]
        result = formatter.filter_result(reminders)
        assert result["ok"] is True
        assert result["count"] == 2
        assert "reminders" in result

    def test_batch_summary_all_success(self):
        formatter = ReminderFormatter()
        results = [
            {"ok": True, "action": "create", "title": "Task 1"},
            {"ok": True, "action": "delete", "keyword": "Old"},
        ]
        result = formatter.batch_summary(results)
        assert result["ok"] is True
        assert result["summary"]["total"] == 2
        assert result["summary"]["succeeded"] == 2

    def test_batch_summary_with_failures(self):
        formatter = ReminderFormatter()
        results = [
            {"ok": True, "action": "create"},
            {"ok": False, "action": "delete", "error": "Not found"},
        ]
        result = formatter.batch_summary(results)
        assert result["ok"] is True
        assert result["summary"]["failed"] == 1

    def test_guarded_response(self):
        formatter = ReminderFormatter()
        guard = {
            "allowed": False,
            "error": "需要明确指定",
            "candidates": [{"title": "Task 1"}],
            "needs_confirmation": True,
        }
        result = formatter.guarded_response(guard)
        assert result["ok"] is False
        assert result["needs_confirmation"] is True

    def test_error_response(self):
        formatter = ReminderFormatter()
        result = formatter.error("Something went wrong", code="test_error")
        assert result["ok"] is False
        assert result["error"] == "Something went wrong"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/reminder/test_formatter.py -v
```

Expected: `ModuleNotFoundError: No module named 'agent.agno_agent.tools.reminder.formatter'`

**Step 3: Implement ReminderFormatter**

```python
# agent/agno_agent/tools/reminder/formatter.py
"""Response message formatting for reminder operations."""

import logging
from datetime import datetime
from typing import Optional

from .parser import TimeParser

logger = logging.getLogger(__name__)


class ReminderFormatter:
    """Format reminder operation results into user-friendly messages."""

    def __init__(self):
        self.parser = TimeParser()

    def create_success(self, reminder: dict) -> dict:
        """
        Format successful reminder creation response.

        Args:
            reminder: Created reminder document

        Returns:
            Response dict with ok=True and formatted message
        """
        reminder_id = reminder.get("reminder_id")
        title = reminder.get("title", "")
        trigger_time = reminder.get("next_trigger_time")

        if trigger_time:
            # Scheduled reminder
            dt = datetime.fromtimestamp(trigger_time)
            trigger_time_str = dt.strftime("%Y年%m月%d日%H时%M分")
            time_friendly = self.parser.format_friendly(trigger_time)

            # Recurrence description
            recurrence = reminder.get("recurrence", {})
            recurrence_desc = ""
            if recurrence.get("enabled"):
                recurrence_type = recurrence.get("type", "")
                interval = recurrence.get("interval", 1)
                recurrence_map = {
                    "daily": "每天",
                    "weekly": "每周",
                    "monthly": "每月",
                    "yearly": "每年",
                    "interval": f"每{interval}分钟",
                }
                recurrence_desc = f"，周期：{recurrence_map.get(recurrence_type, recurrence_type)}"
                if recurrence.get("max_count"):
                    recurrence_desc += f"（最多提醒{recurrence['max_count']}次）"

            # Period description
            period_desc = ""
            time_period = reminder.get("time_period")
            if time_period:
                days_map = {
                    1: "周一", 2: "周二", 3: "周三", 4: "周四",
                    5: "周五", 6: "周六", 7: "周日",
                }
                active_days = time_period.get("active_days", [])
                if active_days == [1, 2, 3, 4, 5]:
                    days_str = "工作日"
                elif active_days:
                    days_str = "、".join([days_map[d] for d in active_days])
                else:
                    days_str = "每天"
                period_desc = (
                    f"，时间段：{days_str} "
                    f"{time_period['start_time']}-{time_period['end_time']}"
                )

            message = (
                f"系统动作(非用户消息)：已按照用户最新的要求创建提醒成功："
                f"已为用户设置「{title}」提醒，时间为{trigger_time_str}"
                f"{recurrence_desc}{period_desc}"
            )
        else:
            # Inbox task (no time)
            message = (
                f"系统动作(非用户消息)：已按照用户最新的要求创建任务成功："
                f"已为用户记录任务「{title}」（无时间，存入收集箱）"
            )

        return {
            "ok": True,
            "status": "created",
            "reminder_id": reminder_id,
            "title": title,
            "next_trigger_time": trigger_time,
            "message": message,
            "time_friendly": time_friendly if trigger_time else "",
        }

    def update_success(self, reminder: dict, changes: dict) -> dict:
        """
        Format successful reminder update response.

        Args:
            reminder: Updated reminder document
            changes: Dict of changed fields

        Returns:
            Response dict
        """
        title = reminder.get("title", "")
        message = f"系统动作(非用户消息)：已按照用户最新的要求更新提醒成功：已更新「{title}」"

        if "new_trigger_time" in changes:
            new_time = changes["new_trigger_time"]
            if new_time:
                dt = datetime.fromtimestamp(new_time)
                time_str = dt.strftime("%Y年%m月%d日%H时%M分")
                message += f"，时间为{time_str}"

        return {
            "ok": True,
            "status": "updated",
            "reminder_id": reminder.get("reminder_id"),
            "message": message,
            "changes": changes,
        }

    def delete_success(self, count: int, keyword: str) -> dict:
        """
        Format successful deletion response.

        Args:
            count: Number of reminders deleted
            keyword: Keyword used for deletion

        Returns:
            Response dict
        """
        if keyword == "*":
            message = f"系统动作(非用户消息)：已按照用户最新的要求删除提醒成功：已删除全部{count}个提醒"
        else:
            message = f"系统动作(非用户消息)：已按照用户最新的要求删除提醒成功：已删除{count}个包含「{keyword}」的提醒"

        return {
            "ok": True,
            "status": "deleted",
            "count": count,
            "message": message,
        }

    def complete_success(self, count: int, keyword: str) -> dict:
        """
        Format successful completion response.

        Args:
            count: Number of reminders completed
            keyword: Keyword used

        Returns:
            Response dict
        """
        message = f"系统动作(非用户消息)：已按照用户最新的要求完成提醒成功：已完成{count}个包含「{keyword}」的提醒"

        return {
            "ok": True,
            "status": "completed",
            "count": count,
            "message": message,
        }

    def filter_result(self, reminders: list) -> dict:
        """
        Format filter/query results.

        Args:
            reminders: List of reminder documents

        Returns:
            Response dict with formatted reminders
        """
        formatted_reminders = []
        reminder_summaries = []

        for i, reminder in enumerate(reminders, 1):
            trigger_time = reminder.get("next_trigger_time", 0)
            status = reminder.get("status", "")

            formatted = {
                "reminder_id": reminder.get("reminder_id"),
                "title": reminder.get("title"),
                "status": status,
                "status_display": self._get_status_indicator(status),
                "next_trigger_time": trigger_time,
                "time_friendly": (
                    self.parser.format_friendly(trigger_time) if trigger_time else ""
                ),
                "time_with_date": (
                    self.parser.format_with_date(trigger_time) if trigger_time else ""
                ),
                "recurrence": reminder.get("recurrence", {}),
                "list_id": reminder.get("list_id", "inbox"),
                "created_at": reminder.get("created_at"),
                "triggered_count": reminder.get("triggered_count", 0),
            }
            formatted_reminders.append(formatted)

            # Build summary
            title = reminder.get("title", "")
            time_with_date = formatted["time_with_date"] or "未设置时间"
            status_indicator = self._get_status_indicator(status)
            reminder_summaries.append(
                f"{i}.{title}({time_with_date}) [{status_indicator}]"
            )

        # Group: with time vs without time
        with_time = [r for r in formatted_reminders if r.get("next_trigger_time")]
        without_time = [r for r in formatted_reminders if not r.get("next_trigger_time")]

        if formatted_reminders:
            parts = []
            if with_time:
                parts.append(f"有{len(with_time)}个定时提醒")
            if without_time:
                parts.append(f"{len(without_time)}个无时间任务")

            summary_str = "、".join(reminder_summaries[:5])  # Limit summary length
            if len(reminder_summaries) > 5:
                summary_str += f"等{len(reminder_summaries)}个"

            message = (
                f"查询成功：用户当前{'、'.join(parts)}：{summary_str}"
            )
        else:
            message = "查询成功：用户当前没有待执行的提醒"

        return {
            "ok": True,
            "count": len(formatted_reminders),
            "reminders": formatted_reminders,
            "with_time": with_time,
            "without_time": without_time,
            "message": message,
        }

    def batch_summary(self, results: list) -> dict:
        """
        Format batch operation summary.

        Args:
            results: List of individual operation results

        Returns:
            Response dict with summary
        """
        total = len(results)
        succeeded = sum(1 for r in results if r.get("ok"))
        failed = total - succeeded

        # Count by action type
        action_counts = {}
        for r in results:
            action = r.get("action", "unknown")
            action_counts[action] = action_counts.get(action, 0) + 1

        # Build message
        parts = []
        if succeeded > 0:
            parts.append(f"成功{succeeded}个")
        if failed > 0:
            parts.append(f"失败{failed}个")

        message = f"批量操作完成：共{total}个操作，{'、'.join(parts)}"

        return {
            "ok": True,
            "message": message,
            "summary": {
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
                "action_counts": action_counts,
            },
            "results": results,
        }

    def guarded_response(self, guard: dict) -> dict:
        """
        Format side-effect guard rejection response.

        Args:
            guard: Guard result dict from validator

        Returns:
            Response dict
        """
        candidates = guard.get("candidates") or []
        display = guard.get("display") or ""

        if display:
            error_msg = f"{guard.get('error')}。可选提醒：{display}"
        else:
            error_msg = guard.get("error", "操作被阻止")

        return {
            "ok": False,
            "error": error_msg,
            "needs_confirmation": guard.get("needs_confirmation", False),
            "candidates": candidates,
        }

    def error(self, message: str, **details) -> dict:
        """
        Format error response.

        Args:
            message: Error message
            **details: Additional error details

        Returns:
            Error response dict
        """
        return {
            "ok": False,
            "error": message,
            **details
        }

    def _get_status_indicator(self, status: str) -> str:
        """Get user-friendly status indicator."""
        status_map = {
            "active": "⏳待执行",
            "triggered": "⏰已触发",
            "completed": "✓已完成",
            "cancelled": "✗已取消",
            # Backward compatibility
            "confirmed": "⏳待执行",
            "pending": "⏳待执行",
        }
        return status_map.get(status, status)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/reminder/test_formatter.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add agent/agno_agent/tools/reminder/formatter.py tests/unit/reminder/test_formatter.py
git commit -m "feat(tools): implement ReminderFormatter module with tests"
```

---

## Task 4: Implement ReminderValidator Module (Part 1: Basic Validation)

**Files:**
- Create: `agent/agno_agent/tools/reminder/validator.py`
- Test: `tests/unit/reminder/test_validator.py`

**Step 1: Write failing tests for basic validation**

```python
# tests/unit/reminder/test_validator.py
import pytest
from unittest.mock import Mock
from agent.agno_agent.tools.reminder.validator import ReminderValidator


class TestReminderValidator:
    def test_check_required_fields_missing_title(self):
        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        result = validator.check_required_fields(None, "30分钟后")
        assert result is not None
        assert result["ok"] is False
        assert "title" in result.get("error", "").lower()

    def test_check_required_fields_all_present(self):
        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        result = validator.check_required_fields("Test Task", None)
        assert result is None  # No error means validation passed

    def test_check_frequency_limit_interval_too_small(self):
        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        result = validator.check_frequency_limit(
            recurrence_type="interval",
            recurrence_interval=30,  # Only 30 minutes
            has_period=False,
        )
        assert result is not None
        assert result["ok"] is False

    def test_check_frequency_limit_interval_ok(self):
        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        result = validator.check_frequency_limit(
            recurrence_type="interval",
            recurrence_interval=90,  # 90 minutes - above limit
            has_period=False,
        )
        assert result is None  # No error

    def test_check_frequency_limit_period_too_small(self):
        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        result = validator.check_frequency_limit(
            recurrence_type="interval",
            recurrence_interval=30,  # Would be OK for interval
            has_period=True,  # But period requires 25 min minimum
        )
        assert result is None  # 30 > 25, so OK

        result = validator.check_frequency_limit(
            recurrence_type="interval",
            recurrence_interval=20,  # Less than 25
            has_period=True,
        )
        assert result is not None
        assert result["ok"] is False

    def test_check_frequency_limit_none_type(self):
        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        result = validator.check_frequency_limit(
            recurrence_type="none",
            recurrence_interval=1,
            has_period=False,
        )
        assert result is None  # No recurrence, no limit check needed

    def test_check_operation_allowed_first_call(self):
        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        allowed, error = validator.check_operation_allowed("create", [])
        assert allowed is True
        assert error == ""

    def test_check_operation_allowed_duplicate(self):
        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        allowed, error = validator.check_operation_allowed("create", ["create"])
        assert allowed is False
        assert "只能执行一次" in error

    def test_check_operation_allowed_batch_exclusive(self):
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        # batch after other operation
        allowed, error = validator.check_operation_allowed("batch", ["create"])
        assert allowed is False

        # other after batch
        allowed, error = validator.check_operation_allowed("create", ["batch"])
        assert allowed is False

    def test_check_duplicate_found(self):
        dao = Mock()
        dao.find_similar_reminder.return_value = {
            "title": "Test Task",
            "next_trigger_time": 1704067200,
        }
        validator = ReminderValidator(dao, "user123")
        result = validator.check_duplicate("Test Task", 1704067200, tolerance=60)
        assert result is not None
        assert result.get("status") == "duplicate"

    def test_check_duplicate_not_found(self):
        dao = Mock()
        dao.find_similar_reminder.return_value = None
        validator = ReminderValidator(dao, "user123")
        result = validator.check_duplicate("Test Task", 1704067200, tolerance=60)
        assert result is None
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/reminder/test_validator.py -v
```

Expected: `ModuleNotFoundError: No module named 'agent.agno_agent.tools.reminder.validator'`

**Step 3: Implement basic ReminderValidator**

```python
# agent/agno_agent/tools/reminder/validator.py
"""Validation rules and side-effect guards for reminder operations."""

import logging
from typing import Optional, List

from dao.reminder_dao import ReminderDAO

logger = logging.getLogger(__name__)


class ReminderValidator:
    """
    Validation and guard logic for reminder operations.

    Constants:
        MIN_INTERVAL_INFINITE: Minimum interval for infinite recurring reminders (minutes)
        MIN_INTERVAL_PERIOD: Minimum interval for time-period reminders (minutes)
        DEFAULT_MAX_TRIGGERS: Default max trigger count for recurring reminders
        TIME_TOLERANCE: Time tolerance for duplicate detection (seconds)
    """

    MIN_INTERVAL_INFINITE = 60  # Infinite recurring: min 60 minutes
    MIN_INTERVAL_PERIOD = 25    # Time period: min 25 minutes
    DEFAULT_MAX_TRIGGERS = 10
    TIME_TOLERANCE = 60

    # Words indicating delete-all intent
    DELETE_ALL_WORDS = ["全部", "所有", "清空", "都删", "全删"]

    def __init__(self, dao: ReminderDAO, user_id: str):
        """
        Initialize validator.

        Args:
            dao: ReminderDAO instance for data access
            user_id: User ID for user-specific validations
        """
        self.dao = dao
        self.user_id = user_id

    def check_required_fields(
        self, title: Optional[str], trigger_time: Optional[str]
    ) -> Optional[dict]:
        """
        Check if required fields are present.

        Note: trigger_time is optional for GTD inbox tasks.

        Args:
            title: Reminder title
            trigger_time: Trigger time string

        Returns:
            Error dict if validation fails, None if passes
        """
        if not title:
            return {
                "ok": False,
                "error": "需要补充: 提醒内容/事项",
                "status": "needs_info",
                "needs_info": {"title": True},
            }
        return None

    def check_frequency_limit(
        self,
        recurrence_type: str,
        recurrence_interval: int,
        has_period: bool,
    ) -> Optional[dict]:
        """
        Check if recurrence frequency is within limits.

        Rules:
        - Infinite interval recurring < 60 minutes: forbidden
        - Time period reminders: minimum 25 minutes

        Args:
            recurrence_type: Type of recurrence ("none", "daily", "weekly", etc.)
            recurrence_interval: Interval number
            has_period: Whether this is a time-period reminder

        Returns:
            Error dict if validation fails, None if passes
        """
        # No recurrence - no frequency limit
        if recurrence_type == "none":
            return None

        # Time period reminders have stricter limits
        if has_period:
            if recurrence_interval < self.MIN_INTERVAL_PERIOD:
                return {
                    "ok": False,
                    "error": (
                        f"时间段提醒最小间隔为{self.MIN_INTERVAL_PERIOD}分钟，"
                        f"当前设置{recurrence_interval}分钟"
                    ),
                }
            return None

        # Interval-based recurring reminders
        if recurrence_type == "interval":
            if recurrence_interval < self.MIN_INTERVAL_INFINITE:
                return {
                    "ok": False,
                    "error": (
                        f"无限重复提醒最小间隔为{self.MIN_INTERVAL_INFINITE}分钟，"
                        f"当前设置{recurrence_interval}分钟。"
                        f"请设置更大的间隔或使用时间段提醒。"
                    ),
                }

        return None

    def check_duplicate(
        self,
        title: str,
        trigger_time: int,
        tolerance: int = TIME_TOLERANCE,
    ) -> Optional[dict]:
        """
        Check for duplicate or similar existing reminders.

        Args:
            title: Reminder title
            trigger_time: Parsed trigger timestamp
            tolerance: Time tolerance in seconds

        Returns:
            Duplicate info dict if found, None if no duplicate
        """
        similar = self.dao.find_similar_reminder(
            self.user_id, title, trigger_time, tolerance
        )

        if similar:
            return {
                "ok": True,
                "status": "duplicate",
                "reminder_id": similar.get("reminder_id"),
                "title": similar.get("title"),
                "existing_time": similar.get("next_trigger_time"),
                "message": f"已存在类似的提醒「{similar.get('title')}」",
            }

        return None

    def check_operation_allowed(
        self, action: str, session_operations: List[str]
    ) -> tuple[bool, str]:
        """
        Check if operation is allowed (prevents circular calls).

        Rules:
        - batch must be the only operation
        - Each other operation can only be called once
        - Cannot call other operations after batch

        Args:
            action: Action type to check
            session_operations: List of already-executed operations

        Returns:
            (allowed, error_message) tuple
        """
        # batch operation special handling
        if action == "batch":
            if session_operations:
                return False, "batch 操作必须是唯一的操作，不能与其他操作混用"
        elif "batch" in session_operations:
            return False, "已执行 batch 操作，不能再执行其他操作"

        # Check for duplicate operations
        if action in session_operations:
            return False, f"{action} 操作只能执行一次"

        return True, ""
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/reminder/test_validator.py::TestReminderValidator::test_check_required_fields_missing_title -v
pytest tests/unit/reminder/test_validator.py::TestReminderValidator::test_check_required_fields_all_present -v
pytest tests/unit/reminder/test_validator.py::TestReminderValidator::test_check_frequency_limit_interval_too_small -v
pytest tests/unit/reminder/test_validator.py::TestReminderValidator::test_check_frequency_limit_interval_ok -v
pytest tests/unit/reminder/test_validator.py::TestReminderValidator::test_check_frequency_limit_period_too_small -v
pytest tests/unit/reminder/test_validator.py::TestReminderValidator::test_check_frequency_limit_none_type -v
pytest tests/unit/reminder/test_validator.py::TestReminderValidator::test_check_operation_allowed_first_call -v
pytest tests/unit/reminder/test_validator.py::TestReminderValidator::test_check_operation_allowed_duplicate -v
pytest tests/unit/reminder/test_validator.py::TestReminderValidator::test_check_operation_allowed_batch_exclusive -v
pytest tests/unit/reminder/test_validator.py::TestReminderValidator::test_check_duplicate_found -v
pytest tests/unit/reminder/test_validator.py::TestReminderValidator::test_check_duplicate_not_found -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add agent/agno_agent/tools/reminder/validator.py tests/unit/reminder/test_validator.py
git commit -m "feat(tools): implement ReminderValidator basic validation with tests"
```

---

## Task 5: Implement ReminderValidator Side-Effect Guard

**Files:**
- Modify: `agent/agno_agent/tools/reminder/validator.py`
- Modify: `tests/unit/reminder/test_validator.py`

**Step 1: Write failing tests for guard_side_effect**

```python
# Add to tests/unit/reminder/test_validator.py

class TestReminderValidatorSideEffectGuard:
    def test_guard_delete_no_match_in_text(self, monkeypatch):
        # Mock session state with user text
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [
                        {"message": "删除那个提醒"}
                    ]
                }
            }
        }

        dao = Mock()
        dao.filter_reminders.return_value = [
            {"title": "Task A", "reminder_id": "a1"},
            {"title": "Task B", "reminder_id": "b1"},
        ]

        validator = ReminderValidator(dao, "user123")
        result = validator.guard_side_effect(
            action="delete",
            keyword=None,
            session_state=session_state,
        )

        assert result["allowed"] is False
        assert result["needs_confirmation"] is True

    def test_guard_delete_single_match_in_text(self, monkeypatch):
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [
                        {"message": "删除开会提醒"}
                    ]
                }
            }
        }

        dao = Mock()
        dao.filter_reminders.return_value = [
            {"title": "开会", "reminder_id": "a1"},
        ]

        validator = ReminderValidator(dao, "user123")
        result = validator.guard_side_effect(
            action="delete",
            keyword=None,
            session_state=session_state,
        )

        assert result["allowed"] is True
        assert result["resolved_keyword"] == "开会"

    def test_guard_delete_keyword_in_text(self):
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [
                        {"message": "删除游泳那个"}
                    ]
                }
            }
        }

        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        result = validator.guard_side_effect(
            action="delete",
            keyword="游泳",
            session_state=session_state,
        )

        assert result["allowed"] is True
        assert result["resolved_keyword"] == "游泳"

    def test_guard_delete_all_explicit(self):
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [
                        {"message": "把全部提醒都删掉"}
                    ]
                }
            }
        }

        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        result = validator.guard_side_effect(
            action="delete",
            keyword="*",
            session_state=session_state,
        )

        assert result["allowed"] is True
        assert result["reason"] == "explicit_delete_all"

    def test_guard_delete_all_not_explicit(self):
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [
                        {"message": "删除提醒"}
                    ]
                }
            }
        }

        dao = Mock()
        dao.filter_reminders.return_value = [
            {"title": "Task A", "reminder_id": "a1"},
        ]

        validator = ReminderValidator(dao, "user123")
        result = validator.guard_side_effect(
            action="delete",
            keyword="*",
            session_state=session_state,
        )

        assert result["allowed"] is False
        assert result["needs_confirmation"] is True

    def test_guard_complete_allowed(self):
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [
                        {"message": "完成任务A"}
                    ]
                }
            }
        }

        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        result = validator.guard_side_effect(
            action="complete",
            keyword="任务A",
            session_state=session_state,
        )

        assert result["allowed"] is True

    def test_guard_non_side_effect_action(self):
        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        result = validator.guard_side_effect(
            action="create",
            keyword="test",
            session_state={},
        )

        assert result["allowed"] is True
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/reminder/test_validator.py::TestReminderValidatorSideEffectGuard -v
```

Expected: Tests fail (method not implemented)

**Step 3: Implement guard_side_effect method**

Add to `ReminderValidator` class in `validator.py`:

```python
    def guard_side_effect(
        self,
        action: str,
        keyword: Optional[str],
        session_state: Optional[dict],
    ) -> dict:
        """
        Guard against unintended side-effect operations (delete/complete).

        Validates that user intent is clear before allowing destructive actions.

        Args:
            action: Action type ("delete" or "complete")
            keyword: Keyword for matching reminders
            session_state: Current session state with user messages

        Returns:
            Guard result dict with keys:
            - allowed: bool
            - needs_confirmation: bool
            - error: str (if not allowed)
            - candidates: list (if confirmation needed)
            - resolved_keyword: str or None
            - reason: str
            - display: str (summary of candidates)
        """
        # Non-side-effect actions are always allowed
        if action not in ("delete", "complete"):
            return {"allowed": True}

        # Get user's original message text
        user_text = self._get_user_text(session_state).strip()

        if not user_text:
            return {
                "allowed": False,
                "needs_confirmation": True,
                "error": "无法获取用户本轮原文，已阻止执行有副作用的提醒操作",
                "candidates": [],
                "resolved_keyword": None,
                "reason": "missing_user_text",
            }

        # Get active candidates
        active_candidates = self._get_active_candidates()

        # Check for exact title matches in user text
        matched_titles = []
        for r in active_candidates:
            title = r.get("title", "").strip()
            if title and title in user_text:
                matched_titles.append(title)
        matched_titles = list(dict.fromkeys(matched_titles))  # Unique, preserve order

        # Single match - allow with resolved keyword
        if len(matched_titles) == 1:
            return {
                "allowed": True,
                "needs_confirmation": False,
                "error": "",
                "candidates": [],
                "resolved_keyword": matched_titles[0],
                "reason": "matched_active_title_in_user_text",
            }

        # Multiple matches - require clarification
        if len(matched_titles) > 1:
            candidates, display = self._summarize_candidates(active_candidates, limit=3)
            return {
                "allowed": False,
                "needs_confirmation": True,
                "error": "本轮消息同时命中多个提醒，无法确定要操作哪一个",
                "candidates": candidates,
                "resolved_keyword": None,
                "reason": "ambiguous_title_matches",
                "display": display,
            }

        # Delete-all handling
        if keyword == "*" and action == "delete":
            if self._contains_any(user_text, self.DELETE_ALL_WORDS):
                return {
                    "allowed": True,
                    "needs_confirmation": False,
                    "error": "",
                    "candidates": [],
                    "resolved_keyword": None,
                    "reason": "explicit_delete_all",
                }
            candidates, display = self._summarize_candidates(active_candidates, limit=3)
            return {
                "allowed": False,
                "needs_confirmation": True,
                "error": "删除全部提醒需要用户明确表示"全部/清空/所有"等意图",
                "candidates": candidates,
                "resolved_keyword": None,
                "reason": "delete_all_not_explicit",
                "display": display,
            }

        # Check if keyword is in user text
        if keyword and keyword in user_text:
            return {
                "allowed": True,
                "needs_confirmation": False,
                "error": "",
                "candidates": [],
                "resolved_keyword": keyword,
                "reason": "keyword_in_user_text",
            }

        # Default: require confirmation
        candidates, display = self._summarize_candidates(active_candidates, limit=3)
        return {
            "allowed": False,
            "needs_confirmation": True,
            "error": "用户本轮消息未明确包含要操作的提醒关键字或标题",
            "candidates": candidates,
            "resolved_keyword": None,
            "reason": "keyword_not_in_user_text",
            "display": display,
        }

    def _get_user_text(self, session_state: Optional[dict]) -> str:
        """Extract user's original message text from session state."""
        if not session_state:
            return ""

        conversation_info = (session_state.get("conversation", {})
                             .get("conversation_info", {}))
        input_messages = conversation_info.get("input_messages") or []

        if not isinstance(input_messages, list):
            return ""

        texts = []
        for msg in input_messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("message")
            if content is not None:
                content_str = str(content).strip()
                if content_str:
                    texts.append(content_str)
        return "\n".join(texts)

    def _get_active_candidates(self) -> list:
        """Get active reminders as candidates for matching."""
        try:
            reminders = self.dao.filter_reminders(
                user_id=self.user_id,
                status_list=["active", "triggered"]
            )
        except Exception:
            logger.warning("Failed to get active candidates")
            return []

        if not isinstance(reminders, list):
            return []
        return reminders

    def _summarize_candidates(
        self, reminders: list, limit: int = 3
    ) -> tuple[list, str]:
        """
        Summarize reminder candidates for display.

        Returns:
            (candidates_list, display_string) tuple
        """
        from datetime import datetime

        candidates = []
        lines = []
        for r in reminders[:limit]:
            title = str(r.get("title") or "").strip()
            ts = r.get("next_trigger_time")
            time_str = ""
            if isinstance(ts, (int, float)) and ts > 0:
                time_str = datetime.fromtimestamp(int(ts)).strftime("%m月%d日%H:%M")
            if title:
                candidates.append({
                    "title": title,
                    "time": time_str,
                    "reminder_id": r.get("reminder_id")
                })
                lines.append(f"「{title}」{('(' + time_str + ')') if time_str else ''}")
        display = "、".join(lines)
        return candidates, display

    @staticmethod
    def _contains_any(text: str, candidates: List[str]) -> bool:
        """Check if text contains any of the candidate words."""
        if not text:
            return False
        for word in candidates:
            if word and word in text:
                return True
        return False
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/reminder/test_validator.py::TestReminderValidatorSideEffectGuard -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add agent/agno_agent/tools/reminder/validator.py tests/unit/reminder/test_validator.py
git commit -m "feat(tools): implement ReminderValidator side-effect guard with tests"
```

---

## Task 6: Implement ReminderService - Create Operation

**Files:**
- Create: `agent/agno_agent/tools/reminder/service.py`
- Test: `tests/unit/reminder/test_service.py`

**Step 1: Write failing tests for service.create**

```python
# tests/unit/reminder/test_service.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from agent.agno_agent.tools.reminder.service import ReminderService


@pytest.fixture
def mock_dao():
    dao = Mock()
    dao.create_reminder.return_value = "test-id-123"
    dao.find_similar_reminder.return_value = None
    return dao


@pytest.fixture
def service(mock_dao):
    return ReminderService(
        user_id="user123",
        character_id="char456",
        conversation_id="conv789",
        base_timestamp=1704067200,
        session_state=None,
    )


class TestReminderServiceCreate:
    def test_create_scheduled_reminder(self, service, mock_dao):
        result = service.create(
            title="Test Meeting",
            trigger_time="明天下午3点",
            recurrence_type="none",
            recurrence_interval=1,
        )

        assert result["ok"] is True
        assert result["status"] == "created"
        assert "Test Meeting" in result["message"]
        assert mock_dao.create_reminder.called

    def test_create_inbox_task_no_time(self, service, mock_dao):
        result = service.create(
            title="Buy groceries",
            trigger_time=None,
            recurrence_type="none",
            recurrence_interval=1,
        )

        assert result["ok"] is True
        assert result["status"] == "created"
        assert "收集箱" in result["message"]

    def test_create_missing_title(self, service):
        result = service.create(
            title=None,
            trigger_time="明天",
        )

        assert result["ok"] is False
        assert "title" in result.get("error", "").lower() or "事项" in result.get("error", "")

    def test_create_duplicate_detected(self, service, mock_dao):
        mock_dao.find_similar_reminder.return_value = {
            "reminder_id": "existing-123",
            "title": "Test Meeting",
            "next_trigger_time": 1704067200,
        }

        result = service.create(
            title="Test Meeting",
            trigger_time="明天下午3点",
        )

        assert result["ok"] is True
        assert result["status"] == "duplicate"

    def test_create_frequency_limit_violation(self, service, mock_dao):
        result = service.create(
            title="Too Frequent",
            trigger_time="30分钟后",
            recurrence_type="interval",
            recurrence_interval=30,  # Below 60 minute limit
        )

        assert result["ok"] is False
        assert "间隔" in result.get("error", "")

    def test_create_with_recurrence(self, service, mock_dao):
        result = service.create(
            title="Daily Standup",
            trigger_time="每天早上9点",
            recurrence_type="daily",
            recurrence_interval=1,
        )

        assert result["ok"] is True
        assert "每天" in result["message"]
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/reminder/test_service.py::TestReminderServiceCreate -v
```

Expected: `ModuleNotFoundError: No module named 'agent.agno_agent.tools.reminder.service'`

**Step 3: Implement ReminderService.create**

```python
# agent/agno_agent/tools/reminder/service.py
"""Business logic layer for reminder operations."""

import logging
import time
import uuid
from typing import Optional

from dao.reminder_dao import ReminderDAO
from .parser import TimeParser
from .validator import ReminderValidator
from .formatter import ReminderFormatter

logger = logging.getLogger(__name__)


class ReminderService:
    """
    Business logic orchestration for reminder operations.

    This layer coordinates validation, parsing, persistence, and formatting
    for all reminder operations.
    """

    def __init__(
        self,
        user_id: str,
        character_id: str,
        conversation_id: str,
        base_timestamp: Optional[int] = None,
        session_state: Optional[dict] = None,
    ):
        """
        Initialize ReminderService.

        Args:
            user_id: User ID
            character_id: Character ID
            conversation_id: Conversation ID
            base_timestamp: Base timestamp for relative time calculations
            session_state: Session state for side-effect guards
        """
        self.user_id = user_id
        self.character_id = character_id
        self.conversation_id = conversation_id
        self.base_timestamp = base_timestamp
        self.session_state = session_state

        # Initialize dependencies
        self.dao = ReminderDAO()
        self.parser = TimeParser(base_timestamp)
        self.validator = ReminderValidator(self.dao, user_id)
        self.formatter = ReminderFormatter()

    def create(
        self,
        title: Optional[str],
        trigger_time: Optional[str],
        action_template: Optional[str] = None,
        recurrence_type: str = "none",
        recurrence_interval: int = 1,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        period_days: Optional[str] = None,
    ) -> dict:
        """
        Create a new reminder.

        Args:
            title: Reminder title (required)
            trigger_time: Trigger time string (optional for inbox tasks)
            action_template: Custom message template
            recurrence_type: Type of recurrence
            recurrence_interval: Recurrence interval
            period_start: Period start time "HH:MM"
            period_end: Period end time "HH:MM"
            period_days: Period active days "1,2,3,4,5"

        Returns:
            Operation result dict
        """
        # Step 1: Validate required fields
        if error := self.validator.check_required_fields(title, trigger_time):
            return error

        # Step 2: Parse time period config (if any)
        has_period = bool(period_start and period_end)
        time_period_config = None
        if has_period:
            time_period_config = self.parser.parse_period_config(
                period_start, period_end, period_days
            )

        # Step 3: Check frequency limits (for recurring reminders)
        if error := self.validator.check_frequency_limit(
            recurrence_type, recurrence_interval, has_period
        ):
            return error

        # Step 4: Parse trigger time (skip for inbox tasks)
        parsed_timestamp = None
        if trigger_time:
            parsed_timestamp = self.parser.parse(trigger_time)
            if not parsed_timestamp:
                return self.formatter.error(f"无法解析时间: {trigger_time}")

        # Step 5: Check for duplicates (only for timed reminders)
        if parsed_timestamp:
            duplicate = self.validator.check_duplicate(
                title, parsed_timestamp
            )
            if duplicate and duplicate.get("status") == "duplicate":
                return duplicate

        # Step 6: Build reminder document
        reminder_doc = self._build_reminder_doc(
            title=title,
            trigger_time=trigger_time,
            timestamp=parsed_timestamp,
            action_template=action_template,
            recurrence_type=recurrence_type,
            recurrence_interval=recurrence_interval,
            time_period_config=time_period_config,
        )

        # Step 7: Persist to database
        try:
            inserted_id = self.dao.create_reminder(reminder_doc)
            if not inserted_id:
                return self.formatter.error("创建提醒失败：数据库写入失败")
        except Exception as e:
            logger.error(f"Failed to create reminder: {e}")
            return self.formatter.error(f"创建提醒失败: {str(e)}")

        # Step 8: Return formatted result
        return self.formatter.create_success(reminder_doc)

    def _build_reminder_doc(
        self,
        title: str,
        trigger_time: Optional[str],
        timestamp: Optional[int],
        action_template: Optional[str],
        recurrence_type: str,
        recurrence_interval: int,
        time_period_config: Optional[dict],
    ) -> dict:
        """Build reminder document for database insertion."""
        current_time = int(time.time())
        reminder_id = str(uuid.uuid4())

        doc = {
            "user_id": self.user_id,
            "reminder_id": reminder_id,
            "title": title,
            "action_template": action_template or f"记得{title}",
            "next_trigger_time": timestamp,
            "time_original": trigger_time,
            "timezone": "Asia/Shanghai",
            "recurrence": {
                "enabled": recurrence_type != "none",
                "type": recurrence_type if recurrence_type != "none" else None,
                "interval": recurrence_interval,
            },
            "status": "active",
            "created_at": current_time,
            "updated_at": current_time,
            "triggered_count": 0,
            "list_id": "inbox" if timestamp is None else None,
        }

        # Set default max count for recurring (non-period) reminders
        if recurrence_type != "none" and not time_period_config:
            doc["recurrence"]["max_count"] = ReminderValidator.DEFAULT_MAX_TRIGGERS

        # Add time period config
        if time_period_config:
            doc["time_period"] = time_period_config
            doc["period_state"] = {
                "today_first_trigger": None,
                "today_last_trigger": None,
                "today_trigger_count": 0,
            }

        # Add optional fields
        if self.conversation_id:
            doc["conversation_id"] = self.conversation_id
        if self.character_id:
            doc["character_id"] = self.character_id

        return doc

    def close(self):
        """Close database connection."""
        self.dao.close()
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/reminder/test_service.py::TestReminderServiceCreate -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add agent/agno_agent/tools/reminder/service.py tests/unit/reminder/test_service.py
git commit -m "feat(tools): implement ReminderService.create with tests"
```

---

## Task 7: Implement ReminderService - Update, Delete, Complete, Filter

**Files:**
- Modify: `agent/agno_agent/tools/reminder/service.py`
- Modify: `tests/unit/reminder/test_service.py`

**Step 1: Write failing tests for remaining operations**

```python
# Add to tests/unit/reminder/test_service.py

class TestReminderServiceUpdate:
    def test_update_by_keyword(self, service, mock_dao):
        mock_dao.update_reminders_by_keyword.return_value = 1
        mock_dao.find_reminders_by_keyword.return_value = [
            {
                "reminder_id": "r1",
                "title": "Meeting",
                "next_trigger_time": 1704067200,
            }
        ]

        result = service.update(
            keyword="Meeting",
            new_title="Team Meeting",
        )

        assert result["ok"] is True
        assert "更新" in result["message"]

    def test_update_not_found(self, service, mock_dao):
        mock_dao.update_reminders_by_keyword.return_value = 0

        result = service.update(
            keyword="NonExistent",
            new_title="New Title",
        )

        assert result["ok"] is False


class TestReminderServiceDelete:
    def test_delete_with_guard_allow(self, service, mock_dao):
        mock_dao.filter_reminders.return_value = []
        mock_dao.delete_reminders_by_keyword.return_value = 1

        result = service.delete(
            keyword="TestTask",
            session_state={
                "conversation": {
                    "conversation_info": {
                        "input_messages": [{"message": "删除TestTask"}]
                    }
                }
            },
        )

        assert result["ok"] is True

    def test_delete_with_guard_block(self, service, mock_dao):
        mock_dao.filter_reminders.return_value = [
            {"title": "TaskA", "reminder_id": "a1"}
        ]
        mock_dao.delete_reminders_by_keyword.return_value = 0

        result = service.delete(
            keyword=None,
            session_state={
                "conversation": {
                    "conversation_info": {
                        "input_messages": [{"message": "删除提醒"}]
                    }
                }
            },
        )

        assert result["ok"] is False
        assert result.get("needs_confirmation") is True


class TestReminderServiceComplete:
    def test_complete_with_guard_allow(self, service, mock_dao):
        mock_dao.filter_reminders.return_value = []
        mock_dao.complete_reminders_by_keyword.return_value = 1

        result = service.complete(
            keyword="BuyMilk",
            session_state={
                "conversation": {
                    "conversation_info": {
                        "input_messages": [{"message": "完成BuyMilk"}]
                    }
                }
            },
        )

        assert result["ok"] is True


class TestReminderServiceFilter:
    def test_filter_active_reminders(self, service, mock_dao):
        mock_dao.filter_reminders.return_value = [
            {"reminder_id": "r1", "title": "Task1", "status": "active",
             "next_trigger_time": 1704067200, "recurrence": {}, "created_at": 1704067200,
             "triggered_count": 0},
        ]

        result = service.filter(
            status='["active"]',
            reminder_type=None,
            keyword=None,
        )

        assert result["ok"] is True
        assert result["count"] == 1

    def test_filter_empty(self, service, mock_dao):
        mock_dao.filter_reminders.return_value = []

        result = service.filter()

        assert result["ok"] is True
        assert result["count"] == 0
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/reminder/test_service.py::TestReminderServiceUpdate -v
pytest tests/unit/reminder/test_service.py::TestReminderServiceDelete -v
pytest tests/unit/reminder/test_service.py::TestReminderServiceComplete -v
pytest tests/unit/reminder/test_service.py::TestReminderServiceFilter -v
```

Expected: Tests fail (methods not implemented)

**Step 3: Implement remaining service methods**

Add to `ReminderService` class:

```python
    def update(
        self,
        keyword: str,
        new_title: Optional[str] = None,
        new_trigger_time: Optional[str] = None,
        recurrence_type: str = "none",
        recurrence_interval: int = 1,
    ) -> dict:
        """
        Update existing reminder by keyword matching.

        Args:
            keyword: Keyword to match reminder title
            new_title: New title (optional)
            new_trigger_time: New trigger time (optional)
            recurrence_type: New recurrence type
            recurrence_interval: New recurrence interval

        Returns:
            Operation result dict
        """
        if not keyword:
            return self.formatter.error("更新提醒需要提供关键字")

        # Parse new time if provided
        parsed_time = None
        if new_trigger_time:
            parsed_time = self.parser.parse(new_trigger_time)
            if not parsed_time:
                return self.formatter.error(f"无法解析时间: {new_trigger_time}")

        # Build update data
        import time
        update_data = {"updated_at": int(time.time())}

        if new_title:
            update_data["title"] = new_title
        if parsed_time:
            update_data["next_trigger_time"] = parsed_time
        if recurrence_type != "none":
            update_data["recurrence"] = {
                "enabled": True,
                "type": recurrence_type,
                "interval": recurrence_interval,
            }

        # Execute update
        try:
            count = self.dao.update_reminders_by_keyword(
                self.user_id, keyword, update_data
            )
            if count == 0:
                return self.formatter.error(f"未找到包含「{keyword}」的提醒")
        except Exception as e:
            logger.error(f"Failed to update reminder: {e}")
            return self.formatter.error(f"更新提醒失败: {str(e)}")

        # Get updated reminder for response
        reminders = self.dao.find_reminders_by_keyword(self.user_id, keyword)
        if reminders:
            return self.formatter.update_success(reminders[0], update_data)

        return self.formatter.update_success(
            {"reminder_id": None, "title": keyword}, update_data
        )

    def delete(
        self,
        keyword: str,
        session_state: Optional[dict] = None,
    ) -> dict:
        """
        Delete reminder(s) by keyword matching.

        Args:
            keyword: Keyword to match ("*" for all)
            session_state: Session state for guard check

        Returns:
            Operation result dict
        """
        # Side-effect guard check
        guard = self.validator.guard_side_effect(
            action="delete",
            keyword=keyword,
            session_state=session_state or self.session_state,
        )

        if not guard.get("allowed"):
            return self.formatter.guarded_response(guard)

        # Use resolved keyword if guard provided one
        resolved_keyword = guard.get("resolved_keyword") or keyword

        try:
            if resolved_keyword == "*":
                count = self.dao.delete_all_by_user(self.user_id)
            else:
                count = self.dao.delete_reminders_by_keyword(
                    self.user_id, resolved_keyword
                )

            if count == 0:
                return self.formatter.error(f"未找到包含「{resolved_keyword}」的提醒")

        except Exception as e:
            logger.error(f"Failed to delete reminder: {e}")
            return self.formatter.error(f"删除提醒失败: {str(e)}")

        return self.formatter.delete_success(count, resolved_keyword)

    def complete(
        self,
        keyword: str,
        session_state: Optional[dict] = None,
    ) -> dict:
        """
        Complete reminder(s) by keyword matching.

        Args:
            keyword: Keyword to match reminder title
            session_state: Session state for guard check

        Returns:
            Operation result dict
        """
        # Side-effect guard check
        guard = self.validator.guard_side_effect(
            action="complete",
            keyword=keyword,
            session_state=session_state or self.session_state,
        )

        if not guard.get("allowed"):
            return self.formatter.guarded_response(guard)

        # Use resolved keyword if guard provided one
        resolved_keyword = guard.get("resolved_keyword") or keyword

        try:
            count = self.dao.complete_reminders_by_keyword(self.user_id, resolved_keyword)

            if count == 0:
                return self.formatter.error(f"未找到包含「{resolved_keyword}」的提醒")

        except Exception as e:
            logger.error(f"Failed to complete reminder: {e}")
            return self.formatter.error(f"完成提醒失败: {str(e)}")

        return self.formatter.complete_success(count, resolved_keyword)

    def filter(
        self,
        status: Optional[str] = None,
        reminder_type: Optional[str] = None,
        keyword: Optional[str] = None,
        trigger_after: Optional[str] = None,
        trigger_before: Optional[str] = None,
    ) -> dict:
        """
        Filter/query reminders with flexible criteria.

        Args:
            status: JSON string of status list like '["active", "triggered"]'
            reminder_type: "one_time" or "recurring"
            keyword: Keyword to search in titles
            trigger_after: Time range start
            trigger_before: Time range end

        Returns:
            Filter result dict with formatted reminders
        """
        import json

        # Parse status parameter
        status_list = None
        if status:
            try:
                status_list = json.loads(status)
                if not isinstance(status_list, list):
                    status_list = [status_list]
            except json.JSONDecodeError:
                status_list = [status]

        # Parse time ranges
        trigger_after_ts = None
        trigger_before_ts = None

        if trigger_after:
            trigger_after_ts = self.parser.parse(trigger_after)
        if trigger_before:
            trigger_before_ts = self.parser.parse(trigger_before)

        try:
            reminders = self.dao.filter_reminders(
                user_id=self.user_id,
                status_list=status_list,
                reminder_type=reminder_type,
                keyword=keyword,
                trigger_after=trigger_after_ts,
                trigger_before=trigger_before_ts,
            )
        except Exception as e:
            logger.error(f"Failed to filter reminders: {e}")
            return self.formatter.error(f"查询提醒失败: {str(e)}")

        return self.formatter.filter_result(reminders or [])
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/reminder/test_service.py::TestReminderServiceUpdate -v
pytest tests/unit/reminder/test_service.py::TestReminderServiceDelete -v
pytest tests/unit/reminder/test_service.py::TestReminderServiceComplete -v
pytest tests/unit/reminder/test_service.py::TestReminderServiceFilter -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add agent/agno_agent/tools/reminder/service.py tests/unit/reminder/test_service.py
git commit -m "feat(tools): implement ReminderService update/delete/complete/filter with tests"
```

---

## Task 8: Implement ReminderService - Batch Operations

**Files:**
- Modify: `agent/agno_agent/tools/reminder/service.py`
- Modify: `tests/unit/reminder/test_service.py`

**Step 1: Write failing tests for batch operations**

```python
# Add to tests/unit/reminder/test_service.py

class TestReminderServiceBatch:
    def test_batch_multiple_creates(self, service, mock_dao):
        operations_json = '[{"action":"create","title":"Task1","trigger_time":"明天"},{"action":"create","title":"Task2","trigger_time":"后天"}]'

        result = service.batch(operations_json)

        assert result["ok"] is True
        assert result["summary"]["total"] == 2
        assert result["summary"]["succeeded"] == 2

    def test_batch_mixed_operations(self, service, mock_dao):
        mock_dao.delete_reminders_by_keyword.return_value = 1
        operations_json = '[{"action":"delete","keyword":"Old"},{"action":"create","title":"New","trigger_time":"明天"}]'

        result = service.batch(operations_json)

        assert result["ok"] is True
        assert result["summary"]["total"] == 2

    def test_batch_invalid_json(self, service):
        result = service.batch("invalid json")

        assert result["ok"] is False
        assert "JSON" in result.get("error", "")

    def test_batch_with_failure(self, service, mock_dao):
        mock_dao.delete_reminders_by_keyword.return_value = 0  # Not found
        operations_json = '[{"action":"delete","keyword":"NonExistent"},{"action":"create","title":"New"}]'

        result = service.batch(operations_json)

        assert result["ok"] is True  # Batch overall succeeds even if individual ops fail
        assert result["summary"]["failed"] == 1
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/reminder/test_service.py::TestReminderServiceBatch -v
```

Expected: Tests fail (batch method not implemented)

**Step 3: Implement batch operation**

Add to `ReminderService` class:

```python
    def batch(self, operations_json: str) -> dict:
        """
        Execute multiple reminder operations in a single call.

        Args:
            operations_json: JSON string of operations to execute

        Returns:
            Batch operation summary dict
        """
        import json

        # Parse operations JSON
        try:
            operations = json.loads(operations_json)
            if not isinstance(operations, list):
                return self.formatter.error("operations 必须是数组")
        except json.JSONDecodeError as e:
            return self.formatter.error(f"无效的 JSON 格式: {str(e)}")

        results = []

        for op in operations:
            if not isinstance(op, dict):
                results.append({
                    "ok": False,
                    "action": "invalid",
                    "error": "操作必须是对象"
                })
                continue

            action = op.get("action")

            try:
                if action == "create":
                    result = self._batch_create(op)
                elif action == "update":
                    result = self._batch_update(op)
                elif action == "delete":
                    result = self._batch_delete(op)
                elif action == "complete":
                    result = self._batch_complete(op)
                else:
                    result = {
                        "ok": False,
                        "action": action,
                        "error": f"不支持的操作: {action}"
                    }
            except Exception as e:
                logger.error(f"Batch operation {action} failed: {e}")
                result = {
                    "ok": False,
                    "action": action,
                    "error": str(e)
                }

            results.append(result)

        return self.formatter.batch_summary(results)

    def _batch_create(self, op: dict) -> dict:
        """Handle create operation within batch."""
        result = self.create(
            title=op.get("title"),
            trigger_time=op.get("trigger_time"),
            recurrence_type=op.get("recurrence_type", "none"),
            recurrence_interval=op.get("recurrence_interval", 1),
            period_start=op.get("period_start"),
            period_end=op.get("period_end"),
            period_days=op.get("period_days"),
        )
        result["action"] = "create"
        return result

    def _batch_update(self, op: dict) -> dict:
        """Handle update operation within batch."""
        result = self.update(
            keyword=op.get("keyword"),
            new_title=op.get("new_title"),
            new_trigger_time=op.get("new_trigger_time"),
            recurrence_type=op.get("recurrence_type", "none"),
            recurrence_interval=op.get("recurrence_interval", 1),
        )
        result["action"] = "update"
        return result

    def _batch_delete(self, op: dict) -> dict:
        """Handle delete operation within batch (skip guard)."""
        keyword = op.get("keyword")

        try:
            if keyword == "*":
                count = self.dao.delete_all_by_user(self.user_id)
            else:
                count = self.dao.delete_reminders_by_keyword(self.user_id, keyword)

            result = self.formatter.delete_success(count, keyword)
            result["action"] = "delete"
            return result
        except Exception as e:
            return {
                "ok": False,
                "action": "delete",
                "error": str(e)
            }

    def _batch_complete(self, op: dict) -> dict:
        """Handle complete operation within batch (skip guard)."""
        keyword = op.get("keyword")

        try:
            count = self.dao.complete_reminders_by_keyword(self.user_id, keyword)
            result = self.formatter.complete_success(count, keyword)
            result["action"] = "complete"
            return result
        except Exception as e:
            return {
                "ok": False,
                "action": "complete",
                "error": str(e)
            }
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/reminder/test_service.py::TestReminderServiceBatch -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add agent/agno_agent/tools/reminder/service.py tests/unit/reminder/test_service.py
git commit -m "feat(tools): implement ReminderService.batch with tests"
```

---

## Task 9: Refactor reminder_tools.py to Use Service Layer

**Files:**
- Modify: `agent/agno_agent/tools/reminder_tools.py`

**Step 1: Read the existing tool for reference**

```bash
head -100 agent/agno_agent/tools/reminder_tools.py
```

**Step 2: Backup and rewrite reminder_tools.py**

Create the new simplified version:

```python
# agent/agno_agent/tools/reminder_tools.py
# -*- coding: utf-8 -*-
"""
Reminder Tool for Agno Agent

This tool provides reminder management capabilities:
- Create new reminders
- Update existing reminders
- Delete reminders
- List/filter reminders
- Complete reminders
- Batch operations

Supports:
- Relative time parsing (e.g., "30分钟后", "明天")
- Absolute time parsing
- Recurrence types: daily, weekly, monthly, yearly
- GTD inbox tasks (no time)
- Time period reminders

Requirements: 3.2, 3.3, 3.4

Refactored: Uses layered architecture with service layer
"""

import contextvars
import logging
from typing import Optional

from agno.tools import tool
from .reminder import ReminderService

logger = logging.getLogger(__name__)

# ========== contextvars Session State Management ==========
# Preserves async isolation for multi-user concurrent processing

_context_session_state: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "session_state", default={}
)
_context_session_state_ref: contextvars.ContextVar[Optional[dict]] = (
    contextvars.ContextVar("session_state_ref", default=None)
)
_context_session_operations: contextvars.ContextVar[list] = contextvars.ContextVar(
    "session_operations", default=[]
)


def set_reminder_session_state(session_state: dict):
    """
    Set session state for current coroutine.

    Uses contextvars to ensure isolation between different async contexts,
    preventing cross-user data contamination in asyncio concurrent processing.

    Args:
        session_state: Session state dict with user, conversation, etc.
    """
    _context_session_state.set(session_state or {})
    _context_session_state_ref.set(session_state or None)
    _context_session_operations.set([])

    user_id = str(session_state.get("user", {}).get("_id", "")) if session_state else ""
    logger.debug(f"set_reminder_session_state: user_id={user_id}")


def _get_current_session_state() -> dict:
    """Get current coroutine's session_state from contextvars."""
    return _context_session_state.get()


def _get_session_operations() -> list:
    """Get current coroutine's operations record."""
    ops = _context_session_operations.get()
    if ops is None:
        ops = []
        _context_session_operations.set(ops)
    return ops


def _check_operation_allowed(action: str) -> tuple[bool, str]:
    """Check if operation is allowed (prevents circular calls)."""
    session_operations = _get_session_operations()

    if action == "batch":
        if session_operations:
            return False, "batch 操作必须是唯一的操作，不能与其他操作混用"
    elif "batch" in session_operations:
        return False, "已执行 batch 操作，不能再执行其他操作"

    if action in session_operations:
        return False, f"{action} 操作只能执行一次"

    session_operations.append(action)
    logger.debug(f"操作记录: {session_operations}")
    return True, ""


def _save_reminder_result_to_session(
    message: str,
    session_state: Optional[dict] = None,
    user_intent: Optional[str] = None,
    action_executed: Optional[str] = None,
    intent_fulfilled: bool = True,
    details: Optional[dict] = None,
):
    """Save reminder operation result to session_state for Agent context."""
    if session_state is None:
        session_state = _get_current_session_state()

    # Backward compatibility
    session_state["【提醒设置工具消息】"] = message

    # Structured context
    if user_intent is None:
        user_intent = "提醒操作"
    if action_executed is None:
        action_executed = "unknown"

    tool_execution_context = {
        "user_intent": user_intent,
        "action_executed": action_executed,
        "intent_fulfilled": intent_fulfilled,
        "result_summary": message,
    }
    if details:
        tool_execution_context["details"] = details

    session_state["tool_execution_context"] = tool_execution_context

    # Sync ref if exists
    session_state_ref = _context_session_state_ref.get()
    if session_state_ref is not None and session_state_ref is not session_state:
        session_state_ref["【提醒设置工具消息】"] = message
        session_state_ref["tool_execution_context"] = tool_execution_context

    logger.info(f"提醒结果已写入 session_state: {message}")


# ========== Tool Entry Point ==========

@tool(
    stop_after_tool_call=True,
    description="""提醒管理工具，用于创建、更新、删除、查询提醒.支持单次提醒、周期提醒和时间段提醒.

## 操作类型 (action)
- "create": 创建单个提醒
- "batch": 批量操作（推荐），一次调用执行多个操作（创建/更新/删除的任意组合）
- "update": 更新提醒（按关键字匹配）
- "delete": 删除提醒（按关键字匹配）
- "filter": 查询提醒（支持灵活的筛选组合）
- "complete": 完成提醒（按关键字匹配）

## 单个操作参数

### create 参数
- title: 提醒标题（必需），如"开会"、"喝水"
- trigger_time: 触发时间（可选），格式"xxxx年xx月xx日xx时xx分"或"30分钟后"。为 None 时创建无时间任务（存入 inbox）
- recurrence_type: 周期类型，可选值: "none"(默认)、"daily"、"weekly"、"monthly"、"interval"
- recurrence_interval: 周期间隔数，默认1（interval类型时单位为分钟）
- period_start/period_end: 时间段，格式 "HH:MM"
- period_days: 生效星期，格式 "1,2,3,4,5，6，7"

### 重复提醒频率限制（系统强制执行）
- 分钟级别（interval < 60分钟）的无限重复提醒：禁止创建（频率过高会导致服务被限制）
- 时间段提醒（设置了period_start/period_end）：最小间隔25分钟
- 小时级别以上的无限重复提醒：允许，但默认10次上限

### update 参数（按关键字匹配）
- keyword: 关键字，模糊匹配要修改的提醒标题（必需）
- new_title: 新标题（可选）
- new_trigger_time: 新触发时间（可选）

### delete 参数（按关键字匹配）
- keyword: 关键字，模糊匹配要删除的提醒标题（必需）
- 使用 "*" 作为 keyword 可删除所有提醒

### filter 参数（查询提醒，替代原 list 操作）
- status: 状态筛选，可选值列表: ["active", "triggered", "completed"]，默认 ["active"]
- reminder_type: 提醒类型，可选值: "one_time" | "recurring"
- keyword: 关键字搜索，模糊匹配 title
- trigger_after: 时间范围开始，格式"xxxx年xx月xx日xx时xx分"或"今天00:00"
- trigger_before: 时间范围结束，格式"xxxx年xx月xx日xx时xx分"或"今天23:59"

### complete 参数（完成提醒）
- keyword: 关键字，模糊匹配要完成的提醒标题（必需）

## 批量操作 (action="batch")-推荐用于复杂场景

当用户消息包含多个操作时使用，一次调用完成所有操作.

参数:
- operations: JSON字符串，包含操作列表.每个操作包含 action 和对应参数.

格式:
```
[
  {"action": "delete", "keyword": "泡衣服"},
  {"action": "create", "title": "喝水", "trigger_time": "2025年12月24日15时00分"},
  {"action": "update", "keyword": "开会", "new_trigger_time": "2025年12月25日10时00分"}
]
```

示例1："把泡衣服的提醒删掉，再帮我加一个喝水提醒"
→ action="batch", operations='[{"action":"delete","keyword":"泡衣服"},{"action":"create","title":"喝水","trigger_time":"..."}]'

示例2："帮我设置三个提醒：8点起床、12点吃饭、6点下班"
→ action="batch", operations='[{"action":"create","title":"起床","trigger_time":"..."},{"action":"create","title":"吃饭","trigger_time":"..."},{"action":"create","title":"下班","trigger_time":"..."}]'

示例3："删除游泳那个提醒，把开会改到明天，再加一个新提醒"
→ action="batch", operations='[{"action":"delete","keyword":"游泳"},{"action":"update","keyword":"开会","new_trigger_time":"..."},{"action":"create","title":"...","trigger_time":"..."}]'

注意: 时间格式必须是"xxxx年xx月xx日xx时xx分"，不支持"下午3点"等格式.
""",
)
def reminder_tool(
    action: Optional[str] = None,
    session_state: Optional[dict] = None,
    title: Optional[str] = None,
    trigger_time: Optional[str] = None,
    action_template: Optional[str] = None,
    keyword: Optional[str] = None,
    new_title: Optional[str] = None,
    new_trigger_time: Optional[str] = None,
    recurrence_type: str = "none",
    recurrence_interval: int = 1,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    period_days: Optional[str] = None,
    operations: Optional[str] = None,
    status: Optional[str] = None,
    reminder_type: Optional[str] = None,
    trigger_after: Optional[str] = None,
    trigger_before: Optional[str] = None,
    include_all: bool = False,
) -> dict:
    """
    Reminder management tool with keyword-based operations.

    This is the thin tool layer that dispatches to ReminderService.
    """
    # Use Agno-injected session_state, fallback to contextvars
    current_session_state = (
        session_state if session_state else _get_current_session_state()
    )
    if session_state:
        _context_session_state.set(session_state)

    # Handle nested action parameter (LLM sometimes passes this way)
    if isinstance(action, dict) and "action" in action:
        action = action["action"]

    # Handle missing action
    if action is None:
        error_message = "操作类型缺失，请指定 action 参数（create/batch/update/delete/filter/complete）"
        logger.error("reminder_tool: action 参数缺失，LLM 未正确传递")
        _save_reminder_result_to_session(
            f"提醒操作失败：{error_message}",
            user_intent="提醒操作",
            action_executed="unknown",
            intent_fulfilled=False,
            details={"error": "action_missing"},
        )
        return {
            "ok": False,
            "error": error_message,
        }

    # Validate action
    valid_actions = ("create", "batch", "update", "delete", "filter", "complete", "list")
    if action not in valid_actions:
        return {
            "ok": False,
            "error": f"不支持的操作类型: {action}，支持的操作: {valid_actions}",
        }

    # Check operation allowance (prevent circular calls)
    allowed, error_msg = _check_operation_allowed(action)
    if not allowed:
        logger.warning(f"操作被拒绝: action={action}, reason={error_msg}")
        _save_reminder_result_to_session(f"操作被拒绝：{error_msg}")
        return {"ok": False, "error": error_msg}

    # Extract context from session_state
    user_id = str(current_session_state.get("user", {}).get("_id", ""))
    character_id = str(current_session_state.get("character", {}).get("_id", ""))
    conversation_id = str(current_session_state.get("conversation", {}).get("_id", ""))
    message_timestamp = current_session_state.get("input_timestamp")

    if not user_id and action in ("create", "batch", "filter", "update", "delete", "complete", "list"):
        logger.warning("reminder_tool: user_id not found in session_state")
        return {"ok": False, "error": "无法获取用户信息，请稍后重试"}

    # Create service instance
    service = ReminderService(
        user_id=user_id,
        character_id=character_id,
        conversation_id=conversation_id,
        base_timestamp=message_timestamp,
        session_state=current_session_state,
    )

    try:
        result = None

        if action == "create":
            result = service.create(
                title=title,
                trigger_time=trigger_time,
                action_template=action_template,
                recurrence_type=recurrence_type,
                recurrence_interval=recurrence_interval,
                period_start=period_start,
                period_end=period_end,
                period_days=period_days,
            )

        elif action == "batch":
            result = service.batch(operations_json=operations)

        elif action == "update":
            result = service.update(
                keyword=keyword,
                new_title=new_title,
                new_trigger_time=new_trigger_time,
                recurrence_type=recurrence_type,
                recurrence_interval=recurrence_interval,
            )

        elif action == "delete":
            result = service.delete(
                keyword=keyword,
                session_state=current_session_state,
            )

        elif action == "filter":
            result = service.filter(
                status=status,
                reminder_type=reminder_type,
                keyword=keyword,
                trigger_after=trigger_after,
                trigger_before=trigger_before,
            )

        elif action == "complete":
            result = service.complete(
                keyword=keyword,
                session_state=current_session_state,
            )

        elif action == "list":
            # Backward compatibility: redirect to filter
            logger.warning("reminder_tool: 'list' action is deprecated, use 'filter' instead")
            result = service.filter(
                status='["active"]' if not include_all else None,
            )

        else:
            result = {"ok": False, "error": f"不支持的操作类型: {action}"}

        # Save result to session
        _save_result_to_session(action, result)

        return result

    except Exception as e:
        logger.error(f"Error in reminder_tool: {e}")
        _save_reminder_result_to_session(
            f"提醒操作失败：{str(e)}",
            user_intent="提醒操作",
            action_executed=action or "unknown",
            intent_fulfilled=False,
        )
        return {"ok": False, "error": str(e)}

    finally:
        service.close()


def _save_result_to_session(action: str, result: dict):
    """Save operation result to session with appropriate intent metadata."""
    intent_map = {
        "create": ("创建提醒", "create"),
        "batch": ("批量操作", "batch"),
        "update": ("更新提醒", "update"),
        "delete": ("删除提醒", "delete"),
        "filter": ("查询提醒", "filter"),
        "complete": ("完成提醒", "complete"),
        "list": ("查询提醒", "list"),
    }

    user_intent, action_executed = intent_map.get(action, ("提醒操作", "unknown"))
    intent_fulfilled = result.get("ok", False)

    _save_reminder_result_to_session(
        message=result.get("message", f"操作{'成功' if intent_fulfilled else '失败'}"),
        user_intent=user_intent,
        action_executed=action_executed,
        intent_fulfilled=intent_fulfilled,
        details={"status": result.get("status")} if intent_fulfilled else None,
    )
```

**Step 3: Run existing tests to verify compatibility**

```bash
pytest tests/unit/test_reminder_tools_* -v
pytest tests/unit/test_reminder_* -v
```

Expected: All existing tests still PASS (behavior preserved)

**Step 4: Commit**

```bash
git add agent/agno_agent/tools/reminder_tools.py
git commit -m "refactor(tools): rewrite reminder_tools.py to use service layer"
```

---

## Task 10: Final Integration Testing and Cleanup

**Files:**
- Test: All reminder-related tests
- Modify: Any discovered issues

**Step 1: Run full test suite for reminder functionality**

```bash
# Unit tests
pytest tests/unit/reminder/ -v
pytest tests/unit/test_reminder_*.py -v

# Integration tests (if MongoDB available)
pytest tests/integration/test_reminder*.py -v
```

Expected: All tests PASS

**Step 2: Check for any remaining old helper functions**

```bash
# Search for any remaining direct references to old internal functions
grep -r "_create_reminder\|_batch_operations\|_update_reminder_by_keyword" agent/ tests/ --include="*.py"
```

If any found, update them to use the new service layer

**Step 3: Verify imports are clean**

```bash
python -c "from agent.agno_agent.tools.reminder_tools import reminder_tool; print('Import OK')"
python -c "from agent.agno_agent.tools.reminder import ReminderService; print('Import OK')"
```

**Step 4: Format code**

```bash
black agent/agno_agent/tools/reminder/ agent/agno_agent/tools/reminder_tools.py
isort agent/agno_agent/tools/reminder/ agent/agno_agent/tools/reminder_tools.py
```

**Step 5: Final commit**

```bash
git add -A
git commit -m "refactor(tools): complete reminder_tools refactoring

- Created layered architecture: service/parser/validator/formatter
- Preserved all existing behavior and LLM interface
- contextvars async isolation maintained
- All tests passing
- Reduced main file from ~2900 lines to ~350 lines"
```

---

## Task 11: Update Documentation

**Files:**
- Create: `docs/architecture/reminder-tools-refactoring.md`

**Step 1: Create architecture documentation**

```markdown
# Reminder Tools Architecture

## Overview

The reminder tool was refactored from a monolithic 2900-line file into a layered architecture for better maintainability.

## Architecture

```
agent/agno_agent/tools/
├── reminder_tools.py          # Thin @tool entry point (~350 lines)
└── reminder/                   # Business logic modules
    ├── __init__.py
    ├── service.py             # Orchestration layer (~500 lines)
    ├── parser.py              # Time parsing (~150 lines)
    ├── validator.py           # Validation rules (~250 lines)
    └── formatter.py           # Response formatting (~200 lines)
```

## Layer Responsibilities

### Tool Layer (reminder_tools.py)
- @tool decorator with LLM description
- contextvars session state management
- Parameter adaptation
- Action routing
- Session result writing

### Service Layer (service.py)
- Business logic orchestration
- Coordinates parser, validator, formatter, DAO
- Implements all CRUD operations
- Batch operation handling

### Parser Module (parser.py)
- Time parsing (relative/absolute)
- Time formatting (friendly/with-date)
- Period configuration parsing

### Validator Module (validator.py)
- Required field validation
- Frequency limit checking
- Duplicate detection
- Side-effect guards (delete/complete protection)
- Operation allowance checking

### Formatter Module (formatter.py)
- Success message building
- Error message formatting
- List/result formatting
- Batch summary generation

## Key Design Decisions

1. **Single Tool Entry**: Kept single @tool for LLM simplicity
2. **Async Isolation**: Preserved contextvars for multi-user safety
3. **Dependency Injection**: Service receives DAO, not hardcoded
4. **Pure Functions**: Parser/Validator/Formatter are stateless where possible
5. **Backward Compatibility**: All existing behavior preserved

## Usage

```python
from agent.agno_agent.tools.reminder import ReminderService

# Service is used internally by tool
service = ReminderService(
    user_id="user123",
    character_id="char456",
    conversation_id="conv789",
    base_timestamp=int(time.time()),
    session_state=session_state,
)

result = service.create(
    title="Meeting",
    trigger_time="明天下午3点",
)

service.close()  # Always close to release DAO connection
```

## Testing

- `tests/unit/reminder/` - Module-specific tests
- `tests/unit/test_reminder_*.py` - Integration-like unit tests
- All tests use mocks for MongoDB
"""
```

**Step 2: Commit documentation**

```bash
git add docs/architecture/reminder-tools-refactoring.md
git commit -m "docs: add reminder tools refactoring architecture documentation"
```

---

## Verification Steps

After completing all tasks:

1. **Code Coverage**: Run coverage report
   ```bash
   pytest --cov=agent/agno_agent/tools/reminder --cov=agent/agno_agent/tools/reminder_tools --cov-report=html
   ```
   Target: >70% coverage

2. **Import Check**: Verify all imports work
   ```bash
   python -c "from agent.agno_agent.tools import reminder_tools; from agent.agno_agent.tools.reminder import *"
   ```

3. **File Size Check**: Verify reduction
   ```bash
   wc -l agent/agno_agent/tools/reminder_tools.py
   ```
   Should be ~350 lines (down from ~2900)

4. **Behavior Verification**: Run any existing integration tests
   ```bash
   pytest -m "integration and reminder" -v
   ```

---

**End of Implementation Plan**
