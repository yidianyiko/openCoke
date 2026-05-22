import json

import pytest
from agno.tools import Function

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.agent_runtime import build_capability_tool_wrappers
from agent.agno_agent.runtime.result import CapabilityResult


def _run_context() -> AgentRunContext:
    from datetime import UTC, datetime

    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
    )


def test_build_capability_tool_wrappers_rejects_retired_reminder_intent_wrapper():
    with pytest.raises(
        ValueError, match="Unsupported capability tool: reminder_intent"
    ):
        build_capability_tool_wrappers(
            ports={"reminder_intent": object()},
            run_context=_run_context(),
            input_message="提醒我喝水",
            tool_results=[],
        )


@pytest.mark.asyncio
async def test_envelope_content_is_json_serializable_for_nested_results():
    captured: list[CapabilityResult] = []

    class StubTimezonePort:
        def run(self, input_message, run_context, args):
            return CapabilityResult(
                name="timezone",
                ok=True,
                content={
                    "visible_summary": "已切换时区",
                    "state": {"timezone": "Asia/Tokyo"},
                },
                metadata={"durable_write": True},
            )

    wrappers = build_capability_tool_wrappers(
        ports={"timezone": StubTimezonePort()},
        run_context=_run_context(),
        input_message="set timezone",
        tool_results=captured,
    )

    envelope = await wrappers["timezone"](action="direct_set")

    assert envelope["content"]["state"] == {"timezone": "Asia/Tokyo"}
    json.dumps(envelope)


@pytest.mark.asyncio
async def test_model_arguments_cannot_spoof_wrapper_internal_tool_name():
    captured: list[CapabilityResult] = []
    received_args = {}

    class StubTimezonePort:
        def run(self, input_message, run_context, args):
            received_args.update(args)
            return CapabilityResult(
                name="timezone",
                ok=True,
                content={"visible_summary": "已切换时区"},
            )

    wrappers = build_capability_tool_wrappers(
        ports={"timezone": StubTimezonePort()},
        run_context=_run_context(),
        input_message="set timezone",
        tool_results=captured,
    )

    envelope = await wrappers["timezone"](action="direct_set")

    assert envelope["name"] == "timezone"
    assert received_args == {"action": "direct_set", "timezone": "", "decision": ""}


def test_agno_function_schema_exposes_top_level_tool_arguments():
    class StubTimezonePort:
        def run(self, input_message, run_context, args):
            return CapabilityResult(
                name="timezone",
                ok=True,
                content={"visible_summary": "已切换时区"},
            )

    wrappers = build_capability_tool_wrappers(
        ports={"timezone": StubTimezonePort()},
        run_context=_run_context(),
        input_message="set timezone",
        tool_results=[],
    )

    function = Function.from_callable(wrappers["timezone"], name="timezone")

    assert "kwargs" not in function.parameters["properties"]
    assert "action" in function.parameters["properties"]
    assert "timezone" in function.parameters["properties"]
    assert "decision" in function.parameters["properties"]


def test_timezone_schema_restricts_action_to_runtime_contract():
    class StubTimezonePort:
        def run(self, input_message, run_context, args):
            return CapabilityResult(
                name="timezone",
                ok=True,
                content={"visible_summary": "已切换时区"},
            )

    wrappers = build_capability_tool_wrappers(
        ports={"timezone": StubTimezonePort()},
        run_context=_run_context(),
        input_message="set timezone",
        tool_results=[],
    )

    function = Function.from_callable(wrappers["timezone"], name="timezone")

    assert function.parameters["properties"]["action"]["enum"] == [
        "direct_set",
        "proposal",
        "confirm",
    ]
