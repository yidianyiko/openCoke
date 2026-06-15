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
        return _mapping_from_content(
            self._complete_content(
                system=system,
                user=user,
                schema_name=schema_name,
            ),
            schema_name=schema_name,
        )

    def complete_json_list(
        self,
        *,
        system: str,
        user: dict,
        schema_name: str,
    ) -> list[Mapping[str, Any]]:
        return _mappings_from_content(
            self._complete_content(
                system=system,
                user=user,
                schema_name=schema_name,
            ),
            schema_name=schema_name,
        )

    def _complete_content(
        self,
        *,
        system: str,
        user: dict,
        schema_name: str,
    ) -> Any:
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
        return response.content


def _mapping_from_content(content: Any, *, schema_name: str) -> Mapping[str, Any]:
    parsed = _mappings_from_content(content, schema_name=schema_name)
    if len(parsed) == 1:
        return parsed[0]
    raise LLMOutputError(f"invalid {schema_name} shape")


def _mappings_from_content(
    content: Any,
    *,
    schema_name: str,
) -> list[Mapping[str, Any]]:
    parsed = _single_mapping_from_value(content)
    if parsed is not None:
        return [parsed]
    if isinstance(content, str):
        try:
            loaded = json.loads(content)
        except json.JSONDecodeError as error:
            raise LLMOutputError(f"invalid {schema_name} JSON") from error
        parsed = _single_mapping_from_value(loaded)
        if parsed is not None:
            return [parsed]
        parsed_many = _mapping_list_from_value(loaded)
        if parsed_many is not None:
            return parsed_many
    parsed_many = _mapping_list_from_value(content)
    if parsed_many is not None:
        return parsed_many
    raise LLMOutputError(f"invalid {schema_name} shape")


def _single_mapping_from_value(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, (list, tuple)) and len(value) == 1:
        item = value[0]
        if isinstance(item, Mapping):
            return item
    return None


def _mapping_list_from_value(value: Any) -> list[Mapping[str, Any]] | None:
    if not isinstance(value, (list, tuple)) or not value:
        return None
    if not all(isinstance(item, Mapping) for item in value):
        return None
    return list(value)


def _model_label(model: Any) -> str:
    for name in ("id", "name", "model", "model_id"):
        value = getattr(model, name, None)
        if isinstance(value, str) and value:
            return value
    return type(model).__name__
