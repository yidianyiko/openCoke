from __future__ import annotations

import asyncio
import json
import os
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
    "accept_pending_shared_reminders_from",
    "reject_pending_shared_reminders_from",
    "cancel_pending_shared_reminders_for",
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
    "accept_pending_shared_reminders_from",
    "reject_pending_shared_reminders_from",
    "cancel_pending_shared_reminders_for",
    "send_friend_request_by_user_link_code",
    "accept_friend_request",
    "reject_friend_request",
    "cancel_friend_request",
    "remove_friendship",
    "reset_user_link",
    "disable_user_link",
}
_DEFAULT_SEMANTIC_INTERPRETER_TIMEOUT_SECONDS = 20.0

_SEMANTIC_INTERPRETER_INSTRUCTIONS = (
    """You classify a user's current reply against a trusted product-action focus.
Return only the structured semantic intent.

Rules:
- Use the trusted focus and allowed_actions as the action boundary.
- Interpret natural-language confirmation or rejection semantically, not by fixed keyword matching.
- If the user confirms the focused action, return intent "accept".
- If the user refuses the focused action, return intent "reject".
- If the focus has multiple candidates and the user clearly selects one candidate by ordinal, offered time, or summary text, return "accept" or "reject" with args {"focus_handle": "<selected action_id>"}.
- If the user asks to accept, reject, or cancel all currently focused shared reminders, return the matching bulk shared-reminder intent.
- If the user asks what the focused action is about, return "ask_detail".
- If the user asks to change the focused action rather than accept or reject it, return "request_change".
- If the user is talking about something unrelated to the focused action, return "unrelated".
- If the focus is missing, stale, multi-candidate without a clear selected candidate, or the reply is unclear, return "ambiguous".
- Use high confidence only when the action meaning is clear from the current utterance and trusted focus.
""".strip()
)


class SemanticIntentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: SemanticIntentName
    confidence: SemanticConfidence
    args: dict[str, Any] = Field(default_factory=dict)
    clarification_reason: str = ""


class SemanticIntentLlmClient:
    def __init__(self, agent: Any) -> None:
        self.agent = agent

    async def create(self, *, payload: Mapping[str, Any], schema: Any) -> Any:
        response = await self.agent.arun(
            input=json.dumps(payload, ensure_ascii=False, sort_keys=True)
        )
        content = getattr(response, "content", response)
        if isinstance(content, schema):
            return content
        if isinstance(content, Mapping):
            return schema.model_validate(content)
        if isinstance(content, str) and content.strip():
            try:
                return schema.model_validate_json(content)
            except Exception:
                return content
        return content


def _create_semantic_intent_agent() -> Any:
    from agno.agent import Agent

    from agent.agno_agent.model_factory import create_llm_model

    return Agent(
        id="coke-semantic-interpreter",
        name="CokeSemanticInterpreter",
        model=create_llm_model(role="semantic_interpreter", max_tokens=800),
        instructions=_SEMANTIC_INTERPRETER_INSTRUCTIONS,
        output_schema=SemanticIntentResult,
        structured_outputs=True,
        markdown=False,
    )


def create_semantic_intent_client() -> SemanticIntentLlmClient:
    return SemanticIntentLlmClient(_create_semantic_intent_agent())


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
    timeout_seconds: float | None = None,
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
            timeout=(
                timeout_seconds
                if timeout_seconds is not None
                else _semantic_interpreter_timeout_seconds()
            ),
        )
        result = (
            raw_result
            if isinstance(raw_result, SemanticIntentResult)
            else SemanticIntentResult.model_validate(raw_result)
        )
    except (TimeoutError, asyncio.TimeoutError):
        return _ambiguous("semantic interpreter timed out")
    except (ValidationError, TypeError, ValueError):
        return _ambiguous("semantic interpreter failed closed")
    if result.confidence == "low" and result.intent in _MUTATION_INTENTS:
        return _ambiguous("low confidence mutation intent")
    return result


def _semantic_interpreter_timeout_seconds() -> float:
    raw_value = os.environ.get("COKE_SEMANTIC_INTERPRETER_TIMEOUT_SECONDS")
    if raw_value is None:
        return _DEFAULT_SEMANTIC_INTERPRETER_TIMEOUT_SECONDS
    try:
        value = float(raw_value)
    except ValueError:
        return _DEFAULT_SEMANTIC_INTERPRETER_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_SEMANTIC_INTERPRETER_TIMEOUT_SECONDS


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
