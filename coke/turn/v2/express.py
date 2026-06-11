from __future__ import annotations

import json
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
from coke.turn.v2.contracts import SettledOutcome

if TYPE_CHECKING:
    from coke.llm.config import ZAILLMConfig

AgentFactory = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ExpressRequest:
    turn_id: str
    conversation_id: str
    account_id: str
    settled_outcome: SettledOutcome
    current_input_messages: Sequence[Mapping[str, Any]] = ()
    conversation_history: Sequence[Mapping[str, Any]] = ()
    persona: str = ""
    assistant_name: str = "Coke"
    user_address_name: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)
    run_id: str | None = None


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
        return cls(model=config.create_interaction_model())

    def render(self, request: ExpressRequest) -> tuple[str, ...]:
        agent = self._build_agent(request)
        run_output = agent.run(
            _agent_input(request),
            **_run_kwargs(request),
        )
        return _segments_from_content(getattr(run_output, "content", None))

    async def render_streaming(
        self,
        request: ExpressRequest,
    ) -> AsyncIterator[str]:
        agent = self._build_agent(request)
        parser = _ReplySegmentStreamParser()
        content_buffer = ""
        final_content: Any = None
        stream = agent.arun(
            _agent_input(request),
            **_run_kwargs(request, run_id=request.run_id or request.turn_id),
            stream=True,
            stream_events=True,
        )
        if not hasattr(stream, "__aiter__"):
            for segment in _segments_from_content(getattr(stream, "content", None)):
                yield segment
            return

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

        if final_content is None:
            final_content = content_buffer
        for segment in _segments_from_content(final_content)[parser.emitted_count :]:
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
    return json.dumps(payload, ensure_ascii=False)


def _settled_outcome_payload(settled_outcome: SettledOutcome) -> dict[str, Any]:
    return {
        "outcomes": [
            {
                "category": outcome.category,
                "status": outcome.status,
                "data": _plain_value(outcome.data),
                "staged_command_id": outcome.staged_command_id,
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
            "Do not claim any state change not present in settled_outcome.",
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


def _instructions() -> list[str]:
    return [
        "Use the input settled_outcome as the only product-state source.",
        "Keep wording concise and user-facing.",
        (
            "Render a list (e.g. a reminder list) as a SINGLE segment with each "
            "item on its own line; never emit one segment per list item. Total "
            "reply is 1-3 segments."
        ),
        "Never expose internal category/status names unless that is the clearest way to avoid overstating the result.",
    ]


def _segments_from_content(content: Any) -> tuple[str, ...]:
    payload = _mapping_from_content(content)
    if payload is None:
        # GLM JSON mode is not always honored for context-light converse turns.
        # Plain prose is a valid single-segment reply — Express makes no state
        # claim for converse, so there is nothing to verify or to overstate.
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
    return normalized


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
