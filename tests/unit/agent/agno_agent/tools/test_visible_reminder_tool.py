from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderCreateCommand,
    ReminderSchedule,
)
from agent.reminder.runtime_contract import ReminderRuntimeContract


NOW = datetime(2026, 5, 22, 1, 0, tzinfo=UTC)


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
        return Reminder(
            id="rem-1",
            owner_user_id=owner_user_id,
            title=command.title,
            schedule=command.schedule,
            agent_output_target=command.agent_output_target,
            created_by_system="agent",
            origin="user",
            visibility="visible",
            fire_mode="notify",
            prompt=None,
            metadata={"source": "unit-test"},
            lifecycle_state="active",
            next_fire_at=command.schedule.anchor_at,
            last_fired_at=None,
            last_event_ack_at=None,
            last_error=None,
            created_at=NOW,
            updated_at=NOW,
            completed_at=None,
            cancelled_at=None,
            failed_at=None,
        )


def _call_tool(**kwargs: Any) -> dict[str, Any]:
    from agent.agno_agent.tools.reminder_protocol import visible_reminder_tool

    entrypoint = getattr(visible_reminder_tool, "entrypoint", visible_reminder_tool)
    raw_function = getattr(entrypoint, "raw_function", entrypoint)
    return raw_function(**kwargs)


def _install_contract_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_state: dict[str, Any],
    service: FakeReminderService,
) -> None:
    from agent.agno_agent.tools.reminder_protocol import tool as tool_module

    target = AgentOutputTarget(
        conversation_id="conv-1",
        character_id="char-1",
        route_key="route-1",
    )
    context = SimpleNamespace(
        owner_user_id="user-1",
        target=target,
        timezone="Asia/Tokyo",
    )
    contract = ReminderRuntimeContract(reminder_service=service)
    monkeypatch.setattr(tool_module, "_derive_runtime_context", lambda _state: context)
    monkeypatch.setattr(tool_module, "_build_reminder_runtime", lambda _state: contract)
    tool_module.set_reminder_session_state(session_state)


def test_visible_reminder_tool_returns_created_reminder_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeReminderService()
    session_state: dict[str, Any] = {"test": "session"}
    _install_contract_context(
        monkeypatch,
        session_state=session_state,
        service=service,
    )

    result = _call_tool(
        action="create",
        title="drink water",
        trigger_at="2026-05-22T04:06:00Z",
    )

    assert result["ok"] is True
    assert result["action"] == "create"
    assert result["summary"] == "已创建提醒：drink water（2026-05-22 13:06）"
    assert result["reminder"]["schedule"]["local_date"] == "2026-05-22"
    assert result["reminder"]["schedule"]["local_time"] == "13:06:00"
    assert result["reminder"]["agent_output_target"]["conversation_id"] == "conv-1"
    assert session_state["tool_results"][0]["ok"] is True
    assert session_state["tool_results"][0]["extra_notes"] == "action=create"


def test_visible_reminder_tool_returns_structured_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeReminderService()
    session_state: dict[str, Any] = {"test": "session"}
    _install_contract_context(
        monkeypatch,
        session_state=session_state,
        service=service,
    )

    result = _call_tool(action="create", title="drink water")

    assert result == {
        "ok": False,
        "action": "create",
        "error_code": "InvalidArgument",
        "summary": "创建提醒失败：trigger_at is required",
    }
    assert session_state["tool_results"][0]["ok"] is False
