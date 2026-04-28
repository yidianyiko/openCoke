from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from agent.reminder.models import AgentOutputTarget, ReminderFiredEvent
from agent.runner.reminder_event_handler import ReminderFireEventHandler


def build_event(**overrides):
    event = ReminderFiredEvent(
        event_type="reminder.fired",
        event_id="evt-1",
        fire_id="rem-1:2026-04-29T01:00:00+00:00",
        reminder_id="rem-1",
        owner_user_id="user-1",
        title="drink water",
        fire_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        scheduled_for=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        agent_output_target=AgentOutputTarget("conv-1", "char-1", None),
    )
    for key, value in overrides.items():
        setattr(event, key, value)
    return event


class FakeLockManager:
    def __init__(self, lock_id="lock-1"):
        self.lock_id = lock_id
        self.acquired = []
        self.released = []

    async def acquire_lock_async(
        self, resource_type, resource_id, timeout=120, max_wait=1
    ):
        self.acquired.append((resource_type, resource_id, timeout, max_wait))
        return self.lock_id

    async def release_lock_safe_async(self, resource_type, resource_id, lock_id):
        self.released.append((resource_type, resource_id, lock_id))
        return True, "released"


@pytest.mark.asyncio
async def test_handler_resolves_target_acquires_lock_writes_output_and_returns_fire_id():
    event = build_event()
    conversation = {
        "_id": "conv-1",
        "platform": "business",
        "chatroom_name": None,
        "talkers": [{"db_user_id": "user-1"}, {"db_user_id": "char-1"}],
    }
    owner = {"_id": "user-1", "nickname": "Owner"}
    character = {"_id": "char-1", "nickname": "Assistant"}
    context = {"conversation": conversation, "user": owner, "character": character}
    lock_manager = FakeLockManager()
    output_writer = Mock(return_value={"_id": "out-1"})
    context_builder = Mock(return_value=context)

    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=conversation)),
        user_dao=Mock(get_user_by_id=Mock(side_effect=[owner, character])),
        lock_manager=lock_manager,
        output_writer=output_writer,
        context_builder=context_builder,
    )

    result = await handler.handle(event)

    context_builder.assert_called_once_with(owner, character, conversation)
    assert lock_manager.acquired == [("conversation", "conv-1", 120, 1)]
    assert lock_manager.released == [("conversation", "conv-1", "lock-1")]
    output_writer.assert_called_once()
    assert output_writer.call_args.args[:2] == (context, "提醒：drink water")
    assert output_writer.call_args.kwargs["message_type"] == "text"
    assert output_writer.call_args.kwargs["metadata"]["reminder_id"] == "rem-1"
    assert result.ok is True
    assert result.fire_id == "rem-1:2026-04-29T01:00:00+00:00"
    assert result.output_reference == "out-1"


@pytest.mark.asyncio
async def test_missing_conversation_returns_failed_result():
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=None)),
        user_dao=Mock(),
        lock_manager=FakeLockManager(),
        output_writer=Mock(),
        context_builder=Mock(),
    )

    result = await handler.handle(build_event())

    assert result.ok is False
    assert result.error_code == "ConversationNotFound"


@pytest.mark.asyncio
async def test_owner_mismatch_returns_failed_result_without_output():
    conversation = {
        "_id": "conv-1",
        "talkers": [{"db_user_id": "someone-else"}, {"db_user_id": "char-1"}],
    }
    output_writer = Mock()
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=conversation)),
        user_dao=Mock(get_user_by_id=Mock(return_value={"_id": "user-1"})),
        lock_manager=FakeLockManager(),
        output_writer=output_writer,
        context_builder=Mock(),
    )

    result = await handler.handle(build_event())

    assert result.ok is False
    assert result.error_code == "OwnerMismatch"
    output_writer.assert_not_called()
