from datetime import UTC, datetime

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
            id="conv-1",
            platform="business",
            route_key=None,
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
    )


def test_url_context_port_is_explicitly_not_a_durable_writer():
    from agent.agno_agent.capabilities.url_context_port import UrlContextPort

    port = UrlContextPort(url_reader=lambda text: {"urls": ["https://example.com"]})

    result = port.run("read https://example.com", _run_context())

    assert result.name == "url_context"
    assert result.ok is True
    assert result.metadata["durable_write"] is False


def test_timezone_port_returns_capability_result():
    from agent.agno_agent.capabilities.timezone_port import TimezonePort

    port = TimezonePort(
        handler=lambda text, context, args: {
            "ok": True,
            "timezone": "Asia/Tokyo",
            "state": {"timezone": "Asia/Tokyo"},
        }
    )

    result = port.run(
        "set timezone to Tokyo",
        _run_context(),
        {"action": "direct_set", "timezone": "Asia/Tokyo"},
    )

    assert result.name == "timezone"
    assert result.ok is True
    assert result.content["timezone"] == "Asia/Tokyo"


def test_calendar_import_port_returns_capability_result():
    from agent.agno_agent.capabilities.calendar_import_port import CalendarImportPort

    port = CalendarImportPort(
        handler=lambda text, context, args: {"ok": True, "status": "queued"}
    )

    result = port.run("import my calendar", _run_context(), {})

    assert result.name == "calendar_import"
    assert result.ok is True
    assert result.content["status"] == "queued"
