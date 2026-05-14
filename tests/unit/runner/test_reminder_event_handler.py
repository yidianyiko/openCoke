import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agent.reminder.models import AgentOutputTarget, ReminderFiredEvent
import agent.runner.reminder_event_handler as reminder_event_handler
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
        fire_mode=overrides.pop("fire_mode", "notify"),
        prompt=overrides.pop("prompt", None),
        metadata=overrides.pop("metadata", {}),
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


class SerializingFakeLockManager(FakeLockManager):
    def __init__(self, lock_id="lock-1"):
        super().__init__(lock_id=lock_id)
        self._lock = asyncio.Lock()

    async def acquire_lock_async(
        self, resource_type, resource_id, timeout=120, max_wait=1
    ):
        self.acquired.append((resource_type, resource_id, timeout, max_wait))
        await asyncio.sleep(0)
        await self._lock.acquire()
        return self.lock_id

    async def release_lock_safe_async(self, resource_type, resource_id, lock_id):
        self.released.append((resource_type, resource_id, lock_id))
        self._lock.release()
        return True, "released"


def build_handler(output_writer, existing_output_lookup=None):
    conversation = {
        "_id": "conv-1",
        "platform": "business",
        "chatroom_name": None,
        "talkers": [{"db_user_id": "user-1"}, {"db_user_id": "char-1"}],
    }
    owner = {"_id": "user-1", "nickname": "Owner"}
    character = {"_id": "char-1", "nickname": "Assistant"}
    context = {"conversation": conversation, "user": owner, "character": character}
    users = {"user-1": owner, "char-1": character}
    return ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=conversation)),
        user_dao=Mock(get_user_by_id=Mock(side_effect=lambda user_id: users[user_id])),
        lock_manager=FakeLockManager(),
        output_writer=output_writer,
        context_builder=Mock(return_value=context),
        existing_output_lookup=existing_output_lookup or Mock(return_value=None),
    )


def _build_handler_with_failing_replay_lookup():
    event = build_event()
    output_writer = Mock()
    existing_output_lookup = Mock(side_effect=RuntimeError("boom"))
    handler = build_handler(output_writer, existing_output_lookup=existing_output_lookup)
    return handler, event, output_writer


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
        existing_output_lookup=Mock(return_value=None),
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
async def test_output_writer_returning_none_returns_failed_result():
    handler = build_handler(Mock(return_value=None))

    result = await handler.handle(build_event())

    assert result.ok is False
    assert result.error_code == "OutputUnavailable"
    assert result.output_reference is None


@pytest.mark.asyncio
async def test_output_writer_failed_status_returns_failed_result():
    handler = build_handler(
        Mock(
            return_value={"_id": "out-1", "status": "failed", "last_error": "no route"}
        )
    )

    result = await handler.handle(build_event())

    assert result.ok is False
    assert result.error_code == "OutputFailed"
    assert result.error_message == "no route"
    assert result.output_reference == "out-1"


@pytest.mark.asyncio
async def test_missing_conversation_returns_failed_result():
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=None)),
        user_dao=Mock(),
        lock_manager=FakeLockManager(),
        output_writer=Mock(),
        context_builder=Mock(),
        existing_output_lookup=Mock(return_value={"_id": "out-existing"}),
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
        existing_output_lookup=Mock(return_value={"_id": "out-existing"}),
    )

    result = await handler.handle(build_event())

    assert result.ok is False
    assert result.error_code == "OwnerMismatch"
    output_writer.assert_not_called()


@pytest.mark.asyncio
async def test_replayed_fire_validates_target_then_returns_existing_output_without_duplicate_write():
    event = build_event()
    output_writer = Mock(return_value={"_id": "out-new"})
    existing_output_lookup = Mock(return_value={"_id": "out-existing"})
    conversation = {
        "_id": "conv-1",
        "platform": "business",
        "chatroom_name": None,
        "talkers": [{"db_user_id": "user-1"}, {"db_user_id": "char-1"}],
    }
    owner = {"_id": "user-1", "nickname": "Owner"}
    character = {"_id": "char-1", "nickname": "Assistant"}
    conversation_dao = Mock(get_conversation_by_id=Mock(return_value=conversation))
    user_dao = Mock(get_user_by_id=Mock(side_effect=[owner, character]))
    lock_manager = FakeLockManager()
    context_builder = Mock()
    handler = ReminderFireEventHandler(
        conversation_dao=conversation_dao,
        user_dao=user_dao,
        lock_manager=lock_manager,
        output_writer=output_writer,
        context_builder=context_builder,
        existing_output_lookup=existing_output_lookup,
    )

    result = await handler.handle(event)

    conversation_dao.get_conversation_by_id.assert_called_once_with("conv-1")
    assert user_dao.get_user_by_id.call_args_list == [
        (("user-1",),),
        (("char-1",),),
    ]
    existing_output_lookup.assert_called_once_with(event)
    assert lock_manager.acquired == []
    context_builder.assert_not_called()
    output_writer.assert_not_called()
    assert result.ok is True
    assert result.fire_id == event.fire_id
    assert result.output_reference == "out-existing"
    assert result.error_code is None
    assert result.error_message is None


@pytest.mark.asyncio
async def test_non_replayed_fire_id_checks_lookup_before_and_after_lock_then_writes_output():
    event = build_event()
    output_writer = Mock(return_value={"_id": "out-new"})
    existing_output_lookup = Mock(return_value=None)
    handler = build_handler(output_writer, existing_output_lookup=existing_output_lookup)

    result = await handler.handle(event)

    assert existing_output_lookup.call_args_list == [((event,),), ((event,),)]
    output_writer.assert_called_once()
    assert result.ok is True
    assert result.output_reference == "out-new"


@pytest.mark.asyncio
async def test_concurrent_same_fire_events_write_once_and_return_same_output_reference():
    event = build_event()
    outputs_by_fire_id = {}
    lock_manager = SerializingFakeLockManager()

    def existing_output_lookup(event):
        return outputs_by_fire_id.get(event.fire_id)

    def output_writer(*args, **kwargs):
        output = {"_id": "out-concurrent"}
        outputs_by_fire_id[event.fire_id] = output
        return output

    writer = Mock(side_effect=output_writer)
    handler = build_handler(writer, existing_output_lookup=existing_output_lookup)
    handler.lock_manager = lock_manager

    first_result, second_result = await asyncio.gather(
        handler.handle(event),
        handler.handle(event),
    )

    assert writer.call_count == 1
    assert first_result.ok is True
    assert second_result.ok is True
    assert first_result.output_reference == "out-concurrent"
    assert second_result.output_reference == "out-concurrent"
    assert lock_manager.acquired == [
        ("conversation", "conv-1", 120, 1),
        ("conversation", "conv-1", 120, 1),
    ]
    assert lock_manager.released == [
        ("conversation", "conv-1", "lock-1"),
        ("conversation", "conv-1", "lock-1"),
    ]


@pytest.mark.asyncio
async def test_in_lock_replay_suppression_releases_lock_without_writing_output():
    event = build_event()
    lock_manager = FakeLockManager()
    output_writer = Mock(return_value={"_id": "out-new"})
    context_builder = Mock()
    existing_output_lookup = Mock(
        side_effect=[None, {"_id": "out-existing"}]
    )
    conversation = {
        "_id": "conv-1",
        "platform": "business",
        "chatroom_name": None,
        "talkers": [{"db_user_id": "user-1"}, {"db_user_id": "char-1"}],
    }
    owner = {"_id": "user-1", "nickname": "Owner"}
    character = {"_id": "char-1", "nickname": "Assistant"}
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=conversation)),
        user_dao=Mock(get_user_by_id=Mock(side_effect=[owner, character])),
        lock_manager=lock_manager,
        output_writer=output_writer,
        context_builder=context_builder,
        existing_output_lookup=existing_output_lookup,
    )

    result = await handler.handle(event)

    assert existing_output_lookup.call_args_list == [((event,),), ((event,),)]
    context_builder.assert_not_called()
    output_writer.assert_not_called()
    assert lock_manager.acquired == [("conversation", "conv-1", 120, 1)]
    assert lock_manager.released == [("conversation", "conv-1", "lock-1")]
    assert result.ok is True
    assert result.output_reference == "out-existing"


@pytest.mark.asyncio
async def test_in_lock_replay_lookup_exception_releases_lock_without_writing_output():
    event = build_event()
    lock_manager = FakeLockManager()
    output_writer = Mock(return_value={"_id": "out-new"})
    context_builder = Mock()
    existing_output_lookup = Mock(side_effect=[None, RuntimeError("lookup failed")])
    conversation = {
        "_id": "conv-1",
        "platform": "business",
        "chatroom_name": None,
        "talkers": [{"db_user_id": "user-1"}, {"db_user_id": "char-1"}],
    }
    owner = {"_id": "user-1", "nickname": "Owner"}
    character = {"_id": "char-1", "nickname": "Assistant"}
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=conversation)),
        user_dao=Mock(get_user_by_id=Mock(side_effect=[owner, character])),
        lock_manager=lock_manager,
        output_writer=output_writer,
        context_builder=context_builder,
        existing_output_lookup=existing_output_lookup,
    )

    result = await handler.handle(event)

    assert existing_output_lookup.call_args_list == [((event,),), ((event,),)]
    context_builder.assert_not_called()
    output_writer.assert_not_called()
    assert lock_manager.acquired == [("conversation", "conv-1", 120, 1)]
    assert lock_manager.released == [("conversation", "conv-1", "lock-1")]
    assert result.ok is False
    assert result.error_code == "ReplayLookupFailed"
    assert result.output_reference is None


@pytest.mark.asyncio
async def test_default_lookup_queries_outputmessages_with_event_metadata(monkeypatch):
    event = build_event()
    queries = []

    class FakeMongo:
        def find_one(self, collection_name, query):
            queries.append((collection_name, query))
            return {"_id": "out-existing"}

    monkeypatch.setattr(reminder_event_handler, "MongoDBBase", lambda: FakeMongo())

    conversation = {
        "_id": "conv-1",
        "talkers": [{"db_user_id": "user-1"}, {"db_user_id": "char-1"}],
    }
    owner = {"_id": "user-1", "nickname": "Owner"}
    character = {"_id": "char-1", "nickname": "Assistant"}
    lock_manager = FakeLockManager()
    output_writer = Mock()
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=conversation)),
        user_dao=Mock(get_user_by_id=Mock(side_effect=[owner, character])),
        lock_manager=lock_manager,
        output_writer=output_writer,
        context_builder=Mock(),
    )

    result = await handler.handle(event)

    assert queries == [
        (
            "outputmessages",
            {
                "metadata.fire_id": event.fire_id,
                "metadata.reminder_id": event.reminder_id,
                "metadata.event_type": event.event_type,
            },
        )
    ]
    assert result.ok is True
    assert result.output_reference == "out-existing"
    assert lock_manager.acquired == []
    output_writer.assert_not_called()


@pytest.mark.asyncio
async def test_replay_lookup_does_not_mask_missing_conversation():
    existing_output_lookup = Mock(return_value={"_id": "out-existing"})
    output_writer = Mock()
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=None)),
        user_dao=Mock(),
        lock_manager=FakeLockManager(),
        output_writer=output_writer,
        context_builder=Mock(),
        existing_output_lookup=existing_output_lookup,
    )

    result = await handler.handle(build_event())

    assert result.ok is False
    assert result.error_code == "ConversationNotFound"
    existing_output_lookup.assert_not_called()
    output_writer.assert_not_called()


@pytest.mark.asyncio
async def test_replay_lookup_does_not_mask_owner_mismatch():
    existing_output_lookup = Mock(return_value={"_id": "out-existing"})
    output_writer = Mock()
    conversation = {
        "_id": "conv-1",
        "talkers": [{"db_user_id": "someone-else"}, {"db_user_id": "char-1"}],
    }
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=conversation)),
        user_dao=Mock(get_user_by_id=Mock(return_value={"_id": "user-1"})),
        lock_manager=FakeLockManager(),
        output_writer=output_writer,
        context_builder=Mock(),
        existing_output_lookup=existing_output_lookup,
    )

    result = await handler.handle(build_event())

    assert result.ok is False
    assert result.error_code == "OwnerMismatch"
    existing_output_lookup.assert_not_called()
    output_writer.assert_not_called()


@pytest.mark.asyncio
async def test_replay_lookup_does_not_mask_missing_owner():
    existing_output_lookup = Mock(return_value={"_id": "out-existing"})
    output_writer = Mock()
    conversation = {
        "_id": "conv-1",
        "talkers": [{"db_user_id": "user-1"}, {"db_user_id": "char-1"}],
    }
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=conversation)),
        user_dao=Mock(get_user_by_id=Mock(return_value=None)),
        lock_manager=FakeLockManager(),
        output_writer=output_writer,
        context_builder=Mock(),
        existing_output_lookup=existing_output_lookup,
    )

    result = await handler.handle(build_event())

    assert result.ok is False
    assert result.error_code == "OwnerNotFound"
    existing_output_lookup.assert_not_called()
    output_writer.assert_not_called()


@pytest.mark.asyncio
async def test_replay_lookup_does_not_mask_missing_character():
    existing_output_lookup = Mock(return_value={"_id": "out-existing"})
    output_writer = Mock()
    conversation = {
        "_id": "conv-1",
        "talkers": [{"db_user_id": "user-1"}, {"db_user_id": "char-1"}],
    }
    owner = {"_id": "user-1", "nickname": "Owner"}
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value=conversation)),
        user_dao=Mock(get_user_by_id=Mock(side_effect=[owner, None])),
        lock_manager=FakeLockManager(),
        output_writer=output_writer,
        context_builder=Mock(),
        existing_output_lookup=existing_output_lookup,
    )

    result = await handler.handle(build_event())

    assert result.ok is False
    assert result.error_code == "CharacterNotFound"
    existing_output_lookup.assert_not_called()
    output_writer.assert_not_called()


@pytest.mark.asyncio
async def test_replay_lookup_exception_returns_failed_result_without_output():
    event = build_event()
    output_writer = Mock()
    existing_output_lookup = Mock(side_effect=RuntimeError("database password leaked"))
    handler = build_handler(output_writer, existing_output_lookup=existing_output_lookup)

    result = await handler.handle(event)

    existing_output_lookup.assert_called_once_with(event)
    output_writer.assert_not_called()
    assert result.ok is False
    assert result.error_code == "ReplayLookupFailed"
    assert result.error_message == "reminder replay lookup failed"
    assert result.output_reference is None


@pytest.mark.asyncio
async def test_replay_lookup_failure_logs_exception(caplog):
    handler, event, output_writer = _build_handler_with_failing_replay_lookup()

    caplog.set_level("ERROR")
    result = await handler.handle(event)

    output_writer.assert_not_called()
    assert result.ok is False
    assert result.error_code == "ReplayLookupFailed"
    assert any(
        "reminder replay lookup failed before lock" in record.message
        and record.exc_info
        for record in caplog.records
    )


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
                    content="Did you get started?",
                    message_type="text",
                    metadata={"runtime_visible": True},
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
    assert agent_input.payload.metadata["fire_mode"] == "followup"
    assert agent_input.payload.metadata["kind"] == "internal_followup"
    assert agent_input.payload.metadata["proactive_times"] == 1
    assert agent_input.metadata["kind"] == "internal_followup"
    assert agent_input.metadata["proactive_times"] == 1
    assert runtime_event_handler.call_args.kwargs["message_source"] == "reminder"
    assert runtime_event_handler.call_args.kwargs["metadata"]["kind"] == (
        "internal_followup"
    )
    assert runtime_event_handler.call_args.kwargs["metadata"]["proactive_times"] == 1
    output_writer.assert_called_once()
    assert output_writer.call_args.args[1] == "Did you get started?"
    assert output_writer.call_args.args[1] != "提醒：drink water"
    assert output_writer.call_args.kwargs["metadata"]["runtime_visible"] is True
    assert output_writer.call_args.kwargs["metadata"]["kind"] == "internal_followup"


@pytest.mark.asyncio
async def test_followup_metadata_collisions_cannot_overwrite_trusted_event_metadata():
    event = build_event(
        fire_mode="followup",
        prompt="ask whether the user started",
        metadata={
            "kind": "user_supplied_kind",
            "fire_id": "user-supplied-fire-id",
            "reminder_id": "user-supplied-reminder-id",
            "event_id": "user-supplied-event-id",
            "fire_mode": "notify",
            "proactive_times": 2,
            "custom": "preserved",
        },
    )
    runtime_event_handler = Mock(
        return_value=SimpleNamespace(
            visible_messages=[
                SimpleNamespace(
                    content="Did you get started?",
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
    metadata = agent_input.payload.metadata
    assert metadata["kind"] == "internal_followup"
    assert metadata["fire_id"] == event.fire_id
    assert metadata["reminder_id"] == event.reminder_id
    assert metadata["event_id"] == event.event_id
    assert metadata["fire_mode"] == "followup"
    assert metadata["proactive_times"] == 2
    assert metadata["reminder_metadata"] == {
        "kind": "user_supplied_kind",
        "fire_id": "user-supplied-fire-id",
        "reminder_id": "user-supplied-reminder-id",
        "event_id": "user-supplied-event-id",
        "fire_mode": "notify",
        "proactive_times": 2,
        "custom": "preserved",
    }
    assert runtime_event_handler.call_args.kwargs["metadata"] == metadata
    assert agent_input.metadata["kind"] == "internal_followup"
    assert agent_input.metadata["fire_id"] == event.fire_id
    assert agent_input.metadata["reminder_metadata"]["custom"] == "preserved"
    assert output_writer.call_args.kwargs["metadata"]["kind"] == "internal_followup"
    assert output_writer.call_args.kwargs["metadata"]["fire_id"] == event.fire_id
    assert output_writer.call_args.kwargs["metadata"]["reminder_metadata"][
        "fire_id"
    ] == "user-supplied-fire-id"


@pytest.mark.asyncio
async def test_followup_fire_without_typed_runtime_fails_without_visible_output():
    event = build_event(
        fire_mode="followup",
        prompt="ask whether the user started",
        metadata={"proactive_times": 1},
    )
    output_writer = Mock(return_value={"_id": "out-1"})
    handler = build_handler(output_writer)

    result = await handler.handle(event)

    assert result.ok is False
    assert result.error_code == "RuntimeRequired"
    assert result.error_message == "internal follow-up fire requires typed runtime handler"
    output_writer.assert_not_called()
