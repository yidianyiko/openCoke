from __future__ import annotations

import json
from typing import Any, Mapping, Protocol

from agno.models.message import Message

from coke.turn.semantic_interpreter import (
    AmbiguityState,
    FollowUpAction,
    FollowUpActionScope,
    FollowUpActionType,
    IntentAction,
    IntentFamily,
    ReplyNecessity,
    RequiredClarification,
    SemanticDecision,
    SemanticInterpreterRequest,
)

REPLY_NECESSITIES: set[ReplyNecessity] = {
    "reply_needed",
    "intentional_no_reply",
}
INTENT_FAMILIES: set[IntentFamily] = {
    "chit_chat",
    "reminder_op",
    "scheduling",
    "friend_op",
    "settings",
    "post_reminder_reply",
    "calendar_import",
    "claim",
}
INTENT_ACTIONS: set[IntentAction] = {
    "create_reminder",
    "update_reminder",
    "complete_reminder",
    "delete_reminder",
    "list_reminders",
    "batch_reminder_ops",
    "schedule_unscheduled",
    "clear_trigger_time",
    "create_shared_reminder",
    "cancel_shared_reminder",
    "list_shared",
    "availability_query",
    "get_friend_link",
    "add_via_code",
    "list_friends",
    "remove_friend",
    "update_settings",
    "set_timezone",
    "toggle_proactive",
    "toggle_memory",
    "calendar_import",
    "claim_identity",
    "chit_chat",
    "none",
}
AMBIGUITIES: set[AmbiguityState] = {
    "clear",
    "missing_time",
    "missing_content",
    "missing_participant",
    "missing_title",
    "missing_context",
    "ambiguous_reference",
    "vague_time",
    "follow_up_time",
    "new_topic_after_confirmation",
    "domain_failure",
    "none",
}
REQUIRED_CLARIFICATIONS: set[RequiredClarification] = {
    "none",
    "ask_trigger_time",
    "ask_reminder_content",
    "ask_participant",
    "ask_shared_title",
    "ask_context",
    "ask_reference_choice",
    "ask_friend_identity",
    "ask_timezone_confirmation",
}
FOLLOW_UP_ACTION_TYPES: set[FollowUpActionType] = {
    "resolve_friend_reference_correction",
}
FOLLOW_UP_ACTION_SCOPES: set[FollowUpActionScope] = {
    "immediately_preceding_unresolved_intent",
}

SEMANTIC_SYSTEM_PROMPT = """
Classify this Coke turn semantically. Do not use keyword routing.
Return only JSON with reply_necessity, intent_family, intent_action, ambiguity,
required_clarification, optional language_hint, and optional follow_up_action.
language_hint is non-authoritative.

Ownership:
- SemanticInterpreter chooses high-level product intent, typed action,
  ambiguity, and required clarification.
- Reminder and Social Scheduling detectors own precise fields and executable
  arguments. Do not extract trigger_time, friend IDs, durations, or write
  arguments here.
- Transcript is language evidence only. Trusted facts, focus, domain results,
  and environment are authoritative for product state.

Examples:
- User: "提醒我明天早上9点跑步" -> reminder_op/create_reminder, clear, none.
- User: "提醒我待会/晚点/过一会跑步" -> reminder_op/create_reminder,
  vague_time, ask_trigger_time. Vague time must not become a concrete trigger time.
- User: "提醒我买牛奶，也提醒我给妈妈打电话" -> reminder_op/batch_reminder_ops,
  clear, none. A multi-operation utterance routes as batch_reminder_ops.
- If Coke just asked for a trigger time, a follow-up that only supplies the missing time
  completes the original reminder action as follow-up_time.
- If a reminder was already confirmed and the user starts a new topic, new topic does not reopen
  that already-confirmed reminder.
- If focus has exactly one reminder object_id, reference-only follow-ups to that reminder are not
  ambiguous; classify reminder edits such as duration, content, or time changes as clear
  reminder_op/update_reminder unless another required field is missing.
- Friend list: friend_op/list_friends. Availability: scheduling/availability_query.
- Shared reminder creation with friend names: scheduling/create_shared_reminder.
- A friend reference correction for the immediately preceding unresolved shared-reminder
  intent is a semantic follow_up_action, not runner keyword routes. Emit
  resolve_friend_reference_correction with prior_reference_text, corrected_friend_text,
  and scope immediately_preceding_unresolved_intent only when the user is correcting
  that unresolved friend reference.
- User challenge such as "我没设过这个" or "你是不是搞错了": keep reply_needed,
  identify the challenged product area if clear, and mark ambiguity/domain_failure
  when trusted facts are needed before claiming what happened.
""".strip()


class LLMOutputError(RuntimeError):
    """Raised when a model response is not trusted structured output."""


class JSONCompletionClient(Protocol):
    def complete_json(
        self,
        *,
        system: str,
        user: dict,
        schema_name: str,
    ) -> Mapping[str, Any]: ...


class AgnoJSONCompletionClient:
    def __init__(self, model) -> None:
        self.model = model

    def complete_json(
        self,
        *,
        system: str,
        user: dict,
        schema_name: str,
    ) -> Mapping[str, Any]:
        response = self.model.response(
            [
                Message(role="system", content=system),
                Message(role="user", content=json.dumps(user, ensure_ascii=False)),
            ],
            response_format={"type": "json_object"},
        )
        return _mapping_from_content(response.content, schema_name=schema_name)


class SiliconFlowSemanticInterpreter:
    def __init__(self, client: JSONCompletionClient) -> None:
        self.client = client

    @classmethod
    def from_model(cls, model) -> SiliconFlowSemanticInterpreter:
        return cls(AgnoJSONCompletionClient(model))

    def interpret(self, request: SemanticInterpreterRequest) -> SemanticDecision:
        payload = self.client.complete_json(
            system=SEMANTIC_SYSTEM_PROMPT,
            user={
                "account_id": request.account_id,
                "conversation_id": request.conversation_id,
                "payload": request.payload,
                "trusted_facts": request.trusted_facts,
                "focus_subject": _focus_subject_payload(request.focus_subject),
                "allowed_reply_necessity": sorted(REPLY_NECESSITIES),
                "allowed_intent_family": sorted(INTENT_FAMILIES),
                "allowed_intent_action": sorted(INTENT_ACTIONS),
                "allowed_ambiguity": sorted(AMBIGUITIES),
                "allowed_required_clarification": sorted(REQUIRED_CLARIFICATIONS),
                "allowed_follow_up_action_type": sorted(FOLLOW_UP_ACTION_TYPES),
                "allowed_follow_up_action_scope": sorted(FOLLOW_UP_ACTION_SCOPES),
            },
            schema_name="semantic_decision",
        )
        reply_necessity = _required_enum(payload, "reply_necessity", REPLY_NECESSITIES)
        intent_family = _required_enum(payload, "intent_family", INTENT_FAMILIES)
        intent_action = _required_enum(payload, "intent_action", INTENT_ACTIONS)
        ambiguity = _required_enum(payload, "ambiguity", AMBIGUITIES)
        required_clarification = _required_enum(
            payload,
            "required_clarification",
            REQUIRED_CLARIFICATIONS,
        )
        language_hint = payload.get("language_hint")
        if language_hint is not None and not isinstance(language_hint, str):
            raise LLMOutputError("invalid language_hint")
        follow_up_action = _optional_follow_up_action(payload)
        return SemanticDecision(
            reply_necessity=reply_necessity,
            intent_family=intent_family,
            intent_action=intent_action,
            ambiguity=ambiguity,
            required_clarification=required_clarification,
            language_hint=language_hint,
            follow_up_action=follow_up_action,
        )


def _mapping_from_content(content: Any, *, schema_name: str) -> Mapping[str, Any]:
    if isinstance(content, Mapping):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise LLMOutputError(f"invalid {schema_name} JSON") from error
        if isinstance(parsed, Mapping):
            return parsed
    raise LLMOutputError(f"invalid {schema_name} shape")


def _required_enum(
    payload: Mapping[str, Any],
    field: str,
    allowed: set[Any],
) -> Any:
    value = payload.get(field)
    if value not in allowed:
        raise LLMOutputError(f"invalid {field}")
    return value


def _optional_follow_up_action(payload: Mapping[str, Any]) -> FollowUpAction | None:
    action = payload.get("follow_up_action")
    if action is None:
        return None
    if not isinstance(action, Mapping):
        raise LLMOutputError("invalid follow_up_action")
    action_type = action.get("type")
    if action_type not in FOLLOW_UP_ACTION_TYPES:
        raise LLMOutputError("invalid follow_up_action.type")
    scope = action.get("scope")
    if scope not in FOLLOW_UP_ACTION_SCOPES:
        raise LLMOutputError("invalid follow_up_action.scope")
    prior_reference_text = action.get("prior_reference_text")
    if not isinstance(prior_reference_text, str) or not prior_reference_text.strip():
        raise LLMOutputError("invalid follow_up_action.prior_reference_text")
    corrected_friend_text = action.get("corrected_friend_text")
    if not isinstance(corrected_friend_text, str) or not corrected_friend_text.strip():
        raise LLMOutputError("invalid follow_up_action.corrected_friend_text")
    return FollowUpAction(
        type=action_type,
        prior_reference_text=prior_reference_text,
        corrected_friend_text=corrected_friend_text,
        scope=scope,
    )


def _focus_subject_payload(focus_subject: Any | None) -> dict[str, Any] | None:
    if focus_subject is None:
        return None
    if isinstance(focus_subject, Mapping):
        subject_type = focus_subject.get("subject_type")
        object_ids = focus_subject.get("object_ids")
        ordered = focus_subject.get("ordered", False)
    else:
        subject_type = getattr(focus_subject, "subject_type", None)
        object_ids = getattr(focus_subject, "object_ids", None)
        ordered = getattr(focus_subject, "ordered", False)
    if not isinstance(subject_type, str):
        return None
    if isinstance(object_ids, str):
        return None
    try:
        normalized_object_ids = tuple(str(object_id) for object_id in object_ids or ())
    except TypeError:
        return None
    return {
        "subject_type": subject_type,
        "object_ids": list(normalized_object_ids),
        "ordered": bool(ordered),
    }
