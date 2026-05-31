from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


ReplyNecessity = Literal["reply_needed", "intentional_no_reply"]
IntentFamily = Literal[
    "chit_chat",
    "reminder_op",
    "scheduling",
    "friend_op",
    "settings",
    "post_reminder_reply",
    "calendar_import",
    "claim",
]
IntentAction = Literal[
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
]
AmbiguityState = Literal[
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
]
RequiredClarification = Literal[
    "none",
    "ask_trigger_time",
    "ask_reminder_content",
    "ask_participant",
    "ask_shared_title",
    "ask_context",
    "ask_reference_choice",
    "ask_friend_identity",
    "ask_timezone_confirmation",
]


@dataclass(frozen=True, slots=True)
class SemanticDecision:
    reply_necessity: ReplyNecessity
    intent_family: IntentFamily
    intent_action: IntentAction = "none"
    ambiguity: AmbiguityState = "none"
    required_clarification: RequiredClarification = "none"
    language_hint: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticInterpreterRequest:
    account_id: str
    conversation_id: str
    payload: dict
    trusted_facts: dict
    focus_subject: Any | None = None


class SemanticInterpreter(Protocol):
    def interpret(self, request: SemanticInterpreterRequest) -> SemanticDecision: ...
