from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderCreateCommand,
    ReminderPatch,
    ReminderQuery,
    ReminderSchedule,
)


NOW = datetime(2026, 4, 28, 1, 0, tzinfo=UTC)


def schedule(
    anchor_at: datetime | None = None,
    timezone: str = "Asia/Tokyo",
    rrule: str | None = None,
) -> ReminderSchedule:
    anchor_at = anchor_at or datetime(2026, 4, 29, 1, 0, tzinfo=UTC)
    return ReminderSchedule(
        anchor_at=anchor_at,
        local_date=anchor_at.date(),
        local_time=anchor_at.time().replace(tzinfo=None),
        timezone=timezone,
        rrule=rrule,
    )


def target(
    conversation_id: str = "conv-1",
    character_id: str = "char-1",
    route_key: str | None = "route-1",
) -> AgentOutputTarget:
    return AgentOutputTarget(
        conversation_id=conversation_id,
        character_id=character_id,
        route_key=route_key,
    )


def reminder(
    reminder_id: str = "rem-1",
    *,
    owner_user_id: str = "user-1",
    title: str = "drink water",
    reminder_schedule: ReminderSchedule | None = None,
    output_target: AgentOutputTarget | None = None,
    lifecycle_state: str = "active",
) -> Reminder:
    return Reminder(
        id=reminder_id,
        owner_user_id=owner_user_id,
        title=title,
        schedule=reminder_schedule or schedule(),
        agent_output_target=output_target or target(),
        created_by_system="agent",
        lifecycle_state=lifecycle_state,
        next_fire_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        last_fired_at=None,
        last_event_ack_at=None,
        last_error=None,
        created_at=NOW,
        updated_at=NOW,
        completed_at=None,
        cancelled_at=None,
        failed_at=None,
    )


class FakeReminderService:
    def __init__(self, reminders: list[Reminder] | None = None) -> None:
        self.reminders = list(reminders or [])
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
        created = reminder(
            f"rem-{len(self.calls)}",
            owner_user_id=owner_user_id,
            title=command.title,
            reminder_schedule=command.schedule,
            output_target=command.agent_output_target,
        )
        self.reminders.append(created)
        return created

    def update(
        self,
        *,
        reminder_id: str,
        owner_user_id: str,
        patch: ReminderPatch,
    ) -> Reminder:
        self.calls.append(
            (
                "update",
                {
                    "reminder_id": reminder_id,
                    "owner_user_id": owner_user_id,
                    "patch": patch,
                },
            )
        )
        title = patch.title or next(
            (item.title for item in self.reminders if item.id == reminder_id),
            "updated",
        )
        updated_schedule = patch.schedule or schedule()
        return reminder(
            reminder_id,
            owner_user_id=owner_user_id,
            title=title,
            reminder_schedule=updated_schedule,
        )

    def cancel(self, *, reminder_id: str, owner_user_id: str) -> Reminder:
        self.calls.append(
            ("cancel", {"reminder_id": reminder_id, "owner_user_id": owner_user_id})
        )
        return reminder(reminder_id, owner_user_id=owner_user_id, title="cancelled")

    def complete(self, *, reminder_id: str, owner_user_id: str) -> Reminder:
        self.calls.append(
            ("complete", {"reminder_id": reminder_id, "owner_user_id": owner_user_id})
        )
        return reminder(reminder_id, owner_user_id=owner_user_id, title="completed")

    def list_for_user(
        self,
        *,
        owner_user_id: str,
        query: ReminderQuery,
    ) -> list[Reminder]:
        self.calls.append(
            ("list_for_user", {"owner_user_id": owner_user_id, "query": query})
        )
        if query.lifecycle_states is None:
            return list(self.reminders)
        return [
            item
            for item in self.reminders
            if item.lifecycle_state in query.lifecycle_states
        ]


class FailingCreateReminderService(FakeReminderService):
    def create(
        self,
        *,
        owner_user_id: str,
        command: ReminderCreateCommand,
    ) -> Reminder:
        self.calls.append(
            ("create", {"owner_user_id": owner_user_id, "command": command})
        )
        raise RuntimeError("database offline")


def call_tool(**kwargs: Any) -> str:
    from agent.agno_agent.tools.reminder_protocol import visible_reminder_tool

    entrypoint = getattr(visible_reminder_tool, "entrypoint", visible_reminder_tool)
    entrypoint = getattr(entrypoint, "raw_function", entrypoint)
    return entrypoint(**kwargs)


def install_service(monkeypatch: pytest.MonkeyPatch, service: FakeReminderService):
    import agent.agno_agent.tools.reminder_protocol.tool as tool_module

    monkeypatch.setattr(tool_module, "ReminderService", lambda: service)


def install_service_factory(monkeypatch: pytest.MonkeyPatch, factory):
    import agent.agno_agent.tools.reminder_protocol.tool as tool_module

    monkeypatch.setattr(tool_module, "ReminderService", factory)


def set_session_state(session_state: dict) -> None:
    from agent.agno_agent.tools.reminder_protocol import set_reminder_session_state

    set_reminder_session_state(session_state)


def test_create_derives_owner_target_and_timezone_from_session_state(monkeypatch):
    service = FakeReminderService()
    install_service(monkeypatch, service)
    session_state = {
        "user": {"id": "user-1", "effective_timezone": "Europe/London"},
        "character": {"id": "char-1"},
        "conversation": {"id": "conv-1"},
        "delivery_route_key": "wechat:personal",
    }
    set_session_state(session_state)

    result = call_tool(
        action="create",
        title="call mom",
        trigger_at="2026-04-29T10:30:00+01:00",
    )

    assert "call mom" in result
    [create_call] = service.calls
    assert create_call[0] == "create"
    assert create_call[1]["owner_user_id"] == "user-1"
    command = create_call[1]["command"]
    assert command.created_by_system == "agent"
    assert command.schedule.timezone == "Europe/London"
    assert command.agent_output_target == AgentOutputTarget(
        conversation_id="conv-1",
        character_id="char-1",
        route_key="wechat:personal",
    )
    assert session_state["reminder_created_with_time"] is True
    assert session_state["tool_results"][0]["ok"] is True
    assert session_state["tool_results"][0]["result_summary"] == (
        "已创建提醒：call mom（2026-04-29 10:30）"
    )


def test_llm_arguments_cannot_override_owner_or_target(monkeypatch):
    service = FakeReminderService()
    install_service(monkeypatch, service)
    session_state = {
        "user": {"_id": 123, "timezone": "Asia/Tokyo"},
        "character": {"_id": "char-session"},
        "conversation": {"_id": "conv-session", "route_key": "route-session"},
    }
    set_session_state(session_state)

    call_tool(
        action="batch",
        operations=[
            {
                "action": "create",
                "title": "secure reminder",
                "trigger_at": "2026-04-29T10:00:00+09:00",
                "owner_user_id": "attacker",
                "agent_output_target": {
                    "conversation_id": "conv-attacker",
                    "character_id": "char-attacker",
                    "route_key": "route-attacker",
                },
            }
        ],
    )

    [create_call] = service.calls
    assert create_call[1]["owner_user_id"] == "123"
    assert create_call[1]["command"].agent_output_target == AgentOutputTarget(
        conversation_id="conv-session",
        character_id="char-session",
        route_key="route-session",
    )


def test_delete_action_maps_to_canonical_cancel(monkeypatch):
    service = FakeReminderService()
    install_service(monkeypatch, service)
    set_session_state(
        {
            "user": {"id": "user-1"},
            "character": {"_id": "char-1"},
            "conversation": {"_id": "conv-1"},
        }
    )

    call_tool(action="delete", reminder_id="rem-1")

    assert service.calls == [
        ("cancel", {"reminder_id": "rem-1", "owner_user_id": "user-1"})
    ]


def test_keyword_update_resolves_by_listing_owner_reminders_and_matching_title(
    monkeypatch,
):
    service = FakeReminderService(
        [
            reminder("rem-1", title="buy milk"),
            reminder("rem-2", title="buy coffee"),
        ]
    )
    install_service(monkeypatch, service)
    set_session_state(
        {
            "user": {"id": "user-1"},
            "character": {"_id": "char-1"},
            "conversation": {"_id": "conv-1"},
        }
    )

    call_tool(action="update", keyword="milk", new_title="buy oat milk")

    assert service.calls[0] == (
        "list_for_user",
        {
            "owner_user_id": "user-1",
            "query": ReminderQuery(lifecycle_states=["active"]),
        },
    )
    assert service.calls[1][0] == "update"
    assert service.calls[1][1]["reminder_id"] == "rem-1"
    assert service.calls[1][1]["patch"].title == "buy oat milk"


def test_ambiguous_keyword_appends_failed_tool_result(monkeypatch):
    service = FakeReminderService(
        [
            reminder("rem-1", title="buy milk"),
            reminder("rem-2", title="buy oat milk"),
        ]
    )
    install_service(monkeypatch, service)
    session_state = {
        "user": {"id": "user-1"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
    }
    set_session_state(session_state)

    result = call_tool(action="update", keyword="milk", new_title="buy soy milk")

    assert "keyword 'milk' matched 2 reminders" in result
    assert session_state["tool_results"] == [
        {
            "tool_name": "提醒操作",
            "ok": False,
            "result_summary": "更新提醒失败：keyword 'milk' matched 2 reminders",
            "extra_notes": "action=update; error_code=AmbiguousReminderKeyword",
        }
    ]
    assert [call[0] for call in service.calls] == ["list_for_user"]


def test_batch_returns_ordered_partial_results(monkeypatch):
    service = FakeReminderService([reminder("rem-1", title="buy milk")])
    install_service(monkeypatch, service)
    session_state = {
        "user": {"id": "user-1", "effective_timezone": "Asia/Tokyo"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
    }
    set_session_state(session_state)

    result = call_tool(
        action="batch",
        operations=[
            {
                "action": "create",
                "title": "drink water",
                "trigger_at": "2026-04-29T10:00:00+09:00",
            },
            {"action": "update", "keyword": "missing", "new_title": "new"},
            {"action": "complete", "reminder_id": "rem-1"},
        ],
    )

    assert result.splitlines()[0].startswith("已创建提醒")
    assert "keyword 'missing' matched 0 reminders" in result.splitlines()[1]
    assert result.splitlines()[2].startswith("已完成提醒")
    assert [item["ok"] for item in session_state["tool_results"]] == [
        True,
        False,
        True,
    ]
    assert [item["result_summary"] for item in session_state["tool_results"]] == [
        "已创建提醒：drink water（2026-04-29 10:00）",
        "更新提醒失败：keyword 'missing' matched 0 reminders",
        "已完成提醒：completed",
    ]


def test_batch_allows_operations_without_top_level_action(monkeypatch):
    service = FakeReminderService()
    install_service(monkeypatch, service)
    session_state = {
        "user": {"id": "user-1", "effective_timezone": "Asia/Tokyo"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
    }
    set_session_state(session_state)

    result = call_tool(
        operations=[
            {
                "action": "create",
                "title": "drink water",
                "trigger_at": "2026-04-29T17:57:00+09:00",
            },
            {
                "action": "create",
                "title": "exercise",
                "trigger_at": "2026-04-29T17:58:00+09:00",
                "rrule": "FREQ=DAILY",
            },
        ],
    )

    assert result.splitlines() == [
        "已创建提醒：drink water（2026-04-29 17:57）",
        "已创建提醒：exercise（每天 17:58）",
    ]
    assert [call[0] for call in service.calls] == ["create", "create"]
    assert [item["ok"] for item in session_state["tool_results"]] == [True, True]


def test_missing_owner_context_appends_failed_tool_result_without_service_call(
    monkeypatch,
):
    service = FakeReminderService()
    install_service(monkeypatch, service)
    session_state = {
        "user": {},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
    }
    set_session_state(session_state)

    result = call_tool(
        action="create",
        title="unsafe",
        trigger_at="2026-04-29T10:00:00+09:00",
    )

    assert result == "创建提醒失败：Reminder owner_user_id is missing"
    assert service.calls == []
    assert session_state["tool_results"] == [
        {
            "tool_name": "提醒操作",
            "ok": False,
            "result_summary": "创建提醒失败：Reminder owner_user_id is missing",
            "extra_notes": "action=create; error_code=InvalidArgument",
        }
    ]
    assert "reminder_created_with_time" not in session_state


@pytest.mark.parametrize(
    "session_state",
    [
        {
            "user": {"id": "user-1"},
            "character": {"_id": "char-1"},
            "conversation": {},
        },
        {
            "user": {"id": "user-1"},
            "character": {},
            "conversation": {"_id": "conv-1"},
        },
    ],
)
def test_missing_target_context_appends_invalid_output_target_failure(
    monkeypatch,
    session_state,
):
    service = FakeReminderService()
    install_service(monkeypatch, service)
    set_session_state(session_state)

    result = call_tool(
        action="create",
        title="missing target",
        trigger_at="2026-04-29T10:00:00+09:00",
    )

    assert result.startswith("创建提醒失败：Reminder output target")
    assert service.calls == []
    assert session_state["tool_results"][0]["ok"] is False
    assert (
        session_state["tool_results"][0]["extra_notes"]
        == "action=create; error_code=InvalidOutputTarget"
    )
    assert "reminder_created_with_time" not in session_state


def test_empty_batch_appends_failed_tool_result(monkeypatch):
    service = FakeReminderService()
    install_service(monkeypatch, service)
    session_state = {
        "user": {"id": "user-1"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
    }
    set_session_state(session_state)

    result = call_tool(action="batch", operations=[])

    assert result == "批量提醒操作失败：operations are required for batch"
    assert service.calls == []
    assert session_state["tool_results"] == [
        {
            "tool_name": "提醒操作",
            "ok": False,
            "result_summary": "批量提醒操作失败：operations are required for batch",
            "extra_notes": "action=batch; error_code=InvalidArgument",
        }
    ]


def test_service_construction_failure_appends_failed_tool_result(monkeypatch):
    def raise_on_construct():
        raise RuntimeError("dao unavailable")

    install_service_factory(monkeypatch, raise_on_construct)
    session_state = {
        "user": {"id": "user-1"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
    }
    set_session_state(session_state)

    result = call_tool(action="list")

    assert result == "提醒操作失败：adapter failure"
    assert session_state["tool_results"] == [
        {
            "tool_name": "提醒操作",
            "ok": False,
            "result_summary": "提醒操作失败：adapter failure",
            "extra_notes": "action=list; error_code=ReminderAdapterError",
        }
    ]


def test_unexpected_service_exception_appends_failed_tool_result(monkeypatch):
    service = FailingCreateReminderService()
    install_service(monkeypatch, service)
    session_state = {
        "user": {"id": "user-1"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
    }
    set_session_state(session_state)

    result = call_tool(
        action="create",
        title="crash",
        trigger_at="2026-04-29T10:00:00+09:00",
    )

    assert result == "创建提醒失败：adapter failure"
    assert session_state["tool_results"] == [
        {
            "tool_name": "提醒操作",
            "ok": False,
            "result_summary": "创建提醒失败：adapter failure",
            "extra_notes": "action=create; error_code=ReminderAdapterError",
        }
    ]
    assert "reminder_created_with_time" not in session_state


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "action": "update",
            "reminder_id": "rem-1",
            "new_trigger_at": "not-a-date",
        },
    ],
)
def test_failed_timed_create_or_update_does_not_set_time_flag(
    monkeypatch,
    kwargs,
):
    service = FakeReminderService([reminder("rem-1", title="old")])
    install_service(monkeypatch, service)
    session_state = {
        "user": {"id": "user-1", "effective_timezone": "Asia/Tokyo"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
    }
    set_session_state(session_state)

    call_tool(**kwargs)

    assert session_state["tool_results"][0]["ok"] is False
    assert "reminder_created_with_time" not in session_state


def test_failed_timed_create_service_error_does_not_set_time_flag(monkeypatch):
    service = FailingCreateReminderService()
    install_service(monkeypatch, service)
    session_state = {
        "user": {"id": "user-1", "effective_timezone": "Asia/Tokyo"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
    }
    set_session_state(session_state)

    call_tool(
        action="create",
        title="service failure",
        trigger_at="2026-04-29T10:00:00+09:00",
    )

    assert session_state["tool_results"][0]["ok"] is False
    assert "reminder_created_with_time" not in session_state


@pytest.mark.parametrize(
    ("kwargs", "expected_flag"),
    [
        (
            {
                "action": "create",
                "title": "timed",
                "trigger_at": "2026-04-29T10:00:00+09:00",
            },
            True,
        ),
        (
            {
                "action": "update",
                "reminder_id": "rem-1",
                "new_trigger_at": "2026-04-29T11:00:00+09:00",
            },
            True,
        ),
        ({"action": "list"}, False),
        ({"action": "cancel", "reminder_id": "rem-1"}, False),
        ({"action": "complete", "reminder_id": "rem-1"}, False),
        ({"action": "update", "reminder_id": "rem-1", "new_title": "title"}, False),
    ],
)
def test_only_successful_timed_create_or_update_sets_time_flag(
    monkeypatch,
    kwargs,
    expected_flag,
):
    service = FakeReminderService([reminder("rem-1", title="old")])
    install_service(monkeypatch, service)
    session_state = {
        "user": {"id": "user-1", "effective_timezone": "Asia/Tokyo"},
        "character": {"_id": "char-1"},
        "conversation": {"_id": "conv-1"},
    }
    set_session_state(session_state)

    call_tool(**kwargs)

    assert ("reminder_created_with_time" in session_state) is expected_flag
