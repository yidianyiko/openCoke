from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from agno.run.agent import RunCompletedEvent, RunContentEvent

from coke.turn.inbound.contracts import ActionOutcome, SettledOutcome
from coke.turn.inbound.express import ExpressAgent, ExpressRequest


@dataclass
class StaticRunAgentInstance:
    content: str
    calls: list[dict[str, Any]]

    def run(self, input, **kwargs):
        self.calls.append({"method": "run", "input": input, "kwargs": kwargs})
        return type("RunOutput", (), {"content": self.content})()


class PartialEchoRunAgentInstance:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, input, **kwargs):
        self.calls.append({"method": "run", "input": input, "kwargs": kwargs})
        outcome = json.loads(input)["settled_outcome"]["outcomes"][0]
        failed = outcome["data"]["failed"][0]
        content = json.dumps(
            {
                "type": "reply",
                "segments": [
                    (
                        f"Partial result: {outcome['status']}; "
                        f"failed {failed['content']} because {failed['reason']}"
                    )
                ],
            }
        )
        return type("RunOutput", (), {"content": content})()


class ReminderListEchoRunAgentInstance:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, input, **kwargs):
        self.calls.append({"method": "run", "input": input, "kwargs": kwargs})
        reminders = json.loads(input)["settled_outcome"]["outcomes"][0]["data"][
            "reminders"
        ]
        content = json.dumps(
            {
                "type": "reply",
                "segments": [
                    "\n".join(
                        f"{index}. {reminder['content']}"
                        for index, reminder in enumerate(reminders, start=1)
                    )
                ],
            }
        )
        return type("RunOutput", (), {"content": content})()


class PartialEchoStreamingAgentInstance:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def arun(self, input, **kwargs):
        # Agno returns an AsyncIterator directly for stream=True. This method is
        # intentionally not async so awaiting it would fail.
        self.calls.append({"method": "arun", "input": input, "kwargs": kwargs})
        outcome = json.loads(input)["settled_outcome"]["outcomes"][0]
        failed = outcome["data"]["failed"][0]
        content = json.dumps(
            {
                "type": "reply",
                "segments": [
                    (
                        f"Partial result: {outcome['status']}; "
                        f"failed {failed['content']} because {failed['reason']}"
                    ),
                    "Which one should I try next?",
                ],
            }
        )

        async def stream():
            yield RunContentEvent(content=content[:32])
            yield RunContentEvent(content=content[32:66])
            yield RunContentEvent(content=content[66:])
            yield RunCompletedEvent(content=content)

        return stream()


class FakeAgentFactory:
    def __init__(self, instance: Any) -> None:
        self.instance = instance
        self.agent_kwargs: list[dict[str, Any]] = []

    def __call__(self, **kwargs):
        self.agent_kwargs.append(kwargs)
        return self.instance


def test_render_produces_segments_from_settled_outcome() -> None:
    fake_agent = StaticRunAgentInstance(
        content=json.dumps(
            {
                "type": "reply",
                "segments": ["Listed 1 reminder", "Anything else?"],
            }
        ),
        calls=[],
    )
    factory = FakeAgentFactory(fake_agent)
    agent = ExpressAgent(model=object(), agent_factory=factory)

    segments = agent.render(
        ExpressRequest(
            turn_id="turn-1",
            conversation_id="conversation-1",
            account_id="account-1",
            settled_outcome=SettledOutcome(
                outcomes=(
                    ActionOutcome(
                        category="done",
                        status="listed",
                        data={"count": 1},
                    ),
                )
            ),
        )
    )

    assert segments == ("Listed 1 reminder", "Anything else?")
    assert json.loads(fake_agent.calls[0]["input"])["settled_outcome"]["outcomes"][
        0
    ] == {
        "category": "done",
        "status": "listed",
        "data": {"count": 1},
    }
    agent_kwargs = factory.agent_kwargs[0]
    assert agent_kwargs["tools"] == []
    assert agent_kwargs["add_history_to_context"] is False
    assert agent_kwargs["use_json_mode"] is True


def test_render_keeps_reminder_list_in_one_multiline_segment() -> None:
    fake_agent = ReminderListEchoRunAgentInstance()
    factory = FakeAgentFactory(fake_agent)
    agent = ExpressAgent(model=object(), agent_factory=factory)

    segments = agent.render(
        ExpressRequest(
            turn_id="turn-1",
            conversation_id="conversation-1",
            account_id="account-1",
            settled_outcome=SettledOutcome(
                outcomes=(
                    ActionOutcome(
                        category="done",
                        status="listed",
                        data={
                            "count": 2,
                            "reminders": [
                                {"content": "take meds"},
                                {"content": "call mom"},
                            ],
                        },
                    ),
                )
            ),
        )
    )

    assert len(segments) == 1
    assert segments == ("1. take meds\n2. call mom",)
    assert (
        "list (e.g. a reminder list) as a SINGLE segment"
        in factory.agent_kwargs[0]["system_message"]
    )


def test_render_appends_onboarding_guidance_when_model_omits_it() -> None:
    fake_agent = StaticRunAgentInstance(
        content=json.dumps({"type": "reply", "segments": ["Hi~"]}),
        calls=[],
    )
    factory = FakeAgentFactory(fake_agent)
    agent = ExpressAgent(model=object(), agent_factory=factory)

    segments = agent.render(
        ExpressRequest(
            turn_id="turn-1",
            conversation_id="conversation-1",
            account_id="account-1",
            settled_outcome=SettledOutcome(outcomes=()),
            onboarding_guidance={
                "assistant_name": "Coke",
                "supported_capabilities": [
                    "reminders",
                    "shared_reminders_with_friends",
                    "availability_checks",
                    "long_term_memory_preferences",
                ],
            },
        )
    )

    assert segments == (
        "Hi~",
        "我是 Coke，你的提醒和约课小助手。你可以直接让我设置提醒、和好友创建共享提醒、查询好友空闲时间、记住你的长期偏好。",
    )
    input_payload = json.loads(fake_agent.calls[0]["input"])
    assert input_payload["onboarding_guidance"]["supported_capabilities"] == [
        "reminders",
        "shared_reminders_with_friends",
        "availability_checks",
        "long_term_memory_preferences",
    ]
    assert "First-use guidance is required" in factory.agent_kwargs[0]["system_message"]


def test_render_does_not_append_duplicate_onboarding_when_model_mentions_synonyms() -> (
    None
):
    model_onboarding = "我是Coke，可以帮你设提醒、和朋友共享提醒、查空闲时间，还会记住你的偏好，随时找我聊"
    fake_agent = StaticRunAgentInstance(
        content=json.dumps({"type": "reply", "segments": ["Hi～", model_onboarding]}),
        calls=[],
    )
    factory = FakeAgentFactory(fake_agent)
    agent = ExpressAgent(model=object(), agent_factory=factory)

    segments = agent.render(
        ExpressRequest(
            turn_id="turn-1",
            conversation_id="conversation-1",
            account_id="account-1",
            settled_outcome=SettledOutcome(outcomes=()),
            onboarding_guidance={
                "assistant_name": "Coke",
                "supported_capabilities": [
                    "reminders",
                    "shared_reminders_with_friends",
                    "availability_checks",
                    "long_term_memory_preferences",
                ],
            },
        )
    )

    assert segments == ("Hi～", model_onboarding)


def test_render_prompt_and_segments_preserve_partial_failure_facts() -> None:
    fake_agent = PartialEchoRunAgentInstance()
    factory = FakeAgentFactory(fake_agent)
    agent = ExpressAgent(model=object(), agent_factory=factory)

    segments = agent.render(_partial_request())

    assert segments == (
        "Partial result: partial; failed gym because already_cancelled",
    )
    system_message = factory.agent_kwargs[0]["system_message"]
    assert "partial" in system_message
    assert "duplicate_active" in system_message
    assert "already_cancelled" in system_message
    input_outcome = json.loads(fake_agent.calls[0]["input"])["settled_outcome"][
        "outcomes"
    ][0]
    assert input_outcome["category"] == "done"
    assert input_outcome["status"] == "partial"
    assert input_outcome["data"]["failed"] == [
        {"content": "gym", "reason": "already_cancelled"}
    ]


@pytest.mark.asyncio
async def test_render_streaming_yields_complete_segments_without_awaiting_arun() -> (
    None
):
    fake_agent = PartialEchoStreamingAgentInstance()
    factory = FakeAgentFactory(fake_agent)
    agent = ExpressAgent(model=object(), agent_factory=factory)

    segments = [segment async for segment in agent.render_streaming(_partial_request())]

    assert segments == [
        "Partial result: partial; failed gym because already_cancelled",
        "Which one should I try next?",
    ]
    call = fake_agent.calls[0]
    assert call["kwargs"]["stream"] is True
    assert call["kwargs"]["stream_events"] is True
    assert call["kwargs"]["run_id"] == "turn-1"


@pytest.mark.asyncio
async def test_render_streaming_appends_onboarding_guidance_when_model_omits_it() -> (
    None
):
    fake_agent = PartialEchoStreamingAgentInstance()
    factory = FakeAgentFactory(fake_agent)
    agent = ExpressAgent(model=object(), agent_factory=factory)
    request = _partial_request(
        onboarding_guidance={
            "assistant_name": "Coke",
            "supported_capabilities": [
                "reminders",
                "shared_reminders_with_friends",
                "availability_checks",
            ],
        }
    )

    segments = [segment async for segment in agent.render_streaming(request)]

    assert segments == [
        "Partial result: partial; failed gym because already_cancelled",
        "Which one should I try next?",
        "我是 Coke，你的提醒和约课小助手。你可以直接让我设置提醒、和好友创建共享提醒、查询好友空闲时间。",
    ]


def _partial_request(
    *,
    onboarding_guidance: dict[str, Any] | None = None,
) -> ExpressRequest:
    return ExpressRequest(
        turn_id="turn-1",
        conversation_id="conversation-1",
        account_id="account-1",
        settled_outcome=SettledOutcome(
            outcomes=(
                ActionOutcome(
                    category="done",
                    status="partial",
                    data={
                        "succeeded": [{"content": "water"}],
                        "failed": [{"content": "gym", "reason": "already_cancelled"}],
                    },
                ),
            )
        ),
        conversation_history=({"role": "user", "content": "cancel water and gym"},),
        persona="concise supervisor",
        onboarding_guidance=onboarding_guidance,
    )


def test_plain_text_converse_output_is_a_single_segment() -> None:
    from coke.turn.inbound.express import _segments_from_content

    assert _segments_from_content("在的，最近挺好的，你呢？") == (
        "在的，最近挺好的，你呢？",
    )


def test_no_reply_payload_raises_when_express_reply_is_required() -> None:
    from coke.turn.inbound.express import ExpressOutputError, _segments_from_content

    with pytest.raises(
        ExpressOutputError,
        match="Express returned no_reply when a reply is required",
    ):
        _segments_from_content({"type": "no_reply"})
