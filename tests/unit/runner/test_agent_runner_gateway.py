import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_main_starts_shared_openclaw_client_and_http_server(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.agent_background_handler",
        SimpleNamespace(background_handler=AsyncMock()),
    )
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.message_processor",
        SimpleNamespace(
            consume_stream_batch=lambda *args, **kwargs: None,
            get_queue_mode=lambda: "poll",
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "agent.runner.agent_handler",
        SimpleNamespace(
            create_handler=lambda worker_id: AsyncMock(),
            _delivery_service=None,
            mongo=SimpleNamespace(),
        ),
    )

    from agent.runner import agent_runner

    openclaw_client = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    app = SimpleNamespace(state=SimpleNamespace())

    monkeypatch.setattr(
        agent_runner,
        "OpenClawClient",
        lambda url, token: openclaw_client,
    )
    monkeypatch.setattr(agent_runner, "create_app", lambda: app)
    monkeypatch.setattr(agent_runner, "background_agents_enabled", lambda: False)
    monkeypatch.setattr(agent_runner, "NUM_WORKERS", 2)
    monkeypatch.setattr(agent_runner, "run_main_agent", AsyncMock())
    monkeypatch.setattr(agent_runner, "run_http_server", AsyncMock())
    monkeypatch.setattr(
        agent_runner,
        "get_config",
        lambda: {
            "gateway": {
                "openclaw_url": "ws://openclaw.example.com",
                "openclaw_token": "token-123",
            }
        },
    )

    await agent_runner.main()

    openclaw_client.start.assert_awaited_once()
    assert app.state.openclaw_client is openclaw_client
    import agent.runner.agent_handler as agent_handler_module

    assert agent_handler_module._delivery_service.openclaw_client is openclaw_client
    agent_runner.run_http_server.assert_awaited_once_with(app)
    agent_runner.run_main_agent.assert_any_await(0)
    agent_runner.run_main_agent.assert_any_await(1)
