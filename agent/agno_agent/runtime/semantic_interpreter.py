from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

SemanticIntentName = Literal[
    "accept",
    "reject",
    "ask_detail",
    "request_change",
    "unrelated",
    "ambiguous",
    "create_shared_reminder",
    "accept_shared_reminder",
    "reject_shared_reminder",
    "cancel_shared_reminder",
    "send_friend_request_by_user_link_code",
    "list_friend_requests",
    "accept_friend_request",
    "reject_friend_request",
    "cancel_friend_request",
    "list_friends",
    "remove_friendship",
    "get_user_link",
    "reset_user_link",
    "disable_user_link",
    "list_friend_calendar_facts",
    "list_shared_reminders",
]
SemanticConfidence = Literal["low", "medium", "high"]

_MUTATION_INTENTS = {
    "accept",
    "reject",
    "create_shared_reminder",
    "accept_shared_reminder",
    "reject_shared_reminder",
    "cancel_shared_reminder",
    "send_friend_request_by_user_link_code",
    "accept_friend_request",
    "reject_friend_request",
    "cancel_friend_request",
    "remove_friendship",
    "reset_user_link",
    "disable_user_link",
}


class SemanticIntentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: SemanticIntentName
    confidence: SemanticConfidence
    args: dict[str, Any] = Field(default_factory=dict)
    clarification_reason: str = ""


def build_semantic_interpreter_input(
    *,
    focus: Any,
    current_utterance: str,
) -> dict[str, Any]:
    return {
        "focus": _jsonable_focus(focus),
        "current_utterance": current_utterance,
    }


async def interpret_semantic_intent(
    *,
    focus: Any,
    current_utterance: str,
    client: Any | None = None,
    timeout_seconds: float = 2.0,
) -> SemanticIntentResult:
    payload = build_semantic_interpreter_input(
        focus=focus,
        current_utterance=current_utterance,
    )
    if client is None:
        return _ambiguous("semantic interpreter client unavailable")
    try:
        raw_result = await asyncio.wait_for(
            client.create(payload=payload, schema=SemanticIntentResult),
            timeout=timeout_seconds,
        )
        result = (
            raw_result
            if isinstance(raw_result, SemanticIntentResult)
            else SemanticIntentResult.model_validate(raw_result)
        )
    except (TimeoutError, asyncio.TimeoutError, ValidationError, TypeError, ValueError):
        return _ambiguous("semantic interpreter failed closed")
    if result.confidence == "low" and result.intent in _MUTATION_INTENTS:
        return _ambiguous("low confidence mutation intent")
    return result


def _jsonable_focus(focus: Any) -> Any:
    if focus is None:
        return None
    if isinstance(focus, BaseModel):
        return focus.model_dump(mode="json")
    if isinstance(focus, Mapping):
        return {str(key): _jsonable_focus(value) for key, value in focus.items()}
    if isinstance(focus, (list, tuple)):
        return [_jsonable_focus(value) for value in focus]
    return focus


def _ambiguous(reason: str) -> SemanticIntentResult:
    return SemanticIntentResult(
        intent="ambiguous",
        confidence="low",
        clarification_reason=reason,
    )
