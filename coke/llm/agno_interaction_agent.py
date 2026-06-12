from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass, is_dataclass, replace
from typing import Any, Mapping
from uuid import uuid4

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.memory.manager import MemoryManager as AgnoMemoryManager

from coke.llm.config import ZAILLMConfig
from coke.turn.agent import (
    AgentRequest,
    AgentResult,
    DomainExecutionResult,
    StateChangingToolPort,
)
from coke.turn.context import TurnMode
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.reminder_list_render import looks_chinese as _shared_looks_chinese
from coke.turn.reminder_list_render import (
    render_reminder_list_line as _shared_render_reminder_list_line,
)
from coke.turn.reminder_list_render import (
    render_reminder_list_reply as _shared_render_reminder_list_reply,
)

AgentFactory = Callable[..., Any]
TaskIdFactory = Callable[[], str]
LOGGER = logging.getLogger(__name__)
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
_REMINDER_OP_ALIASES = {
    "list": "list_reminders",
    "count": "list_reminders",
    "complete": "complete_reminder",
    "done": "complete_reminder",
    "delete": "delete_reminder",
    "cancel": "delete_reminder",
    "remove": "delete_reminder",
    "reschedule": "reschedule_reminder",
    "edit": "update_reminder",
    "modify": "update_reminder",
    "update": "update_reminder",
    "modify_time": "reschedule_reminder",
}
_SETTINGS_OP_ALIASES = {
    "timezone": "set_timezone",
    "set_default_timezone": "set_timezone",
    "reset": "reset_agent_settings",
    "reset_settings": "reset_agent_settings",
}
_SHARED_REMINDER_CREATE_OPERATIONS = frozenset(
    {"create_shared_reminder", "detect_and_create_shared_reminder"}
)


@dataclass(frozen=True, slots=True)
class PromptBlock:
    name: str
    content: str


@dataclass(frozen=True, slots=True)
class CokeVoicePolicy:
    normal_segment_limit: str = "1-3 short segments"
    role_texture: str = "WeChat friend or supervisor"
    challenge_examples: tuple[str, ...] = ("我没设过这个", "你是不是搞错了")

    def render(self) -> str:
        examples = " / ".join(self.challenge_examples)
        return "\n".join(
            [
                f"Speak like Coke as a {self.role_texture}: concise, direct, and warm when useful.",
                f"Use {self.normal_segment_limit} as short message-channel segments; match the user's language and rough message length.",
                "Avoid generic closers and generic customer-service openings such as 您好 or 还有什么可以帮您吗.",
                "Do not end ordinary final statement segments with . or 。; keep ? or ! only when the sentence needs it.",
                "Do not expose internal tools, agents, logs, or architecture.",
                "do not invent facts or times; use trusted facts and domain_result for product state.",
                (
                    f"When the user challenges system behavior, for example {examples}, "
                    "acknowledge the confusion, check trusted facts, state only what is known, "
                    "and do not blame the user."
                ),
                (
                    "Do not hard-refuse coding or deep-research chat solely because of Coke's role; "
                    "chat naturally unless a trusted product boundary says an action is unsupported."
                ),
            ]
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
        config: ZAILLMConfig | None = None,
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
    def from_config(cls, config: ZAILLMConfig) -> AgnoInteractionAgent:
        return cls(model=config.create_interaction_model(), config=config)

    def invoke(self, request: AgentRequest) -> AgentResult:
        return self._run_request(request, store_timeout=True)

    async def ainvoke(self, request: AgentRequest) -> AgentResult:
        return await self._arun_request(request, store_timeout=True)

    async def ainvoke_streaming(
        self, request: AgentRequest
    ) -> AsyncIterator[str | AgentResult]:
        agent, tool_events = self._build_agent(request)
        parser = _ReplySegmentStreamParser()
        content_buffer = ""
        final_content: Any = None
        try:
            # Agno's arun returns an AsyncIterator directly when stream=True
            # (it is not a coroutine), so it must NOT be awaited.
            stream = agent.arun(
                _agent_input(request),
                **self._run_kwargs(
                    request,
                    run_id=request.run_id or request.turn_id,
                ),
                stream=True,
                stream_events=True,
            )
        except TimeoutError:
            yield self._timeout_result(request, store_timeout=True)
            return
        except Exception as exc:
            LOGGER.warning(
                "agno_streaming_start_failed",
                extra={"turn_id": request.turn_id, "error_type": type(exc).__name__},
            )
            yield await self._arun_request(request, store_timeout=True)
            return

        if not hasattr(stream, "__aiter__"):
            LOGGER.warning(
                "agno_streaming_unavailable",
                extra={"turn_id": request.turn_id},
            )
            result = _agent_result_from_content(getattr(stream, "content", None))
            yield _enforce_tool_reply_contracts(result, tool_events, request)
            return

        try:
            async for event in stream:
                content = getattr(event, "content", None)
                if _is_completed_stream_event(event):
                    final_content = content
                    continue
                if isinstance(content, str):
                    delta, content_buffer = _stream_text_delta(content_buffer, content)
                    for segment in parser.feed(delta):
                        yield segment
                elif isinstance(content, Mapping):
                    final_content = content
        except TimeoutError:
            yield self._timeout_result(request, store_timeout=True)
            return
        except Exception as exc:
            if parser.emitted_count == 0:
                LOGGER.warning(
                    "agno_streaming_failed_before_segment",
                    extra={
                        "turn_id": request.turn_id,
                        "error_type": type(exc).__name__,
                    },
                )
                yield await self._arun_request(request, store_timeout=True)
                return
            raise

        if final_content is None:
            final_content = content_buffer
        result = _agent_result_from_content(final_content)
        yield _enforce_tool_reply_contracts(result, tool_events, request)

    async def cancel(self, run_id: str) -> bool:
        return bool(await Agent.acancel_run(run_id))

    def complete_async(self, task_id: str) -> AgentResult:
        request = self._async_requests.pop(task_id, None)
        if request is None:
            raise ValueError("async_task_not_found")
        return self._run_request(request, store_timeout=False)

    def _run_request(
        self, request: AgentRequest, *, store_timeout: bool
    ) -> AgentResult:
        agent, tool_events = self._build_agent(request)
        try:
            run_output = agent.run(
                _agent_input(request),
                **self._run_kwargs(request),
            )
        except TimeoutError:
            return self._timeout_result(request, store_timeout=store_timeout)
        result = _agent_result_from_content(getattr(run_output, "content", None))
        return _enforce_tool_reply_contracts(result, tool_events, request)

    async def _arun_request(
        self, request: AgentRequest, *, store_timeout: bool
    ) -> AgentResult:
        agent, tool_events = self._build_agent(request)
        try:
            run_output = await agent.arun(
                _agent_input(request),
                **self._run_kwargs(
                    request,
                    run_id=request.run_id or request.turn_id,
                ),
            )
        except TimeoutError:
            return self._timeout_result(request, store_timeout=store_timeout)
        result = _agent_result_from_content(getattr(run_output, "content", None))
        return _enforce_tool_reply_contracts(result, tool_events, request)

    def _build_agent(self, request: AgentRequest):
        long_term_enabled = bool(request.trusted_facts.get("memory_enabled", True))
        tool_events: list[dict[str, Any]] = []
        agent = self.agent_factory(
            model=self.model,
            db=self.db,
            memory_manager=self._memory_manager(long_term_enabled),
            enable_agentic_memory=False,
            update_memory_on_run=False,
            enable_user_memories=long_term_enabled,
            add_memories_to_context=long_term_enabled,
            add_history_to_context=_add_history_to_context(request),
            add_session_state_to_context=False,
            tools=self._tools(request, tool_events=tool_events),
            system_message=self._system_message(request),
            instructions=self._instructions(),
            use_json_mode=True,
            parse_response=False,
        )
        return agent, tool_events

    def _run_kwargs(
        self,
        request: AgentRequest,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        kwargs = {
            "user_id": request.account_id,
            "session_id": request.conversation_id,
            "metadata": {
                "turn_id": request.turn_id,
                "trigger_type": request.trigger_type,
                "mode": str(request.mode),
            },
            "add_session_state_to_context": False,
        }
        if run_id is not None:
            kwargs["run_id"] = run_id
        return kwargs

    def _timeout_result(
        self,
        request: AgentRequest,
        *,
        store_timeout: bool,
    ) -> AgentResult:
        if not store_timeout:
            return AgentResult.timeout(self.task_id_factory())
        task_id = self.task_id_factory()
        self._async_requests[task_id] = request
        return AgentResult.timeout(task_id)

    def _memory_manager(self, long_term_enabled: bool):
        if self.db is None:
            return None
        return self.memory_manager_factory(
            model=self.model,
            db=self.db,
            long_term_enabled=long_term_enabled,
        )

    def _tools(
        self, request: AgentRequest, *, tool_events: list[dict[str, Any]] | None = None
    ) -> list[Callable]:
        tools: list[Callable] = []
        for name in request.tool_profile.tool_names:
            port = getattr(request.tool_profile, f"{name}_tool")
            if port is not None:
                tools.append(_tool_callable(name, port, request, tool_events))
        return tools

    def _system_message(self, request: AgentRequest) -> str:
        assistant_name = request.trusted_facts.get("assistant_name") or "Coke"
        user_address_name = request.trusted_facts.get("user_address_name") or ""
        persona = request.trusted_facts.get("persona") or ""
        background = request.trusted_facts.get("background") or ""
        speaking_style = request.trusted_facts.get("speaking_style") or ""
        extra_rules = request.trusted_facts.get("extra_rules") or ""
        output_protocol = (
            'Return only JSON matching the Coke output protocol: {"type":"reply","segments":["text"]}.'
            if request.trigger_type == "NotificationTurn"
            else (
                "Return only JSON matching the Coke output protocol: "
                '{"type":"reply","segments":["text"]} or '
                '{"type":"no_reply","reason":"intentional_no_reply"}.'
            )
        )
        return "\n".join(
            part
            for part in (
                f"You are {assistant_name}, the single Coke Interaction Agent.",
                (
                    f"Address the user as {user_address_name} when it is natural."
                    if user_address_name
                    else ""
                ),
                str(persona),
                str(background),
                str(speaking_style),
                str(extra_rules),
                "Use only trusted_facts and tool results for product claims.",
                "Treat the User message section as the actual user turn. Treat Trusted context as supporting facts, not as the user request.",
                "Users can send voice and images; these reach you already converted to text (voice as its transcript, an image as a description of what it shows). Treat that text as the user's real message and respond to its content. Never tell the user you cannot hear voice messages or see images.",
                output_protocol,
                "A final plain-language assistant message without the JSON protocol is invalid and will not be delivered.",
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
            "For reminder list, count, search, or filter requests, call reminder_tool with operation=list_reminders and owner_account_id from trusted_facts.account_id before answering. Pass keyword, status/lifecycle, kind/reminder_type, trigger_after, and trigger_before when the user asks for those filters. When it succeeds, answer with the total count and list every returned active reminder using display_lines or display_time_label from the tool facts; include each reminder's content and local display time, and label reminders without display_time_label as unscheduled/no set time in the user's language. Do not answer with only the count, do not expose raw UTC next_fire_at as the user-visible time when display_time_label is present, and do not say the full list is unavailable unless the tool result fails.",
            "For reminder content or duration edits, call reminder_tool with operation=update_reminder, owner_account_id from trusted_facts.account_id, reminder_id from trusted context, and content and/or duration_minutes. If the user identifies the target only by keyword, pass keyword instead of reminder_id; if the tool returns ambiguous_reminder_reference, ask the user to choose. Do not call reschedule_reminder for duration-only edits.",
            "When a personal reminder tool result is blocked with reason_code=time_conflict or facts.type=time_conflict, say Coke cannot create or move the reminder to that time because it conflicts with an existing reminder, and ask the user to choose another time. Do not ask whether to still use that time, do not imply override or force-create is available, and do not suggest a concrete alternate time unless a tool result checked it.",
            "If the focus block has subject_type='reminder' with exactly one object_id, use that object_id as reminder_id for follow-up edits to that reminder instead of asking which reminder.",
            "For friend link/code requests, call social_scheduling_tool with operation=get_friend_link and owner_account_id from trusted_facts.account_id.",
            "For adding a friend from an invite code or link token, call social_scheduling_tool with operation=establish_friendship_from_token, joiner_account_id from trusted_facts.account_id, and link_code or public_token from the User message.",
            "For friend-list requests, call social_scheduling_tool with operation=list_friends and account_id from trusted_facts.account_id.",
            "For friend-removal requests, call social_scheduling_tool with operation=remove_friend, account_id from trusted_facts.account_id, and friend_account_id from an active friend account ID.",
            "For availability requests, call social_scheduling_tool with operation=query_availability, requester_account_id from trusted_facts.account_id, friend_account_ids as active friend account IDs, local_start, local_end, and requester_timezone from trusted_facts.default_timezone.",
            "For shared-reminder creation from natural language, call social_scheduling_tool with operation=detect_and_create_shared_reminder, creator_account_id from trusted_facts.account_id, receiver_account_ids as account IDs of active friends, raw_text set to the exact User message, captured_timezone from trusted_facts.default_timezone when unspecified, and duration_minutes only when explicit. Do not compute local_trigger_at yourself.",
            "When a shared-reminder creation tool result succeeds, state that the shared reminder is created and immediately active. Never say or imply waiting for confirmation, pending confirmation, pending acceptance, approval, invitation approval, or that receivers need to accept/reject it.",
            "For shared-reminder time or duration changes, call social_scheduling_tool with operation=update_shared_reminder, account_id from trusted_facts.account_id, shared_reminder_id from trusted context or prior tool results, local_trigger_at when changing time, captured_timezone from trusted_facts.default_timezone, and duration_minutes only when explicit. Do not use cancellation to represent a reschedule.",
            "When the user only changes an existing shared reminder time, call social_scheduling_tool with operation=update_shared_reminder, set local_trigger_at, and omit duration_minutes so the service preserves the existing duration. Do not treat a reschedule as a new shared-reminder creation. Do not ask for an end time or duration unless the user explicitly changes duration or the target has no duration.",
            "When shared-reminder update is blocked by conflict, say the old shared reminder remains unchanged and ask for another time; do not suggest a concrete alternate time unless a tool result checked it.",
            "For shared-reminder cancellation requests, call social_scheduling_tool with operation=cancel_shared_reminder, account_id from trusted_facts.account_id, and shared_reminder_id from trusted context or prior tool results.",
            "When a user gives a friend name but not an account ID, call operation=list_friends first. If exactly one active friend matches the request context, use that friend's account_id; otherwise ask a clarification instead of inventing an ID.",
            "For global timezone switches, call settings_tool with operation=set_timezone, account_id from trusted_facts.account_id, and default_timezone as the requested IANA timezone; do not rewrite existing reminders.",
            "For assistant name, user address name, persona, background, speaking style, extra rules, memory, or proactive preference changes, call settings_tool with operation=update_settings and account_id from trusted_facts.account_id; memory_enabled=false stops long-term memory use/addition, and proactive_enabled=false cancels untriggered proactive follow-ups.",
            "For explicit user profile facts such as real name, nickname, description, or relationship description, call settings_tool with operation=update_profile and account_id from trusted_facts.account_id.",
            "For settings reset requests, call settings_tool with operation=reset_agent_settings and account_id from trusted_facts.account_id.",
            "Unsupported external booking, reservation, class, coach, restaurant, ticket, or appointment actions are not reminder creation. Decline gracefully, explain that the user must complete the external action themselves, and offer to set a reminder; call reminder_tool only when the user explicitly asks for a reminder, and never claim the class or appointment is booked.",
            "Do not answer as if the action happened until the tool result says it happened.",
            "For any state-changing tool result from reminder, social_scheduling, settings, or calendar-import, report success only when ok=true; when ok=false, reason_code is present, or status starts with needs_, must not claim the action succeeded and should ask the required follow-up or report the failure honestly.",
            'After any tool call, you MUST emit a final user-facing protocol object: {"type":"reply","segments":["..."]} confirming the real tool result in the user\'s language, or {"type":"no_reply","reason":"intentional_no_reply"} only when no user-visible message is truly warranted; the final message must still be JSON, not plain natural-language text; never end with empty assistant content, reasoning-only content, or only tool calls.',
            "Render mode must not call tools or imply business mutation. For NotificationTurn, render only from notification facts and error_facts; include creator, title, time, timezone, duration, and status when present. NotificationTurn must return a visible reply; no_reply is invalid because each notification_recipient delivery state must settle. Use concrete factual wording, not a generic placeholder such as 'go check it out'. Shared-reminder notification text is informational only and must not become approval, confirmation, accept/reject, or action-execution wording.",
            "For non-notification turns, if no user-visible message is warranted, return the explicit no_reply JSON.",
            "Text output is limited to one to three non-empty segments.",
            "Use short message-channel segments. Avoid generic customer-service openings or closers. Do not end ordinary final statement segments with . or 。.",
        ]

    def _input_payload(self, request: AgentRequest) -> dict[str, Any]:
        return _support_payload(request)

    def _build_db(self, config: ZAILLMConfig | None):
        if config is None or config.agno_database_url is None:
            return None
        return PostgresDb(
            db_url=config.agno_database_url,
            create_schema=config.agno_create_schema,
        )


def _add_history_to_context(request: AgentRequest) -> bool:
    return request.mode != TurnMode.RENDER


def _tool_callable(
    name: str,
    port: StateChangingToolPort,
    request: AgentRequest,
    tool_events: list[dict[str, Any]] | None = None,
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
                "domain_result": _jsonable(
                    _domain_result_from_parts(
                        domain=name,
                        intent=str(error.reason_code),
                        action=str(error.reason_code),
                        ok=False,
                        facts={"type": error.reason_code},
                        reason_code=error.reason_code,
                    )
                ),
            }
        domain_result = result.domain_result or _domain_result_from_parts(
            domain=name,
            intent=str(command_payload.get("operation") or name),
            action=str(command_payload.get("operation") or name),
            ok=result.ok,
            facts=result.facts,
            reason_code=result.reason_code,
        )
        payload = {
            "ok": result.ok,
            "facts": dict(result.facts),
            "reason_code": result.reason_code,
            "domain_result": _jsonable(domain_result),
        }
        if tool_events is not None:
            tool_events.append(payload)
        return _model_visible_tool_payload(name, payload)

    tool.__name__ = f"{name}_tool"
    tool.__doc__ = _tool_doc(name)
    return tool


def _model_visible_tool_payload(
    name: str, payload: Mapping[str, Any]
) -> Mapping[str, Any]:
    if name != "social_scheduling":
        return payload
    facts = payload.get("facts")
    if not isinstance(facts, Mapping):
        return payload
    outcome = facts.get("social_scheduling_outcome")
    if not isinstance(outcome, Mapping):
        return payload
    if outcome.get("status") != "staged_pending_close":
        return payload
    if outcome.get("operation") not in _SHARED_REMINDER_CREATE_OPERATIONS:
        return payload

    visible_facts = _model_visible_staged_shared_reminder_facts(outcome)
    visible_payload = dict(payload)
    visible_payload["facts"] = visible_facts

    domain_result = payload.get("domain_result")
    if isinstance(domain_result, Mapping):
        visible_domain_result = dict(domain_result)
        visible_domain_result["visible_summary"] = json.dumps(
            visible_facts, ensure_ascii=False, default=str
        )
        if "facts" in visible_domain_result:
            visible_domain_result["facts"] = visible_facts
        for key in ("staged_command_id", "preview", "social_scheduling_outcome"):
            visible_domain_result.pop(key, None)
        visible_payload["domain_result"] = visible_domain_result

    return visible_payload


def _model_visible_staged_shared_reminder_facts(
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    visible: dict[str, Any] = {"operation": str(outcome.get("operation") or "")}
    for key in ("title", "local_trigger_at", "captured_timezone"):
        value = outcome.get(key)
        if isinstance(value, str) and value.strip():
            visible[key] = value
    if outcome.get("duration_minutes") is not None:
        visible["duration_minutes"] = outcome["duration_minutes"]
    participant_account_ids = outcome.get("participant_account_ids")
    if isinstance(participant_account_ids, list | tuple) and participant_account_ids:
        visible["participant_account_ids"] = list(participant_account_ids)
    return visible


def _tool_doc(name: str) -> str:
    if name == "reminder":
        return (
            "Execute a Coke reminder domain command. For a natural-language "
            "create request, call with operation='detect_and_create', "
            "owner_account_id set to trusted_facts.account_id, raw_text set to "
            "the exact User message, captured_timezone set to "
            "trusted_facts.default_timezone, and entry_point='conversation'. "
            "For content or duration edits, call operation='update_reminder' "
            "with reminder_id plus content and/or duration_minutes; if the user "
            "identifies the target by content, pass keyword instead of "
            "reminder_id and ask for clarification when the tool reports "
            "ambiguous_reminder_reference; when the "
            "trusted focus block contains one reminder object_id, use it as "
            "reminder_id for follow-up edits. For time edits, call "
            "operation='reschedule_reminder' with reminder_id "
            "and trigger_time. For completion, call operation='complete_reminder' "
            "with reminder_id or keyword. For cancellation/deletion, call "
            "operation='delete_reminder' with reminder_id or keyword. For "
            "reminder list, count, search, or filter requests, call "
            "operation='list_reminders' with owner_account_id set to "
            "trusted_facts.account_id; optional filters are keyword, "
            "status/lifecycle, kind/reminder_type, trigger_after, and "
            "trigger_before. The result includes count, reminder facts, local "
            "display_time_label values, and display_lines. The "
            "final reply for a successful list_reminders result must include "
            "the total count and every returned active reminder; count-only "
            "answers are incomplete."
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
            "or public_token set from the User message. To list active "
            "friends, call operation='list_friends' with account_id set to "
            "trusted_facts.account_id. To remove a friend, call "
            "operation='remove_friend' with account_id set to "
            "trusted_facts.account_id and friend_account_id set to an active "
            "friend account ID. To query availability, call "
            "operation='query_availability' with requester_account_id set to "
            "trusted_facts.account_id, friend_account_ids, local_start, "
            "local_end, and requester_timezone. To create a shared reminder "
            "from natural language, call "
            "operation='detect_and_create_shared_reminder' with "
            "creator_account_id set to trusted_facts.account_id, "
            "receiver_account_ids set to active friend account IDs, raw_text "
            "set to the exact User message, captured_timezone set to "
            "trusted_facts.default_timezone, duration_minutes only when "
            "explicit. Do not compute local_trigger_at yourself. "
            "To update or reschedule an existing shared reminder, call "
            "operation='update_shared_reminder' with account_id set to "
            "trusted_facts.account_id, shared_reminder_id, local_trigger_at "
            "when changing time, captured_timezone, and duration_minutes only "
            "when explicit. Do not use cancellation for rescheduling. "
            "To cancel a shared reminder, call "
            "operation='cancel_shared_reminder' with "
            "account_id set to trusted_facts.account_id and "
            "shared_reminder_id."
        )
    if name == "settings":
        return (
            "Execute Coke settings/profile commands. Use account_id set to "
            "trusted_facts.account_id. For conversational global timezone "
            "switches, call operation='set_timezone' with default_timezone as "
            "an IANA timezone; this affects future relative-time reminders and "
            "does not rewrite existing reminders. For assistant name, how the "
            "assistant addresses the user, persona, background, speaking_style, "
            "extra_rules, proactive_enabled, or memory_enabled, call "
            "operation='update_settings'. Setting proactive_enabled=false "
            "cancels untriggered proactive follow-ups; setting "
            "memory_enabled=false stops long-term memory use and addition "
            "without deleting existing memory. For explicit profile facts, call "
            "operation='update_profile'. To restore agent defaults, call "
            "operation='reset_agent_settings'. To inspect current values, call "
            "operation='view_settings'."
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
        flattened.update(_mapping_from_tool_value(nested_kwargs, "invalid_tool_kwargs"))
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
    if name == "settings":
        payload = _normalize_settings_operation(command)
        payload.setdefault("account_id", request.account_id)
        return payload
    if name == "social_scheduling":
        payload = dict(command)
        if payload.get("operation") == "detect_and_create_shared_reminder":
            text = _user_text(request)
            payload.setdefault("raw_text", text)
            payload.setdefault("creator_account_id", request.account_id)
            payload.setdefault(
                "captured_timezone",
                str(request.trusted_facts.get("default_timezone") or "UTC"),
            )
        if payload.get("operation") == "update_shared_reminder":
            payload.setdefault("account_id", request.account_id)
            payload.setdefault(
                "captured_timezone",
                str(request.trusted_facts.get("default_timezone") or "UTC"),
            )
        return payload
    if name != "reminder":
        return command
    payload = _normalize_reminder_operation(command)
    if "operation" not in payload:
        payload["operation"] = "detect_and_create"
    if payload.get("operation") == "detect_and_create":
        payload.setdefault("raw_text", _user_text(request))
    payload.setdefault("owner_account_id", request.account_id)
    payload.setdefault(
        "captured_timezone",
        str(request.trusted_facts.get("default_timezone") or "UTC"),
    )
    if payload.get("operation") in {
        "update_reminder",
        "reschedule_reminder",
        "clear_trigger_time",
        "complete_reminder",
        "delete_reminder",
    } and not payload.get("reminder_id"):
        focused_reminder_id = _single_focus_object_id(request, "reminder")
        if focused_reminder_id is not None:
            payload["reminder_id"] = focused_reminder_id
    payload.setdefault("entry_point", "conversation")
    return payload


def _single_focus_object_id(request: AgentRequest, subject_type: str) -> str | None:
    focus = _context_value(request.context, "focus_subject")
    if not focus:
        return None
    if isinstance(focus, Mapping):
        focus_subject_type = focus.get("subject_type")
        object_ids = focus.get("object_ids")
    else:
        focus_subject_type = getattr(focus, "subject_type", None)
        object_ids = getattr(focus, "object_ids", None)
    if focus_subject_type != subject_type or not isinstance(object_ids, (list, tuple)):
        return None
    object_ids = [item for item in object_ids if isinstance(item, str) and item]
    if len(object_ids) != 1:
        return None
    return object_ids[0]


def _normalize_settings_operation(command: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(command)
    nested_command = payload.pop("command", None)
    if isinstance(nested_command, Mapping):
        nested = dict(nested_command)
        op = nested.pop("op", None)
        if op is not None and "operation" not in nested:
            nested["operation"] = _SETTINGS_OP_ALIASES.get(str(op), str(op))
        nested.update(payload)
        payload = nested
    elif "op" in payload and "operation" not in payload:
        op = str(payload.pop("op"))
        payload["operation"] = _SETTINGS_OP_ALIASES.get(op, op)
    if "operation" in payload:
        payload["operation"] = _SETTINGS_OP_ALIASES.get(
            str(payload["operation"]), str(payload["operation"])
        )
    if "timezone" in payload and "default_timezone" not in payload:
        payload["default_timezone"] = payload.pop("timezone")
    return payload


def _normalize_reminder_operation(command: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(command)
    nested_command = payload.pop("command", None)
    if isinstance(nested_command, Mapping):
        nested = dict(nested_command)
        op = nested.pop("op", None)
        if op is not None and "operation" not in nested:
            nested["operation"] = _REMINDER_OP_ALIASES.get(str(op), str(op))
        if "new_trigger_time" in nested and "trigger_time" not in nested:
            nested["trigger_time"] = nested.pop("new_trigger_time")
        if "new_duration_minutes" in nested and "duration_minutes" not in nested:
            nested["duration_minutes"] = nested.pop("new_duration_minutes")
        nested.update(payload)
        payload = nested
    elif "op" in payload and "operation" not in payload:
        op = str(payload.pop("op"))
        payload["operation"] = _REMINDER_OP_ALIASES.get(op, op)
    if "operation" in payload:
        payload["operation"] = _REMINDER_OP_ALIASES.get(
            str(payload["operation"]), str(payload["operation"])
        )
    if "new_trigger_time" in payload and "trigger_time" not in payload:
        payload["trigger_time"] = payload.pop("new_trigger_time")
    if "new_duration_minutes" in payload and "duration_minutes" not in payload:
        payload["duration_minutes"] = payload.pop("new_duration_minutes")
    return payload


def _mapping_or_none(content: Any) -> Mapping[str, Any] | None:
    if isinstance(content, Mapping):
        return content
    if isinstance(content, str):
        if _looks_like_serialized_tool_call(content):
            return {
                "type": "invalid_output_protocol",
                "reason": "serialized_tool_call_output",
            }
        content = _json_text(content)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, Mapping):
            return parsed
    return None


class _ReplySegmentStreamParser:
    def __init__(self) -> None:
        self.buffer = ""
        self.emitted_count = 0

    def feed(self, text: str) -> tuple[str, ...]:
        if not text:
            return ()
        self.buffer += text
        segments = _complete_reply_segments_from_buffer(self.buffer)
        if self.emitted_count >= len(segments):
            return ()
        new_segments = tuple(segments[self.emitted_count :])
        self.emitted_count = len(segments)
        return new_segments


def _complete_reply_segments_from_buffer(buffer: str) -> tuple[str, ...]:
    decoder = json.JSONDecoder()
    index = 0
    while index < len(buffer):
        if buffer[index] != '"':
            index += 1
            continue
        try:
            value, relative_end = decoder.raw_decode(buffer[index:])
        except json.JSONDecodeError:
            return ()
        end = index + relative_end
        colon = _skip_json_whitespace(buffer, end)
        if value == "segments" and colon < len(buffer) and buffer[colon] == ":":
            array_start = _skip_json_whitespace(buffer, colon + 1)
            if array_start >= len(buffer) or buffer[array_start] != "[":
                return ()
            return _complete_string_array_elements(buffer, array_start + 1, decoder)
        index = end
    return ()


def _complete_string_array_elements(
    buffer: str, start: int, decoder: json.JSONDecoder
) -> tuple[str, ...]:
    segments: list[str] = []
    index = start
    while True:
        index = _skip_json_whitespace(buffer, index)
        if index >= len(buffer):
            return tuple(segments)
        if buffer[index] == "]":
            return tuple(segments)
        if buffer[index] != '"':
            return tuple(segments)
        try:
            value, relative_end = decoder.raw_decode(buffer[index:])
        except json.JSONDecodeError:
            return tuple(segments)
        if not isinstance(value, str):
            return tuple(segments)
        end = index + relative_end
        delimiter = _skip_json_whitespace(buffer, end)
        if delimiter < len(buffer) and buffer[delimiter] not in {",", "]"}:
            return tuple(segments)
        segments.append(value)
        if delimiter >= len(buffer):
            return tuple(segments)
        if buffer[delimiter] == "]":
            return tuple(segments)
        index = delimiter + 1


def _skip_json_whitespace(buffer: str, index: int) -> int:
    while index < len(buffer) and buffer[index] in " \t\r\n":
        index += 1
    return index


def _stream_text_delta(previous: str, content: str) -> tuple[str, str]:
    if content.startswith(previous):
        delta = content[len(previous) :]
        return delta, content
    return content, f"{previous}{content}"


def _is_completed_stream_event(event: Any) -> bool:
    event_name = getattr(event, "event", None)
    if event_name == "RunCompleted":
        return True
    return type(event).__name__ == "RunCompletedEvent"


def _agent_result_from_content(content: Any) -> AgentResult:
    if content is None:
        return AgentResult.completed(None, blank_output=True)
    if isinstance(content, str) and not content.strip():
        return AgentResult.completed(None, blank_output=True)
    return AgentResult.completed(_mapping_or_none(content))


def _enforce_tool_reply_contracts(
    result: AgentResult,
    tool_events: list[dict[str, Any]],
    request: AgentRequest,
) -> AgentResult:
    social_outcomes = [
        *_social_scheduling_outcomes_from_tool_events(tool_events),
        *_social_scheduling_outcomes_from_trusted_facts(request.trusted_facts),
    ]
    if social_outcomes or _has_social_scheduling_claim(result.output):
        validator = OutputProtocolValidator()
        validated = validator.validate_first_answer(result.output)
        validated = validator.validate_social_scheduling_claim(
            validated,
            outcomes=social_outcomes,
        )
        if not validated.valid:
            return AgentResult.completed(
                {
                    "type": "invalid_output_protocol",
                    "reason": validated.retry_guidance or validated.reason_code,
                },
                tool_events=tuple(tool_events),
            )
    result = replace(result, tool_events=tuple(tool_events))
    reminder_list = _latest_render_reminder_list_event(tool_events)
    if reminder_list is None or _reminder_list_reply_is_complete(result, reminder_list):
        return result
    return AgentResult.completed(
        {
            "type": "reply",
            "segments": [_render_reminder_list_reply(reminder_list, request)],
        },
        tool_events=tuple(tool_events),
    )


def _social_scheduling_outcomes_from_tool_events(
    tool_events: list[dict[str, Any]],
) -> list[Mapping[str, Any]]:
    outcomes: list[Mapping[str, Any]] = []
    for event in tool_events:
        facts = event.get("facts")
        if not isinstance(facts, Mapping):
            continue
        outcome = facts.get("social_scheduling_outcome")
        if isinstance(outcome, Mapping):
            outcomes.append(dict(outcome))
    return outcomes


def _has_social_scheduling_claim(output: Mapping[str, Any] | None) -> bool:
    if not isinstance(output, Mapping):
        return False
    claim = output.get("domain_claim")
    return isinstance(claim, Mapping) and claim.get("domain") == "social_scheduling"


def _latest_render_reminder_list_event(
    tool_events: list[dict[str, Any]],
) -> Mapping[str, Any] | None:
    for event in reversed(tool_events):
        domain_result = event.get("domain_result")
        if (
            event.get("ok") is True
            and isinstance(domain_result, Mapping)
            and domain_result.get("reply_contract") == "render_reminder_list"
        ):
            facts = event.get("facts")
            if isinstance(facts, Mapping):
                return facts
    return None


def _reminder_list_reply_is_complete(
    result: AgentResult, facts: Mapping[str, Any]
) -> bool:
    output = result.output
    if not isinstance(output, Mapping) or output.get("type") != "reply":
        return False
    segments = output.get("segments")
    if not isinstance(segments, list):
        return False
    text = "\n".join(segment for segment in segments if isinstance(segment, str))
    reminders = facts.get("reminders")
    if not isinstance(reminders, list):
        return False
    for reminder in reminders:
        if not isinstance(reminder, Mapping):
            return False
        content = str(reminder.get("content") or "").strip()
        if content and content not in text:
            return False
        display_time_label = str(reminder.get("display_time_label") or "").strip()
        if display_time_label and display_time_label not in text:
            return False
    return True


def _render_reminder_list_reply(facts: Mapping[str, Any], request: AgentRequest) -> str:
    return _shared_render_reminder_list_reply(
        facts,
        user_text=_user_text(request),
        account_id=request.account_id,
    )


def _render_reminder_list_line(
    index: int, reminder: Mapping[str, Any], chinese: bool
) -> str:
    return _shared_render_reminder_list_line(index, reminder, chinese)


def _looks_chinese(text: str) -> bool:
    return _shared_looks_chinese(text)


def build_prompt_blocks(request: AgentRequest) -> tuple[PromptBlock, ...]:
    blocks: list[PromptBlock] = [
        PromptBlock("turn_source", _turn_source_block(request)),
        PromptBlock("current_input", _current_input_block(request)),
        PromptBlock("identity", _identity_block(request)),
    ]

    persona = _persona_block(request)
    if persona:
        blocks.append(PromptBlock("persona", persona))

    environment = _environment_block(request)
    if environment:
        blocks.append(PromptBlock("environment", environment))

    onboarding_guidance = _onboarding_guidance_block(request)
    if onboarding_guidance:
        blocks.append(PromptBlock("onboarding_guidance", onboarding_guidance))

    focus = _context_value(request.context, "focus_subject")
    if focus:
        blocks.append(PromptBlock("focus", _json_block(focus)))

    domain_result = _domain_result_payload(request)
    if domain_result:
        blocks.append(PromptBlock("domain_result", _domain_result_block(domain_result)))

    social_outcomes = _social_scheduling_outcomes_from_trusted_facts(
        request.trusted_facts
    )
    if social_outcomes:
        blocks.append(
            PromptBlock(
                "social_scheduling_outcomes",
                _social_scheduling_outcomes_block(social_outcomes),
            )
        )

    memory = _memory_payload(request)
    if memory:
        blocks.append(PromptBlock("memory", _json_block(memory)))

    conversation = _conversation_payload(request)
    if conversation:
        blocks.append(
            PromptBlock(
                "conversation",
                "Advisory language evidence only:\n" + _json_block(conversation),
            )
        )

    blocks.append(PromptBlock("voice_policy", CokeVoicePolicy().render()))
    blocks.append(PromptBlock("output_contract", _output_contract_block(request)))
    return tuple(blocks)


def render_prompt_blocks(blocks: tuple[PromptBlock, ...]) -> str:
    return "\n\n".join(
        f'<trusted_block name="{block.name}">\n{block.content}\n</trusted_block>'
        for block in blocks
        if block.content
    )


def _agent_input(request: AgentRequest) -> str:
    return render_prompt_blocks(build_prompt_blocks(request))


def _turn_source_block(request: AgentRequest) -> str:
    source = request.trusted_facts.get("turn_source")
    if not isinstance(source, Mapping):
        source = _turn_source_from_request(request)
    return _plain_mapping(source)


def _turn_source_from_request(request: AgentRequest) -> Mapping[str, Any]:
    trigger_type = request.trigger_type
    if trigger_type == "InboundTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": True,
            "instruction": (
                "This is a real message from the user. Reply to the user's latest message."
            ),
        }
    if trigger_type == "ReminderFireTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": False,
            "instruction": (
                "Render the reminder fact to the user. Do not answer the reminder "
                "title as if the user said it."
            ),
        }
    if trigger_type == "ProactiveFireTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": False,
            "instruction": (
                "This turn was initiated by Coke. The planned action is what Coke "
                "intends to say or check. Do not answer it as a user question."
            ),
        }
    if trigger_type == "NotificationTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": False,
            "instruction": (
                "Render the notification fact; do not answer it as if the user said it."
            ),
        }
    if trigger_type == "AccessDeniedTurn":
        return {
            "trigger_type": trigger_type,
            "user_spoke_this_turn": False,
            "instruction": "Render the access recovery fact; do not continue normal intent execution.",
        }
    return {
        "trigger_type": trigger_type,
        "user_spoke_this_turn": request.mode == TurnMode.INTERACTIVE,
        "instruction": "Render the trusted turn fact according to its source.",
    }


def _current_input_block(request: AgentRequest) -> str:
    if request.trigger_type == "InboundTurn":
        messages = request.current_input_messages or (
            {"seq": None, "text": _user_text(request)},
        )
        lines = [
            "kind: user_message_window",
            (
                "instruction: These are adjacent user messages in the current "
                "open input window. Answer the combined intent in sequence order."
            ),
            (
                "short_confirmation_instruction: If the current user message is "
                "a short confirmation or concise clarification answer such as "
                "yes/ok/是的/好的/a friend name/a time, resolve it against the "
                "immediately preceding assistant clarification in conversation "
                "history. If there is no specific pending action, ask what they "
                "are confirming; do not invent an action."
            ),
        ]
        for message in messages:
            lines.extend(
                [
                    "---",
                    f"seq: {_input_message_seq(message)}",
                    f"text: {_input_message_text(message)}",
                ]
            )
        return "\n".join(lines)
    return _render_trigger_input_block(request)


def _render_trigger_input_block(request: AgentRequest) -> str:
    return "\n".join(
        [
            "kind: trusted_turn_fact",
            f"trigger_type: {request.trigger_type}",
            f"payload: {json.dumps(dict(request.payload), ensure_ascii=False, sort_keys=True)}",
            "instruction: Render the trusted turn fact according to its source.",
        ]
    )


def _input_message_seq(message: Any) -> Any:
    if isinstance(message, Mapping):
        return message.get("seq")
    return getattr(message, "seq", None)


def _input_message_text(message: Any) -> str:
    if isinstance(message, Mapping):
        return str(message.get("text") or "")
    return str(getattr(message, "text", "") or "")


def _identity_block(request: AgentRequest) -> str:
    facts = request.trusted_facts
    identity = {
        "account_id": facts.get("account_id") or request.account_id,
        "conversation_id": request.conversation_id,
        "assistant_name": facts.get("assistant_name") or "Coke",
    }
    if facts.get("user_address_name"):
        identity["user_address_name"] = facts["user_address_name"]
    if facts.get("channel_identity_id"):
        identity["channel_identity_id"] = facts["channel_identity_id"]
    return _plain_mapping(identity)


def _persona_block(request: AgentRequest) -> str:
    facts = request.trusted_facts
    persona = {
        key: facts.get(key)
        for key in ("persona", "background", "speaking_style", "extra_rules")
        if facts.get(key)
    }
    if not persona:
        return ""
    return (
        "User-configured persona and speaking preferences layer on top of "
        "CokeVoicePolicy:\n" + _json_block(persona)
    )


def _environment_block(request: AgentRequest) -> str:
    facts = request.trusted_facts
    environment = {
        key: facts.get(key)
        for key in (
            "default_timezone",
            "timezone",
            "current_time",
            "now",
            "locale",
            "provider_type",
        )
        if facts.get(key)
    }
    if not environment:
        return ""
    return _json_block(environment)


_ONBOARDING_CAPABILITY_LABELS = {
    "reminders": "reminders",
    "shared_reminders_with_friends": "shared reminders with friends",
    "availability_checks": "availability checks",
    "long_term_memory_preferences": "long-term memory/preferences",
}


def _onboarding_guidance_block(request: AgentRequest) -> str | None:
    guidance = request.trusted_facts.get("onboarding_guidance")
    if not isinstance(guidance, Mapping):
        return None
    raw_capabilities = guidance.get("supported_capabilities")
    if not isinstance(raw_capabilities, list | tuple):
        return None
    capabilities = [
        _ONBOARDING_CAPABILITY_LABELS[item]
        for item in raw_capabilities
        if item in _ONBOARDING_CAPABILITY_LABELS
    ]
    if not capabilities:
        return None
    lines = [
        "First-use guidance is required in this visible final reply.",
        (
            "Respond to the user's current message and briefly introduce only "
            "these supported capabilities: " + "; ".join(capabilities)
        ),
        "Do not claim unsupported capabilities.",
    ]
    assistant_name = guidance.get("assistant_name")
    if isinstance(assistant_name, str) and assistant_name.strip():
        lines.append(f"Assistant name: {assistant_name.strip()}")
    user_address_name = guidance.get("user_address_name")
    if isinstance(user_address_name, str) and user_address_name.strip():
        lines.append(f"Trusted user address name: {user_address_name.strip()}")
    return "\n".join(lines)


def _domain_result_payload(request: AgentRequest) -> Mapping[str, Any] | None:
    domain_result = request.trusted_facts.get("domain_result")
    if isinstance(domain_result, Mapping):
        return dict(domain_result)
    context_domain_result = _context_value(request.context, "domain_result")
    if context_domain_result:
        return _jsonable(context_domain_result)
    notification_result = _notification_domain_result(request)
    if notification_result:
        return notification_result
    return None


def _notification_domain_result(request: AgentRequest) -> Mapping[str, Any] | None:
    if request.mode != TurnMode.RENDER or request.trigger_type != "NotificationTurn":
        return None
    render_context = _render_context_payload(request)
    facts = render_context.get("notification_facts")
    if not isinstance(facts, Mapping):
        return None
    status = str(facts.get("status") or "notification")
    return {
        "domain": "notification",
        "intent": "render notification fact",
        "action": str(render_context.get("trigger_type") or "NotificationTurn"),
        "effect": status,
        "intent_fulfilled": True,
        "visible_summary": json.dumps(facts, ensure_ascii=False, default=str),
        "reply_contract": "render_fact",
        "privacy_notes": ["Do not expose raw channel errors or internal codes."],
        "facts": facts,
        **(
            {"error_facts": render_context["error_facts"]}
            if isinstance(render_context.get("error_facts"), Mapping)
            else {}
        ),
    }


def _domain_result_block(domain_result: Mapping[str, Any]) -> str:
    lines = [
        "trusted domain execution result:",
        _json_block(domain_result),
        "Do not infer success from the transcript or from the mere existence of a requested operation.",
    ]
    if domain_result.get("intent_fulfilled") is False:
        lines.append(
            "Do not claim the action succeeded; ask for missing information or report the trusted failure reason."
        )
    return "\n".join(lines)


def _social_scheduling_outcomes_from_trusted_facts(
    trusted_facts: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    outcomes = trusted_facts.get("social_scheduling_outcomes")
    if isinstance(outcomes, list):
        return [dict(item) for item in outcomes if isinstance(item, Mapping)]
    outcome = trusted_facts.get("social_scheduling_outcome")
    if isinstance(outcome, Mapping):
        return [dict(outcome)]
    return []


def _social_scheduling_outcomes_block(outcomes: list[Mapping[str, Any]]) -> str:
    return "\n".join(
        [
            "trusted social_scheduling close-time outcomes:",
            _json_block({"outcomes": outcomes}),
            "When replying about these outcomes, include domain_claim with domain=social_scheduling, outcome_id, status, and the allowed claim that matches the trusted outcome.",
            "created_active requires claim active_created; rescheduled_active requires active_rescheduled; duplicate_active requires active_duplicate; blocked_* requires the matching blocked_* claim and blocker; staged_pending_close allows only no_success_claim and must not be user-visible success.",
        ]
    )


def _memory_payload(request: AgentRequest) -> Mapping[str, Any] | None:
    memory_context = _context_value(request.context, "memory_context")
    if memory_context is not None:
        memory = _jsonable(memory_context)
        if isinstance(memory, Mapping):
            long_term = memory.get("long_term")
            if long_term:
                return {"long_term": long_term}
        return memory if memory else None
    memory = _context_value(request.context, "memory")
    if memory:
        return {"memory": memory}
    return None


def _conversation_payload(request: AgentRequest) -> Mapping[str, Any] | None:
    recent = _context_value(request.context, "recent_conversation")
    if recent:
        return {"recent_conversation": recent}
    memory_context = _context_value(request.context, "memory_context")
    if memory_context is not None:
        memory = _jsonable(memory_context)
        if isinstance(memory, Mapping) and memory.get("short_term"):
            return {"short_term": memory["short_term"]}
    return None


def _output_contract_block(request: AgentRequest) -> str:
    notification_turn = request.trigger_type == "NotificationTurn"
    lines = [
        "Return only the Coke JSON output protocol.",
        'Valid reply: {"type":"reply","segments":["text"]}.',
        "Text output is limited to 1-3 non-empty segments.",
        "A requested action without a trusted domain_result is not success. Do not claim it succeeded.",
        "If domain_result.intent_fulfilled is false, ask only for missing information or state the trusted failure.",
        "Do not create or imply a duplicate proactive follow-up when a timed reminder was already created.",
        "Invalid final output fails closed; do not emit parser repair text, fallback prose, or template summaries.",
    ]
    if notification_turn:
        lines.insert(
            3,
            (
                "NotificationTurn must render a visible reply from notification "
                "facts; no-reply is invalid because notification_recipient delivery "
                "state must settle."
            ),
        )
    else:
        lines.insert(
            3,
            'Valid no-reply: {"type":"no_reply","reason":"intentional_no_reply"}.',
        )
        lines.insert(
            4,
            (
                "Use no-reply only for meaningless content, natural conversation "
                "endings, or explicit no-disturb requests. Do not use no-reply "
                "for post-notification acknowledgements, delivery/status "
                "questions, challenges, or short replies that refer to a recent "
                "product notification."
            ),
        )
    protocol_retry = request.trusted_facts.get("protocol_retry")
    if protocol_retry:
        retry_output = (
            'object only: {"type":"reply","segments":["..."]}.'
            if notification_turn
            else (
                'object only: {"type":"reply","segments":["..."]} or '
                '{"type":"no_reply","reason":"intentional_no_reply"}.'
            )
        )
        lines.extend(
            [
                "Protocol retry instruction:",
                (
                    "The previous assistant answer for this same turn was rejected "
                    "because it was not a valid Coke output protocol object. Do not "
                    "rewrite or summarize that prior answer. Use trusted facts, "
                    "conversation history, and tool results to produce one final JSON "
                    f"{retry_output}"
                ),
                (
                    "Reply JSON must contain one to three non-empty string segments; "
                    "combine lines into fewer segments when needed."
                ),
            ]
        )
        if isinstance(protocol_retry, Mapping) and protocol_retry.get("guidance"):
            lines.append(f"Specific protocol violation: {protocol_retry['guidance']}.")
            if (
                protocol_retry.get("guidance")
                == "serialized_tool_call_output_requires_native_tool_call"
            ):
                lines.append(
                    "Specific protocol violation: serialized tool-call markup was emitted as text. Use the native tool call channel for domain actions, then return one final Coke JSON protocol object."
                )
            if (
                protocol_retry.get("guidance")
                == "state_change_reply_requires_native_tool_call"
            ):
                lines.append(
                    "Specific protocol violation: the previous reply claimed a state-changing scheduling action without a native tool call. Call social_scheduling_tool for the requested shared-reminder work, then return one final Coke JSON protocol object grounded in the tool result."
                )
    return "\n".join(lines)


def _plain_mapping(mapping: Mapping[str, Any]) -> str:
    return "\n".join(f"{key}: {_plain_value(value)}" for key, value in mapping.items())


def _plain_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    return _json_block(value)


def _json_block(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, default=str, indent=2)


def _context_value(context: Any, key: str) -> Any:
    if isinstance(context, Mapping):
        return context.get(key)
    return getattr(context, key, None)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, set | frozenset):
        return [_jsonable(item) for item in sorted(value, key=str)]
    if hasattr(value, "__dict__"):
        return {
            key: _jsonable(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return value


def _domain_result_from_parts(
    *,
    domain: str,
    intent: str,
    action: str,
    ok: bool,
    facts: Mapping[str, Any],
    reason_code: str | None,
) -> DomainExecutionResult:
    effect = "succeeded" if ok else (reason_code or "failed")
    if reason_code and reason_code.startswith("needs_"):
        reply_contract = "ask_missing_info"
    else:
        reply_contract = "confirm_success" if ok else "report_failure"
    return DomainExecutionResult(
        domain=domain,
        intent=intent,
        action=action,
        effect=effect,
        intent_fulfilled=ok,
        visible_summary=json.dumps(dict(facts), ensure_ascii=False, default=str),
        reply_contract=reply_contract,
        privacy_notes=(),
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


def _render_context_payload(request: AgentRequest) -> dict[str, Any]:
    if request.mode != TurnMode.RENDER:
        return {}
    payload = dict(request.payload)
    render_context: dict[str, Any] = {
        "mode": str(request.mode),
        "trigger_type": request.trigger_type,
    }
    notification_fact = payload.get("notification_fact")
    if isinstance(notification_fact, Mapping):
        render_context["notification_fact"] = dict(notification_fact)
        fact_facts = notification_fact.get("facts")
        if isinstance(fact_facts, Mapping):
            render_context["notification_facts"] = dict(fact_facts)
        fact_hash = notification_fact.get("facts_hash")
        if isinstance(fact_hash, str) and fact_hash:
            render_context["facts_hash"] = fact_hash
    elif isinstance(payload.get("facts"), Mapping):
        render_context["notification_facts"] = dict(payload["facts"])
    fact_list = payload.get("notification_facts")
    if isinstance(fact_list, list):
        render_context["notification_facts"] = [
            dict(fact) for fact in fact_list if isinstance(fact, Mapping)
        ]
    if isinstance(payload.get("error_facts"), Mapping):
        render_context["error_facts"] = dict(payload["error_facts"])
    return render_context


def _user_text(request: AgentRequest) -> str:
    text = request.payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return json.dumps(request.payload, ensure_ascii=False, default=str)


def _json_text(content: str) -> str:
    stripped = content.strip()
    fenced = _json_text_from_code_fence(stripped)
    if fenced is not None:
        return fenced
    return stripped


def _json_text_from_code_fence(stripped: str) -> str | None:
    # Normalize only a whole-response markdown envelope, never prose containing JSON.
    if not stripped.startswith("```") or not stripped.endswith("```"):
        return None
    first_newline = stripped.find("\n")
    if first_newline == -1:
        return None
    opening_line = stripped[:first_newline].strip()
    if not opening_line.startswith("```"):
        return None
    inner = stripped[first_newline + 1 : -3]
    return inner.strip()


def _looks_like_serialized_tool_call(content: str) -> bool:
    lowered = content.casefold()
    return any(
        marker in lowered
        for marker in (
            "<tool_call",
            "</tool_call",
            "<minimax:tool_call",
            "<invoke name=",
            "</arg_value>",
            "_model_supplied_args",
        )
    )


def _jsonable_context(context: Any) -> Any:
    return _jsonable(context)
