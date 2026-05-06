from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from agent.agno_agent.runtime.result import (
    AgentRunResult,
    OutputDisposition,
    VisibleMessage,
)
from agent.reminder.models import AgentOutputTarget, ReminderFiredEvent


def _event():
    return ReminderFiredEvent(
        event_type="reminder.fired",
        event_id="evt-1",
        fire_id="rem-1:2026-05-06T01:00:00+00:00",
        reminder_id="rem-1",
        owner_user_id="user-1",
        title="drink water",
        fire_at=datetime(2026, 5, 6, 1, 0, 1, tzinfo=UTC),
        scheduled_for=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        agent_output_target=AgentOutputTarget("conv-1", "char-1", None),
    )


@pytest.mark.asyncio
async def test_reminder_event_handler_can_route_through_typed_runtime():
    from agent.runner.reminder_event_handler import ReminderFireEventHandler

    captured = {}

    async def runtime_event_handler(**kwargs):
        captured.update(kwargs)
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="提醒：drink water")
            ],
            post_analyze_input=None,
            tool_results=[],
            metrics={},
            trace={"runtime": "team"},
            output_disposition=OutputDisposition(status="ok"),
        )

    handler = ReminderFireEventHandler(
        conversation_dao=Mock(
            get_conversation_by_id=Mock(
                return_value={
                    "_id": "conv-1",
                    "talkers": [
                        {"db_user_id": "user-1"},
                        {"db_user_id": "char-1"},
                    ],
                }
            )
        ),
        user_dao=Mock(
            get_user_by_id=Mock(
                side_effect=[
                    {"_id": "user-1", "nickname": "User"},
                    {"_id": "char-1", "nickname": "Coke"},
                ]
            )
        ),
        lock_manager=Mock(
            acquire_lock_async=AsyncMock(return_value="lock-1"),
            release_lock_safe_async=AsyncMock(return_value=(True, "released")),
        ),
        context_builder=Mock(return_value={"conversation": {"_id": "conv-1"}}),
        output_writer=Mock(return_value={"_id": "out-1"}),
        existing_output_lookup=Mock(return_value=None),
        runtime_event_handler=runtime_event_handler,
    )

    result = await handler.handle(_event())

    assert result.ok is True
    assert result.output_reference == "out-1"
    typed_input = captured["agent_input"]
    assert typed_input.input_type == "reminder.fired"
    assert typed_input.text == "提醒：drink water"
    assert typed_input.payload.fire_id.startswith("rem-1:")
    assert typed_input.payload.title == "drink water"
    assert typed_input.metadata["owner_user_id"] == "user-1"
    assert captured["message_source"] == "reminder"
    assert captured["context"]["conversation"]["_id"] == "conv-1"
    assert captured["context"]["message_source"] == "deferred_action"
