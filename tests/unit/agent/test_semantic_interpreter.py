import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.agno_agent.runtime.focus import build_focus_channel
from agent.agno_agent.runtime.semantic_interpreter import (
    SemanticIntentResult,
    build_semantic_interpreter_input,
    create_semantic_intent_client,
    interpret_semantic_intent,
)

CASES_PATH = Path("tests/fixtures/semantic_router_cases.json")


def _cases():
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def _focus_for_case(case):
    focus = case["focus"]
    ambiguity = focus.get("ambiguity")
    if ambiguity == "multi_pending":
        return {
            "current": None,
            "ambiguity": "multi_pending",
            "candidates": [
                {
                    "action_id": f"{case['id']}-{index}",
                    "kind": kind,
                    "allowed_actions": ("accept", "reject"),
                    "status": "pending",
                    "summary_for_llm": f"{kind} candidate {index}",
                }
                for index, kind in enumerate(focus["candidates"], start=1)
            ],
        }
    if ambiguity == "none_actionable":
        return {"current": None, "ambiguity": "none_actionable", "candidates": []}
    return build_focus_channel(
        [
            {
                "action_id": case["id"],
                "kind": focus["kind"],
                "allowed_actions": ("accept", "reject"),
                "status": "pending",
                "summary_for_llm": f"{focus['kind']} for {case['id']}",
            }
        ],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )


def test_semantic_intent_result_accepts_known_intents_and_confidence():
    assert SemanticIntentResult.model_validate(
        {"intent": "accept", "confidence": "high"}
    ).intent == "accept"
    assert SemanticIntentResult.model_validate(
        {"intent": "request_change", "confidence": "medium"}
    ).intent == "request_change"
    assert SemanticIntentResult.model_validate(
        {"intent": "ambiguous", "confidence": "low"}
    ).intent == "ambiguous"


def test_semantic_intent_result_rejects_unknown_intent():
    with pytest.raises(ValidationError):
        SemanticIntentResult.model_validate(
            {"intent": "keyword_router_guess", "confidence": "high"}
        )


def test_semantic_router_fixture_is_representative_and_has_negative_controls():
    cases = _cases()
    categories = {case["category"] for case in cases}

    assert 30 <= len(cases) <= 50
    assert {
        "single_pending_accept",
        "single_pending_reject",
        "multi_pending_ambiguity",
        "ask_detail",
        "request_change",
        "stale_focus",
        "expired_focus",
        "unrelated_utterance",
        "negative_control",
    } <= categories
    negative_controls = {
        case["utterance"]: case["expected_intent"]
        for case in cases
        if case["category"] == "negative_control"
    }
    assert negative_controls["先不要"] != "reject"
    assert negative_controls["先不要急着"] != "reject"
    assert negative_controls["不要现在处理"] != "reject"


def test_semantic_interpreter_input_contains_only_focus_and_current_utterance():
    payload = build_semantic_interpreter_input(
        focus={"ambiguity": "none_actionable"},
        current_utterance="确认",
    )

    assert set(payload) == {"focus", "current_utterance"}
    assert payload["current_utterance"] == "确认"


def test_create_semantic_intent_client_uses_structured_llm_agent(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            captured["agent_kwargs"] = kwargs

    def fake_create_llm_model(*, role, max_tokens):
        captured["model"] = {"role": role, "max_tokens": max_tokens}
        return object()

    monkeypatch.setattr("agno.agent.Agent", FakeAgent)
    monkeypatch.setattr(
        "agent.agno_agent.model_factory.create_llm_model",
        fake_create_llm_model,
    )

    client = create_semantic_intent_client()

    assert client.agent.kwargs == captured["agent_kwargs"]
    assert captured["model"] == {"role": "semantic_interpreter", "max_tokens": 800}
    assert captured["agent_kwargs"]["output_schema"] is SemanticIntentResult
    assert captured["agent_kwargs"]["structured_outputs"] is True


@pytest.mark.asyncio
async def test_semantic_interpreter_replays_fixture_with_fake_structured_client():
    cases = _cases()

    class FakeClient:
        def __init__(self):
            self.payloads = []

        async def create(self, *, payload, schema):
            self.payloads.append(payload)
            case = cases[len(self.payloads) - 1]
            return {
                "intent": case["expected_intent"],
                "confidence": "high",
                "args": {},
            }

    client = FakeClient()

    for case in cases:
        result = await interpret_semantic_intent(
            focus=_focus_for_case(case),
            current_utterance=case["utterance"],
            client=client,
        )
        assert result.intent == case["expected_intent"]

    assert all(set(payload) == {"focus", "current_utterance"} for payload in client.payloads)


@pytest.mark.asyncio
async def test_semantic_interpreter_fails_closed_without_client_for_single_focus():
    focus = build_focus_channel(
        [
            {
                "action_id": "fr_1",
                "kind": "friend_request",
                "allowed_actions": ("accept", "reject"),
                "status": "pending",
                "summary_for_llm": "好友申请。",
            }
        ],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    result = await interpret_semantic_intent(
        focus=focus,
        current_utterance="同意",
        client=None,
    )

    assert result.intent == "ambiguous"
    assert result.clarification_reason == "semantic interpreter client unavailable"


@pytest.mark.asyncio
async def test_semantic_interpreter_uses_configured_timeout_and_fails_closed(
    monkeypatch,
):
    monkeypatch.setenv("COKE_SEMANTIC_INTERPRETER_TIMEOUT_SECONDS", "0.001")
    focus = build_focus_channel(
        [
            {
                "action_id": "fr_1",
                "kind": "friend_request",
                "allowed_actions": ("accept", "reject"),
                "status": "pending",
                "summary_for_llm": "好友申请。",
            }
        ],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    class SlowClient:
        async def create(self, *, payload, schema):
            await asyncio.sleep(0.05)
            return {"intent": "accept", "confidence": "high"}

    result = await interpret_semantic_intent(
        focus=focus,
        current_utterance="同意",
        client=SlowClient(),
    )

    assert result.intent == "ambiguous"
    assert result.clarification_reason == "semantic interpreter timed out"
