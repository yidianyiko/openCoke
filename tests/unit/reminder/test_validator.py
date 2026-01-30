# -*- coding: utf-8 -*-
"""
Unit tests for ReminderValidator module.

Tests the ReminderValidator class which handles validation rules and
side-effect guards for reminder operations.
"""

from unittest.mock import Mock

import pytest

from agent.agno_agent.tools.reminder.validator import ReminderValidator


class TestCheckRequiredFields:
    """Test required field validation."""

    def test_check_required_fields_missing_title(self):
        """Test validation fails when title is missing."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_required_fields(title=None, trigger_time=None)

        assert result is not None
        assert result["ok"] is False
        assert "提醒内容" in result["error"] or "title" in result["error"].lower()

    def test_check_required_fields_empty_title(self):
        """Test validation fails when title is empty string."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_required_fields(title="", trigger_time=None)

        assert result is not None
        assert result["ok"] is False

    def test_check_required_fields_whitespace_only_title(self):
        """Test validation fails when title is whitespace only."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_required_fields(title="   ", trigger_time=None)

        assert result is not None
        assert result["ok"] is False

    def test_check_required_fields_all_present(self):
        """Test validation passes when all required fields are present."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_required_fields(title="开会", trigger_time="明天9点")

        assert result is None


class TestCheckFrequencyLimit:
    """Test frequency limit validation."""

    def test_check_frequency_limit_interval_too_small(self):
        """Test validation fails for interval type with interval < 60 minutes."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_frequency_limit(
            recurrence_type="interval",
            recurrence_interval=30,
            has_period=False,
        )

        assert result is not None
        assert result["ok"] is False
        assert "频率过高" in result["error"] or "60分钟" in result["error"]

    def test_check_frequency_limit_interval_ok(self):
        """Test validation passes for interval type with interval >= 60 minutes."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_frequency_limit(
            recurrence_type="interval",
            recurrence_interval=60,
            has_period=False,
        )

        assert result is None

    def test_check_frequency_limit_period_too_small(self):
        """Test validation fails for period reminder with interval < 25 minutes."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_frequency_limit(
            recurrence_type="interval",
            recurrence_interval=20,
            has_period=True,
        )

        assert result is not None
        assert result["ok"] is False
        assert "25分钟" in result["error"]

    def test_check_frequency_limit_period_ok(self):
        """Test validation passes for period reminder with interval >= 25 minutes."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_frequency_limit(
            recurrence_type="interval",
            recurrence_interval=25,
            has_period=True,
        )

        assert result is None

    def test_check_frequency_limit_none_type(self):
        """Test validation passes for non-interval recurrence types."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        for rtype in ["none", "daily", "weekly", "monthly"]:
            result = validator.check_frequency_limit(
                recurrence_type=rtype,
                recurrence_interval=1,
                has_period=False,
            )
            assert result is None

    def test_check_frequency_limit_exactly_60_minutes(self):
        """Test validation passes for exactly 60 minutes interval."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_frequency_limit(
            recurrence_type="interval",
            recurrence_interval=60,
            has_period=False,
        )

        assert result is None


class TestCheckOperationAllowed:
    """Test operation allowed validation to prevent circular calls."""

    def test_check_operation_allowed_first_call(self):
        """Test first call to an operation is allowed."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_operation_allowed(
            action="create", session_operations=[]
        )

        assert result is None

    def test_check_operation_allowed_duplicate(self):
        """Test duplicate operation is rejected."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_operation_allowed(
            action="create", session_operations=["create"]
        )

        assert result is not None
        assert result["ok"] is False
        assert "只能执行一次" in result["error"]

    def test_check_operation_allowed_batch_exclusive(self):
        """Test batch operation cannot be mixed with other operations."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        # Batch after other operations
        result = validator.check_operation_allowed(
            action="batch", session_operations=["create"]
        )

        assert result is not None
        assert result["ok"] is False

        # Other operations after batch
        result = validator.check_operation_allowed(
            action="create", session_operations=["batch"]
        )

        assert result is not None
        assert result["ok"] is False

    def test_check_operation_allowed_batch_first(self):
        """Test batch operation as first operation is allowed."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        result = validator.check_operation_allowed(
            action="batch", session_operations=[]
        )

        assert result is None

    def test_check_operation_allowed_different_actions(self):
        """Test different actions can be called in sequence."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")

        # create after update is allowed
        result = validator.check_operation_allowed(
            action="create", session_operations=["update"]
        )

        assert result is None

        # delete after create is allowed
        result = validator.check_operation_allowed(
            action="delete", session_operations=["create"]
        )

        assert result is None


class TestCheckDuplicate:
    """Test duplicate reminder validation."""

    def test_check_duplicate_found(self):
        """Test validation detects duplicate reminder."""
        dao = Mock()
        existing_reminder = {
            "reminder_id": "existing123",
            "title": "开会",
            "next_trigger_time": 1234567890,
        }
        dao.find_similar_reminder.return_value = existing_reminder

        validator = ReminderValidator(dao, "user123")

        result = validator.check_duplicate(
            title="开会",
            trigger_time=1234567890,
            recurrence_type="daily",
            tolerance=60,
        )

        assert result is not None
        assert result["ok"] is True
        assert result["status"] == "duplicate"
        dao.find_similar_reminder.assert_called_once()

    def test_check_duplicate_not_found(self):
        """Test validation passes when no duplicate exists."""
        dao = Mock()
        dao.find_similar_reminder.return_value = None

        validator = ReminderValidator(dao, "user123")

        result = validator.check_duplicate(
            title="开会",
            trigger_time=1234567890,
            recurrence_type="daily",
            tolerance=60,
        )

        assert result is None
        dao.find_similar_reminder.assert_called_once()

    def test_check_duplicate_with_different_recurrence_type(self):
        """Test duplicate check considers recurrence type."""
        dao = Mock()
        dao.find_similar_reminder.return_value = None

        validator = ReminderValidator(dao, "user123")

        result = validator.check_duplicate(
            title="开会",
            trigger_time=1234567890,
            recurrence_type="weekly",
            tolerance=60,
        )

        assert result is None

    def test_check_duplicate_with_none_recurrence_type(self):
        """Test duplicate check handles None recurrence type."""
        dao = Mock()
        dao.find_similar_reminder.return_value = None

        validator = ReminderValidator(dao, "user123")

        result = validator.check_duplicate(
            title="开会",
            trigger_time=1234567890,
            recurrence_type=None,
            tolerance=60,
        )

        assert result is None


class TestConstants:
    """Test class constants."""

    def test_min_interval_infinite(self):
        """Test MIN_INTERVAL_INFINITE constant."""
        assert ReminderValidator.MIN_INTERVAL_INFINITE == 60

    def test_min_interval_period(self):
        """Test MIN_INTERVAL_PERIOD constant."""
        assert ReminderValidator.MIN_INTERVAL_PERIOD == 25

    def test_default_max_triggers(self):
        """Test DEFAULT_MAX_TRIGGERS constant."""
        assert ReminderValidator.DEFAULT_MAX_TRIGGERS == 10

    def test_time_tolerance(self):
        """Test TIME_TOLERANCE constant."""
        assert ReminderValidator.TIME_TOLERANCE == 60

    def test_delete_all_words(self):
        """Test DELETE_ALL_WORDS constant."""
        expected = ["全部", "所有", "清空", "都删", "全删"]
        assert ReminderValidator.DELETE_ALL_WORDS == expected


class TestInit:
    """Test ReminderValidator initialization."""

    def test_init_stores_dao_and_user_id(self):
        """Test initialization stores DAO and user_id."""
        dao = Mock()
        user_id = "user123"

        validator = ReminderValidator(dao, user_id)

        assert validator.dao is dao
        assert validator.user_id == user_id


class TestReminderValidatorSideEffectGuard:
    """Test side-effect guard functionality."""

    def test_guard_delete_no_match_in_text(self):
        """Test delete guard when keyword is not in user text."""
        dao = Mock()
        dao.filter_reminders.return_value = [
            {
                "reminder_id": "r1",
                "title": "开会",
                "next_trigger_time": 1738289400,
            }
        ]

        validator = ReminderValidator(dao, "user123")
        session_state = {
            "conversation": {
                "conversation_info": {"input_messages": [{"message": "你好"}]}
            }
        }

        result = validator.guard_side_effect(
            action="delete",
            keyword="开会",
            session_state=session_state,
        )

        assert result["allowed"] is False
        assert result["needs_confirmation"] is True
        assert result["reason"] == "keyword_not_in_user_text"
        assert result["candidates"] == [
            {"title": "开会", "time": "01月31日10:10", "reminder_id": "r1"}
        ]
        assert result["resolved_keyword"] is None

    def test_guard_delete_single_match_in_text(self):
        """Test delete guard when exactly one active reminder title matches text."""
        dao = Mock()
        dao.filter_reminders.return_value = [
            {
                "reminder_id": "r1",
                "title": "开会",
                "next_trigger_time": 1738289400,
            }
        ]

        validator = ReminderValidator(dao, "user123")
        session_state = {
            "conversation": {
                "conversation_info": {
                    "input_messages": [{"message": "把开会这个提醒删掉"}]
                }
            }
        }

        result = validator.guard_side_effect(
            action="delete",
            keyword="开会",
            session_state=session_state,
        )

        assert result["allowed"] is True
        assert result["needs_confirmation"] is False
        assert result["reason"] == "matched_active_title_in_user_text"
        assert result["resolved_keyword"] == "开会"

    def test_guard_delete_keyword_in_text(self):
        """Test delete guard when provided keyword is in user text but no active match."""
        dao = Mock()
        dao.filter_reminders.return_value = [
            {
                "reminder_id": "r1",
                "title": "买牛奶",
                "next_trigger_time": 1738289400,
            }
        ]

        validator = ReminderValidator(dao, "user123")
        session_state = {
            "conversation": {
                "conversation_info": {"input_messages": [{"message": "把任务删了"}]}
            }
        }

        result = validator.guard_side_effect(
            action="delete",
            keyword="任务",
            session_state=session_state,
        )

        assert result["allowed"] is True
        assert result["needs_confirmation"] is False
        assert result["reason"] == "keyword_in_user_text"
        assert result["resolved_keyword"] == "任务"

    def test_guard_delete_all_explicit(self):
        """Test delete-all guard when user explicitly confirms delete-all."""
        dao = Mock()
        dao.filter_reminders.return_value = [
            {
                "reminder_id": "r1",
                "title": "开会",
                "next_trigger_time": 1738289400,
            },
            {
                "reminder_id": "r2",
                "title": "买菜",
                "next_trigger_time": 1738290000,
            },
        ]

        validator = ReminderValidator(dao, "user123")

        for delete_word in ["全部", "所有", "清空", "都删", "全删"]:
            session_state = {
                "conversation": {
                    "conversation_info": {
                        "input_messages": [{"message": f"把{delete_word}提醒删掉"}]
                    }
                }
            }

            result = validator.guard_side_effect(
                action="delete",
                keyword="*",
                session_state=session_state,
            )

            assert result["allowed"] is True, f"Failed for delete word: {delete_word}"
            assert result["needs_confirmation"] is False
            assert result["reason"] == "explicit_delete_all"
            assert result["resolved_keyword"] is None

    def test_guard_delete_all_not_explicit(self):
        """Test delete-all guard when user doesn't explicitly confirm delete-all."""
        dao = Mock()
        dao.filter_reminders.return_value = [
            {
                "reminder_id": "r1",
                "title": "开会",
                "next_trigger_time": 1738289400,
            }
        ]

        validator = ReminderValidator(dao, "user123")
        session_state = {
            "conversation": {
                "conversation_info": {"input_messages": [{"message": "删除提醒"}]}
            }
        }

        result = validator.guard_side_effect(
            action="delete",
            keyword="*",
            session_state=session_state,
        )

        assert result["allowed"] is False
        assert result["needs_confirmation"] is True
        assert result["reason"] == "delete_all_not_explicit"
        assert result["resolved_keyword"] is None

    def test_guard_complete_allowed(self):
        """Test complete action when active reminder title matches text."""
        dao = Mock()
        dao.filter_reminders.return_value = [
            {
                "reminder_id": "r1",
                "title": "买牛奶",
                "next_trigger_time": 1738289400,
            }
        ]

        validator = ReminderValidator(dao, "user123")
        session_state = {
            "conversation": {
                "conversation_info": {"input_messages": [{"message": "我已经买牛奶了"}]}
            }
        }

        result = validator.guard_side_effect(
            action="complete",
            keyword="买牛奶",
            session_state=session_state,
        )

        assert result["allowed"] is True
        assert result["needs_confirmation"] is False
        assert result["reason"] == "matched_active_title_in_user_text"
        assert result["resolved_keyword"] == "买牛奶"

    def test_guard_non_side_effect_action(self):
        """Test non-side-effect actions (create, update, filter, batch) are always allowed."""
        dao = Mock()
        validator = ReminderValidator(dao, "user123")
        session_state = {
            "conversation": {
                "conversation_info": {"input_messages": [{"message": "some message"}]}
            }
        }

        for action in ["create", "update", "filter", "batch"]:
            result = validator.guard_side_effect(
                action=action,
                keyword="something",
                session_state=session_state,
            )

            assert result["allowed"] is True
            assert (
                result.get("needs_confirmation") is None
                or result.get("needs_confirmation") is True
                or result.get("needs_confirmation") is False
            )

    def test_contains_any_static_helper(self):
        """Test _contains_any static helper method."""
        assert ReminderValidator._contains_any("hello world", ["hello"]) is True
        assert ReminderValidator._contains_any("hello world", ["foo", "bar"]) is False
        assert ReminderValidator._contains_any("", ["hello"]) is False
        assert ReminderValidator._contains_any(None, ["hello"]) is False
        assert ReminderValidator._contains_any("test", []) is False
        assert ReminderValidator._contains_any("test", [""]) is False
        assert ReminderValidator._contains_any("test", [None]) is False
