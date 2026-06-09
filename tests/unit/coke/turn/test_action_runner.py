from __future__ import annotations

from coke.turn.action_runner import ActionRunner
from coke.turn.agent import DomainExecutionResult, ToolExecutionResult
from coke.turn.reminder_list_render import render_reminder_list_reply


class FakeReminderTool:
    def __init__(self, result: ToolExecutionResult) -> None:
        self.result = result
        self.calls = []

    def execute_without_staging(self, command, guard):
        self.calls.append((command, guard))
        return self.result


def test_plain_reminder_list_returns_validated_template_reply_and_tool_event():
    facts = {
        "count": 2,
        "reminders": [
            {"content": "pay rent", "display_time_label": "Today 6:00 PM"},
            {"content": "buy milk"},
        ],
    }
    domain_result = DomainExecutionResult(
        domain="reminder",
        intent="list reminders",
        action="list_reminders",
        effect="listed",
        intent_fulfilled=True,
        visible_summary="Active reminder count: 2.",
        reply_contract="render_reminder_list",
        privacy_notes=("Only describe reminders for this account.",),
    )
    tool = FakeReminderTool(
        ToolExecutionResult(ok=True, facts=facts, domain_result=domain_result)
    )
    guard = object()

    result = ActionRunner().run_plain_reminder_list(
        account_id="account_1",
        display_timezone="Asia/Tokyo",
        user_text="list my reminders",
        reminder_tool=tool,
        guard=guard,
    )

    assert result.handled is True
    assert result.validated.valid is True
    assert result.validated.kind == "reply"
    assert result.validated.segments == (
        render_reminder_list_reply(
            facts,
            user_text="list my reminders",
            account_id="account_1",
        ),
    )
    assert tool.calls == [
        (
            {
                "operation": "list_reminders",
                "owner_account_id": "account_1",
                "display_timezone": "Asia/Tokyo",
            },
            guard,
        )
    ]
    assert result.tool_events == (
        {
            "ok": True,
            "facts": facts,
            "reason_code": None,
            "domain_result": {
                "domain": "reminder",
                "intent": "list reminders",
                "action": "list_reminders",
                "effect": "listed",
                "intent_fulfilled": True,
                "visible_summary": "Active reminder count: 2.",
                "reply_contract": "render_reminder_list",
                "privacy_notes": ("Only describe reminders for this account.",),
            },
        },
    )


def test_plain_reminder_list_falls_back_without_fabricating_reply_on_tool_failure():
    tool = FakeReminderTool(
        ToolExecutionResult(
            ok=False,
            facts={"type": "database_unavailable"},
            reason_code="database_unavailable",
        )
    )

    result = ActionRunner().run_plain_reminder_list(
        account_id="account_1",
        display_timezone="Asia/Tokyo",
        user_text="list my reminders",
        reminder_tool=tool,
        guard=object(),
    )

    assert result.handled is False
    assert result.validated is None
    assert result.tool_events[0]["ok"] is False
    assert result.tool_events[0]["reason_code"] == "database_unavailable"
