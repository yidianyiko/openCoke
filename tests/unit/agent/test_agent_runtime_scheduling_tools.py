from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from agno.tools import tool

from agent.agno_agent.runtime.domain_results import DomainExecutionResult
from agent.agno_agent.runtime.execution_agents import _make_scheduling_tool_fn
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.runtime.scheduling_types import SchedulingBookableWindowPreview


def _run_context():
    return SimpleNamespace(
        user=SimpleNamespace(id="ck_a", nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        relation=SimpleNamespace(uid="ck_a", cid="char_1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 6, 1, tzinfo=UTC),
    )


class RecordingPort:
    def __init__(self, name="get_user_link"):
        self.name = name
        self.calls = []

    def run(self, input_message, run_context, args):
        self.calls.append((input_message, run_context, args))
        return CapabilityResult(
            name=self.name,
            ok=True,
            content={"url": "https://kap.example/u/AbCdEfGhIjK_"},
        )


@pytest.mark.asyncio
async def test_scheduling_tool_fn_dispatches_model_args():
    port = RecordingPort(name="request_appointment")
    domain_results: list[DomainExecutionResult] = []
    context = _run_context()

    fn = _make_scheduling_tool_fn(
        "request_appointment",
        port,
        input_message="book that slot",
        run_context=context,
        domain_results=domain_results,
    )
    result = await fn(
        target_account_id="ck_provider",
        window_instance_id="inst_1",
        reason="intro call",
    )

    assert result["domain"] == "scheduling"
    assert result["outcome"] == "executed"
    assert result["operations"][0]["action"] == "request_appointment"
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
    assert [item.operations[0].action for item in domain_results] == [
        "request_appointment"
    ]


def test_scheduling_tool_fn_schema_exposes_top_level_arguments():
    fn = _make_scheduling_tool_fn(
        "request_appointment",
        RecordingPort(name="request_appointment"),
        input_message="book that slot",
        run_context=_run_context(),
        domain_results=[],
    )
    function = tool(name="request_appointment")(fn)

    assert "kwargs" not in function.parameters["properties"]
    assert "target_account_id" in function.parameters["properties"]
    assert "window_instance_id" in function.parameters["properties"]
    assert "idempotency_key" in function.parameters["properties"]


def test_scheduling_tool_fn_schema_exposes_bookable_window_preview_shape():
    fn = _make_scheduling_tool_fn(
        "confirm_bookable_windows",
        RecordingPort(name="confirm_bookable_windows"),
        input_message="confirm these windows",
        run_context=_run_context(),
        domain_results=[],
    )
    function = tool(name="confirm_bookable_windows")(fn)

    preview_schema = function.parameters["properties"]["preview"]["anyOf"][0]
    assert preview_schema["properties"]["previewId"]["type"] == "string"
    window_schema = preview_schema["properties"]["windows"]["items"]
    assert "rule" in window_schema["properties"]
    assert window_schema["properties"]["fingerprint"]["type"] == "string"


@pytest.mark.asyncio
async def test_scheduling_tool_fn_serializes_preview_model():
    port = RecordingPort(name="confirm_bookable_windows")
    fn = _make_scheduling_tool_fn(
        "confirm_bookable_windows",
        port,
        input_message="confirm these windows",
        run_context=_run_context(),
        domain_results=[],
    )

    await fn(
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
