from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from coke.llm.semantic_interpreter import (
    AgnoJSONCompletionClient,
    LLMOutputError,
    SiliconFlowSemanticInterpreter,
)
from coke.turn.focus import MessageSubject
from coke.turn.semantic_interpreter import SemanticInterpreterRequest


class FakeJSONClient:
    def __init__(self, output) -> None:
        self.output = output
        self.calls = []

    def complete_json(self, *, system: str, user: dict, schema_name: str):
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        return self.output


class FakeModel:
    id = "fake-json-model"

    def __init__(self) -> None:
        self.calls = []

    def response(self, messages, response_format):
        self.calls.append({"messages": messages, "response_format": response_format})
        return SimpleNamespace(content='{"answer": "ok"}')


def test_agno_json_completion_client_emits_safe_latency_event(caplog):
    model = FakeModel()
    client = AgnoJSONCompletionClient(model)

    with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
        payload = client.complete_json(
            system="system prompt must not leak",
            user={"text": "user text must not leak"},
            schema_name="semantic_decision",
        )

    assert payload == {"answer": "ok"}
    record = caplog.records[-1]
    assert record.event_name == "turn_latency_event"
    assert record.getMessage().startswith("turn_latency_event {")
    assert record.phase == "llm_json.semantic_decision"
    assert record.model_role == "semantic_decision"
    assert record.model == "fake-json-model"
    assert record.message_count == 2
    assert not hasattr(record, "prompt")
    assert not hasattr(record, "content")
    assert not hasattr(record, "user")
    assert "must not leak" not in record.getMessage()


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
    assert decision.list_is_plain is False
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
    assert "list_is_plain" in call["system"]
    assert (
        "no keyword, no specific date/time window, no status/kind filter"
        in call["system"]
    )


@pytest.mark.parametrize("list_is_plain", [True, False])
def test_interpret_maps_list_is_plain_for_list_reminder_output(list_is_plain):
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "reminder_op",
            "intent_action": "list_reminders",
            "ambiguity": "clear",
            "required_clarification": "none",
            "list_is_plain": list_is_plain,
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    decision = interpreter.interpret(_request())

    assert decision.list_is_plain is list_is_plain


def test_interpret_defaults_list_is_plain_false_when_absent():
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "reminder_op",
            "intent_action": "list_reminders",
            "ambiguity": "clear",
            "required_clarification": "none",
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    decision = interpreter.interpret(_request())

    assert decision.list_is_plain is False


def test_interpret_forces_list_is_plain_false_for_non_list_intent():
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "reminder_op",
            "intent_action": "create_reminder",
            "ambiguity": "clear",
            "required_clarification": "none",
            "list_is_plain": True,
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    decision = interpreter.interpret(_request())

    assert decision.list_is_plain is False


@pytest.mark.parametrize(
    ("text", "intent_action", "model_list_is_plain", "expected"),
    [
        ("list my reminders", "list_reminders", True, True),
        ("列一下我的提醒", "list_reminders", True, True),
        ("what's on Friday", "list_reminders", False, False),
        ("my gym reminders", "list_reminders", False, False),
        ("show overdue", "list_reminders", False, False),
        ("remind me tomorrow", "create_reminder", True, False),
    ],
)
def test_interpret_list_is_plain_cases(
    text,
    intent_action,
    model_list_is_plain,
    expected,
):
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "reminder_op",
            "intent_action": intent_action,
            "ambiguity": "clear",
            "required_clarification": "none",
            "list_is_plain": model_list_is_plain,
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    decision = interpreter.interpret(
        SemanticInterpreterRequest(
            account_id="account_1",
            conversation_id="conversation_1",
            payload={"text": text},
            trusted_facts={"account_id": "account_1", "memory_enabled": True},
        )
    )

    assert decision.list_is_plain is expected


def test_interpret_accepts_friend_reference_correction_follow_up_action():
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "scheduling",
            "intent_action": "create_shared_reminder",
            "ambiguity": "ambiguous_reference",
            "required_clarification": "none",
            "language_hint": "zh",
            "follow_up_action": {
                "type": "resolve_friend_reference_correction",
                "prior_reference_text": "zihao",
                "corrected_friend_text": "olivers",
                "scope": "immediately_preceding_unresolved_intent",
            },
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    decision = interpreter.interpret(_request())

    assert decision.follow_up_action is not None
    assert decision.follow_up_action.type == "resolve_friend_reference_correction"
    assert decision.follow_up_action.prior_reference_text == "zihao"
    assert decision.follow_up_action.corrected_friend_text == "olivers"
    assert decision.follow_up_action.scope == "immediately_preceding_unresolved_intent"


def test_interpret_rejects_invalid_follow_up_action_type():
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "scheduling",
            "intent_action": "create_shared_reminder",
            "ambiguity": "ambiguous_reference",
            "required_clarification": "none",
            "language_hint": "zh",
            "follow_up_action": {
                "type": "regex_friend_alias",
                "prior_reference_text": "zihao",
                "corrected_friend_text": "olivers",
                "scope": "immediately_preceding_unresolved_intent",
            },
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    with pytest.raises(LLMOutputError, match="invalid follow_up_action.type"):
        interpreter.interpret(_request())


def test_interpret_prompt_exposes_friend_reference_correction_action():
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "scheduling",
            "intent_action": "create_shared_reminder",
            "ambiguity": "ambiguous_reference",
            "required_clarification": "none",
            "language_hint": "zh",
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    interpreter.interpret(_request())

    call = client.calls[0]
    assert (
        "resolve_friend_reference_correction"
        in call["user"]["allowed_follow_up_action_type"]
    )
    assert "friend reference correction" in call["system"]
    assert "immediately_preceding_unresolved_intent" in call["system"]
    assert "not runner keyword routes" in call["system"]


def test_interpret_request_includes_trusted_focus_subject():
    client = FakeJSONClient(
        {
            "reply_necessity": "reply_needed",
            "intent_family": "reminder_op",
            "intent_action": "update_reminder",
            "ambiguity": "clear",
            "required_clarification": "none",
            "language_hint": "zh",
        }
    )
    interpreter = SiliconFlowSemanticInterpreter(client)

    interpreter.interpret(
        SemanticInterpreterRequest(
            account_id="account_1",
            conversation_id="conversation_1",
            payload={"text": "把它改成60分钟"},
            trusted_facts={"account_id": "account_1"},
            focus_subject=MessageSubject(
                subject_type="reminder",
                object_ids=("reminder_1",),
                ordered=True,
            ),
        )
    )

    call = client.calls[0]
    assert call["user"]["focus_subject"] == {
        "subject_type": "reminder",
        "object_ids": ["reminder_1"],
        "ordered": True,
    }
    assert "If focus has exactly one reminder" in call["system"]


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
