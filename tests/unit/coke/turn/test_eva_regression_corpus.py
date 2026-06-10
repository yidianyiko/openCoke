from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import count
from types import SimpleNamespace
from typing import Any

import pytest

from coke.composition import SocialSchedulingToolAdapter
from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.domains.reminder.models import Reminder, ReminderFire
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService
from coke.domains.social_scheduling.availability import (
    BusyInterval,
    ParticipantReachabilityPort,
    ReminderAvailabilityPort,
)
from coke.domains.social_scheduling.models import (
    Friendship,
    RecoverableSchedulingIntent,
)
from coke.domains.social_scheduling.repository import (
    InMemorySocialSchedulingRepository,
)
from coke.domains.social_scheduling.service import SocialSchedulingService
from coke.turn.agent import AgentResult, AgentToolPorts
from coke.turn.context import TurnMode, TurnTrigger
from coke.turn.locks import ConversationLockManager
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.runner import DeliveryOutcome, TurnRunner
from coke.turn.semantic_interpreter import FollowUpAction, SemanticDecision
from coke.turn.staged_commands import StagedCommandMaterializer

EVA_NOW = datetime(2026, 6, 6, 2, 51, 34, tzinfo=UTC)
TRACEPARENT = "00-eva00000000000000000000000000000-1111111111111111-01"


@dataclass
class EvaRuntimeFixture:
    clock: MutableClock
    repository: InMemoryConversationRuntimeRepository
    runtime: ConversationRuntimeService
    gate: FakeGatePort
    semantic: FakeSemanticInterpreter
    memory: FakeMemoryPort
    agent: ScriptedAgent
    delivery: CapturingDelivery
    reminder_repository: InMemoryReminderRepository
    reminder_service: ReminderService
    trigger: TurnTrigger


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def id_factory():
    counter = count(1)
    return lambda prefix: f"{prefix}_{next(counter)}"


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, name, value, nx=False, px=None):
        if nx and name in self.values:
            return False
        self.values[name] = value
        return True

    def get(self, name):
        return self.values.get(name)

    def pexpire(self, name, ttl_ms):
        return name in self.values

    def delete(self, name):
        existed = name in self.values
        self.values.pop(name, None)
        return 1 if existed else 0

    def acquire_lock(self, name: str, token: str, ttl_ms: int) -> bool:
        return bool(self.set(name, token, nx=True, px=ttl_ms))

    def get_token(self, name: str) -> str | None:
        return self.get(name)

    def extend_if_owned(self, name: str, token: str, ttl_ms: int) -> bool:
        return self.get(name) == token and bool(self.pexpire(name, ttl_ms))

    def release_if_owned(self, name: str, token: str) -> bool:
        if self.get(name) != token:
            return False
        return bool(self.delete(name))


class FakeGatePort:
    def __init__(self) -> None:
        self.account_timezone = "Asia/Shanghai"
        self.trust_facts: dict[str, Any] = {
            "default_timezone": "Asia/Shanghai",
            "memory_enabled": True,
        }

    def evaluate(self, trigger: TurnTrigger) -> GateDecision:
        return GateDecision.allowed(
            trust_facts={
                "account_id": trigger.account_id,
                **self.trust_facts,
            }
        )


class FakeSemanticInterpreter:
    def __init__(self) -> None:
        self.next_decision = SemanticDecision(
            reply_necessity="reply_needed",
            intent_family="chit_chat",
            intent_action="chit_chat",
            ambiguity="clear",
            required_clarification="none",
            language_hint="zh",
        )
        self.requests = []

    def interpret(self, request):
        self.requests.append(request)
        return self.next_decision


class FakeMemoryPort:
    def recent_context(self, conversation_id: str):
        return ("Eva recently mentioned olivers, coffee, 11:40, and 15:00.",)

    def long_term_context(self, account_id: str):
        return ()


class ScriptedAgent:
    def __init__(self) -> None:
        self.requests = []
        self.queued_results: list[AgentResult] = []
        self.next_result = AgentResult.completed(
            {"type": "reply", "segments": ["ok"]}
        )
        self.next_async_result = AgentResult.completed(
            {"type": "reply", "segments": ["final"]}
        )

    def invoke(self, request):
        self.requests.append(request)
        if self.queued_results:
            return self.queued_results.pop(0)
        return self.next_result

    async def ainvoke(self, request):
        return self.invoke(request)

    async def cancel(self, run_id: str) -> bool:
        return True

    def complete_async(self, task_id: str):
        return self.next_async_result


class CapturingDelivery:
    def __init__(self) -> None:
        self.deliveries = []
        self.outcomes: list[DeliveryOutcome] = []
        self.fail_waiting_with: str | None = None

    def deliver(self, request):
        self.deliveries.append(request)
        if request.message_type == "waiting" and self.fail_waiting_with is not None:
            outcome = DeliveryOutcome(
                status="failed",
                error_code=self.fail_waiting_with,
                attempt=SimpleNamespace(provider_type="wechat_personal"),
            )
        else:
            outcome = DeliveryOutcome(
                status="delivered",
                attempt=SimpleNamespace(provider_type="wechat_personal"),
            )
        self.outcomes.append(outcome)
        return outcome


class FakeReachability(ParticipantReachabilityPort):
    def __init__(self, reachable: set[str] | None = None) -> None:
        self.reachable = reachable or set()

    def has_usable_channel(self, account_id: str) -> bool:
        return account_id in self.reachable


class FakeReminderAvailability(ReminderAvailabilityPort):
    def __init__(self) -> None:
        self.intervals: dict[str, list[BusyInterval]] = {}

    def personal_busy_intervals(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
        requester_timezone: str,
    ) -> list[BusyInterval]:
        return [
            interval
            for interval in self.intervals.get(account_id, [])
            if interval.start < end and interval.end > start
        ]


class RecoveringEvaAgent(ScriptedAgent):
    def __init__(self) -> None:
        super().__init__()
        self.tool_result = None

    def invoke(self, request):
        self.requests.append(request)
        recovery = request.trusted_facts["recoverable_scheduling_intent"]
        self.tool_result = request.tool_profile.social_scheduling_tool.execute(
            {
                "operation": "create_shared_reminder",
                "creator_account_id": request.account_id,
                "receiver_account_ids": [recovery["resolved_friend_account_id"]],
                "title": recovery["title"],
                "local_trigger_at": recovery["local_trigger_at"],
                "captured_timezone": recovery["captured_timezone"],
                "duration_minutes": recovery["duration_minutes"],
                "recoverable_scheduling_intent_id": recovery["id"],
                "facts_hash": recovery["facts_hash"],
            },
            request.freshness_guard,
        )
        return AgentResult.completed(
            {
                "type": "reply",
                "segments": ["已经按 zihao=Olivers 继续约好 11:40 的午饭。"],
            }
        )


class AvailabilityEvaAgent(ScriptedAgent):
    def __init__(self) -> None:
        super().__init__()
        self.tool_result = None

    def invoke(self, request):
        self.requests.append(request)
        self.tool_result = request.tool_profile.social_scheduling_tool.execute(
            {
                "operation": "query_availability",
                "requester_account_id": request.account_id,
                "friend_account_ids": ["friend_olivers"],
                "local_start": "2026-06-06T14:00:00",
                "local_end": "2026-06-06T15:30:00",
                "requester_timezone": "Asia/Shanghai",
            },
            request.freshness_guard,
        )
        return AgentResult.completed(
            {
                "type": "reply",
                "segments": ["Olivers 14:00-14:15忙，15:00-15:15忙，其他时间空。"],
            }
        )


class SupersedingSoftSuccessAgent(ScriptedAgent):
    def __init__(self, runtime: ConversationRuntimeService) -> None:
        super().__init__()
        self.runtime = runtime
        self.tool_result = None

    def invoke(self, request):
        self.requests.append(request)
        self.tool_result = request.tool_profile.social_scheduling_tool.execute(
            {
                "operation": "create_shared_reminder",
                "creator_account_id": request.account_id,
                "receiver_account_ids": ["friend_olivers"],
                "title": "下午三点咖啡",
                "local_trigger_at": "2026-06-06T15:00:00",
                "captured_timezone": "Asia/Shanghai",
                "duration_minutes": 45,
            },
            request.freshness_guard,
        )
        self.runtime.record_inbound(
            account_id=request.account_id,
            channel_identity_id="channel_identity_1",
            causal_inbound_event_id="provider:eva-message-2",
            text="等等，不是咖啡",
            payload={"provider": "wechat_personal"},
            traceparent=TRACEPARENT,
        )
        return AgentResult.completed(
            {
                "type": "reply",
                "segments": ["好，已经帮你发起邀约，等他确认~"],
            }
        )


def _runtime_fixture(initial_text: str = "hello") -> EvaRuntimeFixture:
    clock = MutableClock(EVA_NOW)
    repository = InMemoryConversationRuntimeRepository(now=clock.now)
    runtime = ConversationRuntimeService(
        repository=repository,
        now=clock.now,
        id_factory=id_factory(),
    )
    inbound = runtime.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:eva-message-1",
        text=initial_text,
        payload={"provider": "wechat_personal"},
        traceparent=TRACEPARENT,
    )
    reminder_repository = InMemoryReminderRepository()
    reminder_service = ReminderService(
        repository=reminder_repository,
        now=clock.now,
        friend_identifiers=lambda shared_id, viewer_id: ["Olivers"],
    )
    trigger = TurnTrigger(
        trigger_id="inbound:provider:eva-message-1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=inbound.conversation.id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={"text": initial_text, "traceparent": TRACEPARENT},
    )
    return EvaRuntimeFixture(
        clock=clock,
        repository=repository,
        runtime=runtime,
        gate=FakeGatePort(),
        semantic=FakeSemanticInterpreter(),
        memory=FakeMemoryPort(),
        agent=ScriptedAgent(),
        delivery=CapturingDelivery(),
        reminder_repository=reminder_repository,
        reminder_service=reminder_service,
        trigger=trigger,
    )


def _turn_runner(
    env: EvaRuntimeFixture,
    *,
    social_tool: SocialSchedulingToolAdapter | None = None,
    social_service: SocialSchedulingService | None = None,
) -> TurnRunner:
    return TurnRunner(
        conversation_runtime=env.runtime,
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-eva-corpus",
        ),
        pre_llm_gate=PreLLMGateService(env.gate),
        semantic_interpreter=env.semantic,
        memory_port=env.memory,
        interaction_agent=env.agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=env.delivery,
        tool_ports=AgentToolPorts(social_scheduling_tool=social_tool),
        reminder_fire_facts=env.reminder_service,
        staged_command_materializer=StagedCommandMaterializer(
            reminder_tool=None,
            social_scheduling_tool=social_tool,
            calendar_import_tool=None,
            identity_access_tool=None,
            settings_tool=None,
        ),
        social_scheduling_service=social_service,
        now=env.clock.now,
        account_timezone=lambda _account_id: "Asia/Shanghai",
        waiting_retry_jitter=lambda _attempt: 0,
        waiting_retry_sleep=lambda _seconds: None,
    )


def _social_service(
    *,
    names: dict[str, str] | None = None,
    reachable: set[str] | None = None,
) -> tuple[
    SocialSchedulingService,
    InMemorySocialSchedulingRepository,
    FakeReachability,
    FakeReminderAvailability,
]:
    repository = InMemorySocialSchedulingRepository()
    reachability = FakeReachability(reachable)
    availability = FakeReminderAvailability()
    name_map = names or {}
    service = SocialSchedulingService(
        repository=repository,
        reachability=reachability,
        reminder_availability=availability,
        now=lambda: EVA_NOW,
        id_factory=lambda prefix: f"{prefix}_{len(repository.generated_ids) + 1}",
        token_factory=lambda prefix: (
            f"{prefix}_token_{len(repository.generated_tokens) + 1}"
        ),
        display_name_resolver=lambda account_id: name_map.get(account_id, account_id),
    )
    return service, repository, reachability, availability


def _add_friend(
    repository: InMemorySocialSchedulingRepository,
    account_id: str,
    friend_account_id: str,
) -> None:
    low, high = sorted((account_id, friend_account_id))
    repository.add_friendship(
        Friendship(
            id=f"friendship_{account_id}_{friend_account_id}",
            account_low_id=low,
            account_high_id=high,
            lifecycle="active",
            established_at=EVA_NOW,
            removed_at=None,
            created_at=EVA_NOW,
            updated_at=EVA_NOW,
        )
    )


def _open_recoverable_intent(
    repository: InMemorySocialSchedulingRepository,
    *,
    conversation_id: str,
    title: str = "11:40的午饭",
    facts_hash: str = "eva-facts-hash",
) -> RecoverableSchedulingIntent:
    intent = RecoverableSchedulingIntent(
        id="recoverable_eva_zihao",
        conversation_id=conversation_id,
        creator_account_id="account_1",
        operation="shared_reminder_create",
        status="open",
        blocker="unmatched_friend",
        title=title,
        local_trigger_at=datetime(2026, 6, 6, 11, 40),
        captured_timezone="Asia/Shanghai",
        duration_minutes=60,
        unresolved_reference_text="zihao",
        source_turn_id="turn_unmatched_zihao",
        source_input_from_seq=1,
        source_input_to_seq=1,
        source_message_ids=("provider:eva-message-1",),
        facts={"title": title, "unresolved_reference_text": "zihao"},
        facts_hash=facts_hash,
        expires_at=EVA_NOW + timedelta(minutes=15),
        consumed_turn_id=None,
        created_at=EVA_NOW,
        updated_at=EVA_NOW,
    )
    repository.save_recoverable_intent(intent)
    return intent


def _render_trigger(
    env: EvaRuntimeFixture,
    *,
    fire_ids: list[str],
    trigger_id: str = "reminder_fire:eva",
) -> TurnTrigger:
    return TurnTrigger(
        trigger_id=trigger_id,
        trigger_type="ReminderFireTurn",
        mode=TurnMode.RENDER,
        conversation_id=env.trigger.conversation_id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={"fire_ids": fire_ids, "traceparent": TRACEPARENT},
    )


def _add_reminder_fire(
    repository: InMemoryReminderRepository,
    *,
    reminder_id: str,
    fire_id: str,
    title: str,
    due_at: datetime,
    local_timezone: str,
    shared_reminder_id: str = "shared_1",
) -> None:
    reminder = Reminder(
        id=reminder_id,
        owner_account_id="account_1",
        content=title,
        content_hash=f"hash:{reminder_id}",
        kind="shared_projection",
        next_fire_at=due_at,
        recurrence_rule={},
        captured_timezone=local_timezone,
        duration_minutes=45,
        lifecycle="active",
        hidden_from_calendar=False,
        shared_reminder_id=shared_reminder_id,
        created_at=EVA_NOW,
        updated_at=EVA_NOW,
    )
    fire = ReminderFire(
        id=fire_id,
        reminder_id=reminder_id,
        occurrence_key=due_at.isoformat(),
        due_at=due_at,
        fire_state="claimed",
        delivery_result=None,
        handled_at=None,
        completed_at=None,
        missed_catch_up=False,
        created_at=EVA_NOW,
        updated_at=EVA_NOW,
    )
    repository.add_reminder(reminder)
    repository.add_fire(fire)


@pytest.mark.parametrize(
    "title,due_at,local_due_at,bad_segments,expected_text",
    [
        (
            "和eva约11:30的午饭",
            datetime(2026, 6, 6, 3, 30, tzinfo=UTC),
            "2026-06-06T11:30:00+08:00",
            ["和 olivers 的咖啡快到啦，11:40 见~"],
            "和eva约11:30的午饭 2026-06-06 11:30 Asia/Shanghai",
        ),
        (
            "和Olivers约下午两点喝咖啡",
            datetime(2026, 6, 6, 6, 0, tzinfo=UTC),
            "2026-06-06T14:00:00+08:00",
            ["下午3点和 Oliver 喝咖啡在你可约范围内，没问题~"],
            "和Olivers约下午两点喝咖啡 2026-06-06 14:00 Asia/Shanghai",
        ),
        (
            "约olivers下午三点散步",
            datetime(2026, 6, 6, 7, 0, tzinfo=UTC),
            "2026-06-06T15:00:00+08:00",
            ["到时间啦，你和 Oliver 的咖啡局现在开始"],
            "约olivers下午三点散步 2026-06-06 15:00 Asia/Shanghai",
        ),
    ],
)
def test_eva_reminder_fire_uses_hydrated_fact_not_recent_wrong_chat(
    title: str,
    due_at: datetime,
    local_due_at: str,
    bad_segments: list[str],
    expected_text: str,
):
    env = _runtime_fixture(initial_text="下午3点和 Oliver 喝咖啡")
    _add_reminder_fire(
        env.reminder_repository,
        reminder_id="reminder_1",
        fire_id="fire_1",
        title=title,
        due_at=due_at,
        local_timezone="Asia/Shanghai",
    )
    env.agent.queued_results = [
        AgentResult.completed({"type": "reply", "segments": bad_segments}),
        AgentResult.completed({"type": "reply", "segments": bad_segments}),
    ]
    runner = _turn_runner(env)

    result = runner.run_render_turn(
        _render_trigger(env, fire_ids=["fire_1"], trigger_id=f"reminder_fire:{title}")
    )

    assert result.disposition == "replied"
    assert result.visible_text == expected_text
    request = env.agent.requests[-1]
    reminder_fact = request.trusted_facts["domain_result"]["facts"]["reminders"][0]
    assert reminder_fact["title"] == title
    assert reminder_fact["local_due_at"] == local_due_at


def test_eva_zihao_correction_recovers_shared_reminder_without_generic_refusal():
    env = _runtime_fixture(initial_text="zihao就是olivers")
    service, repository, _reachability, _availability = _social_service(
        names={"friend_olivers": "Olivers"},
        reachable={"account_1", "friend_olivers"},
    )
    _add_friend(repository, "account_1", "friend_olivers")
    intent = _open_recoverable_intent(
        repository,
        conversation_id=env.trigger.conversation_id,
        title="11:40的午饭",
    )
    env.semantic.next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
        follow_up_action=FollowUpAction(
            type="resolve_friend_reference_correction",
            prior_reference_text="zihao",
            corrected_friend_text="olivers",
            scope="immediately_preceding_unresolved_intent",
        ),
    )
    env.agent = RecoveringEvaAgent()
    social_tool = SocialSchedulingToolAdapter(service)
    runner = _turn_runner(env, social_tool=social_tool, social_service=service)

    result = runner.run_inbound_turn(env.trigger)

    assert result.disposition == "replied"
    assert result.visible_text is not None
    assert "我没法查看" not in result.visible_text
    assert "只能看和管理你自己的" not in result.visible_text
    assert repository.get_recoverable_intent(intent.id).status == "consumed"
    staged = env.repository.staged_commands_for_turn(result.turn_id)
    assert [command.status for command in staged] == ["materialized"]
    assert repository.list_shared_reminders_for_participant("account_1")
    assert repository.list_shared_reminders_for_participant("friend_olivers")


def test_eva_availability_reply_has_windows_without_activity_labels():
    env = _runtime_fixture(initial_text="看看 olivers 下午有没有空")
    service, repository, _reachability, availability = _social_service(
        names={"friend_olivers": "Olivers"},
        reachable={"account_1", "friend_olivers"},
    )
    _add_friend(repository, "account_1", "friend_olivers")
    availability.intervals["friend_olivers"] = [
        BusyInterval(
            account_id="friend_olivers",
            start=datetime(2026, 6, 6, 14, 0),
            end=datetime(2026, 6, 6, 14, 15),
            source="shared",
            detail_id="和Olivers约下午两点喝咖啡",
        ),
        BusyInterval(
            account_id="friend_olivers",
            start=datetime(2026, 6, 6, 15, 0),
            end=datetime(2026, 6, 6, 15, 15),
            source="shared",
            detail_id="约olivers下午三点散步",
        ),
    ]
    env.semantic.next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="availability_query",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
    )
    env.agent = AvailabilityEvaAgent()
    social_tool = SocialSchedulingToolAdapter(service)
    runner = _turn_runner(env, social_tool=social_tool, social_service=service)

    result = runner.run_inbound_turn(env.trigger)

    assert result.disposition == "replied"
    assert result.visible_text is not None
    assert "14:00-14:15忙" in result.visible_text
    assert "15:00-15:15忙" in result.visible_text
    serialized_facts = str(env.agent.tool_result.facts)
    assert "friend_olivers" in serialized_facts
    assert "Olivers" in serialized_facts
    assert "busy" in serialized_facts
    for forbidden in ("散步", "咖啡", "你们约了散步"):
        assert forbidden not in serialized_facts
        assert forbidden not in result.visible_text


def test_eva_waiting_provider_failure_is_observable_and_final_reply_closes_turn():
    env = _runtime_fixture(initial_text="hey？")
    conversation = env.repository.get_conversation(env.trigger.conversation_id)
    initial_closed_seq = conversation.last_closed_inbound_seq
    env.agent.next_result = AgentResult.timeout(task_id="eva-async")
    env.agent.next_async_result = AgentResult.completed(
        {"type": "reply", "segments": ["最终回复"]}
    )
    env.delivery.fail_waiting_with = "provider_network_error"
    runner = _turn_runner(env)

    pending = runner.run_inbound_turn(env.trigger)

    assert pending.disposition == "pending_async_reply"
    assert env.delivery.deliveries[0].message_type == "waiting"
    assert env.delivery.deliveries[0].delivery_source == "waiting_sync_timeout"
    assert env.delivery.outcomes[0].status == "failed"
    assert env.delivery.outcomes[0].error_code == "provider_network_error"
    assert (
        env.repository.get_conversation(
            env.trigger.conversation_id
        ).last_closed_inbound_seq
        == initial_closed_seq
    )

    final = runner.complete_async_reply(pending.async_task_id)

    assert final.disposition == "replied"
    assert final.visible_text == "最终回复"
    assert env.runtime.get_disposition(final.turn_id).disposition == "replied"


def test_eva_superseded_shared_reminder_soft_success_does_not_materialize_or_send():
    env = _runtime_fixture(initial_text="帮我和 olivers 约下午三点咖啡")
    service, repository, _reachability, _availability = _social_service(
        names={"friend_olivers": "Olivers"},
        reachable={"account_1", "friend_olivers"},
    )
    _add_friend(repository, "account_1", "friend_olivers")
    env.semantic.next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
    )
    env.agent = SupersedingSoftSuccessAgent(env.runtime)
    social_tool = SocialSchedulingToolAdapter(service)
    runner = _turn_runner(env, social_tool=social_tool, social_service=service)

    result = runner.run_inbound_turn(env.trigger)

    assert result.disposition == "superseded"
    assert result.visible_text is None
    assert repository.list_shared_reminders_for_participant("account_1") == []
    staged = env.repository.staged_commands_for_turn(result.turn_id)
    assert [command.status for command in staged] == ["superseded"]
    assert all(
        "等他确认" not in delivery.visible_text for delivery in env.delivery.deliveries
    )
    assert all("邀约" not in delivery.visible_text for delivery in env.delivery.deliveries)
