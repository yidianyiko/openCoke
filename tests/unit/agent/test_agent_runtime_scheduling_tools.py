import pytest
import sys
import types
from datetime import UTC, datetime
from types import SimpleNamespace

from agno.tools import tool

sys.modules.setdefault("agent.agno_agent.agents", types.ModuleType("agents"))

from agent.agno_agent.runtime import agent_runtime
from agent.agno_agent.runtime.agent_runtime import build_capability_tool_wrappers
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.runtime.scheduling_types import SchedulingBookableWindowPreview

SCHEDULING_TOOL_NAMES = (
    "get_user_link",
    "reset_user_link",
    "disable_user_link",
    "open_bookable_windows",
    "confirm_bookable_windows",
    "query_bookable_windows",
    "request_appointment",
    "confirm_appointment",
    "reject_appointment",
    "cancel_appointment",
    "list_pending_requests",
    "block_service_link",
    "unblock_service_link",
    "remove_service_link",
)


class RecordingPort:
    def __init__(self, name="get_user_link"):
        self.name = name
        self.calls = []

    async def run(self, input_message, run_context, args):
        self.calls.append((input_message, run_context, args))
        return CapabilityResult(
            name=self.name,
            ok=True,
            content={"url": "https://kap.example/u/AbCdEfGhIjK_"},
        )


def _run_context():
    return AgentRunContext(
        user=SimpleNamespace(id="ck_a", nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        relation=SimpleNamespace(uid="ck_a", cid="char_1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 6, 1, tzinfo=UTC),
    )


def test_default_runtime_exposes_all_scheduling_tools(monkeypatch):
    class FakeSchedulingCapabilityPort:
        def __init__(self, *, tool_name):
            self.tool_name = tool_name

    monkeypatch.setattr(
        agent_runtime,
        "SchedulingCapabilityPort",
        FakeSchedulingCapabilityPort,
        raising=False,
    )

    ports = agent_runtime._default_capability_ports()

    assert set(SCHEDULING_TOOL_NAMES).issubset(ports)
    assert ports["get_user_link"].tool_name == "get_user_link"
    assert ports["remove_service_link"].tool_name == "remove_service_link"


@pytest.mark.asyncio
async def test_runtime_scheduling_wrapper_dispatches_model_args():
    port = RecordingPort(name="request_appointment")
    tool_results = []
    context = _run_context()

    wrappers = build_capability_tool_wrappers(
        ports={"request_appointment": port},
        run_context=context,
        input_message="book that slot",
        tool_results=tool_results,
    )
    result = await wrappers["request_appointment"](
        target_account_id="ck_provider",
        window_instance_id="inst_1",
        reason="intro call",
    )

    assert result["name"] == "request_appointment"
    assert result["ok"] is True
    assert port.calls == [
        (
            "book that slot",
            context,
            {
                "target_account_id": "ck_provider",
                "window_instance_id": "inst_1",
                "reason": "intro call",
            },
        )
    ]
    assert [item.name for item in tool_results] == ["request_appointment"]


def test_runtime_scheduling_tool_schema_exposes_top_level_arguments():
    wrappers = build_capability_tool_wrappers(
        ports={"request_appointment": RecordingPort(name="request_appointment")},
        run_context=_run_context(),
        input_message="book that slot",
        tool_results=[],
    )

    function = tool(name="request_appointment")(wrappers["request_appointment"])

    assert "kwargs" not in function.parameters["properties"]
    assert "target_account_id" in function.parameters["properties"]
    assert "window_instance_id" in function.parameters["properties"]
    assert "idempotency_key" in function.parameters["properties"]


def test_runtime_scheduling_tool_schema_exposes_bookable_window_preview_shape():
    wrappers = build_capability_tool_wrappers(
        ports={
            "confirm_bookable_windows": RecordingPort(name="confirm_bookable_windows")
        },
        run_context=_run_context(),
        input_message="confirm these windows",
        tool_results=[],
    )

    function = tool(name="confirm_bookable_windows")(
        wrappers["confirm_bookable_windows"]
    )

    preview_schema = function.parameters["properties"]["preview"]["anyOf"][0]
    assert preview_schema["properties"]["previewId"]["type"] == "string"
    window_schema = preview_schema["properties"]["windows"]["items"]
    assert "rule" in window_schema["properties"]
    assert window_schema["properties"]["fingerprint"]["type"] == "string"


@pytest.mark.asyncio
async def test_runtime_scheduling_wrapper_serializes_preview_model():
    port = RecordingPort(name="confirm_bookable_windows")
    wrappers = build_capability_tool_wrappers(
        ports={"confirm_bookable_windows": port},
        run_context=_run_context(),
        input_message="confirm these windows",
        tool_results=[],
    )

    await wrappers["confirm_bookable_windows"](
        preview=SchedulingBookableWindowPreview(
            previewId="bwp_1",
            windows=[
                {
                    "fingerprint": "fp_1",
                    "rule": {
                        "type": "weekly",
                        "days_of_week": [1],
                        "time_start": "09:00",
                        "time_end": "10:00",
                        "timezone": "Asia/Tokyo",
                        "effective_from": "2026-05-22",
                        "effective_until": None,
                    },
                }
            ],
        )
    )

    assert port.calls[0][2]["preview"]["previewId"] == "bwp_1"
    assert port.calls[0][2]["preview"]["windows"][0]["fingerprint"] == "fp_1"
