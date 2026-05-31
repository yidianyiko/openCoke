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
            "intent_action": "create_reminder",
            "ambiguity": "missing_time",
            "required_clarification": "ask_trigger_time",
            "language_hint": "zh",
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    decision = interpreter.interpret(_request())

    assert decision.reply_necessity == "reply_needed"
    assert decision.intent_family == "reminder_op"
    assert decision.intent_action == "create_reminder"
    assert decision.ambiguity == "missing_time"
    assert decision.required_clarification == "ask_trigger_time"
    assert decision.language_hint == "zh"
    assert client.calls[0]["schema_name"] == "semantic_decision"
    assert (
        "contains_remind_keyword"
        not in client.calls[0]["user"]["allowed_intent_family"]
    )


def test_interpret_prompt_exposes_typed_actions_ambiguity_and_examples():
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "reminder_op",
            "intent_action": "batch_reminder_ops",
            "ambiguity": "clear",
            "required_clarification": "none",
            "language_hint": "zh",
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    interpreter.interpret(_request())

    call = client.calls[0]
    assert "create_reminder" in call["user"]["allowed_intent_action"]
    assert "clear_trigger_time" in call["user"]["allowed_intent_action"]
    assert "availability_query" in call["user"]["allowed_intent_action"]
    assert "claim_identity" in call["user"]["allowed_intent_action"]
    assert "vague_time" in call["user"]["allowed_ambiguity"]
    assert "ask_trigger_time" in call["user"]["allowed_required_clarification"]
    assert "待会/晚点/过一会" in call["system"]
    assert "must not become a concrete trigger time" in call["system"]
    assert "multi-operation utterance" in call["system"]
    assert "batch_reminder_ops" in call["system"]
    assert "follow-up that only supplies the missing time" in call["system"]
    assert "new topic does not reopen" in call["system"]
    assert "Do not use keyword routing" in call["system"]


@pytest.mark.parametrize(
    ("intent_family", "intent_action"),
    [
        ("reminder_op", "create_reminder"),
        ("reminder_op", "update_reminder"),
        ("reminder_op", "complete_reminder"),
        ("reminder_op", "delete_reminder"),
        ("reminder_op", "list_reminders"),
        ("reminder_op", "batch_reminder_ops"),
        ("reminder_op", "schedule_unscheduled"),
        ("reminder_op", "clear_trigger_time"),
        ("scheduling", "create_shared_reminder"),
        ("scheduling", "cancel_shared_reminder"),
        ("scheduling", "list_shared"),
        ("scheduling", "availability_query"),
        ("friend_op", "get_friend_link"),
        ("friend_op", "add_via_code"),
        ("friend_op", "list_friends"),
        ("friend_op", "remove_friend"),
        ("settings", "update_settings"),
        ("settings", "set_timezone"),
        ("settings", "toggle_proactive"),
        ("settings", "toggle_memory"),
        ("calendar_import", "calendar_import"),
        ("claim", "claim_identity"),
        ("chit_chat", "chit_chat"),
        ("chit_chat", "none"),
    ],
)
def test_interpret_accepts_first_migration_intent_action_set(
    intent_family,
    intent_action,
):
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": intent_family,
            "intent_action": intent_action,
            "ambiguity": "clear",
            "required_clarification": "none",
            "language_hint": "en",
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    decision = interpreter.interpret(_request())

    assert decision.intent_action == intent_action


def test_interpret_rejects_invalid_intent_action_without_fallback():
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "reminder_op",
            "intent_action": "contains_remind_keyword",
            "ambiguity": "clear",
            "required_clarification": "none",
            "language_hint": "en",
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    with pytest.raises(LLMOutputError, match="invalid intent_action"):
        interpreter.interpret(_request())


def test_interpret_rejects_invalid_model_output_without_keyword_fallback():
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "contains_remind_keyword",
            "intent_action": "none",
            "ambiguity": "none",
            "required_clarification": "none",
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
