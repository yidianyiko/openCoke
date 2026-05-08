"""Parity check: native tool-call counts stay within pre-cutover baseline +/- 1."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

_BASELINE_PATH = Path(
    "artifacts/evidence/2026-05-09-pre-cutover-baseline/pre-cutover-tool-call-counts.json"
)

SCENARIOS: dict[str, dict[str, str]] = {
    "reminder_create": {"input_text": "明天 8 点提醒我喝水", "timezone": "Asia/Tokyo"},
    "reminder_update": {"input_text": "把喝水提醒改到明天 9 点", "timezone": "Asia/Tokyo"},
    "reminder_cancel": {"input_text": "取消喝水提醒", "timezone": "Asia/Tokyo"},
    "reminder_list": {"input_text": "看一下我的提醒", "timezone": "Asia/Tokyo"},
    "timezone_direct_set": {"input_text": "帮我把时区改成东京", "timezone": "UTC"},
    "timezone_propose_confirm": {"input_text": "我现在在东京", "timezone": "UTC"},
    "calendar_import_handoff": {
        "input_text": "我想导入 Google Calendar",
        "timezone": "Asia/Tokyo",
    },
    "url_synthesis": {
        "input_text": "简单介绍下 https://example.com 这个页面",
        "timezone": "Asia/Tokyo",
    },
}


pytestmark = pytest.mark.skipif(
    os.environ.get("AGENT_RUNTIME_REAL_MODEL_SMOKE") != "1",
    reason="parity smoke is opt-in via AGENT_RUNTIME_REAL_MODEL_SMOKE=1",
)


def test_native_tool_call_counts_within_baseline_band():
    assert _BASELINE_PATH.exists(), f"baseline not present at {_BASELINE_PATH}"

    import json

    baseline = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    for scenario, expected_count in baseline.items():
        observed = _exercise_scenario(scenario)
        assert abs(observed - expected_count) <= 1, (
            f"scenario={scenario} observed={observed} baseline={expected_count}"
        )


def _exercise_scenario(scenario: str) -> int:
    import asyncio

    from agent.agno_agent.runtime.agent_runtime import run_agent_runtime
    from agent.agno_agent.runtime.context import (
        AgentRunContext,
        TrustedCharacterContext,
        TrustedConversationContext,
        TrustedRelationContext,
        TrustedUserContext,
    )
    from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload

    case = SCENARIOS[scenario]
    ctx = AgentRunContext(
        user=TrustedUserContext(
            id="parity-u",
            nickname="Parity",
            timezone=case.get("timezone", "Asia/Tokyo"),
        ),
        character=TrustedCharacterContext(id="parity-c", nickname="Coke"),
        conversation=TrustedConversationContext(
            id=f"parity-{scenario}", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="parity-u", cid="parity-c"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
        runtime_metadata={"message_source": "user"},
    )
    agent_input = AgentInput(
        input_type="user.turn",
        conversation_id=f"parity-{scenario}",
        text=case["input_text"],
        payload=UserTurnPayload(current_message_ids=[f"parity-msg-{scenario}"]),
        occurred_at=datetime.now(UTC),
    )
    result = asyncio.run(run_agent_runtime(agent_input=agent_input, run_context=ctx))
    return int(result.metrics.get("capability_result_count", 0))
