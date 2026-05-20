import sys
import types
from unittest.mock import AsyncMock, Mock

import pytest


def _import_background_handler(monkeypatch):
    stub_agent_handler = types.ModuleType("agent.runner.agent_handler")
    stub_agent_handler.handle_message = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "agent.runner.agent_handler", stub_agent_handler)

    from agent.runner import agent_background_handler as background_handler

    return background_handler


def _legacy_attr(name: str) -> str:
    return "".join(name.split("|"))


@pytest.mark.asyncio
async def test_background_handler_skips_legacy_future_and_reminder_pollers(
    monkeypatch,
):
    background_handler = _import_background_handler(monkeypatch)

    check_hold_messages = AsyncMock()
    legacy_future = AsyncMock()
    legacy_reminders = AsyncMock()

    monkeypatch.setattr(background_handler, "check_hold_messages", check_hold_messages)
    monkeypatch.setattr(
        background_handler,
        _legacy_attr("handle_pending_|future_message"),
        legacy_future,
        raising=False,
    )
    monkeypatch.setattr(
        background_handler,
        _legacy_attr("handle_pending_|reminders"),
        legacy_reminders,
        raising=False,
    )
    monkeypatch.setattr(background_handler.time, "time", lambda: 1)

    await background_handler.background_handler()

    check_hold_messages.assert_awaited_once()
    legacy_future.assert_not_awaited()
    legacy_reminders.assert_not_awaited()


@pytest.mark.asyncio
async def test_background_handler_only_runs_hold_recovery(
    monkeypatch,
):
    background_handler = _import_background_handler(monkeypatch)

    check_hold_messages = AsyncMock()
    legacy_proactive = Mock()

    monkeypatch.setattr(background_handler, "check_hold_messages", check_hold_messages)
    monkeypatch.setattr(
        background_handler,
        "handle_proactive_message",
        legacy_proactive,
        raising=False,
    )
    monkeypatch.setattr(background_handler.time, "time", lambda: 2)

    assert not hasattr(background_handler, "proactive_frequency")
    assert not hasattr(background_handler, "descrease_frequency")
    assert not hasattr(background_handler, "decrease_all")
    assert not hasattr(background_handler, "_resolve_target_character")

    await background_handler.background_handler()

    check_hold_messages.assert_awaited_once()
    legacy_proactive.assert_not_called()
