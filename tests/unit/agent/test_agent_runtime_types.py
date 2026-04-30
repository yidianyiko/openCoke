from datetime import UTC, datetime

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import (
    AgentInput,
    DeferredActionPayload,
    ReminderFirePayload,
    UserTurnPayload,
)
from agent.agno_agent.runtime.result import (
    AgentRunResult,
    CapabilityResult,
    OutputDisposition,
    RuntimeErrorDisposition,
    VisibleMessage,
)


def test_user_turn_input_is_explicit():
    event = AgentInput(
        input_type="user.turn",
        conversation_id="conv-1",
        text="remind me tomorrow",
        payload=UserTurnPayload(current_message_ids=["msg-1"]),
        occurred_at=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
    )

    assert event.input_type == "user.turn"
    assert event.payload.current_message_ids == ["msg-1"]
    assert event.payload.check_new_message is True


def test_reminder_fire_payload_carries_required_fire_fields():
    scheduled_for = datetime(2026, 5, 1, 1, 0, tzinfo=UTC)

    payload = ReminderFirePayload(
        fire_id="rem-1:2026-05-01T01:00:00+00:00",
        reminder_id="rem-1",
        title="drink water",
        scheduled_for=scheduled_for,
        metadata={"event_type": "reminder.fired"},
    )

    assert payload.fire_id.startswith("rem-1:")
    assert payload.reminder_id == "rem-1"
    assert payload.title == "drink water"
    assert payload.scheduled_for == scheduled_for
    assert payload.metadata["event_type"] == "reminder.fired"


def test_deferred_action_payload_can_be_used_as_agent_input():
    scheduled_for = datetime(2026, 5, 1, 2, 0, tzinfo=UTC)

    event = AgentInput(
        input_type="deferred_action.fire",
        conversation_id="conv-1",
        text=None,
        payload=DeferredActionPayload(
            action_id="action-1",
            kind="follow_up",
            scheduled_for=scheduled_for,
            revision=2,
            prompt="Follow up with the user.",
        ),
        occurred_at=scheduled_for,
        metadata={"source": "deferred-action-service"},
    )

    assert event.input_type == "deferred_action.fire"
    assert event.payload.action_id == "action-1"
    assert event.metadata["source"] == "deferred-action-service"


def test_run_context_uses_trusted_context_objects():
    context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key=None,
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: hello",
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
        runtime_metadata={"worker_tag": "[T]"},
    )

    assert context.user.id == "user-1"
    assert context.character.id == "char-1"
    assert context.conversation.id == "conv-1"
    assert context.relation.cid == "char-1"
    assert context.runtime_metadata["worker_tag"] == "[T]"


def test_run_result_has_output_contract_fields():
    result = AgentRunResult(
        visible_messages=[
            VisibleMessage(message_type="text", content="Done", metadata={"k": "v"})
        ],
        post_analyze_input=None,
        tool_results=[CapabilityResult(name="reminder", ok=True, content={"id": "r1"})],
        metrics={"latency_ms": 12},
        trace={"runtime": "team"},
        output_disposition=OutputDisposition(status="ok", output_references=["out-1"]),
    )

    assert result.visible_messages[0].content == "Done"
    assert result.tool_results[0].content == {"id": "r1"}
    assert result.metrics["latency_ms"] == 12
    assert result.trace["runtime"] == "team"
    assert result.output_disposition.status == "ok"
    assert result.output_disposition.output_references == ["out-1"]


def test_runtime_error_disposition_expresses_error_handling():
    error = RuntimeErrorDisposition(
        code="agent_timeout",
        retryable=True,
        user_visible_fallback="I need a moment. Please try again.",
    )

    assert error.code == "agent_timeout"
    assert error.retryable is True
    assert error.user_visible_fallback == "I need a moment. Please try again."


def test_default_metadata_collections_are_not_shared():
    first = UserTurnPayload()
    second = UserTurnPayload()

    first.metadata["k"] = "v"
    first.current_message_ids.append("msg-1")

    assert second.metadata == {}
    assert second.current_message_ids == []
