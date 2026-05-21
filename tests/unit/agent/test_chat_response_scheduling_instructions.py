from datetime import UTC, datetime
import sys
import types
from types import SimpleNamespace

sys.modules.setdefault("agent.agno_agent.agents", types.ModuleType("agents"))

from agent.agno_agent.runtime.chat_response_instructions import (
    build_chat_response_instructions,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload


def test_scheduling_tool_boundary_is_present():
    run_context = SimpleNamespace(
        current_time=datetime(2026, 6, 1, tzinfo=UTC),
        user=SimpleNamespace(id="ck_a", nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        platform="business",
    )
    text = build_chat_response_instructions(
        run_context,
        AgentInput(
            input_type="user.turn",
            conversation_id="conv_1",
            text="show my user link",
            payload=UserTurnPayload(),
            occurred_at=datetime(2026, 6, 1, tzinfo=UTC),
        ),
    )

    assert "Scheduling tool boundary:" in text
    assert "A-side link management" in text
    assert "B-side appointment actions" in text
    assert "Do not create appointment state from ordinary calendar discussion" in text
    assert "Do not reveal raw user-link codes" in text
    assert "confirm before irreversible scheduling changes" in text
