from __future__ import annotations

import pytest

from coke.llm.semantic_interpreter import (
    LLMOutputError,
    SiliconFlowSemanticInterpreter,
)
from coke.turn.semantic_interpreter import SemanticInterpreterRequest


class FakeJSONClient:
    def __init__(self, output) -> None:
        self.output = output
        self.calls = []

    def complete_json(self, *, system: str, user: dict, schema_name: str):
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        return self.output


def test_interpret_maps_structured_model_output_to_semantic_decision():
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "reminder_op",
            "language_hint": "zh",
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    decision = interpreter.interpret(_request())

    assert decision.reply_necessity == "reply_needed"
    assert decision.intent_family == "reminder_op"
    assert decision.language_hint == "zh"
    assert client.calls[0]["schema_name"] == "semantic_decision"
    assert (
        "contains_remind_keyword"
        not in client.calls[0]["user"]["allowed_intent_family"]
    )


def test_interpret_rejects_invalid_model_output_without_keyword_fallback():
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "contains_remind_keyword",
            "language_hint": "en",
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    with pytest.raises(LLMOutputError, match="invalid intent_family"):
        interpreter.interpret(_request())


def _request() -> SemanticInterpreterRequest:
    return SemanticInterpreterRequest(
        account_id="account_1",
        conversation_id="conversation_1",
        payload={"text": "remind me tomorrow"},
        trusted_facts={"account_id": "account_1", "memory_enabled": True},
    )
