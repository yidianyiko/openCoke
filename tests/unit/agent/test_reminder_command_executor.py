from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from agent.agno_agent.adapters import ReminderCommandExecutor
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.domain_results import DomainExecutionResult
from agent.agno_agent.schemas.reminder_detect_schema import (
    ReminderDetectDecision,
    ReminderOperation,
)
from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderCreateCommand,
    ReminderQuery,
    ReminderSchedule,
)


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(
            id="user-1",
            nickname="User",
            timezone="Asia/Tokyo",
        ),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key="route-1",
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: remind me to hydrate",
        current_time=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
    )


def _schedule(anchor_at: datetime | None = None) -> ReminderSchedule:
    anchor_at = anchor_at or datetime(2026, 5, 1, 0, 30, tzinfo=UTC)
    return ReminderSchedule(
        anchor_at=anchor_at,
        local_date=anchor_at.date(),
        local_time=anchor_at.time().replace(tzinfo=None),
        timezone="Asia/Tokyo",
        rrule=None,
    )


def _reminder(
    *,
    reminder_id: str = "rem-1",
    owner_user_id: str = "user-1",
    title: str = "hydrate",
    reminder_schedule: ReminderSchedule | None = None,
    target: AgentOutputTarget | None = None,
) -> Reminder:
    now = datetime(2026, 5, 1, 1, 0, tzinfo=UTC)
    return Reminder(
        id=reminder_id,
        owner_user_id=owner_user_id,
        title=title,
        schedule=reminder_schedule or _schedule(),
        agent_output_target=target
        or AgentOutputTarget(
            conversation_id="conv-1",
            character_id="char-1",
            route_key="route-1",
        ),
        created_by_system="agent",
        origin="user",
        visibility="visible",
        fire_mode="notify",
        prompt=None,
        metadata={},
        lifecycle_state="active",
        next_fire_at=now,
        last_fired_at=None,
        last_event_ack_at=None,
        last_error=None,
        created_at=now,
        updated_at=now,
        completed_at=None,
        cancelled_at=None,
        failed_at=None,
    )


def _tool_reminder_result(
    *,
    action: str = "create",
    reminder_id: str = "rem-1",
    title: str = "hydrate",
) -> dict[str, Any]:
    return {
        "ok": True,
        "action": action,
        "reminder": {
            "id": reminder_id,
            "owner_user_id": "user-1",
            "title": title,
            "schedule": {
                "anchor_at": "2026-05-01T00:30:00+00:00",
                "local_date": "2026-05-01",
                "local_time": "09:30:00",
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
        "summary": f"已创建提醒：{title}（2026-05-01 09:30）",
    }


class FakeReminderService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def create(
        self,
        *,
        owner_user_id: str,
        command: ReminderCreateCommand,
    ) -> Reminder:
        self.calls.append(
            ("create", {"owner_user_id": owner_user_id, "command": command})
        )
        return _reminder(
            owner_user_id=owner_user_id,
            title=command.title,
            reminder_schedule=command.schedule,
            target=command.agent_output_target,
        )

    def list_for_user(
        self,
        *,
        owner_user_id: str,
        query: ReminderQuery,
    ) -> list[Reminder]:
        self.calls.append(
            ("list_for_user", {"owner_user_id": owner_user_id, "query": query})
        )
        return []


def _visible_reminder_raw_function():
    from agent.agno_agent.tools.reminder_protocol import visible_reminder_tool

    entrypoint = getattr(visible_reminder_tool, "entrypoint", visible_reminder_tool)
    return getattr(entrypoint, "raw_function", entrypoint)


def test_success_calls_tool_once_with_decision_fields_and_session_state():
    calls = []
    session_states = []

    def tool_entrypoint(**kwargs):
        calls.append(kwargs)
        return _tool_reminder_result()

    def set_session_state(session_state):
        session_states.append(session_state)

    decision = SimpleNamespace(
        action="create",
        title="hydrate",
        trigger_at="2026-05-01T09:00:00+09:00",
    )

    result = ReminderCommandExecutor(
        tool_entrypoint,
        session_state_setter=set_session_state,
    ).execute(
        decision,
        _run_context(),
    )

    assert isinstance(result, DomainExecutionResult)
    assert result.domain == "reminder"
    assert result.outcome == "executed"
    assert result.operations[0].action == "create"
    assert result.operations[0].entity_id == "rem-1"
    assert result.operations[0].facts["title"] == "hydrate"
    assert result.reply_contract.intent == "confirm_execution"
    assert [item.path for item in result.reply_contract.required_facts] == [
        "operations[0].facts.title",
        "operations[0].facts.local_date",
        "operations[0].facts.local_time",
    ]
    assert calls == [
        {
            "action": "create",
            "title": "hydrate",
            "trigger_at": "2026-05-01T09:00:00+09:00",
            "reminder_id": None,
            "keyword": None,
            "new_title": None,
            "new_trigger_at": None,
            "rrule": None,
            "operations": None,
        }
    ]
    assert session_states == [
        {
            "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
            "character": {"id": "char-1"},
            "conversation": {"id": "conv-1", "route_key": "route-1"},
            "platform": "business",
            "current_time": "2026-05-01T01:00:00+00:00",
            "route_key": "route-1",
            "delivery_route_key": "route-1",
        }
    ]


def test_deadline_at_is_preserved_as_rrule_until_for_bounded_recurring_create():
    calls = []

    def tool_entrypoint(**kwargs):
        calls.append(kwargs)
        return _tool_reminder_result()

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="create",
        title="跑步",
        trigger_at="2026-05-10T20:00:00+09:00",
        rrule="FREQ=DAILY",
        deadline_at="2026-12-07T00:00:00+09:00",
        schedule_basis="explicit_cadence",
        schedule_evidence="每天晚上八点",
    )

    result = ReminderCommandExecutor(
        tool_entrypoint,
        session_state_setter=lambda session_state: None,
    ).execute(
        decision,
        _run_context(),
    )

    assert result.outcome == "executed"
    assert calls[0]["rrule"] == "FREQ=DAILY;UNTIL=20261206T150000Z"
    assert "deadline_at" not in calls[0]


def test_dict_decision_input_is_supported_and_empty_operations_becomes_none():
    calls = []

    def tool_entrypoint(**kwargs):
        calls.append(kwargs)
        return _tool_reminder_result(action="update", title="drink water")

    decision = {
        "action": "update",
        "reminder_id": "rem-1",
        "keyword": "hydrate",
        "new_title": "drink water",
        "new_trigger_at": "2026-05-01T10:00:00+09:00",
        "rrule": "FREQ=DAILY",
        "operations": [],
    }

    result = ReminderCommandExecutor(
        tool_entrypoint,
        session_state_setter=lambda session_state: None,
    ).execute(
        decision,
        _run_context(),
    )

    assert result.outcome == "executed"
    assert result.operations[0].action == "update"
    assert result.operations[0].facts["title"] == "drink water"
    assert calls[0]["action"] == "update"
    assert calls[0]["title"] is None
    assert calls[0]["reminder_id"] == "rem-1"
    assert calls[0]["keyword"] == "hydrate"
    assert calls[0]["new_title"] == "drink water"
    assert calls[0]["new_trigger_at"] == "2026-05-01T10:00:00+09:00"
    assert calls[0]["rrule"] == "FREQ=DAILY"
    assert calls[0]["operations"] is None


def test_real_visible_reminder_tool_receives_trusted_context_from_session_state(
    monkeypatch: pytest.MonkeyPatch,
):
    from agent.reminder import runtime as runtime_module
    from agent.reminder.runtime import ReminderRuntime
    from agent.reminder.runtime_contract import ReminderRuntimeContract

    service = FakeReminderService()
    contract = ReminderRuntimeContract(reminder_service=service)
    runtime = ReminderRuntime(
        contract=contract, scheduler=object(), fire_consumer=object()
    )
    monkeypatch.setattr(runtime_module, "_runtime_instance", runtime)

    result = ReminderCommandExecutor(_visible_reminder_raw_function()).execute(
        SimpleNamespace(
            action="create",
            title="hydrate",
            trigger_at="2026-05-01T09:00:00+09:00",
        ),
        _run_context(),
    )

    assert result.outcome == "executed"
    assert result.operations[0].action == "create"
    assert result.operations[0].facts["title"] == "hydrate"
    assert result.operations[0].facts["local_date"] == "2026-05-01"
    assert result.operations[0].facts["local_time"] == "09:00:00"
    [create_call] = service.calls
    assert create_call[0] == "create"
    assert create_call[1]["owner_user_id"] == "user-1"
    command = create_call[1]["command"]
    assert command.schedule.timezone == "Asia/Tokyo"
    assert command.agent_output_target == AgentOutputTarget(
        conversation_id="conv-1",
        character_id="char-1",
        route_key="route-1",
    )


def test_tool_failure_result_is_propagated_as_failed_capability():
    session_states = []

    def tool_entrypoint(**kwargs):
        return {
            "ok": False,
            "action": "create",
            "error_code": "InvalidSchedule",
            "summary": "创建提醒失败：这个提醒时间已经过去了，请告诉我一个未来的时间。",
        }

    result = ReminderCommandExecutor(
        tool_entrypoint,
        session_state_setter=session_states.append,
    ).execute(
        {
            "action": "create",
            "title": "早读",
            "trigger_at": "2026-05-01T07:00:00+09:00",
        },
        _run_context(),
    )

    assert result.outcome == "failed"
    assert result.error is not None
    assert result.error.code == "InvalidSchedule"
    assert result.error.message == (
        "创建提醒失败：这个提醒时间已经过去了，请告诉我一个未来的时间。"
    )
    assert result.reply_contract.intent == "report_failure"
    assert result.reply_contract.prohibited_claims == ("reminder_created",)
    assert result.operations[0].ok is False
    assert result.operations[0].error == result.error


def test_partial_batch_success_is_not_collapsed_to_last_failure():
    session_states = []

    def tool_entrypoint(**kwargs):
        return {
            "ok": True,
            "action": "batch",
            "operations": [
                _tool_reminder_result(title="通知"),
                {
                    "ok": False,
                    "action": "create",
                    "error_code": "InvalidSchedule",
                    "summary": "创建提醒失败：这个提醒时间已经过去了，请告诉我一个未来的时间。",
                },
            ],
        }

    result = ReminderCommandExecutor(
        tool_entrypoint,
        session_state_setter=session_states.append,
    ).execute(
        {
            "action": "batch",
            "operations": [
                {
                    "action": "create",
                    "title": "通知",
                    "trigger_at": "2026-05-11T15:50:00+09:00",
                },
                {
                    "action": "create",
                    "title": "通知",
                    "trigger_at": "2026-05-11T15:00:00+09:00",
                },
            ],
        },
        _run_context(),
    )

    assert result.outcome == "executed"
    assert [operation.ok for operation in result.operations] == [True, False]
    assert result.operations[0].facts["title"] == "通知"
    assert result.operations[1].error is not None
    assert result.operations[1].error.code == "InvalidSchedule"


def test_batch_reply_contract_points_to_first_successful_write_after_failure():
    def tool_entrypoint(**kwargs):
        return {
            "ok": True,
            "action": "batch",
            "operations": [
                {
                    "ok": False,
                    "action": "create",
                    "error_code": "InvalidSchedule",
                    "summary": "创建提醒失败：这个提醒时间已经过去了，请告诉我一个未来的时间。",
                },
                _tool_reminder_result(title="喝水"),
            ],
        }

    result = ReminderCommandExecutor(
        tool_entrypoint,
        session_state_setter=lambda session_state: None,
    ).execute({"action": "batch"}, _run_context())

    assert [operation.ok for operation in result.operations] == [False, True]
    assert result.operations[1].effect == "write"
    assert [item.path for item in result.reply_contract.required_facts] == [
        "operations[1].facts.title",
        "operations[1].facts.local_date",
        "operations[1].facts.local_time",
    ]


def test_batch_operations_from_reminder_detect_decision_are_dicts():
    calls = []

    def tool_entrypoint(**kwargs):
        calls.append(kwargs)
        return _tool_reminder_result()

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="remind me at 9",
        operations=[
            ReminderOperation(
                action="create",
                title="hydrate",
                trigger_at="2026-05-01T09:00:00+09:00",
            )
        ],
    )

    result = ReminderCommandExecutor(
        tool_entrypoint,
        session_state_setter=lambda session_state: None,
    ).execute(decision, _run_context())

    assert result.outcome == "executed"
    assert calls[0]["operations"] == [
        {
            "action": "create",
            "title": "hydrate",
            "trigger_at": "2026-05-01T09:00:00+09:00",
            "reminder_id": "",
            "keyword": "",
            "new_title": "",
            "new_trigger_at": "",
            "rrule": "",
        }
    ]


def test_failure_returns_capability_error_without_raising():
    def tool_entrypoint(**kwargs):
        raise RuntimeError("reminder store unavailable")

    result = ReminderCommandExecutor(
        tool_entrypoint,
        session_state_setter=lambda session_state: None,
    ).execute(
        {"action": "create", "title": "hydrate"},
        _run_context(),
    )

    assert result.outcome == "failed"
    assert result.error is not None
    assert result.error.code == "ReminderCommandExecutorError"
    assert result.error.message == "adapter failed"
    assert result.error.detail == {"error_type": "RuntimeError"}
    assert "reminder store unavailable" not in str(result.error.detail)
