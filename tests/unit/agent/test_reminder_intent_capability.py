from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_runs_detector_and_executor():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(intent_type="crud", action="create", title="drink water")

    class FakeAgent:
        async def arun(self, *, input, session_state):
            assert "drink water" in input
            assert session_state["user"]["id"] == "user-1"
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision is decision
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：drink water"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("18:00 remind me to drink water", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：drink water"


@pytest.mark.asyncio
async def test_reminder_intent_port_accepts_json_string_detector_content():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    detector_content = """
    {
      "intent_type": "crud",
      "action": "batch",
      "schedule_basis": "explicit_occurrences",
      "schedule_evidence": "17:57喝水，每天17:58锻炼",
      "operations": [
        {
          "action": "create",
          "title": "喝水",
          "trigger_at": "2026-05-07T17:57:00+09:00"
        },
        {
          "action": "create",
          "title": "锻炼",
          "trigger_at": "2026-05-07T17:58:00+09:00",
          "rrule": "FREQ=DAILY"
        }
      ]
    }
    """

    class FakeAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=detector_content)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.intent_type == "crud"
            assert received_decision.action == "batch"
            assert [op.title for op in received_decision.operations] == ["喝水", "锻炼"]
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：喝水；已创建提醒：锻炼"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("今天17:57提醒我喝水，每天17:58提醒我锻炼", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：喝水；已创建提醒：锻炼"


@pytest.mark.asyncio
async def test_reminder_intent_port_returns_noop_for_non_reminder():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(intent_type="none", action=None)

    class FakeAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=decision)

    result = await ReminderIntentPort(detector_agent=FakeAgent()).run(
        "hello", _run_context()
    )

    assert result.ok is True
    assert result.content["action"] == "none"
