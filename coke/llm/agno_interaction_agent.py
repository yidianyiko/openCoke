from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any, Mapping
from uuid import uuid4

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.memory.manager import MemoryManager as AgnoMemoryManager

from coke.llm.config import SiliconFlowLLMConfig
from coke.turn.agent import AgentRequest, AgentResult, StateChangingToolPort

AgentFactory = Callable[..., Any]
TaskIdFactory = Callable[[], str]
_LIST_TOOL_FIELDS = frozenset(
    {
        "participants",
        "participant_account_ids",
        "receiver_account_ids",
        "receiver_names",
        "receivers",
        "friend_account_ids",
    }
)


class ToolArgumentError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class CokeAgnoMemoryManager(AgnoMemoryManager):
    def __init__(self, *, model, db, long_term_enabled: bool) -> None:
        super().__init__(
            model=model,
            db=db,
            add_memories=long_term_enabled,
            update_memories=long_term_enabled,
        )
        self.long_term_enabled = long_term_enabled


class AgnoInteractionAgent:
    def __init__(
        self,
        *,
        model,
        config: SiliconFlowLLMConfig | None = None,
        agent_factory: AgentFactory = Agent,
        db: Any | None = None,
        memory_manager_factory: Callable[..., Any] = CokeAgnoMemoryManager,
        task_id_factory: TaskIdFactory | None = None,
    ) -> None:
        self.model = model
        self.config = config
        self.agent_factory = agent_factory
        self.db = db if db is not None else self._build_db(config)
        self.memory_manager_factory = memory_manager_factory
        self.task_id_factory = task_id_factory or (lambda: f"agno_task_{uuid4().hex}")
        self._async_requests: dict[str, AgentRequest] = {}

    @classmethod
    def from_config(cls, config: SiliconFlowLLMConfig) -> AgnoInteractionAgent:
        return cls(model=config.create_interaction_model(), config=config)

    def invoke(self, request: AgentRequest) -> AgentResult:
        return self._run_request(request, store_timeout=True)

    def complete_async(self, task_id: str) -> AgentResult:
        request = self._async_requests.pop(task_id, None)
        if request is None:
            raise ValueError("async_task_not_found")
        return self._run_request(request, store_timeout=False)

    def _run_request(
        self, request: AgentRequest, *, store_timeout: bool
    ) -> AgentResult:
        long_term_enabled = bool(request.trusted_facts.get("memory_enabled", True))
        agent = self.agent_factory(
            model=self.model,
            db=self.db,
            memory_manager=self._memory_manager(long_term_enabled),
            enable_agentic_memory=False,
            update_memory_on_run=False,
            enable_user_memories=long_term_enabled,
            add_memories_to_context=long_term_enabled,
            add_history_to_context=True,
            add_session_state_to_context=False,
            tools=self._tools(request),
            system_message=self._system_message(request),
            instructions=self._instructions(),
            use_json_mode=True,
            parse_response=False,
        )
        try:
            run_output = agent.run(
                _agent_input(request),
                user_id=request.account_id,
                session_id=request.conversation_id,
                metadata={
                    "turn_id": request.turn_id,
                    "trigger_type": request.trigger_type,
                    "mode": str(request.mode),
                },
                add_session_state_to_context=False,
            )
        except TimeoutError:
            if not store_timeout:
                return AgentResult.timeout(self.task_id_factory())
            task_id = self.task_id_factory()
            self._async_requests[task_id] = request
            return AgentResult.timeout(task_id)
        return AgentResult.completed(
            _mapping_or_none(getattr(run_output, "content", None))
        )

    def _memory_manager(self, long_term_enabled: bool):
        if self.db is None:
            return None
        return self.memory_manager_factory(
            model=self.model,
            db=self.db,
            long_term_enabled=long_term_enabled,
        )

    def _tools(self, request: AgentRequest) -> list[Callable]:
        tools: list[Callable] = []
        for name in request.tool_profile.tool_names:
            port = getattr(request.tool_profile, f"{name}_tool")
            if port is not None:
                tools.append(_tool_callable(name, port, request))
        return tools

    def _system_message(self, request: AgentRequest) -> str:
        assistant_name = request.trusted_facts.get("assistant_name") or "Coke"
        persona = request.trusted_facts.get("persona") or ""
        speaking_style = request.trusted_facts.get("speaking_style") or ""
        extra_rules = request.trusted_facts.get("extra_rules") or ""
        return "\n".join(
            part
            for part in (
                f"You are {assistant_name}, the single Coke Interaction Agent.",
                str(persona),
                str(speaking_style),
                str(extra_rules),
                "Use only trusted_facts and tool results for product claims.",
                "Treat the User message section as the actual user turn. Treat Trusted context as supporting facts, not as the user request.",
                "Return only JSON matching the Coke output protocol: "
                '{"type":"reply","segments":["text"]} or '
                '{"type":"no_reply","reason":"intentional_no_reply"}.',
                "Do not emit fallback prose, parser repair text, or template summaries.",
            )
            if part
        )

    def _instructions(self) -> list[str]:
        return [
            "You own user-visible prose for replies, reminders, notifications, and render turns.",
            "Call tools for state-changing domain work instead of claiming the action happened.",
            "For reminder, scheduling, friendship, settings, or calendar-import requests, call the matching tool before replying.",
            "For natural-language reminder creation, call reminder_tool with operation=detect_and_create, owner_account_id from trusted_facts.account_id, raw_text from the User message, and captured_timezone from trusted_facts.default_timezone.",
            "For friend link/code requests, call social_scheduling_tool with operation=get_friend_link and owner_account_id from trusted_facts.account_id.",
            "For adding a friend from an invite code or link token, call social_scheduling_tool with operation=establish_friendship_from_token, joiner_account_id from trusted_facts.account_id, and link_code or public_token from the User message.",
            "For shared-reminder creation, call social_scheduling_tool with operation=create_shared_reminder, creator_account_id from trusted_facts.account_id, receiver_account_ids as account IDs of active friends, title, local_trigger_at, captured_timezone from trusted_facts.default_timezone when unspecified, duration_minutes, and context.",
            "Do not answer as if the action happened until the tool result says it happened.",
            "For any state-changing tool result from reminder, social_scheduling, settings, or calendar-import, report success only when ok=true; when ok=false, reason_code is present, or status starts with needs_, must not claim the action succeeded and should ask the required follow-up or report the failure honestly.",
            "If no user-visible message is warranted, return the explicit no_reply JSON.",
            "Text output is limited to one to three non-empty segments.",
        ]

    def _input_payload(self, request: AgentRequest) -> dict[str, Any]:
        return _support_payload(request)

    def _build_db(self, config: SiliconFlowLLMConfig | None):
        if config is None or config.agno_database_url is None:
            return None
        return PostgresDb(
            db_url=config.agno_database_url,
            create_schema=config.agno_create_schema,
        )


def _tool_callable(
    name: str,
    port: StateChangingToolPort,
    request: AgentRequest,
) -> Callable[..., dict]:
    def tool(command: dict | None = None, **kwargs) -> dict:
        try:
            command_payload = _with_tool_defaults(
                name,
                _command_payload(command, kwargs),
                request,
            )
            result = port.execute(command_payload, request.freshness_guard)
        except ToolArgumentError as error:
            return {
                "ok": False,
                "facts": {"type": error.reason_code},
                "reason_code": error.reason_code,
            }
        return {
            "ok": result.ok,
            "facts": dict(result.facts),
            "reason_code": result.reason_code,
        }

    tool.__name__ = f"{name}_tool"
    tool.__doc__ = _tool_doc(name)
    return tool


def _tool_doc(name: str) -> str:
    if name == "reminder":
        return (
            "Execute a Coke reminder domain command. For a natural-language "
            "create request, call with operation='detect_and_create', "
            "owner_account_id set to trusted_facts.account_id, raw_text set to "
            "the exact User message, captured_timezone set to "
            "trusted_facts.default_timezone, and entry_point='conversation'."
        )
    if name == "social_scheduling":
        return (
            "Execute Coke social scheduling commands. To give the current user "
            "their friend link or invite code, call operation='get_friend_link' "
            "with owner_account_id set to trusted_facts.account_id. "
            "Supported friend-link maintenance operations are "
            "'reset_friend_link' and 'disable_friend_link'. To add a friend "
            "from an invite code or link token, call "
            "operation='establish_friendship_from_token' with "
            "joiner_account_id set to trusted_facts.account_id and link_code "
            "or public_token set from the User message. To create a shared "
            "reminder, call operation='create_shared_reminder' with "
            "creator_account_id set to trusted_facts.account_id, "
            "receiver_account_ids set to active friend account IDs, title, "
            "local_trigger_at, captured_timezone, duration_minutes, and "
            "context."
        )
    return f"Execute a Coke {name} domain command."


def _command_payload(command: Any, kwargs: Mapping[str, Any]) -> Mapping[str, Any]:
    if command is None:
        payload: Any = dict(kwargs)
    elif kwargs:
        payload = {"command": command, **dict(kwargs)}
    else:
        payload = command
    return _normalize_agno_tool_payload(payload)


def _normalize_agno_tool_payload(payload: Any) -> Mapping[str, Any]:
    normalized = _mapping_from_tool_value(payload, "invalid_tool_arguments")
    normalized = _flatten_agno_tool_payload(normalized)
    return _coerce_tool_fields(normalized)


def _mapping_from_tool_value(value: Any, reason_code: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ToolArgumentError(reason_code) from exc
        if isinstance(parsed, Mapping):
            return dict(parsed)
    raise ToolArgumentError(reason_code)


def _flatten_agno_tool_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if set(payload) == {"kwargs"}:
        return _mapping_from_tool_value(payload.get("kwargs"), "invalid_tool_kwargs")
    if "command" not in payload:
        return dict(payload)

    command = payload.get("command")
    nested_kwargs = payload.get("kwargs")
    flattened = (
        {}
        if command is None
        else _mapping_from_tool_value(command, "invalid_tool_command")
    )

    for key, value in payload.items():
        if key not in {"command", "kwargs"}:
            flattened[key] = value

    if nested_kwargs is not None:
        flattened.update(
            _mapping_from_tool_value(nested_kwargs, "invalid_tool_kwargs")
        )
    return flattened


def _coerce_tool_fields(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized = dict(payload)
    for key in _LIST_TOOL_FIELDS:
        if key in normalized:
            normalized[key] = _coerce_list_field(key, normalized[key])
    return normalized


def _coerce_list_field(key: str, value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ToolArgumentError(f"{key}_invalid") from exc
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, str):
                return [parsed]
            raise ToolArgumentError(f"{key}_invalid")
        return [part.strip() for part in stripped.split(",") if part.strip()]
    raise ToolArgumentError(f"{key}_invalid")


def _with_tool_defaults(
    name: str,
    command: Mapping[str, Any],
    request: AgentRequest,
) -> Mapping[str, Any]:
    if name != "reminder":
        return command
    payload = dict(command)
    if "operation" not in payload:
        payload["operation"] = "detect_and_create"
    if payload.get("operation") == "detect_and_create":
        payload.setdefault("raw_text", _user_text(request))
    payload.setdefault("owner_account_id", request.account_id)
    payload.setdefault(
        "captured_timezone",
        str(request.trusted_facts.get("default_timezone") or "UTC"),
    )
    payload.setdefault("entry_point", "conversation")
    return payload


def _mapping_or_none(content: Any) -> Mapping[str, Any] | None:
    if isinstance(content, Mapping):
        return content
    if isinstance(content, str):
        content = _json_text(content)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, Mapping):
            return parsed
    return None


def _agent_input(request: AgentRequest) -> str:
    return "\n\n".join(
        (
            f"User message:\n{_user_text(request)}",
            "Trusted context:\n"
            + json.dumps(
                _support_payload(request),
                ensure_ascii=False,
                default=str,
            ),
        )
    )


def _support_payload(request: AgentRequest) -> dict[str, Any]:
    return {
        "turn_id": request.turn_id,
        "mode": str(request.mode),
        "trigger_type": request.trigger_type,
        "payload": request.payload,
        "trusted_facts": request.trusted_facts,
        "context": _jsonable_context(request.context),
        "tool_profile": {
            "intent_tools_enabled": request.tool_profile.intent_tools_enabled,
            "tool_names": list(request.tool_profile.tool_names),
            "constrained": request.tool_profile.constrained,
        },
    }


def _user_text(request: AgentRequest) -> str:
    text = request.payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return json.dumps(request.payload, ensure_ascii=False, default=str)


def _json_text(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        return stripped.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def _jsonable_context(context: Any) -> Any:
    if isinstance(context, Mapping):
        return dict(context)
    if hasattr(context, "__dict__"):
        return {
            key: value
            for key, value in vars(context).items()
            if not key.startswith("_")
        }
    return str(context)
