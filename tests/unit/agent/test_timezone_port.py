from datetime import UTC, datetime

from agent.agno_agent.capabilities.timezone_port import TimezonePort
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="UTC"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
    )


def test_unsupported_action_is_not_user_visible():
    result = TimezonePort().run("hi", _ctx(), {"action": "get"})

    assert result.ok is False
    assert result.visible_summary is None


def test_set_action_alias_routes_to_direct_timezone_update():
    received = {}

    def handler(input_message, run_context, args):
        received.update(args)
        return {
            "ok": True,
            "message": "已将您的时区更新为东京时间（UTC+9）。",
            "state": {"timezone": "Asia/Tokyo"},
        }

    result = TimezonePort(handler=handler).run(
        "我在日本，帮我改成日本的时区",
        _ctx(),
        {"action": "set", "timezone": "Asia/Tokyo"},
    )

    assert result.ok is True
    assert result.visible_summary == "已将您的时区更新为东京时间（UTC+9）。"
    assert received["action"] == "direct_set"
