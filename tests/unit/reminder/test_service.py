# -*- coding: utf-8 -*-
"""
Unit tests for ReminderService module.

Tests the ReminderService class which orchestrates the reminder management
operations using DAO, parser, validator, and formatter.
"""

import json
from unittest.mock import Mock

import pytest

from agent.agno_agent.tools.reminder.service import ReminderService

# ============ Fixtures ============


@pytest.fixture
def mock_dao():
    """Mock ReminderDAO instance."""
    dao = Mock()
    dao.create_reminder.return_value = "mock_reminder_id_123"
    dao.find_similar_reminder.return_value = None
    return dao


@pytest.fixture
def service(mock_dao):
    """Create a ReminderService instance with mocked dependencies."""
    service = ReminderService(
        user_id="test_user_123",
        character_id="test_char_456",
        conversation_id="test_conv_789",
        base_timestamp=1738289400,  # 2025-01-31 10:10:00 UTC
        session_state=None,
        dao=mock_dao,
    )
    yield service
    # Cleanup
    try:
        service.close()
    except Exception:
        pass


@pytest.fixture
def service_with_duplicate(mock_dao):
    """Create a service with mock that returns an existing duplicate."""
    mock_dao.find_similar_reminder.return_value = {
        "reminder_id": "existing_123",
        "title": "开会",
        "next_trigger_time": 1738289400,
    }
    service = ReminderService(
        user_id="user123",
        character_id="char456",
        conversation_id="conv789",
        base_timestamp=1738289400,
        session_state=None,
        dao=mock_dao,
    )
    yield service
    try:
        service.close()
    except Exception:
        pass


# ============ Test Create Scheduled Reminder ============


class TestCreateScheduledReminder:
    """Test creating a scheduled reminder with trigger time."""

    def test_create_scheduled_reminder_success(self, service, mock_dao):
        """Test successful creation of a scheduled reminder."""
        result = service.create(
            title="开会",
            trigger_time="明天9点",
            recurrence_type=None,
            recurrence_interval=None,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True
        assert result["status"] == "created"
        assert "reminder_id" in result
        assert "已创建提醒" in result["message"]
        mock_dao.create_reminder.assert_called_once()

        # Verify the reminder document structure
        call_args = mock_dao.create_reminder.call_args
        reminder_doc = call_args[0][0]

        assert reminder_doc["user_id"] == "test_user_123"
        assert reminder_doc["character_id"] == "test_char_456"
        assert reminder_doc["conversation_id"] == "test_conv_789"
        assert reminder_doc["title"] == "开会"
        assert reminder_doc["status"] == "active"
        assert reminder_doc["list_id"] != "inbox"  # Should not be inbox
        assert reminder_doc["next_trigger_time"] is not None

    def test_create_scheduled_reminder_with_parsed_time(self, service, mock_dao):
        """Test creating reminder with specific time parsing."""
        result = service.create(
            title="吃药",
            trigger_time="30分钟后",
            recurrence_type=None,
            recurrence_interval=None,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True
        call_args = mock_dao.create_reminder.call_args
        reminder_doc = call_args[0][0]

        # Check that time was parsed correctly
        assert reminder_doc["next_trigger_time"] == 1738289400 + 1800  # 30 minutes


# ============ Test Create Inbox Task (No Time) ============


class TestCreateInboxTask:
    """Test creating inbox tasks without trigger time."""

    def test_create_inbox_task_no_time(self, service, mock_dao):
        """Test creating an inbox task without trigger time."""
        result = service.create(
            title="买牛奶",
            trigger_time=None,
            recurrence_type=None,
            recurrence_interval=None,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True
        assert result["status"] == "created"

        call_args = mock_dao.create_reminder.call_args
        reminder_doc = call_args[0][0]

        # Inbox task should have list_id="inbox" and no trigger_time
        assert reminder_doc["list_id"] == "inbox"
        assert reminder_doc["next_trigger_time"] is None

    def test_create_inbox_task_empty_trigger_time(self, service, mock_dao):
        """Test creating inbox task with empty trigger_time string."""
        result = service.create(
            title="发邮件",
            trigger_time="",
            recurrence_type=None,
            recurrence_interval=None,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True

        call_args = mock_dao.create_reminder.call_args
        reminder_doc = call_args[0][0]

        # Empty string should be treated as no time
        assert reminder_doc["list_id"] == "inbox"
        assert reminder_doc["next_trigger_time"] is None


# ============ Test Missing Title ============


class TestCreateMissingTitle:
    """Test validation errors when title is missing."""

    def test_create_missing_title_none(self, service, mock_dao):
        """Test validation fails when title is None."""
        result = service.create(
            title=None,
            trigger_time="明天9点",
            recurrence_type=None,
            recurrence_interval=None,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is False
        assert "error" in result
        assert "提醒内容" in result["error"] or "不能为空" in result["error"]
        mock_dao.create_reminder.assert_not_called()

    def test_create_missing_title_empty(self, service, mock_dao):
        """Test validation fails when title is empty string."""
        result = service.create(
            title="",
            trigger_time="明天9点",
            recurrence_type=None,
            recurrence_interval=None,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is False
        mock_dao.create_reminder.assert_not_called()

    def test_create_missing_title_whitespace(self, service, mock_dao):
        """Test validation fails when title is whitespace only."""
        result = service.create(
            title="   ",
            trigger_time="明天9点",
            recurrence_type=None,
            recurrence_interval=None,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is False
        mock_dao.create_reminder.assert_not_called()


# ============ Test Duplicate Detection ============


class TestCreateDuplicateDetected:
    """Test duplicate reminder detection."""

    def test_create_duplicate_detected(self, service_with_duplicate):
        """Test duplicate reminder is detected and rejected."""
        service = service_with_duplicate

        result = service.create(
            title="开会",
            trigger_time="明天9点",
            recurrence_type=None,
            recurrence_interval=None,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True
        assert result["status"] == "duplicate"
        assert result["existing_id"] == "existing_123"
        service.dao.create_reminder.assert_not_called()

    def test_create_no_duplicate_proceeds(self, service):
        """Test creation proceeds when no duplicate found."""
        service.dao.find_similar_reminder.return_value = None

        result = service.create(
            title="新提醒",
            trigger_time="明天9点",
            recurrence_type=None,
            recurrence_interval=None,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True
        assert result["status"] == "created"
        service.dao.create_reminder.assert_called_once()


# ============ Test Frequency Limit Violation ============


class TestCreateFrequencyLimitViolation:
    """Test frequency limit validation."""

    def test_create_frequency_limit_violation_interval_too_small(self, mock_dao):
        """Test interval type with frequency too low is rejected."""
        # Need to patch the validator to return an error
        service = ReminderService(
            user_id="user123",
            character_id="char456",
            conversation_id="conv789",
            base_timestamp=1738289400,
            session_state=None,
        )

        # Use the real validator's check
        result = service.create(
            title="频繁提醒",
            trigger_time="明天9点",
            recurrence_type="interval",
            recurrence_interval=10,  # Less than MIN_INTERVAL_INFINITE (60)
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is False
        assert "频率过高" in result["error"]
        mock_dao.create_reminder.assert_not_called()

    def test_create_frequency_limit_interval_ok(self, mock_dao):
        """Test interval type with acceptable frequency is allowed."""
        service = ReminderService(
            user_id="user123",
            character_id="char456",
            conversation_id="conv789",
            base_timestamp=1738289400,
            session_state=None,
        )

        result = service.create(
            title="每小时提醒",
            trigger_time="明天9点",
            recurrence_type="interval",
            recurrence_interval=60,  # Exactly MIN_INTERVAL_INFINITE
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True
        assert result["status"] == "created"

    def test_create_frequency_limit_period_too_small(self, mock_dao):
        """Test period reminder with frequency too low is rejected."""
        service = ReminderService(
            user_id="user123",
            character_id="char456",
            conversation_id="conv789",
            base_timestamp=1738289400,
            session_state=None,
        )

        result = service.create(
            title="时间段频繁提醒",
            trigger_time="明天9点",
            recurrence_type="interval",
            recurrence_interval=20,  # Less than MIN_INTERVAL_PERIOD (25)
            period_start="09:00",
            period_end="18:00",
            period_days="1,2,3,4,5",
        )

        assert result["ok"] is False
        assert "频率过高" in result["error"]
        assert "25分钟" in result["error"]
        mock_dao.create_reminder.assert_not_called()

    def test_create_frequency_limit_period_ok(self, mock_dao):
        """Test period reminder with acceptable frequency is allowed."""
        service = ReminderService(
            user_id="user123",
            character_id="char456",
            conversation_id="conv789",
            base_timestamp=1738289400,
            session_state=None,
        )

        result = service.create(
            title="工作时间提醒",
            trigger_time="明天9点",
            recurrence_type="interval",
            recurrence_interval=30,  # >= MIN_INTERVAL_PERIOD
            period_start="09:00",
            period_end="18:00",
            period_days="1,2,3,4,5",
        )

        assert result["ok"] is True
        assert result["status"] == "created"


# ============ Test Create With Recurrence ============


class TestCreateWithRecurrence:
    """Test creating reminders with recurrence configuration."""

    def test_create_daily_recurrence(self, service, mock_dao):
        """Test creating a daily recurring reminder."""
        result = service.create(
            title="每天喝水",
            trigger_time="每天9点",
            recurrence_type="daily",
            recurrence_interval=1,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True
        assert result["status"] == "created"

        call_args = mock_dao.create_reminder.call_args
        reminder_doc = call_args[0][0]

        assert reminder_doc["recurrence"]["enabled"] is True
        assert reminder_doc["recurrence"]["type"] == "daily"
        assert reminder_doc["recurrence"]["interval"] == 1

    def test_create_weekly_recurrence(self, service, mock_dao):
        """Test creating a weekly recurring reminder."""
        result = service.create(
            title="周会",
            trigger_time="周一10点",
            recurrence_type="weekly",
            recurrence_interval=1,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True

        call_args = mock_dao.create_reminder.call_args
        reminder_doc = call_args[0][0]

        assert reminder_doc["recurrence"]["enabled"] is True
        assert reminder_doc["recurrence"]["type"] == "weekly"

    def test_create_monthly_recurrence(self, service, mock_dao):
        """Test creating a monthly recurring reminder."""
        result = service.create(
            title="交房租",
            trigger_time="每月1号",
            recurrence_type="monthly",
            recurrence_interval=1,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True

        call_args = mock_dao.create_reminder.call_args
        reminder_doc = call_args[0][0]

        assert reminder_doc["recurrence"]["enabled"] is True
        assert reminder_doc["recurrence"]["type"] == "monthly"

    def test_create_interval_recurrence(self, service, mock_dao):
        """Test creating an interval recurring reminder."""
        result = service.create(
            title="休息提醒",
            trigger_time="明天9点",
            recurrence_type="interval",
            recurrence_interval=120,  # 2 hours
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True

        call_args = mock_dao.create_reminder.call_args
        reminder_doc = call_args[0][0]

        assert reminder_doc["recurrence"]["enabled"] is True
        assert reminder_doc["recurrence"]["type"] == "interval"
        assert reminder_doc["recurrence"]["interval"] == 120

    def test_create_with_time_period(self, service, mock_dao):
        """Test creating reminder with time period constraints."""
        result = service.create(
            title="工作喝水",
            trigger_time="明天9点",
            recurrence_type="interval",
            recurrence_interval=30,
            period_start="09:00",
            period_end="18:00",
            period_days="1,2,3,4,5",
        )

        assert result["ok"] is True

        call_args = mock_dao.create_reminder.call_args
        reminder_doc = call_args[0][0]

        # Check time period configuration
        assert reminder_doc["time_period"]["enabled"] is True
        assert reminder_doc["time_period"]["start_time"] == "09:00"
        assert reminder_doc["time_period"]["end_time"] == "18:00"
        assert reminder_doc["time_period"]["active_days"] == [1, 2, 3, 4, 5]
        assert reminder_doc["time_period"]["timezone"] == "Asia/Shanghai"

    def test_create_no_recurrence(self, service, mock_dao):
        """Test creating a one-time reminder without recurrence."""
        result = service.create(
            title="一次性提醒",
            trigger_time="明天9点",
            recurrence_type=None,
            recurrence_interval=None,
            period_start=None,
            period_end=None,
            period_days=None,
        )

        assert result["ok"] is True

        call_args = mock_dao.create_reminder.call_args
        reminder_doc = call_args[0][0]

        # No recurrence or recurrence disabled
        recurrence = reminder_doc.get("recurrence", {})
        assert (
            recurrence.get("enabled", True) is False or recurrence.get("type") == "none"
        )


# ============ Test Build Reminder Doc ============


class TestBuildReminderDoc:
    """Test _build_reminder_doc helper method."""

    def test_build_reminder_doc_with_all_fields(self, mock_dao):
        """Test building reminder document with all fields."""
        service = ReminderService(
            user_id="user123",
            character_id="char456",
            conversation_id="conv789",
            base_timestamp=1738289400,
            session_state=None,
        )

        doc = service._build_reminder_doc(
            title="完整提醒",
            trigger_time=1738375800,
            recurrence_type="daily",
            recurrence_interval=1,
            period_config={"enabled": True, "start_time": "09:00", "end_time": "18:00"},
        )

        assert doc["user_id"] == "user123"
        assert doc["character_id"] == "char456"
        assert doc["conversation_id"] == "conv789"
        assert doc["title"] == "完整提醒"
        assert doc["next_trigger_time"] == 1738375800
        assert doc["recurrence"]["enabled"] is True
        assert doc["recurrence"]["type"] == "daily"
        assert doc["time_period"]["enabled"] is True
        assert doc["status"] == "active"
        assert "reminder_id" in doc
        assert "created_at" in doc
        assert "updated_at" in doc

    def test_build_reminder_doc_inbox_task(self, mock_dao):
        """Test building inbox task document (no trigger time)."""
        service = ReminderService(
            user_id="user123",
            character_id="char456",
            conversation_id="conv789",
            base_timestamp=1738289400,
            session_state=None,
        )

        doc = service._build_reminder_doc(
            title="收集箱任务",
            trigger_time=None,
            recurrence_type=None,
            recurrence_interval=None,
            period_config=None,
        )

        assert doc["list_id"] == "inbox"
        assert doc["next_trigger_time"] is None
        assert doc["recurrence"]["enabled"] is False


# ============ Test Close ============


class TestClose:
    """Test close method."""

    def test_close_calls_dao_close(self, mock_dao):
        """Test close method calls DAO close."""
        service = ReminderService(
            user_id="user123",
            character_id="char456",
            conversation_id="conv789",
            base_timestamp=1738289400,
            session_state=None,
        )
        service.dao = mock_dao

        service.close()

        mock_dao.close.assert_called_once()

    def test_close_handles_none_dao(self):
        """Test close handles None DAO gracefully."""
        service = ReminderService(
            user_id="user123",
            character_id="char456",
            conversation_id="conv789",
            base_timestamp=1738289400,
            session_state=None,
        )
        service.dao = None

        # Should not raise an exception
        service.close()


# ============ Test Init ============


class TestInit:
    """Test ReminderService initialization."""

    def test_init_creates_dependencies(self):
        """Test initialization creates all necessary dependencies."""
        service = ReminderService(
            user_id="user123",
            character_id="char456",
            conversation_id="conv789",
            base_timestamp=1738289400,
            session_state=None,
        )

        assert service.user_id == "user123"
        assert service.character_id == "char456"
        assert service.conversation_id == "conv789"
        assert service.base_timestamp == 1738289400
        assert service.session_state is None
        assert service.dao is not None
        assert service.parser is not None
        assert service.validator is not None
        assert service.formatter is not None

    def test_init_parser_has_base_timestamp(self):
        """Test parser is initialized with base_timestamp."""
        service = ReminderService(
            user_id="user123",
            character_id="char456",
            conversation_id="conv789",
            base_timestamp=1738289400,
            session_state=None,
        )

        assert service.parser.base_timestamp == 1738289400

    def test_init_validator_has_user_id(self):
        """Test validator is initialized with user_id."""
        service = ReminderService(
            user_id="user123",
            character_id="char456",
            conversation_id="conv789",
            base_timestamp=1738289400,
            session_state=None,
        )

        assert service.validator.user_id == "user123"


# ============ Test Default Max Triggers ============


class TestDefaultMaxTriggers:
    """Test DEFAULT_MAX_TRIGGERS constant usage."""

    def test_default_max_triggers_constant(self):
        """Test DEFAULT_MAX_TRIGGERS is accessible."""
        from agent.agno_agent.tools.reminder.validator import ReminderValidator

        assert ReminderValidator.DEFAULT_MAX_TRIGGERS == 10


# ============ Test Update Method ============


class TestReminderServiceUpdate:
    """Test update method of ReminderService."""

    def test_update_missing_keyword(self, service, mock_dao):
        """Test update fails when keyword is missing."""
        result = service.update(
            keyword=None,
            new_title="新标题",
            new_trigger_time="明天9点",
            recurrence_type=None,
            recurrence_interval=None,
        )

        assert result["ok"] is False
        assert "keyword" in result["error"].lower() or "关键字" in result["error"]
        mock_dao.update_reminders_by_keyword.assert_not_called()

    def test_update_missing_both_fields(self, service, mock_dao):
        """Test update fails when neither new_title nor new_trigger_time provided."""
        result = service.update(
            keyword="开会",
            new_title=None,
            new_trigger_time=None,
            recurrence_type=None,
            recurrence_interval=None,
        )

        assert result["ok"] is False
        assert "字段" in result["error"] or "new_title" in result["error"]
        mock_dao.update_reminders_by_keyword.assert_not_called()

    def test_update_new_title_only(self, service, mock_dao):
        """Test updating reminder title only."""
        mock_dao.update_reminders_by_keyword.return_value = (
            1,
            [{"reminder_id": "r1", "title": "新会议"}],
        )

        result = service.update(
            keyword="开会",
            new_title="新会议",
            new_trigger_time=None,
            recurrence_type=None,
            recurrence_interval=None,
        )

        assert result["ok"] is True
        assert "updated_count" in result
        mock_dao.update_reminders_by_keyword.assert_called_once()

    def test_update_with_new_trigger_time(self, service, mock_dao):
        """Test updating reminder with new trigger time."""
        mock_dao.update_reminders_by_keyword.return_value = (
            1,
            [{"reminder_id": "r1", "title": "开会"}],
        )

        result = service.update(
            keyword="开会",
            new_title=None,
            new_trigger_time="明天10点",
            recurrence_type=None,
            recurrence_interval=None,
        )

        assert result["ok"] is True

        # Check the update_data passed to DAO
        call_args = mock_dao.update_reminders_by_keyword.call_args
        update_data = call_args.kwargs["update_data"]

        assert "next_trigger_time" in update_data
        assert update_data["next_trigger_time"] is not None

    def test_update_with_recurrence(self, service, mock_dao):
        """Test updating reminder with recurrence."""
        mock_dao.update_reminders_by_keyword.return_value = (
            1,
            [{"reminder_id": "r1", "title": "每天开会"}],
        )

        result = service.update(
            keyword="开会",
            new_title=None,
            new_trigger_time=None,
            recurrence_type="daily",
            recurrence_interval=1,
        )

        assert result["ok"] is True

        # Check the update_data passed to DAO
        call_args = mock_dao.update_reminders_by_keyword.call_args
        update_data = call_args.kwargs["update_data"]

        assert "recurrence" in update_data
        assert update_data["recurrence"]["enabled"] is True
        assert update_data["recurrence"]["type"] == "daily"

    def test_update_no_reminders_found(self, service, mock_dao):
        """Test update when no reminders match keyword."""
        mock_dao.update_reminders_by_keyword.return_value = (0, [])

        result = service.update(
            keyword="不存在的提醒",
            new_title="新标题",
            new_trigger_time=None,
            recurrence_type=None,
            recurrence_interval=None,
        )

        assert result["ok"] is False
        assert "没有找到" in result["error"] or "已经完成" in result["error"]

    def test_update_invalid_trigger_time(self, service, mock_dao):
        """Test update with invalid trigger time string."""
        result = service.update(
            keyword="开会",
            new_title=None,
            new_trigger_time="invalid_time_format",
            recurrence_type=None,
            recurrence_interval=None,
        )

        assert result["ok"] is False
        assert "时间" in result["error"] or "解析" in result["error"]
        mock_dao.update_reminders_by_keyword.assert_not_called()


# ============ Test Delete Method ============


class TestReminderServiceDelete:
    """Test delete method of ReminderService."""

    def test_delete_missing_keyword(self, service, mock_dao):
        """Test delete fails when keyword is missing."""
        result = service.delete(keyword=None, session_state=None)

        assert result["ok"] is False
        assert "keyword" in result["error"].lower() or "关键字" in result["error"]
        mock_dao.delete_reminders_by_keyword.assert_not_called()

    def test_delete_missing_session_state(self, service, mock_dao):
        """Test delete fails when session_state is missing (side-effect guard)."""
        result = service.delete(keyword="开会", session_state=None)

        assert result["ok"] is False
        assert "无法获取" in result["error"] or "用户本轮原文" in result["error"]
        mock_dao.delete_reminders_by_keyword.assert_not_called()

    def test_delete_guard_rejects_keyword_not_in_text(self, service, mock_dao):
        """Test delete guard rejects when keyword not in user text."""
        # Mock session with user text that doesn't contain the keyword
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [{"message": "你好，有什么可以帮您的吗？"}]
                }
            }
        }

        # Mock no active reminders
        mock_dao.filter_reminders.return_value = []

        result = service.delete(keyword="开会", session_state=session_state)

        assert result["ok"] is False
        assert result.get("needs_confirmation") is True

    def test_delete_guard_allows_keyword_in_text(self, service, mock_dao):
        """Test delete guard allows when keyword is in user text."""
        # Mock session with user text containing the keyword
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [{"message": "请帮我把开会的提醒删掉"}]
                }
            }
        }

        mock_dao.delete_reminders_by_keyword.return_value = (1, [{"title": "开会"}])

        result = service.delete(keyword="开会", session_state=session_state)

        # Guard should allow, then DAO call succeeds
        assert result["ok"] is True
        mock_dao.delete_reminders_by_keyword.assert_called_once()

    def test_delete_single_reminder_success(self, service, mock_dao):
        """Test successful deletion of single reminder."""
        session_state = {
            "conversation": {
                "conversation_info": {"input_messages": [{"message": "删除开会的提醒"}]}
            }
        }

        mock_dao.delete_reminders_by_keyword.return_value = (
            1,
            [{"reminder_id": "r1", "title": "开会"}],
        )

        result = service.delete(keyword="开会", session_state=session_state)

        assert result["ok"] is True
        assert result["deleted_count"] == 1
        assert "删除成功" in result["message"]

    def test_delete_all_reminders(self, service, mock_dao):
        """Test deleting all reminders with keyword '*'."""
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [{"message": "请把全部提醒都删掉"}]
                }
            }
        }

        mock_dao.delete_all_by_user.return_value = 5

        result = service.delete(keyword="*", session_state=session_state)

        assert result["ok"] is True
        assert result["deleted_count"] == 5

    def test_delete_no_reminders_found(self, service, mock_dao):
        """Test delete when no reminders match."""
        session_state = {
            "conversation": {
                "conversation_info": {"input_messages": [{"message": "删除游泳的提醒"}]}
            }
        }

        mock_dao.delete_reminders_by_keyword.return_value = (0, [])

        result = service.delete(keyword="游泳", session_state=session_state)

        assert result["ok"] is False
        assert "没有找到" in result["error"] or "已经完成" in result["error"]


# ============ Test Complete Method ============


class TestReminderServiceComplete:
    """Test complete method of ReminderService."""

    def test_complete_missing_keyword(self, service, mock_dao):
        """Test complete fails when keyword is missing."""
        result = service.complete(keyword=None, session_state=None)

        assert result["ok"] is False
        assert "keyword" in result["error"].lower() or "关键字" in result["error"]
        mock_dao.complete_reminders_by_keyword.assert_not_called()

    def test_complete_missing_session_state(self, service, mock_dao):
        """Test complete fails when session_state is missing (side-effect guard)."""
        result = service.complete(keyword="开会", session_state=None)

        assert result["ok"] is False
        assert "无法获取" in result["error"] or "用户本轮原文" in result["error"]
        mock_dao.complete_reminders_by_keyword.assert_not_called()

    def test_complete_guard_rejects_keyword_not_in_text(self, service, mock_dao):
        """Test complete guard rejects when keyword not in user text."""
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [{"message": "你好，有什么可以帮您的吗？"}]
                }
            }
        }

        mock_dao.filter_reminders.return_value = []

        result = service.complete(keyword="开会", session_state=session_state)

        assert result["ok"] is False
        assert result.get("needs_confirmation") is True

    def test_complete_guard_allows_keyword_in_text(self, service, mock_dao):
        """Test complete guard allows when keyword is in user text."""
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [{"message": "我已经把开会的提醒完成了"}]
                }
            }
        }

        mock_dao.complete_reminders_by_keyword.return_value = (
            1,
            [{"title": "开会"}],
        )

        result = service.complete(keyword="开会", session_state=session_state)

        assert result["ok"] is True
        mock_dao.complete_reminders_by_keyword.assert_called_once()

    def test_complete_single_reminder_success(self, service, mock_dao):
        """Test successful completion of single reminder."""
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [{"message": "我完成了吃药的提醒"}]
                }
            }
        }

        mock_dao.complete_reminders_by_keyword.return_value = (
            1,
            [{"reminder_id": "r1", "title": "吃药"}],
        )

        result = service.complete(keyword="吃药", session_state=session_state)

        assert result["ok"] is True
        assert result["completed_count"] == 1
        assert "完成成功" in result["message"]

    def test_complete_no_reminders_found(self, service, mock_dao):
        """Test complete when no reminders match."""
        session_state = {
            "conversation": {
                "conversation_info": {"input_messages": [{"message": "我完成了游泳"}]}
            }
        }

        mock_dao.complete_reminders_by_keyword.return_value = (0, [])

        result = service.complete(keyword="游泳", session_state=session_state)

        assert result["ok"] is False
        assert "没有找到" in result["error"] or "已经完成" in result["error"]


# ============ Test Filter Method ============


class TestReminderServiceFilter:
    """Test filter method of ReminderService."""

    def test_filter_default_empty(self, service, mock_dao):
        """Test filter with no parameters returns active reminders."""
        mock_dao.filter_reminders.return_value = [
            {"title": "开会", "next_trigger_time": 1738289400},
        ]

        result = service.filter(
            status=None,
            reminder_type=None,
            keyword=None,
            trigger_after=None,
            trigger_before=None,
        )

        assert result["ok"] is True
        assert result["count"] == 1
        mock_dao.filter_reminders.assert_called_once()

    def test_filter_with_status_json(self, service, mock_dao):
        """Test filter with status as JSON string."""
        mock_dao.filter_reminders.return_value = []

        result = service.filter(
            status='["active", "triggered"]',
            reminder_type=None,
            keyword=None,
            trigger_after=None,
            trigger_before=None,
        )

        assert result["ok"] is True
        # Check that status was parsed correctly
        call_args = mock_dao.filter_reminders.call_args
        status_list = call_args.kwargs["status_list"]
        assert status_list == ["active", "triggered"]

    def test_filter_with_status_single(self, service, mock_dao):
        """Test filter with single status value."""
        mock_dao.filter_reminders.return_value = []

        result = service.filter(
            status="completed",
            reminder_type=None,
            keyword=None,
            trigger_after=None,
            trigger_before=None,
        )

        assert result["ok"] is True
        call_args = mock_dao.filter_reminders.call_args
        status_list = call_args.kwargs["status_list"]
        assert status_list == ["completed"]

    def test_filter_with_keyword(self, service, mock_dao):
        """Test filter with keyword search."""
        mock_dao.filter_reminders.return_value = [
            {"title": "开会议", "next_trigger_time": 1738289400},
        ]

        result = service.filter(
            status=None,
            reminder_type=None,
            keyword="开会",
            trigger_after=None,
            trigger_before=None,
        )

        assert result["ok"] is True
        call_args = mock_dao.filter_reminders.call_args
        assert call_args.kwargs["keyword"] == "开会"

    def test_filter_with_time_range(self, service, mock_dao):
        """Test filter with time range parsing."""
        mock_dao.filter_reminders.return_value = []

        result = service.filter(
            status=None,
            reminder_type=None,
            keyword=None,
            trigger_after="今天00:00",
            trigger_before="今天23:59",
        )

        assert result["ok"] is True
        call_args = mock_dao.filter_reminders.call_args
        # Times should be parsed to timestamps
        assert "trigger_after" in call_args.kwargs
        assert "trigger_before" in call_args.kwargs

    def test_filter_with_reminder_type(self, service, mock_dao):
        """Test filter with reminder type filter."""
        mock_dao.filter_reminders.return_value = []

        result = service.filter(
            status=None,
            reminder_type="recurring",
            keyword=None,
            trigger_after=None,
            trigger_before=None,
        )

        assert result["ok"] is True
        call_args = mock_dao.filter_reminders.call_args
        assert call_args.kwargs["reminder_type"] == "recurring"

    def test_filter_empty_results(self, service, mock_dao):
        """Test filter returns formatted empty message."""
        mock_dao.filter_reminders.return_value = []

        result = service.filter(
            status=None,
            reminder_type=None,
            keyword=None,
            trigger_after=None,
            trigger_before=None,
        )

        assert result["ok"] is True
        assert result["count"] == 0
        assert "没有符合" in result["message"] or "没有" in result["message"]

    def test_filter_with_time_and_inbox(self, service, mock_dao):
        """Test filter groups reminders with time vs inbox."""
        mock_dao.filter_reminders.return_value = [
            {"title": "开会", "next_trigger_time": 1738289400},
            {"title": "买牛奶", "next_trigger_time": None},
        ]

        result = service.filter(
            status=None,
            reminder_type=None,
            keyword=None,
            trigger_after=None,
            trigger_before=None,
        )

        assert result["ok"] is True
        assert result["count"] == 2
        # Message should group by type
        assert "定时提醒" in result["message"] or "待安排" in result["message"]


# ============ Test Batch Operations ============


class TestReminderServiceBatch:
    """Test batch operations."""

    def test_batch_multiple_creates(self, mock_dao):
        """Test batch creating multiple reminders."""
        mock_dao.create_reminder.side_effect = ["id1", "id2", "id3"]
        mock_dao.find_similar_reminder.return_value = None
        mock_dao.filter_reminders.return_value = []

        service = ReminderService(
            user_id="user123",
            character_id="char1",
            conversation_id="conv1",
            base_timestamp=1738289400,
            dao=mock_dao,
        )

        operations = json.dumps([
            {"action": "create", "title": "开会", "trigger_time": "明天9点"},
            {"action": "create", "title": "买菜", "trigger_time": "后天10点"},
            {"action": "create", "title": "健身", "trigger_time": "下周"},
        ])

        result = service.batch(operations)

        assert result["ok"] is True
        assert result["total"] == 3
        assert result["succeeded"] == 3
        assert result["failed"] == 0
        assert len(result["results"]) == 3
        assert mock_dao.create_reminder.call_count == 3

    def test_batch_mixed_operations(self, mock_dao):
        """Test batch with mixed create, update, delete operations."""
        # Setup mock responses
        mock_dao.create_reminder.return_value = "new_id"
        mock_dao.update_reminders_by_keyword.return_value = (1, [{"title": "开会"}])
        mock_dao.delete_reminders_by_keyword.return_value = (1, [{"title": "买菜"}])
        mock_dao.find_similar_reminder.return_value = None
        mock_dao.filter_reminders.return_value = []

        service = ReminderService(
            user_id="user123",
            character_id="char1",
            conversation_id="conv1",
            base_timestamp=1738289400,
            dao=mock_dao,
        )

        operations = json.dumps([
            {"action": "create", "title": "新任务", "trigger_time": "明天9点"},
            {"action": "update", "keyword": "开会", "new_title": "开周会"},
            {"action": "delete", "keyword": "买菜"},
        ])

        result = service.batch(operations)

        assert result["ok"] is True
        assert result["total"] == 3
        assert result["succeeded"] == 3
        assert result["failed"] == 0
        assert mock_dao.create_reminder.call_count == 1
        assert mock_dao.update_reminders_by_keyword.call_count == 1
        assert mock_dao.delete_reminders_by_keyword.call_count == 1

    def test_batch_invalid_json(self, mock_dao):
        """Test batch with invalid JSON returns error."""
        service = ReminderService(
            user_id="user123",
            character_id="char1",
            conversation_id="conv1",
            base_timestamp=1738289400,
            dao=mock_dao,
        )

        result = service.batch("not valid json")

        assert result["ok"] is False
        assert "json" in result["error"].lower() or "格式" in result["error"]

    def test_batch_with_failure(self, mock_dao):
        """Test batch where some operations fail."""
        mock_dao.create_reminder.side_effect = ["id1", Exception("DB error")]
        mock_dao.find_similar_reminder.return_value = None
        mock_dao.filter_reminders.return_value = []

        service = ReminderService(
            user_id="user123",
            character_id="char1",
            conversation_id="conv1",
            base_timestamp=1738289400,
            dao=mock_dao,
        )

        operations = json.dumps([
            {"action": "create", "title": "开会", "trigger_time": "明天9点"},
            {"action": "create", "title": "买菜", "trigger_time": "后天10点"},
        ])

        result = service.batch(operations)

        assert result["ok"] is True  # Batch overall succeeds
        assert result["total"] == 2
        assert result["succeeded"] == 1
        assert result["failed"] == 1

    def test_batch_complete_operation(self, mock_dao):
        """Test batch complete operation."""
        mock_dao.complete_reminders_by_keyword.return_value = (1, [{"title": "开会"}])

        service = ReminderService(
            user_id="user123",
            character_id="char1",
            conversation_id="conv1",
            base_timestamp=1738289400,
            dao=mock_dao,
        )

        operations = json.dumps([
            {"action": "complete", "keyword": "开会"},
        ])

        result = service.batch(operations)

        assert result["ok"] is True
        assert result["succeeded"] == 1
        assert result["results"][0]["ok"] is True
        assert result["results"][0]["completed_count"] == 1

    def test_batch_delete_all_operation(self, mock_dao):
        """Test batch delete all with '*' keyword."""
        mock_dao.delete_all_by_user.return_value = 5

        service = ReminderService(
            user_id="user123",
            character_id="char1",
            conversation_id="conv1",
            base_timestamp=1738289400,
            dao=mock_dao,
        )

        operations = json.dumps([
            {"action": "delete", "keyword": "*"},
        ])

        result = service.batch(operations)

        assert result["ok"] is True
        assert result["succeeded"] == 1
        assert result["results"][0]["ok"] is True
        assert result["results"][0]["deleted_count"] == 5

    def test_batch_not_list(self, mock_dao):
        """Test batch with non-list JSON object returns error."""
        service = ReminderService(
            user_id="user123",
            character_id="char1",
            conversation_id="conv1",
            base_timestamp=1738289400,
            dao=mock_dao,
        )

        result = service.batch(json.dumps({"action": "create", "title": "test"}))

        assert result["ok"] is False
        assert "数组" in result["error"]

    def test_batch_invalid_operation_type(self, mock_dao):
        """Test batch with invalid action type."""
        service = ReminderService(
            user_id="user123",
            character_id="char1",
            conversation_id="conv1",
            base_timestamp=1738289400,
            dao=mock_dao,
        )

        operations = json.dumps([
            {"action": "invalid_action", "title": "test"},
        ])

        result = service.batch(operations)

        assert result["ok"] is True
        assert result["succeeded"] == 0
        assert result["failed"] == 1
        assert "未知操作" in result["results"][0]["error"]

    def test_batch_non_dict_operation(self, mock_dao):
        """Test batch with non-dict operation (e.g., string in list)."""
        service = ReminderService(
            user_id="user123",
            character_id="char1",
            conversation_id="conv1",
            base_timestamp=1738289400,
            dao=mock_dao,
        )

        operations = json.dumps(["just a string"])

        result = service.batch(operations)

        assert result["ok"] is True
        assert result["succeeded"] == 0
        assert result["failed"] == 1
        assert "对象格式" in result["results"][0]["error"]

    def test_batch_create_missing_title(self, mock_dao):
        """Test batch create fails validation when title is missing."""
        mock_dao.find_similar_reminder.return_value = None
        mock_dao.filter_reminders.return_value = []

        service = ReminderService(
            user_id="user123",
            character_id="char1",
            conversation_id="conv1",
            base_timestamp=1738289400,
            dao=mock_dao,
        )

        operations = json.dumps([
            {"action": "create", "trigger_time": "明天9点"},
        ])

        result = service.batch(operations)

        assert result["ok"] is True
        assert result["succeeded"] == 0
        assert result["failed"] == 1
        assert result["results"][0]["ok"] is False
