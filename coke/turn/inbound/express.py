from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Mapping

from agno.agent import Agent

from coke.llm.agno_interaction_agent import (
    CokeVoicePolicy,
    _is_completed_stream_event,
    _ReplySegmentStreamParser,
    _stream_text_delta,
)
from coke.turn.inbound.contracts import ActionOutcome, SettledOutcome

if TYPE_CHECKING:
    from coke.llm.config import ZAILLMConfig

AgentFactory = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ExpressRequest:
    turn_id: str
    conversation_id: str
    account_id: str
    settled_outcome: SettledOutcome
    current_time: str = ""
    default_timezone: str = "UTC"
    current_input_messages: Sequence[Mapping[str, Any]] = ()
    conversation_history: Sequence[Mapping[str, Any]] = ()
    persona: str = ""
    assistant_name: str = "Coke"
    user_address_name: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    onboarding_guidance: Mapping[str, Any] | None = None


class ExpressOutputError(RuntimeError):
    """Raised when Express does not return Coke reply segments."""


class ExpressAgent:
    def __init__(
        self,
        *,
        model: Any,
        agent_factory: AgentFactory = Agent,
    ) -> None:
        self.model = model
        self.agent_factory = agent_factory

    @classmethod
    def from_config(cls, config: ZAILLMConfig) -> ExpressAgent:
        return cls(model=config.create_express_model())

    def render(self, request: ExpressRequest) -> tuple[str, ...]:
        agent = self._build_agent(request)
        run_output = agent.run(
            _agent_input(request),
            **_run_kwargs(request),
        )
        return _with_onboarding_guidance(
            request,
            _segments_from_content(getattr(run_output, "content", None), request),
        )

    async def render_streaming(
        self,
        request: ExpressRequest,
    ) -> AsyncIterator[str]:
        agent = self._build_agent(request)
        parser = _ReplySegmentStreamParser()
        content_buffer = ""
        final_content: Any = None
        generated_segments: list[str] = []
        stream = agent.arun(
            _agent_input(request),
            **_run_kwargs(request, run_id=request.run_id or request.turn_id),
            stream=True,
            stream_events=True,
        )
        if not hasattr(stream, "__aiter__"):
            for segment in _with_onboarding_guidance(
                request,
                _segments_from_content(getattr(stream, "content", None), request),
            ):
                yield segment
            return

        async for event in stream:
            content = getattr(event, "content", None)
            if _is_completed_stream_event(event):
                final_content = content
                continue
            if isinstance(content, str):
                delta, content_buffer = _stream_text_delta(content_buffer, content)
                generated_segments.extend(parser.feed(delta))
            elif isinstance(content, Mapping):
                final_content = content

        if final_content is None:
            final_content = content_buffer
        generated_segments.extend(
            _segments_from_content(final_content, request)[parser.emitted_count :]
        )
        for segment in _with_onboarding_guidance(request, tuple(generated_segments)):
            yield segment

    def _build_agent(self, request: ExpressRequest) -> Any:
        return self.agent_factory(
            model=self.model,
            tools=[],
            system_message=_system_message(request),
            instructions=_instructions(),
            use_json_mode=True,
            parse_response=False,
            add_history_to_context=False,
            add_session_state_to_context=False,
            enable_agentic_memory=False,
            update_memory_on_run=False,
            enable_user_memories=False,
            add_memories_to_context=False,
        )


def _run_kwargs(
    request: ExpressRequest,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "user_id": request.account_id,
        "session_id": request.conversation_id,
        "metadata": {
            "turn_id": request.turn_id,
            "role": "express",
        },
        "add_session_state_to_context": False,
    }
    if run_id is not None:
        kwargs["run_id"] = run_id
    return kwargs


def _agent_input(request: ExpressRequest) -> str:
    # Pass the render context as a JSON STRING user message. Passing a raw dict
    # makes Agno build a message with non-string content, which the GLM/ZAI API
    # rejects with "messages parameter is illegal". This mirrors the interpreter/
    # planner JSON client (Message(role="user", content=json.dumps(...))).
    payload = {
        "mode": "converse" if not request.settled_outcome.outcomes else "render",
        "clock": {
            "current_time": request.current_time,
            "default_timezone": request.default_timezone,
        },
        "settled_outcome": _settled_outcome_payload(request.settled_outcome),
        "current_input_messages": [
            _plain_value(message) for message in request.current_input_messages
        ],
        "conversation_history": [
            _plain_value(message) for message in request.conversation_history
        ],
        "persona": request.persona,
        "payload": _plain_value(request.payload),
    }
    if request.onboarding_guidance:
        payload["onboarding_guidance"] = _plain_value(request.onboarding_guidance)
    return json.dumps(payload, ensure_ascii=False)


def _settled_outcome_payload(settled_outcome: SettledOutcome) -> dict[str, Any]:
    return {
        "outcomes": [
            {
                "category": outcome.category,
                "status": outcome.status,
                "data": _plain_value(outcome.data),
            }
            for outcome in settled_outcome.outcomes
        ]
    }


def _plain_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _plain_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain_value(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


_ONBOARDING_CAPABILITY_LABELS = {
    "reminders": "设置提醒",
    "shared_reminders_with_friends": "和好友创建共享提醒",
    "availability_checks": "查询好友空闲时间",
    "long_term_memory_preferences": "记住你的长期偏好",
}

_ONBOARDING_CAPABILITY_TERMS = {
    "reminders": ("设置提醒", "设提醒", "提醒", "reminder"),
    "shared_reminders_with_friends": (
        "和好友创建共享提醒",
        "好友共享提醒",
        "朋友共享提醒",
        "共享提醒",
        "好友",
        "朋友",
        "sharedreminder",
        "sharedreminders",
        "friend",
    ),
    "availability_checks": (
        "查询好友空闲时间",
        "查空闲时间",
        "查询空闲时间",
        "空闲时间",
        "空闲",
        "availability",
        "available",
    ),
    "long_term_memory_preferences": (
        "记住你的长期偏好",
        "长期偏好",
        "记住你的偏好",
        "偏好",
        "memory",
        "preference",
        "preferences",
    ),
}


def _with_onboarding_guidance(
    request: ExpressRequest,
    segments: tuple[str, ...],
) -> tuple[str, ...]:
    first_use_no_action = not request.settled_outcome.outcomes
    guidance_text = _onboarding_guidance_text(
        request,
        include_starter_question=first_use_no_action,
    )
    if not guidance_text:
        return segments
    if first_use_no_action:
        return _first_use_no_action_segments(
            segments,
            guidance=request.onboarding_guidance,
            guidance_text=guidance_text,
        )
    if _segments_include_onboarding(
        segments,
        guidance=request.onboarding_guidance,
        guidance_text=guidance_text,
    ):
        return segments
    if len(segments) >= 3:
        return (*segments[:2], f"{segments[2]}\n{guidance_text}")
    return (*segments, guidance_text)


def _onboarding_guidance_text(
    request: ExpressRequest,
    *,
    include_starter_question: bool = False,
) -> str | None:
    guidance = request.onboarding_guidance
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
    assistant_name = guidance.get("assistant_name") or request.assistant_name or "Coke"
    if not isinstance(assistant_name, str) or not assistant_name.strip():
        assistant_name = "Coke"
    assistant_name = assistant_name.strip()
    role_intro = (
        "我会在微信里做你的健康搭子：督促你推进近期目标并提醒，"
        "帮你用日历和别人约时间，也可以直接回答问题。"
    )
    if include_starter_question:
        address_name = request.user_address_name.strip()
        greeting = (
            f"Hi, {address_name}！我是 {assistant_name}，你的提醒和约课小助手。"
            if address_name
            else f"Hi！我是 {assistant_name}，你的提醒和约课小助手。"
        )
        return f"{greeting}\n{role_intro}"
    return f"我是 {assistant_name}，你的提醒和约课小助手。{role_intro}"


def _first_use_no_action_segments(
    segments: tuple[str, ...],
    *,
    guidance: Mapping[str, Any] | None,
    guidance_text: str,
) -> tuple[str, ...]:
    followups = [
        segment
        for segment in segments
        if not _is_redundant_first_use_segment(
            segment,
            guidance=guidance,
            guidance_text=guidance_text,
        )
    ]
    return (*_guidance_segments(guidance_text), *followups[:1])


def _guidance_segments(guidance_text: str) -> tuple[str, ...]:
    return tuple(
        segment.strip() for segment in guidance_text.splitlines() if segment.strip()
    )


def _is_redundant_first_use_segment(
    segment: str,
    *,
    guidance: Mapping[str, Any] | None,
    guidance_text: str,
) -> bool:
    normalized = _normalize_onboarding_text(segment)
    if not normalized:
        return True
    if normalized in {"hi", "hello", "hey", "你好", "嗨", "哈喽", "哈啰"}:
        return True
    normalized_guidance = _normalize_onboarding_text(guidance_text)
    if normalized in normalized_guidance or normalized_guidance in normalized:
        return True
    if "coke" in normalized and any(
        marker in normalized for marker in ("健康搭子", "提醒和约课小助手")
    ):
        return True
    if _segments_include_onboarding(
        (segment,),
        guidance=guidance,
        guidance_text=guidance_text,
    ):
        return True
    return "提醒" in normalized and any(
        marker in normalized
        for marker in ("这两天", "有什么要做", "要做的事情", "需要我提醒", "有没有")
    )


def _segments_include_onboarding(
    segments: tuple[str, ...],
    *,
    guidance: Mapping[str, Any] | None = None,
    guidance_text: str | None = None,
) -> bool:
    normalized_segments = [_normalize_onboarding_text(segment) for segment in segments]
    if guidance_text:
        normalized_guidance = _normalize_onboarding_text(guidance_text)
        if normalized_guidance and normalized_guidance in normalized_segments:
            return True

    compact_text = _normalize_onboarding_text("\n".join(segments))
    if not compact_text:
        return False

    supported_capabilities: tuple[str, ...]
    if isinstance(guidance, Mapping) and isinstance(
        guidance.get("supported_capabilities"), list | tuple
    ):
        supported_capabilities = tuple(
            str(item)
            for item in guidance["supported_capabilities"]
            if item in _ONBOARDING_CAPABILITY_TERMS
        )
    else:
        supported_capabilities = (
            "reminders",
            "shared_reminders_with_friends",
            "availability_checks",
        )
    if not supported_capabilities:
        return False
    return all(
        any(_normalize_onboarding_text(term) in compact_text for term in terms)
        for capability, terms in _ONBOARDING_CAPABILITY_TERMS.items()
        if capability in supported_capabilities
    )


def _normalize_onboarding_text(text: str) -> str:
    return re.sub(r"[\s，,。.!！?？~～、：:；;（）()]+", "", text).casefold()


def _system_message(request: ExpressRequest) -> str:
    address = (
        f"Address the user as {request.user_address_name} when it is natural."
        if request.user_address_name
        else ""
    )
    return "\n".join(
        part
        for part in (
            f"You are {request.assistant_name}, Coke's Express layer.",
            address,
            request.persona,
            "You have no tools and must not imply tool calls or domain mutation.",
            "Describe only the provided settled_outcome for product state.",
            _clock_system_message(request),
            (
                "Render every outcome's category and mandatory status faithfully; "
                "status is the domain truth, not a style hint."
            ),
            (
                "A done.partial outcome must be stated as partial and must name "
                "the failures from the outcome data."
            ),
            "A duplicate_active status must not be reported as a fresh create.",
            "An already_cancelled status must not be reported as a new cancel.",
            "For needs_choice, list the candidates and ask which one.",
            (
                "For needs_input or needs_confirmation, ask only for the missing "
                "or risky thing."
            ),
            "For no-action turns with no outcomes, converse from the supplied history and persona.",
            _onboarding_system_message(request),
            "Do not claim any state change not present in settled_outcome.",
            (
                "If the reply asserts a conflict, refusal, can't do it, "
                "unavailability, duplicate, or blocker, include domain_claim "
                "with domain, category, status, claim, and blocker when a "
                "blocker kind exists; those fields must match one "
                "settled_outcome exactly. For done/created/normal outcomes, do "
                "not assert or domain_claim a blocker."
            ),
            (
                "Do not invent a blocker justification, activity, participant, "
                "date, or time that is absent from settled_outcome data."
            ),
            (
                "For social_scheduling availability outcomes, render only the "
                "friend display name, query window, and busy/free windows from "
                "settled_outcome.availability; never include reminder titles, "
                "activities, locations, or participants from conversation history."
            ),
            'Return only JSON: {"type":"reply","segments":["text"]}.',
            "Text output is limited to one to three non-empty segments.",
            (
                "Render a list (e.g. a reminder list) as a SINGLE segment with "
                "each item on its own line; never emit one segment per list item. "
                "Total reply is 1-3 segments."
            ),
            CokeVoicePolicy().render(),
        )
        if part
    )


def _onboarding_system_message(request: ExpressRequest) -> str:
    if not isinstance(request.onboarding_guidance, Mapping):
        return ""
    return (
        "First-use guidance is required in this visible final reply. Use "
        "onboarding_guidance as role and capability constraints. If the "
        "generated reply omits that guidance, Express will append the "
        "configured greeting and role guidance."
    )


def _clock_system_message(request: ExpressRequest) -> str:
    parts = []
    if request.current_time:
        parts.append(
            "The authoritative current time is "
            f"{request.current_time} in {request.default_timezone}. Treat this "
            "as the only now/today anchor. Do not infer the current date or "
            "time from conversation history."
        )
    parts.append(
        "When an outcome provides a *_display sibling for a datetime field, "
        "MUST use the provided *_display field verbatim for the date, relative "
        "day, and clock. Do not recompute 今天/明天, remaining time, or clock "
        "labels from raw ISO fields or conversation history."
    )
    return " ".join(parts)


def _instructions() -> list[str]:
    return [
        "Use the input settled_outcome as the only product-state source.",
        (
            "Use clock.current_time as authoritative now and never infer now, "
            "today, tomorrow, or elapsed/remaining time from conversation history."
        ),
        (
            "For datetime fields with a *_display sibling, use *_display "
            "verbatim when stating the date, relative day, or clock."
        ),
        (
            "For availability outcomes, use only friend display names and "
            "busy/free window times; never include reminder titles, activities, "
            "locations, or participants."
        ),
        "Keep wording concise and user-facing.",
        (
            "Render a list (e.g. a reminder list) as a SINGLE segment with each "
            "item on its own line; never emit one segment per list item. Total "
            "reply is 1-3 segments."
        ),
        "Never expose internal category/status names unless that is the clearest way to avoid overstating the result.",
        (
            "Any conflict, refusal, can't-do-it, unavailability, duplicate, or "
            "blocker wording requires a matching domain_claim bound to a "
            "settled_outcome category/status; otherwise do not use that wording."
        ),
    ]


_BLOCKER_CLAIM_VALUES = {
    "blocker",
    "not_possible",
    "blocked",
    "receiver_conflict",
    "unreachable",
    "duplicate_active",
}
_BLOCKER_OUTCOME_STATUSES = {
    "blocked",
    "receiver_conflict",
    "unreachable",
    "duplicate_active",
}


def _segments_from_content(
    content: Any,
    request: ExpressRequest | None = None,
) -> tuple[str, ...]:
    availability_segments = _availability_segments(request)
    if availability_segments is not None:
        return availability_segments
    payload = _mapping_from_content(content)
    if payload is None:
        # GLM JSON mode is not always honored even on outcome turns (e.g. list
        # replies often come back as a multiline prose list). Plain prose is a
        # valid single-segment reply; the domain_claim guard below only applies to
        # structured replies, so prose carries no fabricated state/blocker claim
        # to validate. Forcing JSON here regressed every prose outcome reply into
        # grounded-failure recovery, so prose is accepted as a single segment.
        if isinstance(content, str) and content.strip():
            return (content.strip(),)
        raise ExpressOutputError("invalid Express output")
    if payload.get("type") == "no_reply":
        raise ExpressOutputError("Express returned no_reply when a reply is required")
    segments = payload.get("segments")
    if not isinstance(segments, list):
        raise ExpressOutputError("Express output missing segments")
    normalized = tuple(
        segment for segment in segments if isinstance(segment, str) and segment
    )
    if not normalized:
        raise ExpressOutputError("Express output has no non-empty segments")
    if len(normalized) > 3:
        raise ExpressOutputError("Express output has too many segments")
    _validate_domain_claim(payload, request)
    return normalized


def _availability_segments(request: ExpressRequest | None) -> tuple[str, ...] | None:
    if request is None:
        return None
    outcomes = request.settled_outcome.outcomes
    if not outcomes or any(outcome.status != "availability" for outcome in outcomes):
        return None

    sections: list[str] = []
    for outcome in outcomes:
        availability = outcome.data.get("availability")
        if not isinstance(availability, list):
            return None
        query_window = _availability_query_window(outcome.data.get("query_window"))
        for item in availability:
            if not isinstance(item, Mapping):
                continue
            name = _availability_friend_name(item)
            if name is None:
                continue
            header = name
            if query_window is not None:
                header = f"{name}（{query_window[0]} 到 {query_window[1]}）"
            window_lines = _availability_window_lines(item.get("windows"))
            if window_lines:
                sections.append("\n".join((header, *window_lines)))
            else:
                sections.append(header)
    if not sections:
        return None
    return ("\n\n".join(sections),)


def _availability_friend_name(item: Mapping[str, Any]) -> str | None:
    for key in ("friend_display_name", "friend_account_id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _availability_query_window(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    return _display_interval(value, "local_start", "local_end")


def _availability_window_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for window in value:
        if not isinstance(window, Mapping):
            continue
        state = window.get("state")
        if state not in {"busy", "free"}:
            continue
        interval = _display_interval(window, "start", "end")
        if interval is None:
            continue
        lines.append(f"- {state}：{interval[0]} 到 {interval[1]}")
    return lines


def _display_interval(
    value: Mapping[str, Any],
    start_key: str,
    end_key: str,
) -> tuple[str, str] | None:
    start = value.get(f"{start_key}_display") or value.get(start_key)
    end = value.get(f"{end_key}_display") or value.get(end_key)
    if not isinstance(start, str) or not start.strip():
        return None
    if not isinstance(end, str) or not end.strip():
        return None
    return start.strip(), end.strip()


def _validate_domain_claim(
    payload: Mapping[str, Any],
    request: ExpressRequest | None,
) -> None:
    if request is None:
        return
    claim = payload.get("domain_claim")
    if claim is None:
        return
    if not isinstance(claim, Mapping):
        raise ExpressOutputError("Express domain_claim must be an object")
    if claim.get("domain") != "social_scheduling":
        return

    matching_outcomes = _matching_claim_outcomes(
        claim,
        request.settled_outcome.outcomes,
    )
    if not matching_outcomes:
        raise ExpressOutputError(
            "Express social_scheduling domain_claim does not match settled_outcome"
        )

    claim_asserts_blocker = _claim_asserts_blocker(claim)
    if not claim_asserts_blocker:
        return

    for outcome in matching_outcomes:
        if _outcome_allows_blocker_claim(outcome, claim):
            return
    raise ExpressOutputError(
        "Express blocker domain_claim is not allowed by settled_outcome"
    )


def _matching_claim_outcomes(
    claim: Mapping[str, Any],
    outcomes: Sequence[ActionOutcome],
) -> tuple[ActionOutcome, ...]:
    claimed_status = claim.get("status")
    if not isinstance(claimed_status, str) or not claimed_status:
        return ()
    claimed_category = claim.get("category")
    return tuple(
        outcome
        for outcome in outcomes
        if outcome.status == claimed_status
        and (
            claimed_category is None
            or (
                isinstance(claimed_category, str)
                and outcome.category == claimed_category
            )
        )
    )


def _claim_asserts_blocker(claim: Mapping[str, Any]) -> bool:
    values = (
        claim.get("claim"),
        claim.get("blocker"),
        claim.get("blocker_kind"),
        claim.get("status"),
        claim.get("category"),
    )
    return any(
        isinstance(value, str) and value in _BLOCKER_CLAIM_VALUES for value in values
    )


def _outcome_allows_blocker_claim(
    outcome: ActionOutcome,
    claim: Mapping[str, Any],
) -> bool:
    if not _is_blocker_outcome(outcome):
        return False
    outcome_blocker = outcome.data.get("blocker")
    if not isinstance(outcome_blocker, Mapping):
        return True
    expected_kind = outcome_blocker.get("kind")
    if not isinstance(expected_kind, str) or not expected_kind:
        return True
    claimed_kind = claim.get("blocker") or claim.get("blocker_kind")
    return claimed_kind == expected_kind


def _is_blocker_outcome(outcome: ActionOutcome) -> bool:
    if outcome.category in {"not_possible", "needs_input", "needs_confirmation"}:
        return True
    return outcome.status in _BLOCKER_OUTCOME_STATUSES or outcome.status.startswith(
        ("needs_", "missing_")
    )


def _mapping_from_content(content: Any) -> Mapping[str, Any] | None:
    if isinstance(content, Mapping):
        return content
    if not isinstance(content, str):
        return None
    text = content.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if isinstance(parsed, Mapping):
        return parsed
    return None
