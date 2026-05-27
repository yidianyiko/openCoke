import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.agno_agent.runtime.focus import build_focus_channel
from agent.agno_agent.runtime.semantic_interpreter import (
    SemanticIntentResult,
    _semantic_interpreter_timeout_seconds,
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
    if ambiguity == "multi_candidate":
        return {
            "current": None,
            "ambiguity": "multi_candidate",
            "candidates": [
                {
                    "action_id": f"{case['id']}-{index}",
                    "kind": kind,
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
                "status": "pending",
                "summary_for_llm": f"{focus['kind']} for {case['id']}",
            }
        ],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )


def test_semantic_intent_result_accepts_known_intents_and_confidence():
    assert SemanticIntentResult.model_validate(
        {"intent": "request_change", "confidence": "medium"}
    ).intent == "request_change"
    assert SemanticIntentResult.model_validate(
        {"intent": "ambiguous", "confidence": "low"}
    ).intent == "ambiguous"


@pytest.mark.parametrize("intent", ["accept", "reject"])
def test_semantic_intent_result_rejects_retired_focus_mutations(intent):
    with pytest.raises(ValidationError):
        SemanticIntentResult.model_validate({"intent": intent, "confidence": "high"})


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
        "create_shared_reminder",
        "cancel_shared_reminder",
        "create_friendship_by_user_link_code",
        "friendship_management",
        "user_link",
        "friend_calendar",
        "list_shared_reminders",
        "ask_detail",
        "request_change",
        "unrelated_utterance",
        "negative_control",
    } <= categories
    negative_controls = {
        case["utterance"]: case["expected_intent"]
        for case in cases
        if case["category"] == "negative_control"
    }
    assert negative_controls["先不要"] == "ambiguous"
    assert negative_controls["先不要急着"] == "ambiguous"
    assert negative_controls["不要现在处理"] == "ambiguous"


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
                "kind": "future_product_candidate",
                "status": "pending",
                "summary_for_llm": "Future product candidate.",
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


def test_semantic_interpreter_default_timeout_covers_production_latency(monkeypatch):
    monkeypatch.delenv("COKE_SEMANTIC_INTERPRETER_TIMEOUT_SECONDS", raising=False)

    assert _semantic_interpreter_timeout_seconds() >= 20.0


@pytest.mark.asyncio
async def test_semantic_interpreter_uses_configured_timeout_and_fails_closed(
    monkeypatch,
):
    monkeypatch.setenv("COKE_SEMANTIC_INTERPRETER_TIMEOUT_SECONDS", "0.001")
    focus = build_focus_channel(
        [
            {
                "action_id": "fr_1",
                "kind": "future_product_candidate",
                "status": "pending",
                "summary_for_llm": "Future product candidate.",
            }
        ],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    class SlowClient:
        async def create(self, *, payload, schema):
            await asyncio.sleep(0.05)
            return {"intent": "create_shared_reminder", "confidence": "high"}

    result = await interpret_semantic_intent(
        focus=focus,
        current_utterance="同意",
        client=SlowClient(),
    )

    assert result.intent == "ambiguous"
    assert result.clarification_reason == "semantic interpreter timed out"
