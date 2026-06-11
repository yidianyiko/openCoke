from __future__ import annotations

import json
from typing import Any, Mapping, Protocol

from agno.models.message import Message

from coke.observability.turn_latency import turn_latency_span


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
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=json.dumps(user, ensure_ascii=False)),
        ]
        with turn_latency_span(
            f"llm_json.{schema_name}",
            extra={
                "model_role": schema_name,
                "model": _model_label(self.model),
                "message_count": len(messages),
            },
        ):
            response = self.model.response(
                messages,
                response_format={"type": "json_object"},
            )
        return _mapping_from_content(response.content, schema_name=schema_name)


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


def _model_label(model: Any) -> str:
    for name in ("id", "name", "model", "model_id"):
        value = getattr(model, name, None)
        if isinstance(value, str) and value:
            return value
    return type(model).__name__
