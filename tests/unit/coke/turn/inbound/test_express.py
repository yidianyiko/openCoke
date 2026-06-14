from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from agno.run.agent import RunCompletedEvent, RunContentEvent

from coke.turn.inbound.contracts import ActionOutcome, SettledOutcome
from coke.turn.inbound.express import ExpressAgent, ExpressOutputError, ExpressRequest


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


class SocialBlockerEchoRunAgentInstance:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, input, **kwargs):
        self.calls.append({"method": "run", "input": input, "kwargs": kwargs})
        outcome = json.loads(input)["settled_outcome"]["outcomes"][0]
        blocker = outcome["data"]["blocker"]
        interval = blocker["requested_interval"]
        participant = blocker["conflicting_participants"][0]
        content = json.dumps(
            {
                "type": "reply",
                "segments": [
                    (
                        f"约不了，{participant} 在 "
                        f"{interval['local_start_display']} 到 "
                        f"{interval['local_end_display']} 有冲突。"
                    )
                ],
                "domain_claim": {
                    "domain": "social_scheduling",
                    "category": outcome["category"],
                    "status": outcome["status"],
                    "claim": "blocker",
                    "blocker": blocker["kind"],
                },
            },
            ensure_ascii=False,
        )
        return type("RunOutput", (), {"content": content})()


class AvailabilityLeakRunAgentInstance:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, input, **kwargs):
        self.calls.append({"method": "run", "input": input, "kwargs": kwargs})
        content = json.dumps(
            {
                "type": "reply",
                "segments": ["Oliver 今天有这些安排：开会 6:00、晚饭 19:30。"],
            },
            ensure_ascii=False,
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


def test_render_payload_and_prompt_include_authoritative_clock() -> None:
    fake_agent = StaticRunAgentInstance(
        content=json.dumps({"type": "reply", "segments": ["已建好。"]}),
        calls=[],
    )
    factory = FakeAgentFactory(fake_agent)
    agent = ExpressAgent(model=object(), agent_factory=factory)

    agent.render(
        ExpressRequest(
            turn_id="turn-1",
            conversation_id="conversation-1",
            account_id="account-1",
            current_time="2026-06-14T21:17:00+08:00",
            default_timezone="Asia/Shanghai",
            settled_outcome=SettledOutcome(
                outcomes=(
                    ActionOutcome(
                        category="done",
                        status="created",
                        data={
                            "shared_reminder": {
                                "title": "开会",
                                "local_trigger_at": "2026-06-15T06:00:00",
                                "local_trigger_at_display": "明天上午6点",
                            },
                        },
                    ),
                )
            ),
        )
    )

    input_payload = json.loads(fake_agent.calls[0]["input"])
    assert input_payload["clock"] == {
        "current_time": "2026-06-14T21:17:00+08:00",
        "default_timezone": "Asia/Shanghai",
    }
    system_message = factory.agent_kwargs[0]["system_message"]
    instructions = factory.agent_kwargs[0]["instructions"]
    assert "authoritative current time" in system_message
    assert "2026-06-14T21:17:00+08:00" in system_message
    assert "MUST use the provided *_display field verbatim" in system_message
    assert any("*_display" in instruction for instruction in instructions)


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


def test_created_social_outcome_rejects_fabricated_blocker_claim() -> None:
    fake_agent = StaticRunAgentInstance(
        content=json.dumps(
            {
                "type": "reply",
                "segments": ["约不了，那个时间有冲突了。"],
                "domain_claim": {
                    "domain": "social_scheduling",
                    "category": "not_possible",
                    "status": "receiver_conflict",
                    "claim": "blocker",
                    "blocker": "receiver_conflict",
                },
            },
            ensure_ascii=False,
        ),
        calls=[],
    )
    factory = FakeAgentFactory(fake_agent)
    agent = ExpressAgent(model=object(), agent_factory=factory)

    with pytest.raises(ExpressOutputError, match="domain_claim does not match"):
        agent.render(
            ExpressRequest(
                turn_id="turn-1",
                conversation_id="conversation-1",
                account_id="account-1",
                settled_outcome=SettledOutcome(
                    outcomes=(
                        ActionOutcome(
                            category="done",
                            status="created",
                            data={
                                "shared_reminder": {
                                    "title": "约 Oliver",
                                    "local_trigger_at": "2026-06-15T21:20:00",
                                    "captured_timezone": "Asia/Shanghai",
                                }
                            },
                        ),
                    )
                ),
                conversation_history=(
                    {"role": "assistant", "content": "20:00 有冲突。"},
                ),
            )
        )


def test_receiver_conflict_social_outcome_renders_only_typed_blocker_facts() -> None:
    fake_agent = SocialBlockerEchoRunAgentInstance()
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
                        category="not_possible",
                        status="receiver_conflict",
                        data={
                            "blocker": {
                                "kind": "receiver_conflict",
                                "conflicting_participants": ["friend-oliver"],
                                "requested_interval": {
                                    "local_start": "2026-06-15T21:20:00",
                                    "local_start_display": "明天晚上9点20分",
                                    "local_end": "2026-06-15T21:35:00",
                                    "local_end_display": "明天晚上9点35分",
                                    "captured_timezone": "Asia/Shanghai",
                                    "duration_minutes": 15,
                                },
                            },
                        },
                    ),
                )
            ),
            conversation_history=(
                {"role": "assistant", "content": "20:00 晚饭有冲突。"},
            ),
        )
    )

    assert segments == (
        "约不了，friend-oliver 在 明天晚上9点20分 到 明天晚上9点35分 有冲突。",
    )
    assert "晚饭" not in segments[0]
    assert "20:00" not in segments[0]
    system_message = factory.agent_kwargs[0]["system_message"]
    assert "domain_claim" in system_message
    assert "conflict, refusal, can't do it, unavailability, duplicate, or blocker" in (
        system_message
    )


def test_availability_render_uses_only_public_busy_free_windows_not_history_titles() -> (
    None
):
    fake_agent = AvailabilityLeakRunAgentInstance()
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
                        status="availability",
                        data={
                            "query_window": {
                                "local_start": "2026-06-15T09:00:00",
                                "local_start_display": "明天上午9点",
                                "local_end": "2026-06-15T11:00:00",
                                "local_end_display": "明天上午11点",
                                "requester_timezone": "Asia/Shanghai",
                                "defaulted": False,
                            },
                            "availability": [
                                {
                                    "friend_display_name": "Oliver",
                                    "windows": [
                                        {
                                            "state": "busy",
                                            "start": "2026-06-15T09:00:00",
                                            "start_display": "明天上午9点",
                                            "end": "2026-06-15T10:00:00",
                                            "end_display": "明天上午10点",
                                        },
                                        {
                                            "state": "free",
                                            "start": "2026-06-15T10:00:00",
                                            "start_display": "明天上午10点",
                                            "end": "2026-06-15T11:00:00",
                                            "end_display": "明天上午11点",
                                        },
                                    ],
                                }
                            ],
                        },
                    ),
                )
            ),
            conversation_history=(
                {"role": "assistant", "content": "我和 Oliver 有共享提醒：开会、晚饭"},
            ),
        )
    )

    assert segments == (
        "Oliver（明天上午9点 到 明天上午11点）\n"
        "- busy：明天上午9点 到 明天上午10点\n"
        "- free：明天上午10点 到 明天上午11点",
    )
    visible = "\n".join(segments)
    assert "Oliver" in visible
    assert "busy" in visible
    assert "free" in visible
    assert "开会" not in visible
    assert "晚饭" not in visible
    assert "6:00" not in visible
    assert "19:30" not in visible
    system_message = factory.agent_kwargs[0]["system_message"]
    assert "availability" in system_message
    assert "never include reminder titles" in system_message


def test_no_action_first_use_renders_configured_onboarding_before_model_starter() -> (
    None
):
    fake_agent = StaticRunAgentInstance(
        content=json.dumps(
            {
                "type": "reply",
                "segments": ["这两天有什么要做的事情吗？我到时候提醒你"],
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
            settled_outcome=SettledOutcome(outcomes=()),
            user_address_name="Oliver",
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
        "Hi, Oliver！我是 Coke，你的提醒和约课小助手。",
        "我会在微信里做你的健康搭子：督促你推进近期目标并提醒，帮你用日历和别人约时间，也可以直接回答问题。",
    )
    input_payload = json.loads(fake_agent.calls[0]["input"])
    assert input_payload["onboarding_guidance"]["supported_capabilities"] == [
        "reminders",
        "shared_reminders_with_friends",
        "availability_checks",
        "long_term_memory_preferences",
    ]
    assert "First-use guidance is required" in factory.agent_kwargs[0]["system_message"]


def test_no_action_first_use_normalizes_model_onboarding_to_configured_copy() -> None:
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

    assert segments == (
        "Hi！我是 Coke，你的提醒和约课小助手。",
        "我会在微信里做你的健康搭子：督促你推进近期目标并提醒，帮你用日历和别人约时间，也可以直接回答问题。",
    )


def test_no_action_first_use_drops_role_intro_duplicate() -> None:
    fake_agent = StaticRunAgentInstance(
        content=json.dumps(
            {
                "type": "reply",
                "segments": ["Hi！我是 Coke，你的微信健康搭子、提醒和约课小助手"],
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
        "Hi！我是 Coke，你的提醒和约课小助手。",
        "我会在微信里做你的健康搭子：督促你推进近期目标并提醒，帮你用日历和别人约时间，也可以直接回答问题。",
    )


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
        "我是 Coke，你的提醒和约课小助手。我会在微信里做你的健康搭子：督促你推进近期目标并提醒，帮你用日历和别人约时间，也可以直接回答问题。",
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


def test_prose_reply_on_outcome_turn_is_accepted_single_segment() -> None:
    # Regression: GLM often returns a prose (non-JSON) list for outcome turns.
    # Express must accept it as a single segment, not fall to grounded-failure
    # recovery. (RC2 force-JSON regressed every prose outcome reply.)
    from coke.turn.inbound.express import _segments_from_content

    request = ExpressRequest(
        turn_id="t",
        conversation_id="c",
        account_id="a",
        settled_outcome=SettledOutcome(
            outcomes=(
                ActionOutcome(
                    category="done",
                    status="listed",
                    data={"reminders": [{"content": "开会"}], "count": 1},
                ),
            )
        ),
    )
    segments = _segments_from_content("今天的提醒：\n开会\n晚饭", request)
    assert segments == ("今天的提醒：\n开会\n晚饭",)
