from __future__ import annotations

import json
from typing import Any, Mapping, Protocol

from agno.models.message import Message

from coke.turn.semantic_interpreter import (
    IntentFamily,
    ReplyNecessity,
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
    "claim",
}


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
            system=(
                "Classify this Coke turn semantically. Do not use keyword routing. "
                "Return only JSON with reply_necessity, intent_family, and optional "
                "language_hint. language_hint is non-authoritative."
            ),
            user={
                "account_id": request.account_id,
                "conversation_id": request.conversation_id,
                "payload": request.payload,
                "trusted_facts": request.trusted_facts,
                "allowed_reply_necessity": sorted(REPLY_NECESSITIES),
                "allowed_intent_family": sorted(INTENT_FAMILIES),
            },
            schema_name="semantic_decision",
        )
        reply_necessity = payload.get("reply_necessity")
        if reply_necessity not in REPLY_NECESSITIES:
            raise LLMOutputError("invalid reply_necessity")
        intent_family = payload.get("intent_family")
        if intent_family not in INTENT_FAMILIES:
            raise LLMOutputError("invalid intent_family")
        language_hint = payload.get("language_hint")
        if language_hint is not None and not isinstance(language_hint, str):
            raise LLMOutputError("invalid language_hint")
        return SemanticDecision(
            reply_necessity=reply_necessity,
            intent_family=intent_family,
            language_hint=language_hint,
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
