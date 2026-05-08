from datetime import UTC, datetime
from typing import get_args, get_type_hints

import pytest

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
    build_agent_run_context,
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
    assert event.payload.current_message_ids == ("msg-1",)
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


def test_agent_run_context_metadata_does_not_smuggle_raw():
    context = build_agent_run_context(
        {
            "user": {
                "id": "user-1",
                "nickname": "User",
                "timezone": "Asia/Tokyo",
            },
            "character": {"id": "char-1", "nickname": "Coke"},
            "conversation": {
                "id": "conv-1",
                "platform": "business",
                "route_key": "route-1",
            },
            "relation": {"uid": "user-1", "cid": "char-1"},
        },
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
    )

    assert "raw" not in context.user.metadata
    assert "raw" not in context.character.metadata
    assert "raw" not in context.conversation.metadata
    assert "raw" not in context.relation.metadata


def test_run_result_has_output_contract_fields():
    result = AgentRunResult(
        visible_messages=[
            VisibleMessage(message_type="text", content="Done", metadata={"k": "v"})
        ],
        post_analyze_input=None,
        tool_results=[CapabilityResult(name="reminder", ok=True, content={"id": "r1"})],
        metrics={"latency_ms": 12},
        trace={"runtime": "agent_runtime"},
        output_disposition=OutputDisposition(status="ok", output_references=["out-1"]),
    )

    assert result.visible_messages[0].content == "Done"
    assert result.tool_results[0].content == {"id": "r1"}
    assert result.metrics["latency_ms"] == 12
    assert result.trace["runtime"] == "agent_runtime"
    assert result.output_disposition.status == "ok"
    assert result.output_disposition.output_references == ("out-1",)


def test_capability_result_exposes_runtime_protocol_fields():
    result = CapabilityResult(
        name="url_context",
        ok=True,
        content={
            "visible_summary": "已读取链接内容。",
            "synthesis_context": {"text": "article body"},
        },
        metadata={"durable_write": False, "requires_response_synthesis": True},
    )

    assert result.visible_summary == "已读取链接内容。"
    assert result.synthesis_context == {"text": "article body"}
    assert result.durable_write is False
    assert result.requires_response_synthesis is True
    assert result.to_manager_payload() == {
        "name": "url_context",
        "ok": True,
        "content": {
            "visible_summary": "已读取链接内容。",
            "synthesis_context": {"text": "article body"},
        },
        "error": None,
        "metadata": {
            "durable_write": False,
            "requires_response_synthesis": True,
        },
    }

    assert (
        CapabilityResult(
            name="timezone",
            ok=True,
            content={"summary": "已切换时区。"},
        ).visible_summary
        == "已切换时区。"
    )
    assert (
        CapabilityResult(
            name="calendar_import",
            ok=True,
            content={"message": "可以从这里导入日历。"},
        ).visible_summary
        == "可以从这里导入日历。"
    )


def test_visible_message_accepts_multimodal_message_types():
    hints = get_type_hints(VisibleMessage)
    assert set(get_args(hints["message_type"])) == {"text", "voice", "photo"}

    voice = VisibleMessage(
        message_type="voice",
        content="我来提醒你",
        metadata={"emotion": "无"},
    )
    photo = VisibleMessage(message_type="photo", content="照片123")

    assert voice.message_type == "voice"
    assert voice.metadata["emotion"] == "无"
    assert photo.message_type == "photo"


def test_runtime_error_disposition_expresses_error_handling():
    error = RuntimeErrorDisposition(
        code="agent_timeout",
        retryable=True,
        user_visible_fallback="I need a moment. Please try again.",
    )

    assert error.code == "agent_timeout"
    assert error.retryable is True
    assert error.user_visible_fallback == "I need a moment. Please try again."


def test_sequence_fields_are_immutable_after_construction():
    payload = UserTurnPayload(current_message_ids=["msg-1"])
    disposition = OutputDisposition(status="ok", output_references=["out-1"])
    result = AgentRunResult(
        visible_messages=[VisibleMessage(message_type="text", content="Done")],
        post_analyze_input=None,
        tool_results=[CapabilityResult(name="reminder", ok=True, content={"id": "r1"})],
        metrics={},
        trace={},
        output_disposition=disposition,
    )

    assert payload.current_message_ids == ("msg-1",)
    assert disposition.output_references == ("out-1",)
    assert isinstance(result.visible_messages, tuple)
    assert isinstance(result.tool_results, tuple)

    with pytest.raises(AttributeError):
        payload.current_message_ids.append("msg-2")
    with pytest.raises(AttributeError):
        disposition.output_references.append("out-2")
    with pytest.raises(AttributeError):
        result.visible_messages.append(
            VisibleMessage(message_type="text", content="Nope")
        )


def test_user_turn_payload_rejects_string_message_id_sequence():
    with pytest.raises(TypeError, match="str, bytes, or bytearray"):
        UserTurnPayload(current_message_ids="msg-1")


def test_metadata_mappings_are_read_only_after_construction():
    payload = UserTurnPayload(metadata={"outer": {"inner": "value"}})
    result = AgentRunResult(
        visible_messages=[VisibleMessage(message_type="text", content="Done")],
        post_analyze_input={"messages": ["msg-1"]},
        tool_results=[CapabilityResult(name="reminder", ok=True, content={"id": "r1"})],
        metrics={"latency_ms": 12},
        trace={"runtime": "agent_runtime"},
        output_disposition=OutputDisposition(status="ok"),
    )

    assert payload.metadata["outer"]["inner"] == "value"
    assert result.post_analyze_input["messages"] == ("msg-1",)

    with pytest.raises(TypeError):
        payload.metadata["new"] = "value"
    with pytest.raises(TypeError):
        payload.metadata["outer"]["inner"] = "changed"
    with pytest.raises(TypeError):
        result.metrics["latency_ms"] = 13
    with pytest.raises(TypeError):
        result.trace["runtime"] = "other"
    with pytest.raises(TypeError):
        result.tool_results[0].content["id"] = "r2"


@pytest.mark.parametrize(
    ("input_type", "payload"),
    [
        (
            "user.turn",
            DeferredActionPayload(
                action_id="action-1",
                kind="follow_up",
                scheduled_for=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
                revision=1,
                prompt="Follow up.",
            ),
        ),
        ("reminder.fired", UserTurnPayload()),
        (
            "deferred_action.fire",
            ReminderFirePayload(
                fire_id="rem-1:2026-05-01T01:00:00+00:00",
                reminder_id="rem-1",
                title="drink water",
                scheduled_for=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
            ),
        ),
    ],
)
def test_agent_input_rejects_mismatched_input_type_and_payload(input_type, payload):
    scheduled_for = datetime(2026, 5, 1, 1, 0, tzinfo=UTC)

    with pytest.raises((TypeError, ValueError)):
        AgentInput(
            input_type=input_type,
            conversation_id="conv-1",
            text="wrong payload",
            payload=payload,
            occurred_at=scheduled_for,
        )
