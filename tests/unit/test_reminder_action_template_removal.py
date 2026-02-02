# -*- coding: utf-8 -*-
"""
Tests for action_template field removal

This test file ensures that reminders no longer use the redundant action_template field.
The field is removed because:
1. LLM only provides title in tool calls (not action_template)
2. action_template was just auto-generated from title
3. AI can generate natural language from title directly
"""
import pytest


@pytest.mark.unit
def test_single_create_reminder_without_action_template(sample_context, monkeypatch):
    """Test that single created reminders do not have action_template field"""
    import time
    from agent.agno_agent.tools.reminder import service

    created_reminders = []

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def create_reminder(self, reminder_data):
            created_reminders.append(reminder_data)
            return "fake_object_id"

        def find_similar_reminder(self, *args, **kwargs):
            return None

        def close(self):
            pass

    monkeypatch.setattr("dao.reminder_dao.ReminderDAO", FakeReminderDAO)

    # Create service instance
    reminder_service = service.ReminderService(
        user_id="test_user",
        character_id="test_char",
        conversation_id="test_conv",
        base_timestamp=int(time.time())
    )

    # Single create (without providing action_template parameter)
    result = reminder_service.create(
        title="买牛奶",
        trigger_time="明天09时00分",
        recurrence_type=None,
        recurrence_interval=None,
        period_start=None,
        period_end=None,
        period_days=None
    )

    # Verify reminder was created successfully
    assert result["ok"] is True
    assert len(created_reminders) == 1

    # THE KEY ASSERTION: action_template field should NOT exist
    reminder = created_reminders[0]
    assert "action_template" not in reminder, \
        f"Reminder should not have action_template field, got: {reminder.get('action_template')}"
    assert reminder["title"] == "买牛奶"


@pytest.mark.unit
def test_batch_create_operation_without_action_template(sample_context, monkeypatch):
    """Test that batch create operations don't add action_template when LLM doesn't provide it"""
    import time
    from agent.agno_agent.tools.reminder import service

    created_reminders = []

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def create_reminder(self, reminder_data):
            created_reminders.append(reminder_data)
            return f"fake_id_{len(created_reminders)}"

        def find_similar_reminder(self, *args, **kwargs):
            return None

        def close(self):
            pass

    monkeypatch.setattr("dao.reminder_dao.ReminderDAO", FakeReminderDAO)

    # Create service instance
    reminder_service = service.ReminderService(
        user_id="test_user",
        character_id="test_char",
        conversation_id="test_conv",
        base_timestamp=1737532800  # Fixed timestamp for parsing
    )

    # Simulate batch create via _batch_create (called by batch operations)
    # This simulates LLM not providing action_template field
    op1 = {
        "action": "create",
        "title": "起床",
        "trigger_time": "明天09时00分"
        # Note: No action_template field (LLM doesn't provide it)
    }

    result = reminder_service._batch_create(op1)

    # Verify reminder was created successfully
    assert result["ok"] is True
    assert len(created_reminders) == 1

    # THE KEY ASSERTION: action_template should NOT exist when not provided by LLM
    reminder = created_reminders[0]
    assert "action_template" not in reminder, \
        f"Batch create should not add action_template when not provided, got: {reminder.get('action_template')}"
    assert reminder["title"] == "起床"


@pytest.mark.unit
def test_batch_update_title_without_updating_action_template(sample_context, monkeypatch):
    """Test that batch update operations don't add action_template when updating title"""
    import time
    from agent.agno_agent.tools.reminder import service

    updated_reminders = {}

    class FakeReminderDAO:
        def __init__(self, *args, **kwargs):
            pass

        def update_reminders_by_keyword(self, user_id, keyword, update_data):
            # Store the update data for verification
            updated_reminders["test_update"] = update_data
            return 1, None  # Return (updated_count, error)

        def close(self):
            pass

    monkeypatch.setattr("dao.reminder_dao.ReminderDAO", FakeReminderDAO)

    # Create service instance
    reminder_service = service.ReminderService(
        user_id="test_user",
        character_id="test_char",
        conversation_id="test_conv",
        base_timestamp=int(time.time())
    )

    # Batch update via _batch_update
    op = {
        "action": "update",
        "keyword": "牛奶",
        "new_title": "买豆奶"
    }

    result = reminder_service._batch_update(op)

    # Verify update was successful
    assert result["ok"] is True

    # THE KEY ASSERTION: action_template should NOT be in update fields
    update_fields = updated_reminders.get("test_update", {})
    assert "action_template" not in update_fields, \
        f"Batch update should not modify action_template, got fields: {update_fields}"
    assert "title" in update_fields
    assert update_fields["title"] == "买豆奶"

