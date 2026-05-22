from datetime import UTC, datetime
from types import SimpleNamespace

from agent.agno_agent.adapters.reminder_command_executor import ReminderCommandExecutor
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.domain_results import DomainExecutionResult


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key="route-1",
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )


def _tool_reminder_result():
    return {
        "ok": True,
        "action": "create",
        "reminder": {
            "id": "rem-1",
            "owner_user_id": "user-1",
            "title": "drink water",
            "schedule": {
                "anchor_at": "2026-05-22T13:06:00+00:00",
                "local_date": "2026-05-22",
                "local_time": "22:06:00",
                "timezone": "Asia/Tokyo",
                "rrule": None,
            },
            "agent_output_target": {
                "conversation_id": "conv-1",
                "character_id": "char-1",
                "route_key": "route-1",
            },
            "lifecycle_state": "active",
        },
        "summary": "已创建提醒：drink water（2026-05-22 22:06）",
    }


def test_execute_returns_domain_execution_result_with_reminder_facts():
    result = ReminderCommandExecutor(
        lambda **kwargs: _tool_reminder_result(),
        session_state_setter=lambda session_state: None,
    ).execute(
        SimpleNamespace(
            action="create",
            title="drink water",
            trigger_at="2026-05-22T22:06:00+09:00",
            rrule=None,
        ),
        _run_context(),
    )

    assert isinstance(result, DomainExecutionResult)
    assert result.domain == "reminder"
    assert result.outcome == "executed"
    assert result.operations[0].action == "create"
    assert result.operations[0].effect == "write"
    assert result.operations[0].entity_id == "rem-1"
    assert result.operations[0].facts == {
        "title": "drink water",
        "local_date": "2026-05-22",
        "local_time": "22:06:00",
        "timezone": "Asia/Tokyo",
        "rrule": None,
        "conversation_id": "conv-1",
        "character_id": "char-1",
        "route_key": "route-1",
        "lifecycle_state": "active",
        "owner_user_id": "user-1",
    }
    assert result.reply_contract.intent == "confirm_execution"
    assert [item.path for item in result.reply_contract.required_facts] == [
        "operations[0].facts.title",
        "operations[0].facts.local_date",
        "operations[0].facts.local_time",
    ]


def test_execute_returns_failed_domain_result_for_structured_tool_failure():
    result = ReminderCommandExecutor(
        lambda **kwargs: {
            "ok": False,
            "action": "create",
            "error_code": "InvalidArgument",
            "summary": "创建提醒失败：trigger_at is required",
        },
        session_state_setter=lambda session_state: None,
    ).execute(
        SimpleNamespace(action="create", title="drink water"),
        _run_context(),
    )

    assert result.outcome == "failed"
    assert result.error is not None
    assert result.error.code == "InvalidArgument"
    assert result.reply_contract.intent == "report_failure"
    assert result.reply_contract.prohibited_claims == ("reminder_created",)


def test_execute_reply_contract_points_to_first_successful_batch_write():
    result = ReminderCommandExecutor(
        lambda **kwargs: {
            "ok": True,
            "action": "batch",
            "operations": [
                {
                    "ok": False,
                    "action": "create",
                    "error_code": "InvalidSchedule",
                    "summary": "创建提醒失败：这个提醒时间已经过去了",
                },
                _tool_reminder_result(),
            ],
        },
        session_state_setter=lambda session_state: None,
    ).execute(
        SimpleNamespace(action="batch"),
        _run_context(),
    )

    assert [operation.ok for operation in result.operations] == [False, True]
    assert result.operations[1].effect == "write"
    assert [item.path for item in result.reply_contract.required_facts] == [
        "operations[1].facts.title",
        "operations[1].facts.local_date",
        "operations[1].facts.local_time",
    ]
