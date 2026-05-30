from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


ReplyNecessity = Literal["reply_needed", "intentional_no_reply"]
IntentFamily = Literal[
    "chit_chat",
    "reminder_op",
    "scheduling",
    "friend_op",
    "settings",
    "post_reminder_reply",
    "claim",
]


@dataclass(frozen=True, slots=True)
class SemanticDecision:
    reply_necessity: ReplyNecessity
    intent_family: IntentFamily
    language_hint: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticInterpreterRequest:
    account_id: str
    conversation_id: str
    payload: dict
    trusted_facts: dict


class SemanticInterpreter(Protocol):
    def interpret(self, request: SemanticInterpreterRequest) -> SemanticDecision: ...
