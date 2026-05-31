from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta
import json
import re
from typing import Any, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.memory.manager import MemoryManager as AgnoMemoryManager

from coke.llm.config import SiliconFlowLLMConfig
from coke.turn.agent import (
    AgentRequest,
    AgentResult,
    DomainExecutionResult,
    StateChangingToolPort,
)
from coke.turn.context import TurnMode

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

    async def ainvoke(self, request: AgentRequest) -> AgentResult:
        return await self._arun_request(request, store_timeout=True)

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
        deterministic = _try_resolved_shared_reminder_followup(request)
        if deterministic is not None:
            return deterministic
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
        deterministic = _try_resolved_shared_reminder_followup(request)
        if deterministic is not None:
            return deterministic
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
            add_history_to_context=True,
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
            "If the focus block has subject_type='reminder' with exactly one object_id, use that object_id as reminder_id for follow-up edits to that reminder instead of asking which reminder.",
            "For friend link/code requests, call social_scheduling_tool with operation=get_friend_link and owner_account_id from trusted_facts.account_id.",
            "For adding a friend from an invite code or link token, call social_scheduling_tool with operation=establish_friendship_from_token, joiner_account_id from trusted_facts.account_id, and link_code or public_token from the User message.",
            "For friend-list requests, call social_scheduling_tool with operation=list_friends and account_id from trusted_facts.account_id.",
            "For friend-removal requests, call social_scheduling_tool with operation=remove_friend, account_id from trusted_facts.account_id, and friend_account_id from an active friend account ID.",
            "For availability requests, call social_scheduling_tool with operation=query_availability, requester_account_id from trusted_facts.account_id, friend_account_ids as active friend account IDs, local_start, local_end, and requester_timezone from trusted_facts.default_timezone.",
            "For shared-reminder creation from natural language, call social_scheduling_tool with operation=detect_and_create_shared_reminder, creator_account_id from trusted_facts.account_id, receiver_account_ids as account IDs of active friends, raw_text set to the exact User message, captured_timezone from trusted_facts.default_timezone when unspecified, duration_minutes only when explicit, and context. Do not compute local_trigger_at yourself.",
            "When a shared-reminder creation tool result succeeds, state that the shared reminder is created and immediately active. Never say or imply waiting for confirmation, pending confirmation, pending acceptance, approval, invitation approval, or that receivers need to accept/reject it.",
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
        return payload

    tool.__name__ = f"{name}_tool"
    tool.__doc__ = _tool_doc(name)
    return tool


def _try_resolved_shared_reminder_followup(request: AgentRequest) -> AgentResult | None:
    pending = request.trusted_facts.get("pending_clarification_resolution")
    if not isinstance(pending, Mapping):
        return None
    if pending.get("type") != "shared_reminder_friend_answer":
        return None
    port = request.tool_profile.social_scheduling_tool
    if port is None:
        return None
    answer = str(pending.get("answer") or "").strip()
    original_text = str(pending.get("original_user_text") or "").strip()
    if not answer or not original_text:
        return None
    friends_result = port.execute(
        {"operation": "list_friends", "account_id": request.account_id},
        request.freshness_guard,
    )
    friends = friends_result.facts.get("friends") if friends_result.ok else None
    if not isinstance(friends, list):
        return None
    matches = [
        friend
        for friend in friends
        if isinstance(friend, Mapping)
        and _friend_name_matches_answer(friend, answer)
        and friend.get("account_id")
    ]
    if len(matches) != 1:
        return None
    friend = matches[0]
    friend_name = str(friend.get("display_name") or answer)
    timezone_name = str(request.trusted_facts.get("default_timezone") or "UTC")
    command = _direct_shared_reminder_create_command(
        original_text,
        creator_account_id=request.account_id,
        receiver_account_ids=[str(friend["account_id"])],
        captured_timezone=timezone_name,
        current_time=str(request.trusted_facts.get("current_time") or ""),
        context={
            "source": "conversation_followup",
            "original_user_text": original_text,
            "friend_answer": answer,
        },
    ) or {
        "operation": "detect_and_create_shared_reminder",
        "creator_account_id": request.account_id,
        "receiver_account_ids": [str(friend["account_id"])],
        "raw_text": f"{original_text}，好友是{friend_name}",
        "captured_timezone": timezone_name,
        "context": {
            "source": "conversation_followup",
            "original_user_text": original_text,
            "friend_answer": answer,
        },
    }
    create_result = port.execute(command, request.freshness_guard)
    if create_result.ok:
        return AgentResult.completed(
            {
                "type": "reply",
                "segments": [f"好的，已帮你和{friend_name}创建这个共享提醒"],
            }
        )
    return AgentResult.completed(
        {
            "type": "reply",
            "segments": ["抱歉，暂时无法帮你创建这个共享提醒，稍后可以再试一次"],
        }
    )


def _friend_name_matches_answer(friend: Mapping[str, Any], answer: str) -> bool:
    normalized_answer = _normalize_lookup_text(answer)
    if not normalized_answer:
        return False
    for key in ("display_name", "nickname", "real_name", "account_id"):
        value = friend.get(key)
        if value is None:
            continue
        normalized_value = _normalize_lookup_text(str(value))
        if normalized_value and (
            normalized_value == normalized_answer
            or normalized_answer in normalized_value
            or normalized_value in normalized_answer
        ):
            return True
    return False


def _normalize_lookup_text(text: str) -> str:
    return text.casefold().strip(" \t\r\n.!?。！？~～")


def _direct_shared_reminder_create_command(
    text: str,
    *,
    creator_account_id: str,
    receiver_account_ids: list[str],
    captured_timezone: str,
    current_time: str,
    context: Mapping[str, Any],
) -> dict[str, Any] | None:
    local_trigger_at = _explicit_zh_local_datetime(
        text, captured_timezone=captured_timezone, current_time=current_time
    )
    title = _shared_reminder_title(text)
    if local_trigger_at is None or title is None:
        return None
    return {
        "operation": "create_shared_reminder",
        "creator_account_id": creator_account_id,
        "receiver_account_ids": receiver_account_ids,
        "title": title,
        "local_trigger_at": local_trigger_at.isoformat(),
        "captured_timezone": captured_timezone,
        "duration_minutes": 15,
        "context": dict(context),
    }


def _explicit_zh_local_datetime(
    text: str, *, captured_timezone: str, current_time: str
) -> datetime | None:
    try:
        zone = ZoneInfo(captured_timezone)
        now = datetime.fromisoformat(current_time).astimezone(zone)
    except (ValueError, ZoneInfoNotFoundError):
        return None

    date_match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if date_match:
        year, month, day = (int(part) for part in date_match.groups())
        base_date = datetime(year, month, day, tzinfo=zone).date()
    elif "明天" in text:
        base_date = (now + timedelta(days=1)).date()
    elif "后天" in text:
        base_date = (now + timedelta(days=2)).date()
    elif "今天" in text:
        base_date = now.date()
    else:
        return None

    time_match = re.search(
        r"(凌晨|早上|上午|中午|下午|晚上|今晚)?\s*"
        r"([零一二三四五六七八九十两\d]{1,3})点"
        r"(半|[零一二三四五六七八九十两\d]{1,3}分?)?",
        text,
    )
    if time_match is None:
        return None
    period, hour_text, minute_text = time_match.groups()
    hour = _zh_number(hour_text)
    if hour is None or hour > 24:
        return None
    minute = 30 if minute_text == "半" else 0
    if minute_text and minute_text != "半":
        minute = _zh_number(minute_text.removesuffix("分")) or -1
    if minute < 0 or minute > 59:
        return None
    if period in {"下午", "晚上", "今晚"} and hour < 12:
        hour += 12
    if period == "中午" and hour < 11:
        hour += 12
    if hour == 24:
        hour = 0
    return datetime.combine(base_date, datetime.min.time(), tzinfo=zone).replace(
        hour=hour, minute=minute
    )


def _zh_number(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if text in digits:
        return digits[text]
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    return None


def _shared_reminder_title(text: str) -> str | None:
    explicit = re.search(r"标题是(.+)$", text)
    if explicit:
        title = explicit.group(1).strip(" ，,。.!?？")
        return title or None
    if "晨跑" in text:
        return "晨跑活动" if "活动" in text else "晨跑"
    return None


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
            "explicit, and context. Do not compute local_trigger_at yourself. "
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
            payload.setdefault("duration_minutes", 15)
            payload.setdefault(
                "context",
                {
                    "source": "conversation",
                    "text": text,
                },
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
    if _state_change_reply_without_tool_call(result, tool_events, request):
        return AgentResult.completed(
            {
                "type": "invalid_output_protocol",
                "reason": "state_change_reply_without_tool_call",
            }
        )
    reminder_list = _latest_render_reminder_list_event(tool_events)
    if reminder_list is None or _reminder_list_reply_is_complete(result, reminder_list):
        return result
    return AgentResult.completed(
        {
            "type": "reply",
            "segments": [_render_reminder_list_reply(reminder_list, request)],
        }
    )


def _state_change_reply_without_tool_call(
    result: AgentResult,
    tool_events: list[dict[str, Any]],
    request: AgentRequest,
) -> bool:
    if tool_events:
        return False
    if "social_scheduling" not in request.tool_profile.tool_names:
        return False
    output = result.output
    if not isinstance(output, Mapping) or output.get("type") != "reply":
        return False
    segments = output.get("segments")
    if not isinstance(segments, list):
        return False
    text = " ".join(segment for segment in segments if isinstance(segment, str))
    normalized = text.casefold()
    action_terms = (
        "共享提醒",
        "提醒",
        "晨跑",
        "shared reminder",
        "reminder",
    )
    claim_terms = (
        "正在帮你",
        "已创建",
        "已经创建",
        "创建好了",
        "设置好了",
        "will create",
        "creating",
        "created",
        "set up",
    )
    return any(term in normalized for term in action_terms) and any(
        term in normalized for term in claim_terms
    )


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
    count = facts.get("count", 0)
    chinese = _looks_chinese(_user_text(request))
    if chinese:
        lines = [f"你现在一共有 {count} 个提醒："]
    else:
        lines = [f"You currently have {count} reminders:"]

    reminders = facts.get("reminders")
    if isinstance(reminders, list):
        for index, reminder in enumerate(reminders, start=1):
            if isinstance(reminder, Mapping):
                lines.append(_render_reminder_list_line(index, reminder, chinese))
    return "\n".join(lines)


def _render_reminder_list_line(
    index: int, reminder: Mapping[str, Any], chinese: bool
) -> str:
    content = str(reminder.get("content") or "").strip()
    time_value = reminder.get("display_time_label") or reminder.get("next_fire_at")
    time_label = (
        str(time_value) if time_value else ("未设定时间" if chinese else "unscheduled")
    )
    if chinese:
        return f"{index}. {content}（{time_label}）"
    return f"{index}. {content} ({time_label})"


def _looks_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


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

    semantic_decision = _semantic_decision_payload(request)
    if semantic_decision:
        semantic_block_payload: dict[str, Any] = {
            "trusted_semantic_decision": semantic_decision,
            "instruction": (
                "Use this for routing and clarification. It is not "
                "a source for executable fields."
            ),
        }
        required_clarification = request.trusted_facts.get("required_clarification")
        if isinstance(required_clarification, Mapping):
            semantic_block_payload["required_clarification_instruction"] = dict(
                required_clarification
            )
        blocks.append(
            PromptBlock(
                "semantic_decision",
                _json_block(semantic_block_payload),
            )
        )

    focus = _context_value(request.context, "focus_subject")
    if focus:
        blocks.append(PromptBlock("focus", _json_block(focus)))

    domain_result = _domain_result_payload(request)
    if domain_result:
        blocks.append(PromptBlock("domain_result", _domain_result_block(domain_result)))

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


def _semantic_decision_payload(request: AgentRequest) -> Mapping[str, Any] | None:
    semantic = request.trusted_facts.get("semantic_decision")
    if isinstance(semantic, Mapping):
        return dict(semantic)
    semantic = _context_value(request.context, "semantic_decision")
    if semantic is None:
        return None
    return _jsonable(semantic)


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
