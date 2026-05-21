from datetime import UTC, datetime
import sys
import types
from types import SimpleNamespace

sys.modules.setdefault("agent.agno_agent.agents", types.ModuleType("agents"))

from agent.agno_agent.runtime.context import AgentRunContext


def _run_context():
    return AgentRunContext(
        user=SimpleNamespace(id="ck_a", nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        relation=SimpleNamespace(uid="ck_a", cid="char_1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
    )


def test_get_user_link_calls_gateway_tool_with_trusted_customer_identity():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    calls = []

    def handler(tool_name, payload):
        calls.append((tool_name, payload))
        return {"ok": True, "data": {"url": "https://kap.example/u/AbCdEfGhIjK_"}}

    port = SchedulingCapabilityPort(tool_name="get_user_link", handler=handler)
    result = port.run(
        "show my link",
        _run_context(),
        {"customer_id": "spoofed", "target_account_id": "ck_b"},
    )

    assert result.ok is True
    assert result.name == "get_user_link"
    assert result.content["url"] == "https://kap.example/u/AbCdEfGhIjK_"
    assert calls == [
        (
            "get_user_link",
            {
                "customer_id": "ck_a",
                "target_account_id": "ck_b",
                "conversation_id": "conv_1",
                "platform": "business",
                "input_message": "show my link",
            },
        )
    ]


def test_request_appointment_forwards_representative_tool_args():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    captured = {}

    def handler(tool_name, payload):
        captured.update({"tool_name": tool_name, "payload": payload})
        return {"ok": True, "data": {"id": "apt_1", "status": "pending_held"}}

    port = SchedulingCapabilityPort(tool_name="request_appointment", handler=handler)
    result = port.run(
        "book that slot",
        _run_context(),
        {
            "target_account_id": "ck_provider",
            "window_instance_id": "inst_1",
            "timezone": "Asia/Shanghai",
            "idempotency_key": "conv_1:inst_1",
        },
    )

    assert result.ok is True
    assert result.content["id"] == "apt_1"
    assert captured["tool_name"] == "request_appointment"
    assert captured["payload"]["customer_id"] == "ck_a"
    assert captured["payload"]["target_account_id"] == "ck_provider"
    assert captured["payload"]["window_instance_id"] == "inst_1"
    assert captured["payload"]["idempotency_key"] == "conv_1:inst_1"
    assert result.visible_summary == "已提交预约请求。"
    assert result.durable_write is True


def test_scheduling_gateway_client_uses_internal_auth():
    from agent.agno_agent.capabilities.scheduling import SchedulingGatewayClient

    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True, "data": {"pending": []}}

    class Session:
        def post(self, url, json, headers, timeout):
            captured.update(
                {"url": url, "json": json, "headers": headers, "timeout": timeout}
            )
            return Response()

    client = SchedulingGatewayClient(
        api_url="https://api.example",
        api_key="internal-key",
        session=Session(),
    )

    assert client.call_tool("list_pending_requests", {"customer_id": "ck_a"}) == {
        "ok": True,
        "data": {"pending": []},
    }
    assert (
        captured["url"]
        == "https://api.example/api/internal/scheduling/tools/list_pending_requests"
    )
    assert captured["headers"]["Authorization"] == "Bearer internal-key"


def test_scheduling_gateway_client_returns_error_envelope():
    from agent.agno_agent.capabilities.scheduling import (
        SchedulingGatewayClient,
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": False, "error": "service_link_not_found"}

    class Session:
        def post(self, url, json, headers, timeout):
            return Response()

    client = SchedulingGatewayClient(
        api_url="https://api.example",
        api_key="internal-key",
        session=Session(),
    )

    assert client.call_tool("remove_service_link", {"customer_id": "ck_a"}) == {
        "ok": False,
        "error": "service_link_not_found",
    }


def test_port_turns_gateway_domain_error_into_model_visible_failure():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        return {"ok": False, "error": "service_link_not_found"}

    port = SchedulingCapabilityPort(tool_name="remove_service_link", handler=handler)

    result = port.run("remove old link", _run_context(), {"other_account_id": "ck_b"})

    assert result.ok is False
    assert result.error == "service_link_not_found"
    assert result.visible_summary == "日程操作暂时无法完成。"
    assert result.durable_write is False


def test_port_turns_gateway_exception_into_model_visible_failure():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    def handler(tool_name, payload):
        raise RuntimeError("gateway unavailable")

    port = SchedulingCapabilityPort(tool_name="request_appointment", handler=handler)

    result = port.run("book that slot", _run_context(), {})

    assert result.ok is False
    assert result.error == "gateway unavailable"
    assert result.visible_summary == "日程操作暂时无法完成。"
    assert result.durable_write is False
